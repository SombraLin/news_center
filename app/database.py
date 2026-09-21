from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Generator
from uuid import uuid4

from app.config import settings


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db_path() -> Path:
    p = settings.database_path
    if not p.is_absolute():
        p = settings.base_dir / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@contextlib.contextmanager
def connection() -> Generator[sqlite3.Connection, None, None]:
    db_file = get_db_path()
    conn = sqlite3.connect(str(db_file), timeout=15.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS news (
                id TEXT PRIMARY KEY,
                tag TEXT NOT NULL,
                title TEXT NOT NULL,
                source TEXT,
                url TEXT NOT NULL UNIQUE,
                summary TEXT,
                published_at TEXT,
                fetched_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_news_tag ON news(tag);
            CREATE INDEX IF NOT EXISTS idx_news_published_at ON news(published_at DESC);
            CREATE INDEX IF NOT EXISTS idx_news_fetched_at ON news(fetched_at DESC);

            CREATE TABLE IF NOT EXISTS scheduler_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                enabled INTEGER NOT NULL DEFAULT 1,
                interval_minutes INTEGER NOT NULL DEFAULT 30,
                tags_json TEXT NOT NULL,
                last_run_at TEXT,
                last_status TEXT,
                last_result_json TEXT,
                updated_at TEXT NOT NULL
            );
            """
        )

        # 确保 scheduler_config 存在初始化记录
        row = db.execute("SELECT id FROM scheduler_config WHERE id = 1").fetchone()
        if not row:
            initial_tags = json.dumps(settings.default_tags, ensure_ascii=False)
            now = utc_now_iso()
            db.execute(
                """
                INSERT INTO scheduler_config (
                    id, enabled, interval_minutes, tags_json, last_run_at, last_status, last_result_json, updated_at
                ) VALUES (1, ?, ?, ?, NULL, NULL, NULL, ?)
                """,
                (1 if settings.scheduler_autostart else 0, settings.fetch_interval_minutes, initial_tags, now),
            )


def insert_news_candidate(candidate: Any) -> bool:
    """插入单条候选新闻，若 url 重复则忽略并返回 False，插入成功返回 True"""
    now = utc_now_iso()
    pub = candidate.published_at.isoformat() if candidate.published_at else None
    news_id = uuid4().hex
    with connection() as db:
        cursor = db.execute(
            """
            INSERT OR IGNORE INTO news (id, tag, title, source, url, summary, published_at, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (news_id, candidate.tag, candidate.title, candidate.source, candidate.url, candidate.summary, pub, now),
        )
        return cursor.rowcount > 0


def insert_news_batch(candidates: list[Any]) -> tuple[int, int]:
    """批量插入新闻，使用单事务写入，返回 (新增数量, 重复跳过数量)。"""
    if not candidates:
        return 0, 0

    now = utc_now_iso()
    added = 0

    with connection() as db:
        for candidate in candidates:
            pub = candidate.published_at.isoformat() if candidate.published_at else None
            cursor = db.execute(
                """
                INSERT OR IGNORE INTO news (id, tag, title, source, url, summary, published_at, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid4().hex,
                    candidate.tag,
                    candidate.title,
                    candidate.source,
                    candidate.url,
                    candidate.summary,
                    pub,
                    now,
                ),
            )
            added += max(cursor.rowcount, 0)

    return added, len(candidates) - added


def query_news(
    tag: str | None = None,
    keyword: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """查询新闻列表，支持分类筛选和关键词模糊搜索，按发布时间倒序排列"""
    where_clauses: list[str] = []
    params: list[Any] = []

    if tag:
        where_clauses.append("tag = ?")
        params.append(tag)

    if keyword:
        where_clauses.append("(title LIKE ? OR summary LIKE ? OR source LIKE ?)")
        kw = f"%{keyword.strip()}%"
        params.extend([kw, kw, kw])

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    with connection() as db:
        count_cursor = db.execute(f"SELECT COUNT(*) AS total FROM news {where_sql}", params)
        total = count_cursor.fetchone()["total"]

        query_sql = f"""
            SELECT id, tag, title, source, url, summary, published_at, fetched_at
            FROM news
            {where_sql}
            ORDER BY published_at DESC, fetched_at DESC
            LIMIT ? OFFSET ?
        """
        rows = db.execute(query_sql, [*params, limit, offset]).fetchall()
        items = [dict(r) for r in rows]

    return items, total


def get_news_by_id(news_id: str) -> dict[str, Any] | None:
    with connection() as db:
        row = db.execute(
            "SELECT id, tag, title, source, url, summary, published_at, fetched_at FROM news WHERE id = ?",
            (news_id,),
        ).fetchone()
        return dict(row) if row else None


def cleanup_old_news(days: int) -> int:
    """清理发布时间早于 N 天前的旧新闻"""
    if days <= 0:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with connection() as db:
        cursor = db.execute("DELETE FROM news WHERE published_at < ? OR (published_at IS NULL AND fetched_at < ?)", (cutoff, cutoff))
        return cursor.rowcount


def get_scheduler_config() -> dict[str, Any]:
    with connection() as db:
        row = db.execute(
            "SELECT enabled, interval_minutes, tags_json, last_run_at, last_status, last_result_json, updated_at FROM scheduler_config WHERE id = 1"
        ).fetchone()
        if not row:
            init_db()
            return get_scheduler_config()

        tags = json.loads(row["tags_json"] or "[]")
        last_result = json.loads(row["last_result_json"]) if row["last_result_json"] else None
        return {
            "enabled": bool(row["enabled"]),
            "interval_minutes": int(row["interval_minutes"]),
            "tags": tags,
            "last_run_at": row["last_run_at"],
            "last_status": row["last_status"],
            "last_result": last_result,
            "updated_at": row["updated_at"],
        }


def update_scheduler_config(
    enabled: bool | None = None,
    interval_minutes: int | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    current = get_scheduler_config()
    new_enabled = current["enabled"] if enabled is None else enabled
    new_interval = current["interval_minutes"] if interval_minutes is None else max(1, interval_minutes)
    new_tags = current["tags"] if tags is None else tags
    now = utc_now_iso()

    with connection() as db:
        db.execute(
            """
            UPDATE scheduler_config
            SET enabled = ?, interval_minutes = ?, tags_json = ?, updated_at = ?
            WHERE id = 1
            """,
            (1 if new_enabled else 0, new_interval, json.dumps(new_tags, ensure_ascii=False), now),
        )

    return get_scheduler_config()


def record_scheduler_run(status: str, result_data: dict[str, Any]) -> None:
    now = utc_now_iso()
    with connection() as db:
        db.execute(
            """
            UPDATE scheduler_config
            SET last_run_at = ?, last_status = ?, last_result_json = ?, updated_at = ?
            WHERE id = 1
            """,
            (now, status, json.dumps(result_data, ensure_ascii=False), now),
        )
