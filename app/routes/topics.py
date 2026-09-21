from __future__ import annotations

from typing import Any
from fastapi import APIRouter
from app.crawler import get_preset_topics
from app.database import connection

router = APIRouter()


@router.get("/topics", summary="获取所有预设的新闻主题列表")
def list_preset_topics() -> dict[str, Any]:
    """
    返回系统预设的全部新闻主题列表。
    调用方可直接在此获取可选的主题 tag，无需猜测或随意输入。
    """
    topics = get_preset_topics()

    # 附带统计本地数据库中已入库的各主题新闻数量
    counts: dict[str, int] = {}
    try:
        with connection() as db:
            rows = db.execute("SELECT tag, COUNT(*) AS count FROM news GROUP BY tag").fetchall()
            for r in rows:
                counts[r["tag"]] = r["count"]
    except Exception:
        pass

    results = []
    for item in topics:
        results.append({
            "tag": item["tag"],
            "name": item["name"],
            "description": item["description"],
            "article_count": counts.get(item["tag"], 0),
        })

    return {
        "total_topics": len(results),
        "topics": results,
    }
