"""Auth and ownership dependencies: the only place either is enforced.

Every route under a shop takes OwnedShop, which resolves the shop for its
owner and is a 404 for anyone else, indistinguishable from a missing shop."""

import hashlib
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connect import get_db
from app.database.models import Shop
from app.services import shops as shop_service
from app.supabase_auth import AuthUnavailableError, AuthUser, user_from_token
from config import settings

_bearer = HTTPBearer(auto_error=False)


async def require_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in first.")
    try:
        user = await user_from_token(credentials.credentials)
    except AuthUnavailableError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Sign-in can't be checked right now. Try again in a minute.") from None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has ended. Sign in again.")
    return user


CurrentUser = Annotated[AuthUser, Depends(require_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_owned_shop(shop_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Shop:
    return await shop_service.owned_shop(db, shop_id, user.id)


OwnedShop = Annotated[Shop, Depends(get_owned_shop)]


async def require_admin(user: CurrentUser) -> AuthUser:
    """Server-side admin gate for /api/v1/admin/*. A UI check alone is never enough."""
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required.")
    return user


AdminUser = Annotated[AuthUser, Depends(require_admin)]


def client_ip_hash(request: Request) -> str | None:
    """A salted hash of the caller's IP, for rate limits; the IP itself is never kept."""
    forwarded = request.headers.get(settings.client_ip_header, "")
    ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else "")
    if not ip:
        return None
    return hashlib.sha256(f"{settings.ip_hash_salt}:{ip}".encode()).hexdigest()
