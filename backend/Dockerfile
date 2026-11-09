# The API: FastAPI + the shop agents + the payment watcher. Built by Railway
# (backend/railway.json); runs as exactly one replica.
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1

WORKDIR /app
# Dependencies first, so a code change doesn't reinstall them.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .

# One socket for IPv6 (Railway's private network) and IPv4 (its edge): serve.py.
CMD ["python", "serve.py"]
