from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, OwnedShop
from app.schemas.rules import BudgetIn, PayeeOut, PayeesIn, PlatformTermsOut
from app.schemas.shops import ShopOut, SupplierOut
from app.services import platform as platform_service
from app.services import rules as rule_service

router = APIRouter(tags=["rules"])


@router.get("/platform/terms", response_model=PlatformTermsOut)
async def platform_terms(_: CurrentUser, db: DbSession) -> PlatformTermsOut:
    return PlatformTermsOut.model_validate(await platform_service.get_platform(db))


@router.get("/shops/{shop_id}/payees", response_model=list[PayeeOut])
async def list_payees(shop: OwnedShop, db: DbSession) -> list[PayeeOut]:
    return [PayeeOut.model_validate(p) for p in await rule_service.list_payees(db, shop)]


@router.put("/shops/{shop_id}/payees", response_model=list[PayeeOut])
async def replace_payees(body: PayeesIn, shop: OwnedShop, db: DbSession) -> list[PayeeOut]:
    payees = await rule_service.replace_payees(db, shop, [p.model_dump() for p in body.payees])
    return [PayeeOut.model_validate(p) for p in payees]


@router.put("/shops/{shop_id}/budget", response_model=ShopOut)
async def set_budget(body: BudgetIn, shop: OwnedShop, db: DbSession) -> ShopOut:
    return ShopOut.of(await rule_service.set_daily_budget(db, shop, body.daily_budget_usd))


@router.get("/shops/{shop_id}/suppliers", response_model=list[SupplierOut])
async def list_suppliers(shop: OwnedShop, db: DbSession) -> list[SupplierOut]:
    """The shops this shop may buy from, as its signed policy allows."""
    return [SupplierOut(id=s.id, slug=s.slug, name=s.name, wallet_account_id=s.wallet_account_id)
            for s in await rule_service.list_suppliers(db, shop)]
