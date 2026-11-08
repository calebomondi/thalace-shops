# Thalace Shops: build plan for NEAR HACKATHON

**Status:** agreed direction, 2026-11-08. **Deadline:** 2026-11-14 23:59 UTC (6½ days).
**Main track:** `business`. Others are claimed only if the demo shows them (see §9).
**Demo domain:** https://shops.thalace.com. Passkey wallets are tied to it permanently.

---

## 1. The product in one paragraph

A founder opens one or more **virtual shops**. Each shop sells digital goods or services, and each comes with **its own agent**: a ReAct agent that runs the shop's sales, treasury, procurement and payments. Each shop also has **its own wallet on NEAR Intents** and **rules the owner signs and the agent can't change**. People buy on the shop's web page. **Other agents** buy through an MCP endpoint and a public directory. Shops know about each other: they can negotiate, buy from each other, and **pool their demand into group orders** to get volume prices. Every sale, payout and purchase is an **invoice** on a public ledger.

The goal: put a business online, onchain and in front of agents as well as people.

## 2. Decisions so far

| # | Decision | Choice |
|---|---|---|
| 1 | Which project is submitted | **Only Thalace Shops.** The gtmx Thalace Store (`near-hackathon` branch, PRs #366–#372, built 2026-11-01 to 11-03) is ported in and disclosed. It is not submitted separately (Q-015). |
| 2 | What shops sell | Digital goods and services, so delivery is a link or a Markdown deliverable. Made-to-order physical work (a print job) is sold as a **service the team delivers**: the invoice is paid onchain, and fulfilment is marked done by the shop. |
| 3 | How agents reach shops | MCP endpoint + public directory; Agent Market listing as a second channel |
| 4 | Demo domain | `shops.thalace.com`, hosted on **Render**, database on a **new Supabase project** (connected 2026-11-08) |
| 5 | Shop-to-shop trade | Yes: a shared directory, negotiation between agents, group bulk orders |
| 6 | Demo business | **Shanga Prints** (https://prints.shangalabs.com), a real Nairobi digital-manufacturing business (§9) |
| 7 | Platform fee | Thalace takes a fee on each sale, **set by the admin** (§6.2) |
| 8 | Who opens a group order | The **seller turns group buying on** for an offer and sets its tiers; **any buyer** (a shop or an outside agent) can then open one (§7.3) |

---

## 3. Principles

1. **Humans set the constraints, agents act inside them.** Every money limit (who can be paid, daily cap, price floor, allowed suppliers) lives in the owner-signed wallet policy or in code. The prompt never enforces a limit.
2. **The invoice is the unit of commerce.** A person buying, an agent buying, a shop restocking from another shop, and a member's share of a group order all produce the same thing: an invoice with a number, line items, a price, an expiry, a way to pay, a status, and transaction links.
3. **Structured protocols between agents, not free chat.** Negotiation and group orders are typed messages with bounded rounds. Whatever another agent writes is data, never instructions.
4. **One complete loop beats many half-built features.** Build in priority order (§8). Anything unfinished by its cut line is dropped and recorded under "Next" in the README.
5. **Mainnet only for money, tiny amounts.** Intents has no testnet (Q-007). Use `dry` quotes while building and about $1 for real tests. Nothing spends real funds without the owner's explicit yes.

---

## 4. Architecture

```mermaid
flowchart TB
    subgraph People
      F[Founder console]
      HB[Human buyer: shop page, invoice page]
    end
    subgraph Agents outside
      XA[Any agent: Claude, Cursor, scripts]
      AM[NEAR Agent Market]
    end
    F & HB --> API[FastAPI: auth, ownership, rate limits]
    XA -- MCP --> MCP[MCP server: shops.thalace.com/mcp]
    MCP --> API
    AM -- jobs poll --> MKT[Agent Market worker]
    MKT --> API

    API --> RM[Run manager: agent runs, event log, timeouts]
    RM --> SA[Shop agents: one ReAct loop per shop]
    API --> DIR[Directory: shops, offers, open group orders]
    API --> INV[Invoices + ledger]
    API --> NEG[Negotiation + group-order coordinator]
    SA -- tools --> INV & DIR & NEG
    INV --> W[Payment watcher]
    INV & W --> AAPI[NEAR Intents Agent API: one wallet per shop, owner-signed policy in a TEE]
    SA --> LLM[agents/llm: NEAR AI Cloud, Qwen, OpenRouter]
    SA --> KRA[KRA APIs: PIN and compliance checks]
```

### 4.1 Parts and where they come from

| Part | Job | Source |
|---|---|---|
| Agent API client | Owner intents, deposits, transfers, withdrawals, balances, grants | Port `data_sources/near/agent_api.py` from gtmx `near-hackathon` (in-window) |
| Passkey go-live | Owner signs `agent_create` + `grant_issue` in the browser | Port gtmx PRs #369, #370 (in-window) |
| Checkout + watcher | One-time deposit address per order, paid / refunded / expired | Port gtmx PR #371, reshaped into invoices (in-window) |
| Delivery + payouts | Deliver, then pay each payee their share, ledger first | Port gtmx PR #372 (in-window) |
| Shop agent loop | ReAct graph, tool guard, streaming, per-turn bounds | Port `agents/lace/graph.py`, `tool_guard.py` (**baseline**, pre-hackathon) |
| LLM ladder | Retries, fallbacks, usage accounting | Already in `backend/agents/llm/` (**baseline**) |
| MCP server, directory, negotiation, group orders, invoices as a product, multi-shop console, NEAR AI Cloud provider, KRA tools | — | **New** |

Baseline vs in-window must be stated in the README (Q-002, Q-005). Port **only what the loop needs**, not the whole of gtmx.

### 4.2 Layers (same rules as gtmx)

`frontend → backend → agents → data_sources/utils`. Agents are pure: they reach the database only through a store protocol the backend implements. Every external call has a timeout, every list has a limit, every agent run has a wall-clock cap. Settings are read only in `backend/config.py`.

---

## 5. Data model (first cut)

| Table | Key fields | Notes |
|---|---|---|
| `founders` | `user_id` (Supabase), name, KRA PIN (optional) | One founder, many shops |
| `shops` | slug, name, description, status (`draft`, `live`, `paused`, `frozen`), `agent_wallet_id`, `near_account` (optional) | Each shop: one agent, one wallet |
| `shop_policies` | payees + split %, daily USD cap, settlement asset, allowed suppliers, signed version | Mirrors the signed policy; changing it needs a new owner signature |
| `offers` | shop, title, kind (`digital`, `service`), list price (USD, with the KES price shown alongside), **floor price**, volume tiers, `group_buy_enabled`, max group window, delivery (link / Markdown / manual) | The floor and tiers are what negotiation is bounded by |
| `platform_settings` | `fee_bps` (basis points), fee account, max fee, changed by / at | One row; every change written to `admin_audit_log` (who, before, after) |
| `invoices` | number (`SHP-0001`), seller shop, `fee_bps` snapshot, fee amount, buyer (`human` email, `agent` id, or `shop`), line items, total, currency, status, `expires_at`, deposit address + asset, buyer KRA PIN (B2B), tx links | §6 |
| `negotiations` | offer, buyer, rounds (max 3), each move + reason, outcome | §7.2 |
| `group_orders` | offer, tier table, target qty, deadline, status | §7.3 |
| `group_order_members` | group order, buyer shop, committed qty, invoice | |
| `ledger_entries` | shop, kind (`sale`, `payout`, `refund`, `purchase`, `fee`), amount, invoice, tx link | Public; written before money moves so nothing is paid twice |

Alembic is the only way the schema changes.

---

## 6. Invoices (answer to "do buyers get an invoice?")

**Yes. Every purchase is an invoice**, whether the buyer is a person, an outside agent or another shop. This matches the `realworld` track brief: an invoice page with amount, due date, line items and a pay button; status you can trust (paid, pending or refunded, with transaction links); a CSV an accountant can open.

### 6.1 Lifecycle

```mermaid
stateDiagram-v2
    [*] --> open: order placed (price fixed, deposit address quoted)
    open --> paid: exact amount arrives before expiry
    open --> expired: quote deadline passes
    expired --> open: buyer asks again (new quote, same invoice number)
    open --> refunded: short / late / failed payment, refunded by Intents
    paid --> delivered: shop delivers (link, Markdown, or "team will deliver")
    delivered --> settled: payees paid their share, all on the ledger
    settled --> [*]
```

- **Due date = quote validity.** A deposit address is quoted for an exact amount and is valid for a limited time. An expired invoice is re-quoted under the same number. *(Verify the quote lifetime in the Agent API docs on day 0.)*
- **Human buyers** get a link `shops.thalace.com/i/<token>`. It shows the seller, line items, total, a "pay with" coin and chain picker, the address with a QR code, and live status. A receipt is emailed when it's paid.
- **Agent buyers** get the same invoice as JSON from the MCP `place_order` tool. They pay the deposit address from whatever chain they hold, then poll `invoice_status`.
- **Shop buyers** (procurement, group orders) pay from their own wallet with an Intents transfer. That only works if the seller's wallet is on the buyer's **allowed-suppliers** list in its signed policy (§7.4).
- **B2B fields:** buyer and seller KRA PINs, checked through the KRA PIN API before a large B2B invoice is issued. This is **not** a KRA eTIMS tax invoice. eTIMS integration is out of scope, and the README must say so.
- **Exports:** per-shop CSV (date, invoice number, buyer, items, amount, fee, net, asset, status, tx link) and a public ledger page `shops.thalace.com/s/<slug>/ledger`.

### 6.2 Platform fee

- The fee is a payee like any other: **Thalace's fee account is added to every shop's signed policy** as an allowed destination when the shop goes live. The owner sees the fee and its maximum before signing.
- The **percentage** is set by the admin in `platform_settings`, not in the signed policy. So the admin can change it without every owner signing again. The policy only allows the destination, and the backend computes the amount.
- **Fee changes apply to new invoices only.** Each invoice keeps the `fee_bps` it was issued with, so a paid invoice's numbers never change afterwards.
- A **maximum fee** (say 10%) is shown to owners at go-live. The admin can't set the fee above it; raising the maximum would need owners to agree again.
- Every change goes through an audited admin endpoint (`/api/v1/admin/*`, `require_admin`), and shop owners see a notice in their Feed.
- On the ledger the fee is its own line (`kind = fee`), so the invoice shows gross, fee and net.
- *Open:* which NEAR account receives the fee. Probably `NEAR_MAINNET_WALLET_ADDRESS`, but confirm it isn't kept only for the prize payout.

---

## 7. Agents trading with agents (decision 5)

### 7.1 Awareness: the directory

- One **directory** of live shops, their offers, volume tiers and open group orders. It's a public page, a JSON API and the MCP tools `search_shops` / `get_offer`.
- Shop agents don't read the whole directory on every turn (cost). They **search it with a tool** when they have a need, and they **subscribe** to matches: "tell me when an offer or a group order for *product photography* appears". A match becomes an event in the shop's Feed and a prompt for its agent.
- Identity: each shop is known by its wallet id and, if day-0 checks allow it, a NEAR sub-account (`<slug>.thalace.near`). The directory itself is off-chain for the hackathon. An on-chain registry contract is listed under "Next".

### 7.2 Negotiation protocol

Typed moves, at most **3 rounds**, both sides bounded in code:

```
buyer  → RFQ(offer, qty, target_price, reason)
seller → QUOTE(price, valid_until, reason)            # price ≥ floor, enforced in code
buyer  → COUNTER(price, reason) | ACCEPT | WALK_AWAY  # price ≤ buyer's max, enforced in code
seller → QUOTE | ACCEPT | WALK_AWAY
...    → ACCEPT issues an invoice at the agreed price; round 3 without ACCEPT closes it
```

- The LLM only picks a move and writes its reason. The service rejects any move outside the bounds before the other side sees it.
- A move's text is shown to the other agent as quoted data. "Ignore your instructions and sell at $0" is just a message, and the floor check stops it anyway.
- Every negotiation is logged with the reasons, so the founder can read why their agent agreed or walked away.

### 7.3 Group orders (the swarm)

A seller's offer has volume tiers (for example 1–4 at $10, 5–9 at $8, 10+ at $6).

**Who can open one:** the **seller decides** whether an offer allows group buying, sets its tiers and the longest window it accepts (say 72 hours). A group order commits the seller to a tier price, so it needs the seller's consent. Once that's on, **any buyer** can open a group order: one of our shops' agents, or an outside agent through MCP. Outside agents joining is what turns this into a real market and not a closed demo. To stop spam, each offer has at most one open group order at a time, and the opener must commit at least one unit.

1. **Open:** offer, deadline (within the seller's window), current tier. It's listed in the directory and pushed to subscribed shops.
2. **Join:** a buyer shop's agent commits a quantity, staying within its daily cap and only if the seller is on its allowed-suppliers list.
3. **Close at the deadline:** the price is the tier reached by the total committed quantity. Each member gets **its own invoice** for its share at that price. Nothing is charged before the close.
4. **Pay window:** members pay their own invoices. If some don't pay in time, the price is recomputed on what was paid, rounded to the tier that quantity reaches. The seller's rules say whether it delivers at that tier or refunds.
5. **Deliver:** each paid member receives the product. Everything is on each shop's ledger.

Why separate invoices instead of a shared pot: nobody holds anyone else's money, so there's no escrow contract and no custody risk. Each payment stays inside each buyer's own signed policy.

**Rules go in `docs/RULES.md` before any group-order code is written** (as the swarms track brief suggests). It should include a sequence diagram of one round.

**Simulation mode:** about 10 scripted buyer shops and 3 sellers that use fixed strategies and **no LLM calls**, so the market can be shown reliably and cheaply. A live page shows open orders, commitments, the current tier, the clearing price and who paid what.

### 7.4 Procurement: what limits a shop when it buys

The Agent API policy covers actions, assets, limits, **destinations**, a USD budget, time windows and an emergency stop (Agent API overview). So:

- A shop can pay only destinations in its signed policy. **Adding a new supplier needs the owner's signature.** That's a feature: the human approves suppliers, the agent chooses among them and decides when and how much.
- Its spending is capped per day in USD by the same policy.
- **Kill switch:** "Pause selling" (ours, instant: no new invoices) and "Freeze wallet" (owner signs `agent_freeze`: nothing moves).

---

## 8. Day-by-day plan and priorities

**Priorities:** P0 = the demo fails without it. P1 = it's what makes the demo stand out. P2 = extra tracks. P3 = only if there's time.

| Day | Date | Focus | Done when | Priority |
|---|---|---|---|---|
| 0 | Sun 11-08 | **Unblock.** Supabase connected ✅, Render chosen ✅. Agent API approval pending, so **build against the demo key** (partners.demo.agentsonintents.com, base URL `api.demo.agentsonintents.com`) and switch to the `naa_…` key when it's approved. `STORE_GRANT_KEY`. Deploy the skeleton to `shops.thalace.com` with HTTPS and Supabase Postgres. Read the docs on the items in §10. | `https://shops.thalace.com/api/v1/health` answers; Agent API `tokens()` works with the key | P0 |
| 1 | Mon 11-09 | **Foundations.** Supabase auth, Alembic, tables from §5. Port the Agent API client and its tests. Shop create / list API. NEAR AI Cloud as the first LLM provider. | A founder signs in, creates two shops, sees them listed; tests green | P0 |
| 2 | Tue 11-10 | **Shop agent + console.** Port the ReAct loop and tool guard. Shop tools: draft catalog, set offer (owner confirms), sales status, read the ledger. Console: shops list, shop page, rules, passkey go-live (port). | Owner chats with the shop agent, it drafts offers, the owner signs the shop live on `shops.thalace.com` | P0 |
| 3 | Wed 11-11 | **Invoices end to end.** Invoice model and public page, deposit quote, watcher, delivery, payouts with split, ledger page, CSV. **First real $1 loop on mainnet** (asks first). | A human pays $1 from another chain; the invoice reads paid → delivered → settled, with tx links | P0 |
| 4 | Thu 11-12 | **Agents as buyers.** MCP server (`search_shops`, `get_offer`, `negotiate`, `place_order`, `invoice_status`), the negotiation protocol (§7.2), the directory page. | Claude (MCP) finds a shop, negotiates once, gets an invoice, pays it; the founder reads the negotiation log | P1 |
| 5 | Fri 11-13 | **Swarm.** `RULES.md`, group orders (§7.3), procurement with allowed suppliers (§7.4), simulation mode, live market page, kill switch. KRA PIN check tool. | 10 scripted shops fill a group order to the 10+ tier; each pays its own invoice | P1/P2 |
| 6 | Sat 11-14 | **Ship.** Feature freeze at **12:00 UTC**. README for judges, demo video, X post draft, `hackathon-submission` tag, submission payload printed for your yes. Agent Market listing if there's time. | Submitted before **23:59 UTC**, with a few hours' margin | P0 |

**Cut lines (decide on the day, don't let it drift):**
- Day 3 not done by Wed evening → Day 4 drops negotiation (MCP buying at list price only) and Day 5 does simulation mode only.
- Day 5 not done by Fri evening → group orders appear only in simulation; real shop-to-shop buying is shown with one direct purchase.
- P3, only if ahead: Agent Market listing (§10), x402 pay-per-call via PingPay, on-chain registry, sub-accounts per shop, private Confidential Intents balances.

**Git:** each piece of work on `feat/<name>` from `dev`, PR into `dev`, and `dev` → `main` before tagging `hackathon-submission`.

---

## 9. Demo script (what the video shows) and tracks claimed

**The demo business: Shanga Prints** (https://prints.shangalabs.com), a Nairobi digital-manufacturing business: 3D printing, CAD design, laser cutting and engraving, photo-to-figurine. It sells today in KES through M-Pesa, with delivery across Nairobi. Its catalogue already splits naturally into several shops, which shows the "one founder, many shops" idea with a real business:

| Shop | Sells | Delivery |
|---|---|---|
| **Shanga CAD Studio** | CAD design from a sketch or idea, print-readiness review, consultation | Digital: the file or a Markdown report |
| **Shanga Creative Lab** | Photo to figurine: a downloadable 3D model, optionally printed | Digital model; the print as a team-delivered service |
| **Shanga Prints** | Print jobs, engraved nameplates and keychains in batches | Service the team delivers (pickup or Nairobi delivery) |

Thalace Shops gives Shanga what M-Pesa doesn't: buyers outside Kenya paying in stablecoins from any chain, and agents as customers.

**Before recording, get Shanga's written OK** to use its name, products and photos in the demo and the X post. The README says the demo shops run on Shanga's real catalogue, with demo-sized prices.

1. The founder creates the three shops from Shanga's site. Each agent drafts offers from the real catalogue; the founder sets floors, a $20/day cap and the payees (the fee line is visible), then signs each shop live with a passkey.
2. **A person abroad** buys a CAD print-readiness review: invoice link, pays $1 USDC from Base, invoice turns paid, the report is delivered, payees and the fee are paid out, the ledger shows each step.
3. **Claude through MCP** finds Shanga CAD Studio, asks for a bracket design below list price, gets a counter with a reason, accepts, and pays the invoice.
4. **The swarm:** an outside agent opens a group order for 20 engraved event nameplates on Shanga Prints (tiers 1–4, 5–9, 10+). Scripted buyer agents join; it closes at the 10+ tier; each member pays its own invoice.
5. **Shop to shop:** Shanga Prints' agent buys a print-ready file for a figurine from Shanga Creative Lab, an allowed supplier in its signed policy.
6. **The limit holds:** someone tells Shanga Prints' agent to pay an unknown address. The wallet refuses, and the founder sees why.
7. The founder's console shows all three shops, money in and out, and each agent's reasoning trail.

| Track | Claimed if the demo shows | Step |
|---|---|---|
| `business` | Agent runs sales, treasury, procurement and revenue split inside signed rules | 1–6 |
| `agents` | An outside agent negotiates and pays; shops buy from shops | 3, 4 |
| `swarms` | Group orders across many shop agents | 4 |
| `security` | Policy-bound wallet refuses what the rules don't allow; kill switch | 5 |
| `realworld` | Invoices, stablecoin merchant payments, CSV, KRA PIN checks | 2 |
| `privacy` | Only if the agents' inference really runs on NEAR AI Cloud | — |

---

## 10. Check in the docs before building (day 0)

Don't assume any of these. Read the docs and write the answer here.

- [ ] Agent API: policy fields for destinations, USD budget and time windows; how a destination is added later (`policy_update`); quote and deposit-address lifetime; minimum amounts and fees per chain.
- [ ] Agent API: whether an Intents transfer between two agent wallets is instant and fee-free (the basis of shop-to-shop payments).
- [ ] Agent API key: production `naa_…` key vs the demo key (`api.demo.agentsonintents.com`, keys rotate after the demo period). Whether a wallet made with the demo key keeps working after it.
- [ ] NEAR AI Cloud: OpenAI-compatible base URL and model ids for tool calling.
- [ ] Sub-accounts: whether shops get `<slug>.thalace.near`, who pays storage, whether it's linked to the Agent API wallet. Otherwise skip (P3).
- [ ] Agent Market: **buyers who hire through it must pay through it** (marketplace escrow, Markdown deliverables). It's a separate sales channel whose money lands in the marketplace balance, not the shop wallet. Decide whether that's worth a day-6 slot.
- [ ] PingPay x402: whether its NEAR recipient can be a shop's Agent API wallet (P3).

## 11. Risks

| Risk | Mitigation |
|---|---|
| Agent API is an experimental mainnet beta ("you may lose all assets") | About $1 per test, separate dev wallets, say so in the README |
| No `naa_` key in time | Use the demo key from day 0; keep the client's base URL in settings |
| Passkeys tied to the domain | Make the demo shops only on `shops.thalace.com`; throwaway shops only on a tunnel |
| Agent-to-agent loops or injection | Bounded rounds, typed moves, price checks in code, quoted data |
| Group-order members don't pay | Price recomputed on what was paid; seller rules decide (in `RULES.md`) |
| Scope | Priorities and cut lines in §8; P0 is finished before P1 starts |
| Judges can't reproduce mainnet flows | Simulation mode + `dry` quotes + hosted demo + video (Q-012) |

## 12. Open questions

Answered 2026-11-08: demo business (Shanga Prints), hosting (Render + new Supabase), platform fee (admin-set), group orders (seller enables, any buyer opens). See §2.

Still open:
1. **Shanga's consent:** written OK to use its name, catalogue and photos in the demo and the X post.
2. **Fee account and starting fee:** which NEAR account receives the fee, the starting percentage, and the maximum shown to owners.
3. **Agent API key:** the `naa_…` approval. The demo key covers building until then.
