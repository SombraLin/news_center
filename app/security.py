from __future__ import annotations

import hmac

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.config import settings

_admin_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def admin_auth_enabled() -> bool:
    return bool(settings.admin_api_key)


async def require_admin_api_key(
    supplied_key: str | None = Security(_admin_key_header),
) -> None:
    """Protect mutation/management endpoints when an admin key is configured.

    Empty NEWS_CENTER_ADMIN_API_KEY intentionally keeps local/development
    deployments backward compatible.
    """
    expected = settings.admin_api_key
    if not expected:
        return

    if not supplied_key or not hmac.compare_digest(supplied_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少或无效的管理 API Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
