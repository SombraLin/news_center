from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.crawler import fetch_zaker, normalize_tag
from app.database import (
    cleanup_old_news,
    get_scheduler_config,
    insert_news_batch,
    record_scheduler_run,
    update_scheduler_config,
)

logger = logging.getLogger("news_center.scheduler")

JOB_ID = "news_center_fetch_job"


async def fetch_news_job() -> dict[str, Any]:
    """定时任务核心执行函数：按配置的 tags 进行轮询抓取与入库"""
    cfg = get_scheduler_config()
    if not cfg["enabled"]:
        logger.info("调度任务触发，但当前配置为禁用状态，已跳过")
        return {"status": "skipped", "reason": "scheduler_disabled"}

    tags = cfg.get("tags") or settings.default_tags
    logger.info("开始执行定时新闻抓取，目标主题列表: %s", tags)

    summary_stats: dict[str, Any] = {}
    total_added = 0
    total_skipped = 0
    failures: dict[str, str] = {}

    for tag in tags:
        try:
            norm_tag = normalize_tag(tag)
            candidates, stats = await fetch_zaker(
                norm_tag,
                timeout=settings.fetch_timeout_seconds,
            )
            added, skipped = insert_news_batch(candidates)
            total_added += added
            total_skipped += skipped
            summary_stats[norm_tag] = {
                "fetched": stats.get("fetched", 0),
                "valid": stats.get("valid", 0),
                "added": added,
                "duplicate_history": skipped,
            }
        except Exception as exc:
            logger.warning("抓取主题 [%s] 发生异常: %s", tag, exc)
            failures[tag] = str(exc)

    # 清理过期新闻（如配置天数大于0）
    cleaned_count = 0
    if settings.cleanup_days > 0:
        try:
            cleaned_count = cleanup_old_news(settings.cleanup_days)
            if cleaned_count > 0:
                logger.info("已自动清理 %d 条过期新闻（超过 %d 天）", cleaned_count, settings.cleanup_days)
        except Exception as exc:
            logger.warning("清理过期新闻异常: %s", exc)

    status = "failed" if failures and not summary_stats else ("partial" if failures else "success")
    run_result = {
        "status": status,
        "total_added": total_added,
        "total_skipped": total_skipped,
        "cleaned_count": cleaned_count,
        "details": summary_stats,
        "failures": failures,
    }

    try:
        record_scheduler_run(status, run_result)
    except Exception as exc:
        logger.error("记录调度执行结果失败: %s", exc)

    logger.info("定时抓取完成: 新增 %d 篇，跳过历史重复 %d 篇，状态 %s", total_added, total_skipped, status)
    return run_result


class NewsScheduler:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self) -> None:
        if self._is_running:
            return

        cfg = get_scheduler_config()
        interval = cfg.get("interval_minutes", settings.fetch_interval_minutes)
        trigger = IntervalTrigger(minutes=max(1, interval))

        self._scheduler.add_job(
            fetch_news_job,
            trigger=trigger,
            id=JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        self._scheduler.start()
        self._is_running = True
        logger.info("新闻定时抓取调度器已启动，轮询周期: %d 分钟", interval)

        # 如果配置为暂停，则暂停 job
        if not cfg.get("enabled", True):
            self._scheduler.pause_job(JOB_ID)
            logger.info("调度器已根据配置暂停抓取任务")

    def shutdown(self) -> None:
        if self._is_running:
            self._scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("新闻定时抓取调度器已关闭")

    def update_job_interval(self, minutes: int) -> None:
        if not self._is_running:
            return
        clean_minutes = max(1, minutes)
        trigger = IntervalTrigger(minutes=clean_minutes)
        self._scheduler.reschedule_job(JOB_ID, trigger=trigger)
        logger.info("调度器已更新轮询周期为 %d 分钟", clean_minutes)

    def pause(self) -> None:
        if self._is_running:
            self._scheduler.pause_job(JOB_ID)
            update_scheduler_config(enabled=False)
            logger.info("调度器任务已暂停")

    def resume(self) -> None:
        if self._is_running:
            self._scheduler.resume_job(JOB_ID)
            update_scheduler_config(enabled=True)
            logger.info("调度器任务已恢复")

    def get_status(self) -> dict[str, Any]:
        cfg = get_scheduler_config()
        job = self._scheduler.get_job(JOB_ID) if self._is_running else None
        next_run_time = job.next_run_time.isoformat() if (job and job.next_run_time) else None

        return {
            "scheduler_running": self._is_running,
            "job_enabled": cfg["enabled"],
            "interval_minutes": cfg["interval_minutes"],
            "configured_tags": cfg["tags"],
            "next_run_time": next_run_time,
            "last_run_at": cfg["last_run_at"],
            "last_status": cfg["last_status"],
            "last_result": cfg["last_result"],
        }

    async def trigger_now(self) -> dict[str, Any]:
        """立即手动执行一次全量定时抓取任务"""
        return await fetch_news_job()


news_scheduler = NewsScheduler()
