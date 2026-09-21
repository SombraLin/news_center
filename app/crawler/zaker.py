from __future__ import annotations

import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
import html
import re
import unicodedata
from urllib.parse import urlsplit
from typing import Any

import httpx

# 预设主题定义与元数据映射
TOPIC_DEFINITIONS: list[dict[str, Any]] = [
    {
        "tag": "hot",
        "name": "热点",
        "description": "实时热门资讯与高关注度全网头条",
        "app_id": None,
        "endpoint": "https://skills.myzaker.com/api/v1/article/hot",
    },
    {
        "tag": "china",
        "name": "国内",
        "description": "国内重点政经要闻与社会焦点新闻",
        "app_id": 1,
        "endpoint": "https://skills.myzaker.com/api/v1/article/category",
    },
    {
        "tag": "world",
        "name": "国际",
        "description": "全球国际要闻、大国外交与重大突发事件",
        "app_id": 2,
        "endpoint": "https://skills.myzaker.com/api/v1/article/category",
    },
    {
        "tag": "military",
        "name": "军事",
        "description": "国防军工、战略演练与国际安全动态",
        "app_id": 3,
        "endpoint": "https://skills.myzaker.com/api/v1/article/category",
    },
    {
        "tag": "finance",
        "name": "财经",
        "description": "宏观经济、股市投资、商业地产与产业理财",
        "app_id": 4,
        "endpoint": "https://skills.myzaker.com/api/v1/article/category",
    },
    {
        "tag": "internet",
        "name": "互联网",
        "description": "互联网科技巨头、商业模式与创投动向",
        "app_id": 5,
        "endpoint": "https://skills.myzaker.com/api/v1/article/category",
    },
    {
        "tag": "auto",
        "name": "汽车",
        "description": "新能源汽车、行业新车发布与智能座舱技术",
        "app_id": 7,
        "endpoint": "https://skills.myzaker.com/api/v1/article/category",
    },
    {
        "tag": "sports",
        "name": "体育",
        "description": "足球、篮球、综合赛事、奥运热点与体坛风云",
        "app_id": 8,
        "endpoint": "https://skills.myzaker.com/api/v1/article/category",
    },
    {
        "tag": "entertainment",
        "name": "娱乐",
        "description": "影视剧评、文化演出与文娱动态",
        "app_id": 9,
        "endpoint": "https://skills.myzaker.com/api/v1/article/category",
    },
    {
        "tag": "tech",
        "name": "科技",
        "description": "数码电子、人工智能、硬核前沿技术创新",
        "app_id": 13,
        "endpoint": "https://skills.myzaker.com/api/v1/article/category",
    },
]

SUPPORTED_TAGS: tuple[str, ...] = tuple(t["tag"] for t in TOPIC_DEFINITIONS)
CATEGORY_APP_IDS: dict[str, int] = {t["tag"]: t["app_id"] for t in TOPIC_DEFINITIONS if t["app_id"] is not None}
TAG_ALIASES: dict[str, str] = {
    "sport": "sports",
    "technology": "tech",
    "automotive": "auto",
    "domestic": "china",
    "international": "world",
}

_HTML_TAG = re.compile(r"<[^>]*>")
_WHITESPACE = re.compile(r"\s+")
_EFFECTIVE_CHAR = re.compile(r"[\u3400-\u9fffA-Za-z0-9]")


@dataclass
class Candidate:
    title: str
    source: str
    url: str
    published_at: datetime | None
    summary: str
    tag: str
    language: str = "zh-CN"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.published_at:
            d["published_at"] = self.published_at.isoformat()
        return d


def get_preset_topics() -> list[dict[str, Any]]:
    """返回所有已预设的可用新闻主题列表，供前端或调用方选择展示"""
    return [
        {
            "tag": item["tag"],
            "name": item["name"],
            "description": item["description"],
        }
        for item in TOPIC_DEFINITIONS
    ]


def normalize_tag(tag: str) -> str:
    cleaned = tag.strip().lower().replace("-", "_")
    value = TAG_ALIASES.get(cleaned, cleaned)
    if value not in SUPPORTED_TAGS:
        raise ValueError(f"不支持的新闻分类：{tag}。支持的分类有: {', '.join(SUPPORTED_TAGS)}")
    return value


def parse_publish_time(value: object) -> datetime | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) or str(value).replace(".", "", 1).isdigit():
        stamp = float(value)
        if stamp > 10_000_000_000:
            stamp /= 1000
        try:
            return datetime.fromtimestamp(stamp, timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    text = str(value).strip()
    normalized = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        # 默认北京时间 UTC+8
        parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
    return parsed.astimezone(timezone.utc)


def clean_summary(value: str) -> str:
    value = html.unescape(value or "")
    value = _HTML_TAG.sub(" ", value)
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value)).strip()


def validate_candidate(candidate: Candidate, now: datetime) -> str | None:
    if not candidate.title or len(candidate.title) > 512:
        return "invalid_title"
    try:
        parsed_url = urlsplit(candidate.url)
    except ValueError:
        return "invalid_url"
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname or len(candidate.url) > 1024:
        return "invalid_url"
    if not candidate.published_at:
        return "invalid_time"
    if candidate.published_at > now + timedelta(minutes=10):
        return "future_time"
    if candidate.published_at < now - timedelta(hours=36):
        return "too_old"
    normalized_title = _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", candidate.title)).strip().casefold()
    normalized_summary = candidate.summary.casefold()
    if len(_EFFECTIVE_CHAR.findall(candidate.summary)) < 15 or normalized_summary == normalized_title:
        return "invalid_summary"
    return None


async def _get_with_retry(client: httpx.AsyncClient, url: str, params: dict[str, str]) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("ZAKER 返回格式异常：不是 JSON 对象")
            return payload
        except (httpx.HTTPError, ValueError) as exc:
            last_exc = exc
            if attempt < 2:
                await asyncio.sleep(0.5 * (2 ** attempt))
    raise RuntimeError(f"ZAKER 抓取网络请求失败: {last_exc}")


async def fetch_zaker(
    tag: str,
    language: str = "zh-CN",
    timeout: float = 12.0,
) -> tuple[list[Candidate], dict[str, int]]:
    """根据 tag 抓取指定分类的最新新闻候选列表"""
    clean_tag = normalize_tag(tag)
    if clean_tag == "hot":
        url = "https://skills.myzaker.com/api/v1/article/hot"
        params = {"v": "1.0.3"}
    else:
        url = "https://skills.myzaker.com/api/v1/article/category"
        params = {"v": "1.0.6", "app_id": str(CATEGORY_APP_IDS[clean_tag])}

    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        payload = await _get_with_retry(client, url, params)

    if payload.get("stat") != 1:
        raise RuntimeError(str(payload.get("msg") or "ZAKER 接口返回业务错误"))

    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("list"), list):
        raise RuntimeError("ZAKER 返回数据结构缺少 data.list")

    raw_items = data["list"]
    stats: dict[str, int] = {"fetched": len(raw_items)}
    candidates: list[Candidate] = []
    seen_urls: set[str] = set()
    now = datetime.now(timezone.utc)

    for item in raw_items:
        if not isinstance(item, dict):
            stats["invalid_item"] = stats.get("invalid_item", 0) + 1
            continue
        title = item.get("title")
        item_url = item.get("url")
        if not isinstance(title, str) or not isinstance(item_url, str):
            stats["invalid_item"] = stats.get("invalid_item", 0) + 1
            continue

        raw_summary = item.get("summary") if isinstance(item.get("summary"), str) else ""
        cleaned = clean_summary(raw_summary)
        candidate = Candidate(
            title=title.strip(),
            source=str(item.get("author") or "ZAKER").strip(),
            url=item_url.strip(),
            published_at=parse_publish_time(item.get("publish_time")),
            summary=cleaned,
            tag=clean_tag,
            language=language,
        )

        reason = validate_candidate(candidate, now)
        if reason:
            stats[reason] = stats.get(reason, 0) + 1
            continue

        if candidate.url in seen_urls:
            stats["duplicate_url_in_response"] = stats.get("duplicate_url_in_response", 0) + 1
            continue

        seen_urls.add(candidate.url)
        candidates.append(candidate)

    candidates.sort(key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    stats["valid"] = len(candidates)
    return candidates, stats
