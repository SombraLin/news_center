from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.domain import ArticleCandidate


@dataclass(slots=True)
class ProviderFetchResult:
    articles: list[ArticleCandidate]
    stats: dict[str, int] = field(default_factory=dict)


class NewsProvider(Protocol):
    """Contract implemented by every news source adapter."""

    name: str

    async def fetch(self, topic: str) -> ProviderFetchResult:
        ...
