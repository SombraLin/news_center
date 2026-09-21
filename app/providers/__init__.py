from .base import NewsProvider, ProviderFetchResult
from .registry import ProviderRegistry, provider_registry
from .zaker import ZakerProvider

if "zaker" not in provider_registry.names():
    provider_registry.register(ZakerProvider())

__all__ = [
    "NewsProvider",
    "ProviderFetchResult",
    "ProviderRegistry",
    "provider_registry",
    "ZakerProvider",
]
