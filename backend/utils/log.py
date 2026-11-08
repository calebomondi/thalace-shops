"""Process-wide logging, configured once from settings.

`current_run_id` tags work (LLM calls, tool calls) with the run it belongs to;
set it at the start of a run and every log line and usage record carries it.
"""

import json
import logging
import sys
from contextvars import ContextVar

from config import settings

current_run_id: ContextVar[str | None] = ContextVar("current_run_id", default=None)


class _RunIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = current_run_id.get() or "-"
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "run_id": getattr(record, "run_id", "-"),
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _build_logger() -> logging.Logger:
    log = logging.getLogger("thalace")
    if log.handlers:
        return log
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(_RunIdFilter())
    if settings.log_format == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(run_id)s] %(name)s: %(message)s"))
    log.addHandler(handler)
    log.setLevel(settings.log_level.upper())
    log.propagate = False
    return log


logger = _build_logger()
