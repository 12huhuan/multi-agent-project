#!/usr/bin/env python3
"""
Listing 生成工作流 — 命令行测试脚本

用法: 从项目根目录执行
    python scripts/run_listing.py                    # 交互式选择产品
    python scripts/run_listing.py --product 0         # 蓝牙耳机
    python scripts/run_listing.py --product 1         # 瑜伽垫
    python scripts/run_listing.py --product 2         # 台灯
    python scripts/run_listing.py --product 0 --skip-review  # 跳过人工审核

6 个 Agent 链:
  关键词研究 → 标题生成 → 五点描述 → 长描述 → A+内容 → SEO评分 → 人工审核
"""

import argparse
import asyncio
import json
import os
import sys
import time
import uuid

# 确保项目根在 sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)


def load_products():
    path = os.path.join(PROJECT_ROOT, "scripts", "sample_products.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def print_header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_keywords(state: dict):
    print_header("1. 关键词研究结果")
    kws = state.get("keywords", [])
    top = state.get("top_keywords", [])
    print(f"  Top 5: {', '.join(top)}")
    print(f"  共发现 {len(kws)} 个关键词:")
    for kw in kws[:10]:
        print(f"    [{kw.get('search_volume_level','?'):6s}] [{kw.get('competition_level','?'):6s}] "
              f"{kw.get('keyword','?'):40s} (relevance: {kw.get('relevance_score',0)})")
    if len(kws) > 10:
        print(f"    ... 还有 {len(kws)-10} 个")


def print_titles(state: dict):
    print_header("2. 标题候选")
    print(f"  推荐: {state.get('best_title', '')}")
    for i, t in enumerate(state.get("title_candidates", [])):
        print(f"\n  候选 {i+1} (评分: {t.get('score', 0)})")
        print(f"  {t.get('title', '')}")
        print(f"  字符数: {t.get('char_count', 0)}, 合规问题: {t.get('compliance_issues', [])}")


def print_bullets(state: dict):
    print_header("3. 五点描述")
    for i, bp in enumerate(state.get("bullet_points", []), 1):
        print(f"  {i}. {bp.get('text', '')}")
        print(f"     功能: {bp.get('feature_highlighted', '')} → 利益: {bp.get('benefit_highlighted', '')}")


def print_seo(state: dict):
    print_header("6. SEO 评分报告")
    seo = state.get("seo_report", {})
    print(f"  总分: {seo.get('overall_score', 0)}/100")
    for dim in ["keyword_density", "readability", "completeness", "conversion_potential"]:
        d = seo.get(dim, {})
        print(f"  {dim}: {d.get('score', 0)}/100")
        for s in d.get("suggestions", [])[:2]:
            print(f"    → {s}")
    print(f"  改进优先级: {seo.get('improvement_priority', [])}")


def print_full_report(state: dict, duration_s: float):
    print_header(f"LISTING 生成完成 (耗时 {duration_s:.1f}s)")
    print_keywords(state)
    print_titles(state)
    print_bullets(state)
    print(f"\n  4. 长描述: {len(state.get('description_html', ''))} 字符 HTML")
    print(f"  5. A+ 模块: {len(state.get('a_plus_modules', []))} 个模块")
    print_seo(state)


async def run_workflow(product: dict, skip_review: bool = False):
    """执行完整 Listing 工作流"""
    from backend.app.workflows.listing_workflow import listing_workflow, ListingState

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    print_header(f"产品: {product['product_name']}")
    print(f"  品类: {product['category']}")
    print(f"  特性: {len(product['features'])} 条")
    print(f"  平台: {product['target_platform']} / {product['target_language']}")

    initial_state: ListingState = {
        "task_id": thread_id,
        "product_name": product["product_name"],
        "category": product["category"],
        "features": product["features"],
        "brand_story": product.get("brand_story"),
        "image_descriptions": product.get("image_descriptions", []),
        "target_platform": product["target_platform"],
        "target_language": product["target_language"],
        "keywords": [],
        "top_keywords": [],
        "title_candidates": [],
        "best_title": "",
        "bullet_points": [],
        "description_html": "",
        "a_plus_modules": [],
        "seo_report": {},
        "status": "running",
        "error": "",
        "current_step": "started",
    }

    t0 = time.time()

    # 第一轮: 执行 6 个 Agent
    print("\n  [1/6] 关键词研究...")
    final_state = await listing_workflow.ainvoke(initial_state, config)

    if final_state.get("status") == "failed":
        print(f"\n  ✗ 失败: {final_state.get('error', '未知错误')}")
        return None

    # 打印中间结果
    print_keywords(final_state)
    print_titles(final_state)
    print_bullets(final_state)
    print(f"\n  4. 长描述: {len(final_state.get('description_html', ''))} 字符 (已生成)")
    print(f"  5. A+ 模块: {len(final_state.get('a_plus_modules', []))} 个 (已生成)")

    duration = time.time() - t0

    # 第二轮: 人工审核 (workflow 在 seo_scoring 后中断)
    if not skip_review:
        print(f"\n{'─'*60}")
        print(f"  工作流已暂停，等待人工审核 (耗时 {duration:.1f}s)")
        print(f"  状态: {final_state.get('status', '')}")
        print(f"{'─'*60}")

        while True:
            choice = input("\n  [A]批准 / [R]驳回 / [S]跳过(直接完成): ").strip().lower()
            if choice == "a":
                final_state["status"] = "completed"
                break
            elif choice == "r":
                note = input("  驳回原因: ").strip() or "需修改"
                final_state["status"] = "rejected"
                final_state["error"] = note
                break
            elif choice == "s":
                break
            else:
                print("  请输入 A/R/S")

        # 恢复工作流（移到 END）
        try:
            final_state = await listing_workflow.ainvoke(None, config)
        except Exception:
            pass  # 工作流已结束

    duration = time.time() - t0
    print_seo(final_state)
    print_full_report(final_state, duration)

    return final_state


async def main():
    parser = argparse.ArgumentParser(description="Listing 生成工作流")
    parser.add_argument("--product", type=int, default=None, help="产品索引 (0-2)")
    parser.add_argument("--skip-review", action="store_true", help="跳过人工审核")
    args = parser.parse_args()

    products = load_products()

    if args.product is not None:
        if 0 <= args.product < len(products):
            selected = products[args.product]
        else:
            print(f"无效索引, 可选 0-{len(products)-1}")
            return
    else:
        print("\n  可用产品:")
        for i, p in enumerate(products):
            print(f"    [{i}] {p['name']}: {p['product_name'][:60]}...")
        choice = input("\n  选择产品 (0-2): ").strip()
        try:
            selected = products[int(choice)]
        except (ValueError, IndexError):
            print("  无效选择")
            return

    state = await run_workflow(selected, args.skip_review)

    # 保存结果
    output_path = os.path.join(PROJECT_ROOT, "scripts", f"output_{selected['name'].replace(' ', '_')}.json")
    if state:
        # 清理不可序列化的字段
        save_state = {k: v for k, v in state.items() if isinstance(v, (str, int, float, list, dict, bool, type(None)))}
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(save_state, f, ensure_ascii=False, indent=2)
        print(f"\n  结果已保存: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
