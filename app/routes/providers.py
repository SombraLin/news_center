from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.config import settings
from app.providers import provider_registry

router = APIRouter()


@router.get("/providers", summary="获取可用新闻 Provider")
def list_providers() -> dict[str, Any]:
    return {
        "default_provider": settings.default_provider,
        "total": len(provider_registry.names()),
        "providers": provider_registry.describe(),
    }
