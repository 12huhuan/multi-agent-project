"""
选品工作流 — LangGraph StateGraph。

Agent 链:
品类输入 → [1.趋势分析] → [2.产品匹配] → [3.机会评分] → 选品报告
"""

from typing import TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from backend.app.agents.selection.trend_analyzer import TrendAnalyzerAgent, TrendAnalyzerInput
from backend.app.agents.selection.product_matcher import ProductMatcherAgent, ProductMatcherInput
from backend.app.agents.selection.opportunity_scorer import OpportunityScorerAgent, OpportunityScorerInput


class SelectionState(TypedDict):
    task_id: str
    category: str
    keywords: list[str]
    target_market: str
    seller_budget: str
    seller_strengths: list[str]

    category_overview: str
    trends: list[dict]
    recommended_niches: list[str]
    matched_products: list[dict]
    scored_products: list[dict]
    top_pick: str

    # 数据来源追踪
    raw_search_data: list[dict]
    data_source: str

    status: str
    error: str
    current_step: str


trend_agent = TrendAnalyzerAgent()
match_agent = ProductMatcherAgent()
score_agent = OpportunityScorerAgent()


async def trend_node(state: SelectionState) -> SelectionState:
    try:
        result = await trend_agent.run(
            TrendAnalyzerInput(
                category=state["category"],
                keywords=state["keywords"],
                target_market=state["target_market"],
            ),
            context={"task_id": state["task_id"]},
        )
        state["category_overview"] = result.category_overview
        state["trends"] = [t.model_dump() for t in result.trends]
        state["recommended_niches"] = result.recommended_niches
        state["raw_search_data"] = result.raw_search_data
        state["data_source"] = result.data_source
        state["current_step"] = "trend_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def match_node(state: SelectionState) -> SelectionState:
    if state["status"] == "failed":
        return state
    try:
        result = await match_agent.run(
            ProductMatcherInput(
                category=state["category"],
                recommended_niches=state["recommended_niches"],
                seller_budget=state["seller_budget"],
                seller_strengths=state["seller_strengths"],
                target_market=state["target_market"],
            ),
            context={"task_id": state["task_id"]},
        )
        state["matched_products"] = [m.model_dump() for m in result.matched_products]
        state["current_step"] = "match_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def score_node(state: SelectionState) -> SelectionState:
    if state["status"] == "failed":
        return state
    try:
        result = await score_agent.run(
            OpportunityScorerInput(
                products=state["matched_products"],
                trend_data=state["trends"],
            ),
            context={"task_id": state["task_id"]},
        )
        state["scored_products"] = [s.model_dump() for s in result.scored_products]
        state["top_pick"] = result.top_pick
        state["current_step"] = "score_done"
        state["status"] = "awaiting_review"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


def build_selection_workflow() -> StateGraph:
    workflow = StateGraph(SelectionState)
    workflow.add_node("trend_analysis", trend_node)
    workflow.add_node("product_match", match_node)
    workflow.add_node("opportunity_score", score_node)
    workflow.set_entry_point("trend_analysis")
    workflow.add_edge("trend_analysis", "product_match")
    workflow.add_edge("product_match", "opportunity_score")
    workflow.add_edge("opportunity_score", END)
    return workflow


selection_workflow = build_selection_workflow().compile(
    checkpointer=MemorySaver(),
    interrupt_after=["opportunity_score"],
)
