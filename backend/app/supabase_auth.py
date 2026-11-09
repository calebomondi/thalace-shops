"""Who is calling: a Supabase access token resolved to a user.

Supabase owns identity (there's no local users table): we ask Supabase's
Auth API for the token's user, and trust a verified answer for a short while
so every request isn't a round trip."""

import time
import uuid
from dataclasses import dataclass

import httpx

from config import settings
from utils.log import logger

# Verified tokens kept at most; the oldest go first past this.
_CACHE_MAX = 1_000


@dataclass(frozen=True)
class AuthUser:
    id: uuid.UUID
    email: str | None
    name: str | None
    # From app_metadata.role (only the service key can write it), or a
    # confirmed email listed in ADMIN_BOOTSTRAP_EMAILS.
    is_admin: bool = False


class AuthUnavailableError(Exception):
    """Supabase Auth could not be asked. Not the same as a bad token."""


_cache: dict[str, tuple[float, AuthUser]] = {}


def _admin(body: dict) -> bool:
    if (body.get("app_metadata") or {}).get("role") == "admin":
        return True
    email = (body.get("email") or "").lower()
    confirmed = bool(body.get("email_confirmed_at") or body.get("confirmed_at"))
    return confirmed and email in {e.lower() for e in settings.admin_bootstrap_emails}


def _user(body: dict) -> AuthUser | None:
    try:
        uid = uuid.UUID(str(body["id"]))
    except (KeyError, ValueError):
        return None
    meta = body.get("user_metadata") or {}
    return AuthUser(id=uid, email=body.get("email"), name=meta.get("full_name") or meta.get("name"),
                    is_admin=_admin(body))


async def user_from_token(token: str, *, transport: httpx.AsyncBaseTransport | None = None) -> AuthUser | None:
    """The token's user, or None when Supabase says the token is invalid or
    expired. Raises AuthUnavailableError when Supabase can't be reached."""
    now = time.monotonic()
    cached = _cache.get(token)
    if cached and now - cached[0] < settings.auth_cache_ttl_s:
        return cached[1]
    if not settings.supabase_base_url or not settings.supabase_anon_key:
        raise AuthUnavailableError("SUPABASE_BASE_URL and SUPABASE_ANON_KEY must be set")
    try:
        async with httpx.AsyncClient(timeout=settings.supabase_timeout_s, transport=transport) as client:
            response = await client.get(
                f"{settings.supabase_base_url.rstrip('/')}/auth/v1/user",
                headers={"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        logger.warning("Supabase Auth unreachable: %s", exc)
        raise AuthUnavailableError(str(exc)) from exc
    if response.status_code in (401, 403):
        return None
    if response.status_code >= 400:
        logger.warning("Supabase Auth answered %s", response.status_code)
        raise AuthUnavailableError(f"Supabase Auth answered {response.status_code}")
    user = _user(response.json())
    if user is not None:
        if len(_cache) >= _CACHE_MAX:
            _cache.pop(next(iter(_cache)))
        _cache[token] = (now, user)
    return user
