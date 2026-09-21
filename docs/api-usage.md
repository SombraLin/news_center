# News Center V0.2 API 使用说明

本文面向调用 News Center 的前端、机器人、LLM 服务或其他后端服务。

默认服务地址：

```text
http://127.0.0.1:8100
```

Swagger：

```text
http://127.0.0.1:8100/docs
```

## 1. 推荐调用流程

典型调用链：

```text
1. GET /topics
        ↓
2. POST /fetch
        ↓
3. GET /news
        ↓
4. GET /news/search
        ↓
5. GET /news/{id}
```

含义：

- `/topics`：了解可用新闻分类。
- `/fetch`：主动抓取最新新闻。
- `/news`：按时间浏览新闻列表。
- `/news/search`：按内容相关性检索新闻。
- `/news/{id}`：读取单篇完整详情和正文。

## 2. 启动服务

安装：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

启动：

```bash
python -m app.main
```

或：

```bash
./run.sh
```

验证服务：

```bash
curl http://127.0.0.1:8100/
```

示例返回：

```json
{
  "service": "news_center",
  "status": "running",
  "docs_url": "/docs",
  "topics_url": "/topics",
  "news_url": "/news"
}
```

## 3. 查询支持的主题

```bash
curl http://127.0.0.1:8100/topics
```

主要 tag：

- `hot`
- `china`
- `world`
- `military`
- `finance`
- `internet`
- `tech`
- `auto`
- `sports`
- `entertainment`

每个主题返回当前文章数量 `article_count`。

## 4. 主动抓取新闻

单主题：

```bash
curl -X POST http://127.0.0.1:8100/fetch \
  -H "Content-Type: application/json" \
  -d '{
    "tag": "tech",
    "limit_per_tag": 10
  }'
```

多主题：

```bash
curl -X POST http://127.0.0.1:8100/fetch \
  -H "Content-Type: application/json" \
  -d '{
    "tags": ["hot", "tech", "finance"],
    "limit_per_tag": 10
  }'
```

显式指定 Provider：

```json
{
  "tag": "tech",
  "limit_per_tag": 10,
  "provider": "zaker"
}
```

成功返回核心字段：

```json
{
  "success": true,
  "status": "success",
  "total_added": 8,
  "total_skipped": 2,
  "results": {
    "tech": {
      "topic": "tech",
      "provider": "zaker",
      "fetched": 20,
      "valid": 15,
      "added": 8,
      "duplicate_history": 2,
      "error": null
    }
  }
}
```

`status`：

- `success`：所有主题处理成功。
- `partial`：部分主题失败。
- `failed`：所有主题失败。

注意：

- 正文抓取是 best-effort。
- 某篇详情页无法访问时，该新闻仍可凭标题和摘要正常入库。
- `content` 在这种情况下可能为 `null`。
- 当前版本明确不抓取图片。

## 5. 按时间查询新闻

最新科技新闻：

```bash
curl "http://127.0.0.1:8100/news?tag=tech&limit=20&offset=0"
```

保留的兼容关键词入口：

```bash
curl --get http://127.0.0.1:8100/news \
  --data-urlencode "keyword=人工智能"
```

当存在 `keyword` 时，内部使用 SQLite FTS5，而不是 SQL `LIKE`。

列表项主要字段：

```json
{
  "id": "article-id",
  "tag": "tech",
  "topics": ["hot", "tech"],
  "title": "新闻标题",
  "source": "新闻来源",
  "url": "原始文章地址",
  "canonical_url": "规范化地址",
  "summary": "摘要",
  "content": "正文；提取失败时可能为 null",
  "language": "zh-CN",
  "provider": "zaker",
  "published_at": "2026-09-21T03:20:00+00:00",
  "fetched_at": "2026-09-21T05:00:00+00:00",
  "updated_at": "2026-09-21T05:00:00+00:00"
}
```

## 6. 全文搜索

推荐搜索入口：

```bash
curl --get http://127.0.0.1:8100/news/search \
  --data-urlencode "q=人工智能"
```

限定科技主题：

```bash
curl --get http://127.0.0.1:8100/news/search \
  --data-urlencode "q=机器人" \
  --data-urlencode "tag=tech" \
  --data-urlencode "limit=10"
```

搜索范围：

- title
- summary
- source
- content

搜索结果按 BM25 相关性排序，而不是发布时间排序。

对于少于 3 个字符的短查询（例如 `AI`），服务会自动退回安全的普通字段匹配，以避免 trigram tokenizer 的短词限制；调用方无需区分两种模式。

额外字段：

```json
{
  "relevance": -3.21,
  "match_snippet": "……<mark>人工智能</mark>……"
}
```

说明：

- SQLite FTS5 的 BM25 数值越小通常代表匹配越靠前。
- 调用方应使用接口返回顺序，不建议自行根据 `relevance` 数值重新排序。
- `match_snippet` 可能包含 `<mark>` 标签，前端可以用于高亮；语音/LLM 调用方可自行去除标签。

## 7. 获取单篇详情

```bash
curl http://127.0.0.1:8100/news/<article_id>
```

推荐上层 AI 工作流：

```text
用户问题
  ↓
/news/search?q=...
  ↓
取前 3~5 条
  ↓
/news/{id}
  ↓
使用 content / summary 做后续理解、改写或播报
```

News Center 自身不负责：

- LLM 摘要
- 儿童化改写
- 个性化推荐
- TTS
- 图片抓取

## 8. 定时抓取

查看状态：

```bash
curl http://127.0.0.1:8100/scheduler/status
```

更新：

```bash
curl -X POST http://127.0.0.1:8100/scheduler/config \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "interval_minutes": 30,
    "tags": ["hot", "tech", "finance"]
  }'
```

立即执行一轮：

```bash
curl -X POST http://127.0.0.1:8100/scheduler/run
```

## 9. 正文抓取配置

环境变量：

```bash
NEWS_CENTER_CONTENT_FETCH_ENABLED=true
NEWS_CENTER_CONTENT_FETCH_TIMEOUT_SECONDS=8
NEWS_CENTER_CONTENT_FETCH_CONCURRENCY=4
NEWS_CENTER_CONTENT_MAX_CHARS=30000
```

含义：

- `CONTENT_FETCH_ENABLED`：是否抓取文章正文。
- `CONTENT_FETCH_TIMEOUT_SECONDS`：单篇正文页面 HTTP 超时。
- `CONTENT_FETCH_CONCURRENCY`：同一批次最多同时抓取多少详情页。
- `CONTENT_MAX_CHARS`：每篇正文最大保存字符数。

若希望只抓标题和摘要：

```bash
NEWS_CENTER_CONTENT_FETCH_ENABLED=false
```

## 10. 分页建议

时间流：

```text
GET /news?limit=20&offset=0
GET /news?limit=20&offset=20
GET /news?limit=20&offset=40
```

搜索：

```text
GET /news/search?q=AI&limit=20&offset=0
GET /news/search?q=AI&limit=20&offset=20
```

当前 V0.2 使用 offset 分页。数据量显著增长后再考虑 cursor pagination。

## 11. 常见错误

### 400 不支持的 tag

例如：

```text
/news?tag=unknown
```

或：

```json
{
  "tag": "unknown"
}
```

会返回 `400`。

### 404 新闻不存在

```text
GET /news/not-exists
```

返回 `404`。

### /fetch success=false

这表示 Provider 抓取失败，不表示 FastAPI 服务本身不可访问。查看：

- `status`
- `results.<topic>.error`

定位来源侧错误。

## 12. 接口可用性测试

仓库 CI 会执行：

```bash
python -m pytest -q
```

其中包含完整无外网依赖的接口链路测试：

```text
POST /fetch
   ↓
GET /news
   ↓
GET /news/search
   ↓
GET /news/{id}
```

测试同时验证：

- 正文可以入库；
- 正文关键词可以进入 FTS5；
- 搜索结果可以取得文章 ID；
- 文章详情可以正常读取。
