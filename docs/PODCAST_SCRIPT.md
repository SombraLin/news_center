# Podcast Script 模块使用说明

本模块用于把手工粘贴的新闻 JSON 交给阿里云百炼 / Model Studio 的 **Qwen-Plus**，整理成可继续复制到豆包音频生成模型的双主播新闻播客文案。

## 1. 模块边界

当前流程刻意保持手工、解耦：

```text
News Center 新闻抓取
        ↓
GET /news/text?tag=hot&limit=20
        ↓
手工复制长文本
        ↓
POST /podcast/script
        ↓
Qwen-Plus 整理
        ↓
返回双主播播客文案
        ↓
手工复制 script
        ↓
豆包音频生成 API
```

Podcast Script 模块：

- 不读取 News Center 数据库；
- 不调用 `/fetch`；
- 不依赖 crawler / repository / scheduler；
- 不自动调用豆包音频接口；
- 只负责 **手工新闻输入 → Qwen-Plus → 播客文案**。

推荐优先使用纯文本流程；JSON 输入继续保留用于兼容。

因此未来可以独立替换新闻源、LLM 或音频模型。

## 2. Qwen 配置

阿里云 Model Studio OpenAI-compatible Chat Completions：

- 模型固定使用：`qwen-plus`
- 默认 Base URL：

```text
https://dashscope.aliyuncs.com/compatible-mode/v1
```

配置 `.env`：

```dotenv
DASHSCOPE_API_KEY=sk-your-api-key

NEWS_CENTER_QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
NEWS_CENTER_QWEN_TIMEOUT_SECONDS=90
NEWS_CENTER_PODCAST_MAX_ARTICLES=20
NEWS_CENTER_PODCAST_MAX_ARTICLE_CHARS=2500
```

也可以使用：

```dotenv
NEWS_CENTER_QWEN_API_KEY=sk-your-api-key
```

当两个 Key 都存在时，`NEWS_CENTER_QWEN_API_KEY` 优先。

生产环境如果使用阿里云 workspace 专属域名，可直接修改 `NEWS_CENTER_QWEN_BASE_URL`。

阿里云官方说明：

<https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions>

## 3. 推荐操作：直接获取 hot 最新 20 条长文本

先确保热点新闻已经存在于 News Center。

推荐查询：

```bash
curl "http://localhost:8100/news/text?tag=hot&limit=20&offset=0"
```

该接口返回 `text/plain`，不是 JSON，内容类似：

```text
新闻主题：hot
新闻数量：20

【新闻 1】
标题：……
来源：……
发布时间：……
摘要：……
正文：
……

----------------------------------------

【新闻 2】
……
```

默认每篇正文最多输出 2500 字，可调整：

```bash
curl "http://localhost:8100/news/text?tag=hot&limit=20&max_content_chars=5000"
```

如果仍需要 JSON，原接口继续可用：

```bash
curl "http://localhost:8100/news?tag=hot&limit=20&offset=0"
```

JSON 会返回类似：

```json
{
  "total": 100,
  "limit": 20,
  "offset": 0,
  "count": 20,
  "items": [
    {
      "id": "ARTICLE_ID",
      "tag": "hot",
      "topics": ["hot"],
      "title": "新闻标题",
      "source": "新闻来源",
      "summary": "摘要",
      "content": "正文",
      "published_at": "2026-09-21T08:00:00+00:00"
    }
  ]
}
```

对于推荐的纯文本流程，直接复制 `/news/text` 的整个响应即可。

对于 JSON 流程，仍可复制整个返回对象，不需要自己只截取 `items`。

## 4. 调用播客文案接口

接口：

```text
POST /podcast/script
```

在 Swagger：

```text
http://localhost:8100/docs
```

找到 **播客文案 → POST /podcast/script**。

推荐的纯文本请求：

```json
{
  "news_text": "新闻主题：hot\n新闻数量：20\n\n【新闻 1】\n标题：……\n来源：……\n摘要：……\n正文：\n……",
  "target_minutes": 8,
  "episode_title": null
}
```

兼容的 JSON 请求：

```json
{
  "news": {
    "total": 100,
    "limit": 20,
    "offset": 0,
    "count": 20,
    "items": [
      {
        "title": "示例热点新闻",
        "source": "示例来源",
        "summary": "摘要",
        "content": "正文",
        "published_at": "2026-09-21T08:00:00+00:00",
        "tag": "hot"
      }
    ]
  },
  "target_minutes": 8,
  "episode_title": null
}
```

输入方式二选一：

- `news_text`：推荐，直接粘贴 `GET /news/text` 的长文本；
- `news`：兼容模式，可粘贴 `GET /news` 的完整返回对象、文章数组或对应 JSON 字符串。

`news` 与 `news_text` 不能同时提供。

如果传入超过 20 条，模块会按照：

1. `published_at`
2. `publish_time`
3. `fetched_at`
4. `updated_at`

从新到旧选择最多 20 条，并进行基础去重。

## 5. curl 示例

假设已经保存了请求到 `podcast-request.json`：

```bash
curl -X POST "http://localhost:8100/podcast/script" \
  -H "Content-Type: application/json" \
  --data-binary @podcast-request.json
```

如果配置了：

```dotenv
NEWS_CENTER_ADMIN_API_KEY=YOUR_SECRET
```

则需要：

```bash
curl -X POST "http://localhost:8100/podcast/script" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_SECRET" \
  --data-binary @podcast-request.json
```

由于 Qwen 调用会产生模型费用，因此生产环境建议开启管理 API Key。

## 6. 返回格式

示例：

```json
{
  "script": "主播 1 是成年男性……\n\n主播 2 是年轻女性……\n\n主播 1 语调平缓：“……”",
  "model": "qwen-plus",
  "received_count": 20,
  "selected_count": 20,
  "source_titles": [
    "新闻标题 A",
    "新闻标题 B"
  ],
  "usage": {
    "prompt_tokens": 5000,
    "completion_tokens": 1800,
    "total_tokens": 6800
  },
  "request_id": "..."
}
```

主要关注：

- `script`：最终可复制播客文案；
- `selected_count`：实际交给 Qwen 的新闻数量；
- `source_titles`：本轮使用的文章标题，方便人工核查；
- `usage`：Qwen 返回的 Token 使用量。

## 7. 固定主播设定

服务端固定前置：

```text
主播 1 是成年男性，嗓音低沉，略带沙哑，吐字清晰，语速略微偏快

主播 2 是年轻女性，嗓音偏御，略哑，略微低沉
```

这两行不是让 Qwen 自由生成，而是由程序确定性添加，避免模型每次改写音色描述。

Qwen 主要负责生成后续类似：

```text
主播 1 语调平缓：“今天先从最受关注的一组消息聊起……”

主播 2 稍微有点沙哑，简短地接着说：“这个变化确实值得关注。”

主播 1 略微提高语气，以解释的口吻说道：“再往下看……”
```

的对话正文。

## 8. Qwen 的编辑规则

Prompt 已固定以下原则：

- 只使用输入 JSON 中明确存在的事实；
- 不虚构人物原话；
- 不虚构数字、日期、地点、原因或结论；
- 相同事件的多篇新闻合并整理；
- 优先热点与影响范围较大的事件；
- 不机械逐条朗读 20 条新闻；
- 主播 1 承担约 65%-75% 信息量；
- 主播 2 负责追问、补充、承接；
- 使用自然的语调、停顿和少量强调提示；
- 不输出 Markdown、JSON、SSML 或模型参数。

如果素材不足以支撑目标时长，要求模型宁可缩短，不允许为了时长编造内容。

## 9. 目标时长

默认：

```json
{
  "target_minutes": 8
}
```

允许范围：

```text
3 - 20 分钟
```

系统会按约 240 个中文字符/分钟给 Qwen 一个目标文本区间，但这是写作参考，不是严格音频时长保证。

实际音频时长仍取决于豆包音频模型的语速、停顿和演绎。

## 10. 手工复制到豆包

本项目当前不会调用豆包音频 API。

拿到响应以后：

1. 复制响应中的 `script`；
2. 作为音频生成文案提交给豆包音频生成模型；
3. 音频参数、声音生成任务由独立模块或人工请求负责。

豆包音频生成官方文档：

<https://docs.volcengine.com/docs/DoubaoVoice/audio-generation-http?lang=zh>

这样保持：

```text
新闻数据
  ≠
LLM 内容编辑
  ≠
音频生成
```

三个模块彼此独立。

## 11. 常见错误

### HTTP 400

新闻 JSON 无法解析，例如：

- 不是有效 JSON；
- 没有 `items/news/articles` 数组；
- 数组内没有有效 `title`。

### HTTP 401

配置了 `NEWS_CENTER_ADMIN_API_KEY`，但请求没有正确携带 `X-API-Key`。

### HTTP 503

没有配置 Qwen API Key。

检查：

```dotenv
DASHSCOPE_API_KEY=
```

或：

```dotenv
NEWS_CENTER_QWEN_API_KEY=
```

### HTTP 502

News Center 已正常收到请求，但调用阿里云 Qwen API 失败。

常见原因：

- API Key 与区域不匹配；
- Base URL 配置错误；
- workspace 权限问题；
- Qwen 服务返回限流或其他错误。

## 12. 当前刻意不做的事情

本阶段不实现：

- hot fetch 完成后自动触发 Qwen；
- News Center 内部直接读取 hot 20 条并生成播客；
- 自动调用豆包生成音频；
- 自动保存播客文案到数据库；
- 自动发布播客；
- 图片处理。

这些都可以在后续独立模块中按需要逐步增加。
