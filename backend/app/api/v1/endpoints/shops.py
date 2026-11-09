from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession, OwnedShop
from app.schemas.shops import ShopCreate, ShopOut, ShopUpdate
from app.services import shops as shop_service

router = APIRouter(prefix="/shops", tags=["shops"])


@router.post("", response_model=ShopOut, status_code=status.HTTP_201_CREATED)
async def create_shop(body: ShopCreate, user: CurrentUser, db: DbSession) -> ShopOut:
    shop = await shop_service.create_shop(db, user.id, name=body.name, slug=body.slug, tagline=body.tagline,
                                          description=body.description,
                                          website=str(body.website) if body.website else None)
    return ShopOut.of(shop)


@router.get("", response_model=list[ShopOut])
async def list_shops(user: CurrentUser, db: DbSession) -> list[ShopOut]:
    return [ShopOut.of(shop) for shop in await shop_service.list_shops(db, user.id)]


@router.get("/{shop_id}", response_model=ShopOut)
async def get_shop(shop: OwnedShop) -> ShopOut:
    return ShopOut.of(shop)


@router.patch("/{shop_id}", response_model=ShopOut)
async def update_shop(body: ShopUpdate, shop: OwnedShop, db: DbSession) -> ShopOut:
    fields = body.model_dump(exclude_unset=True)
    website = fields.get("website")
    shop = await shop_service.update_shop(
        db, shop, name=fields.get("name"), tagline=fields.get("tagline"), description=fields.get("description"),
        website=(str(website) if website else "") if "website" in fields else None)
    return ShopOut.of(shop)
