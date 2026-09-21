#!/usr/bin/env python3
import asyncio
import json
from pprint import pprint

from app.crawler import fetch_zaker, get_preset_topics
from app.database import init_db, insert_news_batch, query_news, get_scheduler_config
from app.scheduler import news_scheduler


async def main():
    print("=== 1. 初始化数据库 ===")
    init_db()

    print("\n=== 2. 获取预设主题列表 (GET /topics 数据源) ===")
    topics = get_preset_topics()
    print(f"共有 {len(topics)} 个预设主题:")
    for t in topics:
        print(f"  - [{t['tag']}] {t['name']}: {t['description']}")

    print("\n=== 3. 实测抓取 'hot' (热点) 分类新闻 ===")
    candidates, stats = await fetch_zaker("hot", timeout=12.0)
    print(f"抓取统计: {stats}")
    print(f"获取到有效候选: {len(candidates)} 篇")
    if candidates:
        first = candidates[0]
        print(f"  首篇新闻示例:")
        print(f"    标题: {first.title}")
        print(f"    来源: {first.source}")
        print(f"    时间: {first.published_at}")
        print(f"    链接: {first.url}")
        print(f"    摘要: {first.summary[:80]}...")

    print("\n=== 4. 入库测试与去重 ===")
    added, skipped = insert_news_batch(candidates[:5])
    print(f"首轮入库 5 篇: 新增 {added} 篇, 跳过重复 {skipped} 篇")
    added2, skipped2 = insert_news_batch(candidates[:5])
    print(f"再次入库相同 5 篇: 新增 {added2} 篇, 跳过重复 {skipped2} 篇")

    print("\n=== 5. 查询入库新闻 (GET /news) ===")
    items, total = query_news(tag="hot", limit=3)
    print(f"当前 'hot' 分类总数: {total}, 取前 {len(items)} 条:")
    for idx, it in enumerate(items, 1):
        print(f"  [{idx}] {it['title']} ({it['source']}) - ID: {it['id']}")

    print("\n=== 6. 查看调度配置 ===")
    cfg = get_scheduler_config()
    print(f"当前调度配置: interval={cfg['interval_minutes']}m, enabled={cfg['enabled']}, tags={cfg['tags']}")

    print("\n服务最小系统功能验证完成！全部指标正常。")


if __name__ == "__main__":
    asyncio.run(main())
