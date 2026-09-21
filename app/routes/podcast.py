from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.podcast import (
    PodcastInputError,
    PodcastScriptService,
    QwenAPIError,
    QwenChatClient,
    QwenConfigError,
)
from app.security import require_admin_api_key

router = APIRouter(
    prefix="/podcast",
    dependencies=[Depends(require_admin_api_key)],
)

_podcast_script_service = PodcastScriptService(
    QwenChatClient(
        api_key=settings.qwen_api_key,
        base_url=settings.qwen_base_url,
        model="qwen-plus",
        timeout=settings.qwen_timeout_seconds,
    ),
    max_articles=settings.podcast_max_articles,
    max_article_chars=settings.podcast_max_article_chars,
)


def get_podcast_script_service() -> PodcastScriptService:
    return _podcast_script_service


class PodcastScriptRequest(BaseModel):
    news: Any | None = Field(
        None,
        description=(
            "手工粘贴的新闻 JSON。可直接传 /news 返回对象、文章数组，"
            "或它们对应的 JSON 字符串。与 news_text 二选一。"
        ),
    )
    news_text: str | None = Field(
        None,
        min_length=20,
        description=(
            "手工粘贴的新闻长文本，推荐直接使用 GET /news/text 的返回结果。"
            "与 news 二选一。"
        ),
    )
    target_minutes: int = Field(
        8,
        ge=3,
        le=20,
        description="目标播客时长（分钟），默认 8 分钟。",
    )
    episode_title: str | None = Field(
        None,
        max_length=120,
        description="可选节目主题。为空时由模型从新闻中自行提炼主线。",
    )


@router.post("/script", summary="将新闻 JSON 或长文本整理成双人播客文案")
async def generate_podcast_script(
    request: PodcastScriptRequest,
    service: PodcastScriptService = Depends(get_podcast_script_service),
) -> dict[str, Any]:
    """独立的手工输入 -> Qwen-Plus -> 播客文案流程。

    该接口不会读取新闻数据库、不会触发抓取，也不会调用音频生成服务。
    """
    if (request.news is None) == (request.news_text is None):
        raise HTTPException(
            status_code=400,
            detail="news 与 news_text 必须且只能提供一个",
        )

    try:
        if request.news_text is not None:
            result = await service.generate_from_text(
                request.news_text,
                target_minutes=request.target_minutes,
                episode_title=request.episode_title,
            )
        else:
            result = await service.generate(
                request.news,
                target_minutes=request.target_minutes,
                episode_title=request.episode_title,
            )
    except PodcastInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except QwenConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except QwenAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return result.to_dict()
