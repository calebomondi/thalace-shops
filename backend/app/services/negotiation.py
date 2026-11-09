"""Negotiations between a buyer (usually another agent) and a shop's agent.

The protocol, all checked here: the buyer makes up to `negotiation_max_offers`
offers; to each the seller accepts, counters or walks away (agents.shop.
negotiator decides, inside the floor and list price). The buyer may accept
the seller's latest counter, or walk away. An agreed unit price can then be
invoiced once, at that price, which issue_invoice checks against the floor
again."""

import asyncio
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.schemas.shop import BuyerKind
from agents.shop.negotiator import ModelCall, Situation, Turn, decide
from app.database.models import Invoice, Negotiation, NegotiationMoveRow, Offer, Shop
from app.services import invoices as invoice_service
from app.services.errors import ConflictError, InvalidInputError, NotFoundError
from config import settings


async def _moves(db: AsyncSession, negotiation: Negotiation) -> list[NegotiationMoveRow]:
    rows = await db.scalars(select(NegotiationMoveRow).where(NegotiationMoveRow.negotiation_id == negotiation.id)
                            .order_by(NegotiationMoveRow.created_at))
    return list(rows)


async def by_token(db: AsyncSession, token: str) -> Negotiation:
    negotiation = await db.scalar(select(Negotiation).where(Negotiation.public_token == token))
    if negotiation is None:
        raise NotFoundError("No such negotiation.")
    return negotiation


async def _sellable(db: AsyncSession, offer_id: uuid.UUID) -> tuple[Shop, Offer]:
    offer = await db.get(Offer, offer_id)
    shop = await db.get(Shop, offer.shop_id) if offer else None
    if offer is None or offer.status != "active" or shop is None or not invoice_service.selling(shop):
        raise NotFoundError("That offer isn't on sale.")
    return shop, offer


async def make_offer(db: AsyncSession, *, offer_id: uuid.UUID, quantity: int, unit_price_cents: int, message: str,
                     buyer_name: str, buyer_kind: BuyerKind, token: str | None,
                     model_call: ModelCall | None = None) -> tuple[Negotiation, list[NegotiationMoveRow]]:
    """The buyer offers a unit price; the shop's agent answers. Starts a
    negotiation when `token` is None."""
    if unit_price_cents <= 0:
        raise InvalidInputError("Offer a price above zero.")
    if not 0 < quantity <= settings.max_invoice_quantity:
        raise InvalidInputError(f"The quantity must be between 1 and {settings.max_invoice_quantity}.")
    if token is None:
        shop, offer = await _sellable(db, offer_id)
        negotiation = Negotiation(shop_id=shop.id, offer_id=offer.id, public_token=secrets.token_urlsafe(24),
                                  buyer_kind=buyer_kind, buyer_name=buyer_name.strip()[:120] or "A buyer",
                                  quantity=quantity)
        db.add(negotiation)
        await db.flush()
    else:
        negotiation = await by_token(db, token)
        if negotiation.offer_id != offer_id:
            raise InvalidInputError("That negotiation is about another offer.")
        shop, offer = await _sellable(db, negotiation.offer_id)
        negotiation.quantity = quantity
    if negotiation.status != "open":
        raise ConflictError(f"This negotiation is {negotiation.status.replace('_', ' ')}.")
    history = await _moves(db, negotiation)
    offers_made = sum(m.side == "buyer" and m.move == "offer" for m in history)
    if offers_made >= settings.negotiation_max_offers:
        raise ConflictError("No offers left: accept the shop's last price or walk away.")
    db.add(NegotiationMoveRow(negotiation_id=negotiation.id, side="buyer", move="offer",
                              unit_price_cents=unit_price_cents, message=message.strip()[:2000]))
    situation = Situation(
        shop_name=shop.name, offer_title=offer.title, offer_description=offer.description,
        list_cents=offer.price_cents, floor_cents=offer.floor_cents, quantity=quantity,
        buyer_name=negotiation.buyer_name, buyer_offer_cents=unit_price_cents, buyer_message=message,
        history=[Turn(m.side, m.move, m.unit_price_cents, m.message) for m in history],
        rounds_left=settings.negotiation_max_offers - offers_made - 1)
    # The model call is synchronous and may wait on throttles: off the event loop.
    decision = await asyncio.wait_for(asyncio.to_thread(decide, situation, model_call),
                                      timeout=settings.agent_turn_timeout_s)
    db.add(NegotiationMoveRow(negotiation_id=negotiation.id, side="seller", move=decision.move,
                              unit_price_cents=decision.unit_cents, message=decision.reason))
    if decision.move == "accept":
        negotiation.status, negotiation.agreed_unit_cents = "agreed", decision.unit_cents
    elif decision.move == "walk_away":
        negotiation.status = "walked_away"
    await db.commit()
    await db.refresh(negotiation)
    return negotiation, await _moves(db, negotiation)


async def respond(db: AsyncSession, token: str, move: str,
                  message: str) -> tuple[Negotiation, list[NegotiationMoveRow]]:
    """The buyer accepts the seller's latest counter, or walks away."""
    negotiation = await by_token(db, token)
    if negotiation.status != "open":
        raise ConflictError(f"This negotiation is {negotiation.status.replace('_', ' ')}.")
    history = await _moves(db, negotiation)
    last = history[-1] if history else None
    if move == "accept":
        if last is None or last.side != "seller" or last.move != "counter":
            raise ConflictError("There's no counter from the shop to accept.")
        negotiation.status, negotiation.agreed_unit_cents = "agreed", last.unit_price_cents
    elif move == "walk_away":
        negotiation.status = "walked_away"
    else:
        raise InvalidInputError("The buyer can accept or walk_away here; to name a price, make an offer.")
    db.add(NegotiationMoveRow(negotiation_id=negotiation.id, side="buyer", move=move,
                              unit_price_cents=last.unit_price_cents if move == "accept" else None,
                              message=message.strip()[:2000]))
    await db.commit()
    await db.refresh(negotiation)
    return negotiation, await _moves(db, negotiation)


async def invoice_agreed(db: AsyncSession, token: str, *, buyer_email: str | None, buyer_name: str | None,
                         ip_hash: str | None) -> Invoice:
    """Issue the invoice for an agreed negotiation, once, at the agreed price."""
    negotiation = await by_token(db, token)
    if negotiation.status == "invoiced":
        raise ConflictError("This deal was already invoiced.")
    if negotiation.status != "agreed":
        raise ConflictError("There's no agreed price to invoice yet.")
    shop = await db.get(Shop, negotiation.shop_id)
    invoice = await invoice_service.issue_invoice(
        db, shop, offer_id=negotiation.offer_id, quantity=negotiation.quantity,
        unit_price_cents=negotiation.agreed_unit_cents, buyer_kind=negotiation.buyer_kind, buyer_email=buyer_email,
        buyer_name=buyer_name or negotiation.buyer_name, ip_hash=ip_hash)
    negotiation.status, negotiation.invoice_id = "invoiced", invoice.id
    await db.commit()
    return invoice


async def for_shop(db: AsyncSession, shop: Shop, limit: int = 100) -> list[tuple[Negotiation, Offer, list]]:
    """The owner's view: every negotiation with its moves and reasons."""
    rows = await db.execute(select(Negotiation, Offer).join(Offer, Offer.id == Negotiation.offer_id)
                            .where(Negotiation.shop_id == shop.id)
                            .order_by(Negotiation.created_at.desc()).limit(limit))
    out = []
    for negotiation, offer in rows.all():
        out.append((negotiation, offer, await _moves(db, negotiation)))
    return out

