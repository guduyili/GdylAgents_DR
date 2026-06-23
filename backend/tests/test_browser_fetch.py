from __future__ import annotations

from config import Configuration
from services.browser_fetch import (
    BrowserFetchService,
    PageFetchResult,
    needs_page_enrichment,
    strip_html_to_text,
)


def test_strip_html_to_text_removes_tags_and_scripts() -> None:
    html = "<html><script>ignore()</script><body><h1>Title</h1><p>Body</p></body></html>"

    text = strip_html_to_text(html)

    assert "Title" in text
    assert "Body" in text
    assert "ignore" not in text


def test_needs_page_enrichment_detects_thin_hits() -> None:
    assert needs_page_enrichment({"url": "https://example.com", "content": "short"}) is True
    assert needs_page_enrichment(
        {"url": "https://example.com", "content": "x" * 200}
    ) is False


def test_browser_fetch_service_enriches_thin_results_with_http_backend() -> None:
    config = Configuration(enable_notes=False, fetch_full_page=True, enable_browser_fetch=True)

    def fake_http(url: str, **kwargs):
        return PageFetchResult(url=url, content="补全后的页面正文" * 20, backend="http")

    def fail_browser(url: str, **kwargs):
        raise AssertionError("browser fetch should not run when HTTP succeeds")

    service = BrowserFetchService(http_fetcher=fake_http, browser_fetcher=fail_browser)
    payload, notices = service.enrich_search_payload(
        {
            "results": [
                {"title": "A", "url": "https://example.com", "content": "短"},
            ]
        },
        config=config,
    )

    enriched = payload["results"][0]
    assert enriched["fetch_backend"] == "http"
    assert len(enriched["raw_content"]) >= 120
    assert any("http" in notice for notice in notices)


def test_browser_fetch_service_falls_back_to_browser_when_http_is_thin() -> None:
    config = Configuration(enable_notes=False, fetch_full_page=True, enable_browser_fetch=True)

    def thin_http(url: str, **kwargs):
        return PageFetchResult(url=url, content="短", backend="http")

    def browser_fetch(url: str, **kwargs):
        return PageFetchResult(url=url, content="浏览器渲染正文" * 30, backend="browser")

    service = BrowserFetchService(http_fetcher=thin_http, browser_fetcher=browser_fetch)
    payload, notices = service.enrich_search_payload(
        {
            "results": [
                {"title": "A", "url": "https://spa.example.com", "content": ""},
            ]
        },
        config=config,
    )

    enriched = payload["results"][0]
    assert enriched["fetch_backend"] == "browser"
    assert any("browser" in notice for notice in notices)


def test_browser_fetch_service_is_noop_when_disabled() -> None:
    config = Configuration(enable_notes=False, fetch_full_page=True, enable_browser_fetch=False)
    service = BrowserFetchService(
        http_fetcher=lambda url, **kwargs: (_ for _ in ()).throw(AssertionError("disabled")),
        browser_fetcher=lambda url, **kwargs: (_ for _ in ()).throw(AssertionError("disabled")),
    )

    original = {"results": [{"title": "A", "url": "https://example.com", "content": "短"}]}
    payload, notices = service.enrich_search_payload(original, config=config)

    assert payload == original
    assert notices == []