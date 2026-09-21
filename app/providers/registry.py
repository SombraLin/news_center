from __future__ import annotations

from app.providers.base import NewsProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, NewsProvider] = {}

    def register(self, provider: NewsProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> NewsProvider:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise ValueError(f"未注册的新闻 Provider: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(self._providers.keys())


provider_registry = ProviderRegistry()
