from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Query
from app.crawler import normalize_tag
from app.database import get_news_by_id, query_news

router = APIRouter()


@router.get("/news", summary="查询已入库的新闻列表")
def get_news_list(
    tag: str | None = Query(None, description="主题分类过滤，例如 hot, tech, china 等"),
    keyword: str | None = Query(None, description="按标题或摘要关键词模糊匹配搜索"),
    limit: int = Query(20, ge=1, le=100, description="分页大小，默认 20，最大 100"),
    offset: int = Query(0, ge=0, description="分页偏移量，默认 0"),
) -> dict[str, Any]:
    """
    分页查询已抓取入库的新闻文字内容。
    - 支持按分类 `tag` 筛选
    - 支持按关键字 `keyword` 搜索
    - 结果按发布时间倒序排列
    """
    clean_tag = None
    if tag:
        try:
            clean_tag = normalize_tag(tag)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    items, total = query_news(
        tag=clean_tag,
        keyword=keyword,
        limit=limit,
        offset=offset,
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "count": len(items),
        "items": items,
    }


@router.get("/news/{news_id}", summary="获取单篇新闻详情")
def get_single_news(news_id: str) -> dict[str, Any]:
    """根据新闻唯一 ID 获取新闻详情"""
    item = get_news_by_id(news_id)
    if not item:
        raise HTTPException(status_code=404, detail="未找到对应新闻记录")
    return item
