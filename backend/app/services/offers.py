"""What a shop sells. The owner (or the shop's agent, as a draft) writes an
offer; only the owner puts it on sale. The floor is the lowest price the
agent may agree to when negotiating, and it is checked here, not in a prompt."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.schemas.shop import OfferDelivery, OfferKind
from app.database.models import Offer, Shop
from app.services.errors import InvalidInputError, NotFoundError
from config import settings


def _check(price_cents: int, floor_cents: int, delivery: OfferDelivery, delivery_url: str | None) -> None:
    if price_cents <= 0:
        raise InvalidInputError("The price must be more than zero.")
    if not 0 < floor_cents <= price_cents:
        raise InvalidInputError("The lowest price must be above zero and no higher than the list price.")
    if delivery == "link" and not delivery_url:
        raise InvalidInputError("A link offer needs the link the buyer receives once they've paid.")


async def list_offers(db: AsyncSession, shop: Shop, *, include_archived: bool = False) -> list[Offer]:
    query = select(Offer).where(Offer.shop_id == shop.id)
    if not include_archived:
        query = query.where(Offer.status != "archived")
    rows = await db.scalars(query.order_by(Offer.position, Offer.created_at).limit(settings.max_offers_per_shop))
    return list(rows)


async def create_offer(db: AsyncSession, shop: Shop, *, title: str, description: str, kind: OfferKind,
                       price_cents: int, floor_cents: int | None, delivery: OfferDelivery,
                       delivery_url: str | None, delivery_note: str, created_by: uuid.UUID | None) -> Offer:
    """A new offer, always a draft: drafted by the agent (created_by None) or
    written by the owner, and put on sale only by the owner."""
    floor = price_cents if floor_cents is None else floor_cents
    _check(price_cents, floor, delivery, delivery_url)
    count = await db.scalar(select(func.count()).select_from(Offer).where(Offer.shop_id == shop.id))
    if count >= settings.max_offers_per_shop:
        raise InvalidInputError(f"A shop holds at most {settings.max_offers_per_shop} offers.")
    offer = Offer(shop_id=shop.id, title=title.strip(), description=description.strip(), kind=kind,
                  price_cents=price_cents, floor_cents=floor, delivery=delivery, delivery_url=delivery_url,
                  delivery_note=delivery_note.strip(), status="draft", position=count, created_by=created_by)
    db.add(offer)
    await db.commit()
    await db.refresh(offer)
    return offer


async def shop_offer(db: AsyncSession, shop: Shop, offer_id: uuid.UUID) -> Offer:
    offer = await db.get(Offer, offer_id)
    if offer is None or offer.shop_id != shop.id:
        raise NotFoundError("Offer not found.")
    return offer


async def update_offer(db: AsyncSession, offer: Offer, changes: dict) -> Offer:
    """Apply the fields the owner sent. A status change to 'active' is how an
    offer goes on sale; 'archived' takes it off for good."""
    for field in ("title", "description", "delivery_note"):
        if field in changes:
            setattr(offer, field, (changes[field] or "").strip())
    for field in ("kind", "price_cents", "floor_cents", "delivery", "delivery_url", "status"):
        if field in changes:
            setattr(offer, field, changes[field])
    _check(offer.price_cents, offer.floor_cents, offer.delivery, offer.delivery_url)
    await db.commit()
    await db.refresh(offer)
    return offer

