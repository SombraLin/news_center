from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.domain import ArticleCandidate
from app.providers import ProviderFetchResult, provider_registry
from app.services.ingestion import IngestionService


class FakeProvider:
    name = "fake"

    async def fetch(self, topic: str) -> ProviderFetchResult:
        article = ArticleCandidate(
            title=f"{topic} 测试新闻",
            source="测试源",
            url=f"https://example.com/{topic}",
            published_at=datetime.now(timezone.utc),
            summary="这是一条用于验证 V0.2 ingestion pipeline 的测试新闻摘要。",
            topic=topic,
            provider=self.name,
            canonical_url=f"https://example.com/{topic}",
        )
        return ProviderFetchResult(
            articles=[article],
            stats={"fetched": 1, "valid": 1},
        )


class FakeRepository:
    def __init__(self) -> None:
        self.saved: list[ArticleCandidate] = []

    def insert_batch(
        self,
        articles: list[ArticleCandidate],
        *,
        max_added: int | None = None,
    ) -> tuple[int, int]:
        selected = articles if max_added is None else articles[:max_added]
        self.saved.extend(selected)
        return len(selected), 0


def test_ingestion_service_is_provider_independent():
    async def scenario() -> None:
        provider_registry.register(FakeProvider())
        repository = FakeRepository()
        service = IngestionService(repository=repository)

        result = await service.ingest_topics(
            ["tech", "finance"],
            provider_name="fake",
            concurrency=2,
        )

        assert result.status == "success"
        assert result.total_added == 2
        assert result.total_skipped == 0
        assert set(result.details) == {"tech", "finance"}
        assert {article.provider for article in repository.saved} == {"fake"}

    asyncio.run(scenario())


def test_ingestion_service_deduplicates_requested_topics():
    async def scenario() -> None:
        provider_registry.register(FakeProvider())
        repository = FakeRepository()
        service = IngestionService(repository=repository)

        result = await service.ingest_topics(
            ["tech", "tech", "technology"],
            provider_name="fake",
        )

        assert result.status == "success"
        assert result.total_added == 1
        assert len(repository.saved) == 1
        assert repository.saved[0].topic == "tech"

    asyncio.run(scenario())
