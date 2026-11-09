"""After a sale: the platform's fee and each payee's share go out of the
shop's wallet, on their own as the watcher goes round.

The fee comes off the credited amount first; payees split what remains, and
whatever no payee takes stays in the shop's wallet. Each line is written to
the ledger as pending, with its idempotency key, before it's sent, so a crash
or a retry never pays twice. One money action runs per wallet at a time, as
NEAR Intents requires. The wallet's signed policy refuses any destination but
the payees and the fee account, and anything past the daily cap, whatever
this code asks. Ported from the gtmx Store's fulfilment (built 2026-11-03)."""

from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.schemas.shop import FULL_SHARE_BPS
from app.database.connect import AsyncSessionLocal
from app.database.models import Invoice, LedgerEntry, Payee, Shop
from app.services import platform as platform_service
from app.services import signing
from app.services.errors import ConflictError
from app.services.invoices import pay_options
from config import settings
from data_sources.near.agent_api import AgentApi, AgentApiError, new_idempotency_key
from utils.log import logger

# Refusals that pass with time or the owner's action: the line stays pending
# and is sent again, under the same key, on a later round.
WAIT_CODES = frozenset({"wallet_busy", "spend_budget_exceeded", "policy_limit_exceeded",
                        "policy_action_limit_exceeded", "policy_schedule_denied", "wallet_frozen", "policy_not_ready"})
_OUTGOING = ("fee", "payout")


async def _decimals(asset: str) -> int:
    for token in await pay_options():
        if token.asset_id == asset:
            return token.decimals
    raise ConflictError(f"NEAR Intents doesn't list {asset}.")


def split(base: Decimal, fee_bps: int, payees: list[Payee]) -> tuple[Decimal, list[tuple[Payee, Decimal]]]:
    """The fee off the top, then each payee's share of the rest, rounded down
    so the shop never sends more than it was credited."""
    fee = (base * fee_bps / FULL_SHARE_BPS).to_integral_value(ROUND_DOWN)
    net = base - fee
    shares = [(p, (net * p.share_bps / FULL_SHARE_BPS).to_integral_value(ROUND_DOWN)) for p in payees]
    return fee, [(p, amount) for p, amount in shares if amount > 0]


def _line(shop: Shop, invoice: Invoice, kind: str, amount: Decimal, counterparty: str, decimals: int,
          payee: Payee | None = None) -> LedgerEntry:
    return LedgerEntry(shop_id=shop.id, invoice_id=invoice.id, payee_id=payee.id if payee else None, kind=kind,
                       asset=shop.settlement_asset, amount_raw=amount,
                       amount_usd=(amount / Decimal(10) ** decimals).quantize(Decimal("0.01")),
                       counterparty=counterparty, idempotency_key=new_idempotency_key(f"{kind}:{invoice.id}"))


async def plan_payouts(db: AsyncSession) -> int:
    """Write the pending fee and payout lines for each paid invoice that has
    none yet. Returns how many lines were written."""
    planned = exists().where(LedgerEntry.invoice_id == Invoice.id, LedgerEntry.kind.in_(_OUTGOING))
    invoices = list((await db.scalars(
        select(Invoice).join(Shop, Shop.id == Invoice.shop_id)
        .where(Invoice.status.in_(("paid", "delivered")), Invoice.credited_raw.is_not(None),
               Shop.grant_id.is_not(None), ~planned)
        .order_by(Invoice.paid_at).limit(settings.watcher_batch))).all())
    if not invoices:
        return 0
    platform = await platform_service.get_platform(db)
    written = 0
    for invoice in invoices:
        shop = await db.get(Shop, invoice.shop_id)
        decimals = await _decimals(shop.settlement_asset)
        payees = list((await db.scalars(select(Payee).where(Payee.shop_id == shop.id))).all())
        fee, shares = split(invoice.credited_raw, invoice.fee_bps, payees)
        if fee > 0:
            db.add(_line(shop, invoice, "fee", fee, platform.fee_account, decimals))
            written += 1
        for payee, amount in shares:
            db.add(_line(shop, invoice, "payout", amount, payee.address, decimals, payee))
            written += 1
    await db.commit()
    return written


async def _send(api: AgentApi, shop: Shop, entry: LedgerEntry, payee: Payee | None) -> None:
    grant = signing.decrypt_grant(shop.grant_token_enc)
    common = {"asset": entry.asset, "amount": str(entry.amount_raw), "idempotency_key": entry.idempotency_key}
    if payee is None or payee.route == "transfer":
        op = await api.transfer(shop.agent_id, grant, recipient=entry.counterparty, **common)
    else:
        op = await api.withdraw(shop.agent_id, grant, chain=payee.chain, recipient=payee.address, memo=payee.memo,
                                **common)
    entry.correlation_id = op.correlation_id


def _failed(entry: LedgerEntry, code: str) -> None:
    entry.status, entry.failure_code, entry.settled_at = "failed", code, datetime.now(UTC)
    logger.warning("Ledger %s (%s to %s) failed: %s; the money stays in the shop's wallet",
                   entry.id, entry.kind, entry.counterparty, code)


async def send_payouts(db: AsyncSession) -> int:
    """Send the oldest unsent fee or payout of each shop whose wallet is idle.
    Returns how many were sent."""
    in_flight = select(LedgerEntry.shop_id).where(LedgerEntry.kind.in_(_OUTGOING), LedgerEntry.status == "pending",
                                                  LedgerEntry.correlation_id.is_not(None))
    entries = list((await db.scalars(
        select(LedgerEntry).where(LedgerEntry.kind.in_(_OUTGOING), LedgerEntry.status == "pending",
                                  LedgerEntry.correlation_id.is_(None), LedgerEntry.shop_id.not_in(in_flight))
        .order_by(LedgerEntry.created_at).limit(settings.watcher_batch))).all())
    api, sent, busy = signing.agent_api(), 0, set()
    for entry in entries:
        if entry.shop_id in busy:
            continue
        busy.add(entry.shop_id)
        shop = await db.get(Shop, entry.shop_id)
        payee = await db.get(Payee, entry.payee_id) if entry.payee_id else None
        if shop.frozen_at is not None or (entry.kind == "payout" and payee is None):
            continue
        try:
            await _send(api, shop, entry, payee)
            sent += 1
        except AgentApiError as exc:
            if exc.retryable or exc.code in WAIT_CODES or exc.code == "unreachable":
                logger.info("Shop %s %s %s waits: %s", shop.id, entry.kind, entry.id, exc.code)
            else:
                _failed(entry, exc.code)
        except ConflictError as exc:
            # The grant can't be read (SHOP_GRANT_KEY unset or changed): nothing was sent.
            logger.error("Shop %s %s %s not sent: %s", shop.id, entry.kind, entry.id, exc)
        await db.commit()
    return sent


async def settle_payouts(db: AsyncSession) -> int:
    """Read each sent fee or payout until it settles. Returns how many completed."""
    entries = list((await db.scalars(
        select(LedgerEntry).where(LedgerEntry.kind.in_(_OUTGOING), LedgerEntry.status == "pending",
                                  LedgerEntry.correlation_id.is_not(None))
        .order_by(LedgerEntry.created_at).limit(settings.watcher_batch))).all())
    api, done = signing.agent_api(), 0
    for entry in entries:
        try:
            op = await api.status(entry.correlation_id)
        except AgentApiError as exc:
            logger.warning("Ledger %s: status not read: %s", entry.id, exc.code)
            continue
        if not op.final:
            continue
        if op.status == "SUCCESS":
            entry.status, entry.settled_at = "done", datetime.now(UTC)
            entry.tx_hash = op.details.get("tx_hash") or op.details.get("destination_tx_hash")
            done += 1
        else:
            _failed(entry, op.failure_code or op.status.lower())
        await db.commit()
    return done


async def fulfil() -> int:
    """One round after the payment watcher: plan the fee and payouts, settle
    what was sent, then send the next. Settling first frees a wallet whose
    last action finished, so its next line goes out in the same round.
    Returns how many completed."""
    async with AsyncSessionLocal() as db:
        await plan_payouts(db)
        done = await settle_payouts(db)
        await send_payouts(db)
        return done

