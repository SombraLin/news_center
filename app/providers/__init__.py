from .base import NewsProvider, ProviderFetchResult
from .registry import ProviderRegistry, provider_registry
from .zaker import ZakerProvider

__all__ = [
    "NewsProvider",
    "ProviderFetchResult",
    "ProviderRegistry",
    "provider_registry",
    "ZakerProvider",
]
