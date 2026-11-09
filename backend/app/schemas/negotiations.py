import uuid
from datetime import datetime

from pydantic import BaseModel

from agents.schemas.shop import BuyerKind, NegotiationMove, NegotiationSide, NegotiationStatus


class MoveOut(BaseModel):
    side: NegotiationSide
    move: NegotiationMove
    unit_price_cents: int | None
    message: str
    created_at: datetime


class NegotiationOut(BaseModel):
    """The owner's view: who bargained over what, and every move with its reason."""
    id: uuid.UUID
    offer_title: str
    list_price_cents: int
    floor_cents: int
    buyer_kind: BuyerKind
    buyer_name: str
    quantity: int
    status: NegotiationStatus
    agreed_unit_cents: int | None
    moves: list[MoveOut]
    created_at: datetime


class DirectoryShopOut(BaseModel):
    slug: str
    name: str
    tagline: str
    offers: list[dict]
