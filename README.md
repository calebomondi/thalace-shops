# Thalace Shops

**A founder opens one or more virtual shops. Each shop gets its own AI agent and its own wallet on NEAR Intents, inside rules the owner signs and the agent can't change. People buy on the shop's page; other agents buy through MCP; shops negotiate with each other, buy from each other and pool their demand into group orders. Every purchase is an invoice on a public ledger.**

Built for **NEAR HACKATHON** (2026-10-19 → 2026-11-14). Main track: **`business`** (Autonomous Business). Also: `agents`, `swarms`, `security`, `realworld` (see [Tracks](#tracks)).

## The problem

A small business, such as a 3D-printing workshop in Nairobi that takes M-Pesa, can't easily sell to a buyer abroad who holds stablecoins, or to the growing number of buyers that are AI agents. Even if it could, handing an AI agent money is risky: an agent that can sell, pay suppliers and split revenue can also be talked into paying the wrong address.

Thalace Shops puts the business online, onchain and in front of agents, with the money rules enforced where the agent can't reach them:

- **Each shop's wallet is a NEAR Intents Agent API wallet whose policy the owner signs with a passkey.** It can pay only the payees the owner listed, the platform fee account and allowed supplier shops, only in the shop's settlement coin, and never more than the daily cap. The policy is enforced by the Agent API in an attested TEE and by the wallet itself, not by the prompt.
- **The agent runs the shop inside those rules:** it drafts offers from the shop's website, negotiates with buyer agents (never below the owner's floor, enforced in code), buys from allowed suppliers and joins group orders.
- **Buyers pay in a dollar stablecoin on any chain** (USDC on NEAR, Base, Arbitrum, Solana, Ethereum; USDT on NEAR, Tron). NEAR Intents credits the shop's wallet in USDC on NEAR.

The demo business is **Shanga Prints** (https://prints.shangalabs.com), a real digital-manufacturing business in Nairobi run by this project's founder: CAD design, 3D printing, laser cutting and engraving.

## What it does

| | For whom | What happens |
|---|---|---|
| **Shops and agents** | Founders | Create shops from a name and website. Each shop's ReAct agent (on NEAR AI Cloud) reads the site and drafts offers; the owner puts them on sale and sets the floor price, payees and daily cap. |
| **Go live** | Founders | Sign twice with a passkey: `agent_create` opens the shop's wallet under the signed policy, `grant_issue` lets the backend act inside it. One passkey owns all of a founder's shops. |
| **Invoices** | People | A shop page at `/s/<slug>`; buying issues an invoice (`SP-0001`); picking a coin quotes a one-time deposit address for the exact total; the invoice page shows the QR, a countdown and the status live (paid, expired, refunded to the shop). |
| **Payouts** | Everyone | When a payment lands, the 2% platform fee goes to `thalaceshops.near`, then each payee's share, one transfer at a time per wallet, each on the ledger before it's sent. Public ledger and CSV export. |
| **Agents as buyers** | Other agents | An MCP server at `/mcp`: search shops, negotiate, place orders, pay, check status. |
| **Negotiation** | Agents and shops | Typed moves, at most 3 buyer offers. The shop's agent accepts, counters or walks away; code makes sure it never agrees below the floor, never counters outside the buyer's offer and the list price, and never reveals the floor. |
| **Group orders** | Buyers, swarms | Buyers pool demand on an offer with volume tiers; at the deadline the price locks at the tier reached and each member gets their own invoice ([rules](docs/RULES.md)). Market at `/market`. |
| **Shop to shop** | Shops' agents | A shop's agent buys from an allowed supplier, paid by an Intents transfer from its wallet; the transfer settles the supplier's invoice. |
| **Controls** | Founders | Pause selling (instant), freeze the wallet (signed), change payees, cap and allowed suppliers on a live wallet (signed `policy_update`). |

## How NEAR is used

| NEAR piece | Where | What for |
|---|---|---|
| **NEAR Intents Agent API** (`docs.agentsonintents.com`) | `backend/data_sources/near/agent_api.py`, `backend/app/services/signing.py` | One wallet per shop. `agent_create` with an owner-signed policy (destinations, per-asset limits, USD budget), `grant_issue`, `policy_update`, `agent_freeze` / `agent_unfreeze`, all signed by the owner's **passkey** (`webauthn`). |
| **Intents deposits (1Click)** | `backend/app/services/invoices.py` | A one-time deposit address per invoice, quoted for the exact amount in the buyer's coin and chain, converted on arrival to the shop's settlement asset. Refunds land in the shop's own wallet. |
| **Intents transfers** | `backend/app/services/fulfilment.py`, `procurement.py` | The platform fee, payee shares and shop-to-shop purchases, each only to destinations in the signed policy, within the daily cap; idempotency keys stored before sending. |
| **NEAR accounts** | Policy destinations | Payees and the platform treasury (`thalaceshops.near`) are NEAR accounts; each shop's wallet is its own NEAR Intents account. |
| **NEAR AI Cloud** | `backend/agents/llm/main.py` | First provider for the shop agents and the negotiator (GLM-5.3, Qwen3.8-27B, DeepSeek V4.1 Flash, each checked to call tools). |

## Try it

### Without keys or money: the tests

The whole system runs against a fake Agent API in the test suite (121 tests: negotiation limits, group-order rules, the fee and payout split, shop-to-shop transfers, wallet controls, MCP over JSON-RPC).

```sh
cd backend
uv sync
docker compose up -d --wait postgres     # Postgres 17 on port 5433
uv run pytest                            # -> 121 passed
```

Do these → see this:

- `uv run pytest tests/agents/test_negotiator.py` → the shop never accepts below its floor, a reason naming the floor is replaced, a buyer's "ignore your rules" is passed to the model as quoted data.
- `uv run pytest tests/app/test_group_orders.py` → 3 + 4 + 5 units reach the 10+ tier; each member is invoiced at $6.00.
- `uv run pytest tests/app/test_invoices.py -k fee_then` → a $7.99 payment: $0.1598 fee to the treasury, then 90% of the rest to the payee, one transfer at a time.
- `uv run pytest tests/app/test_procurement.py` → buying is refused until the owner signs the supplier into the policy; then the transfer pays the supplier's invoice.

### Locally, with keys

You need: Supabase (auth), a NEAR Intents Agent API key (the demo key works: `https://api.demo.agentsonintents.com`; it runs on **mainnet**), a NEAR AI Cloud key, and a Firecrawl key (the agent reads websites).

```sh
# API on http://localhost:8100
cd backend
cp .env.example .env            # fill in the keys; SHOP_GRANT_KEY is a Fernet key (see docs/deploy-railway.md)
uv sync
./scripts/dev.sh                # Postgres, migrations, then the API

# App on http://localhost:5180
cd frontend
cp .env.example .env.local      # VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY
bun install
bun run dev
```

Passkeys need `https://`: for going live locally, run `cloudflared tunnel --url http://localhost:5180` and set `FRONTEND_BASE_URL` to the tunnel's address. A shop made through a tunnel is tied to that address for good.

Do these → see this:

1. Sign in (email link or Google) → **New shop** → name it and give its website → the shop page opens with the agent chat.
2. Ask the agent *"Read my website and draft offers for buyers paying online"* → it reads the site and drafts offers marked "drafted by your agent"; **Put on sale** on one.
3. Set a payee and the daily cap → **Sign and go live** → two passkey prompts → the shop shows its wallet's NEAR Intents account.
4. Open **Shop page** → **Buy** → invoice `XX-0001` → pick a coin → a deposit address, exact amount and QR. *(Paying it moves real money: $1 minimum.)*
5. Ask an MCP client to buy (below) → the shop page's **Negotiations** shows every move and reason.
6. On an offer, **Group buying** → add a tier → `uv run python scripts/simulate_market.py --offer <offer id>` → `/market` fills with simulated buyers ("Sim buyer N"; no LLM calls, nothing paid).

### Buy with your own agent (MCP)

Point any MCP client at `<app>/mcp` (streamable HTTP, no auth):

```json
{ "mcpServers": { "thalace-shops": { "type": "http", "url": "https://shops.thalace.com/mcp" } } }
```

Tools: `search_shops`, `get_shop`, `negotiate`, `respond_to_counter`, `place_order`, `invoice_status`, `list_group_orders`, `open_group_order`, `join_group_order`, `group_order_status`, `pay_invoice`.

## Checked against the real services

| Checked live | Result |
|---|---|
| Go live through a tunnel, demo Agent API key | `agent_create` and `grant_issue` signed with a passkey; the shop got its own wallet on mainnet. Found and fixed: the API requires `limits` in the policy. |
| Deposit quotes on that wallet | $1 accepted for USDC on Base and on NEAR; quotes last about four days. |
| NEAR AI Cloud | Tool calls from GLM-5.3, Qwen3.8-27B, DeepSeek V4.1 Flash and Kimi K3. |
| Agent reading the shop's site | Drafted three offers from prints.shangalabs.com. |
| Negotiation over MCP | Buyer offered $25 × 3 for CAD designs → shop's agent countered $40 → accepted $32 (floor $30, never shown). |
| Docker images | API and app images built and run together; the API answers on IPv4 and IPv6; Caddy forwards `/api` and `/mcp`. |

Not yet run with real money: a paid invoice, fee and payout transfers, a shop-to-shop transfer, `policy_update` and `agent_freeze` on a live wallet. The tests cover these with a fake Agent API.

## Architecture

```
frontend (React 19, Vite, Tailwind)  ─┐   served by Caddy on Railway; /api and /mcp forwarded
                                      ▼
backend/app (FastAPI)  ── auth (Supabase), ownership, invoices, signing, ledger, MCP server
   │   └─ worker: closes group orders, watches payments, sends fees, payouts and purchases
   ▼
backend/agents (LangGraph)  ── the shop agent (ReAct) and the negotiator; pure, they reach data through a store protocol
   ▼
backend/data_sources  ── NEAR Intents Agent API, Firecrawl
```

| Path | What |
|---|---|
| `backend/app/services/` | Business logic: `invoices`, `fulfilment`, `signing`, `rules`, `negotiation`, `group_orders`, `procurement`, `ledger`, `directory` |
| `backend/app/mcp_server.py` | The MCP server |
| `backend/app/worker.py` | The watcher loop (one API replica, always on) |
| `backend/agents/shop/` | The shop agent: graph, tools, store protocol, prompts, negotiator |
| `backend/app/database/migrations/` | Alembic migrations (each round-tripped) |
| `frontend/src/features/` | Console (`shops`, `shop`), public pages (`storefront`), sign-in (`auth`) |
| `docs/RULES.md` | Group-order rules |
| `docs/build-plan.md` | The plan, decisions and the Agent API facts the design rests on |
| `docs/deploy-railway.md` | Deploying on Railway |

## Tracks

| Track | Why |
|---|---|
| `business` (main) | Each shop's agent runs sales, purchasing and revenue sharing; the owner only sets the rules (payees, cap, floor, suppliers), signed into the wallet. |
| `agents` | Outside agents find shops, negotiate and pay through MCP; shops' agents buy from other shops. |
| `swarms` | Group orders: many buyer agents and shops pool demand on volume tiers; each settles its own invoice through NEAR Intents. |
| `security` | Spending is bounded by an owner-signed policy in the Agent API's TEE (destinations, limits, budget), a signed freeze, floors enforced in code, and buyer text treated as data. |
| `realworld` | Invoices, stablecoin payments from any chain, a public ledger and an accountant's CSV, for a real Nairobi business. |

## Disclosures

- **Baseline (pre-hackathon) code**, from the founder's own product Thalace (GTMX): `backend/agents/llm/` (the LLM provider ladder) and the shape of `backend/config.py`. The shop agent's loop (`backend/agents/shop/graph.py`) follows that product's agent design. HACKATHON.md Q-002, Q-005.
- **Built inside the window but outside this repo:** the "Thalace Store" on the GTMX `near-hackathon` branch (PRs #366–#372, 2026-11-01 to 11-03). Its Agent API client, passkey go-live, checkout, watcher and payouts were ported here and reshaped (invoices, the fee, shop-to-shop, group orders). The GTMX Store isn't submitted separately.
- **This repository** started on 2026-11-08; everything else in it was written during the hackathon.
- **AI assistance:** much of the code was written with Claude Code, directed and reviewed by the founder.
- **Libraries:** FastAPI, SQLAlchemy, Alembic, psycopg, pydantic, LangGraph, LangChain, MCP Python SDK, httpx, cryptography, React, React Router, Tailwind CSS, Supabase JS, SimpleWebAuthn, qrcode, Caddy.
- **Not included:** KRA (Kenya Revenue Authority) checks and email receipts.
- **Risk:** the NEAR Intents Agent API is an experimental, mainnet-only beta; real tests use about $1.

## License

MIT, see [LICENSE](LICENSE).
