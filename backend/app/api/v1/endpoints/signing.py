from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession, OwnedShop
from app.schemas.shops import ShopOut
from app.schemas.signing import (
    FreezeIn,
    PasskeyIn,
    PasskeyStatusOut,
    PendingSignatureOut,
    RulesChangeIn,
    SignatureStatusOut,
    SignedIn,
)
from app.services import signing

router = APIRouter(tags=["signing"])


def _status(row, shop) -> SignatureStatusOut:
    return SignatureStatusOut(correlation_id=row.correlation_id, type=row.type, status=row.status,
                              failure_code=row.failure_code, shop=ShopOut.of(shop))


@router.get("/passkeys/current", response_model=PasskeyStatusOut)
async def passkey_status(user: CurrentUser, db: DbSession) -> PasskeyStatusOut:
    origin, rp_id = signing.site()
    return PasskeyStatusOut(has_passkey=await signing.current_passkey(db, user.id) is not None, rp_id=rp_id,
                            origin=origin)


@router.post("/passkeys", response_model=PasskeyStatusOut, status_code=status.HTTP_201_CREATED)
async def add_passkey(body: PasskeyIn, user: CurrentUser, db: DbSession) -> PasskeyStatusOut:
    row = await signing.register_passkey(db, user.id, signing.PasskeyIn(**body.model_dump()))
    return PasskeyStatusOut(has_passkey=True, rp_id=row.rp_id, origin=row.origin)


@router.post("/shops/{shop_id}/signatures", response_model=PendingSignatureOut,
             status_code=status.HTTP_201_CREATED)
async def request_signature(shop: OwnedShop, user: CurrentUser, db: DbSession) -> PendingSignatureOut:
    """The next request the owner signs to take the shop live."""
    pending = await signing.request_signature(db, shop, user.id)
    return PendingSignatureOut(**pending.__dict__)


@router.post("/shops/{shop_id}/signatures/{correlation_id}", response_model=SignatureStatusOut)
async def submit_signature(correlation_id: str, body: SignedIn, shop: OwnedShop, user: CurrentUser,
                           db: DbSession) -> SignatureStatusOut:
    row = await signing.submit_signature(db, shop, user.id, correlation_id, body.signed_data)
    return _status(row, shop)


@router.get("/shops/{shop_id}/signatures/{correlation_id}", response_model=SignatureStatusOut)
async def signature_status(correlation_id: str, shop: OwnedShop, user: CurrentUser,
                           db: DbSession) -> SignatureStatusOut:
    return _status(await signing.refresh_signature(db, shop, user.id, correlation_id), shop)


@router.post("/shops/{shop_id}/wallet/freeze", response_model=PendingSignatureOut,
             status_code=status.HTTP_201_CREATED)
async def request_freeze(body: FreezeIn, shop: OwnedShop, user: CurrentUser, db: DbSession) -> PendingSignatureOut:
    """The wallet's emergency stop (or its release), for the owner to sign."""
    return PendingSignatureOut(**(await signing.request_freeze(db, shop, user.id, body.freeze)).__dict__)


@router.post("/shops/{shop_id}/wallet/rules", response_model=PendingSignatureOut,
             status_code=status.HTTP_201_CREATED)
async def request_rules_change(body: RulesChangeIn, shop: OwnedShop, user: CurrentUser,
                               db: DbSession) -> PendingSignatureOut:
    """New payees, cap and allowed suppliers for a live shop, for the owner to sign."""
    pending = await signing.request_rules_change(
        db, shop, user.id, payees=[p.model_dump() for p in body.payees], daily_budget_usd=body.daily_budget_usd,
        supplier_shop_ids=body.supplier_shop_ids)
    return PendingSignatureOut(**pending.__dict__)
