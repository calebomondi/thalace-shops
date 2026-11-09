from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, OwnedShop
from app.schemas.rules import BudgetIn, PayeeOut, PayeesIn, PlatformTermsOut
from app.schemas.shops import ShopOut
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
