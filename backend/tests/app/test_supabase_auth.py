"""Resolving a Supabase access token: who it is, whether they're an admin,
and telling a bad token apart from Supabase being unreachable."""

import uuid

import httpx
import pytest

from app import supabase_auth
from app.supabase_auth import AuthUnavailableError, user_from_token
from config import settings

UID = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def supabase(monkeypatch):
    monkeypatch.setattr(settings, "supabase_base_url", "https://project.supabase.test")
    monkeypatch.setattr(settings, "supabase_anon_key", "anon")
    monkeypatch.setattr(settings, "admin_bootstrap_emails", ["boss@example.com"])
    monkeypatch.setattr(supabase_auth, "_cache", {})


def _answering(status: int, body: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/v1/user"
        assert request.headers["apikey"] == "anon"
        return httpx.Response(status, json=body or {})
    return httpx.MockTransport(handler)


async def test_a_valid_token_is_its_user():
    body = {"id": UID, "email": "kofi@example.com", "user_metadata": {"full_name": "Kofi"}}
    user = await user_from_token("t", transport=_answering(200, body))
    assert (str(user.id), user.email, user.name, user.is_admin) == (UID, "kofi@example.com", "Kofi", False)


async def test_an_invalid_token_is_nobody():
    assert await user_from_token("t", transport=_answering(401)) is None


async def test_the_admin_role_comes_from_app_metadata():
    body = {"id": UID, "email": "x@example.com", "app_metadata": {"role": "admin"}}
    assert (await user_from_token("t", transport=_answering(200, body))).is_admin


async def test_a_bootstrap_email_is_admin_only_once_confirmed():
    unconfirmed = {"id": UID, "email": "Boss@example.com"}
    assert not (await user_from_token("a", transport=_answering(200, unconfirmed))).is_admin
    confirmed = {**unconfirmed, "email_confirmed_at": "2026-11-09T08:00:00Z"}
    assert (await user_from_token("b", transport=_answering(200, confirmed))).is_admin


async def test_supabase_unreachable_is_not_a_bad_token():
    def handler(request):
        raise httpx.ConnectError("down", request=request)
    with pytest.raises(AuthUnavailableError):
        await user_from_token("t", transport=httpx.MockTransport(handler))


async def test_a_verified_token_is_reused_without_asking_again():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"id": UID})

    transport = httpx.MockTransport(handler)
    await user_from_token("t", transport=transport)
    await user_from_token("t", transport=transport)
    assert len(calls) == 1
