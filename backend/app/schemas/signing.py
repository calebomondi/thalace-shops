from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from agents.schemas.shop import ShopIntentStatus, ShopIntentType
from app.schemas.shops import ShopOut


class PasskeyIn(BaseModel):
    credential_id: str = Field(min_length=4, max_length=512)
    # P-256 SPKI, base64url, as the browser's registration returns it.
    public_key: str = Field(min_length=40, max_length=256)
    rp_id: str = Field(min_length=1, max_length=253)
    origin: str = Field(min_length=8, max_length=255)


class PasskeyStatusOut(BaseModel):
    """Whether the founder has a passkey on this site, and the site it must be made on."""
    has_passkey: bool
    rp_id: str
    origin: str


class PendingSignatureOut(BaseModel):
    correlation_id: str
    type: ShopIntentType
    # Passed to the browser's passkey prompt unchanged.
    intent: dict[str, Any]
    preview: dict[str, Any]
    expires_at: datetime


class SignedIn(BaseModel):
    signed_data: dict[str, Any]


class SignatureStatusOut(BaseModel):
    correlation_id: str
    type: ShopIntentType
    status: ShopIntentStatus
    failure_code: str | None
    shop: ShopOut
