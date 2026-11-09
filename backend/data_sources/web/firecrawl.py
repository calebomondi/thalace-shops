"""Reading one web page as Markdown, through Firecrawl's scrape API."""

from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from config import settings
from utils.log import logger

_SCRAPE_URL = "https://api.firecrawl.dev/v2/scrape"


class PageReadError(Exception):
    """The page couldn't be read. The message is safe to show the model."""


@dataclass(frozen=True)
class Page:
    url: str
    title: str
    markdown: str
    truncated: bool


def _check_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise PageReadError("Only http(s) pages can be read.")


async def read_page(url: str, *, max_chars: int | None = None,
                    transport: httpx.AsyncBaseTransport | None = None) -> Page:
    _check_url(url)
    if not settings.firecrawl_api_key:
        raise PageReadError("Reading websites isn't set up (FIRECRAWL_API_KEY).")
    limit = max_chars or settings.website_read_max_chars
    try:
        async with httpx.AsyncClient(timeout=settings.firecrawl_timeout_s, transport=transport) as client:
            response = await client.post(
                _SCRAPE_URL, headers={"Authorization": f"Bearer {settings.firecrawl_api_key}"},
                json={"url": url, "formats": ["markdown"], "onlyMainContent": True})
    except httpx.HTTPError as exc:
        logger.warning("Firecrawl unreachable for %s: %s", url, exc)
        raise PageReadError("The page reader didn't answer. Try again in a minute.") from exc
    if response.status_code >= 400:
        logger.warning("Firecrawl refused %s: %s", url, response.status_code)
        raise PageReadError(f"That page couldn't be read (status {response.status_code}).")
    data = (response.json().get("data") or {})
    markdown = data.get("markdown") or ""
    if not markdown.strip():
        raise PageReadError("That page has no readable text.")
    title = (data.get("metadata") or {}).get("title") or url
    return Page(url=url, title=str(title), markdown=markdown[:limit], truncated=len(markdown) > limit)
