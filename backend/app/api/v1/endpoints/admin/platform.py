from fastapi import APIRouter

from app.api.deps import AdminUser, DbSession
from app.schemas.platform import FeeUpdate, PlatformOut
from app.services import platform as platform_service

router = APIRouter(prefix="/admin/platform", tags=["admin"])


@router.get("", response_model=PlatformOut)
async def get_platform(_: AdminUser, db: DbSession) -> PlatformOut:
    return PlatformOut.model_validate(await platform_service.get_platform(db))


@router.patch("/fee", response_model=PlatformOut)
async def set_fee(body: FeeUpdate, admin: AdminUser, db: DbSession) -> PlatformOut:
    return PlatformOut.model_validate(await platform_service.set_fee(db, admin, body.fee_bps))
