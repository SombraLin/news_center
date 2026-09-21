from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class ArticleCandidate:
    """Provider-independent news article candidate used by the ingestion pipeline."""

    title: str
    source: str
    url: str
    published_at: datetime | None
    summary: str
    topic: str
    language: str = "zh-CN"
    provider: str = "unknown"
    source_article_id: str | None = None
    canonical_url: str | None = None
    content: str | None = None
    image_url: str | None = None

    @property
    def tag(self) -> str:
        """Backward-compatible alias while the legacy news table still uses tag."""
        return self.topic

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.published_at:
            data["published_at"] = self.published_at.isoformat()
        return data


@dataclass(slots=True)
class TopicIngestionResult:
    topic: str
    provider: str
    fetched: int = 0
    valid: int = 0
    added: int = 0
    duplicate_history: int = 0
    provider_stats: dict[str, int] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class IngestionResult:
    status: str
    total_added: int = 0
    total_skipped: int = 0
    details: dict[str, TopicIngestionResult] = field(default_factory=dict)
    newly_added_sample: list[dict[str, Any]] = field(default_factory=list)

    @property
    def failures(self) -> dict[str, str]:
        return {
            topic: item.error
            for topic, item in self.details.items()
            if item.error is not None
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "total_added": self.total_added,
            "total_skipped": self.total_skipped,
            "details": {key: value.to_dict() for key, value in self.details.items()},
            "failures": self.failures,
            "newly_added_sample": self.newly_added_sample,
        }
