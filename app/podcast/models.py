from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class QwenCompletion:
    content: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None


@dataclass(slots=True)
class PodcastScriptResult:
    script: str
    model: str
    received_count: int
    selected_count: int
    source_titles: list[str]
    usage: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "script": self.script,
            "model": self.model,
            "received_count": self.received_count,
            "selected_count": self.selected_count,
            "source_titles": self.source_titles,
            "usage": self.usage,
            "request_id": self.request_id,
        }
