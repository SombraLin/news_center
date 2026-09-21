# News Center V0.2 API 使用说明

本文面向直接调用 News Center 的前端、玩偶服务、LLM 服务或其他后端。

默认服务地址：

```text
http://localhost:8100
```

交互式 OpenAPI：

```text
http://localhost:8100/docs
```

---

## 1. 启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

验证服务：

```bash
curl http://localhost:8100/
```

正常返回：

```json
{
  "service": "news_center",
  "status": "running",
  "docs_url": "/docs",
  "topics_url": "/topics",
  "news_url": "/news",
  "search_url": "/news/search?q=关键词"
}
```

---

## 2. 推荐调用流程

典型调用链：

```text
GET /topics
    ↓
POST /fetch
    ↓
GET /news
    ↓
GET /news/search
    ↓
GET /news/{id}
```

定时模式下可省略手动 `POST /fetch`，由 scheduler 周期抓取。

---

## 3. 获取主题

```bash
curl "http://localhost:8100/topics"
```

支持主题：

`hot`, `china`, `world`, `military`, `finance`, `internet`, `tech`, `auto`, `sports`, `entertainment`

返回示例：

```json
{
  "total_topics": 10,
  "topics": [
    {
      "tag": "tech",
      "name": "科技",
      "description": "数码电子、人工智能、硬核前沿技术创新",
      "article_count": 42
    }
  ]
}
```

---

## 4. 手动抓取并入库

抓取单一主题：

```bash
curl -X POST "http://localhost:8100/fetch" \
  -H "Content-Type: application/json" \
  -d '{
    "tag": "tech",
    "limit_per_tag": 10
  }'
```

批量主题：

```bash
curl -X POST "http://localhost:8100/fetch" \
  -H "Content-Type: application/json" \
  -d '{
    "tags": ["tech", "finance", "world"],
    "limit_per_tag": 10
  }'
```

返回关键字段：

```json
{
  "success": true,
  "status": "success",
  "total_added": 7,
  "total_skipped": 3,
  "results": {
    "tech": {
      "topic": "tech",
      "provider": "zaker",
      "fetched": 20,
      "valid": 15,
      "added": 7,
      "duplicate_history": 3,
      "provider_stats": {
        "fetched": 20,
        "valid": 15,
        "content_attempted": 15,
        "content_enriched": 11,
        "content_failed": 4
      },
      "error": null
    }
  }
}
```

### 正文抓取说明

正文抓取是 **best effort**：

- 抓取列表成功后，会并发访问文章页面提取正文。
- 优先读取 JSON-LD 中的 `articleBody`。
- 若没有结构化正文，则从有效段落中提取纯文本。
- 单篇正文抓取失败不会导致整轮新闻抓取失败。
- 抓不到正文时，`content` 为 `null`，但 title / summary / source / url 仍然可正常使用。

本项目当前不抓取图片。

---

## 5. 查询新闻列表

最新科技新闻：

```bash
curl "http://localhost:8100/news?tag=tech&limit=20&offset=0"
```

兼容旧关键词入口：

```bash
curl --get "http://localhost:8100/news" \
  --data-urlencode "keyword=人工智能" \
  --data-urlencode "limit=20"
```

`keyword` 已由 SQLite FTS5 实现，不再使用全表 `LIKE`。

文章返回示例：

```json
{
  "id": "ARTICLE_ID",
  "tag": "tech",
  "topics": ["hot", "tech"],
  "title": "示例新闻标题",
  "source": "示例来源",
  "url": "https://example.com/article",
  "canonical_url": "https://example.com/article",
  "summary": "文章摘要",
  "content": "抓取到的新闻正文纯文本……",
  "image_url": null,
  "language": "zh-CN",
  "provider": "zaker",
  "published_at": "2026-09-21T04:00:00+00:00",
  "fetched_at": "2026-09-21T05:00:00+00:00",
  "updated_at": "2026-09-21T05:00:00+00:00"
}
```

---

## 6. 全文搜索

推荐上层 AI / 玩偶服务使用：

```bash
curl --get "http://localhost:8100/news/search" \
  --data-urlencode "q=人工智能机器人" \
  --data-urlencode "tag=tech" \
  --data-urlencode "limit=10"
```

搜索覆盖：

- title
- summary
- source
- content

返回按 BM25 相关性排序，并包含：

```json
{
  "query": "人工智能机器人",
  "tag": "tech",
  "total": 3,
  "items": [
    {
      "id": "ARTICLE_ID",
      "title": "示例标题",
      "content": "正文……",
      "relevance": -4.2,
      "match_snippet": "……<mark>人工智能机器人</mark>……"
    }
  ]
}
```

注意：BM25 的数值本身不适合跨不同查询直接比较，只用于当前查询结果排序。

---

## 7. 获取单篇详情

```bash
curl "http://localhost:8100/news/ARTICLE_ID"
```

不存在时返回 HTTP 404：

```json
{
  "detail": "未找到对应新闻记录"
}
```

---

## 8. Scheduler

查看状态：

```bash
curl "http://localhost:8100/scheduler/status"
```

更新配置：

```bash
curl -X POST "http://localhost:8100/scheduler/config" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "interval_minutes": 30,
    "tags": ["hot", "tech", "finance"]
  }'
```

立即执行：

```bash
curl -X POST "http://localhost:8100/scheduler/run"
```

---

## 9. 正文抓取配置

`.env`：

```dotenv
NEWS_CENTER_CONTENT_FETCH_ENABLED=true
NEWS_CENTER_CONTENT_FETCH_TIMEOUT_SECONDS=8
NEWS_CENTER_CONTENT_FETCH_CONCURRENCY=4
NEWS_CENTER_CONTENT_MAX_CHARS=30000
```

说明：

- `CONTENT_FETCH_ENABLED=false`：仅抓列表摘要，不访问文章正文页。
- `CONTENT_FETCH_TIMEOUT_SECONDS`：单个 HTTP 请求超时。
- `CONTENT_FETCH_CONCURRENCY`：正文页面并发数。
- `CONTENT_MAX_CHARS`：单篇正文最多保留字符数。

如果主要部署在带宽有限的设备上，可以关闭正文抓取；如果作为中心服务器给 LLM 检索使用，建议保持开启。

---

## 10. API 状态含义

`POST /fetch`：

- `success`：所有主题抓取成功。
- `partial`：部分主题失败，其余成功。
- `failed`：所有目标主题均失败。

单篇正文提取失败不会让主题变为 failed。

---

## 11. 上层 AI 推荐使用方式

对于“给我最近关于机器人/AI 的新闻”：

1. 调用 `GET /news/search?q=机器人 AI&limit=5`。
2. 根据返回的 `id` 获取必要的单篇详情。
3. 优先使用 `content`；若 `content=null`，回退到 `summary`。
4. 在上层完成摘要、儿童化改写、TTS 或个性化推荐。

News Center 本身不承担 LLM 改写和语音生成。

---

## 12. 验证部署是否正常

启动后依次执行：

```bash
curl http://localhost:8100/
curl http://localhost:8100/topics

curl -X POST http://localhost:8100/fetch \
  -H "Content-Type: application/json" \
  -d '{"tag":"tech","limit_per_tag":3}'

curl "http://localhost:8100/news?tag=tech&limit=3"
curl --get "http://localhost:8100/news/search" --data-urlencode "q=人工智能"
```

只要以上调用均返回 2xx，并且 `/fetch` 的 `status` 为 `success` 或 `partial`，服务的核心调用链即正常。
