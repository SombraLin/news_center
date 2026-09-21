from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.crawler import normalize_tag
from app.services import ingestion_service

router = APIRouter()


class FetchRequest(BaseModel):
    tag: str | None = Field(None, description="要抓取的主题 tag，如 hot, tech。与 tags 传其一即可")
    tags: list[str] | None = Field(None, description="要批量抓取的多个主题 tag 列表")
    limit_per_tag: int = Field(10, ge=1, le=20, description="每个主题最多入库的新闻数量，默认 10，上限 20")
    provider: str = Field("zaker", description="新闻 Provider 名称，当前默认 zaker")


@router.post("/fetch", summary="手动触发新闻抓取与入库")
async def trigger_fetch(request: FetchRequest) -> dict[str, Any]:
    """手动触发新闻抓取，并通过统一 IngestionService 完成入库。"""
    if request.tags:
        target_tags = request.tags
    elif request.tag:
        target_tags = [request.tag]
    else:
        target_tags = ["hot"]

    try:
        cleaned_tags = [normalize_tag(tag) for tag in target_tags]
        result = await ingestion_service.ingest_topics(
            cleaned_tags,
            provider_name=request.provider,
            limit_per_topic=request.limit_per_tag,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = result.to_dict()
    return {
        "success": result.status != "failed",
        "status": result.status,
        "total_added": result.total_added,
        "total_skipped": result.total_skipped,
        "results": payload["details"],
        "newly_added_sample": result.newly_added_sample,
    }
