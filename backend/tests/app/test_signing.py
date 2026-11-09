"""Going live: the founder adds one passkey for this site, then signs each
shop's wallet into being and grants our backend access, each request relayed
unchanged. The policy holds the owner's rules plus the fee account, the grant
token is stored encrypted, and only the person a request was made for submits
it. Ported from the gtmx Store's tests."""

import hashlib

import psycopg
import pytest
from cryptography.fernet import Fernet

from app.services import signing
from config import settings
from data_sources.near.agent_api import AgentApiError, GeneratedIntent, Operation
from tests.conftest import make_user

SITE = "https://shops.thalace.test"
PASSKEY = {"credential_id": "Y3JlZC0x", "public_key": "M" + "A" * 90, "rp_id": "shops.thalace.test", "origin": SITE}
AGENT = "a" * 64


class FakeAgentApi:
    """Answers like the Agent API: each owner request succeeds once submitted."""

    def __init__(self):
        self.generated: list[tuple[str, dict]] = []
        self.submitted: list[tuple[str, str, dict]] = []
        self.refuse: AgentApiError | None = None
        self.agents = 0

    async def generate_intent(self, kind, fields, *, idempotency_key=None):
        if self.refuse:
            raise self.refuse
        self.generated.append((kind, fields))
        n = len(self.generated)
        return GeneratedIntent(correlation_id=f"intent_{kind}_{n}", type=kind, expires_at="2099-01-01T00:00:00Z",
                               intent={"standard": "webauthn", "payload": {"challenge": "abc"}},
                               preview={"summary": f"Sign {kind}"})

    async def submit_intent(self, kind, correlation_id, signed_data):
        self.submitted.append((kind, correlation_id, signed_data))

    async def status(self, correlation_id, *, wait_ms=0):
        if correlation_id.startswith("intent_agent_create"):
            self.agents += 1
            return Operation(correlation_id, "agent_create", "SUCCESS", agent_id=f"{self.agents}" * 64,
                             details={"revision": 1})
        return Operation(correlation_id, "grant_issue", "SUCCESS",
                         details={"grant": {"grant_id": f"g-{correlation_id}", "expires_at": "2027-05-01T00:00:00Z"}})

    async def agent(self, agent_id):
        return {"id": agent_id, "wallet": {"near_account_id": "f00d" * 16},
                "owner_account": {"account_id": "0s" + "1" * 40}}


@pytest.fixture
def agent_api(monkeypatch):
    fake = FakeAgentApi()
    monkeypatch.setattr(signing, "agent_api", lambda: fake)
    monkeypatch.setattr(settings, "shop_grant_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "frontend_base_url", SITE)
    return fake


def _shop(client, name="Shanga Prints"):
    shop = client.post("/api/v1/shops", json={"name": name}).json()
    client.put(f"/api/v1/shops/{shop['id']}/payees", json={"payees": [
        {"label": "Founder", "route": "transfer", "address": "kaleb.near", "share_bps": 7000},
        {"label": "Designer", "route": "withdraw", "chain": "base", "address": "0xabc1", "share_bps": 2000}]})
    client.put(f"/api/v1/shops/{shop['id']}/budget", json={"daily_budget_usd": "50"})
    return shop["id"]


def _sign(client, shop_id):
    pending = client.post(f"/api/v1/shops/{shop_id}/signatures")
    assert pending.status_code == 201, pending.text
    body = pending.json()
    signed = {**body["intent"], "credential": {"id": "Y3JlZC0x", "response": {"signature": "sig"}}}
    return body, client.post(f"/api/v1/shops/{shop_id}/signatures/{body['correlation_id']}",
                             json={"signed_data": signed})


def _grant_token_enc(shop_id):
    with psycopg.connect(settings.database_url) as conn:
        return conn.execute("SELECT grant_token_enc FROM shops WHERE id = %s", (shop_id,)).fetchone()[0]


def test_the_passkey_must_be_for_this_site(client, agent_api):
    assert client.get("/api/v1/passkeys/current").json() == {"has_passkey": False, "rp_id": "shops.thalace.test",
                                                              "origin": SITE}
    other = {**PASSKEY, "origin": "https://evil.test", "rp_id": "evil.test"}
    assert client.post("/api/v1/passkeys", json=other).status_code == 422
    assert client.post("/api/v1/passkeys", json=PASSKEY).status_code == 201
    assert client.get("/api/v1/passkeys/current").json()["has_passkey"] is True
    assert client.post("/api/v1/passkeys", json=PASSKEY).status_code == 409


def test_two_signatures_take_the_shop_live(client, agent_api):
    client.post("/api/v1/passkeys", json=PASSKEY)
    shop_id = _shop(client)

    created, done = _sign(client, shop_id)
    assert created["type"] == "agent_create" and created["preview"]["summary"] == "Sign agent_create"
    assert done.json()["status"] == "succeeded"
    shop = done.json()["shop"]
    assert (shop["status"], shop["wallet_open"], shop["wallet_account_id"]) == ("draft", True, "f00d" * 16)

    granted, done = _sign(client, shop_id)
    assert granted["type"] == "grant_issue"
    shop = done.json()["shop"]
    assert shop["status"] == "live" and shop["live_since"]
    assert "grant" not in str(shop)

    # The owner signed the commitment of the very token we keep, encrypted.
    token = Fernet(settings.shop_grant_key.encode()).decrypt(_grant_token_enc(shop_id).encode()).decode()
    assert token.startswith("ngt_")
    assert agent_api.generated[1][1]["credential"] == hashlib.sha256(token.encode()).hexdigest()
    # The browser's signature went to the API as it was.
    assert agent_api.submitted[0][2]["credential"]["response"]["signature"] == "sig"
    assert client.post(f"/api/v1/shops/{shop_id}/signatures").status_code == 409


def test_the_policy_holds_the_owners_rules_and_the_fee_account(client, agent_api):
    client.post("/api/v1/passkeys", json=PASSKEY)
    _sign(client, _shop(client))
    _, fields = agent_api.generated[0]
    assert fields["owner"] == {"type": "passkey", **PASSKEY}
    policy = fields["policy"]
    assert policy["destinations"] == {"mode": "only", "list": [
        {"action": "transfer", "address": settings.near_mainnet_platform_treasury_wallet_address,
         "confidential": False},
        {"action": "transfer", "address": "kaleb.near", "confidential": False},
        {"action": "withdraw", "chain": "base", "address": "0xabc1", "memo": None}]}
    assert policy["budget"]["daily_usd"] == "50.00"
    assert policy["assets"] == [settings.default_settlement_asset]
    assert set(policy["actions"]) == {"transfer", "withdraw"}


def test_one_passkey_owns_every_shop_with_a_wallet_each(client, agent_api):
    client.post("/api/v1/passkeys", json=PASSKEY)
    for name in ("Shanga CAD Studio", "Shanga Prints"):
        shop_id = _shop(client, name)
        _sign(client, shop_id)
        _sign(client, shop_id)
    owners = [f["owner"]["credential_id"] for kind, f in agent_api.generated if kind == "agent_create"]
    assert owners == [PASSKEY["credential_id"]] * 2
    assert {s["status"] for s in client.get("/api/v1/shops").json()} == {"live"}


def test_once_the_wallet_exists_its_rules_are_fixed(client, agent_api):
    client.post("/api/v1/passkeys", json=PASSKEY)
    shop_id = _shop(client)
    _sign(client, shop_id)
    assert client.put(f"/api/v1/shops/{shop_id}/payees", json={"payees": []}).status_code == 409
    assert client.put(f"/api/v1/shops/{shop_id}/budget", json={"daily_budget_usd": "10"}).status_code == 409


def test_no_signature_without_a_passkey(client, agent_api):
    assert client.post(f"/api/v1/shops/{_shop(client)}/signatures").status_code == 409


def test_only_the_owner_signs_and_only_their_own_request(client, agent_api):
    client.post("/api/v1/passkeys", json=PASSKEY)
    shop_id = _shop(client)
    pending = client.post(f"/api/v1/shops/{shop_id}/signatures").json()
    client.sign_in(make_user("Stranger"))
    assert client.post(f"/api/v1/shops/{shop_id}/signatures").status_code == 404
    assert client.post(f"/api/v1/shops/{shop_id}/signatures/{pending['correlation_id']}",
                       json={"signed_data": {}}).status_code == 404


def test_a_refusal_from_near_intents_is_a_conflict(client, agent_api):
    client.post("/api/v1/passkeys", json=PASSKEY)
    shop_id = _shop(client)
    agent_api.refuse = AgentApiError("owner_type_unsupported", status=400)
    refused = client.post(f"/api/v1/shops/{shop_id}/signatures")
    assert refused.status_code == 409 and "owner_type_unsupported" in refused.text


def test_without_a_grant_key_nothing_goes_live(client, agent_api, monkeypatch):
    monkeypatch.setattr(settings, "shop_grant_key", "")
    client.post("/api/v1/passkeys", json=PASSKEY)
    shop_id = _shop(client)
    _sign(client, shop_id)
    refused = client.post(f"/api/v1/shops/{shop_id}/signatures")
    assert refused.status_code == 409 and "aren't complete" in refused.text
