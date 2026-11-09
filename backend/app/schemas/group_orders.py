import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from agents.schemas.shop import BuyerKind, GroupOrderStatus


class TierIn(BaseModel):
    min_quantity: int = Field(ge=2, le=10_000)
    unit_price_cents: int = Field(gt=0)


class TierOut(BaseModel):
    min_quantity: int
    unit_price_cents: int


class GroupBuyingIn(BaseModel):
    enabled: bool
    window_hours: int = Field(default=72, ge=1)
    tiers: list[TierIn] = Field(default_factory=list, max_length=10)


class GroupBuyingOut(BaseModel):
    enabled: bool
    window_hours: int
    tiers: list[TierOut]


class GroupMemberOut(BaseModel):
    buyer_kind: BuyerKind
    buyer_name: str
    quantity: int
    # Shown to the member themselves and to the owner; never on the public market.
    invoice_token: str | None = None


class GroupOrderOut(BaseModel):
    group_order_id: str
    shop_slug: str
    shop_name: str
    offer_id: uuid.UUID
    offer_title: str
    status: GroupOrderStatus
    opened_by: str
    deadline: datetime
    committed_quantity: int
    unit_price_cents: int
    list_price_cents: int
    next_tier: TierOut | None
    tiers: list[TierOut]
    members: list[GroupMemberOut]
    closed_at: datetime | None


class GroupOpenIn(BaseModel):
    offer_id: uuid.UUID
    quantity: int = Field(ge=1)
    hours: float = Field(gt=0)
    buyer_name: str = Field(min_length=1, max_length=120)
    buyer_email: EmailStr


class GroupJoinIn(BaseModel):
    quantity: int = Field(ge=1)
    buyer_name: str = Field(min_length=1, max_length=120)
    buyer_email: EmailStr


class MembershipOut(BaseModel):
    """A buyer's own place in a group order: keep the token to find the invoice after the close."""
    member_token: str
    group_order: GroupOrderOut
    invoice_token: str | None
