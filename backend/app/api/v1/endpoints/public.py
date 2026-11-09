"""What anyone can reach without signing in: a live shop's page, issuing an
invoice, an invoice by its unguessable token, paying it, and the shop's
public ledger. Buyers' emails never appear on anything public."""

from decimal import Decimal

from fastapi import APIRouter, Request, status

from app.api.deps import DbSession, client_ip_hash
from app.schemas.invoices import (
    DeliveryOut,
    InvoiceCreate,
    LedgerLineOut,
    PayIn,
    PaymentOut,
    PayOption,
    PublicInvoiceOut,
    PublicOffer,
    PublicShopOut,
)
from app.schemas.negotiations import DirectoryShopOut
from app.services import directory
from app.services import invoices as invoice_service
from app.services import ledger as ledger_service

router = APIRouter(prefix="/public", tags=["public"])


def _invoice_out(view: invoice_service.InvoiceView) -> PublicInvoiceOut:
    invoice, offer, coin = view.invoice, view.offer, view.coin
    payment = None
    if invoice.pay_asset and invoice.pay_amount_raw is not None:
        decimals = coin.decimals if coin else 6
        payment = PaymentOut(asset_id=invoice.pay_asset, symbol=coin.symbol if coin else None,
                             chain=coin.blockchain if coin else None,
                             amount=(invoice.pay_amount_raw / Decimal(10) ** decimals).quantize(
                                 Decimal(1).scaleb(-decimals)),
                             address=invoice.deposit_address, memo=invoice.deposit_memo,
                             expires_at=invoice.deposit_expires_at)
    delivery = None
    if invoice.status in ("paid", "delivered"):
        delivery = DeliveryOut(url=offer.delivery_url if offer.delivery == "link" else None,
                               note=offer.delivery_note, deliverable=invoice.deliverable)
    return PublicInvoiceOut(
        number=invoice.number, public_token=invoice.public_token, shop_slug=view.shop.slug, shop_name=view.shop.name,
        title=invoice.title, quantity=invoice.quantity, unit_price_cents=invoice.unit_price_cents,
        total_cents=invoice.total_cents, status=invoice.status, buyer_name=invoice.buyer_name, payment=payment,
        payment_tx_url=ledger_service.tx_url(invoice.payment_tx_hash), refund_tx_hash=invoice.refund_tx_hash,
        failure_code=invoice.failure_code, delivery=delivery, created_at=invoice.created_at,
        paid_at=invoice.paid_at, delivered_at=invoice.delivered_at)


@router.get("/shops/{slug}", response_model=PublicShopOut)
async def shop_page(slug: str, db: DbSession) -> PublicShopOut:
    shop = await invoice_service.public_shop(db, slug)
    offers = await invoice_service.active_offers(db, shop)
    options = await invoice_service.pay_options()
    return PublicShopOut(
        slug=shop.slug, name=shop.name, tagline=shop.tagline, description=shop.description, website=shop.website,
        selling=invoice_service.selling(shop), wallet_account_id=shop.wallet_account_id,
        offers=[PublicOffer(id=o.id, title=o.title, description=o.description, kind=o.kind,
                            price_cents=o.price_cents, delivery=o.delivery) for o in offers],
        pay_options=[PayOption(asset_id=t.asset_id, symbol=t.symbol, chain=t.blockchain) for t in options])


@router.post("/shops/{slug}/invoices", response_model=PublicInvoiceOut, status_code=status.HTTP_201_CREATED)
async def issue_invoice(slug: str, body: InvoiceCreate, request: Request, db: DbSession) -> PublicInvoiceOut:
    shop = await invoice_service.public_shop(db, slug)
    invoice = await invoice_service.issue_invoice(
        db, shop, offer_id=body.offer_id, quantity=body.quantity, unit_price_cents=None, buyer_kind="person",
        buyer_email=str(body.buyer_email), buyer_name=body.buyer_name, ip_hash=client_ip_hash(request))
    return _invoice_out(await invoice_service.view(db, invoice))


@router.get("/invoices/{token}", response_model=PublicInvoiceOut)
async def invoice_page(token: str, db: DbSession) -> PublicInvoiceOut:
    invoice = await invoice_service.invoice_by_token(db, token)
    await invoice_service.check_invoice(db, invoice)
    return _invoice_out(await invoice_service.view(db, invoice))


@router.post("/invoices/{token}/pay", response_model=PublicInvoiceOut)
async def pay_invoice(token: str, body: PayIn, db: DbSession) -> PublicInvoiceOut:
    invoice = await invoice_service.invoice_by_token(db, token)
    invoice = await invoice_service.quote_payment(db, invoice, body.pay_asset)
    return _invoice_out(await invoice_service.view(db, invoice))


@router.get("/shops/{slug}/ledger", response_model=list[LedgerLineOut])
async def public_ledger(slug: str, db: DbSession) -> list[LedgerLineOut]:
    shop = await invoice_service.public_shop(db, slug)
    rows = await ledger_service.entries(db, shop)
    # Public: the counterparty of a sale is a buyer, so it isn't shown.
    return [LedgerLineOut(kind=e.kind, status=e.status, amount_usd=e.amount_usd,
                          counterparty=None if e.kind == "sale" else e.counterparty,
                          invoice_number=i.number if i else None, tx_url=ledger_service.tx_url(e.tx_hash),
                          failure_code=e.failure_code, created_at=e.created_at, settled_at=e.settled_at)
            for e, i in rows]


@router.get("/directory", response_model=list[DirectoryShopOut])
async def search_directory(db: DbSession, q: str = "") -> list[DirectoryShopOut]:
    """Live shops and their offers, matching every word of `q`. List prices only."""
    return [DirectoryShopOut(slug=s.slug, name=s.name, tagline=s.tagline,
                             offers=[{"id": str(o.id), "title": o.title, "price_cents": o.price_cents,
                                      "kind": o.kind} for o in offers])
            for s, offers in await directory.search(db, q[:200])]
