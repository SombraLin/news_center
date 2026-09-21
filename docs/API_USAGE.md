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
  "search_url": "/news/search?q=关键词",
  "podcast_script_url": "/podcast/script"
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


---

## 13. 健康检查

Liveness：

```bash
curl http://localhost:8100/health/live
```

正常：

```json
{
  "status": "alive",
  "service": "news_center",
  "version": "0.2.0"
}
```

Readiness：

```bash
curl http://localhost:8100/health/ready
```

Readiness 会检查：

- SQLite 可查询
- `articles`
- `article_topics`
- `articles_fts`
- `scheduler_config`
- 默认 Provider 已注册

正常返回 HTTP 200；数据库或默认 Provider 不可用时返回 HTTP 503。

Kubernetes / Docker 编排建议：

```text
liveness  -> GET /health/live
readiness -> GET /health/ready
```

健康检查不会访问 ZAKER 等外部新闻源，避免上游短暂故障导致本服务被错误重启。

---

## 14. 管理 API Key

默认情况下：

```dotenv
NEWS_CENTER_ADMIN_API_KEY=
```

为空表示兼容本地开发模式，不启用管理鉴权。

生产环境建议设置：

```dotenv
NEWS_CENTER_ADMIN_API_KEY=replace-with-a-long-random-secret
```

启用后，以下管理接口要求：

```http
X-API-Key: replace-with-a-long-random-secret
```

受保护接口：

- `POST /fetch`
- `GET /scheduler/status`
- `POST /scheduler/config`
- `POST /scheduler/run`
- `POST /podcast/script`

示例：

```bash
curl -X POST http://localhost:8100/fetch \
  -H "Content-Type: application/json" \
  -H "X-API-Key: replace-with-a-long-random-secret" \
  -d '{"tag":"tech","limit_per_tag":3}'
```

Key 缺失或错误时返回 HTTP 401。

以下读取接口仍保持公开：

- `/`
- `/health/live`
- `/health/ready`
- `/providers`
- `/topics`
- `/news`
- `/news/search`
- `/news/{id}`

---

## 15. Provider 发现与切换

查看已注册 Provider：

```bash
curl http://localhost:8100/providers
```

返回示例：

```json
{
  "default_provider": "zaker",
  "total": 1,
  "providers": [
    {
      "name": "zaker",
      "description": "ZAKER 新闻主题列表 + best-effort 正文提取",
      "supports_content": true,
      "supported_topics": ["hot", "china", "world", "tech"]
    }
  ]
}
```

手动抓取指定 Provider：

```bash
curl -X POST http://localhost:8100/fetch \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_ADMIN_KEY" \
  -d '{
    "tag": "tech",
    "provider": "zaker",
    "limit_per_tag": 5
  }'
```

Scheduler 切换 Provider：

```bash
curl -X POST http://localhost:8100/scheduler/config \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_ADMIN_KEY" \
  -d '{
    "provider": "zaker",
    "tags": ["hot", "tech", "finance"],
    "interval_minutes": 30
  }'
```

默认 Provider：

```dotenv
NEWS_CENTER_DEFAULT_PROVIDER=zaker
```

新增 Provider 的实现说明见：

```text
docs/PROVIDER_GUIDE.md
```


---

## 16. 独立播客文案模块

将手工粘贴的新闻 JSON 使用 Qwen-Plus 整理成双主播播客文案：

```text
POST /podcast/script
```

该接口不会自动读取数据库或触发新闻抓取，也不会调用音频生成模型。

详细使用方法：

```text
docs/PODCAST_SCRIPT.md
```


---

## 17. 新闻长文本导出

推荐用于人工复制给 LLM / Podcast Script：

```bash
curl "http://localhost:8100/news/text?tag=hot&limit=20"
```

返回类型：

```text
Content-Type: text/plain
```

返回内容包含每条新闻的：

- 标题
- 来源
- 发布时间
- 摘要
- 正文

默认每篇正文最多输出 2500 字：

```text
max_content_chars=2500
```

可调整到最多 30000：

```bash
curl "http://localhost:8100/news/text?tag=hot&limit=20&max_content_chars=5000"
```

推荐 Podcast 调用方式：

```json
{
  "news_text": "把 /news/text 的完整响应粘贴到这里",
  "target_minutes": 8
}
```

然后提交：

```text
POST /podcast/script
```
