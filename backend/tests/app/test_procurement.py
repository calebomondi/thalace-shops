"""Shops buying from shops, and the controls around a live wallet: new rules
signed by the owner (payees, cap, allowed suppliers), the freeze, pausing,
and a purchase paid by an Intents transfer that settles the supplier's
invoice."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from cryptography.fernet import Fernet
from langchain_core.messages import AIMessage

from app.services import fulfilment, group_orders, invoices, shop_agent, signing
from config import settings
from data_sources.near.agent_api import GeneratedIntent, Operation
from tests.app.test_invoices import FakeAgentApi
from tests.conftest import make_user

SUPPLIER_WALLET = "5" * 64
BUYER_WALLET = "6" * 64


class FakeApi(FakeAgentApi):
    """Payments and owner intents, each intent succeeding once submitted."""

    def __init__(self):
        super().__init__()
        self.generated: list[tuple[str, dict]] = []

    async def generate_intent(self, kind, fields, *, idempotency_key=None):
        self.generated.append((kind, fields))
        return GeneratedIntent(correlation_id=f"intent_{kind}_{len(self.generated)}", type=kind,
                               expires_at="2099-01-01T00:00:00Z", intent={"standard": "webauthn", "payload": {}},
                               preview={"summary": kind})

    async def submit_intent(self, kind, correlation_id, signed_data):
        return None

    async def policy(self, agent_id):
        return {"revision": 3}

    async def status(self, correlation_id, *, wait_ms=0):
        if correlation_id.startswith("intent_"):
            return Operation(correlation_id, correlation_id.split("_")[1], "SUCCESS", details={"revision": 4})
        return await super().status(correlation_id, wait_ms=wait_ms)


@pytest.fixture
def api(monkeypatch):
    fake = FakeApi()
    monkeypatch.setattr(signing, "agent_api", lambda: fake)
    monkeypatch.setattr(invoices, "_tokens", (0.0, {}))
    monkeypatch.setattr(settings, "shop_grant_key", Fernet.generate_key().decode())
    return fake


def _live_shop(client, name, wallet, price=500):
    shop = client.post("/api/v1/shops", json={"name": name}).json()
    url = f"/api/v1/shops/{shop['id']}/offers"
    offer = client.post(url, json={"title": f"{name} special", "kind": "digital", "price_cents": price,
                                   "floor_cents": 300, "delivery": "markdown"}).json()
    client.patch(f"{url}/{offer['id']}", json={"status": "active"})
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute("UPDATE shops SET status = 'live', agent_id = %s, grant_id = 'g', grant_token_enc = %s,"
                     " wallet_account_id = %s, live_since = now() WHERE id = %s",
                     (wallet[:64], signing.encrypt_grant("ngt_x"), wallet, shop["id"]))
    return {"id": shop["id"], "slug": shop["slug"], "offer": offer["id"]}


@pytest.fixture
def shops(client, api, user):
    supplier_owner = make_user("Supplier")
    client.sign_in(supplier_owner)
    supplier = _live_shop(client, "Shanga Creative Lab", SUPPLIER_WALLET)
    client.sign_in(user)
    buyer = _live_shop(client, "Shanga Prints", BUYER_WALLET)
    return {"supplier": supplier, "buyer": buyer, "supplier_owner": supplier_owner}


def _sign(client, shop_id, pending):
    assert pending.status_code == 201, pending.text
    body = pending.json()
    done = client.post(f"/api/v1/shops/{shop_id}/signatures/{body['correlation_id']}",
                       json={"signed_data": {**body["intent"], "credential": {}}})
    assert done.status_code == 200, done.text
    return done.json()


def _allow(client, shops):
    return _sign(client, shops["buyer"]["id"], client.post(
        f"/api/v1/shops/{shops['buyer']['id']}/wallet/rules",
        json={"payees": [{"label": "Founder", "route": "transfer", "address": "kaleb.near", "share_bps": 5000}],
              "daily_budget_usd": "30", "supplier_shop_ids": [shops["supplier"]["id"]]}))


def _ledger(shop_id):
    with psycopg.connect(settings.database_url) as conn:
        return conn.execute("SELECT kind, status, counterparty FROM ledger_entries WHERE shop_id = %s"
                            " ORDER BY created_at", (shop_id,)).fetchall()


def test_signed_new_rules_add_payees_a_cap_and_a_supplier(client, shops, api):
    done = _allow(client, shops)
    assert done["status"] == "succeeded" and done["shop"]["daily_budget_usd"] == "30.00"
    kind, fields = api.generated[-1]
    assert (kind, fields["expected_revision"]) == ("policy_update", 3)
    addresses = [d["address"] for d in fields["policy"]["destinations"]["list"]]
    assert addresses == [settings.near_mainnet_platform_treasury_wallet_address, "kaleb.near", SUPPLIER_WALLET]
    assert [s["name"] for s in client.get(f"/api/v1/shops/{shops['buyer']['id']}/suppliers").json()] == [
        "Shanga Creative Lab"]
    assert [p["address"] for p in client.get(f"/api/v1/shops/{shops['buyer']['id']}/payees").json()] == [
        "kaleb.near"]


def test_a_supplier_must_be_a_live_shop(client, shops):
    draft = client.post("/api/v1/shops", json={"name": "Not live"}).json()
    refused = client.post(f"/api/v1/shops/{shops['buyer']['id']}/wallet/rules",
                          json={"payees": [], "daily_budget_usd": "30", "supplier_shop_ids": [draft["id"]]})
    assert refused.status_code == 422


async def _buy(shop_id, offer_id, quantity=2):
    return await shop_agent.DbShopStore(uuid.UUID(shop_id)).buy(uuid.UUID(offer_id), quantity)


def test_buying_needs_the_supplier_allowed_in_the_signed_rules(client, shops):
    with pytest.raises(shop_agent.PurchaseRefusedError, match="allowed suppliers"):
        asyncio.run(_buy(shops["buyer"]["id"], shops["supplier"]["offer"]))


def test_a_purchase_is_paid_by_transfer_and_settles_the_suppliers_invoice(client, shops, api):
    _allow(client, shops)
    purchase = asyncio.run(_buy(shops["buyer"]["id"], shops["supplier"]["offer"]))
    assert (purchase.total_usd, purchase.status, purchase.supplier) == ("10.00", "awaiting_payment",
                                                                        "Shanga Creative Lab")
    asyncio.run(fulfilment.fulfil())
    assert [(t["recipient"], t["amount"]) for t in api.transfers] == [(SUPPLIER_WALLET, "10000000")]

    api.statuses["op_tx_1"] = Operation("op_tx_1", "transfer", "SUCCESS", details={"tx_hash": "buyTx"})
    asyncio.run(fulfilment.fulfil())
    assert _ledger(shops["buyer"]["id"]) == [("purchase", "done", SUPPLIER_WALLET)]
    # The supplier was paid: a sale, then its own fee goes out from its wallet.
    supplier_lines = _ledger(shops["supplier"]["id"])
    assert supplier_lines[0][:2] == ("sale", "done")
    assert ("fee", "pending", settings.near_mainnet_platform_treasury_wallet_address) in supplier_lines
    assert api.transfers[-1]["recipient"] == settings.near_mainnet_platform_treasury_wallet_address


def test_a_frozen_wallet_buys_nothing_and_sends_nothing(client, shops, api):
    _allow(client, shops)
    frozen = _sign(client, shops["buyer"]["id"], client.post(f"/api/v1/shops/{shops['buyer']['id']}/wallet/freeze",
                                                              json={"freeze": True}))
    assert frozen["shop"]["frozen"] is True
    with pytest.raises(shop_agent.PurchaseRefusedError, match="frozen"):
        asyncio.run(_buy(shops["buyer"]["id"], shops["supplier"]["offer"]))
    thawed = _sign(client, shops["buyer"]["id"], client.post(f"/api/v1/shops/{shops['buyer']['id']}/wallet/freeze",
                                                              json={"freeze": False}))
    assert thawed["shop"]["frozen"] is False


def test_pausing_stops_new_invoices_at_once(client, shops):
    shop = shops["buyer"]
    assert client.post(f"/api/v1/shops/{shop['id']}/pause").json()["status"] == "paused"
    issue = {"offer_id": shop["offer"], "quantity": 1, "buyer_email": "a@example.com"}
    assert client.post(f"/api/v1/public/shops/{shop['slug']}/invoices", json=issue).status_code == 409
    client.post(f"/api/v1/shops/{shop['id']}/resume")
    assert client.post(f"/api/v1/public/shops/{shop['slug']}/invoices", json=issue).status_code == 201


def test_a_shop_in_a_group_order_pays_from_its_wallet_at_the_close(client, shops, api):
    _allow(client, shops)
    supplier = shops["supplier"]
    client.sign_in(shops["supplier_owner"])
    client.put(f"/api/v1/shops/{supplier['id']}/offers/{supplier['offer']}/group-buying",
               json={"enabled": True, "window_hours": 24, "tiers": [{"min_quantity": 5, "unit_price_cents": 400}]})
    opened = client.post("/api/v1/public/group-orders", json={
        "offer_id": supplier["offer"], "quantity": 3, "hours": 1, "buyer_name": "A person",
        "buyer_email": "p@example.com"}).json()
    group_id = opened["group_order"]["group_order_id"]
    joined = asyncio.run(shop_agent.DbShopStore(uuid.UUID(shops["buyer"]["id"])).join_group_order(group_id, 2))
    assert joined.unit_price_usd == "4.00"
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute("UPDATE group_orders SET deadline = %s", (datetime.now(UTC) - timedelta(seconds=1),))
    asyncio.run(group_orders.close_due())
    # The shop's invoice (2 × $4) is queued from its wallet; the person pays their own.
    lines = _ledger(shops["buyer"]["id"])
    assert lines == [("purchase", "pending", SUPPLIER_WALLET)]


def test_the_shop_agent_buys_with_its_tool(client, shops, api):
    _allow(client, shops)
    script = [AIMessage(content="", tool_calls=[{"id": "c1", "name": "buy_from_supplier",
                                                 "args": {"offer_id": shops["supplier"]["offer"], "quantity": 1}}]),
              AIMessage(content="Bought one from Shanga Creative Lab.")]

    async def run():
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        from app.database.models import Shop
        engine = create_async_engine(settings.sqlalchemy_database_url, poolclass=NullPool)
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            shop = await db.get(Shop, uuid.UUID(shops["buyer"]["id"]))
            turn = await shop_agent.run_turn(db, shop, shop.owner_id, "Buy one special from the Creative Lab",
                                             model_step=lambda m, t: script.pop(0))
        await engine.dispose()
        return turn

    turn = asyncio.run(run())
    assert turn[-1]["actions"] == ["buy_from_supplier"]
    assert _ledger(shops["buyer"]["id"]) == [("purchase", "pending", SUPPLIER_WALLET)]
