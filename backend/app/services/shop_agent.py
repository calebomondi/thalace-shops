"""Running the shop agent: one owner turn at a time, its conversation kept in
shop_messages, its tools reaching the shop only through DbShopStore.

A turn runs inside the request, with a wall-clock cap. The store opens its
own session per call, because the agent may call several tools at once."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.schemas.agent import (
    GroupOrderView,
    MarketOffer,
    MarketShop,
    OfferDraft,
    OfferView,
    PayeeView,
    Purchase,
    SalesSummary,
    ShopView,
)
from agents.schemas.shop import FULL_SHARE_BPS
from agents.shop.graph import ModelStep, build_shop_graph
from agents.shop.store import DraftOnlyError, PurchaseRefusedError, ShopNotFoundError
from agents.shop.tools import PageReader
from app.database.connect import AsyncSessionLocal
from app.database.models import (
    GroupOrder,
    Invoice,
    Negotiation,
    Offer,
    Payee,
    Shop,
    ShopMessage,
    ShopSupplier,
)
from app.services import directory, group_orders, procurement
from app.services import offers as offer_service
from app.services import platform as platform_service
from app.services.errors import RateLimitedError, ServiceError, UnavailableError
from config import settings
from data_sources.web.firecrawl import read_page
from utils.log import logger

# Messages shown to the owner at most, newest kept.
HISTORY_SHOWN = 200
# Messages replayed to the model at most; history_window trims further by tokens.
HISTORY_REPLAYED = 400


def _usd(cents: int) -> str:
    return f"{Decimal(cents) / 100:.2f}"


def _offer_view(offer: Offer) -> OfferView:
    return OfferView(id=offer.id, title=offer.title, description=offer.description, kind=offer.kind,
                     price_usd=_usd(offer.price_cents), floor_usd=_usd(offer.floor_cents), delivery=offer.delivery,
                     status=offer.status)


class DbShopStore:
    """The ShopStore for one shop, on the database. The agent's drafts are
    saved with created_by None, which marks them as the agent's."""

    def __init__(self, shop_id: uuid.UUID) -> None:
        self._shop_id = shop_id

    async def shop(self) -> ShopView:
        async with AsyncSessionLocal() as db:
            shop = await db.get(Shop, self._shop_id)
            if shop is None:
                raise ShopNotFoundError(str(self._shop_id))
            payees = await db.scalars(select(Payee).where(Payee.shop_id == shop.id).order_by(Payee.created_at))
            platform = await platform_service.get_platform(db)
            return ShopView(
                name=shop.name, slug=shop.slug, tagline=shop.tagline, description=shop.description,
                website=shop.website, status=shop.status, daily_budget_usd=f"{shop.daily_budget_usd:.2f}",
                platform_fee_percent=platform.fee_bps * 100 / FULL_SHARE_BPS,
                payees=[PayeeView(label=p.label, address=p.address, share_percent=p.share_bps * 100 / FULL_SHARE_BPS)
                        for p in payees])

    async def offers(self) -> list[OfferView]:
        async with AsyncSessionLocal() as db:
            rows = await db.scalars(select(Offer).where(Offer.shop_id == self._shop_id)
                                    .order_by(Offer.position, Offer.created_at).limit(settings.max_offers_per_shop))
            return [_offer_view(o) for o in rows]

    async def draft_offer(self, draft: OfferDraft) -> OfferView:
        async with AsyncSessionLocal() as db:
            shop = await db.get(Shop, self._shop_id)
            if shop is None:
                raise ShopNotFoundError(str(self._shop_id))
            offer = await offer_service.create_offer(
                db, shop, title=draft.title, description=draft.description, kind=draft.kind,
                price_cents=draft.price_cents, floor_cents=draft.floor_cents, delivery=draft.delivery,
                delivery_url=None, delivery_note=draft.delivery_note, created_by=None)
            return _offer_view(offer)

    async def update_draft(self, offer_id: uuid.UUID, draft: OfferDraft) -> OfferView:
        async with AsyncSessionLocal() as db:
            offer = await db.get(Offer, offer_id)
            if offer is None or offer.shop_id != self._shop_id:
                raise ShopNotFoundError(str(offer_id))
            if offer.status != "draft":
                raise DraftOnlyError(str(offer_id))
            offer = await offer_service.update_offer(db, offer, draft.model_dump())
            return _offer_view(offer)

    async def sales(self) -> SalesSummary:
        async with AsyncSessionLocal() as db:
            paid = (await db.execute(select(func.count(), func.coalesce(func.sum(Invoice.total_cents), 0))
                                     .where(Invoice.shop_id == self._shop_id,
                                            Invoice.status.in_(("paid", "delivered"))))).one()
            awaiting = await db.scalar(select(func.count()).select_from(Invoice).where(
                Invoice.shop_id == self._shop_id, Invoice.status == "awaiting_payment"))
            talks = await db.scalar(select(func.count()).select_from(Negotiation).where(
                Negotiation.shop_id == self._shop_id, Negotiation.status == "open"))
            groups = await db.scalar(select(func.count()).select_from(GroupOrder).where(
                GroupOrder.shop_id == self._shop_id, GroupOrder.status == "open"))
            return SalesSummary(invoices_paid=paid[0], revenue_usd=_usd(paid[1]), invoices_awaiting_payment=awaiting,
                                open_negotiations=talks, open_group_orders=groups)

    async def find_suppliers(self, query: str) -> list[MarketShop]:
        async with AsyncSessionLocal() as db:
            allowed = set(await db.scalars(select(ShopSupplier.supplier_shop_id)
                                           .where(ShopSupplier.shop_id == self._shop_id)))
            found = await directory.search(db, query)
            return [MarketShop(slug=s.slug, name=s.name, tagline=s.tagline, allowed_supplier=s.id in allowed,
                               offers=[MarketOffer(id=o.id, title=o.title, price_usd=_usd(o.price_cents), kind=o.kind)
                                       for o in offers])
                    for s, offers in found if s.id != self._shop_id]

    async def buy(self, offer_id: uuid.UUID, quantity: int) -> Purchase:
        async with AsyncSessionLocal() as db:
            buyer = await db.get(Shop, self._shop_id)
            try:
                invoice = await procurement.buy(db, buyer, offer_id=offer_id, quantity=quantity)
            except ServiceError as exc:
                raise PurchaseRefusedError(str(exc)) from None
            supplier = await db.get(Shop, invoice.shop_id)
            return Purchase(invoice_number=invoice.number, supplier=supplier.name, item=invoice.title,
                            quantity=invoice.quantity, total_usd=_usd(invoice.total_cents), status=invoice.status)

    async def open_group_orders(self) -> list[GroupOrderView]:
        async with AsyncSessionLocal() as db:
            return [_group_view(v) for v in await group_orders.market(db) if v.group.status == "open"]

    async def join_group_order(self, group_order_id: str, quantity: int) -> GroupOrderView:
        async with AsyncSessionLocal() as db:
            buyer = await db.get(Shop, self._shop_id)
            try:
                group = await group_orders.by_token(db, group_order_id)
                if group.shop_id == buyer.id:
                    raise PurchaseRefusedError("That group order is for this shop's own offer.")
                await group_orders.join(db, group_order_id, quantity=quantity, buyer_kind="shop",
                                        buyer_name=buyer.name, buyer_email=None, buyer_shop_id=buyer.id)
            except ServiceError as exc:
                raise PurchaseRefusedError(str(exc)) from None
            return _group_view(await group_orders.view(db, group))


def _group_view(v: group_orders.GroupView) -> GroupOrderView:
    return GroupOrderView(group_order_id=v.group.public_token, shop=v.shop.name, offer=v.offer.title,
                          committed_quantity=v.committed, unit_price_usd=_usd(v.unit_price_cents),
                          next_tier_quantity=v.next.min_quantity if v.next else None,
                          next_tier_price_usd=_usd(v.next.unit_price_cents) if v.next else None,
                          deadline=v.group.deadline.isoformat())


# -- Conversation storage -----------------------------------------------------

def _to_message(row: ShopMessage) -> AnyMessage:
    if row.role == "user":
        return HumanMessage(content=row.content, id=str(row.id))
    if row.role == "tool":
        return ToolMessage(content=row.content, tool_call_id=row.tool_call_id or "", name=row.tool_name,
                           id=str(row.id))
    return AIMessage(content=row.content, tool_calls=row.tool_calls or [], id=str(row.id))


def _to_row(shop_id: uuid.UUID, message: AnyMessage) -> ShopMessage:
    content = message.content if isinstance(message.content, str) else message.text
    if isinstance(message, ToolMessage):
        return ShopMessage(shop_id=shop_id, role="tool", content=content, tool_call_id=message.tool_call_id,
                           tool_name=message.name)
    calls = [{"id": c["id"], "name": c["name"], "args": c["args"]} for c in getattr(message, "tool_calls", None) or []]
    return ShopMessage(shop_id=shop_id, role="assistant", content=content, tool_calls=calls or None)


async def _history(db: AsyncSession, shop_id: uuid.UUID, limit: int) -> list[ShopMessage]:
    rows = await db.scalars(select(ShopMessage).where(ShopMessage.shop_id == shop_id)
                            .order_by(ShopMessage.created_at.desc(), ShopMessage.id.desc()).limit(limit))
    return list(reversed(list(rows)))


def transcript(rows: list[ShopMessage]) -> list[dict]:
    """What the owner sees: their messages and the agent's replies, each reply
    with the tools the agent used since the owner last spoke."""
    out: list[dict] = []
    actions: list[str] = []
    for row in rows:
        if row.role == "user":
            actions = []
            out.append({"id": row.id, "role": "user", "content": row.content, "actions": [],
                        "created_at": row.created_at})
        elif row.role == "assistant":
            actions += [c["name"] for c in row.tool_calls or []]
            if row.content.strip():
                out.append({"id": row.id, "role": "assistant", "content": row.content, "actions": actions,
                            "created_at": row.created_at})
                actions = []
    return out


async def conversation(db: AsyncSession, shop: Shop) -> list[dict]:
    return transcript(await _history(db, shop.id, HISTORY_SHOWN))


# -- One turn -----------------------------------------------------------------

async def _check_daily_limit(db: AsyncSession, owner_id: uuid.UUID) -> None:
    since = datetime.now(UTC) - timedelta(days=1)
    sent = await db.scalar(select(func.count()).select_from(ShopMessage)
                           .where(ShopMessage.author_id == owner_id, ShopMessage.created_at >= since))
    if sent >= settings.max_agent_turns_per_day:
        raise RateLimitedError(f"You've sent {settings.max_agent_turns_per_day} messages to your agents today. "
                               "Try again tomorrow.")


async def run_turn(db: AsyncSession, shop: Shop, owner_id: uuid.UUID, text: str, *,
                   model_step: ModelStep | None = None, page_reader: PageReader = read_page) -> list[dict]:
    """The owner says `text`; the agent works until it answers. Returns the
    turn as the owner sees it (their message, then the agent's replies)."""
    await _check_daily_limit(db, owner_id)
    history = [_to_message(r) for r in await _history(db, shop.id, HISTORY_REPLAYED)]
    asked = ShopMessage(shop_id=shop.id, role="user", content=text.strip(), author_id=owner_id)
    db.add(asked)
    await db.commit()

    graph_kwargs = {"model_step": model_step} if model_step else {}
    graph = build_shop_graph(DbShopStore(shop.id), page_reader, **graph_kwargs)
    start = [*history, HumanMessage(content=asked.content, id=str(asked.id))]
    try:
        result = await asyncio.wait_for(graph.ainvoke({"messages": start}),
                                        timeout=settings.agent_turn_timeout_s)
    except TimeoutError:
        logger.warning("Shop agent turn timed out for shop %s", shop.id)
        raise UnavailableError("Your agent took too long on that. Ask again, or ask for less at once.") from None
    except Exception:
        logger.exception("Shop agent turn failed for shop %s", shop.id)
        raise UnavailableError("Your agent couldn't answer just now. Try again in a minute.") from None

    new = result["messages"][len(start):]
    rows = [_to_row(shop.id, m) for m in new]
    db.add_all(rows)
    await db.commit()
    return transcript([asked, *rows])
