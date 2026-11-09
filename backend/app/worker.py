"""The loop that keeps money moving without anyone watching: it reads each
payment awaiting arrival, closes group orders whose deadline passed, and plans,
sends and settles fees and payouts.

It runs inside the API process, which is why the API runs as exactly one
always-on replica on Railway: two copies would race each other, and a
sleeping one would miss payments."""

import asyncio
import contextlib

from app.services import fulfilment, group_orders, invoices
from config import settings
from utils.log import logger


async def run_once() -> None:
    closed = await group_orders.close_due()
    paid = await invoices.watch_invoices()
    settled = await fulfilment.fulfil()
    if closed or paid or settled:
        logger.info("Watcher: %d group orders closed, %d invoices paid, %d fees and payouts settled",
                    closed, paid, settled)


async def _loop() -> None:
    while True:
        try:
            await run_once()
        except Exception:  # noqa: BLE001 -- one bad round must not stop the loop; logged with its trace
            logger.exception("Watcher round failed")
        await asyncio.sleep(settings.watcher_interval_s)


@contextlib.asynccontextmanager
async def running():
    """Run the watcher for the life of the app, when enabled."""
    if not settings.watcher_enabled:
        yield
        return
    task = asyncio.create_task(_loop(), name="watcher")
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
