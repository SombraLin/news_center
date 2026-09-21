from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


def _get_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes", "y", "on")


def _get_list(key: str, default: list[str]) -> list[str]:
    val = os.getenv(key)
    if not val:
        return default
    return [item.strip() for item in val.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    base_dir: Path = BASE_DIR
    host: str = os.getenv("NEWS_CENTER_HOST", "0.0.0.0").strip()
    port: int = int(os.getenv("NEWS_CENTER_PORT", "8100"))
    database_path: Path = Path(os.getenv("NEWS_CENTER_DB_PATH", str(BASE_DIR / "data" / "news.db")))
    fetch_timeout_seconds: float = float(os.getenv("NEWS_CENTER_FETCH_TIMEOUT_SECONDS", "12.0"))
    default_tags: list[str] = field(default_factory=lambda: _get_list("NEWS_CENTER_DEFAULT_TAGS", ["hot", "china", "world", "tech", "finance"]))
    fetch_interval_minutes: int = int(os.getenv("NEWS_CENTER_FETCH_INTERVAL_MINUTES", "30"))
    scheduler_autostart: bool = _get_bool("NEWS_CENTER_SCHEDULER_AUTOSTART", True)
    cleanup_days: int = int(os.getenv("NEWS_CENTER_CLEANUP_DAYS", "7"))
    default_provider: str = os.getenv("NEWS_CENTER_DEFAULT_PROVIDER", "zaker").strip() or "zaker"
    admin_api_key: str = os.getenv("NEWS_CENTER_ADMIN_API_KEY", "").strip()
    content_fetch_enabled: bool = _get_bool("NEWS_CENTER_CONTENT_FETCH_ENABLED", True)
    content_fetch_timeout_seconds: float = float(os.getenv("NEWS_CENTER_CONTENT_FETCH_TIMEOUT_SECONDS", "8.0"))
    content_fetch_concurrency: int = int(os.getenv("NEWS_CENTER_CONTENT_FETCH_CONCURRENCY", "4"))
    content_max_chars: int = int(os.getenv("NEWS_CENTER_CONTENT_MAX_CHARS", "30000"))


settings = Settings()
