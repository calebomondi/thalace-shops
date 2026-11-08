# Thalace Shops

> Built for NEAR HACKATHON (2026-10-19 → 2026-11-14). Product description, NEAR integration and judge walkthrough: TODO.

## Repository layout

| Path | What it is |
| --- | --- |
| `backend/` | Python 3.14 API (FastAPI) and agents (LangGraph), managed with uv |
| `backend/app/` | FastAPI app: `main.py`, routes under `api/v1/`, database in `database/` |
| `backend/agents/` | Agents; `agents/llm/` is the LLM provider ladder (Qwen, then OpenRouter) |
| `backend/utils/` | Shared helpers (logging) |
| `backend/config.py` | The only place that reads env vars (`backend/.env`) |
| `frontend/` | React 19 + TypeScript + Vite, managed with bun |
| `HACKATHON.md` | The hackathon rules (live copy: https://nearhackathon.com/HACKATHON.md) |

## Run it locally

Prerequisites: [uv](https://docs.astral.sh/uv/), [bun](https://bun.sh/) and Docker (local Postgres on port 5433).

```sh
# Backend: http://localhost:8000
cd backend
cp .env.example .env        # then fill in the keys
uv sync
./scripts/dev.sh            # starts Docker Postgres, then the API
curl localhost:8000/api/v1/health   # -> {"status":"ok",...}

# Frontend: http://localhost:5173
cd frontend
bun install
bun run dev
```

## Baseline code and disclosures

- `backend/agents/llm/` and `backend/config.py` are adapted from the team's pre-hackathon product, Thalace. They count as baseline (HACKATHON.md Q-002, Q-005), and only the NEAR integration built during the hackathon is judged.
- Libraries: FastAPI, LangGraph, LangChain (langchain-qwq, langchain-openai), SQLAlchemy, psycopg, pydantic-settings, React, Vite.
- Parts of this code were written with AI assistance (Claude Code).
