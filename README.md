# News Center

轻量级、可嵌入的新闻采集与全文检索服务。

当前 V0.2 的定位是 **News Content & Retrieval Hub**：

```text
News Provider
     ↓
IngestionService
     ↓
去重 / 多主题归档
     ↓
SQLite articles
     ├── article_topics
     └── FTS5 全文索引
              ↓
       REST Retrieval API
```

News Center 专注于：

- 新闻采集
- 正文 best-effort 提取
- canonical URL / content hash 去重
- 一篇文章关联多个 topic
- SQLite 持久化
- FTS5 中文全文检索
- APScheduler 定时采集

明确不负责：

- LLM 改写
- 个性化推荐
- TTS
- 图片抓取

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

默认地址：

```text
http://127.0.0.1:8100
```

Swagger：

```text
http://127.0.0.1:8100/docs
```

## 最常用接口

```text
GET  /topics
POST /fetch
GET  /news
GET  /news/search?q=人工智能
GET  /news/{id}

GET  /scheduler/status
POST /scheduler/config
POST /scheduler/run
```

最简单的使用流程：

```bash
curl -X POST http://127.0.0.1:8100/fetch \
  -H "Content-Type: application/json" \
  -d '{"tag":"tech","limit_per_tag":10}'

curl "http://127.0.0.1:8100/news?tag=tech"

curl --get http://127.0.0.1:8100/news/search \
  --data-urlencode "q=人工智能"
```

## 文档

- [完整 API 使用说明](docs/api-usage.md)
- [V0.2 架构说明](docs/architecture-v0.2.md)

## 数据模型

主要表：

```text
articles
article_topics
articles_fts
scheduler_config
```

V0.1 的 `news` 表暂时保留作为回滚兼容 shadow table。

文章身份识别依次利用：

1. `provider + source_article_id`
2. canonical URL
3. title + summary content hash

## 正文

默认会尝试抓取文章详情页正文：

```bash
NEWS_CENTER_CONTENT_FETCH_ENABLED=true
NEWS_CENTER_CONTENT_FETCH_TIMEOUT_SECONDS=8
NEWS_CENTER_CONTENT_FETCH_CONCURRENCY=4
NEWS_CENTER_CONTENT_MAX_CHARS=30000
```

正文抓取失败不会导致新闻抓取失败。

此时：

- title 正常保存
- summary 正常保存
- content 可能为 null
- 仍然可以通过标题/摘要搜索

## 测试

```bash
PYTHONPATH=. python -m pytest -q
```

GitHub Actions 会在 PR 更新时自动执行测试。

测试包含真实 FastAPI 路由的端到端链路：

```text
POST /fetch
  → GET /news
  → GET /news/search
  → GET /news/{id}
```

## 当前主题

`hot`, `china`, `world`, `military`, `finance`, `internet`, `tech`, `auto`, `sports`, `entertainment`.
