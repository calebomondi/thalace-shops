# Thalace Shops backend

FastAPI API and LangGraph agents, Python 3.14, managed with uv. Run every command from `backend/`.

```sh
cp .env.example .env   # fill in the keys
uv sync
./scripts/dev.sh       # http://localhost:8000
curl localhost:8000/api/v1/health
```

| Path | What it is |
| --- | --- |
| `config.py` | All settings; the only reader of `.env` |
| `app/` | FastAPI app (`main.py`), routes (`api/v1/`), database (`database/`) |
| `agents/` | Agents; `agents/llm/` is the LLM provider ladder |
| `utils/` | Logging (`log.py`) |
| `tests/` | Tests |
