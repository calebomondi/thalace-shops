"""A shop's money rules, as the owner sets them before signing: who shares in
each sale (the payees) and the daily cap on what the shop may send out.

The platform fee comes off each sale first; the payees split what remains,
and whatever no payee takes stays in the shop's wallet. Once a shop is live
these rules are in its signed wallet policy, so changing them needs a new
owner signature: here they can only change while the shop is a draft."""

import re
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.schemas.shop import FULL_SHARE_BPS, PayeeRoute
from app.database.models import Payee, Shop
from app.services.errors import ConflictError, InvalidInputError
from config import settings

# NEAR account ids: named (alice.near) or implicit (64 hex).
_NEAR_ACCOUNT = r"^(([a-z\d]+[-_])*[a-z\d]+\.)*([a-z\d]+[-_])*[a-z\d]+$"


def _draft_only(shop: Shop) -> None:
    # Once the wallet exists (after the first signature), its policy holds
    # these rules, even before the shop is fully live.
    if shop.status != "draft" or shop.agent_id is not None:
        raise ConflictError("This shop's wallet holds these rules now: changing them needs a new signature from you.")


async def list_payees(db: AsyncSession, shop: Shop) -> list[Payee]:
    rows = await db.scalars(select(Payee).where(Payee.shop_id == shop.id).order_by(Payee.created_at)
                            .limit(settings.max_payees_per_shop))
    return list(rows)


async def replace_payees(db: AsyncSession, shop: Shop, payees: list[dict]) -> list[Payee]:
    """Set the whole revenue split at once, so shares are checked together."""
    _draft_only(shop)
    if len(payees) > settings.max_payees_per_shop:
        raise InvalidInputError(f"A shop pays at most {settings.max_payees_per_shop} payees.")
    if sum(p["share_bps"] for p in payees) > FULL_SHARE_BPS:
        raise InvalidInputError("The shares add up to more than 100%.")
    seen: set[tuple] = set()
    for p in payees:
        route: PayeeRoute = p["route"]
        if route == "transfer" and not re.fullmatch(_NEAR_ACCOUNT, p["address"]):
            raise InvalidInputError(f"{p['address']} isn't a NEAR account id.")
        if route == "withdraw" and not p.get("chain"):
            raise InvalidInputError("A payout to another chain needs the chain.")
        key = (route, p.get("chain"), p["address"])
        if key in seen:
            raise InvalidInputError(f"{p['address']} is listed twice.")
        seen.add(key)
    await db.execute(delete(Payee).where(Payee.shop_id == shop.id))
    for p in payees:
        db.add(Payee(shop_id=shop.id, label=p["label"].strip(), route=p["route"],
                     chain=p.get("chain") if p["route"] == "withdraw" else None, address=p["address"],
                     memo=p.get("memo"), share_bps=p["share_bps"]))
    await db.commit()
    return await list_payees(db, shop)


async def set_daily_budget(db: AsyncSession, shop: Shop, daily_budget_usd: Decimal) -> Shop:
    _draft_only(shop)
    if not Decimal(0) <= daily_budget_usd <= Decimal(settings.max_daily_budget_usd):
        raise InvalidInputError(f"The daily cap must be between $0 and ${settings.max_daily_budget_usd}.")
    shop.daily_budget_usd = daily_budget_usd
    await db.commit()
    await db.refresh(shop)
    return shop
