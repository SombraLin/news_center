from __future__ import annotations

from typing import Any

import httpx

from app.podcast.models import QwenCompletion


class QwenConfigError(RuntimeError):
    pass


class QwenAPIError(RuntimeError):
    pass


class QwenChatClient:
    """Minimal OpenAI-compatible client for Alibaba Cloud Model Studio."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str = "qwen-plus",
        timeout: float = 90.0,
    ) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model.strip() or "qwen-plus"
        self.timeout = timeout

    async def complete(self, *, system_prompt: str, user_prompt: str) -> QwenCompletion:
        if not self.api_key:
            raise QwenConfigError(
                "未配置 Qwen API Key。请设置 DASHSCOPE_API_KEY 或 NEWS_CENTER_QWEN_API_KEY。"
            )
        if not self.base_url:
            raise QwenConfigError("未配置 Qwen OpenAI-compatible Base URL。")

        endpoint = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.6,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                trust_env=False,
            ) as client:
                response = await client.post(endpoint, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise QwenAPIError(f"Qwen 请求失败: {exc}") from exc

        if response.status_code >= 400:
            try:
                error_payload = response.json()
                message = (
                    error_payload.get("error", {}).get("message")
                    or error_payload.get("message")
                    or response.text
                )
            except ValueError:
                message = response.text
            raise QwenAPIError(
                f"Qwen API 返回 HTTP {response.status_code}: {str(message)[:500]}"
            )

        try:
            data: dict[str, Any] = response.json()
            choices = data.get("choices")
            if not isinstance(choices, list) or not choices:
                raise ValueError("缺少 choices")
            message = choices[0].get("message") or {}
            content = message.get("content")
        except (ValueError, TypeError, AttributeError) as exc:
            raise QwenAPIError("Qwen API 返回结构异常") from exc

        if isinstance(content, list):
            content = "".join(
                str(item.get("text") or "")
                for item in content
                if isinstance(item, dict)
            )
        if not isinstance(content, str) or not content.strip():
            raise QwenAPIError("Qwen API 未返回有效文案")

        usage = data.get("usage")
        return QwenCompletion(
            content=content.strip(),
            model=str(data.get("model") or self.model),
            usage=usage if isinstance(usage, dict) else {},
            request_id=response.headers.get("x-request-id") or data.get("request_id"),
        )
