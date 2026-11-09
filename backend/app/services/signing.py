"""Going live: the owner signs with their passkey, twice per shop.

1. `agent_create`: the Agent API opens a wallet for the shop under a policy
   built from the owner's rules: money may leave only to the payees and the
   platform fee account, in the shop's settlement asset, within the daily cap.
2. `grant_issue`: the owner lets our backend act for that wallet, inside
   that policy. The grant token is made here, stored encrypted, and never
   leaves the backend.

We generate each request, the owner's browser signs it unchanged, and we
submit what it signed. Only the person a request was generated for may
submit it. Ported from the gtmx Thalace Store (built 2026-11-01..03)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.schemas.shop import ShopIntentType
from app.database.models import OwnerPasskey, Payee, Shop, ShopIntent
from app.services import platform as platform_service
from app.services.errors import ConflictError, InvalidInputError, NotFoundError
from config import settings
from data_sources.near.agent_api import AgentApi, AgentApiError, Operation, new_grant_credential, new_idempotency_key
from utils.log import logger

GRANT_LABEL = "Thalace Shops"
# Money actions a shop's wallet may run in an hour: a burst of payouts after sales.
MAX_ACTIONS_PER_HOUR = 60
# How long a submit waits for the API to finish an owner request.
SUBMIT_WAIT_MS = 20_000
NOT_CONFIGURED = "Shops can't go live on this server yet: its NEAR Intents settings aren't complete."


def agent_api() -> AgentApi:
    """The client every signing call goes through; tests answer for it."""
    return AgentApi()


def _fernet() -> Fernet:
    if not settings.shop_grant_key:
        raise ConflictError(NOT_CONFIGURED)
    return Fernet(settings.shop_grant_key.encode())


def encrypt_grant(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decrypt_grant(encrypted: str) -> str:
    """The grant token, for one call to the Agent API. Never log or return it."""
    try:
        return _fernet().decrypt(encrypted.encode()).decode()
    except InvalidToken:
        logger.error("A shop grant token could not be decrypted: SHOP_GRANT_KEY changed?")
        raise ConflictError("The shop's access to its wallet can't be read. Its owner needs to sign again.") from None


def _refusal(exc: AgentApiError) -> ConflictError:
    if exc.code == "not_configured":
        return ConflictError(NOT_CONFIGURED)
    if exc.code == "unreachable":
        return ConflictError("NEAR Intents didn't answer. Try again in a minute.")
    return ConflictError(f"NEAR Intents refused this ({exc.code}).")


# -- The owner's passkey ------------------------------------------------------

@dataclass(frozen=True)
class PasskeyIn:
    credential_id: str
    public_key: str
    rp_id: str
    origin: str


def site() -> tuple[str, str]:
    """This app's origin and passkey rp_id: passkeys are bound to them for good."""
    parts = urlsplit(settings.frontend_base_url)
    return f"{parts.scheme}://{parts.netloc}", parts.hostname or ""


async def current_passkey(db: AsyncSession, user_id: uuid.UUID) -> OwnerPasskey | None:
    _, rp_id = site()
    return await db.scalar(select(OwnerPasskey).where(OwnerPasskey.user_id == user_id, OwnerPasskey.rp_id == rp_id))


async def register_passkey(db: AsyncSession, user_id: uuid.UUID, passkey: PasskeyIn) -> OwnerPasskey:
    """Save the founder's passkey for this site. It must be for this site, and
    there's one per founder per site: it signs for every shop they take live."""
    origin, rp_id = site()
    if passkey.origin.rstrip("/") != origin or passkey.rp_id != rp_id:
        raise InvalidInputError("That passkey isn't for this site.")
    if await current_passkey(db, user_id) is not None:
        raise ConflictError("You already have a passkey for this site; it signs for all your shops.")
    row = OwnerPasskey(user_id=user_id, credential_id=passkey.credential_id, public_key=passkey.public_key,
                       rp_id=rp_id, origin=origin)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


# -- The policy ---------------------------------------------------------------

def destination(payee: Payee) -> dict[str, Any]:
    if payee.route == "transfer":
        return {"action": "transfer", "address": payee.address, "confidential": False}
    return {"action": "withdraw", "chain": payee.chain, "address": payee.address, "memo": payee.memo}


def build_policy(shop: Shop, payees: list[Payee], fee_account: str) -> dict[str, Any]:
    """The rules the owner signs. Money leaves only to the payees and the fee
    account, only in the shop's settlement asset, never past the daily cap.
    The agent and our backend act inside it and can't change it."""
    destinations = [{"action": "transfer", "address": fee_account, "confidential": False}]
    destinations += [destination(p) for p in payees if not (p.route == "transfer" and p.address == fee_account)]
    return {
        "frozen": False,
        "actions": ["transfer", "withdraw"],
        "confidential": False,
        "owner_approval": False,
        "assets": [shop.settlement_asset],
        "max_actions_per_hour": MAX_ACTIONS_PER_HOUR,
        "destinations": {"mode": "only", "list": destinations},
        "budget": {"daily_usd": f"{shop.daily_budget_usd:.2f}", "weekly_usd": None, "monthly_usd": None},
        "timelock_ms": 0,
    }


# -- Signature requests -------------------------------------------------------

@dataclass(frozen=True)
class PendingSignature:
    """What the owner's browser gets: the request to sign, and what it means."""
    correlation_id: str
    type: ShopIntentType
    intent: dict[str, Any]
    preview: dict[str, Any]
    expires_at: datetime


def next_signature(shop: Shop) -> ShopIntentType | None:
    """What going live still needs from the owner, if anything."""
    if shop.agent_id is None:
        return "agent_create"
    if shop.grant_id is None:
        return "grant_issue"
    return None


async def _owner_passkey(db: AsyncSession, shop: Shop, user_id: uuid.UUID) -> OwnerPasskey:
    if shop.owner_passkey_id is not None:
        passkey = await db.get(OwnerPasskey, shop.owner_passkey_id)
    else:
        passkey = await current_passkey(db, user_id)
    if passkey is None:
        raise ConflictError("Add your passkey for this site first.")
    return passkey


async def request_signature(db: AsyncSession, shop: Shop, user_id: uuid.UUID) -> PendingSignature:
    """Generate the next request the owner signs to take the shop live."""
    kind = next_signature(shop)
    if kind is None:
        raise ConflictError("The shop is already live.")
    passkey = await _owner_passkey(db, shop, user_id)
    token_enc = None
    if kind == "agent_create":
        payees = list((await db.scalars(select(Payee).where(Payee.shop_id == shop.id))).all())
        platform = await platform_service.get_platform(db)
        fields = {"name": shop.name, "external_user_id": str(shop.id),
                  "policy": build_policy(shop, payees, platform.fee_account),
                  "owner": {"type": "passkey", "credential_id": passkey.credential_id,
                            "public_key": passkey.public_key, "rp_id": passkey.rp_id, "origin": passkey.origin}}
        shop.owner_passkey_id = passkey.id
    else:
        token, commitment = new_grant_credential()
        token_enc = encrypt_grant(token)
        expires = datetime.now(UTC) + timedelta(days=settings.shop_grant_days)
        fields = {"agent_id": shop.agent_id, "label": GRANT_LABEL, "credential": commitment,
                  "expires_at": expires.isoformat().replace("+00:00", "Z")}
    try:
        generated = await agent_api().generate_intent(kind, fields,
                                                      idempotency_key=new_idempotency_key(f"{kind}:{shop.id}"))
    except AgentApiError as exc:
        raise _refusal(exc) from exc
    expires_at = datetime.fromisoformat(generated.expires_at.replace("Z", "+00:00"))
    db.add(ShopIntent(shop_id=shop.id, correlation_id=generated.correlation_id, type=kind, requested_by=user_id,
                      grant_token_enc=token_enc, expires_at=expires_at))
    await db.commit()
    return PendingSignature(correlation_id=generated.correlation_id, type=kind, intent=generated.intent,
                            preview=generated.preview, expires_at=expires_at)


async def _intent(db: AsyncSession, shop: Shop, correlation_id: str, user_id: uuid.UUID) -> ShopIntent:
    row = await db.scalar(select(ShopIntent).where(ShopIntent.correlation_id == correlation_id,
                                                   ShopIntent.shop_id == shop.id))
    # Someone else's request reads as missing, like any resource that isn't yours.
    if row is None or row.requested_by != user_id:
        raise NotFoundError("No such signature request.")
    return row


async def _apply_create(shop: Shop, op: Operation) -> None:
    shop.agent_id = op.agent_id or op.details.get("agent_id")
    shop.policy_revision = op.details.get("revision")
    try:
        agent = await agent_api().agent(shop.agent_id)
    except AgentApiError:
        # The wallet exists; its address is read again on the next refresh.
        logger.warning("Shop %s: agent %s created but not read back", shop.id, shop.agent_id)
        return
    shop.wallet_account_id = (agent.get("wallet") or {}).get("near_account_id")
    shop.owner_account_id = (agent.get("owner_account") or {}).get("account_id")


def _apply_grant(shop: Shop, row: ShopIntent, op: Operation) -> None:
    grant = op.details.get("grant") or {}
    shop.grant_id = grant.get("grant_id")
    shop.grant_token_enc, row.grant_token_enc = row.grant_token_enc, None
    expires = grant.get("expires_at")
    shop.grant_expires_at = datetime.fromisoformat(expires.replace("Z", "+00:00")) if expires else None
    shop.status, shop.live_since = "live", datetime.now(UTC)


async def _settle(db: AsyncSession, shop: Shop, row: ShopIntent, op: Operation) -> None:
    """Record a finished owner request: its effect on the shop, or why it failed."""
    if not op.final:
        return
    row.completed_at = datetime.now(UTC)
    if op.status != "SUCCESS":
        row.status, row.failure_code, row.grant_token_enc = "failed", op.failure_code or op.status.lower(), None
    else:
        row.status = "succeeded"
        if row.type == "agent_create":
            await _apply_create(shop, op)
        elif row.type == "grant_issue":
            _apply_grant(shop, row, op)


async def submit_signature(db: AsyncSession, shop: Shop, user_id: uuid.UUID, correlation_id: str,
                           signed_data: dict[str, Any]) -> ShopIntent:
    row = await _intent(db, shop, correlation_id, user_id)
    if row.status != "awaiting_signature":
        raise ConflictError("This request was already submitted.")
    if row.expires_at <= datetime.now(UTC):
        row.status, row.grant_token_enc = "expired", None
        await db.commit()
        raise ConflictError("The time to sign ran out. Start again.")
    api = agent_api()
    try:
        await api.submit_intent(row.type, correlation_id, signed_data)
        row.status = "submitted"
        await db.commit()
        await _settle(db, shop, row, await api.status(correlation_id, wait_ms=SUBMIT_WAIT_MS))
    except AgentApiError as exc:
        raise _refusal(exc) from exc
    await db.commit()
    await db.refresh(shop)
    return row


async def refresh_signature(db: AsyncSession, shop: Shop, user_id: uuid.UUID, correlation_id: str) -> ShopIntent:
    """Where a submitted request stands, settling it once the API has."""
    row = await _intent(db, shop, correlation_id, user_id)
    if row.status == "submitted":
        try:
            await _settle(db, shop, row, await agent_api().status(correlation_id))
        except AgentApiError as exc:
            raise _refusal(exc) from exc
        await db.commit()
        await db.refresh(shop)
    return row
