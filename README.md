# News Center (新闻中心服务)

轻量、独立的定时新闻抓取与文字内容检索后端微服务。

- **职责单一**：专注于新闻抓取、去重持久化与按主题检索文字内容，不耦合 LLM 改写或音频合成；
- **主题预设明确**：内置 10 大已验证的 Zaker 新闻主题，提供 `/topics` 接口供用户或前端直接选择，调用方无需盲猜；
- **内嵌定时调度**：基于 APScheduler 实现单进程轻量级定时轮询抓取，无需外部 Celery 或 Cron 依赖；
- **配置热更新持久化**：定时任务周期、启停状态、抓取主题存放在 SQLite 中，修改即刻生效且重启不丢失；
- **去重与自动清理**：基于新闻原始 URL 自动去重，支持配置自动清理超过 N 天的过期新闻。

---

## 1. 预设新闻主题 (10大分类)

通过 `GET /topics` 即可获取全部可选主题：

| Tag | 主题中文名 | 描述 |
|---|---|---|
| `hot` | 热点 | 实时热门资讯与高关注度全网头条 |
| `china` | 国内 | 国内重点政经要闻与社会焦点新闻 |
| `world` | 国际 | 全球国际要闻、大国外交与重大突发事件 |
| `military` | 军事 | 国防军工、战略演练与国际安全动态 |
| `finance` | 财经 | 宏观经济、股市投资、商业地产与产业理财 |
| `internet` | 互联网 | 互联网科技巨头、商业模式与创投动向 |
| `tech` | 科技 | 数码电子、人工智能、硬核前沿技术创新 |
| `auto` | 汽车 | 新能源汽车、行业新车发布与智能座舱技术 |
| `sports` | 体育 | 足球、篮球、综合赛事、奥运热点与体坛风云 |
| `entertainment` | 娱乐 | 影视剧评、文化演出与文娱动态 |

---

## 2. 接口列表 (RESTful API)

交互式文档请访问服务启动后的: `http://localhost:8100/docs`

### 2.1 主题选择
- **`GET /topics`**
  - 获取所有预设主题列表以及当前各主题在数据库中的存量文章数。

### 2.2 新闻查询
- **`GET /news`**
  - 参数：
    - `tag` (可选): 按主题过滤，例如 `?tag=tech`
    - `keyword` (可选): 按标题或摘要内容模糊搜索
    - `limit` (可选): 分页每页数量，默认 20，最大 100
    - `offset` (可选): 分页偏移量，默认 0
  - 返回按发布时间倒序排列的新闻列表与总记录数。
- **`GET /news/{id}`**
  - 根据唯一 ID 获取单篇新闻详情。

### 2.3 按需手动抓取
- **`POST /fetch`**
  - 请求示例：
    ```json
    {
      "tag": "tech",
      "limit_per_tag": 10
    }
    ```
    或批量主题抓取：
    ```json
    {
      "tags": ["china", "world", "finance"],
      "limit_per_tag": 5
    }
    ```
  - 即时抓取并入库，返回入库增量与跳过重复统计。

### 2.4 定时调度控制
- **`GET /scheduler/status`**
  - 查看当前调度器启停状态、抓取周期、下一次运行时间与上一次运行执行报告。
- **`POST /scheduler/config`**
  - 请求示例：
    ```json
    {
      "enabled": true,
      "interval_minutes": 30,
      "tags": ["hot", "china", "world", "tech", "finance"]
    }
    ```
  - 动态热更新调度器参数，并在 SQLite 中持久化。
- **`POST /scheduler/run`**
  - 立即手动触发一轮全量定时任务。

---

## 3. 项目结构

```
news_center/
├── app/
│   ├── __init__.py
│   ├── config.py           # 环境变量与默认参数配置
│   ├── database.py         # SQLite 数据库模型、CRUD与自动建表
│   ├── crawler/
│   │   ├── __init__.py
│   │   └── zaker.py        # 独立无依赖的 Zaker 抓取实现与 10 大主题预设
│   ├── scheduler.py        # APScheduler 定时轮询调度管理器
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── topics.py       # GET /topics
│   │   ├── news.py         # GET /news, GET /news/{id}
│   │   ├── fetch.py        # POST /fetch
│   │   └── scheduler_route.py # GET/POST /scheduler/*
│   └── main.py             # FastAPI 应用入口与生命周期管理
├── data/                   # 存放 SQLite 数据库文件 (news.db)
├── tests/
│   └── test_api.py         # 单元与接口自动化测试
├── .env.example            # 配置项模板
├── requirements.txt        # 依赖清单
└── run.sh                  # 一键启动脚本
```

---

## 4. 快速开始

### 4.1 安装依赖
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4.2 运行服务
```bash
./run.sh
# 或者
source .venv/bin/activate
python -m app.main
```
服务默认监听在 `http://0.0.0.0:8100`。

### 4.3 运行测试
```bash
source .venv/bin/activate
pytest tests/
```
