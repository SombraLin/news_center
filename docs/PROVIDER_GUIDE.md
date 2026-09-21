# News Center Provider 开发指南

V0.2 的 Provider 是新闻源适配层。核心服务不关心上游是 ZAKER、RSS、第三方 API 还是自建聚合接口，只要求 Provider 输出统一的 `ArticleCandidate`。

## 1. Provider 契约

最小实现：

```python
from app.domain import ArticleCandidate
from app.providers.base import ProviderFetchResult


class MyProvider:
    name = "my-provider"
    description = "示例新闻 Provider"
    supports_content = True
    supported_topics = (
        "hot",
        "china",
        "world",
        "military",
        "finance",
        "internet",
        "tech",
        "auto",
        "sports",
        "entertainment",
    )

    async def fetch(self, topic: str) -> ProviderFetchResult:
        articles = [
            ArticleCandidate(
                title="示例标题",
                source="示例来源",
                url="https://example.com/article/1",
                published_at=...,
                summary="示例摘要",
                content="可选正文；抓不到时可以为 None",
                topic=topic,
                language="zh-CN",
                provider=self.name,
                source_article_id="upstream-stable-id",
                canonical_url="https://example.com/article/1",
            )
        ]

        return ProviderFetchResult(
            articles=articles,
            stats={
                "fetched": 1,
                "valid": 1,
            },
        )
```

真正强制的接口只有：

- `name`
- `async fetch(topic)`

以下元数据用于 `GET /providers`，建议提供：

- `description`
- `supports_content`
- `supported_topics`

---

## 2. 统一 Topic 语义

News Center 当前使用固定的 10 个内部 topic：

```text
hot
china
world
military
finance
internet
tech
auto
sports
entertainment
```

新的 Provider 应在适配层把自己的栏目映射到这些内部 topic。

例如上游接口使用：

```text
technology_news → tech
business → finance
global → world
```

不要把第三方栏目名称直接写入数据库，否则不同 Provider 之间无法共享 topic 查询和去重关系。

---

## 3. 注册 Provider

在 `app/providers/__init__.py` 中注册：

```python
from .my_provider import MyProvider

if "my-provider" not in provider_registry.names():
    provider_registry.register(MyProvider())
```

注册后：

```bash
curl http://localhost:8100/providers
```

应能看到：

```json
{
  "name": "my-provider",
  "description": "示例新闻 Provider",
  "supports_content": true,
  "supported_topics": ["hot", "tech"]
}
```

---

## 4. 手动使用指定 Provider

```bash
curl -X POST http://localhost:8100/fetch \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_ADMIN_KEY" \
  -d '{
    "tag": "tech",
    "provider": "my-provider",
    "limit_per_tag": 10
  }'
```

如果未配置 `NEWS_CENTER_ADMIN_API_KEY`，可以省略 `X-API-Key`。

---

## 5. 作为默认 Provider

环境变量：

```dotenv
NEWS_CENTER_DEFAULT_PROVIDER=my-provider
```

该值用于：

- `POST /fetch` 未显式传 provider 时
- 新建 scheduler 配置时的默认 Provider
- readiness 对默认 Provider 的可用性检查

如果设置了一个未注册的默认 Provider：

```text
GET /health/ready
```

会返回 HTTP 503。

---

## 6. Scheduler 使用 Provider

```bash
curl -X POST http://localhost:8100/scheduler/config \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_ADMIN_KEY" \
  -d '{
    "provider": "my-provider",
    "tags": ["tech", "finance"],
    "interval_minutes": 30,
    "enabled": true
  }'
```

Scheduler 每一轮都会读取 SQLite 中持久化的 `provider` 配置。

---

## 7. 正文处理建议

Provider 可以直接给 `ArticleCandidate.content`。

如果上游只提供列表和 URL，可复用：

```python
from app.providers.content import enrich_articles_with_content

stats = await enrich_articles_with_content(articles)
```

正文提取失败应视为非致命错误。

推荐保留：

```python
stats["content_attempted"]
stats["content_enriched"]
stats["content_failed"]
```

这些值会通过 `POST /fetch` 的 `provider_stats` 暴露。

项目当前不处理图片。

---

## 8. Article 身份字段

优先提供稳定的：

```text
provider
source_article_id
canonical_url
```

News Center 当前按以下顺序识别重复文章：

```text
provider + source_article_id
        OR
canonical_url
        OR
content_hash(title + summary)
```

因此 Provider 不需要自己访问数据库做历史去重。

---

## 9. Provider 不应该做的事情

Provider 层不要负责：

- SQLite 写入
- Scheduler
- FastAPI response
- LLM 摘要/改写
- TTS
- 个性化推荐

正确边界：

```text
External Source
      ↓
Provider
      ↓
ArticleCandidate
      ↓
IngestionService
      ↓
Repository
```

---

## 10. 测试要求

至少增加一个不访问真实外网的 Fake Provider 测试：

```text
Provider.fetch
    ↓
POST /fetch
    ↓
SQLite
    ↓
GET /news
    ↓
GET /news/search
```

运行：

```bash
PYTHONPATH=. python -m pytest -q
```

Provider 合入前应保证 GitHub Actions 为绿色。
