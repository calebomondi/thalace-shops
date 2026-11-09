from fastapi import APIRouter

from app.api.deps import DbSession, OwnedShop
from app.schemas.negotiations import MoveOut, NegotiationOut
from app.services import negotiation as negotiation_service

router = APIRouter(prefix="/shops/{shop_id}/negotiations", tags=["negotiations"])


@router.get("", response_model=list[NegotiationOut])
async def list_negotiations(shop: OwnedShop, db: DbSession) -> list[NegotiationOut]:
    return [NegotiationOut(id=n.id, offer_title=o.title, list_price_cents=o.price_cents, floor_cents=o.floor_cents,
                           buyer_kind=n.buyer_kind, buyer_name=n.buyer_name, quantity=n.quantity, status=n.status,
                           agreed_unit_cents=n.agreed_unit_cents, created_at=n.created_at,
                           moves=[MoveOut(side=m.side, move=m.move, unit_price_cents=m.unit_price_cents,
                                          message=m.message, created_at=m.created_at) for m in moves])
            for n, o, moves in await negotiation_service.for_shop(db, shop)]
