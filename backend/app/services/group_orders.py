"""Group orders: buyers pooling demand for one offer to reach a volume price.
The rules are in docs/RULES.md; every one of them is checked here.

The seller turns group buying on for an offer and sets its tiers. Any buyer
opens or joins a group order until its deadline. At the deadline the watcher
closes it: the unit price is locked at the tier the total committed quantity
reached, and each member gets their own invoice at that price. Nothing is
charged before the close, and nobody holds anyone else's money."""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agents.schemas.shop import BuyerKind
from app.database.connect import AsyncSessionLocal
from app.database.models import GroupOrder, GroupOrderMember, Invoice, Offer, OfferTier, Shop
from app.services import invoices as invoice_service
from app.services import procurement
from app.services.errors import ConflictError, InvalidInputError, NotFoundError, ServiceError
from config import settings
from utils.log import logger


@dataclass(frozen=True)
class Tier:
    min_quantity: int
    unit_price_cents: int


# -- The seller's terms -------------------------------------------------------

async def tiers(db: AsyncSession, offer: Offer) -> list[Tier]:
    """The offer's tiers, the list price from 1 unit always first."""
    rows = await db.scalars(select(OfferTier).where(OfferTier.offer_id == offer.id).order_by(OfferTier.min_quantity))
    return [Tier(1, offer.price_cents)] + [Tier(r.min_quantity, r.unit_price_cents) for r in rows]


def price_for(steps: list[Tier], quantity: int) -> int:
    """The unit price at the highest tier `quantity` reaches."""
    return [t for t in steps if quantity >= t.min_quantity][-1].unit_price_cents


def next_tier(steps: list[Tier], quantity: int) -> Tier | None:
    return next((t for t in steps if t.min_quantity > quantity), None)


async def set_group_buying(db: AsyncSession, offer: Offer, *, enabled: bool, window_hours: int,
                           steps: list[Tier]) -> list[Tier]:
    """The seller's terms. Each tier above 1 unit needs more units and a lower
    price than the one before, and never goes below the floor."""
    if not 1 <= window_hours <= settings.group_order_max_window_hours:
        raise InvalidInputError(f"The window must be between 1 and {settings.group_order_max_window_hours} hours.")
    steps = sorted((t for t in steps if t.min_quantity > 1), key=lambda t: t.min_quantity)
    last_qty, last_price = 1, offer.price_cents
    for tier in steps:
        if tier.min_quantity <= last_qty:
            raise InvalidInputError("Each tier needs more units than the one before.")
        if tier.unit_price_cents >= last_price:
            raise InvalidInputError("Each tier needs a lower unit price than the one before.")
        if tier.unit_price_cents < offer.floor_cents:
            raise InvalidInputError("A tier can't be below the offer's lowest price.")
        last_qty, last_price = tier.min_quantity, tier.unit_price_cents
    if enabled and not steps:
        raise InvalidInputError("Add at least one volume tier before turning group buying on.")
    await db.execute(delete(OfferTier).where(OfferTier.offer_id == offer.id))
    db.add_all(OfferTier(offer_id=offer.id, min_quantity=t.min_quantity, unit_price_cents=t.unit_price_cents)
               for t in steps)
    offer.group_buy_enabled, offer.group_window_hours = enabled, window_hours
    await db.commit()
    return await tiers(db, offer)


# -- Buyers -------------------------------------------------------------------

def _check_buyer(buyer_kind: BuyerKind, buyer_email: str | None, quantity: int) -> None:
    if not 0 < quantity <= settings.max_invoice_quantity:
        raise InvalidInputError(f"The quantity must be between 1 and {settings.max_invoice_quantity}.")
    if buyer_kind == "person" and not buyer_email:
        raise InvalidInputError("Give an email for your invoice.")


async def open_group_order(db: AsyncSession, *, offer_id: uuid.UUID, quantity: int, hours: float,
                           buyer_kind: BuyerKind, buyer_name: str, buyer_email: str | None
                           ) -> tuple[GroupOrder, GroupOrderMember]:
    """Open a group order and join it as its first member."""
    _check_buyer(buyer_kind, buyer_email, quantity)
    offer = await db.get(Offer, offer_id)
    shop = await db.get(Shop, offer.shop_id) if offer else None
    if offer is None or offer.status != "active" or shop is None or not invoice_service.selling(shop):
        raise NotFoundError("That offer isn't on sale.")
    if not offer.group_buy_enabled:
        raise ConflictError("This offer doesn't take group orders.")
    minimum = settings.group_order_min_minutes / 60
    if not minimum <= hours <= offer.group_window_hours:
        raise InvalidInputError(f"The deadline must be between {settings.group_order_min_minutes} minutes and "
                                f"{offer.group_window_hours} hours away.")
    group = GroupOrder(shop_id=shop.id, offer_id=offer.id, public_token=secrets.token_urlsafe(24),
                       opened_by=buyer_name.strip()[:120] or "A buyer",
                       deadline=datetime.now(UTC) + timedelta(hours=hours))
    db.add(group)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("This offer already has an open group order: join it instead.") from None
    member = GroupOrderMember(group_order_id=group.id, public_token=secrets.token_urlsafe(24), buyer_kind=buyer_kind,
                              buyer_name=group.opened_by, buyer_email=buyer_email, quantity=quantity)
    db.add(member)
    await db.commit()
    return group, member


async def by_token(db: AsyncSession, token: str) -> GroupOrder:
    group = await db.scalar(select(GroupOrder).where(GroupOrder.public_token == token))
    if group is None:
        raise NotFoundError("No such group order.")
    return group


async def join(db: AsyncSession, token: str, *, quantity: int, buyer_kind: BuyerKind, buyer_name: str,
               buyer_email: str | None, buyer_shop_id: uuid.UUID | None = None) -> GroupOrderMember:
    _check_buyer(buyer_kind, buyer_email, quantity)
    # Locked so a join can't slip in while the watcher closes it.
    group = await db.scalar(select(GroupOrder).where(GroupOrder.public_token == token).with_for_update())
    if group is None:
        raise NotFoundError("No such group order.")
    if group.status != "open" or group.deadline <= datetime.now(UTC):
        raise ConflictError("This group order has closed.")
    members = await db.scalar(select(func.count()).select_from(GroupOrderMember)
                              .where(GroupOrderMember.group_order_id == group.id))
    if members >= settings.group_order_max_members:
        raise ConflictError("This group order is full.")
    member = GroupOrderMember(group_order_id=group.id, public_token=secrets.token_urlsafe(24), buyer_kind=buyer_kind,
                              buyer_name=buyer_name.strip()[:120] or "A buyer", buyer_email=buyer_email,
                              buyer_shop_id=buyer_shop_id, quantity=quantity)
    db.add(member)
    await db.commit()
    return member


async def member_by_token(db: AsyncSession, token: str) -> tuple[GroupOrderMember, GroupOrder]:
    member = await db.scalar(select(GroupOrderMember).where(GroupOrderMember.public_token == token))
    if member is None:
        raise NotFoundError("No such member.")
    return member, await db.get(GroupOrder, member.group_order_id)


# -- Reading ------------------------------------------------------------------

@dataclass(frozen=True)
class GroupView:
    group: GroupOrder
    shop: Shop
    offer: Offer
    tiers: list[Tier]
    members: list[GroupOrderMember]

    @property
    def committed(self) -> int:
        return sum(m.quantity for m in self.members)

    @property
    def unit_price_cents(self) -> int:
        return self.group.unit_price_cents or price_for(self.tiers, self.committed)

    @property
    def next(self) -> Tier | None:
        return None if self.group.status != "open" else next_tier(self.tiers, self.committed)


async def view(db: AsyncSession, group: GroupOrder) -> GroupView:
    offer = await db.get(Offer, group.offer_id)
    members = list((await db.scalars(select(GroupOrderMember).where(GroupOrderMember.group_order_id == group.id)
                                      .order_by(GroupOrderMember.created_at))).all())
    return GroupView(group=group, shop=await db.get(Shop, group.shop_id), offer=offer, tiers=await tiers(db, offer),
                     members=members)


async def market(db: AsyncSession, limit: int = 50) -> list[GroupView]:
    """Open group orders, soonest deadline first, then the latest closed ones."""
    open_rows = await db.scalars(select(GroupOrder).where(GroupOrder.status == "open")
                                 .order_by(GroupOrder.deadline).limit(limit))
    closed_rows = await db.scalars(select(GroupOrder).where(GroupOrder.status != "open")
                                   .order_by(GroupOrder.closed_at.desc()).limit(limit // 2))
    return [await view(db, g) for g in [*open_rows, *closed_rows]]


async def for_shop(db: AsyncSession, shop: Shop, limit: int = 50) -> list[GroupView]:
    rows = await db.scalars(select(GroupOrder).where(GroupOrder.shop_id == shop.id)
                            .order_by(GroupOrder.created_at.desc()).limit(limit))
    return [await view(db, g) for g in rows]


# -- Closing ------------------------------------------------------------------

async def close(db: AsyncSession, group: GroupOrder) -> GroupView:
    """Lock the price at the tier reached and invoice each member."""
    current = await view(db, group)
    group.closed_at = datetime.now(UTC)
    if not current.members or not invoice_service.selling(current.shop) or current.offer.status != "active":
        group.status = "cancelled"
        await db.commit()
        return current
    group.total_quantity, group.unit_price_cents = current.committed, price_for(current.tiers, current.committed)
    group.status = "closed"
    for member in current.members:
        invoice: Invoice = await invoice_service.issue_invoice(
            db, current.shop, offer_id=current.offer.id, quantity=member.quantity,
            unit_price_cents=group.unit_price_cents, buyer_kind=member.buyer_kind, buyer_email=member.buyer_email,
            buyer_name=member.buyer_name, ip_hash=None, buyer_shop_id=member.buyer_shop_id)
        member.invoice_id = invoice.id
    await db.commit()
    await _shops_pay(db, current)
    return current


async def _shops_pay(db: AsyncSession, current: GroupView) -> None:
    """Shops that joined pay their invoices from their own wallets. One that
    can't (not an allowed supplier, frozen) leaves its invoice open to pay by hand."""
    for member in current.members:
        if member.buyer_shop_id is None or member.invoice_id is None:
            continue
        buyer = await db.get(Shop, member.buyer_shop_id)
        invoice = await db.get(Invoice, member.invoice_id)
        try:
            await procurement.pay_from_wallet(db, buyer, invoice)
        except ServiceError as exc:
            await db.rollback()
            logger.info("Group order %s: %s didn't pay from its wallet: %s", current.group.id, buyer.name, exc)


async def close_due() -> int:
    """Close every open group order whose deadline has passed. Returns how many."""
    closed = 0
    async with AsyncSessionLocal() as db:
        due = list((await db.scalars(select(GroupOrder).where(GroupOrder.status == "open",
                                                              GroupOrder.deadline <= datetime.now(UTC))
                                     .order_by(GroupOrder.deadline).limit(settings.watcher_batch)
                                     .with_for_update(skip_locked=True))).all())
        for group in due:
            try:
                await close(db, group)
                closed += 1
            except ServiceError as exc:
                await db.rollback()
                logger.warning("Group order %s not closed: %s", group.id, exc)
    return closed
