from fastapi import APIRouter
from .topics import router as topics_router
from .news import router as news_router
from .fetch import router as fetch_router
from .scheduler_route import router as scheduler_router

api_router = APIRouter()
api_router.include_router(topics_router, tags=["主题列表"])
api_router.include_router(news_router, tags=["新闻查询"])
api_router.include_router(fetch_router, tags=["按需抓取"])
api_router.include_router(scheduler_router, tags=["调度控制"])

__all__ = ["api_router"]
