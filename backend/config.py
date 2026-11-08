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
    frontend_base_url: str = "http://localhost:5173"

    # -- Supabase --
    supabase_base_url: str = ""
    supabase_anon_key: str = ""
    supabase_secret_key: str = ""

    # -- Database --
    # Postgres everywhere. DATABASE_URL wins; otherwise SUPABASE_DB_CONN_STR
    # (point it at Supabase's transaction pooler, port 6543); otherwise a
    # local Postgres.
    database_url: str = Field(
        "postgresql://thalace:thalace@localhost:5432/thalace",
        validation_alias=AliasChoices("DATABASE_URL", "SUPABASE_DB_CONN_STR"),
    )
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # -- LLM providers --
    dashscope_api_key: str = ""
    dashscope_base_url: str = ""
    # The OpenRouter key; .env names it OPENROUTER_API_KEY.
    openai_api_key: str = Field("", validation_alias=AliasChoices("OPENROUTER_API_KEY", "OPENAI_API_KEY"))
    # Qwen models, tried in order (comma-separated in env). `llm_models` serves
    # reasoning calls; `llm_cheap_models` the bulk extraction/condensing calls.
    llm_models: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["qwen-plus-2025-04-28", "qwen-plus-2025-07-14", "qwen-plus-latest", "qwen-max"])
    llm_cheap_models: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["qwen-plus-2025-04-28", "qwen-plus-2025-07-14", "qwen-plus-latest", "qwen-max"])
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

    @field_validator("allowed_origins", "admin_bootstrap_emails", "llm_models", "llm_cheap_models", "llm_fallback_models", mode="before")
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
