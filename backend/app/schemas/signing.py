import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from agents.schemas.shop import ShopIntentStatus, ShopIntentType
from app.schemas.rules import PayeeIn
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


class FreezeIn(BaseModel):
    freeze: bool


class RulesChangeIn(BaseModel):
    """The complete new rules for a live shop's wallet."""
    payees: list[PayeeIn]
    daily_budget_usd: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    supplier_shop_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
