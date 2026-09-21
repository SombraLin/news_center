from __future__ import annotations

from typing import Any


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def render_news_text(
    items: list[dict[str, Any]],
    *,
    tag: str | None,
    max_content_chars: int = 2500,
) -> str:
    """Render news rows as copy-friendly plain text for LLM input."""
    lines = [
        f"新闻主题：{tag or '全部'}",
        f"新闻数量：{len(items)}",
        "",
    ]

    for index, item in enumerate(items, start=1):
        title = _clean_text(item.get("title"))
        source = _clean_text(item.get("source"))
        published_at = _clean_text(item.get("published_at"))
        summary = _clean_text(item.get("summary"))
        content = _clean_text(item.get("content"))

        if max_content_chars > 0 and len(content) > max_content_chars:
            content = content[:max_content_chars].rstrip() + "…"

        lines.extend(
            [
                f"【新闻 {index}】",
                f"标题：{title}",
            ]
        )
        if source:
            lines.append(f"来源：{source}")
        if published_at:
            lines.append(f"发布时间：{published_at}")
        if summary:
            lines.append(f"摘要：{summary}")
        if content:
            lines.extend(["正文：", content])
        elif summary:
            lines.extend(["正文：", "未抓取到完整正文，请以摘要信息为准。"])
        else:
            lines.extend(["正文：", "暂无正文或摘要。"])

        lines.extend(["", "----------------------------------------", ""])

    return "\n".join(lines).rstrip() + "\n"
