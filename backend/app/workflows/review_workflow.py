"""
评论监控工作流 — LangGraph StateGraph (Phase 2 优化版)

Agent 链:
ASIN → [1.抓取] → [2.情感分析×N·并行] → [3.翻译×N·并行]
                                ↓
  Human Review ← [5.回复建议×N·并行] ← [4.预警×N·并行]

优化: 所有逐条操作的 LLM 调用用 asyncio.gather 并行化
"""

import asyncio
from typing import TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from backend.app.agents.review.review_scraper import ReviewScraperAgent, ReviewScraperInput
from backend.app.agents.review.sentiment_analyzer import SentimentAnalyzerAgent, SentimentAnalyzerInput
from backend.app.agents.review.review_translator import ReviewTranslatorAgent, ReviewTranslatorInput
from backend.app.agents.review.negative_alert import NegativeAlertAgent, NegativeAlertInput
from backend.app.agents.review.reply_suggestion import ReplySuggestionAgent, ReplySuggestionInput


class ReviewState(TypedDict):
    task_id: str
    product_asin: str
    platform: str
    max_reviews: int
    language: str

    reviews: list[dict]
    total_scraped: int
    analyzed_count: int
    negative_count: int
    alert_count: int

    status: str
    error: str
    current_step: str


# 并发限制：DeepSeek API 限流，最多 5 个并发 LLM 调用
SEMAPHORE = asyncio.Semaphore(5)

scraper_agent = ReviewScraperAgent()


async def scrape_node(state: ReviewState) -> ReviewState:
    try:
        result = await scraper_agent.run(
            ReviewScraperInput(
                product_asin=state["product_asin"],
                platform=state["platform"],
                max_reviews=state["max_reviews"],
            ),
            context={"task_id": state["task_id"]},
        )
        state["reviews"] = [r.model_dump() for r in result.reviews]
        state["total_scraped"] = result.total_scraped
        state["current_step"] = "scrape_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def _analyze_one_review(review: dict, platform: str, task_id: str) -> dict:
    """对单条评论做情感分析，返回更新的字段"""
    async with SEMAPHORE:
        agent = SentimentAnalyzerAgent()
        result = await agent.run(
        SentimentAnalyzerInput(
            review_title=review.get("title", ""),
            review_content=review.get("content", ""),
            rating=review.get("rating", 3.0),
            platform=platform,
        ),
        context={"task_id": task_id},
    )
    return {
        "sentiment": result.sentiment,
        "sentiment_score": result.score,
        "urgency_level": result.urgency_level,
        "key_phrases": result.key_phrases,
        "topics_mentioned": result.topics_mentioned,
    }


async def sentiment_node(state: ReviewState) -> ReviewState:
    if state["status"] == "failed":
        return state
    try:
        reviews = state["reviews"][:30]
        tasks = [_analyze_one_review(r, state["platform"], state["task_id"]) for r in reviews]
        results = await asyncio.gather(*tasks)

        negative_count = 0
        for review, data in zip(reviews, results):
            review.update(data)
            if data["sentiment"] == "negative":
                negative_count += 1

        state["analyzed_count"] = len(reviews)
        state["negative_count"] = negative_count
        state["current_step"] = "sentiment_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def _translate_one_review(review: dict, language: str, task_id: str) -> dict:
    """翻译单条评论"""
    async with SEMAPHORE:
        agent = ReviewTranslatorAgent()
        result = await agent.run(
        ReviewTranslatorInput(
            review_content=review.get("content", ""),
            review_title=review.get("title", ""),
            source_language="en",
            target_language=language,
        ),
        context={"task_id": task_id},
    )
    return {
        "translated_title": result.translated_title,
        "translated_content": result.translated_content,
    }


async def translate_node(state: ReviewState) -> ReviewState:
    if state["status"] == "failed":
        return state
    try:
        tasks = [_translate_one_review(r, state.get("language", "zh"), state["task_id"]) for r in state["reviews"]]
        results = await asyncio.gather(*tasks)

        for review, data in zip(state["reviews"], results):
            review.update(data)

        state["current_step"] = "translate_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def _check_one_alert(review: dict, task_id: str) -> dict:
    """对单条评论做预警判断"""
    agent = NegativeAlertAgent()
    result = await agent.run(
        NegativeAlertInput(
            review_content=review.get("content", ""),
            review_title=review.get("title", ""),
            rating=review.get("rating", 3.0),
            sentiment=review.get("sentiment", "neutral"),
            sentiment_score=review.get("sentiment_score", 5.0),
            urgency_level=review.get("urgency_level", "normal"),
            reviewer_name=review.get("reviewer_name", ""),
        ),
        context={"task_id": task_id},
    )
    return {
        "alert_level": result.alert_level,
        "alert_title": result.alert_title,
        "requires_reply": result.requires_reply,
        "requires_escalation": result.requires_escalation,
    }


async def alert_node(state: ReviewState) -> ReviewState:
    if state["status"] == "failed":
        return state
    try:
        tasks = [_check_one_alert(r, state["task_id"]) for r in state["reviews"]]
        results = await asyncio.gather(*tasks)

        alert_count = 0
        for review, data in zip(state["reviews"], results):
            review.update(data)
            if data["alert_level"] in ("alert", "critical"):
                alert_count += 1

        state["alert_count"] = alert_count
        state["current_step"] = "alert_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def _generate_one_reply(idx: int, review: dict, language: str, task_id: str) -> tuple[int, dict]:
    """为需要回复的评论生成回复建议"""
    if not review.get("requires_reply"):
        return idx, {}
    async with SEMAPHORE:
        agent = ReplySuggestionAgent()
        result = await agent.run(
        ReplySuggestionInput(
            review_content=review.get("content", ""),
            review_title=review.get("title", ""),
            reviewer_name=review.get("reviewer_name", "Customer"),
            rating=review.get("rating", 3.0),
            sentiment=review.get("sentiment", "neutral"),
            alert_level=review.get("alert_level", "none"),
            language=language,
        ),
        context={"task_id": task_id},
    )
    return idx, {
        "reply_suggestion": result.reply_text,
        "reply_subject": result.subject,
        "reply_tone": result.tone,
    }


async def reply_suggestion_node(state: ReviewState) -> ReviewState:
    if state["status"] == "failed":
        return state
    try:
        tasks = [
            _generate_one_reply(i, r, state.get("language", "en"), state["task_id"])
            for i, r in enumerate(state["reviews"])
        ]
        results = await asyncio.gather(*tasks)

        for idx, data in results:
            if data:
                state["reviews"][idx].update(data)

        state["current_step"] = "reply_done"
        state["status"] = "awaiting_review"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


def build_review_workflow() -> StateGraph:
    workflow = StateGraph(ReviewState)

    workflow.add_node("scrape", scrape_node)
    workflow.add_node("sentiment", sentiment_node)
    workflow.add_node("translate", translate_node)
    workflow.add_node("alert", alert_node)
    workflow.add_node("reply_suggestion", reply_suggestion_node)

    workflow.set_entry_point("scrape")
    workflow.add_edge("scrape", "sentiment")
    workflow.add_edge("sentiment", "translate")
    workflow.add_edge("translate", "alert")
    workflow.add_edge("alert", "reply_suggestion")
    workflow.add_edge("reply_suggestion", END)

    return workflow


review_workflow = build_review_workflow().compile(
    checkpointer=MemorySaver(),
    interrupt_after=["reply_suggestion"],
)
