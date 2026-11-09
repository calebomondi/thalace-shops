"""What the shop agent reads and returns. Plain models: the agent never sees
database rows, only these, through its store."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel

from agents.schemas.shop import OfferDelivery, OfferKind, OfferStatus, ShopStatus


class ToolResult(BaseModel):
    """What every shop tool returns. `summary` stands on its own; `data`
    carries the detail. A failure is a result too: the model reads the error
    and decides what to do, and the turn keeps going."""
    ok: bool
    summary: str
    data: Any = None
    error: str | None = None

    @classmethod
    def success(cls, summary: str, data: Any = None) -> "ToolResult":
        return cls(ok=True, summary=summary, data=data)

    @classmethod
    def failure(cls, error: str) -> "ToolResult":
        return cls(ok=False, summary=error, error=error)


class PayeeView(BaseModel):
    label: str
    address: str
    share_percent: float


class ShopView(BaseModel):
    name: str
    slug: str
    tagline: str
    description: str
    website: str | None
    status: ShopStatus
    daily_budget_usd: str
    platform_fee_percent: float
    payees: list[PayeeView]


class OfferView(BaseModel):
    id: UUID
    title: str
    description: str
    kind: OfferKind
    price_usd: str
    floor_usd: str
    delivery: OfferDelivery
    status: OfferStatus


class OfferDraft(BaseModel):
    """An offer the agent proposes. It is always saved as a draft."""
    title: str
    description: str
    kind: OfferKind
    price_cents: int
    floor_cents: int
    delivery: OfferDelivery
    delivery_note: str


class MarketOffer(BaseModel):
    id: UUID
    title: str
    price_usd: str
    kind: OfferKind


class MarketShop(BaseModel):
    """Another live shop, as a possible supplier."""
    slug: str
    name: str
    tagline: str
    # The owner allowed this shop to pay it (a destination in the signed policy).
    allowed_supplier: bool
    offers: list[MarketOffer]


class Purchase(BaseModel):
    invoice_number: str
    supplier: str
    item: str
    quantity: int
    total_usd: str
    status: str


class GroupOrderView(BaseModel):
    group_order_id: str
    shop: str
    offer: str
    committed_quantity: int
    unit_price_usd: str
    next_tier_quantity: int | None
    next_tier_price_usd: str | None
    deadline: str


class SalesSummary(BaseModel):
    invoices_paid: int
    revenue_usd: str
    invoices_awaiting_payment: int
    open_negotiations: int
    open_group_orders: int
