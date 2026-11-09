from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.schemas.me import MeOut

router = APIRouter(tags=["me"])


@router.get("/me", response_model=MeOut)
async def me(user: CurrentUser) -> MeOut:
    return MeOut(id=user.id, email=user.email, name=user.name, is_admin=user.is_admin)
