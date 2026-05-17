"""广告管理 API — 实时监控 + 一键优化（stateful，优化前后可见变化）"""

import copy
from datetime import datetime, timezone

from fastapi import APIRouter
from backend.app.agents.ads.performance_analyzer import (
    PerformanceAnalyzerAgent, PerformanceAnalyzerInput, AdCampaign,
)
from backend.app.agents.ads.bid_optimizer import (
    BidOptimizerAgent, BidOptimizerInput, KeywordMetric,
)
from backend.app.agents.ads.budget_allocator import (
    BudgetAllocatorAgent, BudgetAllocatorInput,
)

router = APIRouter(prefix="/api/v1/ads", tags=["ads"])

# ── Stateful 广告数据（优化会直接修改，Dashboard 可见变化）──
_campaigns: list[dict] = [
    {"id":"camp_1","name":"蓝牙耳机-主力词","platform":"amazon","budget":200,"spend":187,"sales":680,
     "impressions":12000,"clicks":320,"orders":22,"acos":27.5,"roas":3.64,"ctr":2.67,
     "cpc":0.58,"conversion_rate":6.88,"status":"active"},
    {"id":"camp_2","name":"蓝牙耳机-长尾词","platform":"amazon","budget":100,"spend":89,"sales":410,
     "impressions":8000,"clicks":180,"orders":15,"acos":21.7,"roas":4.61,"ctr":2.25,
     "cpc":0.49,"conversion_rate":8.33,"status":"active"},
    {"id":"camp_3","name":"无线耳机-自动投放","platform":"amazon","budget":150,"spend":165,"sales":280,
     "impressions":25000,"clicks":550,"orders":8,"acos":58.9,"roas":1.70,"ctr":2.20,
     "cpc":0.30,"conversion_rate":1.45,"status":"active"},
    {"id":"camp_4","name":"降噪耳机-竞品词","platform":"amazon","budget":50,"spend":42,"sales":95,
     "impressions":3000,"clicks":95,"orders":3,"acos":44.2,"roas":2.26,"ctr":3.17,
     "cpc":0.44,"conversion_rate":3.16,"status":"active"},
]

_keywords: list[dict] = [
    {"keyword":"bluetooth headphones","campaign_id":"camp_1","match_type":"exact",
     "current_bid":0.75,"spend":85,"sales":320,"acos":26.6,"clicks":150,"orders":10,"conversion_rate":6.67},
    {"keyword":"wireless headphones","campaign_id":"camp_1","match_type":"phrase",
     "current_bid":0.65,"spend":62,"sales":210,"acos":29.5,"clicks":100,"orders":7,"conversion_rate":7.0},
    {"keyword":"bluetooth earbuds long battery","campaign_id":"camp_2","match_type":"broad",
     "current_bid":0.55,"spend":45,"sales":240,"acos":18.8,"clicks":90,"orders":9,"conversion_rate":10.0},
    {"keyword":"noise cancelling headphones","campaign_id":"camp_3","match_type":"broad",
     "current_bid":0.80,"spend":120,"sales":150,"acos":80.0,"clicks":400,"orders":2,"conversion_rate":0.5},
    {"keyword":"headphone","campaign_id":"camp_3","match_type":"broad",
     "current_bid":0.40,"spend":45,"sales":130,"acos":34.6,"clicks":150,"orders":6,"conversion_rate":4.0},
    {"keyword":"sony headphone alternative","campaign_id":"camp_4","match_type":"phrase",
     "current_bid":1.20,"spend":42,"sales":95,"acos":44.2,"clicks":95,"orders":3,"conversion_rate":3.16},
]

_optimization_log: list[dict] = []


def _snapshot(label: str = "") -> dict:
    return {"label": label, "campaigns": copy.deepcopy(_campaigns), "keywords": copy.deepcopy(_keywords)}


def _apply_bids(suggestions: list) -> int:
    changed = 0
    kw_map = {k["keyword"]: k for k in _keywords}
    for s in suggestions:
        kw = kw_map.get(s.get("keyword", ""))
        if not kw: continue
        old = kw["current_bid"]
        if s.get("action") == "pause":
            kw["current_bid"] = 0
        else:
            kw["current_bid"] = s.get("suggested_bid", old)
        if kw["current_bid"] != old:
            changed += 1
    return changed


def _apply_budgets(allocations: list) -> int:
    changed = 0
    camp_map = {c["name"]: c for c in _campaigns}
    for a in allocations:
        camp = camp_map.get(a.get("campaign_name", ""))
        if camp:
            old = camp["budget"]
            camp["budget"] = a.get("suggested_budget", old)
            if camp["budget"] != old:
                changed += 1
    return changed


# ── API ───────────────────────────────

@router.get("/dashboard")
async def ads_dashboard():
    total_spend = sum(c["spend"] for c in _campaigns)
    total_sales = sum(c["sales"] for c in _campaigns)
    total_orders = sum(c["orders"] for c in _campaigns)
    overall_acos = round(total_spend / total_sales * 100, 1) if total_sales else 0
    overall_roas = round(total_sales / total_spend, 2) if total_spend else 0
    return {
        "overview": {"total_spend": total_spend, "total_sales": total_sales,
                     "total_orders": total_orders, "overall_acos": overall_acos,
                     "overall_roas": overall_roas, "active_campaigns": len(_campaigns)},
        "campaigns": _campaigns,
        "keywords": _keywords,
    }


@router.post("/analyze")
async def analyze_performance():
    agent = PerformanceAnalyzerAgent()
    result = await agent.run(PerformanceAnalyzerInput(
        campaigns=[AdCampaign(**c) for c in _campaigns], target_acos=30.0,
    ))
    return result.model_dump()


@router.post("/full-optimize")
async def full_optimize():
    """一键全优化：分析 → 竞价(应用) → 预算(应用) → 返回前后对比"""
    before = _snapshot("优化前")

    # 1. 分析
    perf_agent = PerformanceAnalyzerAgent()
    perf_result = await perf_agent.run(PerformanceAnalyzerInput(
        campaigns=[AdCampaign(**c) for c in _campaigns], target_acos=30.0,
    ))

    # 2. 竞价优化 → 立即应用
    bid_agent = BidOptimizerAgent()
    bid_result = await bid_agent.run(BidOptimizerInput(
        keywords=[KeywordMetric(**k) for k in _keywords], target_acos=30.0,
    ))
    bid_suggestions = [s.model_dump() for s in bid_result.suggestions]
    bid_changed = _apply_bids(bid_suggestions)

    # 3. 预算分配 → 立即应用
    budget_agent = BudgetAllocatorAgent()
    budget_result = await budget_agent.run(BudgetAllocatorInput(
        campaigns=copy.deepcopy(_campaigns), total_budget=500, target_acos=30.0,
    ))
    budget_allocations = [a.model_dump() for a in budget_result.allocations]
    budget_changed = _apply_budgets(budget_allocations)

    after = _snapshot("优化后")

    # 记录历史
    _optimization_log.insert(0, {
        "id": str(int(datetime.now(timezone.utc).timestamp())),
        "time": datetime.now(timezone.utc).isoformat(),
        "bid_changes": bid_changed,
        "budget_changes": budget_changed,
        "bid_suggestions": bid_suggestions,
        "budget_allocations": budget_allocations,
        "savings": bid_result.total_estimated_savings,
    })

    return {
        "analysis": {
            "overall_health": perf_result.overall_health,
            "overall_acos": perf_result.overall_acos,
            "overall_roas": perf_result.overall_roas,
            "insights": [i.model_dump() for i in perf_result.campaign_insights],
        },
        "bid_optimization": {
            "applied": bid_changed,
            "suggestions": bid_suggestions,
            "savings_per_day": bid_result.total_estimated_savings,
        },
        "budget_allocation": {
            "applied": budget_changed,
            "allocations": budget_allocations,
        },
        "before": before,
        "after": after,
        "summary": (
            f"ACOS {perf_result.overall_acos}% | "
            f"竞价调整 {bid_changed} 个关键词（预估日省${bid_result.total_estimated_savings:.0f}）| "
            f"预算重分配 {budget_changed} 个活动"
        ),
    }


@router.get("/optimization-log")
async def get_optimization_log():
    return _optimization_log


@router.post("/reset")
async def reset():
    """重置为初始 mock 数据"""
    import importlib
    import backend.app.api.ads as mod
    importlib.reload(mod)
    return {"status": "reset"}
