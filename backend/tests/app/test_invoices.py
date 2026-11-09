"""Invoices end to end, with the Agent API faked: a buyer gets an invoice,
pays a quoted address, the watcher sees the money, and the fee and payee
shares go out one at a time, each on the ledger before it's sent."""

import asyncio
from decimal import Decimal

import psycopg
import pytest
from cryptography.fernet import Fernet

from app.services import fulfilment, invoices, signing
from config import settings
from data_sources.near.agent_api import AgentApiError, Operation, Token
from tests.conftest import make_user

USDC_NEAR = settings.default_settlement_asset
USDC_BASE = "nep141:base-0x833589fcd6edb6e08f4c7c32d4f71b54bda02913.omft.near"
AGENT = "b" * 64


class FakeAgentApi:
    def __init__(self):
        self.deposits: list[dict] = []
        self.transfers: list[dict] = []
        self.statuses: dict[str, Operation] = {}
        self.refuse_transfer: AgentApiError | None = None

    async def tokens(self):
        return [Token(USDC_NEAR, "USDC", 6, "near", 1.0), Token(USDC_BASE, "USDC", 6, "base", 1.0)]

    async def deposit(self, agent_id, *, origin_asset, amount, destination_asset, idempotency_key):
        n = len(self.deposits) + 1
        self.deposits.append({"agent": agent_id, "origin": origin_asset, "amount": amount,
                              "destination": destination_asset, "key": idempotency_key})
        return Operation(f"op_dep_{n}", "deposit", "PENDING_DEPOSIT",
                         details={"deposit_address": f"0xDEPOSIT{n}", "expires_at": "2099-01-01T00:00:00Z"})

    async def transfer(self, agent_id, grant, *, asset, amount, recipient, idempotency_key):
        if self.refuse_transfer:
            raise self.refuse_transfer
        n = len(self.transfers) + 1
        self.transfers.append({"grant": grant, "asset": asset, "amount": amount, "recipient": recipient,
                               "key": idempotency_key})
        return Operation(f"op_tx_{n}", "transfer", "PROCESSING")

    async def status(self, correlation_id, *, wait_ms=0):
        return self.statuses.get(correlation_id, Operation(correlation_id, "deposit", "PENDING_DEPOSIT"))


@pytest.fixture
def api(monkeypatch):
    fake = FakeAgentApi()
    monkeypatch.setattr(signing, "agent_api", lambda: fake)
    monkeypatch.setattr(invoices, "_tokens", (0.0, {}))
    monkeypatch.setattr(settings, "shop_grant_key", Fernet.generate_key().decode())
    return fake


@pytest.fixture
def live_shop(client, api):
    """Shanga Prints, live: a wallet, an encrypted grant, a payee taking 90%
    of what's left after the fee, and two offers on sale."""
    shop = client.post("/api/v1/shops", json={"name": "Shanga Prints"}).json()
    client.put(f"/api/v1/shops/{shop['id']}/payees", json={"payees": [
        {"label": "Founder", "route": "transfer", "address": "kaleb.near", "share_bps": 9000}]})
    url = f"/api/v1/shops/{shop['id']}/offers"
    review = client.post(url, json={"title": "Print-readiness review", "kind": "service", "price_cents": 800,
                                    "floor_cents": 600, "delivery": "markdown"}).json()
    guide = client.post(url, json={"title": "Filament guide", "kind": "digital", "price_cents": 300,
                                   "delivery": "link", "delivery_url": "https://example.com/guide.pdf"}).json()
    for offer in (review, guide):
        client.patch(f"{url}/{offer['id']}", json={"status": "active"})
    grant = signing.encrypt_grant("ngt_secret")
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute("UPDATE shops SET status = 'live', agent_id = %s, grant_id = 'g1', grant_token_enc = %s,"
                     " wallet_account_id = 'f00d' WHERE id = %s", (AGENT, grant, shop["id"]))
    return {"id": shop["id"], "slug": shop["slug"], "review": review["id"], "guide": guide["id"]}


def _buy(client, shop, offer="review", quantity=1):
    return client.post(f"/api/v1/public/shops/{shop['slug']}/invoices",
                       json={"offer_id": shop[offer], "quantity": quantity, "buyer_email": "buyer@example.com",
                             "buyer_name": "Wanjiru"})


def _paid(api, invoice_no: int, amount_out: str):
    api.statuses[f"op_dep_{invoice_no}"] = Operation(
        f"op_dep_{invoice_no}", "deposit", "SUCCESS", details={"amount_out": amount_out, "tx_hash": "nearTx1"})


def _run(coro):
    return asyncio.run(coro)


def _ledger(shop_id):
    with psycopg.connect(settings.database_url) as conn:
        return conn.execute("SELECT kind, status, amount_raw, counterparty FROM ledger_entries WHERE shop_id = %s"
                            " ORDER BY created_at, kind", (shop_id,)).fetchall()


def test_the_shop_page_shows_offers_on_sale_and_the_coins_it_takes(client, live_shop):
    client.sign_out()
    page = client.get(f"/api/v1/public/shops/{live_shop['slug']}").json()
    assert page["selling"] is True
    assert [o["title"] for o in page["offers"]] == ["Print-readiness review", "Filament guide"]
    assert {(p["symbol"], p["chain"]) for p in page["pay_options"]} == {("USDC", "near"), ("USDC", "base")}
    assert "delivery_url" not in str(page)


def test_a_draft_shop_has_no_public_page(client, api):
    shop = client.post("/api/v1/shops", json={"name": "Not yet"}).json()
    assert client.get(f"/api/v1/public/shops/{shop['slug']}").status_code == 404


def test_invoices_are_numbered_per_shop_and_keep_the_fee_in_force(client, live_shop):
    first, second = _buy(client, live_shop).json(), _buy(client, live_shop, quantity=3).json()
    assert (first["number"], second["number"]) == ("SP-0001", "SP-0002")
    assert (second["total_cents"], second["status"], second["payment"]) == (2400, "open", None)
    with psycopg.connect(settings.database_url) as conn:
        assert conn.execute("SELECT DISTINCT fee_bps FROM invoices").fetchall() == [(settings.platform_fee_bps,)]


def test_paying_quotes_one_address_for_the_exact_total(client, live_shop, api):
    invoice = _buy(client, live_shop, quantity=2).json()
    paying = client.post(f"/api/v1/public/invoices/{invoice['public_token']}/pay", json={"pay_asset": USDC_BASE})
    body = paying.json()
    assert body["status"] == "awaiting_payment"
    assert (body["payment"]["address"], body["payment"]["amount"], body["payment"]["chain"]) == (
        "0xDEPOSIT1", "16.000000", "base")
    assert api.deposits[0] == {"agent": AGENT, "origin": USDC_BASE, "amount": "16000000", "destination": USDC_NEAR,
                               "key": api.deposits[0]["key"]}
    again = client.post(f"/api/v1/public/invoices/{invoice['public_token']}/pay", json={"pay_asset": USDC_NEAR})
    assert again.status_code == 409


def test_a_coin_the_shop_doesnt_take_is_refused(client, live_shop):
    invoice = _buy(client, live_shop).json()
    assert client.post(f"/api/v1/public/invoices/{invoice['public_token']}/pay",
                       json={"pay_asset": "nep141:wrap.near"}).status_code == 422


def test_a_paid_invoice_pays_the_fee_then_the_payee_one_at_a_time(client, live_shop, api):
    invoice = _buy(client, live_shop).json()
    client.post(f"/api/v1/public/invoices/{invoice['public_token']}/pay", json={"pay_asset": USDC_BASE})
    _paid(api, 1, "7990000")  # $7.99 credited after the route's conversion

    assert _run(invoices.watch_invoices()) == 1
    page = client.get(f"/api/v1/public/invoices/{invoice['public_token']}").json()
    assert page["status"] == "paid" and page["payment_tx_url"].endswith("/nearTx1")
    assert page["delivery"]["deliverable"] is None

    _run(fulfilment.fulfil())
    # The fee off the top (2% of 7.99 = 0.1598), the payee's 90% of the rest.
    assert _ledger(live_shop["id"]) == [
        ("sale", "done", Decimal(7990000), "buyer@example.com"),
        ("fee", "pending", Decimal(159800), settings.near_mainnet_platform_treasury_wallet_address),
        ("payout", "pending", Decimal(7047180), "kaleb.near")]
    # Only one money action in flight for this wallet: the fee goes first.
    assert [(t["recipient"], t["amount"], t["grant"]) for t in api.transfers] == [
        (settings.near_mainnet_platform_treasury_wallet_address, "159800", "ngt_secret")]

    api.statuses["op_tx_1"] = Operation("op_tx_1", "transfer", "SUCCESS", details={"tx_hash": "feeTx"})
    _run(fulfilment.fulfil())
    assert [t["recipient"] for t in api.transfers] == [settings.near_mainnet_platform_treasury_wallet_address,
                                                       "kaleb.near"]
    api.statuses["op_tx_2"] = Operation("op_tx_2", "transfer", "SUCCESS", details={"tx_hash": "payTx"})
    _run(fulfilment.fulfil())
    assert [row[1] for row in _ledger(live_shop["id"])] == ["done", "done", "done"]
    # Nothing is planned or sent twice.
    _run(fulfilment.fulfil())
    assert len(api.transfers) == 2


def test_a_busy_wallet_waits_and_a_refusal_fails_the_line(client, live_shop, api):
    invoice = _buy(client, live_shop).json()
    client.post(f"/api/v1/public/invoices/{invoice['public_token']}/pay", json={"pay_asset": USDC_NEAR})
    _paid(api, 1, "8000000")
    _run(invoices.watch_invoices())
    api.refuse_transfer = AgentApiError("wallet_busy", status=409)
    _run(fulfilment.fulfil())
    assert {row[1] for row in _ledger(live_shop["id"]) if row[0] != "sale"} == {"pending"}
    api.refuse_transfer = AgentApiError("policy_destination_denied", status=403, layer="policy")
    _run(fulfilment.fulfil())
    assert ("fee", "failed") in {(row[0], row[1]) for row in _ledger(live_shop["id"])}


def test_an_expired_quote_is_paid_again_under_the_same_number(client, live_shop, api):
    invoice = _buy(client, live_shop).json()
    token = invoice["public_token"]
    client.post(f"/api/v1/public/invoices/{token}/pay", json={"pay_asset": USDC_BASE})
    api.statuses["op_dep_1"] = Operation("op_dep_1", "deposit", "FAILED", failure_code="deposit_expired")
    _run(invoices.watch_invoices())
    assert client.get(f"/api/v1/public/invoices/{token}").json()["status"] == "expired"
    again = client.post(f"/api/v1/public/invoices/{token}/pay", json={"pay_asset": USDC_BASE}).json()
    assert (again["number"], again["status"], again["payment"]["address"]) == ("SP-0001", "awaiting_payment",
                                                                               "0xDEPOSIT2")
    assert api.deposits[0]["key"] != api.deposits[1]["key"]


def test_a_refund_says_where_the_money_went(client, live_shop, api):
    invoice = _buy(client, live_shop).json()
    client.post(f"/api/v1/public/invoices/{invoice['public_token']}/pay", json={"pay_asset": USDC_BASE})
    api.statuses["op_dep_1"] = Operation("op_dep_1", "deposit", "REFUNDED", failure_code="amount_mismatch",
                                         details={"refund_tx_hash": "refundTx"})
    _run(invoices.watch_invoices())
    page = client.get(f"/api/v1/public/invoices/{invoice['public_token']}").json()
    assert (page["status"], page["refund_tx_hash"], page["delivery"]) == ("refunded", "refundTx", None)


def test_a_link_offer_is_delivered_as_soon_as_it_is_paid(client, live_shop, api):
    invoice = _buy(client, live_shop, offer="guide").json()
    client.post(f"/api/v1/public/invoices/{invoice['public_token']}/pay", json={"pay_asset": USDC_NEAR})
    _paid(api, 1, "3000000")
    _run(invoices.watch_invoices())
    page = client.get(f"/api/v1/public/invoices/{invoice['public_token']}").json()
    assert (page["status"], page["delivery"]["url"]) == ("delivered", "https://example.com/guide.pdf")


def test_the_owner_delivers_a_written_review_once_paid(client, live_shop, api):
    invoice = _buy(client, live_shop).json()
    shop_invoices = client.get(f"/api/v1/shops/{live_shop['id']}/invoices").json()
    deliver = f"/api/v1/shops/{live_shop['id']}/invoices/{shop_invoices[0]['id']}/deliver"
    assert client.post(deliver, json={"deliverable": "Looks good"}).status_code == 409
    client.post(f"/api/v1/public/invoices/{invoice['public_token']}/pay", json={"pay_asset": USDC_NEAR})
    _paid(api, 1, "8000000")
    _run(invoices.watch_invoices())
    done = client.post(deliver, json={"deliverable": "## Review\nWall thickness is fine."}).json()
    assert done["status"] == "delivered"
    page = client.get(f"/api/v1/public/invoices/{invoice['public_token']}").json()
    assert page["delivery"]["deliverable"].startswith("## Review")


def test_the_public_ledger_hides_buyers_and_the_csv_reads_plainly(client, live_shop, api):
    invoice = _buy(client, live_shop).json()
    client.post(f"/api/v1/public/invoices/{invoice['public_token']}/pay", json={"pay_asset": USDC_NEAR})
    _paid(api, 1, "8000000")
    _run(invoices.watch_invoices())
    _run(fulfilment.fulfil())
    public = client.get(f"/api/v1/public/shops/{live_shop['slug']}/ledger").json()
    assert "buyer@example.com" not in str(public)
    csv = client.get(f"/api/v1/shops/{live_shop['id']}/ledger.csv").text.splitlines()
    assert csv[0].startswith("Date (UTC),Shop,Invoice,Type")
    assert any(",Platform fee," in line and ",-0.16," in line for line in csv)


def test_a_stranger_cannot_read_a_shops_invoices_or_ledger(client, live_shop):
    client.sign_in(make_user("Stranger"))
    assert client.get(f"/api/v1/shops/{live_shop['id']}/invoices").status_code == 404
    assert client.get(f"/api/v1/shops/{live_shop['id']}/ledger.csv").status_code == 404


def test_too_many_invoices_from_one_network_are_refused(client, live_shop, monkeypatch):
    monkeypatch.setattr(settings, "invoices_per_ip_per_hour", 2)
    assert [_buy(client, live_shop).status_code for _ in range(3)] == [201, 201, 429]


def test_the_split_never_sends_more_than_was_credited():
    payee = type("P", (), {"share_bps": 3333})
    fee, shares = fulfilment.split(Decimal(1000001), 200, [payee, payee, payee])
    assert fee + sum(a for _, a in shares) <= 1000001
    assert fee == 20000


def test_an_invoice_number_comes_from_the_shops_initials():
    assert invoices.invoice_prefix("shanga-prints") == "SP"
    assert invoices.invoice_prefix("shanga-cad-studio") == "SCS"
    assert invoices.invoice_prefix("kiosk") == "KIO"
