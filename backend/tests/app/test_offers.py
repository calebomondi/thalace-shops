"""Offers: drafts until the owner puts them on sale, with a floor the agent
may not go below, and only on the owner's own shop."""

import pytest

from tests.conftest import make_user


@pytest.fixture
def shop(client):
    return client.post("/api/v1/shops", json={"name": "Shanga CAD Studio"}).json()


def _offer(**fields):
    return {"title": "Print-readiness review", "kind": "service", "price_cents": 1500, "delivery": "markdown",
            **fields}


def test_a_new_offer_is_a_draft_with_the_list_price_as_its_floor(client, shop):
    response = client.post(f"/api/v1/shops/{shop['id']}/offers", json=_offer())
    assert response.status_code == 201
    offer = response.json()
    assert (offer["status"], offer["floor_cents"], offer["drafted_by_agent"]) == ("draft", 1500, False)


def test_the_floor_can_be_lower_but_never_above_the_price(client, shop):
    url = f"/api/v1/shops/{shop['id']}/offers"
    assert client.post(url, json=_offer(floor_cents=1000)).json()["floor_cents"] == 1000
    response = client.post(url, json=_offer(floor_cents=2000))
    assert response.status_code == 422
    assert "lowest price" in response.json()["detail"]


def test_a_link_offer_needs_its_link(client, shop):
    response = client.post(f"/api/v1/shops/{shop['id']}/offers", json=_offer(kind="digital", delivery="link"))
    assert response.status_code == 422


def test_the_owner_puts_an_offer_on_sale_and_archives_it(client, shop):
    url = f"/api/v1/shops/{shop['id']}/offers"
    offer = client.post(url, json=_offer()).json()
    assert client.patch(f"{url}/{offer['id']}", json={"status": "active"}).json()["status"] == "active"
    client.patch(f"{url}/{offer['id']}", json={"status": "archived"})
    assert client.get(url).json() == []
    assert [o["status"] for o in client.get(url, params={"include_archived": True}).json()] == ["archived"]


def test_lowering_the_price_below_the_floor_is_refused(client, shop):
    url = f"/api/v1/shops/{shop['id']}/offers"
    offer = client.post(url, json=_offer(floor_cents=1000)).json()
    assert client.patch(f"{url}/{offer['id']}", json={"price_cents": 900}).status_code == 422


def test_another_owners_offers_are_not_found(client, shop):
    url = f"/api/v1/shops/{shop['id']}/offers"
    offer = client.post(url, json=_offer()).json()
    client.sign_in(make_user("Stranger"))
    assert client.get(url).status_code == 404
    assert client.patch(f"{url}/{offer['id']}", json={"price_cents": 1}).status_code == 404
