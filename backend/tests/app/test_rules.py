"""A shop's money rules before it's signed: the revenue split and the daily
cap, checked together and frozen once the shop is live."""

import psycopg
import pytest

from config import settings


@pytest.fixture
def shop(client):
    return client.post("/api/v1/shops", json={"name": "Shanga Prints"}).json()


def _payee(address="kaleb.near", share=9000, **fields):
    return {"label": "Founder", "route": "transfer", "address": address, "share_bps": share, **fields}


def test_the_owner_sets_the_revenue_split(client, shop):
    url = f"/api/v1/shops/{shop['id']}/payees"
    payees = client.put(url, json={"payees": [_payee(), _payee("designer.near", 500, label="Designer")]}).json()
    assert [(p["address"], p["share_bps"]) for p in payees] == [("kaleb.near", 9000), ("designer.near", 500)]
    assert len(client.get(url).json()) == 2


def test_shares_over_100_percent_are_refused(client, shop):
    response = client.put(f"/api/v1/shops/{shop['id']}/payees",
                          json={"payees": [_payee(), _payee("designer.near", 1500)]})
    assert response.status_code == 422
    assert "100%" in response.json()["detail"]


def test_a_transfer_payee_must_be_a_near_account(client, shop):
    response = client.put(f"/api/v1/shops/{shop['id']}/payees", json={"payees": [_payee("Not An Account!")]})
    assert response.status_code == 422


def test_a_withdraw_payee_names_its_chain(client, shop):
    url = f"/api/v1/shops/{shop['id']}/payees"
    assert client.put(url, json={"payees": [_payee("0xabc", route="withdraw")]}).status_code == 422
    ok = client.put(url, json={"payees": [_payee("0xabc", route="withdraw", chain="base")]})
    assert ok.json()[0]["chain"] == "base"


def test_the_same_destination_twice_is_refused(client, shop):
    response = client.put(f"/api/v1/shops/{shop['id']}/payees", json={"payees": [_payee(share=10), _payee(share=10)]})
    assert response.status_code == 422


def test_the_daily_cap_is_bounded(client, shop):
    url = f"/api/v1/shops/{shop['id']}/budget"
    assert client.put(url, json={"daily_budget_usd": "35.50"}).json()["daily_budget_usd"] == "35.50"
    assert client.put(url, json={"daily_budget_usd": settings.max_daily_budget_usd + 1}).status_code == 422


def test_rules_are_frozen_once_the_shop_is_live(client, shop):
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute("UPDATE shops SET status = 'live', agent_id = 'agent-1' WHERE id = %s", (shop["id"],))
    assert client.put(f"/api/v1/shops/{shop['id']}/payees", json={"payees": [_payee()]}).status_code == 409
    assert client.put(f"/api/v1/shops/{shop['id']}/budget", json={"daily_budget_usd": "5"}).status_code == 409


def test_owners_read_the_platform_terms(client):
    terms = client.get("/api/v1/platform/terms").json()
    assert terms == {"fee_bps": settings.platform_fee_bps, "max_fee_bps": settings.platform_fee_max_bps,
                     "fee_account": settings.near_mainnet_platform_treasury_wallet_address}
