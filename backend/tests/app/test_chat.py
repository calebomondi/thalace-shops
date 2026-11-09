"""The chat with a shop's agent is the owner's alone."""

from tests.conftest import make_user


def test_a_new_shop_has_an_empty_conversation(client):
    shop = client.post("/api/v1/shops", json={"name": "Shanga Prints"}).json()
    assert client.get(f"/api/v1/shops/{shop['id']}/chat").json() == []


def test_strangers_cannot_read_or_talk_to_a_shops_agent(client):
    shop = client.post("/api/v1/shops", json={"name": "Shanga Prints"}).json()
    client.sign_in(make_user("Stranger"))
    assert client.get(f"/api/v1/shops/{shop['id']}/chat").status_code == 404
    assert client.post(f"/api/v1/shops/{shop['id']}/chat", json={"message": "hi"}).status_code == 404


def test_an_empty_message_is_refused(client):
    shop = client.post("/api/v1/shops", json={"name": "Shanga Prints"}).json()
    assert client.post(f"/api/v1/shops/{shop['id']}/chat", json={"message": ""}).status_code == 422
