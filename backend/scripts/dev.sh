#!/usr/bin/env bash
#
# Dev backend runner: uvicorn with reload, run from backend/ so `config`,
# `app`, `agents` and `utils` import as top-level packages.
#
# The explicit --reload-dir list keeps the watcher on Python source only, so
# .venv churn doesn't bounce the server mid-request.
#
# Caveat: --reload-dir only takes directories, so a change to config.py is not
# picked up. Restart manually after editing it.
set -euo pipefail

cd "$(dirname "$0")/.."

exec uv run uvicorn app.main:app \
  --reload \
  --host 0.0.0.0 \
  --port 8000 \
  --reload-dir app \
  --reload-dir agents \
  --reload-dir utils
