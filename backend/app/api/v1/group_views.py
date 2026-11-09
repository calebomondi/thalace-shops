"""Turning a group order into what the API returns, shared by the owner's,
the public and the MCP views. Invoice tokens are included only where the
reader may see them."""

from app.database.models import Invoice
from app.schemas.group_orders import GroupMemberOut, GroupOrderOut, TierOut
from app.services.group_orders import GroupView


def group_out(v: GroupView, invoices_by_id: dict | None = None) -> GroupOrderOut:
    by_id: dict = invoices_by_id or {}
    members = []
    for m in v.members:
        invoice: Invoice | None = by_id.get(m.invoice_id)
        members.append(GroupMemberOut(buyer_kind=m.buyer_kind, buyer_name=m.buyer_name, quantity=m.quantity,
                                      invoice_token=invoice.public_token if invoice else None))
    return GroupOrderOut(
        group_order_id=v.group.public_token, shop_slug=v.shop.slug, shop_name=v.shop.name, offer_id=v.offer.id,
        offer_title=v.offer.title, status=v.group.status, opened_by=v.group.opened_by, deadline=v.group.deadline,
        committed_quantity=v.committed, unit_price_cents=v.unit_price_cents, list_price_cents=v.offer.price_cents,
        next_tier=TierOut(min_quantity=v.next.min_quantity, unit_price_cents=v.next.unit_price_cents)
        if v.next else None,
        tiers=[TierOut(min_quantity=t.min_quantity, unit_price_cents=t.unit_price_cents) for t in v.tiers],
        members=members, closed_at=v.group.closed_at)
