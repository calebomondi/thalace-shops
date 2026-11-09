"""The single source of runtime configuration for every layer.

It lives at backend/ root, beside app/, agents/ and utils/, so every layer
imports it as `config` without importing the API. It reads backend/.env.
Nothing else in the codebase reads os.environ or .env: add a field here instead.

Field names are lowercase; pydantic-settings matches them to env vars
case-insensitively (`exa_api_key` <- EXA_API_KEY).
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_ROOT = Path(__file__).resolve().parent
# Qwen (DashScope) models tried in order when NEAR AI Cloud can't answer.
_QWEN_MODELS = ("qwen-plus-2025-04-28", "qwen-plus-2025-07-14", "qwen-plus-latest", "qwen-max")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- App --
    project_name: str = "Thalace Shops"
    api_v1_str: str = "/api/v1"
    environment: str = "development"
    log_level: str = "INFO"
    # "text" for a terminal, "json" (one object per line) for a log shipper.
    log_format: Literal["text", "json"] = "text"
    # Empty = same-origin only. Comma-separated or a JSON array, e.g.
    # ALLOWED_ORIGINS=http://localhost:5173,https://app.example.com
    allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    admin_bootstrap_emails: Annotated[list[str], NoDecode] = Field(default_factory=list)
    frontend_base_url: str = "http://localhost:5180"

    # -- Supabase --
    supabase_base_url: str = ""
    supabase_anon_key: str = ""
    supabase_secret_key: str = ""

    # -- Database --
    # Postgres everywhere. Local dev: the docker-compose.yml service on 5433
    # (DATABASE_URL in .env). Production: Supabase's transaction pooler
    # (port 6543), set as DATABASE_URL on Render. Only DATABASE_URL is read,
    # never SUPABASE_DB_CONN_STR, so local dev can't reach production by
    # falling back to it.
    database_url: str = "postgresql://thalace:thalace@localhost:5433/thalace"
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # -- LLM providers --
    dashscope_api_key: str = ""
    dashscope_base_url: str = ""
    # The OpenRouter key; .env names it OPENROUTER_API_KEY.
    openai_api_key: str = Field("", validation_alias=AliasChoices("OPENROUTER_API_KEY", "OPENAI_API_KEY"))
    # Qwen models, tried in order (comma-separated in env). `llm_models` serves
    # reasoning calls; `llm_cheap_models` the bulk extraction/condensing calls.
    llm_models: Annotated[list[str], NoDecode] = Field(default_factory=lambda: list(_QWEN_MODELS))
    llm_cheap_models: Annotated[list[str], NoDecode] = Field(default_factory=lambda: list(_QWEN_MODELS))
    # Second provider (OpenRouter), tried in order when every Qwen model fails.
    llm_fallback_models: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["openai/gpt-4o-mini"])
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Per-call cap and max LLM calls in flight per provider (process-wide).
    llm_call_timeout_s: float = 240.0
    llm_max_concurrency: int = 24

    # -- Web data --
    exa_api_key: str = ""
    exa_timeout_s: float = 60.0
    tavily_api_key: str = ""
    firecrawl_api_key: str = ""
    firecrawl_timeout_s: float = 60.0
    brightdata_api_key: str = ""
    composio_api_key: str = ""
    # Composio auth config per toolkit, as a JSON object.
    composio_auth_configs: dict[str, str] = Field(default_factory=dict)

    # -- Email --
    resend_api_key: str = ""
    resend_timeout_s: float = 15.0

    # -- NEAR --
    # Intents (1Click) partner JWT, NEAR AI Cloud inference key, and the
    # mainnet account that receives funds. Mainnet only: Intents has no testnet.
    near_intents_agent_api_key: str = ""
    near_ai_cloud_api_key: str = ""
    near_mainnet_wallet_address: str = ""
    # Receives the platform fee on every sale; listed in each shop's signed
    # policy at go-live, so it must exist on NEAR first.
    near_mainnet_platform_treasury_wallet_address: str = ""
    # Seed values for platform_settings; the admin changes the fee from the
    # dashboard afterwards, never above the maximum owners agreed to.
    platform_fee_bps: int = 200
    platform_fee_max_bps: int = 1000
    near_intents_agent_api_url: str = "https://api.demo.agentsonintents.com"
    near_intents_timeout_s: float = 30.0
    # Encrypts each shop's grant token at rest (a Fernet key). Never change it:
    # live shops couldn't pay out until their owners signed again.
    shop_grant_key: str = ""
    # How long the backend's grant on a shop's wallet lasts (the API allows 365).
    shop_grant_days: int = 180
    near_ai_cloud_base_url: str = "https://cloud-api.near.ai/v1"
    # NEAR AI Cloud models for agent steps, tried in order before Qwen. Each
    # was checked to call tools (2026-11-09); qwen/qwen3.7-max answered 502.
    near_ai_models: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["z-ai/glm-5.3", "Qwen/Qwen3.8-27B", "deepseek/deepseek-v4.1-flash"])

    # -- Shops --
    # Native USDC on NEAR: what a sale is credited as unless the owner picks
    # another asset (asset ids from the Agent API's GET /v1/tokens).
    default_settlement_asset: str = "nep141:17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1"
    default_daily_budget_usd: int = 20
    max_shops_per_owner: int = 10
    max_offers_per_shop: int = 50
    max_payees_per_shop: int = 10
    # The highest daily cap an owner may sign: keeps a mistyped cap from
    # letting a shop move far more than a small business would.
    max_daily_budget_usd: int = 1000
    # -- Invoices and payments --
    # Dollar stablecoins a buyer may pay with (asset ids from GET /v1/tokens);
    # each is credited to the shop as its settlement asset.
    pay_assets: Annotated[list[str], NoDecode] = Field(default_factory=lambda: [
        "nep141:17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1",  # USDC, NEAR
        "nep141:base-0x833589fcd6edb6e08f4c7c32d4f71b54bda02913.omft.near",  # USDC, Base
        "nep141:arb-0xaf88d065e77c8cc2239327c5edb3a432268e5831.omft.near",  # USDC, Arbitrum
        "nep141:sol-5ce3bf3a31af18be40ba30f721101b4341690186.omft.near",  # USDC, Solana
        "nep141:eth-0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48.omft.near",  # USDC, Ethereum
        "nep141:usdt.tether-token.near",  # USDT, NEAR
        "nep141:tron-d28a265909efecdcee7c5028585214ea0b96f015.omft.near",  # USDT, Tron
    ])
    # How long the Agent API's token list is reused before reading it again.
    tokens_cache_s: float = 300.0
    max_invoice_quantity: int = 100
    invoices_per_ip_per_hour: int = 20
    # The header the proxy in front of the API puts the visitor's IP in
    # (Render, Vite and Cloudflare all set x-forwarded-for; first entry).
    client_ip_header: str = "x-forwarded-for"
    # Salt for the stored IP hash: rate limiting without keeping raw IPs.
    ip_hash_salt: str = "thalace-shops"
    # The background loop that watches payments and sends payouts.
    watcher_enabled: bool = True
    watcher_interval_s: float = 10.0
    watcher_batch: int = 50
    # An invoice page asks the Agent API itself when the watcher hasn't for this long.
    invoice_recheck_s: float = 5.0

    # -- Shop agent --
    # Per owner turn: tool calls before the agent must answer, the
    # conversation re-sent each step, and the turn's wall clock.
    agent_max_tool_calls_per_turn: int = 12
    agent_history_token_budget: int = 16_000
    agent_turn_timeout_s: float = 180.0
    max_agent_turns_per_day: int = 100
    # Characters of one web page the agent reads.
    website_read_max_chars: int = 30_000
    # How long a verified Supabase access token is trusted before asking again.
    auth_cache_ttl_s: float = 60.0
    supabase_timeout_s: float = 10.0

    # -- KRA (Kenya Revenue Authority) API credentials, one pair per product --
    kra_taxpayer_obligations_cons_key: str = ""
    kra_taxpayer_obligations_cons_secret: str = ""
    kra_pin_checker_cons_key: str = ""
    kra_pin_checker_cons_secret: str = ""
    kra_tax_comp_cert_checker_cons_key: str = ""
    kra_tax_comp_cert_checker_cons_secret: str = ""

    # -- Observability (all opt-in: empty means off) --
    sentry_dsn: str = ""
    langsmith_api_key: str = ""
    langsmith_project: str = "thalace-shops"

    @computed_field
    @property
    def sqlalchemy_database_url(self) -> str:
        """`database_url` with the async psycopg driver SQLAlchemy needs."""
        return "postgresql+psycopg://" + self.database_url.split("://", 1)[1]

    @field_validator("database_url")
    @classmethod
    def _require_postgres(cls, value: str) -> str:
        """Accept any Postgres URI form and store the plain libpq one."""
        scheme, sep, rest = value.strip().partition("://")
        if not sep or scheme.split("+", 1)[0] not in ("postgresql", "postgres"):
            raise ValueError(f"DATABASE_URL must be a Postgres URI (got scheme {scheme!r})")
        return f"postgresql://{rest}"

    @field_validator("llm_models", "llm_cheap_models")
    @classmethod
    def _require_models(cls, value: list[str]) -> list[str]:
        # Fail at startup, not on the first LLM call.
        if not value:
            raise ValueError("at least one model is required")
        return value

    @field_validator("allowed_origins", "admin_bootstrap_emails", "llm_models", "llm_cheap_models",
                     "llm_fallback_models", "near_ai_models", "pay_assets", mode="before")
    @classmethod
    def _parse_str_list(cls, value):
        """Accept a comma-separated string or a JSON array from the env."""
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value:
            return []
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [str(parsed).strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
