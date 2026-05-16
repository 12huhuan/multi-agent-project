"""评论监控 API 路由"""

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from backend.app.schemas.schemas import (
    ReviewScrapeRequest,
    ReviewResponse,
    ReviewReplyApproveRequest,
    ReviewReplySuggestionResponse,
)
from backend.app.workflows.review_workflow import review_workflow, ReviewState
from backend.app.agents.review.reply_suggestion import ReplySuggestionAgent, ReplySuggestionInput

router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])

# 内存存储
_task_states: dict[str, dict] = {}
_reviews: dict[str, dict] = {}  # review_id → review dict


@router.post("/scrape")
async def scrape_reviews(request: ReviewScrapeRequest):
    """触发评论抓取工作流"""
    task_id = str(uuid.uuid4())

    initial_state: ReviewState = {
        "task_id": task_id,
        "product_asin": request.product_asin,
        "platform": request.platform,
        "max_reviews": request.max_reviews,
        "language": "zh",
        "reviews": [],
        "total_scraped": 0,
        "analyzed_count": 0,
        "negative_count": 0,
        "alert_count": 0,
        "status": "running",
        "error": "",
        "current_step": "started",
    }

    _task_states[task_id] = initial_state

    import asyncio
    config = {"configurable": {"thread_id": task_id}}

    async def run_in_background():
        try:
            async for chunk in review_workflow.astream(initial_state, config):
                for node_name, node_state in chunk.items():
                    if isinstance(node_state, dict):
                        _task_states[task_id].update(node_state)
            # 将评论存入 _reviews 以支持单条查询
            for review in _task_states[task_id].get("reviews", []):
                rid = str(uuid.uuid4())
                review["id"] = rid
                review["product_asin"] = request.product_asin
                review["reply_status"] = review.get("reply_status", "none")
                _reviews[rid] = review
        except Exception as e:
            import traceback
            traceback.print_exc()
            _task_states[task_id]["status"] = "failed"
            _task_states[task_id]["error"] = str(e)

    asyncio.create_task(run_in_background())

    return {
        "task_id": task_id,
        "product_asin": request.product_asin,
        "status": "running",
        "message": f"开始抓取 {request.product_asin} 的评论",
    }


@router.get("/", response_model=list[ReviewResponse])
async def list_reviews(sentiment: str = "", rating: int = 0):
    """评论列表，支持按情感和评分筛选"""
    results = []
    for rid, r in _reviews.items():
        if sentiment and r.get("sentiment", "") != sentiment:
            continue
        if rating and int(r.get("rating", 0)) != rating:
            continue
        results.append(ReviewResponse(
            id=rid,
            product_asin=r.get("product_asin", ""),
            reviewer_name=r.get("reviewer_name", "Anonymous"),
            rating=r.get("rating", 0),
            title=r.get("title", ""),
            content=r.get("content", ""),
            translated_title=r.get("translated_title", ""),
            translated_content=r.get("translated_content", ""),
            sentiment=r.get("sentiment", "neutral"),
            sentiment_score=r.get("sentiment_score", 5.0),
            alert_level=r.get("alert_level", "none"),
            reply_suggestion=r.get("reply_suggestion", ""),
            reply_status=r.get("reply_status", "none"),
            date=r.get("date", ""),
            verified_purchase=r.get("verified_purchase", False),
        ))
    return results


@router.get("/{task_id}/status")
async def get_review_task_status(task_id: str):
    """查询评论抓取任务状态和进度"""
    if task_id not in _task_states:
        raise HTTPException(status_code=404, detail="Task not found")
    state = _task_states[task_id]
    return {
        "task_id": task_id,
        "status": state.get("status", "running"),
        "current_step": state.get("current_step", ""),
        "total_scraped": state.get("total_scraped", 0),
        "analyzed_count": state.get("analyzed_count", 0),
        "negative_count": state.get("negative_count", 0),
        "alert_count": state.get("alert_count", 0),
        "error": state.get("error", ""),
    }


@router.get("/{task_id}/result")
async def get_review_task_result(task_id: str):
    """获取评论抓取最终结果"""
    if task_id not in _task_states:
        raise HTTPException(status_code=404, detail="Task not found")
    state = _task_states[task_id]
    return {
        "task_id": task_id,
        "status": state.get("status"),
        "reviews": state.get("reviews", []),
        "total_scraped": state.get("total_scraped", 0),
        "negative_count": state.get("negative_count", 0),
        "alert_count": state.get("alert_count", 0),
    }


@router.get("/stats")
async def review_stats():
    """评论统计概览"""
    all_reviews = list(_reviews.values())
    total = len(all_reviews)
    if total == 0:
        return {"total": 0, "avg_rating": 0, "sentiment_distribution": {}, "alert_count": 0}

    avg_rating = sum(r.get("rating", 0) for r in all_reviews) / total
    sentiment_dist = {"positive": 0, "neutral": 0, "negative": 0}
    alert_count = 0
    for r in all_reviews:
        s = r.get("sentiment", "neutral")
        if s in sentiment_dist:
            sentiment_dist[s] += 1
        if r.get("alert_level") in ("alert", "critical"):
            alert_count += 1

    return {
        "total": total,
        "avg_rating": round(avg_rating, 2),
        "sentiment_distribution": sentiment_dist,
        "alert_count": alert_count,
    }


@router.get("/{review_id}", response_model=ReviewResponse)
async def get_review(review_id: str):
    """单条评论详情"""
    if review_id not in _reviews:
        raise HTTPException(status_code=404, detail="Review not found")
    r = _reviews[review_id]
    return ReviewResponse(
        id=review_id,
        product_asin=r.get("product_asin", ""),
        reviewer_name=r.get("reviewer_name", "Anonymous"),
        rating=r.get("rating", 0),
        title=r.get("title", ""),
        content=r.get("content", ""),
        translated_title=r.get("translated_title", ""),
        translated_content=r.get("translated_content", ""),
        sentiment=r.get("sentiment", "neutral"),
        sentiment_score=r.get("sentiment_score", 5.0),
        alert_level=r.get("alert_level", "none"),
        reply_suggestion=r.get("reply_suggestion", ""),
        reply_status=r.get("reply_status", "none"),
        date=r.get("date", ""),
        verified_purchase=r.get("verified_purchase", False),
    )


@router.post("/{review_id}/suggest-reply", response_model=ReviewReplySuggestionResponse)
async def suggest_reply(review_id: str):
    """为指定评论生成回复建议"""
    if review_id not in _reviews:
        raise HTTPException(status_code=404, detail="Review not found")

    r = _reviews[review_id]
    agent = ReplySuggestionAgent()
    result = await agent.run(
        ReplySuggestionInput(
            review_content=r.get("content", ""),
            review_title=r.get("title", ""),
            reviewer_name=r.get("reviewer_name", "Customer"),
            rating=r.get("rating", 3.0),
            sentiment=r.get("sentiment", "neutral"),
            alert_level=r.get("alert_level", "none"),
            language="en",
        ),
        context={"task_id": review_id},
    )

    r["reply_suggestion"] = result.reply_text
    r["reply_status"] = "pending"

    return ReviewReplySuggestionResponse(
        review_id=review_id,
        subject=result.subject,
        reply_text=result.reply_text,
        alternative_reply=result.alternative_reply,
        tone=result.tone,
        key_points_addressed=result.key_points_addressed,
    )


@router.post("/{review_id}/approve-reply")
async def approve_reply(review_id: str, request: ReviewReplyApproveRequest):
    """审核回复 (approve/reject + edit)"""
    if review_id not in _reviews:
        raise HTTPException(status_code=404, detail="Review not found")

    r = _reviews[review_id]
    if request.approved:
        r["reply_status"] = "approved"
        if request.edited_reply:
            r["reply_suggestion"] = request.edited_reply
    else:
        r["reply_status"] = "rejected"

    return {
        "review_id": review_id,
        "reply_status": r["reply_status"],
        "message": "回复已审核" if request.approved else "回复已驳回",
    }


@router.websocket("/{task_id}/stream")
async def review_stream(websocket: WebSocket, task_id: str):
    """WebSocket 实时推送评论抓取进度"""
    await websocket.accept()
    try:
        while True:
            if task_id in _task_states:
                state = _task_states[task_id]
                await websocket.send_json({
                    "type": "progress",
                    "task_id": task_id,
                    "current_step": state.get("current_step", ""),
                    "status": state.get("status", ""),
                    "total_scraped": state.get("total_scraped", 0),
                    "negative_count": state.get("negative_count", 0),
                    "alert_count": state.get("alert_count", 0),
                })
                if state.get("status") in ("completed", "failed", "awaiting_review"):
                    await websocket.send_json({"type": "done", "status": state["status"]})
                    break
            else:
                await websocket.send_json({"type": "waiting", "task_id": task_id})
            import asyncio
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
