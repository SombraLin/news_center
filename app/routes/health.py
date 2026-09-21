from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import check_database_readiness
from app.providers import provider_registry
from app.security import admin_auth_enabled

router = APIRouter()


@router.get("/health/live", summary="Liveness 探针")
def health_live() -> dict[str, Any]:
    """Process-level liveness. Does not call external news sources."""
    return {
        "status": "alive",
        "service": "news_center",
        "version": "0.2.0",
    }


@router.get("/health/ready", summary="Readiness 探针")
def health_ready():
    """Check local dependencies required to serve API traffic."""
    checks: dict[str, Any] = {}
    ready = True

    try:
        db_status = check_database_readiness()
        checks["database"] = db_status
        ready = ready and bool(db_status.get("ready"))
    except Exception as exc:
        checks["database"] = {"ready": False, "error": str(exc)}
        ready = False

    providers = provider_registry.names()
    provider_ready = settings.default_provider in providers and bool(providers)
    checks["providers"] = {
        "ready": provider_ready,
        "default": settings.default_provider,
        "registered": list(providers),
    }
    ready = ready and provider_ready

    payload = {
        "status": "ready" if ready else "not_ready",
        "service": "news_center",
        "checks": checks,
        "admin_auth_enabled": admin_auth_enabled(),
    }
    if ready:
        return payload
    return JSONResponse(status_code=503, content=payload)
