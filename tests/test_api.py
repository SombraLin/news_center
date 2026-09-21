from __future__ import annotations

import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# 设置测试环境变量，使用临时测试库
os.environ["NEWS_CENTER_DB_PATH"] = "./data/test_news.db"
os.environ["NEWS_CENTER_SCHEDULER_AUTOSTART"] = "false"

from app.crawler import (
    TOPIC_DEFINITIONS,
    Candidate,
    clean_summary,
    get_preset_topics,
    normalize_tag,
    parse_publish_time,
)
from app.database import (
    cleanup_old_news,
    connection,
    get_db_path,
    get_news_by_id,
    get_scheduler_config,
    init_db,
    insert_news_batch,
    insert_news_candidate,
    query_news,
    update_scheduler_config,
)
from app.main import app


@pytest.fixture(autouse=True)
def setup_test_db():
    db_file = get_db_path()
    if db_file.exists():
        db_file.unlink()
    init_db()
    yield
    if db_file.exists():
        db_file.unlink()


def test_preset_topics_metadata():
    """验证预设分类列表是否完整（10个主题）并且包含中文名称与描述"""
    topics = get_preset_topics()
    assert len(topics) == 10
    tags = [t["tag"] for t in topics]
    assert "hot" in tags
    assert "china" in tags
    assert "world" in tags
    assert "tech" in tags
    assert "finance" in tags
    assert "auto" in tags
    assert "sports" in tags
    assert "entertainment" in tags
    assert "military" in tags
    assert "internet" in tags

    for t in topics:
        assert len(t["name"]) > 0
        assert len(t["description"]) > 0


def test_tag_normalization():
    assert normalize_tag("hot") == "hot"
    assert normalize_tag("technology") == "tech"
    assert normalize_tag("sport") == "sports"
    assert normalize_tag("domestic") == "china"
    assert normalize_tag("international") == "world"

    with pytest.raises(ValueError):
        normalize_tag("unknown_invalid_category")


def test_clean_summary():
    raw = "<p>这是一条<b>重要</b>新闻&nbsp;&amp;&nbsp;测试。</p>"
    cleaned = clean_summary(raw)
    assert "<" not in cleaned
    assert "这是" in cleaned


def test_parse_publish_time():
    t1 = parse_publish_time("2026-09-21 11:40:00")
    assert t1 is not None
    assert t1.tzinfo is not None

    t2 = parse_publish_time(1789958379)
    assert t2 is not None


def test_database_insert_and_deduplication():
    cand1 = Candidate(
        title="测试新闻1",
        source="新华社",
        url="https://example.com/news/1",
        published_at=parse_publish_time("2026-09-21 10:00:00"),
        summary="这是测试新闻的摘要内容1",
        tag="tech",
    )
    cand2 = Candidate(
        title="测试新闻2",
        source="央视网",
        url="https://example.com/news/2",
        published_at=parse_publish_time("2026-09-21 10:30:00"),
        summary="这是测试新闻的摘要内容2",
        tag="finance",
    )

    added, skipped = insert_news_batch([cand1, cand2])
    assert added == 2
    assert skipped == 0

    # 再次插入相同的 cand1，应该被去重忽略
    added2, skipped2 = insert_news_batch([cand1])
    assert added2 == 0
    assert skipped2 == 1

    # 同一 URL 的新闻可以追加新的 topic，而不会重复创建 article
    cand1_finance = Candidate(
        title="测试新闻1",
        source="新华社",
        url="https://example.com/news/1?utm_source=test",
        published_at=parse_publish_time("2026-09-21 10:00:00"),
        summary="这是测试新闻的摘要内容1",
        tag="finance",
    )
    added3, skipped3 = insert_news_batch([cand1_finance])
    assert added3 == 0
    assert skipped3 == 1

    # 查询验证
    items, total = query_news(tag="tech")
    assert total == 1
    assert items[0]["title"] == "测试新闻1"
    assert set(items[0]["topics"]) == {"tech", "finance"}

    finance_items, finance_total = query_news(tag="finance")
    assert finance_total == 2
    assert any(item["title"] == "测试新闻1" for item in finance_items)

    # 关键字模糊查询验证
    items_kw, total_kw = query_news(keyword="央视网")
    assert total_kw == 1
    assert items_kw[0]["source"] == "央视网"



def test_legacy_news_migration_is_idempotent():
    with connection() as db:
        db.execute(
            """
            INSERT INTO news (id, tag, title, source, url, summary, published_at, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-1",
                "world",
                "旧版新闻迁移测试",
                "旧版来源",
                "https://example.com/legacy/1?utm_source=old",
                "这是一条用于验证旧版 news 表迁移的新闻摘要。",
                "2026-09-21T02:00:00+00:00",
                "2026-09-21T02:05:00+00:00",
            ),
        )

    init_db()
    first_items, first_total = query_news(tag="world")
    assert first_total == 1
    assert first_items[0]["id"] == "legacy-1"
    assert first_items[0]["canonical_url"] == "https://example.com/legacy/1"

    # Re-running initialization must not duplicate migrated articles/topics.
    init_db()
    second_items, second_total = query_news(tag="world")
    assert second_total == 1
    assert second_items[0]["id"] == "legacy-1"


def test_v02_insert_shadow_writes_legacy_news_table():
    candidate = Candidate(
        title="回滚兼容测试",
        source="测试来源",
        url="https://example.com/rollback/1",
        published_at=parse_publish_time("2026-09-21 11:20:00"),
        summary="这是一条用于验证 V0.1 回滚兼容影子写入的新闻摘要。",
        tag="tech",
    )
    assert insert_news_candidate(candidate) is True

    with connection() as db:
        row = db.execute(
            "SELECT tag, title FROM news WHERE url = ?",
            (candidate.url,),
        ).fetchone()

    assert row is not None
    assert row["tag"] == "tech"
    assert row["title"] == "回滚兼容测试"


def test_scheduler_config_persistence():
    cfg = get_scheduler_config()
    assert cfg["interval_minutes"] == 30

    update_scheduler_config(interval_minutes=15, enabled=False, tags=["hot", "tech"])
    new_cfg = get_scheduler_config()
    assert new_cfg["interval_minutes"] == 15
    assert new_cfg["enabled"] is False
    assert new_cfg["tags"] == ["hot", "tech"]


def test_api_routes():
    client = TestClient(app)

    # 1. 测试 GET /
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert res_root.json()["service"] == "news_center"

    # 2. 测试 GET /topics
    res_topics = client.get("/topics")
    assert res_topics.status_code == 200
    data = res_topics.json()
    assert data["total_topics"] == 10
    assert any(t["tag"] == "tech" and t["name"] == "科技" for t in data["topics"])

    # 3. 插入测试数据并测试 GET /news
    cand = Candidate(
        title="科技前沿快讯",
        source="科技日报",
        url="https://example.com/tech/1",
        published_at=parse_publish_time("2026-09-21 11:00:00"),
        summary="这是一篇科技快讯摘要",
        tag="tech",
    )
    insert_news_candidate(cand)

    res_news = client.get("/news?tag=tech")
    assert res_news.status_code == 200
    news_data = res_news.json()
    assert news_data["total"] >= 1
    news_id = news_data["items"][0]["id"]

    # 4. 测试 GET /news/{id}
    res_single = client.get(f"/news/{news_id}")
    assert res_single.status_code == 200
    assert res_single.json()["title"] == "科技前沿快讯"

    # 5. 测试 GET /scheduler/status
    res_status = client.get("/scheduler/status")
    assert res_status.status_code == 200

    # 6. 测试 POST /scheduler/config
    res_update = client.post("/scheduler/config", json={"interval_minutes": 20, "tags": ["china", "world"]})
    assert res_update.status_code == 200
    assert res_update.json()["config"]["interval_minutes"] == 20
