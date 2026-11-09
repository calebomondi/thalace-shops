"""Shops buying from shops: a shop's agent pays a supplier's invoice straight
from its own wallet, with an Intents transfer to the supplier's wallet.

The wallet's signed policy is what allows it: the supplier must be one of the
shop's allowed suppliers (a destination the owner signed), and the payment
counts against the daily cap. This code checks the same things first, so a
refusal is explained here rather than by the wallet. The purchase is a ledger
line in the buyer's one-at-a-time queue; when the transfer settles, the
supplier's invoice is paid."""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Invoice, LedgerEntry, Offer, Shop, ShopSupplier
from app.services import invoices
from app.services.errors import ConflictError, NotFoundError
from data_sources.near.agent_api import new_idempotency_key


async def _allowed(db: AsyncSession, buyer: Shop, supplier: Shop) -> bool:
    return await db.scalar(select(ShopSupplier.id).where(ShopSupplier.shop_id == buyer.id,
                                                         ShopSupplier.supplier_shop_id == supplier.id)) is not None


def _can_spend(buyer: Shop) -> None:
    if buyer.status != "live" or buyer.grant_id is None or buyer.agent_id is None:
        raise ConflictError("This shop can only buy once it's live.")
    if buyer.frozen_at is not None:
        raise ConflictError("This shop's wallet is frozen: nothing can be paid from it.")


async def pay_from_wallet(db: AsyncSession, buyer: Shop, invoice: Invoice) -> LedgerEntry:
    """Queue the payment of a supplier's invoice from the buyer shop's wallet."""
    _can_spend(buyer)
    supplier = await db.get(Shop, invoice.shop_id)
    if supplier is None or not supplier.wallet_account_id:
        raise ConflictError("That supplier has no wallet to pay into.")
    if not await _allowed(db, buyer, supplier):
        raise ConflictError(f"{supplier.name} isn't one of this shop's allowed suppliers. The owner can add it by "
                            "signing new rules.")
    if supplier.settlement_asset != buyer.settlement_asset:
        raise ConflictError("That supplier settles in another coin than this shop holds.")
    if invoice.status not in ("open", "expired", "failed"):
        raise ConflictError("That invoice isn't waiting for payment.")
    decimals = await invoices.settlement_decimals(buyer.settlement_asset)
    amount = invoices.atomic_amount(invoice.total_cents, decimals)
    invoice.status, invoice.pay_asset, invoice.pay_amount_raw = "awaiting_payment", buyer.settlement_asset, amount
    invoice.buyer_shop_id = buyer.id
    line = LedgerEntry(shop_id=buyer.id, invoice_id=invoice.id, kind="purchase", asset=buyer.settlement_asset,
                       amount_raw=amount, amount_usd=Decimal(invoice.total_cents) / 100,
                       counterparty=supplier.wallet_account_id,
                       idempotency_key=new_idempotency_key(f"purchase:{invoice.id}"))
    db.add(line)
    await db.commit()
    return line


async def buy(db: AsyncSession, buyer: Shop, *, offer_id: uuid.UUID, quantity: int) -> Invoice:
    """Buy an offer at its list price from an allowed supplier, paid from this shop's wallet."""
    _can_spend(buyer)
    offer = await db.get(Offer, offer_id)
    supplier = await db.get(Shop, offer.shop_id) if offer else None
    if offer is None or supplier is None:
        raise NotFoundError("No such offer.")
    if supplier.id == buyer.id:
        raise ConflictError("A shop can't buy from itself.")
    if not await _allowed(db, buyer, supplier):
        raise ConflictError(f"{supplier.name} isn't one of this shop's allowed suppliers. The owner can add it by "
                            "signing new rules.")
    invoice = await invoices.issue_invoice(db, supplier, offer_id=offer.id, quantity=quantity, unit_price_cents=None,
                                           buyer_kind="shop", buyer_email=None, buyer_name=buyer.name, ip_hash=None,
                                           buyer_shop_id=buyer.id)
    await pay_from_wallet(db, buyer, invoice)
    return invoice
