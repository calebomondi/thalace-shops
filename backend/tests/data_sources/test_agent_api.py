"""The NEAR Intents Agent API client: the headers each call needs, what a
refusal turns into, and the shapes we read back."""

import hashlib
import json

import httpx
import pytest

from data_sources.near.agent_api import AgentApi, AgentApiError, new_grant_credential, new_idempotency_key


def _api(handler, key="naa_test"):
    return AgentApi(api_key=key, base_url="https://agent.test", timeout_s=5, transport=httpx.MockTransport(handler))


def test_a_grant_credential_is_a_token_and_its_sha256():
    token, commitment = new_grant_credential()
    assert token.startswith("ngt_") and len(token) == 4 + 43
    assert commitment == hashlib.sha256(token.encode()).hexdigest()
    assert new_grant_credential()[0] != token


def test_idempotency_keys_fit_the_api_alphabet():
    key = new_idempotency_key("order:42")
    assert 8 <= len(key) <= 128 and all(c.isalnum() or c in "._:-" for c in key)


async def test_without_a_key_nothing_is_sent():
    def handler(request):
        raise AssertionError("no request without a key")

    with pytest.raises(AgentApiError) as refused:
        await _api(handler, key="").balances("a1")
    assert refused.value.code == "not_configured"


async def test_tokens_are_public():
    def handler(request):
        assert "X-API-Key" not in request.headers
        return httpx.Response(200, json={"data": [{"asset_id": "nep141:usdt.tether-token.near", "symbol": "USDT",
                                                   "decimals": 6, "blockchain": "near", "price": 0.9987}]})

    [usdt] = await _api(handler).tokens()
    assert (usdt.symbol, usdt.decimals, usdt.price_usd) == ("USDT", 6, 0.9987)


async def test_a_deposit_asks_for_an_exact_amount_converted_on_arrival():
    def handler(request):
        assert request.url.path == "/v1/agents/a1/deposit"
        assert request.headers["X-API-Key"] == "naa_test" and request.headers["Idempotency-Key"] == "order:1:abcdefgh"
        assert "X-Grant-Token" not in request.headers
        assert json.loads(request.content) == {"origin_asset": "nep141:sol-usdc", "amount": "29000000",
                                               "destination_asset": "nep141:near-usdc"}
        return httpx.Response(202, json={"correlation_id": "op_1", "type": "deposit", "status": "PENDING_DEPOSIT",
                                         "details": {"deposit_address": "Dep0sit", "min_amount": "29000000"}})

    op = await _api(handler).deposit("a1", origin_asset="nep141:sol-usdc", amount="29000000",
                                     destination_asset="nep141:near-usdc", idempotency_key="order:1:abcdefgh")
    assert (op.status, op.final, op.details["deposit_address"]) == ("PENDING_DEPOSIT", False, "Dep0sit")


async def test_paying_in_the_asset_credited_sends_no_conversion():
    def handler(request):
        assert "destination_asset" not in json.loads(request.content)
        return httpx.Response(202, json={"correlation_id": "op_2", "status": "PENDING_DEPOSIT"})

    await _api(handler).deposit("a1", origin_asset="nep141:near-usdc", amount="1",
                                destination_asset="nep141:near-usdc", idempotency_key="order:2:abcdefgh")


async def test_a_transfer_runs_under_the_grant():
    def handler(request):
        assert request.headers["X-Grant-Token"] == "ngt_secret"
        assert json.loads(request.content) == {"asset": "nep141:near-usdc", "amount": "8700000",
                                               "recipient": "cofounder.near"}
        return httpx.Response(202, json={"correlation_id": "op_3", "type": "transfer", "status": "SUCCESS"})

    op = await _api(handler).transfer("a1", "ngt_secret", asset="nep141:near-usdc", amount="8700000",
                                      recipient="cofounder.near", idempotency_key="payout:3:abcdefgh")
    assert op.final


async def test_a_refusal_carries_the_api_code_and_its_layer():
    def handler(request):
        return httpx.Response(403, json={"errors": [{
            "status": "403", "code": "policy_destination_denied", "layer": "policy",
            "title": "Destination denied", "detail": "Not in the policy's list."}]})

    with pytest.raises(AgentApiError) as refused:
        await _api(handler).withdraw("a1", "ngt_x", asset="a", amount="1", chain="base", recipient="0xabc",
                                     memo=None, idempotency_key="payout:4:abcdefgh")
    assert (refused.value.code, refused.value.layer, refused.value.status) == (
        "policy_destination_denied", "policy", 403)
    assert not refused.value.retryable


async def test_a_retryable_refusal_says_so():
    def handler(request):
        return httpx.Response(503, json={"errors": [{"code": "database_busy", "meta": {"retryable": True}}]})

    with pytest.raises(AgentApiError) as refused:
        await _api(handler).status("op_1")
    assert refused.value.retryable


async def test_an_unreachable_api_is_a_typed_error():
    def handler(request):
        raise httpx.ConnectTimeout("slow", request=request)

    with pytest.raises(AgentApiError) as refused:
        await _api(handler).status("op_1")
    assert refused.value.code == "unreachable"


async def test_status_waits_at_most_what_the_api_holds_open():
    def handler(request):
        assert request.url.params["wait_ms"] == "30000"
        return httpx.Response(200, json={"correlation_id": "intent_1", "type": "agent_create", "status": "SUCCESS",
                                         "agent_id": "a1", "details": {"revision": 1}})

    op = await _api(handler).status("intent_1", wait_ms=120_000)
    assert (op.agent_id, op.details["revision"]) == ("a1", 1)


async def test_an_owner_intent_returns_what_the_wallet_signs():
    def handler(request):
        body = json.loads(request.content)
        assert body["type"] == "grant_issue" and body["credential"] == "c0ffee"
        return httpx.Response(200, json={"correlation_id": "intent_2", "type": "grant_issue",
                                         "status": "PENDING_SIGNATURE", "expires_at": "2026-11-04T10:00:00Z",
                                         "intent": {"standard": "nep413", "payload": {"message": "m"}},
                                         "preview": {"summary": "Let Thalace act for this shop"}})

    generated = await _api(handler).generate_intent(
        "grant_issue", {"agent_id": "a1", "label": "Thalace Shops", "credential": "c0ffee",
                        "expires_at": "2027-11-01T00:00:00Z"})
    assert generated.intent["standard"] == "nep413"
    assert generated.preview["summary"].startswith("Let Thalace")


@pytest.mark.live
async def test_the_live_token_list_has_usdc_on_near():
    tokens = await AgentApi(api_key="").tokens()
    assert any(t.symbol == "USDC" and t.blockchain == "near" and t.decimals == 6 for t in tokens)
