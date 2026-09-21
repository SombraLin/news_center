from __future__ import annotations

import contextlib
import logging
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.config import settings
from app.database import init_db
from app.routes import api_router
from app.scheduler import news_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("news_center")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("正在初始化 news_center 服务...")
    # 1. 初始化数据库
    init_db()
    logger.info("SQLite 数据库初始化完成: %s", settings.database_path)

    # 2. 启动后台定时调度器
    if settings.scheduler_autostart:
        news_scheduler.start()

    yield

    # 优雅停机
    logger.info("正在关闭 news_center 服务...")
    news_scheduler.shutdown()
    logger.info("news_center 服务已安全退出")


app = FastAPI(
    title="News Center API",
    description="轻量级新闻抓取与内容中心服务。支持多主题定时轮询、按需检索与即时抓取。",
    version="0.2.0",
    lifespan=lifespan,
)

# 允许跨域，方便前端或调用方直接访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/", summary="服务健康状态与信息")
def index() -> dict[str, str]:
    return {
        "service": "news_center",
        "status": "running",
        "docs_url": "/docs",
        "topics_url": "/topics",
        "news_url": "/news",
        "search_url": "/news/search?q=关键词",
        "providers_url": "/providers",
        "liveness_url": "/health/live",
        "readiness_url": "/health/ready",
    }


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
