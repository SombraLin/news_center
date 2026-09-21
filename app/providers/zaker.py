from __future__ import annotations

from app.config import settings
from app.crawler import fetch_zaker
from app.domain import ArticleCandidate
from app.providers.base import ProviderFetchResult


class ZakerProvider:
    """Adapter around the legacy ZAKER crawler.

    The crawler remains unchanged during V0.2 migration. This adapter prevents
    FastAPI routes and scheduler code from depending on ZAKER directly.
    """

    name = "zaker"

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
        return ProviderFetchResult(articles=articles, stats=stats)
