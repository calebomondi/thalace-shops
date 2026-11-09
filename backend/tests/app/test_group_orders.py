"""Group orders, rule by rule (docs/RULES.md): the seller's tiers, one open
group order per offer, joining until the deadline, and the close that locks
the price at the tier reached and invoices each member."""

import asyncio
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from app.services import group_orders, invoices, signing
from config import settings
from tests.app.test_invoices import FakeAgentApi
from tests.app.test_negotiation_mcp import call
from tests.conftest import make_user


@pytest.fixture
def api(monkeypatch):
    fake = FakeAgentApi()
    monkeypatch.setattr(signing, "agent_api", lambda: fake)
    monkeypatch.setattr(invoices, "_tokens", (0.0, {}))
    return fake


@pytest.fixture
def shop(client, api):
    shop = client.post("/api/v1/shops", json={"name": "Shanga Prints"}).json()
    url = f"/api/v1/shops/{shop['id']}/offers"
    offer = client.post(url, json={"title": "Engraved nameplate", "kind": "service", "price_cents": 1000,
                                   "floor_cents": 500, "delivery": "service"}).json()
    client.patch(f"{url}/{offer['id']}", json={"status": "active"})
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute("UPDATE shops SET status = 'live', agent_id = %s, grant_id = 'g1' WHERE id = %s",
                     ("d" * 64, shop["id"]))
    return {"id": shop["id"], "offer": offer["id"], "tiers_url": f"{url}/{offer['id']}/group-buying"}


TIERS = [{"min_quantity": 5, "unit_price_cents": 800}, {"min_quantity": 10, "unit_price_cents": 600}]


def _turn_on(client, shop, tiers=TIERS, hours=72):
    return client.put(shop["tiers_url"], json={"enabled": True, "window_hours": hours, "tiers": tiers})


def _open(client, shop, quantity=2, hours=1.0, name="Event planner"):
    return client.post("/api/v1/public/group-orders", json={
        "offer_id": shop["offer"], "quantity": quantity, "hours": hours, "buyer_name": name,
        "buyer_email": "planner@example.com"})


def _join(client, group_id, quantity, name):
    return client.post(f"/api/v1/public/group-orders/{group_id}/join", json={
        "quantity": quantity, "buyer_name": name, "buyer_email": f"{name.split()[0].lower()}@example.com"})


def _expire(group_id):
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute("UPDATE group_orders SET deadline = %s WHERE public_token = %s",
                     (datetime.now(UTC) - timedelta(seconds=1), group_id))


def test_the_seller_sets_tiers_that_step_down_and_stay_above_the_floor(client, shop):
    assert [t["min_quantity"] for t in _turn_on(client, shop).json()["tiers"]] == [1, 5, 10]
    assert _turn_on(client, shop, [{"min_quantity": 5, "unit_price_cents": 400}]).status_code == 422  # below floor
    assert _turn_on(client, shop, [{"min_quantity": 5, "unit_price_cents": 1100}]).status_code == 422  # not lower
    assert _turn_on(client, shop, [{"min_quantity": 5, "unit_price_cents": 800},
                                   {"min_quantity": 10, "unit_price_cents": 900}]).status_code == 422
    assert _turn_on(client, shop, []).status_code == 422  # on needs a tier
    assert _turn_on(client, shop, hours=500).status_code == 422


def test_an_offer_without_group_buying_takes_no_group_order(client, shop):
    assert _open(client, shop).status_code == 409


def test_one_open_group_order_per_offer(client, shop):
    _turn_on(client, shop)
    assert _open(client, shop).status_code == 201
    assert _open(client, shop, name="Someone else").status_code == 409


def test_the_deadline_is_within_the_sellers_window(client, shop):
    _turn_on(client, shop, hours=24)
    assert _open(client, shop, hours=48).status_code == 422
    assert _open(client, shop, hours=0.05).status_code == 422  # under 10 minutes


def test_the_price_drops_as_members_join_and_locks_at_the_close(client, shop):
    _turn_on(client, shop)
    opened = _open(client, shop, quantity=3).json()
    group_id = opened["group_order"]["group_order_id"]
    assert (opened["group_order"]["unit_price_cents"], opened["group_order"]["next_tier"]["min_quantity"]) == (1000, 5)
    _join(client, group_id, 4, "Wanjiru school")
    after = _join(client, group_id, 5, "Kamau club").json()["group_order"]
    assert (after["committed_quantity"], after["unit_price_cents"], after["next_tier"]) == (12, 600, None)

    _expire(group_id)
    assert asyncio.run(group_orders.close_due()) == 1
    closed = client.get(f"/api/v1/public/group-orders/{group_id}").json()
    assert (closed["status"], closed["unit_price_cents"]) == ("closed", 600)
    with psycopg.connect(settings.database_url) as conn:
        invoiced = conn.execute("SELECT buyer_name, quantity, unit_price_cents, total_cents FROM invoices").fetchall()
    # One invoice each, all at the locked price; their order isn't a rule.
    assert sorted(invoiced) == [("Event planner", 3, 600, 1800), ("Kamau club", 5, 600, 3000),
                                ("Wanjiru school", 4, 600, 2400)]
    # Each member finds their own invoice by their member token.
    member = client.get(f"/api/v1/public/memberships/{opened['member_token']}").json()
    assert member["invoice_token"] and client.get(f"/api/v1/public/invoices/{member['invoice_token']}").json()[
        "total_cents"] == 1800


def test_no_joining_after_the_deadline(client, shop):
    _turn_on(client, shop)
    group_id = _open(client, shop).json()["group_order"]["group_order_id"]
    _expire(group_id)
    assert _join(client, group_id, 1, "Late comer").status_code == 409


def test_a_closed_shop_cancels_its_group_order(client, shop):
    _turn_on(client, shop)
    group_id = _open(client, shop).json()["group_order"]["group_order_id"]
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute("UPDATE shops SET status = 'paused' WHERE id = %s", (shop["id"],))
    _expire(group_id)
    asyncio.run(group_orders.close_due())
    assert client.get(f"/api/v1/public/group-orders/{group_id}").json()["status"] == "cancelled"


def test_the_market_never_shows_members_invoices(client, shop):
    _turn_on(client, shop)
    _open(client, shop)
    client.sign_out()
    market = client.get("/api/v1/public/market").json()
    assert len(market) == 1 and all(m["invoice_token"] is None for m in market[0]["members"])


def test_agents_open_join_and_pay_through_mcp(client, shop, api):
    _turn_on(client, shop)
    opened = call(client, "open_group_order", offer_id=shop["offer"], quantity=6, hours=1, buyer_name="Bot A")
    assert (opened["unit_price_cents"], opened["members"]) == (800, 1)
    listed = call(client, "list_group_orders")
    assert [g["group_order_id"] for g in listed] == [opened["group_order_id"]]
    joined = call(client, "join_group_order", group_order_id=opened["group_order_id"], quantity=4,
                  buyer_name="Bot B")
    assert joined["unit_price_cents"] == 600

    _expire(opened["group_order_id"])
    asyncio.run(group_orders.close_due())
    status = call(client, "group_order_status", member_token=joined["member_token"])
    paid = call(client, "pay_invoice", invoice_token=status["invoice_token"], pay_with="USDC on base")
    assert (paid["quantity"], paid["total_usd"], paid["payment"]["chain"]) == (4, "24.00", "base")


def test_the_owner_sees_their_group_orders_with_invoices(client, shop):
    _turn_on(client, shop)
    group_id = _open(client, shop).json()["group_order"]["group_order_id"]
    _expire(group_id)
    asyncio.run(group_orders.close_due())
    owned = client.get(f"/api/v1/shops/{shop['id']}/group-orders").json()
    assert owned[0]["members"][0]["invoice_token"]
    client.sign_in(make_user("Stranger"))
    assert client.get(f"/api/v1/shops/{shop['id']}/group-orders").status_code == 404


def test_the_tier_reached_is_the_highest_step_met():
    steps = [group_orders.Tier(1, 1000), group_orders.Tier(5, 800), group_orders.Tier(10, 600)]
    assert [group_orders.price_for(steps, q) for q in (1, 4, 5, 9, 10, 50)] == [1000, 1000, 800, 800, 600, 600]
    assert group_orders.next_tier(steps, 7) == group_orders.Tier(10, 600)
