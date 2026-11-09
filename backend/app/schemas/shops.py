import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from agents.schemas.shop import ShopStatus


class ShopCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    # The public address /s/<slug>; made from the name when left out.
    slug: str | None = Field(default=None, min_length=3, max_length=48)
    tagline: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=4000)
    website: HttpUrl | None = None


class ShopUpdate(BaseModel):
    """Only the fields sent change. An empty website clears it."""
    name: str | None = Field(default=None, min_length=2, max_length=120)
    tagline: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    website: HttpUrl | None = None


class ShopOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    tagline: str
    description: str
    website: str | None
    status: ShopStatus
    settlement_asset: str
    daily_budget_usd: Decimal
    wallet_account_id: str | None
    owner_account_id: str | None
    # The first signature opened the wallet; its money rules are fixed now.
    wallet_open: bool
    frozen: bool
    live_since: datetime | None
    created_at: datetime

    @classmethod
    def of(cls, shop) -> "ShopOut":
        return cls.model_validate({**shop.__dict__, "frozen": shop.frozen_at is not None,
                                   "wallet_open": shop.agent_id is not None})


class SupplierOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    wallet_account_id: str | None
