"""A founder's shops: made as drafts, addressed by a unique slug, seen only by
their owner."""

from config import settings
from tests.conftest import make_user


def _create(client, name="Shanga CAD Studio", **fields):
    return client.post("/api/v1/shops", json={"name": name, **fields})


def test_a_new_shop_is_a_draft_with_an_address_from_its_name(client):
    response = _create(client, tagline="Designs from a sketch", website="https://prints.shangalabs.com")
    assert response.status_code == 201
    shop = response.json()
    assert (shop["slug"], shop["status"], shop["frozen"]) == ("shanga-cad-studio", "draft", False)
    assert shop["settlement_asset"] == settings.default_settlement_asset
    assert shop["wallet_account_id"] is None
    assert shop["website"] == "https://prints.shangalabs.com/"


def test_the_same_name_twice_gets_a_numbered_address(client):
    assert _create(client).json()["slug"] == "shanga-cad-studio"
    assert _create(client).json()["slug"] == "shanga-cad-studio-2"


def test_a_chosen_address_that_is_taken_is_refused(client):
    assert _create(client, slug="shanga-prints").status_code == 201
    response = _create(client, name="Other", slug="shanga-prints")
    assert response.status_code == 409
    assert "/s/shanga-prints" in response.json()["detail"]


def test_a_malformed_or_reserved_address_is_refused(client):
    assert _create(client, slug="Bad Slug!").status_code == 422
    assert _create(client, slug="admin").status_code == 422


def test_a_name_without_letters_still_gets_an_address(client):
    assert _create(client, name="!!").json()["slug"] == "shop"


def test_owners_see_only_their_own_shops(client):
    mine = _create(client).json()
    stranger = make_user("Stranger")
    client.sign_in(stranger)
    assert client.get("/api/v1/shops").json() == []
    assert client.get(f"/api/v1/shops/{mine['id']}").status_code == 404
    assert client.patch(f"/api/v1/shops/{mine['id']}", json={"name": "Taken over"}).status_code == 404


def test_listing_returns_shops_in_the_order_they_were_made(client):
    for name in ("Shanga CAD Studio", "Shanga Creative Lab", "Shanga Prints"):
        _create(client, name=name)
    assert [s["name"] for s in client.get("/api/v1/shops").json()] == [
        "Shanga CAD Studio", "Shanga Creative Lab", "Shanga Prints"]


def test_an_owner_edits_their_shop_and_can_clear_the_website(client):
    shop = _create(client, website="https://prints.shangalabs.com").json()
    updated = client.patch(f"/api/v1/shops/{shop['id']}", json={"tagline": "CAD in a day", "website": None}).json()
    assert (updated["tagline"], updated["website"], updated["name"]) == ("CAD in a day", None, "Shanga CAD Studio")


def test_there_is_a_limit_on_shops_per_owner(client, monkeypatch):
    monkeypatch.setattr(settings, "max_shops_per_owner", 2)
    assert _create(client, name="One").status_code == 201
    assert _create(client, name="Two").status_code == 201
    response = _create(client, name="Three")
    assert response.status_code == 409
    assert "at most 2" in response.json()["detail"]


def test_shops_need_a_signed_in_user(client):
    client.sign_out()
    assert client.get("/api/v1/shops").status_code == 401
