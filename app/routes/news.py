from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.crawler import normalize_tag
from app.database import get_news_by_id, query_news, search_news

router = APIRouter()


@router.get("/news", summary="查询已入库的新闻列表")
def get_news_list(
    tag: str | None = Query(None, description="主题分类过滤，例如 hot, tech, china 等"),
    keyword: str | None = Query(None, description="全文关键词搜索；内部使用 SQLite FTS5"),
    limit: int = Query(20, ge=1, le=100, description="分页大小，默认 20，最大 100"),
    offset: int = Query(0, ge=0, description="分页偏移量，默认 0"),
) -> dict[str, Any]:
    """分页查询新闻。

    - tag: 按主题过滤
    - keyword: 使用 FTS5 全文索引搜索 title / summary / source / content
    - 无 keyword 时按发布时间倒序
    """
    clean_tag = None
    if tag:
        try:
            clean_tag = normalize_tag(tag)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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


@router.get("/news/search", summary="全文搜索新闻")
def search_news_endpoint(
    q: str = Query(..., min_length=1, max_length=200, description="全文搜索关键词"),
    tag: str | None = Query(None, description="可选主题过滤，例如 tech, finance"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """使用 SQLite FTS5 + BM25 相关性排序进行新闻全文搜索。"""
    clean_tag = None
    if tag:
        try:
            clean_tag = normalize_tag(tag)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    items, total = search_news(
        query=q,
        tag=clean_tag,
        limit=limit,
        offset=offset,
    )
    return {
        "query": q,
        "tag": clean_tag,
        "total": total,
        "limit": limit,
        "offset": offset,
        "count": len(items),
        "items": items,
    }


@router.get("/news/{news_id}", summary="获取单篇新闻详情")
def get_single_news(news_id: str) -> dict[str, Any]:
    item = get_news_by_id(news_id)
    if not item:
        raise HTTPException(status_code=404, detail="未找到对应新闻记录")
    return item
