import uuid

from fastapi import APIRouter
from fastapi.responses import Response

from app.api.deps import DbSession, OwnedShop
from app.database.models import Invoice, Offer
from app.schemas.invoices import DeliverIn, LedgerLineOut, OwnerInvoiceOut
from app.services import invoices as invoice_service
from app.services import ledger as ledger_service

router = APIRouter(prefix="/shops/{shop_id}", tags=["invoices"])


def _out(invoice: Invoice, offer: Offer) -> OwnerInvoiceOut:
    return OwnerInvoiceOut(id=invoice.id, number=invoice.number, public_token=invoice.public_token,
                           title=invoice.title, quantity=invoice.quantity, total_cents=invoice.total_cents,
                           fee_bps=invoice.fee_bps, status=invoice.status, buyer_kind=invoice.buyer_kind,
                           buyer_email=invoice.buyer_email, buyer_name=invoice.buyer_name, delivery=offer.delivery,
                           deliverable=invoice.deliverable, created_at=invoice.created_at, paid_at=invoice.paid_at,
                           delivered_at=invoice.delivered_at)


@router.get("/invoices", response_model=list[OwnerInvoiceOut])
async def list_invoices(shop: OwnedShop, db: DbSession) -> list[OwnerInvoiceOut]:
    rows = await invoice_service.list_invoices(db, shop)
    offers = {o.id: o for o in [await db.get(Offer, oid) for oid in {i.offer_id for i in rows}]}
    return [_out(i, offers[i.offer_id]) for i in rows]


@router.post("/invoices/{invoice_id}/deliver", response_model=OwnerInvoiceOut)
async def deliver(invoice_id: uuid.UUID, body: DeliverIn, shop: OwnedShop, db: DbSession) -> OwnerInvoiceOut:
    invoice = await invoice_service.shop_invoice(db, shop, invoice_id)
    invoice = await invoice_service.mark_delivered(db, invoice, body.deliverable)
    return _out(invoice, await db.get(Offer, invoice.offer_id))


@router.get("/ledger", response_model=list[LedgerLineOut])
async def ledger(shop: OwnedShop, db: DbSession) -> list[LedgerLineOut]:
    return [LedgerLineOut(kind=e.kind, status=e.status, amount_usd=e.amount_usd, counterparty=e.counterparty,
                          invoice_number=i.number if i else None, tx_url=ledger_service.tx_url(e.tx_hash),
                          failure_code=e.failure_code, created_at=e.created_at, settled_at=e.settled_at)
            for e, i in await ledger_service.entries(db, shop)]


@router.get("/ledger.csv", response_class=Response)
async def ledger_csv(shop: OwnedShop, db: DbSession) -> Response:
    body = ledger_service.as_csv(shop, await ledger_service.entries(db, shop))
    return Response(body, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{shop.slug}-ledger.csv"'})
