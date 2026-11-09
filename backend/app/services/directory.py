"""The directory: live shops and what they sell, searchable by people and by
agents (the MCP server's search_shops). A shop's floor price is never shown."""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Offer, Shop
from config import settings


async def search(db: AsyncSession, query: str, limit: int | None = None) -> list[tuple[Shop, list[Offer]]]:
    """Live shops whose name, description or offers match every word of
    `query` (all live shops when it's empty), each with its offers on sale."""
    limit = min(limit or settings.directory_limit, settings.directory_limit)
    shops = select(Shop).where(Shop.status == "live", Shop.frozen_at.is_(None))
    for word in query.split()[:8]:
        pattern = f"%{word}%"
        offer_match = select(Offer.shop_id).where(
            Offer.status == "active", or_(Offer.title.ilike(pattern), Offer.description.ilike(pattern)))
        shops = shops.where(or_(Shop.name.ilike(pattern), Shop.tagline.ilike(pattern),
                                Shop.description.ilike(pattern), Shop.id.in_(offer_match)))
    found = list((await db.scalars(shops.order_by(Shop.live_since.desc()).limit(limit))).all())
    out = []
    for shop in found:
        offers = await db.scalars(select(Offer).where(Offer.shop_id == shop.id, Offer.status == "active")
                                  .order_by(Offer.position, Offer.created_at).limit(settings.max_offers_per_shop))
        out.append((shop, list(offers)))
    return out
