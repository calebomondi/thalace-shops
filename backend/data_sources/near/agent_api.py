"""The NEAR Intents Agent API (docs.agentsonintents.com): a wallet per shop,
held in an attested enclave, that only acts within a policy its owner signed.

Two kinds of call:
- Owner intents (create the agent, grant us access, freeze it, change its
  rules): we generate the request, the owner's wallet signs it in the
  browser, we submit what the wallet returned. The payloads are relayed
  untouched, since the API checks they are exactly what it sent.
- Actions under a grant (transfer, withdraw), with our partner key and the
  shop's grant token. Deposits need neither a grant nor a signature.

Amounts are atomic-unit strings throughout, as the API takes them."""

import base64
import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from config import settings
from utils.log import logger

# Status values an operation can report. Everything outside FINAL moves on
# its own, so the caller keeps polling the same correlation_id.
OperationStatus = Literal[
    "PENDING_SIGNATURE", "PENDING_DEPOSIT", "PENDING_APPROVAL", "QUEUED", "PROCESSING", "UNCERTAIN",
    "SUCCESS", "FAILED", "REFUNDED", "NEEDS_REVIEW",
]
FINAL: frozenset[str] = frozenset({"SUCCESS", "FAILED", "REFUNDED", "NEEDS_REVIEW"})
OwnerIntentType = Literal[
    "agent_create", "policy_update", "agent_freeze", "agent_unfreeze", "grant_issue", "grant_revoke",
]
# The API holds a status request open this long waiting for a change.
MAX_WAIT_MS = 30_000
GRANT_PREFIX = "ngt_"


class AgentApiError(Exception):
    """The Agent API refused or could not be reached. `code` is the API's own
    stable code (e.g. `wallet_busy`, `policy_destination_denied`), or ours:
    `not_configured`, `unreachable`, `bad_response`."""

    def __init__(self, code: str, detail: str = "", *, status: int | None = None, layer: str | None = None,
                 retryable: bool = False, available_at: str | None = None) -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code, self.detail, self.status, self.layer = code, detail, status, layer
        self.retryable, self.available_at = retryable, available_at


@dataclass(frozen=True)
class Token:
    asset_id: str
    symbol: str
    decimals: int
    blockchain: str
    price_usd: float | None


@dataclass(frozen=True)
class Balance:
    asset_id: str
    symbol: str | None
    balance_raw: str
    available_raw: str


@dataclass(frozen=True)
class Operation:
    """Where an owner intent, deposit or action stands."""
    correlation_id: str
    type: str
    status: OperationStatus
    failure_code: str | None = None
    agent_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def final(self) -> bool:
        return self.status in FINAL


@dataclass(frozen=True)
class GeneratedIntent:
    """An owner intent waiting for its signature. `intent` and `preview` go to
    the owner's browser as they are; nothing else does."""
    correlation_id: str
    type: str
    expires_at: str
    intent: dict[str, Any]
    preview: dict[str, Any]
    agent_id: str | None = None


def new_grant_credential() -> tuple[str, str]:
    """A fresh grant token and the SHA-256 commitment the owner signs. The
    token is a spending password within the policy: store it encrypted and
    never send it to a browser or a prompt."""
    token = GRANT_PREFIX + base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    return token, hashlib.sha256(token.encode()).hexdigest()


def new_idempotency_key(prefix: str) -> str:
    """A key for one logical request (8-128 of A-Za-z0-9._:-). Save it with
    the record before sending, so a retry after a crash reuses it."""
    return f"{prefix}:{secrets.token_urlsafe(18)}"


def _error(response: httpx.Response) -> AgentApiError:
    try:
        first = (response.json().get("errors") or [{}])[0]
    except ValueError:
        first = {}
    meta = first.get("meta") or {}
    return AgentApiError(first.get("code") or f"http_{response.status_code}", first.get("detail") or "",
                         status=response.status_code, layer=first.get("layer"),
                         retryable=bool(meta.get("retryable")), available_at=meta.get("available_at"))


def _operation(body: dict[str, Any]) -> Operation:
    try:
        return Operation(correlation_id=body["correlation_id"], type=body.get("type") or "",
                         status=body["status"], failure_code=body.get("failure_code"),
                         agent_id=body.get("agent_id"), details=body.get("details") or {})
    except KeyError as missing:
        raise AgentApiError("bad_response", f"operation without {missing}") from None


class AgentApi:
    """One client per request scope; `transport` lets tests answer for the API."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 timeout_s: float | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._key = settings.near_intents_agent_api_key if api_key is None else api_key
        self._base = (base_url or settings.near_intents_agent_api_url).rstrip("/")
        self._timeout = timeout_s or settings.near_intents_timeout_s
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self._key)

    async def _call(self, method: str, path: str, *, json: dict[str, Any] | None = None,
                    params: dict[str, Any] | None = None, grant: str | None = None,
                    idempotency_key: str | None = None, keyless: bool = False) -> Any:
        if not keyless and not self._key:
            raise AgentApiError("not_configured", "NEAR_INTENTS_AGENT_API_KEY is not set")
        headers = {} if keyless else {"X-API-Key": self._key}
        if grant:
            headers["X-Grant-Token"] = grant
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            async with httpx.AsyncClient(base_url=self._base, timeout=self._timeout,
                                         transport=self._transport) as client:
                response = await client.request(method, path, json=json, params=params, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("Agent API %s %s unreachable: %s", method, path, exc)
            raise AgentApiError("unreachable", str(exc)) from exc
        if response.status_code >= 400:
            error = _error(response)
            logger.warning("Agent API %s %s refused: %s (%s)", method, path, error.code, error.status)
            raise error
        try:
            return response.json()
        except ValueError:
            raise AgentApiError("bad_response", f"{method} {path} did not return JSON") from None

    # -- Public reads --

    async def tokens(self) -> list[Token]:
        body = await self._call("GET", "/v1/tokens", keyless=True)
        return [Token(asset_id=t["asset_id"], symbol=t["symbol"], decimals=t["decimals"],
                      blockchain=t["blockchain"], price_usd=t.get("price")) for t in body.get("data", [])]

    # -- Owner intents --

    async def generate_intent(self, kind: OwnerIntentType, fields: dict[str, Any], *,
                              idempotency_key: str | None = None) -> GeneratedIntent:
        body = await self._call("POST", "/v1/generate-intent", json={"type": kind, **fields},
                                idempotency_key=idempotency_key)
        try:
            return GeneratedIntent(correlation_id=body["correlation_id"], type=body.get("type") or kind,
                                   expires_at=body["expires_at"], intent=body["intent"],
                                   preview=body.get("preview") or {}, agent_id=body.get("agent_id"))
        except KeyError as missing:
            raise AgentApiError("bad_response", f"generated intent without {missing}") from None

    async def submit_intent(self, kind: OwnerIntentType, correlation_id: str,
                            signed_data: dict[str, Any]) -> None:
        await self._call("POST", "/v1/submit-intent",
                         json={"type": kind, "correlation_id": correlation_id, "signed_data": signed_data})

    async def status(self, correlation_id: str, *, wait_ms: int = 0) -> Operation:
        params = {"correlation_id": correlation_id}
        if wait_ms:
            params["wait_ms"] = min(wait_ms, MAX_WAIT_MS)
        return _operation(await self._call("GET", "/v1/status", params=params))

    async def agent(self, agent_id: str) -> dict[str, Any]:
        """The agent, with `status` and `wallet.near_account_id`."""
        return await self._call("GET", f"/v1/agents/{agent_id}")

    async def policy(self, agent_id: str) -> dict[str, Any]:
        """The policy in force, its `revision` (for a `policy_update`) and usage."""
        return await self._call("GET", f"/v1/agents/{agent_id}/policy")

    async def balances(self, agent_id: str) -> list[Balance]:
        body = await self._call("GET", f"/v1/agents/{agent_id}/balances", params={"source": "public"})
        return [Balance(asset_id=b["asset_id"], symbol=b.get("symbol"), balance_raw=b["balance_raw"],
                        available_raw=b.get("available_raw") or b["balance_raw"])
                for b in body.get("balances", [])]

    # -- Money in --

    async def deposit(self, agent_id: str, *, origin_asset: str, amount: str | None,
                      destination_asset: str | None, idempotency_key: str) -> Operation:
        """A one-time address a buyer pays into. With `amount`, it's quoted for
        exactly that; `destination_asset` converts the payment on arrival.
        A wrong or late payment is refunded into the agent's own balance."""
        body: dict[str, Any] = {"origin_asset": origin_asset}
        if amount is not None:
            body["amount"] = amount
        if destination_asset and destination_asset != origin_asset:
            body["destination_asset"] = destination_asset
        return _operation(await self._call("POST", f"/v1/agents/{agent_id}/deposit", json=body,
                                           idempotency_key=idempotency_key))

    # -- Money out, under the shop's grant and within its policy --

    async def transfer(self, agent_id: str, grant: str, *, asset: str, amount: str, recipient: str,
                       idempotency_key: str) -> Operation:
        """To another NEAR Intents account (a payee listed in the policy)."""
        return _operation(await self._call(
            "POST", f"/v1/agents/{agent_id}/transfer", grant=grant, idempotency_key=idempotency_key,
            json={"asset": asset, "amount": amount, "recipient": recipient}))

    async def withdraw(self, agent_id: str, grant: str, *, asset: str, amount: str, chain: str,
                       recipient: str, memo: str | None, idempotency_key: str) -> Operation:
        """Out of NEAR Intents to an address on `chain` (listed in the policy)."""
        body: dict[str, Any] = {"asset": asset, "amount": amount, "chain": chain, "recipient": recipient}
        if memo:
            body["memo"] = memo
        return _operation(await self._call("POST", f"/v1/agents/{agent_id}/withdraw", grant=grant,
                                           idempotency_key=idempotency_key, json=body))
