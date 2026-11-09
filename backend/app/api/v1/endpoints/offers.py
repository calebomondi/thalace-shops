import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession, OwnedShop
from app.schemas.offers import OfferCreate, OfferOut, OfferUpdate
from app.services import offers as offer_service

router = APIRouter(prefix="/shops/{shop_id}/offers", tags=["offers"])


@router.get("", response_model=list[OfferOut])
async def list_offers(shop: OwnedShop, db: DbSession, include_archived: bool = False) -> list[OfferOut]:
    return [OfferOut.of(o) for o in await offer_service.list_offers(db, shop, include_archived=include_archived)]


@router.post("", response_model=OfferOut, status_code=status.HTTP_201_CREATED)
async def create_offer(body: OfferCreate, shop: OwnedShop, user: CurrentUser, db: DbSession) -> OfferOut:
    offer = await offer_service.create_offer(db, shop, created_by=user.id, **body.model_dump())
    return OfferOut.of(offer)


@router.patch("/{offer_id}", response_model=OfferOut)
async def update_offer(offer_id: uuid.UUID, body: OfferUpdate, shop: OwnedShop, db: DbSession) -> OfferOut:
    offer = await offer_service.shop_offer(db, shop, offer_id)
    return OfferOut.of(await offer_service.update_offer(db, offer, body.model_dump(exclude_unset=True)))
