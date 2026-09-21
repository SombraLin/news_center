from __future__ import annotations

from app.config import settings
from app.crawler import SUPPORTED_TAGS, fetch_zaker
from app.domain import ArticleCandidate
from app.providers.base import ProviderFetchResult
from app.providers.content import enrich_articles_with_content


class ZakerProvider:
    """Adapter around the legacy ZAKER crawler.

    The crawler remains unchanged during V0.2 migration. This adapter prevents
    FastAPI routes and scheduler code from depending on ZAKER directly.
    """

    name = "zaker"
    description = "ZAKER 新闻主题列表 + best-effort 正文提取"
    supports_content = True
    supported_topics = SUPPORTED_TAGS

    async def fetch(self, topic: str) -> ProviderFetchResult:
        candidates, stats = await fetch_zaker(
            topic,
            timeout=settings.fetch_timeout_seconds,
        )
        articles = [
            ArticleCandidate(
                title=item.title,
                source=item.source,
                url=item.url,
                published_at=item.published_at,
                summary=item.summary,
                topic=item.tag,
                language=item.language,
                provider=self.name,
                canonical_url=item.url,
            )
            for item in candidates
        ]

        if settings.content_fetch_enabled and articles:
            content_stats = await enrich_articles_with_content(
                articles,
                timeout=settings.content_fetch_timeout_seconds,
                concurrency=settings.content_fetch_concurrency,
                max_chars=settings.content_max_chars,
            )
            stats.update(content_stats)

        return ProviderFetchResult(articles=articles, stats=stats)
