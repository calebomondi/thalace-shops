import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field

from agents.schemas.shop import BuyerKind, InvoiceStatus, LedgerKind, LedgerStatus, OfferDelivery, OfferKind


class PublicOffer(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    kind: OfferKind
    price_cents: int
    delivery: OfferDelivery


class PayOption(BaseModel):
    asset_id: str
    symbol: str
    chain: str


class PublicShopOut(BaseModel):
    slug: str
    name: str
    tagline: str
    description: str
    website: str | None
    # False while the owner has paused it or frozen its wallet.
    selling: bool
    wallet_account_id: str | None
    offers: list[PublicOffer]
    pay_options: list[PayOption]


class InvoiceCreate(BaseModel):
    offer_id: uuid.UUID
    quantity: int = Field(default=1, ge=1)
    buyer_email: EmailStr
    buyer_name: str | None = Field(default=None, max_length=120)


class PayIn(BaseModel):
    pay_asset: str = Field(min_length=3, max_length=128)


class PaymentOut(BaseModel):
    """Where and how much to send. Only an address the shop's wallet quoted."""
    asset_id: str
    symbol: str | None
    chain: str | None
    amount: Decimal
    address: str | None
    memo: str | None
    expires_at: datetime | None


class DeliveryOut(BaseModel):
    """What the buyer gets, shown only once the invoice is paid."""
    url: str | None
    note: str
    deliverable: str | None


class PublicInvoiceOut(BaseModel):
    number: str
    public_token: str
    shop_slug: str
    shop_name: str
    title: str
    quantity: int
    unit_price_cents: int
    total_cents: int
    status: InvoiceStatus
    buyer_name: str | None
    payment: PaymentOut | None
    payment_tx_url: str | None
    refund_tx_hash: str | None
    failure_code: str | None
    delivery: DeliveryOut | None
    created_at: datetime
    paid_at: datetime | None
    delivered_at: datetime | None


class OwnerInvoiceOut(BaseModel):
    id: uuid.UUID
    number: str
    public_token: str
    title: str
    quantity: int
    total_cents: int
    fee_bps: int
    status: InvoiceStatus
    buyer_kind: BuyerKind
    buyer_email: str | None
    buyer_name: str | None
    delivery: OfferDelivery
    deliverable: str | None
    created_at: datetime
    paid_at: datetime | None
    delivered_at: datetime | None


class DeliverIn(BaseModel):
    deliverable: str | None = Field(default=None, max_length=20_000)


class LedgerLineOut(BaseModel):
    kind: LedgerKind
    status: LedgerStatus
    amount_usd: Decimal | None
    counterparty: str | None
    invoice_number: str | None
    tx_url: str | None
    failure_code: str | None
    created_at: datetime
    settled_at: datetime | None
