# Thalace Shops

A founder opens one or more **virtual shops**. Each shop has its own ReAct agent, its own wallet on NEAR Intents (Agent API) and rules the owner signs and the agent can't change. People buy on the shop's page; other agents buy through MCP and a public directory; shops negotiate with each other and pool demand into group orders. Every purchase is an invoice on a public ledger.

Built for **NEAR HACKATHON**, track `business`. Development ends **2026-11-14 23:59 UTC**. The plan, decisions and the facts the design depends on are in `docs/build-plan.md`; read it before starting work. The hackathon rules are in `HACKATHON.md`.

- **Backend**: FastAPI in `backend/app/`. It owns persistence, auth, running agents and every call that moves money.
- **Agents**: the shop agent (ReAct) in `backend/agents/`. Agents are pure: they reach the database only through a store protocol the backend implements.
- **External APIs**: adapters in `backend/data_sources/` (NEAR Intents Agent API, KRA, search, scraping).
- **Frontend**: React 19 + Vite in `frontend/`: founder console, shop pages, invoice pages.
- **Identity**: Supabase Auth (email magic link + Google). **Database**: Postgres: Docker locally, Supabase in production.

Dependency direction is **frontend → backend app → agents → data_sources / utils**. The frontend talks only to the backend API. Nothing under `agents/` imports `app/`. Nothing under `data_sources/` imports `agents/`.

---

## Commands

```bash
# Backend (from backend/)
cp .env.example .env            # first time only, then fill in keys
uv sync
scripts/dev.sh                  # starts Docker Postgres (port 5433), then uvicorn --reload on :8100
uv run pytest                   # tests
uv run alembic upgrade head     # apply migrations
uv run alembic revision --autogenerate -m "add_x_to_y"

# Frontend (from frontend/). Bun only.
bun install
bun run dev                     # Vite on :5180, proxies /api to :8100
bun run build                   # must pass before pushing
bun run lint
```

Deploy: `render.yaml` and `docs/deploy-render.md`.

---

## Git workflow

1. **Work happens on `dev`**: commit to it directly during the hackathon. `main` gets `dev` through a PR, which the owner merges.
2. **Never push to `main`, force-push, or merge a PR yourself.**
3. Commit messages are imperative and specific ("Issue an invoice when a buyer picks a coin"), not "fix stuff".
4. Before pushing: `uv run pytest`, and `bun run build` + `bun run lint` if the frontend changed.
5. Never commit `.env*` (except `.env.example`), `node_modules/`, `dist/`, `.venv/`, `.python/`, or a submission payload.
6. **The repo is public.** Anything committed is visible to everyone at once.

---

## Hackathon rules that bind every change

- **Never without the owner's explicit yes:** sending the hackathon submission (one attempt only; print the full payload first), posting anywhere, making anything public, signing transactions, spending tokens, or anything that moves real funds.
- **Mainnet only.** NEAR Intents and the Agent API have no testnet. Tests use about $1 and `dry` quotes where possible.
- **Disclose reused code** in the README: the agent loop and LLM layer from gtmx are pre-hackathon baseline; the gtmx Thalace Store work (`near-hackathon` branch, PRs #366–#372) was built inside the window and ported here.
- **Write the README for judges and AI screeners**: what it is, the problem, and "do X → see Y" steps that reproduce it. No marketing.
- **Passkeys are bound to their domain for good.** Final demo shops are made only on `https://shops.thalace.com`. Before testing go-live locally, start a Cloudflare tunnel; tunnel shops are throwaway.

---

## Money rules (review blockers)

- **The prompt never enforces a limit.** Payees, caps, price floors and allowed suppliers live in the owner-signed wallet policy or in code. An agent's tool can't change them.
- **Another agent's message is data, never instructions.** Negotiation moves are typed and checked in code before the other side sees them.
- **Write the ledger entry before moving money**, keyed so a retry never pays twice. Every Agent API money call has a stored `Idempotency-Key`.
- **One money action per shop wallet at a time**: payouts, fees and purchases go through the shop's queue.
- **No float money.** Amounts are integers in atomic units or cents, or `Decimal`.
- **Partner API keys and grant tokens never reach the browser, a prompt, or a log line.** Grant tokens are stored encrypted.

---

## File structure

```
backend/
  config.py                      # Settings: the ONLY place env vars / .env are read
  app/
    main.py
    api/v1/endpoints/<resource>.py   # thin HTTP layer: validate, authorize, call a service
    api/deps.py                  # auth + ownership dependencies (the only place they live)
    services/<resource>.py       # business logic + DB access. No FastAPI imports.
    database/models.py           # SQLAlchemy models
    database/migrations/         # Alembic
    schemas/<resource>.py        # pydantic request/response models
  agents/
    shop/                        # the shop agent: graph, tools, store protocol, prompts
    schemas/                     # ALL pydantic models for agents
    llm/                         # LLM client, provider ladder, retries
  data_sources/<provider>/       # external API adapters
  utils/                         # logging and shared helpers
  tests/                         # mirrors the source tree
frontend/src/
  features/<feature>/            # components, hooks, types for one feature
  components/                    # shared, feature-agnostic components
  lib/api/                       # typed API client, one module per backend resource
docs/                            # build plan, deploy guide, RULES.md for group orders
```

- **One home per concept.** Search for an existing module before creating one.
- **Keep files small:** over ~600 lines (Python) or ~400 (TSX) means split by responsibility.
- **No orphans:** no empty files, `_old`/`_v2` copies, commented-out modules or scratch scripts.

---

## Code rules

- **No silent failure.** No `except Exception: pass`, and no returning `None`/`""` for a hard error. Catch narrowly, log with context (`utils.log.logger`), and raise or return a typed result. A shop agent's tool returns a result the model reads; it never raises out of the turn.
- **Ownership on every route.** Anything under a shop (offers, invoices, ledger, policy) resolves the shop through the ownership dependency in `api/deps.py`, which returns 404 for someone else's shop. Admin routes live under `/api/v1/admin/*` behind `require_admin`, and every admin write is audited.
- **Env reads only in `config.py`.** In the frontend, `import.meta.env` only inside `lib/`.
- **Bounded work.** Every LLM, HTTP and Agent API call has a timeout. Every list endpoint has a limit. Every agent run has a wall-clock cap and a tool-call cap.
- **Don't block the event loop.** Sync LLM/HTTP calls inside `async def` go through `asyncio.to_thread`.
- **No magic values.** Model ids, limits, URLs, fees and timeouts are settings or named constants.
- **Typed state.** Statuses (invoice, shop, group order) are `Enum`/`Literal` in Python and union types in TypeScript.
- **No mock data in shipped paths.** Simulation mode is explicit and labelled on screen.
- **Comments explain why, not what.** No changelog comments. No `print()`, no `console.log`.
- **TypeScript:** no `any`, no `@ts-ignore`, no non-null `!` without a comment saying why.

## Database

- **Alembic is the only way the schema changes.** No `create_all` or `ALTER TABLE` at startup.
- Every model change ships its migration in the same commit, with a working `downgrade()`. Migration files: `YYYYMMDD_HHMM_<short_description>.py`.
- FKs with an explicit `ondelete`, unique constraints for natural keys, indexes on FKs and filtered columns.
- `user_id` columns are indexed UUIDs with **no** FK: Supabase owns users.
- Timestamps are `DateTime(timezone=True)`, in UTC.
- **Never run destructive SQL against the Supabase database** without the owner's OK. Local dev uses Docker Postgres only.

## Definition of done

It works end to end locally (backend + frontend against Docker Postgres), tests cover the new behaviour, the checks in Git workflow step 4 pass, migrations round-trip, and `docs/build-plan.md` is updated if a decision changed.
