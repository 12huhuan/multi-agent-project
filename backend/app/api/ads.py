"""广告管理 API 路由 — 效果分析 + 竞价优化 + 预算分配"""

import uuid
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


def _mock_campaigns() -> list[AdCampaign]:
    """生成模拟广告数据"""
    return [
        AdCampaign(id="camp_1", name="蓝牙耳机-主力词", platform="amazon",
                   budget=200, spend=187, sales=680, impressions=12000,
                   clicks=320, orders=22, acos=27.5, roas=3.64, ctr=2.67,
                   cpc=0.58, conversion_rate=6.88),
        AdCampaign(id="camp_2", name="蓝牙耳机-长尾词", platform="amazon",
                   budget=100, spend=89, sales=410, impressions=8000,
                   clicks=180, orders=15, acos=21.7, roas=4.61, ctr=2.25,
                   cpc=0.49, conversion_rate=8.33),
        AdCampaign(id="camp_3", name="无线耳机-自动投放", platform="amazon",
                   budget=150, spend=165, sales=280, impressions=25000,
                   clicks=550, orders=8, acos=58.9, roas=1.70, ctr=2.20,
                   cpc=0.30, conversion_rate=1.45),
        AdCampaign(id="camp_4", name="降噪耳机-竞品词", platform="amazon",
                   budget=50, spend=42, sales=95, impressions=3000,
                   clicks=95, orders=3, acos=44.2, roas=2.26, ctr=3.17,
                   cpc=0.44, conversion_rate=3.16),
    ]


def _mock_keywords() -> list[KeywordMetric]:
    """生成模拟关键词数据"""
    return [
        KeywordMetric(keyword="bluetooth headphones", campaign_id="camp_1",
                      match_type="exact", current_bid=0.75, spend=85, sales=320,
                      acos=26.6, clicks=150, orders=10, conversion_rate=6.67),
        KeywordMetric(keyword="wireless headphones", campaign_id="camp_1",
                      match_type="phrase", current_bid=0.65, spend=62, sales=210,
                      acos=29.5, clicks=100, orders=7, conversion_rate=7.0),
        KeywordMetric(keyword="bluetooth earbuds long battery", campaign_id="camp_2",
                      match_type="broad", current_bid=0.55, spend=45, sales=240,
                      acos=18.8, clicks=90, orders=9, conversion_rate=10.0),
        KeywordMetric(keyword="noise cancelling headphones", campaign_id="camp_3",
                      match_type="broad", current_bid=0.80, spend=120, sales=150,
                      acos=80.0, clicks=400, orders=2, conversion_rate=0.5),
        KeywordMetric(keyword="headphone", campaign_id="camp_3",
                      match_type="broad", current_bid=0.40, spend=45, sales=130,
                      acos=34.6, clicks=150, orders=6, conversion_rate=4.0),
        KeywordMetric(keyword="sony headphone alternative", campaign_id="camp_4",
                      match_type="phrase", current_bid=1.20, spend=42, sales=95,
                      acos=44.2, clicks=95, orders=3, conversion_rate=3.16),
    ]


@router.get("/dashboard")
async def ads_dashboard():
    """广告仪表盘概览"""
    campaigns = _mock_campaigns()
    total_spend = sum(c.spend for c in campaigns)
    total_sales = sum(c.sales for c in campaigns)
    total_orders = sum(c.orders for c in campaigns)
    overall_acos = round(total_spend / total_sales * 100, 1) if total_sales > 0 else 0
    overall_roas = round(total_sales / total_spend, 2) if total_spend > 0 else 0

    return {
        "overview": {
            "total_spend": total_spend, "total_sales": total_sales,
            "total_orders": total_orders, "overall_acos": overall_acos,
            "overall_roas": overall_roas, "active_campaigns": len(campaigns),
        },
        "campaigns": [c.model_dump() for c in campaigns],
    }


@router.post("/analyze")
async def analyze_performance():
    """分析广告效果，识别问题"""
    agent = PerformanceAnalyzerAgent()
    result = await agent.run(PerformanceAnalyzerInput(
        campaigns=_mock_campaigns(), target_acos=30.0,
    ))
    return result.model_dump()


@router.post("/optimize-bids")
async def optimize_bids():
    """优化关键词竞价"""
    agent = BidOptimizerAgent()
    result = await agent.run(BidOptimizerInput(
        keywords=_mock_keywords(), target_acos=30.0,
    ))
    return result.model_dump()


@router.post("/allocate-budget")
async def allocate_budget():
    """智能分配预算"""
    agent = BudgetAllocatorAgent()
    result = await agent.run(BudgetAllocatorInput(
        campaigns=[c.model_dump() for c in _mock_campaigns()],
        total_budget=500, target_acos=30.0,
    ))
    return result.model_dump()


@router.post("/full-optimize")
async def full_optimize():
    """一键全优化：分析 + 竞价 + 预算"""
    perf_agent = PerformanceAnalyzerAgent()
    perf_result = await perf_agent.run(PerformanceAnalyzerInput(
        campaigns=_mock_campaigns(), target_acos=30.0,
    ))

    bid_agent = BidOptimizerAgent()
    bid_result = await bid_agent.run(BidOptimizerInput(
        keywords=_mock_keywords(), target_acos=30.0,
    ))

    budget_agent = BudgetAllocatorAgent()
    budget_result = await budget_agent.run(BudgetAllocatorInput(
        campaigns=[c.model_dump() for c in _mock_campaigns()],
        total_budget=500, target_acos=30.0,
    ))

    return {
        "performance": perf_result.model_dump(),
        "bid_optimization": bid_result.model_dump(),
        "budget_allocation": budget_result.model_dump(),
        "total_savings": bid_result.total_estimated_savings,
        "summary": f"优化完成: ACOS {perf_result.overall_acos}%, "
                   f"建议节约 ${bid_result.total_estimated_savings:.0f}/天, "
                   f"调整 {len(budget_result.allocations)} 个 Campaign 预算",
    }
