"""The platform's terms: the fee on each sale and where it goes. One row,
seeded from settings the first time it's read; after that only an admin
changes it, every change audited."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AdminAuditLog, PlatformSettings
from app.services.errors import InvalidInputError
from app.supabase_auth import AuthUser
from config import settings


def _snapshot(row: PlatformSettings) -> dict:
    return {"fee_bps": row.fee_bps, "max_fee_bps": row.max_fee_bps, "fee_account": row.fee_account}


async def get_platform(db: AsyncSession) -> PlatformSettings:
    row = await db.get(PlatformSettings, 1)
    if row is not None:
        return row
    if not settings.near_mainnet_platform_treasury_wallet_address:
        raise InvalidInputError("NEAR_MAINNET_PLATFORM_TREASURY_WALLET_ADDRESS must be set before the platform runs.")
    # Two first readers at once must not both insert.
    await db.execute(insert(PlatformSettings).values(
        id=1, fee_bps=settings.platform_fee_bps, max_fee_bps=settings.platform_fee_max_bps,
        fee_account=settings.near_mainnet_platform_treasury_wallet_address,
    ).on_conflict_do_nothing(index_elements=["id"]))
    await db.commit()
    return await db.scalar(select(PlatformSettings).where(PlatformSettings.id == 1))


async def set_fee(db: AsyncSession, admin: AuthUser, fee_bps: int) -> PlatformSettings:
    """Change the fee for invoices issued from now on. Never above the
    maximum owners agreed to; raising that maximum isn't done here."""
    row = await get_platform(db)
    if not 0 <= fee_bps <= row.max_fee_bps:
        raise InvalidInputError(f"The fee must be between 0 and {row.max_fee_bps / 100:g}%.")
    before = _snapshot(row)
    row.fee_bps = fee_bps
    row.updated_by = admin.id
    db.add(AdminAuditLog(actor_id=admin.id, actor_email=admin.email, action="platform.set_fee",
                         target="platform_settings:1", before=before, after=_snapshot(row)))
    await db.commit()
    await db.refresh(row)
    return row
