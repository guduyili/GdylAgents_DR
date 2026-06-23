"""Browser fetch service: enrich thin search hits with HTTP or Playwright page content."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from config import Configuration

logger = logging.getLogger(__name__)

MIN_CONTENT_CHARS = 120
DEFAULT_HTTP_TIMEOUT_SECONDS = 15
DEFAULT_MAX_PAGE_CHARS = 8000
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style)[^>]*>.*?</\1>")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class PageFetchResult:
    """Normalized page text extracted from a URL."""

    url: str
    content: str
    backend: str


def strip_html_to_text(html: str) -> str:
    """Convert HTML into plain text for LLM context."""
    without_blocks = _SCRIPT_STYLE_RE.sub(" ", html)
    without_tags = _HTML_TAG_RE.sub(" ", without_blocks)
    return _WHITESPACE_RE.sub(" ", without_tags).strip()


def needs_page_enrichment(source: dict[str, Any], *, min_chars: int = MIN_CONTENT_CHARS) -> bool:
    """Return True when a search hit lacks enough page text for downstream summarization."""
    url = str(source.get("url") or "").strip()
    if not url:
        return False

    content = str(source.get("content") or "").strip()
    raw_content = str(source.get("raw_content") or "").strip()
    return max(len(content), len(raw_content)) < min_chars


def fetch_page_http(
    url: str,
    *,
    timeout_seconds: int = DEFAULT_HTTP_TIMEOUT_SECONDS,
    max_chars: int = DEFAULT_MAX_PAGE_CHARS,
) -> PageFetchResult | None:
    """Fetch a page via plain HTTP and extract visible text."""
    try:
        request = Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; GdylAgentsDR/1.0; +https://example.com/bot)"
                )
            },
        )
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            html = payload.decode(charset, errors="ignore")
    except (URLError, TimeoutError, ValueError) as exc:
        logger.debug("HTTP 页面抓取失败 url=%s error=%s", url, exc)
        return None

    text = strip_html_to_text(html)
    if not text:
        return None

    if len(text) > max_chars:
        text = f"{text[:max_chars]}... [truncated]"

    return PageFetchResult(url=url, content=text, backend="http")


def fetch_page_browser(
    url: str,
    *,
    max_chars: int = DEFAULT_MAX_PAGE_CHARS,
) -> PageFetchResult | None:
    """Fetch a page via Playwright when HTTP extraction is insufficient."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.info("Playwright 未安装，跳过 browser fetch: %s", url)
        return None

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                text = page.inner_text("body").strip()
            finally:
                browser.close()
    except Exception as exc:
        logger.warning("Browser 页面抓取失败 url=%s error=%s", url, exc)
        return None

    if not text:
        return None

    if len(text) > max_chars:
        text = f"{text[:max_chars]}... [truncated]"

    return PageFetchResult(url=url, content=text, backend="browser")


class BrowserFetchService:
    """Enrich search results by fetching missing page bodies."""

    def __init__(
        self,
        *,
        http_fetcher: Callable[..., PageFetchResult | None] = fetch_page_http,
        browser_fetcher: Callable[..., PageFetchResult | None] = fetch_page_browser,
        min_content_chars: int = MIN_CONTENT_CHARS,
        max_page_chars: int = DEFAULT_MAX_PAGE_CHARS,
    ) -> None:
        self._http_fetcher = http_fetcher
        self._browser_fetcher = browser_fetcher
        self._min_content_chars = min_content_chars
        self._max_page_chars = max_page_chars

    def enrich_search_payload(
        self,
        payload: dict[str, Any],
        *,
        config: Configuration,
    ) -> tuple[dict[str, Any], list[str]]:
        """Fill thin search hits with fetched page text when browser fetch is enabled."""
        if not config.fetch_full_page or not config.enable_browser_fetch:
            return payload, []

        results = list(payload.get("results") or [])
        if not results:
            return payload, []

        notices: list[str] = []
        enriched_results: list[dict[str, Any]] = []

        for source in results:
            if not isinstance(source, dict):
                enriched_results.append(source)
                continue

            if not needs_page_enrichment(source, min_chars=self._min_content_chars):
                enriched_results.append(source)
                continue

            url = str(source.get("url") or "").strip()
            fetched = self._http_fetcher(url, max_chars=self._max_page_chars)
            if fetched is None or len(fetched.content) < self._min_content_chars:
                fetched = self._browser_fetcher(url, max_chars=self._max_page_chars)

            if fetched is None or not fetched.content:
                enriched_results.append(source)
                continue

            enriched = dict(source)
            enriched["content"] = fetched.content
            enriched["raw_content"] = fetched.content
            enriched["fetch_backend"] = fetched.backend
            enriched_results.append(enriched)
            notices.append(f"已通过 {fetched.backend} 补全页面内容: {url}")

        if not notices:
            return payload, []

        enriched_payload = dict(payload)
        enriched_payload["results"] = enriched_results
        return enriched_payload, notices