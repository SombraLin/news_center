from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.podcast.models import QwenCompletion
from app.podcast.qwen import QwenChatClient, QwenConfigError
from app.podcast.service import PodcastScriptService
from app.routes.podcast import get_podcast_script_service


class FakeQwenClient:
    model = "qwen-plus"

    def __init__(self) -> None:
        self.system_prompt = ""
        self.user_prompt = ""

    async def complete(self, *, system_prompt: str, user_prompt: str) -> QwenCompletion:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return QwenCompletion(
            content=(
                "主播 1 是成年男性，嗓音低沉，略带沙哑，吐字清晰，语速略微偏快\n\n"
                "主播 2 是年轻女性，嗓音偏御，略哑，略微低沉\n\n"
                "主播 1 语调平缓：“今天先从最受关注的一组新闻聊起。”\n\n"
                "主播 2 简短回应：“好，我们接着往下梳理。”"
            ),
            model="qwen-plus",
            usage={"prompt_tokens": 123, "completion_tokens": 45},
            request_id="test-request-id",
        )


def _news_items(count: int = 21) -> list[dict]:
    base = datetime(2026, 9, 21, 8, 0, tzinfo=timezone.utc)
    return [
        {
            "id": f"news-{index}",
            "title": f"热点新闻 {index}",
            "source": "测试新闻源",
            "summary": f"这是热点新闻 {index} 的摘要。",
            "content": f"这是热点新闻 {index} 的正文内容。",
            "published_at": (base + timedelta(minutes=index)).isoformat(),
            "tag": "hot",
            "topics": ["hot"],
        }
        for index in range(count)
    ]


def test_podcast_service_selects_latest_twenty_and_builds_voice_prompt():
    fake = FakeQwenClient()
    service = PodcastScriptService(fake, max_articles=20, max_article_chars=2500)

    result = asyncio.run(
        service.generate(
            {"items": _news_items(21)},
            target_minutes=8,
            episode_title="今日热点",
        )
    )

    assert result.received_count == 21
    assert result.selected_count == 20
    assert result.source_titles[0] == "热点新闻 20"
    assert "热点新闻 0" not in result.source_titles
    assert result.model == "qwen-plus"
    assert "主播 1 是成年男性" in result.script
    assert "主播 2 是年轻女性" in fake.system_prompt
    assert "严禁虚构" in fake.system_prompt
    assert "今日热点" in fake.user_prompt
    assert "热点新闻 20" in fake.user_prompt


def test_podcast_service_accepts_raw_json_text():
    fake = FakeQwenClient()
    service = PodcastScriptService(fake)

    payload = json.dumps({"items": _news_items(2)}, ensure_ascii=False)
    result = asyncio.run(service.generate(payload, target_minutes=5))

    assert result.received_count == 2
    assert result.selected_count == 2


def test_podcast_api_accepts_news_list_response_shape():
    fake = FakeQwenClient()
    service = PodcastScriptService(fake)

    app.dependency_overrides[get_podcast_script_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.post(
            "/podcast/script",
            json={
                "news": {
                    "total": 20,
                    "limit": 20,
                    "offset": 0,
                    "count": 20,
                    "items": _news_items(20),
                },
                "target_minutes": 8,
            },
        )
    finally:
        app.dependency_overrides.pop(get_podcast_script_service, None)

    assert response.status_code == 200
    data = response.json()
    assert data["model"] == "qwen-plus"
    assert data["selected_count"] == 20
    assert data["received_count"] == 20
    assert data["request_id"] == "test-request-id"
    assert "主播 1 是成年男性" in data["script"]
    assert len(data["source_titles"]) == 20


def test_podcast_api_rejects_invalid_news_json():
    fake = FakeQwenClient()
    service = PodcastScriptService(fake)

    app.dependency_overrides[get_podcast_script_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.post(
            "/podcast/script",
            json={"news": "not-json", "target_minutes": 8},
        )
    finally:
        app.dependency_overrides.pop(get_podcast_script_service, None)

    assert response.status_code == 400


def test_qwen_client_requires_api_key_before_network_call():
    client = QwenChatClient(
        api_key="",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen-plus",
    )

    async def scenario() -> None:
        try:
            await client.complete(system_prompt="system", user_prompt="user")
        except QwenConfigError as exc:
            assert "API Key" in str(exc)
        else:
            raise AssertionError("expected QwenConfigError")

    asyncio.run(scenario())
