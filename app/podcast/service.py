from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Protocol

from app.podcast.models import PodcastScriptResult, QwenCompletion
from app.podcast.prompt import (
    HOST_1_PROFILE,
    HOST_2_PROFILE,
    SYSTEM_PROMPT,
    build_user_prompt,
)


class PodcastInputError(ValueError):
    pass


class ChatCompletionClient(Protocol):
    model: str

    async def complete(self, *, system_prompt: str, user_prompt: str) -> QwenCompletion:
        ...


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        stamp = float(value)
        if stamp > 10_000_000_000:
            stamp /= 1000
        try:
            return datetime.fromtimestamp(stamp, timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None

    text = str(value).strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_items(news: Any) -> list[dict[str, Any]]:
    value = news
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise PodcastInputError("news 字符串不是有效 JSON") from exc

    if isinstance(value, dict):
        if isinstance(value.get("items"), list):
            value = value["items"]
        elif isinstance(value.get("news"), list):
            value = value["news"]
        elif isinstance(value.get("articles"), list):
            value = value["articles"]
        else:
            raise PodcastInputError(
                "news 对象必须包含 items、news 或 articles 数组，或直接传文章数组"
            )

    if not isinstance(value, list):
        raise PodcastInputError("news 必须是文章数组、包含 items 的对象，或对应的 JSON 字符串")

    items = [item for item in value if isinstance(item, dict)]
    if not items:
        raise PodcastInputError("没有找到可用于整理的新闻条目")
    return items


def _article_sort_time(item: dict[str, Any]) -> datetime:
    for key in ("published_at", "publish_time", "fetched_at", "updated_at"):
        parsed = _parse_datetime(item.get(key))
        if parsed:
            return parsed
    return datetime.min.replace(tzinfo=timezone.utc)


def _normalize_article(item: dict[str, Any], max_chars: int) -> dict[str, Any] | None:
    title = str(item.get("title") or "").strip()
    if not title:
        return None

    summary = str(item.get("summary") or "").strip()
    content = str(item.get("content") or "").strip()
    if len(content) > max_chars:
        content = content[:max_chars] + "…"

    topics = item.get("topics")
    if not isinstance(topics, list):
        topics = [item.get("tag")] if item.get("tag") else []

    return {
        "title": title,
        "source": str(item.get("source") or "").strip(),
        "published_at": item.get("published_at") or item.get("publish_time"),
        "topics": [str(value) for value in topics if value],
        "summary": summary,
        "content": content,
    }


def _finalize_script(body: str) -> str:
    cleaned = body.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    # Older/custom model prompts may echo the profiles. Avoid duplicate headers.
    if cleaned.startswith(HOST_1_PROFILE):
        parts = cleaned.splitlines()
        body_lines = []
        passed_profiles = False
        for line in parts:
            stripped = line.strip()
            if not passed_profiles and (
                not stripped
                or stripped == HOST_1_PROFILE
                or stripped == HOST_2_PROFILE
            ):
                continue
            passed_profiles = True
            body_lines.append(line)
        cleaned = "\n".join(body_lines).strip()

    return f"{HOST_1_PROFILE}\n\n{HOST_2_PROFILE}\n\n{cleaned}"


class PodcastScriptService:
    """Independent JSON -> Qwen -> podcast-script workflow.

    This module intentionally does not import the crawler, database, repository,
    ingestion service, or scheduler.
    """

    def __init__(
        self,
        client: ChatCompletionClient,
        *,
        max_articles: int = 20,
        max_article_chars: int = 2500,
    ) -> None:
        self._client = client
        self.max_articles = max(1, max_articles)
        self.max_article_chars = max(500, max_article_chars)

    def prepare_articles(self, news: Any) -> tuple[list[dict[str, Any]], int]:
        raw_items = _extract_items(news)
        received_count = len(raw_items)

        indexed = list(enumerate(raw_items))
        indexed.sort(
            key=lambda pair: (_article_sort_time(pair[1]), -pair[0]),
            reverse=True,
        )

        selected: list[dict[str, Any]] = []
        seen: set[str] = set()

        for _, raw in indexed:
            normalized = _normalize_article(raw, self.max_article_chars)
            if not normalized:
                continue

            identity = (
                str(raw.get("id") or "").strip()
                or str(raw.get("canonical_url") or raw.get("url") or "").strip()
                or f"{normalized['source']}::{normalized['title']}"
            )
            if identity in seen:
                continue
            seen.add(identity)
            selected.append(normalized)
            if len(selected) >= self.max_articles:
                break

        if not selected:
            raise PodcastInputError("新闻条目缺少有效 title，无法生成播客文案")

        return selected, received_count

    async def generate(
        self,
        news: Any,
        *,
        target_minutes: int = 8,
        episode_title: str | None = None,
    ) -> PodcastScriptResult:
        articles, received_count = self.prepare_articles(news)
        completion = await self._client.complete(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(
                articles,
                target_minutes=target_minutes,
                episode_title=episode_title,
            ),
        )
        return PodcastScriptResult(
            script=_finalize_script(completion.content),
            model=completion.model,
            received_count=received_count,
            selected_count=len(articles),
            source_titles=[item["title"] for item in articles],
            usage=completion.usage,
            request_id=completion.request_id,
        )
