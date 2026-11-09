"""A founder's shops: creating them, listing them, and resolving one for its
owner. A new shop is a draft: no wallet and nothing on sale until its owner
signs it live."""

import re
import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.schemas.shop import SHOP_SLUG_MAX_LEN, SHOP_SLUG_PATTERN
from app.database.models import Shop
from app.services.errors import ConflictError, InvalidInputError, NotFoundError
from config import settings

# Slugs tried with a numeric suffix before giving up on a name.
_SLUG_ATTEMPTS = 20
# Paths of the app that a shop's /s/<slug> can never shadow are under /s/,
# but a few words read badly as a shop address.
_RESERVED_SLUGS = frozenset({"admin", "api", "app", "new", "shops", "thalace", "directory", "invoices"})


def slugify(name: str) -> str:
    """A URL-safe base for a shop's address, from its name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:SHOP_SLUG_MAX_LEN].strip("-")


def _valid_slug(slug: str) -> bool:
    return bool(re.fullmatch(SHOP_SLUG_PATTERN, slug)) and slug not in _RESERVED_SLUGS


async def _taken(db: AsyncSession, slug: str) -> bool:
    return await db.scalar(select(func.count()).select_from(Shop).where(Shop.slug == slug)) > 0


async def _free_slug(db: AsyncSession, wanted: str | None, name: str) -> str:
    if wanted is not None:
        if not _valid_slug(wanted):
            raise InvalidInputError("That address can't be used. Use 3–48 lowercase letters, digits and dashes.")
        if await _taken(db, wanted):
            raise ConflictError(f"The address /s/{wanted} is taken. Pick another.")
        return wanted
    base = slugify(name)
    if len(base) < 3:
        base = f"shop-{base}".strip("-") if base else "shop"
    for attempt in range(_SLUG_ATTEMPTS):
        suffix = "" if attempt == 0 else f"-{attempt + 1}"
        candidate = base[:SHOP_SLUG_MAX_LEN - len(suffix)].strip("-") + suffix
        if _valid_slug(candidate) and not await _taken(db, candidate):
            return candidate
    raise ConflictError("Couldn't find a free address for that name. Pick one yourself.")


async def create_shop(db: AsyncSession, owner_id: uuid.UUID, *, name: str, slug: str | None, tagline: str,
                      description: str, website: str | None) -> Shop:
    count = await db.scalar(select(func.count()).select_from(Shop).where(Shop.owner_id == owner_id))
    if count >= settings.max_shops_per_owner:
        raise ConflictError(f"You can run at most {settings.max_shops_per_owner} shops.")
    shop = Shop(owner_id=owner_id, slug=await _free_slug(db, slug, name), name=name.strip(), tagline=tagline.strip(),
                description=description.strip(), website=website,
                settlement_asset=settings.default_settlement_asset,
                daily_budget_usd=Decimal(settings.default_daily_budget_usd))
    db.add(shop)
    await db.commit()
    await db.refresh(shop)
    return shop


async def list_shops(db: AsyncSession, owner_id: uuid.UUID) -> list[Shop]:
    rows = await db.scalars(select(Shop).where(Shop.owner_id == owner_id).order_by(Shop.created_at)
                            .limit(settings.max_shops_per_owner))
    return list(rows)


async def owned_shop(db: AsyncSession, shop_id: uuid.UUID, owner_id: uuid.UUID) -> Shop:
    shop = await db.get(Shop, shop_id)
    if shop is None or shop.owner_id != owner_id:
        raise NotFoundError("Shop not found.")
    return shop


async def update_shop(db: AsyncSession, shop: Shop, *, name: str | None, tagline: str | None,
                      description: str | None, website: str | None) -> Shop:
    if name is not None:
        shop.name = name.strip()
    if tagline is not None:
        shop.tagline = tagline.strip()
    if description is not None:
        shop.description = description.strip()
    if website is not None:
        shop.website = website or None
    await db.commit()
    await db.refresh(shop)
    return shop
