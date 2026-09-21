from __future__ import annotations

from typing import Protocol

from app.domain import ArticleCandidate
from app.database import insert_news_batch


class NewsRepository(Protocol):
    def insert_batch(self, articles: list[ArticleCandidate]) -> tuple[int, int]:
        ...


class SqliteNewsRepository:
    """Repository facade over the current SQLite schema.

    V0.2 keeps the legacy news table intact. A later migration can replace this
    implementation without changing the ingestion service.
    """

    def insert_batch(self, articles: list[ArticleCandidate]) -> tuple[int, int]:
        return insert_news_batch(articles)


news_repository = SqliteNewsRepository()
