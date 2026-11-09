import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from agents.schemas.shop import OfferDelivery, OfferKind, OfferStatus

# A million dollars in cents: far above anything a shop sells, low enough to
# catch a price typed in the wrong unit.
_MAX_CENTS = 100_000_000


class OfferCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=4000)
    kind: OfferKind
    price_cents: int = Field(gt=0, le=_MAX_CENTS)
    # The lowest price the agent may agree to; the list price when left out.
    floor_cents: int | None = Field(default=None, gt=0, le=_MAX_CENTS)
    delivery: OfferDelivery
    delivery_url: str | None = Field(default=None, max_length=2000)
    delivery_note: str = Field(default="", max_length=2000)


class OfferUpdate(BaseModel):
    """Only the fields sent change. status 'active' puts the offer on sale."""
    title: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    kind: OfferKind | None = None
    price_cents: int | None = Field(default=None, gt=0, le=_MAX_CENTS)
    floor_cents: int | None = Field(default=None, gt=0, le=_MAX_CENTS)
    delivery: OfferDelivery | None = None
    delivery_url: str | None = Field(default=None, max_length=2000)
    delivery_note: str | None = Field(default=None, max_length=2000)
    status: OfferStatus | None = None


class OfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    kind: OfferKind
    price_cents: int
    floor_cents: int
    delivery: OfferDelivery
    delivery_url: str | None
    delivery_note: str
    status: OfferStatus
    # The shop's agent wrote it; the owner hasn't changed who made it.
    drafted_by_agent: bool
    created_at: datetime

    @classmethod
    def of(cls, offer) -> "OfferOut":
        return cls.model_validate({**offer.__dict__, "drafted_by_agent": offer.created_by is None})
