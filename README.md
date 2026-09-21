# News Center V0.2

轻量、独立的 **News Content & Retrieval Hub**。

News Center 负责：

```text
抓取
  ↓
正文提取
  ↓
规范化
  ↓
去重
  ↓
多主题关联
  ↓
SQLite 持久化
  ↓
FTS5 全文检索
```

新闻采集核心层不负责 LLM 改写、儿童化表达、推荐策略或 TTS。

V0.2 额外提供一个**完全独立的 Podcast Script 模块**：仅接受人工粘贴的新闻 JSON，调用 Qwen-Plus 整理为双主播播客文案；它不会自动触发新闻抓取，也不会自动调用音频生成服务。

## 当前能力

- 10 个预设新闻主题
- Provider 抽象，当前默认 ZAKER
- 手动抓取与定时抓取统一经过 `IngestionService`
- 正文页面 best-effort 提取，不抓取图片
- `provider + source_article_id` / canonical URL / content hash 三层去重
- 一篇文章可关联多个 topic
- SQLite 单事务批量写入
- SQLite FTS5 + trigram 中文全文检索
- BM25 相关性排序
- V0.1 `news` shadow table，支持回滚兼容
- GitHub Actions 自动运行 pytest
- 独立 `POST /podcast/script`：手工新闻 JSON → Qwen-Plus → 双主播播客文案

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

默认地址：

```text
http://localhost:8100
```

OpenAPI：

```text
http://localhost:8100/docs
```

完整调用说明：

**[docs/API_USAGE.md](docs/API_USAGE.md)**

架构说明：

**[docs/architecture-v0.2.md](docs/architecture-v0.2.md)**

Podcast Script 使用说明：

**[docs/PODCAST_SCRIPT.md](docs/PODCAST_SCRIPT.md)**

## 最短验证流程

```bash
curl http://localhost:8100/
curl http://localhost:8100/topics

curl -X POST http://localhost:8100/fetch \
  -H "Content-Type: application/json" \
  -d '{"tag":"tech","limit_per_tag":3}'

curl "http://localhost:8100/news?tag=tech&limit=3"

curl --get "http://localhost:8100/news/search" \
  --data-urlencode "q=人工智能"
```

## API

| Method | Path | 用途 |
|---|---|---|
| GET | `/` | 服务状态 |
| GET | `/topics` | 获取主题及文章数量 |
| POST | `/fetch` | 手动抓取并入库 |
| GET | `/news` | 按时间分页查询；兼容 keyword 搜索 |
| GET | `/news/search` | FTS5 + BM25 全文检索 |
| GET | `/news/{id}` | 单篇详情 |
| GET | `/scheduler/status` | Scheduler 状态 |
| POST | `/scheduler/config` | 更新 Scheduler 配置 |
| POST | `/scheduler/run` | 立即执行一轮定时任务 |
| POST | `/podcast/script` | 将手工粘贴的新闻 JSON 整理为 Qwen-Plus 双主播播客文案 |

## 主题

`hot`, `china`, `world`, `military`, `finance`, `internet`, `tech`, `auto`, `sports`, `entertainment`

## 正文提取

默认开启：

```dotenv
NEWS_CENTER_CONTENT_FETCH_ENABLED=true
NEWS_CENTER_CONTENT_FETCH_TIMEOUT_SECONDS=8
NEWS_CENTER_CONTENT_FETCH_CONCURRENCY=4
NEWS_CENTER_CONTENT_MAX_CHARS=30000
```

提取策略：

1. 优先 JSON-LD `articleBody`
2. 回退到有效正文段落
3. HTML 转为纯文本
4. 页面抓取失败时保留 summary，不让整条新闻失败

项目当前**不抓取图片**。

`POST /fetch` 的 `provider_stats` 可查看正文抓取结果：

```json
{
  "content_attempted": 15,
  "content_enriched": 11,
  "content_failed": 4
}
```

## 搜索

推荐 AI / 玩偶上层服务使用：

```bash
curl --get "http://localhost:8100/news/search" \
  --data-urlencode "q=机器人 人工智能" \
  --data-urlencode "tag=tech" \
  --data-urlencode "limit=5"
```

搜索索引覆盖：

- title
- summary
- source
- content

搜索结果按 BM25 相关性排序。

## 数据模型

```text
articles
   │
   ├──── article_topics
   │
   ├──── articles_fts
   │
   └──── legacy news shadow table
```

## 项目结构

```text
app/
├── domain/
│   ├── models.py
│   └── identity.py
├── providers/
│   ├── base.py
│   ├── registry.py
│   ├── zaker.py
│   └── content.py
├── podcast/
│   ├── prompt.py
│   ├── qwen.py
│   ├── models.py
│   └── service.py
├── repositories/
│   └── news.py
├── services/
│   └── ingestion.py
├── crawler/
│   └── zaker.py
├── routes/
│   ├── fetch.py
│   ├── news.py
│   ├── topics.py
│   ├── podcast.py
│   └── scheduler_route.py
├── database.py
├── scheduler.py
├── config.py
└── main.py

docs/
├── API_USAGE.md
└── architecture-v0.2.md
```

## 测试

```bash
PYTHONPATH=. python -m pytest -q
```

GitHub Actions 会在 PR 更新后自动执行同一测试集。


## 健康检查与管理鉴权

公开健康检查：

```text
GET /health/live
GET /health/ready
```

Provider 发现：

```text
GET /providers
```

生产环境建议设置：

```dotenv
NEWS_CENTER_ADMIN_API_KEY=replace-with-a-long-random-secret
```

设置后，以下管理接口必须携带：

```http
X-API-Key: replace-with-a-long-random-secret
```

受保护接口：

- `POST /fetch`
- `GET /scheduler/status`
- `POST /scheduler/config`
- `POST /scheduler/run`
- `POST /podcast/script`

未设置 `NEWS_CENTER_ADMIN_API_KEY` 时保持本地开发兼容模式，不要求 Key。

## Provider 扩展

默认 Provider：

```dotenv
NEWS_CENTER_DEFAULT_PROVIDER=zaker
```

Scheduler 配置可以持久化指定 Provider，`POST /fetch` 也可按请求选择 Provider。

新增数据源开发指南：

**[docs/PROVIDER_GUIDE.md](docs/PROVIDER_GUIDE.md)**

完整 API 与鉴权说明：

**[docs/API_USAGE.md](docs/API_USAGE.md)**
