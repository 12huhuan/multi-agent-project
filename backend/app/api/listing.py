"""Listing 优化 API 路由"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.models.models import ListingTask
from backend.app.schemas.schemas import (
    ListingTaskCreate,
    ListingTaskResponse,
    ListingTaskStatus,
    ListingResultResponse,
    WorkflowApproveRequest,
    ChatRequest,
    ChatResponse,
)
from backend.app.workflows.listing_workflow import listing_workflow, ListingState

router = APIRouter(prefix="/api/v1/listing", tags=["listing"])

# 内存中的任务执行记录（生产环境应放入 Redis）
_task_states: dict[str, dict] = {}


@router.post("/run", response_model=ListingTaskResponse)
async def run_listing_workflow(request: ListingTaskCreate):
    """触发 Listing 优化工作流"""
    import uuid as _uuid

    task_id = str(_uuid.uuid4())

    # 启动 LangGraph 工作流
    initial_state: ListingState = {
        "task_id": task_id,
        "product_name": request.product_name,
        "category": request.category,
        "features": request.features,
        "brand_story": request.brand_story,
        "image_descriptions": request.product_images_descriptions,
        "target_platform": request.target_platform,
        "target_language": request.target_language,
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

    # 预先缓存初始状态，让 /status 立即可查
    _task_states[task_id] = initial_state

    # 后台异步执行（不阻塞请求返回）
    import asyncio
    config = {"configurable": {"thread_id": task_id}}

    async def run_in_background():
        try:
            # 用 astream 逐节点推送进度
            async for chunk in listing_workflow.astream(initial_state, config):
                for node_name, node_state in chunk.items():
                    if isinstance(node_state, dict):
                        _task_states[task_id].update(node_state)
        except Exception as e:
            import traceback
            traceback.print_exc()
            _task_states[task_id]["status"] = "failed"
            _task_states[task_id]["error"] = str(e)

    asyncio.create_task(run_in_background())

    return ListingTaskResponse(
        id=task_id,
        product_name=request.product_name,
        category=request.category,
        target_platform=request.target_platform,
        target_language=request.target_language,
        status="running",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


@router.get("/{task_id}/status", response_model=ListingTaskStatus)
async def get_listing_status(task_id: str):
    """查询 Listing 任务状态和中间结果"""
    if task_id not in _task_states:
        raise HTTPException(status_code=404, detail="Task not found")

    state = _task_states[task_id]
    agents_order = ["keyword_research", "title_generation", "bullet_points", "description", "aplus_content", "seo_scoring"]

    current_idx = 0
    step_map = {
        "keywords_done": "keyword_research",
        "title_done": "title_generation",
        "bp_done": "bullet_points",
        "description_done": "description",
        "aplus_done": "aplus_content",
        "seo_done": "seo_scoring",
    }
    current_agent = step_map.get(state.get("current_step", ""), "")
    if current_agent in agents_order:
        current_idx = agents_order.index(current_agent) + 1

    return ListingTaskStatus(
        task_id=task_id,
        status=state.get("status", "running"),
        progress=f"{current_idx}/{len(agents_order)}",
        completed_agents=agents_order[:current_idx],
        pending_agents=agents_order[current_idx:],
        intermediate_results={
            "keywords": state.get("keywords", []),
            "title_candidates": state.get("title_candidates", []),
            "best_title": state.get("best_title", ""),
            "bullet_points": state.get("bullet_points", []),
        },
        final_result=state if state.get("status") == "awaiting_review" else None,
    )


@router.post("/{task_id}/approve")
async def approve_listing(task_id: str, request: WorkflowApproveRequest):
    """人工审核通过/驳回"""
    if task_id not in _task_states:
        raise HTTPException(status_code=404, detail="Task not found")

    state = _task_states[task_id]

    if request.approved:
        state["status"] = "completed"
        # 如果有修改，应用修改
        if request.modifications:
            for key, value in request.modifications.items():
                if key in state:
                    state[key] = value
    else:
        state["status"] = "rejected"

    return {"task_id": task_id, "status": state["status"], "message": "审核完成"}


@router.get("/{task_id}/result", response_model=ListingResultResponse)
async def get_listing_result(task_id: str):
    """获取 Listing 最终结果"""
    if task_id not in _task_states:
        raise HTTPException(status_code=404, detail="Task not found")

    state = _task_states[task_id]
    return ListingResultResponse(
        task_id=task_id,
        title_candidates=state.get("title_candidates", []),
        bullet_points=[bp.get("text", "") for bp in state.get("bullet_points", [])],
        description_html=state.get("description_html", ""),
        a_plus_content={"modules": state.get("a_plus_modules", [])},
        seo_score=state.get("seo_report", {}),
        keywords=state.get("keywords", []),
    )


@router.websocket("/{task_id}/stream")
async def listing_stream(websocket: WebSocket, task_id: str):
    """WebSocket 实时推送 Listing 工作流进度"""
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
