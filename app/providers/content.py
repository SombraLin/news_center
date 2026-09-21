from __future__ import annotations

import asyncio
import html
import json
import re
import unicodedata
from html.parser import HTMLParser
from typing import Any

import httpx

from app.domain import ArticleCandidate

_WHITESPACE = re.compile(r"\s+")
_SCRIPT_JSONLD = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
_EFFECTIVE_CHAR = re.compile(r"[\u3400-\u9fffA-Za-z0-9]")


def normalize_content(value: str, max_chars: int = 30_000) -> str:
    value = html.unescape(value or "")
    value = unicodedata.normalize("NFKC", value)
    value = _WHITESPACE.sub(" ", value).strip()
    return value[:max_chars]


def _find_article_body(value: Any) -> str | None:
    if isinstance(value, dict):
        body = value.get("articleBody")
        if isinstance(body, str) and body.strip():
            return body
        for child in value.values():
            result = _find_article_body(child)
            if result:
                return result
    elif isinstance(value, list):
        for child in value:
            result = _find_article_body(child)
            if result:
                return result
    return None


def _extract_jsonld_body(document: str) -> str | None:
    for raw in _SCRIPT_JSONLD.findall(document):
        try:
            payload = json.loads(html.unescape(raw).strip())
        except (json.JSONDecodeError, TypeError):
            continue
        body = _find_article_body(payload)
        if body:
            return body
    return None


class _ParagraphParser(HTMLParser):
    """Conservative generic article-text fallback.

    It keeps paragraph text and ignores common chrome/noise containers. This is
    intentionally source-agnostic so Provider adapters do not depend on one
    site's CSS structure.
    """

    _ignored_tags = {"script", "style", "noscript", "svg", "nav", "header", "footer", "aside"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._in_p = 0
        self._parts: list[str] = []
        self.paragraphs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in self._ignored_tags:
            self._ignored_depth += 1
            return
        if self._ignored_depth == 0 and lowered == "p":
            self._in_p += 1
            if self._in_p == 1:
                self._parts = []

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in self._ignored_tags:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if self._ignored_depth == 0 and lowered == "p" and self._in_p:
            self._in_p -= 1
            if self._in_p == 0:
                paragraph = normalize_content(" ".join(self._parts))
                if len(_EFFECTIVE_CHAR.findall(paragraph)) >= 12:
                    self.paragraphs.append(paragraph)
                self._parts = []

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0 and self._in_p:
            self._parts.append(data)


def extract_content_from_html(
    document: str,
    *,
    min_chars: int = 80,
    max_chars: int = 30_000,
) -> str | None:
    """Extract article text without site-specific dependencies."""
    jsonld_body = _extract_jsonld_body(document)
    if jsonld_body:
        normalized = normalize_content(jsonld_body, max_chars=max_chars)
        if len(_EFFECTIVE_CHAR.findall(normalized)) >= min_chars:
            return normalized

    parser = _ParagraphParser()
    try:
        parser.feed(document)
        parser.close()
    except Exception:
        return None

    paragraphs: list[str] = []
    seen: set[str] = set()
    for paragraph in parser.paragraphs:
        key = paragraph.casefold()
        if key in seen:
            continue
        seen.add(key)
        paragraphs.append(paragraph)

    normalized = normalize_content("\n".join(paragraphs), max_chars=max_chars)
    if len(_EFFECTIVE_CHAR.findall(normalized)) < min_chars:
        return None
    return normalized


async def _fetch_content(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_chars: int,
) -> str | None:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            response = await client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if content_type and "html" not in content_type and "text/" not in content_type:
                return None
            # Avoid spending parser time on pathological multi-megabyte pages.
            document = response.text[:1_000_000]
            return extract_content_from_html(document, max_chars=max_chars)
        except (httpx.HTTPError, UnicodeError) as exc:
            last_error = exc
            if attempt == 0:
                await asyncio.sleep(0.25)
    return None


async def enrich_articles_with_content(
    articles: list[ArticleCandidate],
    *,
    timeout: float = 8.0,
    concurrency: int = 4,
    max_chars: int = 30_000,
) -> dict[str, int]:
    """Best-effort article-body enrichment.

    Failure is deliberately non-fatal: list metadata and summary remain useful
    even when a source page blocks crawling or changes its markup.
    """
    if not articles:
        return {"content_attempted": 0, "content_enriched": 0, "content_failed": 0}

    semaphore = asyncio.Semaphore(max(1, concurrency))
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; NewsCenter/0.2; +https://github.com/SombraLin/news_center)",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
    }

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        trust_env=False,
        headers=headers,
    ) as client:
        async def enrich(article: ArticleCandidate) -> bool:
            async with semaphore:
                content = await _fetch_content(client, article.url, max_chars=max_chars)
                if content:
                    article.content = content
                    return True
                return False

        results = await asyncio.gather(*(enrich(article) for article in articles))

    enriched = sum(1 for value in results if value)
    return {
        "content_attempted": len(articles),
        "content_enriched": enriched,
        "content_failed": len(articles) - enriched,
    }
