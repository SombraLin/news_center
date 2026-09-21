from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Generator
from uuid import uuid4

from app.config import settings
from app.domain.identity import build_content_hash, canonicalize_url


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
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _article_identity(candidate: Any) -> tuple[str, str]:
    identity_url = getattr(candidate, "canonical_url", None) or candidate.url
    canonical_url = canonicalize_url(identity_url)
    content_hash = build_content_hash(candidate.title, candidate.summary)
    return canonical_url, content_hash


def _find_existing_article_id(
    db: sqlite3.Connection,
    canonical_url: str,
    content_hash: str,
    provider: str | None = None,
    source_article_id: str | None = None,
) -> str | None:
    if provider and source_article_id:
        row = db.execute(
            """
            SELECT id
            FROM articles
            WHERE canonical_url = ?
               OR content_hash = ?
               OR (provider = ? AND source_article_id = ?)
            LIMIT 1
            """,
            (canonical_url, content_hash, provider, source_article_id),
        ).fetchone()
    else:
        row = db.execute(
            """
            SELECT id
            FROM articles
            WHERE canonical_url = ? OR content_hash = ?
            LIMIT 1
            """,
            (canonical_url, content_hash),
        ).fetchone()
    return str(row["id"]) if row else None


def _upsert_topic(db: sqlite3.Connection, article_id: str, topic: str) -> None:
    db.execute(
        """
        INSERT OR IGNORE INTO article_topics (article_id, topic)
        VALUES (?, ?)
        """,
        (article_id, topic),
    )


def _migrate_legacy_news(db: sqlite3.Connection) -> None:
    legacy_exists = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='news'"
    ).fetchone()
    if not legacy_exists:
        return

    rows = db.execute(
        """
        SELECT id, tag, title, source, url, summary, published_at, fetched_at
        FROM news
        ORDER BY fetched_at ASC
        """
    ).fetchall()

    for row in rows:
        canonical_url = canonicalize_url(row["url"])
        content_hash = build_content_hash(row["title"], row["summary"] or "")
        existing_id = _find_existing_article_id(db, canonical_url, content_hash)

        if existing_id:
            _upsert_topic(db, existing_id, row["tag"])
            continue

        now = row["fetched_at"] or utc_now_iso()
        db.execute(
            """
            INSERT OR IGNORE INTO articles (
                id, provider, source_article_id, canonical_url, url,
                title, source, summary, content, image_url, language,
                published_at, fetched_at, updated_at, content_hash
            ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                "legacy",
                canonical_url,
                row["url"],
                row["title"],
                row["source"],
                row["summary"],
                "zh-CN",
                row["published_at"],
                now,
                now,
                content_hash,
            ),
        )
        article_id = _find_existing_article_id(db, canonical_url, content_hash)
        if article_id:
            _upsert_topic(db, article_id, row["tag"])


def _clean_search_query(value: str) -> str:
    return " ".join((value or "").strip().split())


def _fts_query(value: str) -> str:
    """Escape user input as a literal FTS5 phrase."""
    cleaned = _clean_search_query(value)
    return '"' + cleaned.replace('"', '""') + '"'


def _use_fts(value: str) -> bool:
    """Trigram search becomes useful at three or more visible characters."""
    return len(_clean_search_query(value)) >= 3


def _sync_fts_article(db: sqlite3.Connection, article_id: str) -> None:
    row = db.execute(
        """
        SELECT id, title, summary, source, content
        FROM articles
        WHERE id = ?
        """,
        (article_id,),
    ).fetchone()
    if not row:
        db.execute("DELETE FROM articles_fts WHERE article_id = ?", (article_id,))
        return

    db.execute("DELETE FROM articles_fts WHERE article_id = ?", (article_id,))
    db.execute(
        """
        INSERT INTO articles_fts (article_id, title, summary, source, content)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            row["id"],
            row["title"] or "",
            row["summary"] or "",
            row["source"] or "",
            row["content"] or "",
        ),
    )


def _rebuild_fts(db: sqlite3.Connection) -> None:
    """Reconcile the FTS index from authoritative article rows."""
    db.execute("DELETE FROM articles_fts")
    db.execute(
        """
        INSERT INTO articles_fts (article_id, title, summary, source, content)
        SELECT id, title, COALESCE(summary, ''), COALESCE(source, ''), COALESCE(content, '')
        FROM articles
        """
    )


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

            CREATE TABLE IF NOT EXISTS articles (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                source_article_id TEXT,
                canonical_url TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                source TEXT,
                summary TEXT,
                content TEXT,
                image_url TEXT,
                language TEXT NOT NULL DEFAULT 'zh-CN',
                published_at TEXT,
                fetched_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                content_hash TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_canonical_url
                ON articles(canonical_url);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_content_hash
                ON articles(content_hash);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_provider_source_id
                ON articles(provider, source_article_id)
                WHERE source_article_id IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_articles_published_at
                ON articles(published_at DESC);
            CREATE INDEX IF NOT EXISTS idx_articles_fetched_at
                ON articles(fetched_at DESC);
            CREATE INDEX IF NOT EXISTS idx_articles_provider
                ON articles(provider);

            CREATE TABLE IF NOT EXISTS article_topics (
                article_id TEXT NOT NULL,
                topic TEXT NOT NULL,
                PRIMARY KEY (article_id, topic),
                FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_article_topics_topic
                ON article_topics(topic);

            CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
                article_id UNINDEXED,
                title,
                summary,
                source,
                content,
                tokenize = 'trigram'
            );

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

        _migrate_legacy_news(db)
        _rebuild_fts(db)

        row = db.execute("SELECT id FROM scheduler_config WHERE id = 1").fetchone()
        if not row:
            initial_tags = json.dumps(settings.default_tags, ensure_ascii=False)
            now = utc_now_iso()
            db.execute(
                """
                INSERT INTO scheduler_config (
                    id, enabled, interval_minutes, tags_json,
                    last_run_at, last_status, last_result_json, updated_at
                ) VALUES (1, ?, ?, ?, NULL, NULL, NULL, ?)
                """,
                (
                    1 if settings.scheduler_autostart else 0,
                    settings.fetch_interval_minutes,
                    initial_tags,
                    now,
                ),
            )


def _insert_article(
    db: sqlite3.Connection,
    candidate: Any,
    now: str,
) -> tuple[bool, str]:
    canonical_url, content_hash = _article_identity(candidate)
    provider = getattr(candidate, "provider", "legacy")
    source_article_id = getattr(candidate, "source_article_id", None)
    existing_id = _find_existing_article_id(
        db,
        canonical_url,
        content_hash,
        provider=provider,
        source_article_id=source_article_id,
    )

    if existing_id:
        _upsert_topic(db, existing_id, candidate.tag)
        db.execute(
            """
            UPDATE articles
            SET
                updated_at = ?,
                content = COALESCE(NULLIF(content, ''), ?),
                image_url = COALESCE(NULLIF(image_url, ''), ?)
            WHERE id = ?
            """,
            (
                now,
                getattr(candidate, "content", None),
                getattr(candidate, "image_url", None),
                existing_id,
            ),
        )
        _sync_fts_article(db, existing_id)
        return False, existing_id

    article_id = uuid4().hex
    published_at = candidate.published_at.isoformat() if candidate.published_at else None
    db.execute(
        """
        INSERT INTO articles (
            id, provider, source_article_id, canonical_url, url,
            title, source, summary, content, image_url, language,
            published_at, fetched_at, updated_at, content_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            article_id,
            provider,
            source_article_id,
            canonical_url,
            candidate.url,
            candidate.title,
            candidate.source,
            candidate.summary,
            getattr(candidate, "content", None),
            getattr(candidate, "image_url", None),
            getattr(candidate, "language", "zh-CN"),
            published_at,
            now,
            now,
            content_hash,
        ),
    )
    _upsert_topic(db, article_id, candidate.tag)

    # V0.1 compatibility shadow write. This keeps rollback possible while
    # articles/article_topics are the authoritative V0.2 schema.
    db.execute(
        """
        INSERT OR IGNORE INTO news (
            id, tag, title, source, url, summary, published_at, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            article_id,
            candidate.tag,
            candidate.title,
            candidate.source,
            candidate.url,
            candidate.summary,
            published_at,
            now,
        ),
    )
    _sync_fts_article(db, article_id)
    return True, article_id


def insert_news_candidate(candidate: Any) -> bool:
    """Backward-compatible single item insert against the V0.2 article schema."""
    with connection() as db:
        added, _ = _insert_article(db, candidate, utc_now_iso())
        return added


def insert_news_batch(
    candidates: list[Any],
    max_added: int | None = None,
) -> tuple[int, int]:
    """Batch insert articles in one transaction.

    Existing articles are not duplicated; their topic association is merged.
    max_added limits newly created articles, preserving V0.1 /fetch semantics.
    """
    if not candidates:
        return 0, 0

    now = utc_now_iso()
    added = 0
    skipped = 0

    with connection() as db:
        for candidate in candidates:
            if max_added is not None and added >= max_added:
                break
            was_added, _ = _insert_article(db, candidate, now)
            if was_added:
                added += 1
            else:
                skipped += 1

    return added, skipped


def _row_to_news_item(row: sqlite3.Row, requested_tag: str | None = None) -> dict[str, Any]:
    topics = [topic for topic in (row["topics_csv"] or "").split(",") if topic]
    tag = requested_tag if requested_tag and requested_tag in topics else (topics[0] if topics else None)
    return {
        "id": row["id"],
        "tag": tag,
        "topics": topics,
        "title": row["title"],
        "source": row["source"],
        "url": row["url"],
        "canonical_url": row["canonical_url"],
        "summary": row["summary"],
        "content": row["content"],
        "image_url": row["image_url"],
        "language": row["language"],
        "provider": row["provider"],
        "published_at": row["published_at"],
        "fetched_at": row["fetched_at"],
        "updated_at": row["updated_at"],
    }


def query_news(
    tag: str | None = None,
    keyword: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    where_clauses: list[str] = []
    params: list[Any] = []

    if tag:
        where_clauses.append(
            "EXISTS (SELECT 1 FROM article_topics f WHERE f.article_id = a.id AND f.topic = ?)"
        )
        params.append(tag)

    if keyword:
        if _use_fts(keyword):
            where_clauses.append(
                "EXISTS (SELECT 1 FROM articles_fts f WHERE f.article_id = a.id AND articles_fts MATCH ?)"
            )
            params.append(_fts_query(keyword))
        else:
            where_clauses.append(
                "(a.title LIKE ? OR a.summary LIKE ? OR a.source LIKE ? OR a.content LIKE ?)"
            )
            short_query = f"%{_clean_search_query(keyword)}%"
            params.extend([short_query, short_query, short_query, short_query])

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    with connection() as db:
        total = db.execute(
            f"SELECT COUNT(*) AS total FROM articles a {where_sql}",
            params,
        ).fetchone()["total"]

        rows = db.execute(
            f"""
            SELECT
                a.id, a.provider, a.canonical_url, a.url, a.title, a.source,
                a.summary, a.content, a.image_url, a.language,
                a.published_at, a.fetched_at, a.updated_at,
                (
                    SELECT GROUP_CONCAT(topic, ',')
                    FROM (
                        SELECT topic
                        FROM article_topics t
                        WHERE t.article_id = a.id
                        ORDER BY topic
                    )
                ) AS topics_csv
            FROM articles a
            {where_sql}
            ORDER BY a.published_at DESC, a.fetched_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()

    return [_row_to_news_item(row, tag) for row in rows], total


def search_news(
    query: str,
    tag: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Search articles.

    Queries with three or more characters use FTS5/BM25. Shorter queries fall
    back to LIKE because the trigram tokenizer cannot reliably match them.
    """
    cleaned_query = _clean_search_query(query)
    if not cleaned_query:
        return [], 0

    if not _use_fts(cleaned_query):
        items, total = query_news(
            tag=tag,
            keyword=cleaned_query,
            limit=limit,
            offset=offset,
        )
        for item in items:
            item["relevance"] = None
            text = " ".join(
                str(value or "")
                for value in (item["title"], item["summary"], item["source"], item["content"])
            )
            index = text.casefold().find(cleaned_query.casefold())
            if index >= 0:
                start_at = max(0, index - 30)
                end_at = min(len(text), index + len(cleaned_query) + 50)
                item["match_snippet"] = text[start_at:end_at]
            else:
                item["match_snippet"] = item["summary"] or item["title"]
        return items, total

    fts_query = _fts_query(cleaned_query)
    where_tag = ""
    params: list[Any] = [fts_query]

    if tag:
        where_tag = """
            AND EXISTS (
                SELECT 1 FROM article_topics tf
                WHERE tf.article_id = a.id AND tf.topic = ?
            )
        """
        params.append(tag)

    with connection() as db:
        total = db.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM articles_fts f
            JOIN articles a ON a.id = f.article_id
            WHERE articles_fts MATCH ?
            {where_tag}
            """,
            params,
        ).fetchone()["total"]

        rows = db.execute(
            f"""
            SELECT
                a.id, a.provider, a.canonical_url, a.url, a.title, a.source,
                a.summary, a.content, a.image_url, a.language,
                a.published_at, a.fetched_at, a.updated_at,
                bm25(articles_fts, 8.0, 3.0, 1.5, 1.0, 2.0) AS relevance,
                snippet(articles_fts, -1, '<mark>', '</mark>', '…', 18) AS match_snippet,
                (
                    SELECT GROUP_CONCAT(topic, ',')
                    FROM (
                        SELECT topic
                        FROM article_topics t
                        WHERE t.article_id = a.id
                        ORDER BY topic
                    )
                ) AS topics_csv
            FROM articles_fts f
            JOIN articles a ON a.id = f.article_id
            WHERE articles_fts MATCH ?
            {where_tag}
            ORDER BY relevance ASC, a.published_at DESC, a.fetched_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()

    items = []
    for row in rows:
        item = _row_to_news_item(row, tag)
        item["relevance"] = float(row["relevance"])
        item["match_snippet"] = row["match_snippet"]
        items.append(item)
    return items, total


def get_news_by_id(news_id: str) -> dict[str, Any] | None:
    with connection() as db:
        row = db.execute(
            """
            SELECT
                a.id, a.provider, a.canonical_url, a.url, a.title, a.source,
                a.summary, a.content, a.image_url, a.language,
                a.published_at, a.fetched_at, a.updated_at,
                (
                    SELECT GROUP_CONCAT(topic, ',')
                    FROM (
                        SELECT topic
                        FROM article_topics t
                        WHERE t.article_id = a.id
                        ORDER BY topic
                    )
                ) AS topics_csv
            FROM articles a
            WHERE a.id = ?
            """,
            (news_id,),
        ).fetchone()

    return _row_to_news_item(row) if row else None


def count_articles_by_topic() -> dict[str, int]:
    with connection() as db:
        rows = db.execute(
            """
            SELECT topic, COUNT(*) AS count
            FROM article_topics
            GROUP BY topic
            """
        ).fetchall()
    return {str(row["topic"]): int(row["count"]) for row in rows}


def cleanup_old_news(days: int) -> int:
    if days <= 0:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with connection() as db:
        stale_ids = [
            row["id"]
            for row in db.execute(
                """
                SELECT id FROM articles
                WHERE published_at < ?
                   OR (published_at IS NULL AND fetched_at < ?)
                """,
                (cutoff, cutoff),
            ).fetchall()
        ]
        if stale_ids:
            db.executemany(
                "DELETE FROM articles_fts WHERE article_id = ?",
                [(article_id,) for article_id in stale_ids],
            )

        cursor = db.execute(
            """
            DELETE FROM articles
            WHERE published_at < ?
               OR (published_at IS NULL AND fetched_at < ?)
            """,
            (cutoff, cutoff),
        )
        deleted = cursor.rowcount
        db.execute(
            """
            DELETE FROM news
            WHERE published_at < ?
               OR (published_at IS NULL AND fetched_at < ?)
            """,
            (cutoff, cutoff),
        )
        return deleted


def get_scheduler_config() -> dict[str, Any]:
    with connection() as db:
        row = db.execute(
            """
            SELECT enabled, interval_minutes, tags_json, last_run_at,
                   last_status, last_result_json, updated_at
            FROM scheduler_config
            WHERE id = 1
            """
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
            (
                1 if new_enabled else 0,
                new_interval,
                json.dumps(new_tags, ensure_ascii=False),
                now,
            ),
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
