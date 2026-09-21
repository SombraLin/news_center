from __future__ import annotations

from typing import Any

from app.providers.base import NewsProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, NewsProvider] = {}

    def register(self, provider: NewsProvider) -> None:
        name = str(provider.name).strip()
        if not name:
            raise ValueError("Provider name 不能为空")
        self._providers[name] = provider

    def get(self, name: str) -> NewsProvider:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise ValueError(f"未注册的新闻 Provider: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers.keys()))

    def describe(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for name in self.names():
            provider = self._providers[name]
            topics = getattr(provider, "supported_topics", ())
            results.append(
                {
                    "name": name,
                    "description": getattr(provider, "description", ""),
                    "supports_content": bool(getattr(provider, "supports_content", False)),
                    "supported_topics": list(topics),
                }
            )
        return results


provider_registry = ProviderRegistry()
