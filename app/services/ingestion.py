from __future__ import annotations

import asyncio
from collections.abc import Iterable

from app.crawler import normalize_tag
from app.domain import IngestionResult, TopicIngestionResult
from app.providers import ZakerProvider, provider_registry
from app.repositories import NewsRepository, news_repository

# Default registration lives at the application composition boundary.
if "zaker" not in provider_registry.names():
    provider_registry.register(ZakerProvider())


class IngestionService:
    """Coordinates provider fetches and persistence.

    API routes and schedulers should depend on this service instead of a
    provider-specific crawler.
    """

    def __init__(self, repository: NewsRepository = news_repository) -> None:
        self._repository = repository
        self._run_lock = asyncio.Lock()

    async def ingest_topics(
        self,
        topics: Iterable[str],
        *,
        provider_name: str = "zaker",
        limit_per_topic: int | None = None,
        concurrency: int = 4,
    ) -> IngestionResult:
        provider = provider_registry.get(provider_name)
        cleaned_topics = list(dict.fromkeys(normalize_tag(topic) for topic in topics))
        semaphore = asyncio.Semaphore(max(1, concurrency))

        async with self._run_lock:
            async def ingest_one(topic: str) -> tuple[str, TopicIngestionResult, list[dict]]:
                async with semaphore:
                    try:
                        fetched = await provider.fetch(topic)
                        articles = fetched.articles
                        added, skipped = self._repository.insert_batch(
                            articles,
                            max_added=limit_per_topic,
                        )
                        result = TopicIngestionResult(
                            topic=topic,
                            provider=provider.name,
                            fetched=fetched.stats.get("fetched", len(fetched.articles)),
                            valid=fetched.stats.get("valid", len(fetched.articles)),
                            added=added,
                            duplicate_history=skipped,
                            provider_stats=dict(fetched.stats),
                        )
                        sample = [item.to_dict() for item in articles[: min(added, 10)]]
                        return topic, result, sample
                    except Exception as exc:
                        return (
                            topic,
                            TopicIngestionResult(
                                topic=topic,
                                provider=provider.name,
                                error=str(exc),
                            ),
                            [],
                        )

            rows = await asyncio.gather(*(ingest_one(topic) for topic in cleaned_topics))

        details = {topic: item for topic, item, _ in rows}
        total_added = sum(item.added for item in details.values())
        total_skipped = sum(item.duplicate_history for item in details.values())
        failures = sum(1 for item in details.values() if item.error)

        if failures == len(details) and details:
            status = "failed"
        elif failures:
            status = "partial"
        else:
            status = "success"

        sample: list[dict] = []
        for _, _, items in rows:
            sample.extend(items)
            if len(sample) >= 10:
                break

        return IngestionResult(
            status=status,
            total_added=total_added,
            total_skipped=total_skipped,
            details=details,
            newly_added_sample=sample[:10],
        )


ingestion_service = IngestionService()
