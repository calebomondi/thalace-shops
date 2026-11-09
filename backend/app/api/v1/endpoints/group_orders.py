import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import DbSession, OwnedShop
from app.api.v1.group_views import group_out
from app.database.models import Invoice
from app.schemas.group_orders import (
    GroupBuyingIn,
    GroupBuyingOut,
    GroupJoinIn,
    GroupOpenIn,
    GroupOrderOut,
    MembershipOut,
    TierOut,
)
from app.services import group_orders
from app.services import offers as offer_service

owner = APIRouter(prefix="/shops/{shop_id}", tags=["group orders"])
public = APIRouter(prefix="/public", tags=["group orders"])


def _buying(offer, tiers) -> GroupBuyingOut:
    return GroupBuyingOut(enabled=offer.group_buy_enabled, window_hours=offer.group_window_hours,
                          tiers=[TierOut(min_quantity=t.min_quantity, unit_price_cents=t.unit_price_cents)
                                 for t in tiers])


@owner.get("/offers/{offer_id}/group-buying", response_model=GroupBuyingOut)
async def get_group_buying(offer_id: uuid.UUID, shop: OwnedShop, db: DbSession) -> GroupBuyingOut:
    offer = await offer_service.shop_offer(db, shop, offer_id)
    return _buying(offer, await group_orders.tiers(db, offer))


@owner.put("/offers/{offer_id}/group-buying", response_model=GroupBuyingOut)
async def set_group_buying(offer_id: uuid.UUID, body: GroupBuyingIn, shop: OwnedShop, db: DbSession) -> GroupBuyingOut:
    offer = await offer_service.shop_offer(db, shop, offer_id)
    steps = [group_orders.Tier(t.min_quantity, t.unit_price_cents) for t in body.tiers]
    tiers = await group_orders.set_group_buying(db, offer, enabled=body.enabled, window_hours=body.window_hours,
                                                steps=steps)
    return _buying(offer, tiers)


@owner.get("/group-orders", response_model=list[GroupOrderOut])
async def shop_group_orders(shop: OwnedShop, db: DbSession) -> list[GroupOrderOut]:
    views = await group_orders.for_shop(db, shop)
    ids = [m.invoice_id for v in views for m in v.members if m.invoice_id]
    found = {i.id: i for i in (await db.scalars(select(Invoice).where(Invoice.id.in_(ids)))).all()} if ids else {}
    return [group_out(v, found) for v in views]


@public.get("/market", response_model=list[GroupOrderOut])
async def market(db: DbSession) -> list[GroupOrderOut]:
    """Open group orders and the latest closed ones. Members' invoices aren't shown."""
    return [group_out(v) for v in await group_orders.market(db)]


@public.get("/group-orders/{token}", response_model=GroupOrderOut)
async def get_group_order(token: str, db: DbSession) -> GroupOrderOut:
    return group_out(await group_orders.view(db, await group_orders.by_token(db, token)))


async def _membership(db, member_token: str) -> MembershipOut:
    member, group = await group_orders.member_by_token(db, member_token)
    invoice = await db.get(Invoice, member.invoice_id) if member.invoice_id else None
    return MembershipOut(member_token=member.public_token, group_order=group_out(await group_orders.view(db, group)),
                         invoice_token=invoice.public_token if invoice else None)


@public.post("/group-orders", response_model=MembershipOut, status_code=status.HTTP_201_CREATED)
async def open_group_order(body: GroupOpenIn, db: DbSession) -> MembershipOut:
    _, member = await group_orders.open_group_order(
        db, offer_id=body.offer_id, quantity=body.quantity, hours=body.hours, buyer_kind="person",
        buyer_name=body.buyer_name, buyer_email=str(body.buyer_email))
    return await _membership(db, member.public_token)


@public.post("/group-orders/{token}/join", response_model=MembershipOut, status_code=status.HTTP_201_CREATED)
async def join_group_order(token: str, body: GroupJoinIn, db: DbSession) -> MembershipOut:
    member = await group_orders.join(db, token, quantity=body.quantity, buyer_kind="person",
                                     buyer_name=body.buyer_name, buyer_email=str(body.buyer_email))
    return await _membership(db, member.public_token)


@public.get("/memberships/{member_token}", response_model=MembershipOut)
async def membership(member_token: str, db: DbSession) -> MembershipOut:
    """A member's place in a group order, and their invoice once it closed."""
    return await _membership(db, member_token)
