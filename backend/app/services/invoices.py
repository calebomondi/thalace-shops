"""Buying from a shop: the public shop page, issuing an invoice, quoting a
payment for it, and watching the money arrive.

A buyer (a person, an agent, or another shop) gets an invoice: a number,
the line bought, the total and the platform fee in force. When they pick a
dollar stablecoin on any chain, the shop's wallet quotes a one-time deposit
address for exactly the total, credited as the shop's settlement asset.
A late, short or failed payment is refunded by NEAR Intents into the shop's
own wallet, never back to the buyer; the invoice says so. Ported from the
gtmx Store's checkout (built 2026-11-03)."""

import re
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agents.schemas.shop import BuyerKind
from app.database.connect import AsyncSessionLocal
from app.database.models import Invoice, LedgerEntry, Offer, Shop
from app.services import platform as platform_service
from app.services import signing
from app.services.errors import ConflictError, InvalidInputError, NotFoundError, RateLimitedError
from config import settings
from data_sources.near.agent_api import AgentApiError, Operation, Token, new_idempotency_key
from utils.log import logger

_RATE_WINDOW = timedelta(hours=1)
_tokens: tuple[float, dict[str, Token]] = (0.0, {})


async def pay_options() -> list[Token]:
    """The coins a buyer may pay with, as NEAR Intents lists them now."""
    global _tokens
    read_at, by_id = _tokens
    if time.monotonic() - read_at > settings.tokens_cache_s or not by_id:
        try:
            by_id = {t.asset_id: t for t in await signing.agent_api().tokens()}
        except AgentApiError as exc:
            if not by_id:
                raise ConflictError("Payment options can't be read right now. Try again in a minute.") from exc
            logger.warning("Token list not refreshed, using the last one: %s", exc.code)
        else:
            _tokens = (time.monotonic(), by_id)
    return [by_id[a] for a in settings.pay_assets if a in by_id]


async def settlement_decimals(asset_id: str) -> int:
    """Decimals of a shop's settlement asset, as NEAR Intents lists it."""
    for token in await pay_options():
        if token.asset_id == asset_id:
            return token.decimals
    raise ConflictError(f"NEAR Intents doesn't list {asset_id}.")


def atomic_amount(cents: int, decimals: int) -> Decimal:
    """A USD amount as atomic units of a dollar stablecoin: $29.50 in a
    6-decimal coin is 29_500_000."""
    if decimals < 2:
        raise InvalidInputError("That coin can't express cents.")
    return Decimal(cents) * Decimal(10) ** (decimals - 2)


def invoice_prefix(slug: str) -> str:
    """Initials of the shop's address: shanga-prints -> SP."""
    words = [w for w in re.split(r"[^a-z0-9]+", slug) if w]
    initials = "".join(w[0] for w in words).upper()[:4]
    return initials if len(initials) >= 2 else slug[:3].upper()


def _parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


# -- The public shop ----------------------------------------------------------

async def public_shop(db: AsyncSession, slug: str) -> Shop:
    shop = await db.scalar(select(Shop).where(Shop.slug == slug))
    # A shop still being set up isn't there for the public yet.
    if shop is None or shop.status == "draft":
        raise NotFoundError("No such shop.")
    return shop


def selling(shop: Shop) -> bool:
    return shop.status == "live" and shop.frozen_at is None


async def active_offers(db: AsyncSession, shop: Shop) -> list[Offer]:
    rows = await db.scalars(select(Offer).where(Offer.shop_id == shop.id, Offer.status == "active")
                            .order_by(Offer.position, Offer.created_at).limit(settings.max_offers_per_shop))
    return list(rows)


# -- Issuing an invoice -------------------------------------------------------

async def _check_rate(db: AsyncSession, ip_hash: str | None) -> None:
    if ip_hash is None:
        return
    recent = await db.scalar(select(func.count()).select_from(Invoice).where(
        Invoice.ip_hash == ip_hash, Invoice.created_at >= datetime.now(UTC) - _RATE_WINDOW))
    if recent >= settings.invoices_per_ip_per_hour:
        raise RateLimitedError("Too many invoices from this network. Try again in an hour.",
                               retry_after_s=int(_RATE_WINDOW.total_seconds()))


async def _next_number(db: AsyncSession, shop: Shop) -> str:
    # The row update locks the shop until commit, so two invoices never share a number.
    seq = await db.scalar(update(Shop).where(Shop.id == shop.id).values(invoice_seq=Shop.invoice_seq + 1)
                          .returning(Shop.invoice_seq))
    return f"{invoice_prefix(shop.slug)}-{seq:04d}"


async def issue_invoice(db: AsyncSession, shop: Shop, *, offer_id: uuid.UUID, quantity: int,
                        unit_price_cents: int | None, buyer_kind: BuyerKind, buyer_email: str | None,
                        buyer_name: str | None, ip_hash: str | None, buyer_shop_id: uuid.UUID | None = None
                        ) -> Invoice:
    """An invoice for an offer on sale. The unit price is the list price
    unless a negotiation agreed another, which can never be below the floor."""
    if not selling(shop):
        raise ConflictError("This shop isn't taking orders right now.")
    offer = await db.get(Offer, offer_id)
    if offer is None or offer.shop_id != shop.id or offer.status != "active":
        raise NotFoundError("That offer isn't on sale.")
    if not 0 < quantity <= settings.max_invoice_quantity:
        raise InvalidInputError(f"The quantity must be between 1 and {settings.max_invoice_quantity}.")
    price = offer.price_cents if unit_price_cents is None else unit_price_cents
    if price < offer.floor_cents:
        raise InvalidInputError("That price is below what this shop accepts.")
    await _check_rate(db, ip_hash)
    platform = await platform_service.get_platform(db)
    invoice = Invoice(shop_id=shop.id, number=await _next_number(db, shop), public_token=secrets.token_urlsafe(24),
                      offer_id=offer.id, title=offer.title, quantity=quantity, unit_price_cents=price,
                      total_cents=price * quantity, fee_bps=platform.fee_bps, buyer_kind=buyer_kind,
                      buyer_email=buyer_email, buyer_name=buyer_name, ip_hash=ip_hash, buyer_shop_id=buyer_shop_id)
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return invoice


async def invoice_by_token(db: AsyncSession, public_token: str) -> Invoice:
    invoice = await db.scalar(select(Invoice).where(Invoice.public_token == public_token))
    if invoice is None:
        raise NotFoundError("No such invoice.")
    return invoice


# -- Paying it ----------------------------------------------------------------

# A new address only when no live one exists: a payment into a replaced
# address would reach the shop's wallet with no invoice tracking it.
_PAYABLE = frozenset({"open", "expired", "failed"})


async def quote_payment(db: AsyncSession, invoice: Invoice, pay_asset: str) -> Invoice:
    """The one-time address this invoice is paid into, for exactly its total
    in the chosen coin. After a quote runs out it can be paid again under the
    same invoice number, with a new address."""
    if invoice.status == "awaiting_payment":
        raise ConflictError("This invoice already has a payment address. Pay it, or wait for it to expire.")
    if invoice.status not in _PAYABLE:
        raise ConflictError("This invoice can't be paid now.")
    shop = await db.get(Shop, invoice.shop_id)
    if not selling(shop):
        raise ConflictError("This shop isn't taking payments right now.")
    coin = next((t for t in await pay_options() if t.asset_id == pay_asset), None)
    if coin is None:
        raise InvalidInputError("This shop doesn't take that coin.")
    invoice.pay_asset = pay_asset
    invoice.pay_amount_raw = atomic_amount(invoice.total_cents, coin.decimals)
    invoice.deposit_idempotency_key = new_idempotency_key(f"invoice:{invoice.id}")
    invoice.deposit_correlation_id = invoice.deposit_address = invoice.deposit_memo = None
    invoice.deposit_expires_at = invoice.failure_code = None
    # Saved with its key first, so a crash before the address comes back can
    # ask for the same address again rather than a second one.
    await db.commit()
    try:
        op = await signing.agent_api().deposit(
            shop.agent_id, origin_asset=pay_asset, amount=str(invoice.pay_amount_raw),
            destination_asset=shop.settlement_asset, idempotency_key=invoice.deposit_idempotency_key)
    except AgentApiError as exc:
        invoice.status, invoice.failure_code = "failed", exc.code
        await db.commit()
        logger.warning("Shop %s: no deposit address for invoice %s: %s %s", shop.id, invoice.number, exc.code,
                       exc.detail)
        if exc.code == "amount_too_low":
            raise ConflictError("That amount is below what this coin's route accepts. Pick another coin.") from exc
        raise ConflictError("The payment address couldn't be made. Try again in a minute.") from exc
    details = op.details
    if not details.get("deposit_address"):
        invoice.status, invoice.failure_code = "failed", "deposit_address_missing"
        await db.commit()
        raise ConflictError("The payment address couldn't be made. Try again in a minute.")
    invoice.status = "awaiting_payment"
    invoice.deposit_correlation_id = op.correlation_id
    invoice.deposit_address, invoice.deposit_memo = details["deposit_address"], details.get("memo")
    invoice.deposit_expires_at = _parse_time(details.get("expires_at"))
    await db.commit()
    await db.refresh(invoice)
    return invoice


# -- Watching payments --------------------------------------------------------

def _usd(cents: int) -> Decimal:
    return Decimal(cents) / 100


async def _record_sale(db: AsyncSession, invoice: Invoice, shop: Shop) -> None:
    db.add(LedgerEntry(shop_id=shop.id, invoice_id=invoice.id, kind="sale", status="done", asset=shop.settlement_asset,
                       amount_raw=invoice.credited_raw or Decimal(0), amount_usd=_usd(invoice.total_cents),
                       counterparty=invoice.buyer_email or invoice.buyer_name, tx_hash=invoice.payment_tx_hash,
                       correlation_id=invoice.deposit_correlation_id, settled_at=invoice.paid_at))


async def settle_payment(db: AsyncSession, invoice: Invoice, op: Operation) -> None:
    """Move an unpaid invoice on from its deposit's status."""
    invoice.checked_at = datetime.now(UTC)
    if not op.final:
        return
    shop = await db.get(Shop, invoice.shop_id)
    details = op.details
    if op.status == "SUCCESS":
        invoice.status, invoice.paid_at = "paid", datetime.now(UTC)
        out = details.get("amount_out")
        invoice.credited_raw = Decimal(out) if out else None
        invoice.payment_tx_hash = details.get("destination_tx_hash") or details.get("tx_hash")
        await _record_sale(db, invoice, shop)
        await _deliver_link(db, invoice)
        return
    invoice.failure_code = op.failure_code or details.get("failure_reason") or op.status.lower()
    invoice.refund_tx_hash = details.get("refund_tx_hash")
    if op.failure_code == "deposit_expired":
        invoice.status = "expired"
    else:
        invoice.status = "refunded" if op.status == "REFUNDED" else "failed"


async def settle_by_transfer(db: AsyncSession, invoice: Invoice, amount_raw: Decimal, tx_hash: str | None) -> None:
    """Another shop paid this invoice from its wallet with an Intents transfer
    (procurement): there's no deposit to watch, so the confirmed transfer is the
    payment. The rest is a normal sale: the seller's ledger, fee and payouts."""
    if invoice.status not in ("awaiting_payment", "open"):
        return
    shop = await db.get(Shop, invoice.shop_id)
    invoice.status, invoice.paid_at = "paid", datetime.now(UTC)
    invoice.credited_raw, invoice.payment_tx_hash = amount_raw, tx_hash
    await _record_sale(db, invoice, shop)
    await _deliver_link(db, invoice)


async def _deliver_link(db: AsyncSession, invoice: Invoice) -> None:
    """A link offer is delivered the moment it's paid: the invoice page shows it."""
    offer = await db.get(Offer, invoice.offer_id)
    if offer is not None and offer.delivery == "link":
        invoice.status, invoice.delivered_at = "delivered", datetime.now(UTC)


async def check_invoice(db: AsyncSession, invoice: Invoice) -> None:
    """Ask the Agent API about this invoice's payment now (the invoice page
    does, when the watcher hasn't lately)."""
    if invoice.status != "awaiting_payment" or invoice.deposit_correlation_id is None:
        return
    fresh = timedelta(seconds=settings.invoice_recheck_s)
    if invoice.checked_at and datetime.now(UTC) - invoice.checked_at < fresh:
        return
    try:
        op = await signing.agent_api().status(invoice.deposit_correlation_id)
    except AgentApiError as exc:
        logger.warning("Invoice %s: payment status not read: %s", invoice.number, exc.code)
        return
    await settle_payment(db, invoice, op)
    await db.commit()


async def watch_invoices() -> int:
    """Read the payment of each invoice awaiting one, least recently checked
    first. Returns how many were paid."""
    async with AsyncSessionLocal() as db:
        rows = list((await db.scalars(
            select(Invoice).where(Invoice.status == "awaiting_payment", Invoice.deposit_correlation_id.is_not(None))
            .order_by(Invoice.checked_at.asc().nulls_first()).limit(settings.watcher_batch))).all())
        api, paid = signing.agent_api(), 0
        for invoice in rows:
            try:
                op = await api.status(invoice.deposit_correlation_id)
            except AgentApiError as exc:
                logger.warning("Invoice %s: payment status not read: %s", invoice.number, exc.code)
                continue
            await settle_payment(db, invoice, op)
            paid += invoice.status in ("paid", "delivered")
            await db.commit()
        return paid


# -- The owner's side ---------------------------------------------------------

async def list_invoices(db: AsyncSession, shop: Shop, limit: int = 200) -> list[Invoice]:
    rows = await db.scalars(select(Invoice).where(Invoice.shop_id == shop.id)
                            .order_by(Invoice.created_at.desc()).limit(limit))
    return list(rows)


async def shop_invoice(db: AsyncSession, shop: Shop, invoice_id: uuid.UUID) -> Invoice:
    invoice = await db.get(Invoice, invoice_id)
    if invoice is None or invoice.shop_id != shop.id:
        raise NotFoundError("Invoice not found.")
    return invoice


async def mark_delivered(db: AsyncSession, invoice: Invoice, deliverable: str | None) -> Invoice:
    """The owner (or later, the agent) hands over what was bought: a written
    deliverable shown on the invoice, or a note that the service is done."""
    if invoice.status != "paid":
        raise ConflictError("Only a paid invoice can be marked delivered.")
    invoice.deliverable = (deliverable or "").strip() or None
    invoice.status, invoice.delivered_at = "delivered", datetime.now(UTC)
    await db.commit()
    await db.refresh(invoice)
    return invoice


@dataclass(frozen=True)
class InvoiceView:
    invoice: Invoice
    shop: Shop
    offer: Offer
    coin: Token | None


async def view(db: AsyncSession, invoice: Invoice) -> InvoiceView:
    shop = await db.get(Shop, invoice.shop_id)
    offer = await db.get(Offer, invoice.offer_id)
    coin = None
    if invoice.pay_asset:
        coin = next((t for t in await pay_options() if t.asset_id == invoice.pay_asset), None)
    return InvoiceView(invoice=invoice, shop=shop, offer=offer, coin=coin)
