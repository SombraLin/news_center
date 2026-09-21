from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.crawler import get_preset_topics
from app.database import count_articles_by_topic

router = APIRouter()


@router.get("/topics", summary="获取所有预设的新闻主题列表")
def list_preset_topics() -> dict[str, Any]:
    """返回系统预设主题，并附带 V0.2 article_topics 中的文章数量。"""
    topics = get_preset_topics()

    try:
        counts = count_articles_by_topic()
    except Exception:
        counts = {}

    results = [
        {
            "tag": item["tag"],
            "name": item["name"],
            "description": item["description"],
            "article_count": counts.get(item["tag"], 0),
        }
        for item in topics
    ]

    return {
        "total_topics": len(results),
        "topics": results,
    }
