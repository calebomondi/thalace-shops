from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, OwnedShop
from app.schemas.chat import ChatIn, ChatMessageOut
from app.services import shop_agent

router = APIRouter(prefix="/shops/{shop_id}/chat", tags=["chat"])


@router.get("", response_model=list[ChatMessageOut])
async def conversation(shop: OwnedShop, db: DbSession) -> list[ChatMessageOut]:
    return [ChatMessageOut(**m) for m in await shop_agent.conversation(db, shop)]


@router.post("", response_model=list[ChatMessageOut])
async def send(body: ChatIn, shop: OwnedShop, user: CurrentUser, db: DbSession) -> list[ChatMessageOut]:
    """Say something to the shop's agent; returns this turn once it has answered."""
    return [ChatMessageOut(**m) for m in await shop_agent.run_turn(db, shop, user.id, body.message)]
