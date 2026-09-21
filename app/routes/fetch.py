from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.crawler import fetch_zaker, normalize_tag
from app.database import insert_news_candidate

router = APIRouter()


class FetchRequest(BaseModel):
    tag: str | None = Field(None, description="要抓取的主题 tag，如 hot, tech。与 tags 传其一即可")
    tags: list[str] | None = Field(None, description="要批量抓取的多个主题 tag 列表")
    limit_per_tag: int = Field(10, ge=1, le=20, description="每个主题最多入库的新闻数量，默认 10，上限 20")


@router.post("/fetch", summary="手动触发新闻抓取与入库")
async def trigger_fetch(request: FetchRequest) -> dict[str, Any]:
    """
    手动触发新闻抓取。
    调用方可以指定单个主题 `tag` 或多个主题 `tags` 进行抓取。
    自动去重入库，并返回本次抓取结果和成功入库的文章。
    """
    target_tags: list[str] = []
    if request.tags:
        target_tags.extend(request.tags)
    elif request.tag:
        target_tags.append(request.tag)
    else:
        target_tags.append("hot")

    cleaned_tags: list[str] = []
    for t in target_tags:
        try:
            cleaned_tags.append(normalize_tag(t))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    total_added = 0
    total_skipped = 0
    results: dict[str, Any] = {}
    new_articles: list[dict[str, Any]] = []

    for ctag in cleaned_tags:
        try:
            candidates, stats = await fetch_zaker(
                ctag,
                timeout=settings.fetch_timeout_seconds,
            )
            tag_added = 0
            tag_skipped = 0
            for cand in candidates:
                if tag_added >= request.limit_per_tag:
                    break
                if insert_news_candidate(cand):
                    tag_added += 1
                    new_articles.append(cand.to_dict())
                else:
                    tag_skipped += 1

            total_added += tag_added
            total_skipped += tag_skipped
            results[ctag] = {
                "fetched": stats.get("fetched", 0),
                "valid": stats.get("valid", 0),
                "added": tag_added,
                "duplicate_history": tag_skipped,
            }
        except Exception as exc:
            results[ctag] = {"error": str(exc)}

    return {
        "success": True,
        "total_added": total_added,
        "total_skipped": total_skipped,
        "results": results,
        "newly_added_sample": new_articles[:10],
    }
