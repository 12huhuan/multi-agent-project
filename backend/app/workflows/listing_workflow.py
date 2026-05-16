"""
Listing 优化工作流 — LangGraph StateGraph。

Agent 链:
产品输入 → [1.关键词研究] → [2.标题生成] → [3.五点描述] → [4.长描述] → [5.A+内容] → [6.SEO评分] → Human Review
"""

from typing import TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from backend.app.agents.listing.keyword_research import KeywordResearchAgent, KeywordResearchInput
from backend.app.agents.listing.title_generation import TitleGenerationAgent, TitleGenerationInput
from backend.app.agents.listing.bullet_points import BulletPointsAgent, BulletPointsInput
from backend.app.agents.listing.description import DescriptionAgent, DescriptionInput
from backend.app.agents.listing.aplus_content import APlusContentAgent, APlusContentInput
from backend.app.agents.listing.seo_scoring import SEOScoringAgent, SEOScoringInput


class ListingState(TypedDict):
    # 输入
    task_id: str
    product_name: str
    category: str
    features: list[str]
    brand_story: str | None
    image_descriptions: list[str]
    target_platform: str
    target_language: str

    # 中间结果
    keywords: list[dict]
    top_keywords: list[str]
    title_candidates: list[dict]
    best_title: str
    bullet_points: list[dict]
    description_html: str
    a_plus_modules: list[dict]
    seo_report: dict

    # 状态
    status: str  # running | awaiting_review | completed | failed
    error: str
    current_step: str


# Agent 实例
kw_agent = KeywordResearchAgent()
title_agent = TitleGenerationAgent()
bp_agent = BulletPointsAgent()
desc_agent = DescriptionAgent()
aplus_agent = APlusContentAgent()
seo_agent = SEOScoringAgent()


async def keyword_research_node(state: ListingState) -> ListingState:
    try:
        result = await kw_agent.run(
            KeywordResearchInput(
                product_name=state["product_name"],
                category=state["category"],
                features=state["features"],
                target_platform=state["target_platform"],
                target_language=state["target_language"],
            ),
            context={"task_id": state["task_id"]},
        )
        state["keywords"] = [k.model_dump() for k in result.keywords]
        state["top_keywords"] = result.top_keywords
        state["current_step"] = "keywords_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def title_generation_node(state: ListingState) -> ListingState:
    if state["status"] == "failed":
        return state
    try:
        result = await title_agent.run(
            TitleGenerationInput(
                product_name=state["product_name"],
                category=state["category"],
                top_keywords=state["top_keywords"],
                features=state["features"],
                target_platform=state["target_platform"],
                target_language=state["target_language"],
            ),
            context={"task_id": state["task_id"]},
        )
        state["title_candidates"] = [c.model_dump() for c in result.candidates]
        state["best_title"] = result.best_title
        state["current_step"] = "title_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def bullet_points_node(state: ListingState) -> ListingState:
    if state["status"] == "failed":
        return state
    try:
        result = await bp_agent.run(
            BulletPointsInput(
                product_name=state["product_name"],
                features=state["features"],
                keywords=state["top_keywords"],
                target_platform=state["target_platform"],
                target_language=state["target_language"],
            ),
            context={"task_id": state["task_id"]},
        )
        state["bullet_points"] = [bp.model_dump() for bp in result.bullet_points]
        state["current_step"] = "bp_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def description_node(state: ListingState) -> ListingState:
    if state["status"] == "failed":
        return state
    try:
        bp_texts = [bp.get("text", "") for bp in state["bullet_points"]]
        result = await desc_agent.run(
            DescriptionInput(
                product_name=state["product_name"],
                category=state["category"],
                features=state["features"],
                bullet_points=bp_texts,
                keywords=state["top_keywords"],
                brand_story=state.get("brand_story"),
                target_platform=state["target_platform"],
                target_language=state["target_language"],
            ),
            context={"task_id": state["task_id"]},
        )
        state["description_html"] = result.html_content
        state["current_step"] = "description_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def aplus_content_node(state: ListingState) -> ListingState:
    if state["status"] == "failed":
        return state
    try:
        result = await aplus_agent.run(
            APlusContentInput(
                product_name=state["product_name"],
                category=state["category"],
                features=state["features"],
                brand_story=state.get("brand_story"),
                image_descriptions=state.get("image_descriptions", []),
                target_language=state["target_language"],
            ),
            context={"task_id": state["task_id"]},
        )
        state["a_plus_modules"] = [m.model_dump() for m in result.modules]
        state["current_step"] = "aplus_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def seo_scoring_node(state: ListingState) -> ListingState:
    if state["status"] == "failed":
        return state
    try:
        bp_texts = [bp.get("text", "") for bp in state["bullet_points"]]
        result = await seo_agent.run(
            SEOScoringInput(
                product_name=state["product_name"],
                title=state.get("best_title", ""),
                bullet_points=bp_texts,
                description_html=state.get("description_html", ""),
                keywords=state["top_keywords"],
                target_platform=state["target_platform"],
            ),
            context={"task_id": state["task_id"]},
        )
        state["seo_report"] = result.model_dump()
        state["current_step"] = "seo_done"
        state["status"] = "awaiting_review"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


def build_listing_workflow() -> StateGraph:
    """构建 Listing 优化 LangGraph 工作流"""
    workflow = StateGraph(ListingState)

    workflow.add_node("keyword_research", keyword_research_node)
    workflow.add_node("title_generation", title_generation_node)
    workflow.add_node("bullet_points", bullet_points_node)
    workflow.add_node("description", description_node)
    workflow.add_node("aplus_content", aplus_content_node)
    workflow.add_node("seo_scoring", seo_scoring_node)

    workflow.set_entry_point("keyword_research")
    workflow.add_edge("keyword_research", "title_generation")
    workflow.add_edge("title_generation", "bullet_points")
    workflow.add_edge("bullet_points", "description")
    workflow.add_edge("description", "aplus_content")
    workflow.add_edge("aplus_content", "seo_scoring")
    workflow.add_edge("seo_scoring", END)

    return workflow


# 编译后的工作流（带内存检查点，支持 HITL interrupt）
listing_workflow = build_listing_workflow().compile(
    checkpointer=MemorySaver(),
    interrupt_after=["seo_scoring"],  # SEO评分后暂停，等待人工审核
)
