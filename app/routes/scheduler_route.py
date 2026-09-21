from __future__ import annotations

import asyncio
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.crawler import normalize_tag
from app.database import update_scheduler_config
from app.scheduler import news_scheduler

router = APIRouter()


class SchedulerConfigUpdate(BaseModel):
    enabled: bool | None = Field(None, description="是否启用定时抓取")
    interval_minutes: int | None = Field(None, ge=1, le=1440, description="抓取轮询间隔（分钟），范围 1-1440")
    tags: list[str] | None = Field(None, description="定时抓取的目标主题列表，如 ['hot', 'tech', 'finance']")


@router.get("/scheduler/status", summary="查看定时调度器状态")
def get_scheduler_status() -> dict[str, Any]:
    """返回调度器运行状态、下次抓取时间与最近一轮执行概况"""
    return news_scheduler.get_status()


@router.post("/scheduler/config", summary="更新定时调度配置")
async def update_config(body: SchedulerConfigUpdate) -> dict[str, Any]:
    """
    修改定时调度参数（热更新生效，持久化存入数据库）。
    - 支持启停调度
    - 支持调整分钟间隔
    - 支持修改定时抓取的主题 tag 列表
    """
    cleaned_tags = None
    if body.tags is not None:
        cleaned_tags = []
        for t in body.tags:
            try:
                cleaned_tags.append(normalize_tag(t))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
        if not cleaned_tags:
            raise HTTPException(status_code=400, detail="主题列表不能为空")

    # 更新数据库配置
    new_cfg = update_scheduler_config(
        enabled=body.enabled,
        interval_minutes=body.interval_minutes,
        tags=cleaned_tags,
    )

    # 同步动态调整运行中的调度器
    if body.interval_minutes is not None:
        news_scheduler.update_job_interval(body.interval_minutes)

    if body.enabled is not None:
        if body.enabled:
            news_scheduler.resume()
        else:
            news_scheduler.pause()

    return {
        "success": True,
        "config": new_cfg,
        "scheduler_status": news_scheduler.get_status(),
    }


@router.post("/scheduler/run", summary="立即触发一轮完整定时抓取")
async def trigger_scheduler_run() -> dict[str, Any]:
    """立即在当前轮次触发全量定时抓取任务"""
    result = await news_scheduler.trigger_now()
    return {
        "success": True,
        "result": result,
    }
