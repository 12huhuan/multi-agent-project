"""
评论监控工作流 — LangGraph StateGraph。

Agent 链:
ASIN/URL → [1.评论抓取] → [2.情感分析] → [3.翻译] → [4.预警判断] → [5.回复建议] → Human Review
"""

from typing import TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from backend.app.agents.review.review_scraper import ReviewScraperAgent, ReviewScraperInput
from backend.app.agents.review.sentiment_analyzer import SentimentAnalyzerAgent, SentimentAnalyzerInput
from backend.app.agents.review.review_translator import ReviewTranslatorAgent, ReviewTranslatorInput
from backend.app.agents.review.negative_alert import NegativeAlertAgent, NegativeAlertInput
from backend.app.agents.review.reply_suggestion import ReplySuggestionAgent, ReplySuggestionInput


class ReviewState(TypedDict):
    # 输入
    task_id: str
    product_asin: str
    platform: str
    max_reviews: int
    language: str  # 翻译目标语言

    # 中间结果
    reviews: list[dict]
    total_scraped: int
    analyzed_count: int
    negative_count: int
    alert_count: int

    # 状态
    status: str  # running | awaiting_review | completed | failed
    error: str
    current_step: str


scraper_agent = ReviewScraperAgent()
sentiment_agent = SentimentAnalyzerAgent()
translator_agent = ReviewTranslatorAgent()
alert_agent = NegativeAlertAgent()
reply_agent = ReplySuggestionAgent()


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


async def sentiment_node(state: ReviewState) -> ReviewState:
    if state["status"] == "failed":
        return state
    try:
        negative_count = 0
        for i, review in enumerate(state["reviews"]):
            if i >= 30:  # 限制 LLM 调用次数
                break
            result = await sentiment_agent.run(
                SentimentAnalyzerInput(
                    review_title=review.get("title", ""),
                    review_content=review.get("content", ""),
                    rating=review.get("rating", 3.0),
                    platform=state["platform"],
                ),
                context={"task_id": state["task_id"]},
            )
            review["sentiment"] = result.sentiment
            review["sentiment_score"] = result.score
            review["urgency_level"] = result.urgency_level
            review["key_phrases"] = result.key_phrases
            review["topics_mentioned"] = result.topics_mentioned
            if result.sentiment == "negative":
                negative_count += 1

        state["analyzed_count"] = min(len(state["reviews"]), 30)
        state["negative_count"] = negative_count
        state["current_step"] = "sentiment_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def translate_node(state: ReviewState) -> ReviewState:
    if state["status"] == "failed":
        return state
    try:
        for review in state["reviews"]:
            result = await translator_agent.run(
                ReviewTranslatorInput(
                    review_content=review.get("content", ""),
                    review_title=review.get("title", ""),
                    source_language="en",
                    target_language=state.get("language", "zh"),
                ),
                context={"task_id": state["task_id"]},
            )
            review["translated_title"] = result.translated_title
            review["translated_content"] = result.translated_content

        state["current_step"] = "translate_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def alert_node(state: ReviewState) -> ReviewState:
    if state["status"] == "failed":
        return state
    try:
        alert_count = 0
        for review in state["reviews"]:
            result = await alert_agent.run(
                NegativeAlertInput(
                    review_content=review.get("content", ""),
                    review_title=review.get("title", ""),
                    rating=review.get("rating", 3.0),
                    sentiment=review.get("sentiment", "neutral"),
                    sentiment_score=review.get("sentiment_score", 5.0),
                    urgency_level=review.get("urgency_level", "normal"),
                    reviewer_name=review.get("reviewer_name", ""),
                ),
                context={"task_id": state["task_id"]},
            )
            review["alert_level"] = result.alert_level
            review["alert_title"] = result.alert_title
            review["requires_reply"] = result.requires_reply
            review["requires_escalation"] = result.requires_escalation
            if result.alert_level in ("alert", "critical"):
                alert_count += 1

        state["alert_count"] = alert_count
        state["current_step"] = "alert_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def reply_suggestion_node(state: ReviewState) -> ReviewState:
    if state["status"] == "failed":
        return state
    try:
        for review in state["reviews"]:
            if not review.get("requires_reply"):
                continue
            result = await reply_agent.run(
                ReplySuggestionInput(
                    review_content=review.get("content", ""),
                    review_title=review.get("title", ""),
                    reviewer_name=review.get("reviewer_name", "Customer"),
                    rating=review.get("rating", 3.0),
                    sentiment=review.get("sentiment", "neutral"),
                    alert_level=review.get("alert_level", "none"),
                    language=state.get("language", "en"),
                ),
                context={"task_id": state["task_id"]},
            )
            review["reply_suggestion"] = result.reply_text
            review["reply_subject"] = result.subject
            review["reply_tone"] = result.tone

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
