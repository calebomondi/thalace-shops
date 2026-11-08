import time
import json
import random
import re
import threading
from typing import Any, Callable, Protocol, Sequence

from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.messages import AIMessage, message_chunk_to_message
from langchain_openai import ChatOpenAI
from langchain_qwq import ChatQwen

from utils.log import current_run_id, logger  # noqa: F401 -- current_run_id is re-exported for callers of agents.llm
from config import get_settings


class _ChatQwen(ChatQwen):
    """ChatQwen whose `_support_tool_choice` does not clobber enable_thinking.

    The base implementation sets `self.enable_thinking = False` for any model
    without "thinking" in its name — which silently breaks chat completions on
    models that only accept enable_thinking=True (e.g. qwen3.7-max), because
    with_structured_output goes through tool-choice checks first."""

    def _support_tool_choice(self) -> bool:
        return True

    def with_structured_output(self, schema, **kwargs):
        saved = self.enable_thinking
        try:
            # Thinking mode rejects tool_choice="required" (function_calling),
            # so fall back to json_mode for thinking models.
            if self.enable_thinking and "method" not in kwargs:
                kwargs["method"] = "json_mode"
            return super().with_structured_output(schema, **kwargs)
        finally:
            # Base impl force-disables thinking on non-"thinking"-named models.
            self.enable_thinking = saved


cfg = get_settings()

# Model ladders come from settings (LLM_MODELS / LLM_CHEAP_MODELS), so a model
# swap -- e.g. when one runs out of quota -- is an env change, not a code change.
QWEN_MODELS: list[str] = [m for m in cfg.llm_models if m.strip()]

# Cheap text-only tier, for bulk mechanical work that doesn't need a flagship
# reasoning model: distilling scraped documents, condensing the offer's own
# material, and the other extraction/paraphrase calls. Keeping these off the
# flagship matters for more than cost — the flagship is a large omni model, and
# a run that routes its high-volume extraction work there is what pushes the
# account into tokens-per-minute throttling in the first place.
CHEAP_QWEN_MODELS: list[str] = [m for m in cfg.llm_cheap_models if m.strip()]


FALLBACK_MODELS: list[str] = [m for m in cfg.llm_fallback_models if m.strip()]

# Output ceiling for every call. Above the largest real structured output
# (~8k tokens), so it only stops a runaway: one page summary on a model that
# forces thinking once wrote 16k tokens over 169s.
MAX_OUTPUT_TOKENS = 12_000
# Reasoning allowed when a call asked for none but the model only runs with
# thinking on. Enough to plan an answer, not to write an essay first.
FORCED_THINKING_BUDGET = 1_024


def _with_fallback(primary: list[tuple[str, list[str]]]) -> list[tuple[str, list[str]]]:
    """Append the second provider when it is configured, so an outage or an
    exhausted quota on Qwen degrades to another model instead of failing runs."""
    return primary + ([("openrouter", FALLBACK_MODELS)] if cfg.openai_api_key and FALLBACK_MODELS else [])


def default_providers() -> list[tuple[str, list[str]]]:
    return _with_fallback([("qwen", QWEN_MODELS)])


def cheap_providers() -> list[tuple[str, list[str]]]:
    """Provider ladder for bulk extraction work. Ordered cheapest-first."""
    return _with_fallback([("qwen", CHEAP_QWEN_MODELS)])


# -- Usage accounting ---------------------------------------------------------
# Calls are billed to utils.log.current_run_id, which the backend sets for the
# span of a run segment; ContextThreadPoolExecutor carries it into workers.

# Receives one record per LLM call attempt (failed attempts cost tokens too).
# agents/ stays free of the database: the backend registers the sink.
_usage_sink: Callable[[dict], None] | None = None


def set_usage_sink(sink: Callable[[dict], None] | None) -> None:
    global _usage_sink
    _usage_sink = sink


def _report_usage(log_label: str, provider: str, model: str, handler: UsageMetadataCallbackHandler,
                  seconds: float, ok: bool) -> None:
    if _usage_sink is None:
        return
    usage = next(iter(handler.usage_metadata.values()), {}) if handler.usage_metadata else {}
    try:
        _usage_sink({
            "run_id": current_run_id.get(),
            "log_label": log_label[:120],
            "provider": provider,
            "model": model,
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "seconds": round(seconds, 3),
            "ok": ok,
        })
    except Exception:  # noqa: BLE001 -- accounting must never break an LLM call
        logger.exception("LLM usage sink failed")

# (provider, model) pairs discovered to be dead (quota exhausted / auth /
# model unavailable) for the lifetime of this process. Once a model trips one
# of those plumbing errors we stop wasting calls on it and fall through to the
# next model immediately.
_DOWN_MODELS: set[tuple[str, str]] = set()

# (provider, model) pairs that rejected an enabled-thinking request (e.g. the
# omni-flash family returns 400 "thinking_budget must be a positive integer" for
# ANY enable_thinking=True). Once learned, all calls to that model run with
# thinking disabled so we stop paying a 400 round-trip per call.
_NO_THINKING_MODELS: set[tuple[str, str]] = set()

# Inverse learning: models that REJECT enable_thinking=False (some only
# accept thinking=True). Once learned, retry/run them with thinking enabled
# instead of paying a 400 round-trip per call.
_FORCE_THINKING_MODELS: set[tuple[str, str]] = {("qwen", "qwen3.8-2.4t-a95b")}

# Per-log_label wall-clock accounting, so a run can be attributed rather than
# guessed at. `log_label` is the only stable identity a call site has, and it is
# already threaded through every call. The first version of this run's cost
# model was inferred by dividing total runtime by call count and it was wrong by
# ~40%, because a large share of the time is Exa search/scrape, which never
# passes through here at all -- these numbers are the LLM share only.
_CALL_TIMING: dict[str, dict[str, float]] = {}
_CALL_TIMING_LOCK = threading.Lock()


def _record_call_timing(log_label: str, seconds: float, model: str) -> None:
    # The lock is load-bearing now that distilling a page fan-out runs these
    # calls on a thread pool: setdefault + `+=` is a read-modify-write, so
    # concurrent calls would otherwise lose counts and skew exactly the numbers
    # this exists to produce.
    with _CALL_TIMING_LOCK:
        entry = _CALL_TIMING.setdefault(
            log_label, {"calls": 0.0, "seconds": 0.0, "model": 0.0}
        )
        entry["calls"] += 1
        entry["seconds"] += seconds
        # Keep the last model seen, not a sum: a float field is a hack, but the
        # alternative is a second dict and this is only ever read by a debug
        # helper.
        entry["model"] = model


def llm_timing_report() -> str:
    """Human-readable LLM wall-clock breakdown, slowest label first.

    Read-only, for diagnosing where a run's time goes. Not wired into the UI."""
    with _CALL_TIMING_LOCK:
        snapshot = {k: dict(v) for k, v in _CALL_TIMING.items()}
    if not snapshot:
        return "no LLM calls recorded"
    rows = sorted(snapshot.items(), key=lambda kv: -kv[1]["seconds"])
    total = sum(e["seconds"] for _, e in rows)
    width = max(len(k) for k, _ in rows)
    lines = [
        f"LLM wall clock: {total:.1f}s across {int(sum(e['calls'] for _, e in rows))} calls",
    ]
    for label, e in rows:
        pct = (e["seconds"] / total * 100) if total else 0.0
        lines.append(
            f"  {label:<{width}}  {e['seconds']:7.1f}s  "
            f"({int(e['calls'])}x, avg {e['seconds'] / e['calls']:5.2f}s, {pct:4.1f}%)"
        )
    return "\n".join(lines)


class LlmProvidersExhaustedError(RuntimeError):
    """Every (provider, model) in the ladder failed.

    Carries the failing step plus the last underlying provider error, so callers
    can explain the failure in plain language instead of shipping a provider
    traceback into the UI.
    """

    def __init__(self, log_label: str, last_err: BaseException | None = None):
        super().__init__(f"All LLM providers failed for {log_label}")
        self.log_label = log_label
        self.last_err = last_err


# Provider errors that retire a model for the process: the key is bad, the model
# is not available to this account, or access is denied. None of these clear
# with time, so retrying is pointless.
_RETIRED_MODEL_MARKERS = (
    "invalid_api_key",
    "unauthorized",
    "permission_denied",
    "permission denied",
    "forbidden",
    "access denied",
    "error code: 401",
    "error code: 403",
    # The model id is wrong or retired: no wait or retry will make it exist.
    "model_not_found",
    "model not exist",
    "model does not exist",
)

# Throttling. Alibaba phrases its tokens-per-minute throttle as "Allocated quota
# exceeded", which shares the word "quota" with a genuine billing wall — so the
# throttle is matched on its own wording rather than on a bare "quota" substring.
# Retiring a model here is what wedged the ladder before, and the throttle always
# arrives alongside a 429, so matching the code first is enough.
_THROTTLE_MARKERS = (
    "429",
    "rate_limit",
    "rate limit",
    "too many requests",
    "throttl",
    "allocated quota exceeded",
)

# A genuine "out of credit" complaint. Deliberately credit-shaped: none of these
# phrasings appear in a throttle, so a body that matches one really is billing.
_BILLING_WALL_MARKERS = (
    "insufficient_user_quota",
    "insufficient_quota",
    "exceeded your current quota",
    "quota exhausted",
    "free quota exhausted",
    # DashScope's free tier: "The free quota has been exhausted."
    "quota has been exhausted",
    "out of credit",
    "add funds",
    "arrearage",
    "billing",
)

# The prompt outgrew the model's context window. Not retriable — resending an
# identical oversized prompt just fails identically — and it is the single most
# actionable provider error we can get, because it means our own context
# assembly let the run grow past what the model accepts.
_CONTEXT_OVERFLOW_MARKERS = (
    "range of input length",
    "input length should be",
    "context length",
    "context_length_exceeded",
    "maximum context",
    "too many tokens",
    "reduce the length of the messages",
    "string too long",
    "input is too long",
)

_MAX_RETRY_DELAY_S = 60.0

# At most settings.llm_max_concurrency calls in flight per provider, process-
# wide. Every run fans out (research workers, hunt tasks, profiles), and many
# runs at once exceed the provider's concurrency/request-rate limits; past the
# cap calls queue here instead of bouncing off 429s and backing off.
_PROVIDER_SLOTS: dict[str, threading.BoundedSemaphore] = {}
_SLOTS_LOCK = threading.Lock()


def _provider_slot(provider: str) -> threading.BoundedSemaphore:
    with _SLOTS_LOCK:
        if provider not in _PROVIDER_SLOTS:
            _PROVIDER_SLOTS[provider] = threading.BoundedSemaphore(cfg.llm_max_concurrency)
        return _PROVIDER_SLOTS[provider]

# --- Throttle circuit breaker -------------------------------------------
# A single transient 429 is worth waiting out, but a sustained one is not: with
# both models throttled, each call would otherwise block for the full backoff
# budget (~2min) and a 20-call run would spend half an hour failing the same
# way. Once consecutive calls have exhausted their throttle budget without a
# single success, trip the breaker and fail fast until a cooldown elapses, so
# the run surfaces a real error instead of crawling.
_THROTTLE_TRIP_THRESHOLD = 2
_THROTTLE_COOLDOWN_S = 120.0
_throttle_state = {"consecutive": 0, "open_until": 0.0}


def _throttle_circuit_state() -> str:
    """Report the breaker so callers can log why a call failed instantly."""
    remaining = _throttle_state["open_until"] - time.monotonic()
    if remaining > 0:
        return f"throttled upstream, cooling down {remaining:.0f}s"
    return "ok"


def _note_throttle_outcome(succeeded: bool) -> None:
    if succeeded:
        _throttle_state["consecutive"] = 0
        _throttle_state["open_until"] = 0.0
        return
    _throttle_state["consecutive"] += 1
    if _throttle_state["consecutive"] >= _THROTTLE_TRIP_THRESHOLD:
        _throttle_state["open_until"] = time.monotonic() + _THROTTLE_COOLDOWN_S
        logger.warning(
            "Throttle circuit opened after %d consecutive throttled calls; "
            "failing fast for %.0fs",
            _throttle_state["consecutive"], _THROTTLE_COOLDOWN_S,
        )


def classify_llm_error(err: BaseException) -> str:
    """Bucket a provider error into the cases the retry ladder reacts to.

    Public because the websocket endpoint reports the same failure to the user;
    sharing one classifier is the only way the retry decision and the message
    the user reads can be guaranteed to agree.

    Ordering is load-bearing. Alibaba's throttle is a 429 whose body reads
    "Allocated quota exceeded", so a naive ``"quota" in str(err)`` test retires a
    perfectly healthy model on a transient rate limit — and with a one-model
    ladder that wedges every later call in the process until it is restarted. A
    429 is therefore always treated as a rate limit here, never as a retirement.
    """
    text = str(err).lower()
    if any(marker in text for marker in _CONTEXT_OVERFLOW_MARKERS):
        # Checked first: some providers report an oversized request with a 4xx
        # body that also mentions quota accounting.
        return "context_overflow"
    if any(marker in text for marker in _THROTTLE_MARKERS):
        return "rate_limit"
    # Billing is checked before retirement because Alibaba returns 403 for
    # "out of credit" as well as for "not allowed to use this model"; only the
    # body tells them apart, and the user needs to be told which one it is.
    if any(marker in text for marker in _BILLING_WALL_MARKERS):
        return "billing"
    if any(marker in text for marker in _RETIRED_MODEL_MARKERS):
        return "auth"
    return "other"


def _provider_retry_after_seconds(err: BaseException) -> float | None:
    """Read the wait the provider actually asked for, from the response header
    when the SDK surfaced one and from the error body otherwise."""
    headers = getattr(getattr(err, "response", None), "headers", None)
    if headers:
        for key in ("retry-after", "Retry-After", "x-ratelimit-reset-after"):
            try:
                raw = headers.get(key)
            except Exception:
                raw = None
            if raw is None:
                continue
            try:
                return float(str(raw).strip().rstrip("s"))
            except (TypeError, ValueError):
                continue

    text = str(err)
    match = re.search(
        r"try again in ([\d.]+)\s*"
        r"(milliseconds|millisecond|ms|minutes|minute|mins|min|seconds|second|secs|sec|s|m)?",
        text,
        re.IGNORECASE,
    )
    if match:
        amount = float(match.group(1))
        unit = (match.group(2) or "s").lower()
        if unit.startswith("ms") or unit.startswith("milli"):
            return amount / 1000.0
        if unit.startswith("m"):
            return amount * 60.0
        return amount

    match = re.search(r"retry[-_ ]?after[\"'\s:=]+([\d.]+)", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def _retry_delay_seconds(err: BaseException, attempt: int) -> float:
    """How long to wait before retrying a throttled call.

    Prefers the provider's own hint, because backoff guessed from a local
    counter routinely under-waits a tokens-per-minute window and burns the whole
    budget re-colliding with the same limit. Jittered either way: a run fires
    many calls in bursts, and unjittered backoff just re-synchronises them.
    """
    hinted = _provider_retry_after_seconds(err)
    if hinted is None:
        hinted = 2.0 * (2 ** (attempt - 1))
    return min(max(hinted, 0.0), _MAX_RETRY_DELAY_S) * (0.75 + random.random() * 0.5)


def _json_from_text(text: str):
    """Pull the first valid JSON value out of model text (handles prose,
    markdown fences, trailing commentary)."""
    if not text:
        return None
    decoder = json.JSONDecoder()
    for key in ("{", "["):
        idx = text.find(key)
        while idx != -1:
            try:
                obj, _ = decoder.raw_decode(text[idx:])
                return obj
            except json.JSONDecodeError:
                idx = text.find(key, idx + 1)
    return None


def _try_repair_structured(llm, messages: Sequence[Any], schema: Any, config: dict | None = None):
    """When with_structured_output's re-built schema rejects a response (weaker
    models double-serialize nested list/dict fields as JSON strings), re-ask the
    plain model for a single JSON object and validate against the REAL schema —
    whose validators (e.g. _coerce_json) repair the double-serialization."""
    try:
        from langchain_core.messages import HumanMessage
        schema_text = json.dumps(schema.model_json_schema(), indent=2)
        repair_messages = list(messages) + [HumanMessage(content=(
            "Your previous response failed schema validation. Reply ONLY with a single valid JSON "
            "object matching the schema exactly: every list field must be a real JSON array, every "
            "object field a real JSON object. No prose, no markdown fences, no trailing text.\n\n"
            f"SCHEMA:\n{schema_text}"
        ))]
        raw = llm.invoke(repair_messages, config=config)
        content = raw if isinstance(raw, str) else getattr(raw, "content", str(raw))
        obj = _json_from_text(content)
        if obj is None:
            return None
        return schema.model_validate(obj)
    except Exception:
        return None


def _llm(
    provider: str = "qwen",
    model: str | None = None,
    thinking: bool = False,
    thinking_budget: int | None = None,
) -> ChatQwen | ChatOpenAI:
    if provider == "qwen":
        m = model or QWEN_MODELS[0]
        if (provider, m) in _NO_THINKING_MODELS:
            # Learned to reject enable_thinking — run it non-thinking.
            thinking = False
            thinking_budget = None
        if (provider, m) in _FORCE_THINKING_MODELS and not thinking:
            # Learned to require thinking, on a call that wanted none: allow
            # only a short budget so a quick job stays quick.
            thinking = True
            thinking_budget = thinking_budget or FORCED_THINKING_BUDGET
        logger.info("Using Qwen (%s, thinking=%s, budget=%s)", m, thinking, thinking_budget)
        kwargs = {"enable_thinking": thinking}
        if thinking_budget is not None:
            # Only send an explicit budget when we have one. Passing
            # thinking_budget=None alongside enable_thinking=True makes the
            # omni-flash family reject the request outright, which the
            # _NO_THINKING_MODELS learning would otherwise have to undo with a
            # wasted 400 round-trip on every fresh process.
            kwargs["thinking_budget"] = thinking_budget
        return _ChatQwen(
            model=m,
            api_key=cfg.dashscope_api_key,
            base_url=cfg.dashscope_base_url,
            timeout=cfg.llm_call_timeout_s,
            # Retries are this module's ladder's job (it knows a throttle from a
            # dead model); SDK-level retries would just multiply the wait.
            max_retries=0,
            max_tokens=MAX_OUTPUT_TOKENS,
            # Streamed calls report token usage only when asked to.
            stream_usage=True,
            **kwargs,
        )
    if provider == "openrouter":
        m = model or FALLBACK_MODELS[0]
        logger.info("Using OpenRouter fallback (%s)", m)
        return ChatOpenAI(
            model=m,
            api_key=cfg.openai_api_key,
            base_url=cfg.openrouter_base_url,
            timeout=cfg.llm_call_timeout_s,
            max_retries=0,
            max_tokens=MAX_OUTPUT_TOKENS,
            stream_usage=True,
        )
    raise ValueError(f"Unknown LLM provider {provider!r}")


def invoke_structured_with_fallback(
    messages: Sequence[Any],
    schema: Any | None = None,
    providers: list[tuple[str, list[str]]] | None = None,
    log_label: str = "LLM call",
    max_retries: int = 2,
    thinking: bool = False,
    thinking_budget: int | None = None,
    rate_limit_retries: int = 5,
):
    """The model's answer: a `schema` instance when one is given, else its text.
    See _invoke_ladder for the retry and fallback behaviour."""
    result = _invoke_ladder(messages, schema, None, providers, log_label, max_retries,
                            thinking, thinking_budget, rate_limit_retries)
    if schema is None and hasattr(result, "content"):
        return result.content
    return result


class TokenSink(Protocol):
    """Receives an answer as it is written. `reset` means discard what came so
    far: a retry or the next model in the ladder is starting over."""

    def token(self, text: str) -> None: ...

    def reset(self) -> None: ...


def invoke_with_tools(
    messages: Sequence[Any],
    tools: Sequence[Any],
    providers: list[tuple[str, list[str]]] | None = None,
    log_label: str = "LLM call",
    thinking: bool = False,
    rate_limit_retries: int = 5,
    sink: TokenSink | None = None,
) -> AIMessage:
    """One agent step: the model's full message, which may carry tool calls.
    With `sink`, the text is streamed into it as it is generated; the full
    message is still returned. Same ladder as structured calls; tool-call
    arguments are validated by the tool, not here."""
    return _invoke_ladder(messages, None, tools, providers, log_label, 2,
                          thinking, None, rate_limit_retries, sink)


def _stream(runnable, messages: Sequence[Any], config: dict, sink: TokenSink) -> AIMessage:
    merged = None
    for chunk in runnable.stream(messages, config=config):
        if chunk.text:
            sink.token(chunk.text)
        merged = chunk if merged is None else merged + chunk
    if merged is None:
        raise ValueError("The model streamed nothing")
    return message_chunk_to_message(merged)


def _invoke_ladder(
    messages: Sequence[Any],
    schema: Any | None,
    tools: Sequence[Any] | None,
    providers: list[tuple[str, list[str]]] | None,
    log_label: str,
    max_retries: int,
    thinking: bool,
    thinking_budget: int | None,
    rate_limit_retries: int,
    sink: TokenSink | None = None,
):
    """
    Invoke an LLM across a prioritized list of (provider, [models]) pairs,
    falling back on failure. Retries on 429/rate-limit errors with backoff.
    With `tools`, the model may call them; with `schema`, structured output;
    otherwise a plain invoke.

    `thinking` defaults to False, so a new call site is fast by default and has
    to argue for the latency. Measured on qwen3.6-27b with an identical prompt,
    median of 3: thinking=False 2.37s, thinking=True 9.33s -- 3.9x. Pass
    thinking=True only where the call actually deliberates: the interview
    answers, the ICP reasoning, and the final section writer. Extraction,
    classification, persona generation and summarisation of already-distilled
    notes do not.

    `thinking_budget` is not a substitute for turning thinking off. Measured at
    1024 tokens it came out at 10.49s against 9.33s unbounded -- no saving,
    because the cap only binds on the reasoning tail and this workload's
    thinking is short. It also carries a real hazard: a model that rejects an
    explicit budget is learned into _NO_THINKING_MODELS and then runs
    non-thinking for the rest of the process, which would silently disable
    deliberation on the very calls that asked for it.

    `rate_limit_retries` is deliberately larger than `max_retries`. A throttle
    clears with time; a bad key or a retired model never will. Conflating the two
    is what used to kill runs: two 1.5s attempts could not outlast a
    tokens-per-minute window, and the resulting error then marked the only model
    in the ladder permanently down.
    """
    if providers is None:
        providers = default_providers()

    # Sustained upstream throttling: fail fast instead of spending the full
    # backoff budget on every remaining call in the run.
    if _throttle_state["open_until"] > time.monotonic():
        logger.warning(
            "%s skipped (%s)", log_label, _throttle_circuit_state(),
        )
        raise LlmProvidersExhaustedError(log_label, None)

    last_err = None
    attempts_made = 0
    for provider, models in providers:
        for model in models:
            if (provider, model) in _DOWN_MODELS:
                logger.info("%s skipping %s/%s (marked down this process)", log_label, provider, model)
                continue

            attempt = 0
            throttles = 0
            # Hard ceiling so no path below can spin forever.
            budget = max(max_retries, rate_limit_retries) + 3

            while attempt < budget:
                attempt += 1
                if sink is not None and attempts_made:
                    # A retry or the next model starts the answer over.
                    sink.reset()
                attempts_made += 1
                llm = None
                usage = UsageMetadataCallbackHandler()
                started = time.perf_counter()
                try:
                    llm = _llm(provider, model=model, thinking=thinking, thinking_budget=thinking_budget)
                    config = {"callbacks": [usage]}
                    queued = time.perf_counter()
                    with _provider_slot(provider):
                        waited = time.perf_counter() - queued
                        if waited > 1:
                            logger.info("%s waited %.1fs for a %s slot", log_label, waited, provider)
                        started = time.perf_counter()  # time the call, not the queue
                        if schema is not None:
                            result = llm.with_structured_output(schema).invoke(messages, config=config)
                        else:
                            runnable = llm.bind_tools(list(tools)) if tools else llm
                            if sink is not None:
                                result = _stream(runnable, messages, config, sink)
                            else:
                                result = runnable.invoke(messages, config=config)
                    _record_call_timing(
                        log_label, time.perf_counter() - started, model
                    )
                    if result is None:
                        raise ValueError(
                            f"{log_label} returned None with {provider}/{model} (unexpected structured output)"
                        )
                    _report_usage(log_label, provider, model, usage, time.perf_counter() - started, ok=True)
                    logger.info("%s succeeded with %s/%s", log_label, provider, model)
                    _DOWN_MODELS.discard((provider, model))
                    _note_throttle_outcome(True)
                    return result
                except Exception as e:
                    _report_usage(log_label, provider, model, usage, time.perf_counter() - started, ok=False)
                    last_err = e
                    err_str = str(e).lower()
                    kind = classify_llm_error(e)
                    is_thinking_reject = (
                        thinking
                        and ("thinking_budget" in err_str or "enable_thinking" in err_str)
                        and ("invalid" in err_str or "positive integer" in err_str)
                    )
                    logger.warning(
                        "%s failed with %s/%s (%s, attempt %d/%d): %s",
                        log_label, provider, model, kind, attempt, budget, e,
                    )
                    if is_thinking_reject and (provider, model) not in _NO_THINKING_MODELS:
                        # This model can't do thinking. Learn it and retry the
                        # same model non-thinking immediately (bypass the ladder).
                        _NO_THINKING_MODELS.add((provider, model))
                        logger.info(
                            "%s: %s/%s rejected thinking; retrying same model with thinking off",
                            log_label, provider, model,
                        )
                        continue
                    is_thinking_required = (
                        not thinking
                        and "enable_thinking" in err_str
                        and ("restricted to true" in err_str or "restricted_to_true" in err_str)
                    )
                    if is_thinking_required and (provider, model) not in _FORCE_THINKING_MODELS:
                        # This model only accepts thinking ON. Learn it and retry
                        # the same model with thinking enabled immediately.
                        _FORCE_THINKING_MODELS.add((provider, model))
                        logger.info(
                            "%s: %s/%s requires thinking; retrying same model with thinking on",
                            log_label, provider, model,
                        )
                        continue
                    if kind == "auth":
                        # Unusable for this key no matter how long we wait.
                        _DOWN_MODELS.add((provider, model))
                        break
                    if kind == "context_overflow":
                        # Every remaining model in the ladder has the same or a
                        # smaller window, so falling through buys nothing and
                        # resending the identical oversized prompt cannot help.
                        # Fail fast with a cause the caller can explain.
                        _note_throttle_outcome(False)
                        logger.error(
                            "%s: prompt exceeds %s's context window. Trim the "
                            "accumulated interview context.",
                            log_label, model,
                        )
                        break
                    if kind == "rate_limit":
                        throttles += 1
                        if throttles <= rate_limit_retries:
                            delay = _retry_delay_seconds(e, throttles)
                            logger.info(
                                "Rate limited on %s/%s; retry %d/%d in %.1fs",
                                provider, model, throttles, rate_limit_retries, delay,
                            )
                            time.sleep(delay)
                            continue
                        # Budget spent. Fall through to the next model rather than
                        # dying here, and deliberately do NOT retire this one: a
                        # throttle says nothing about whether the model works, so
                        # retiring it would poison the ladder for good.
                        logger.info(
                            "%s: %s/%s still throttled after %d waits; falling through",
                            log_label, provider, model, throttles,
                        )
                        _note_throttle_outcome(False)
                        break
                    if kind == "billing":
                        _DOWN_MODELS.add((provider, model))
                        time.sleep(0.25)
                        break
                    # Not a plumbing failure: the model answered, it just didn't
                    # match the schema. Try one JSON re-parse repair.
                    if schema is not None and llm is not None and attempt < max_retries:
                        repair_usage = UsageMetadataCallbackHandler()
                        repair_started = time.perf_counter()
                        repaired = _try_repair_structured(llm, messages, schema, config={"callbacks": [repair_usage]})
                        _report_usage(f"{log_label}:repair", provider, model, repair_usage,
                                      time.perf_counter() - repair_started, ok=repaired is not None)
                        if repaired is not None:
                            logger.info(
                                "%s repaired via JSON re-parse with %s/%s (attempt %d)",
                                log_label, provider, model, attempt,
                            )
                            _DOWN_MODELS.discard((provider, model))
                            return repaired
                    break

    raise LlmProvidersExhaustedError(log_label, last_err) from last_err