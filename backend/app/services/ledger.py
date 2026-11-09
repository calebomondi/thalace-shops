"""Reading a shop's ledger: for its owner, as a public page, and as a CSV an
accountant can open without asking a question."""

import csv
import io

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Invoice, LedgerEntry, Shop

LEDGER_LIMIT = 1_000
NEARBLOCKS_TX = "https://nearblocks.io/txns/"

_KIND_TEXT = {"sale": "Sale", "fee": "Platform fee", "payout": "Payout", "refund": "Refund"}


async def entries(db: AsyncSession, shop: Shop) -> list[tuple[LedgerEntry, Invoice | None]]:
    rows = await db.execute(select(LedgerEntry, Invoice).outerjoin(Invoice, Invoice.id == LedgerEntry.invoice_id)
                            .where(LedgerEntry.shop_id == shop.id)
                            .order_by(LedgerEntry.created_at.desc()).limit(LEDGER_LIMIT))
    return [(entry, invoice) for entry, invoice in rows.all()]


def tx_url(tx_hash: str | None) -> str | None:
    return f"{NEARBLOCKS_TX}{tx_hash}" if tx_hash else None


def signed_usd(entry: LedgerEntry) -> str:
    """Money in as positive, money out (fees, payouts, refunds) as negative."""
    if entry.amount_usd is None:
        return ""
    amount = -entry.amount_usd if entry.kind in ("fee", "payout", "refund") else entry.amount_usd
    return f"{amount:.2f}"


def as_csv(shop: Shop, rows: list[tuple[LedgerEntry, Invoice | None]]) -> str:
    """One line per ledger entry, oldest first, amounts in US dollars."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Date (UTC)", "Shop", "Invoice", "Type", "Description", "Counterparty", "Amount (USD)",
                     "Status", "Transaction"])
    for entry, invoice in reversed(rows):
        writer.writerow([
            entry.created_at.strftime("%Y-%m-%d %H:%M:%S"), shop.name, invoice.number if invoice else "",
            _KIND_TEXT.get(entry.kind, entry.kind), invoice.title if invoice else "", entry.counterparty or "",
            signed_usd(entry), entry.status, tx_url(entry.tx_hash) or "",
        ])
    return out.getvalue()
