"""智能选品 API 路由"""

import uuid
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from backend.app.schemas.schemas import SelectionAnalyzeRequest
from backend.app.workflows.selection_workflow import selection_workflow, SelectionState

router = APIRouter(prefix="/api/v1/selection", tags=["selection"])
_task_states: dict[str, dict] = {}


@router.post("/analyze")
async def analyze_selection(request: SelectionAnalyzeRequest):
    """触发选品分析"""
    task_id = str(uuid.uuid4())

    initial_state: SelectionState = {
        "task_id": task_id,
        "category": request.category,
        "keywords": request.keywords,
        "target_market": request.target_market,
        "seller_budget": request.seller_budget or "$5000-$15000",
        "seller_strengths": request.seller_strengths,
        "category_overview": "",
        "trends": [],
        "recommended_niches": [],
        "matched_products": [],
        "scored_products": [],
        "top_pick": "",
        "status": "running",
        "error": "",
        "current_step": "started",
    }

    _task_states[task_id] = initial_state

    import asyncio
    config = {"configurable": {"thread_id": task_id}}

    async def run_in_background():
        try:
            async for chunk in selection_workflow.astream(initial_state, config):
                for node_name, node_state in chunk.items():
                    if isinstance(node_state, dict):
                        _task_states[task_id].update(node_state)
        except Exception as e:
            _task_states[task_id]["status"] = "failed"
            _task_states[task_id]["error"] = str(e)

    asyncio.create_task(run_in_background())
    return {"task_id": task_id, "category": request.category, "status": "running"}


@router.get("/{task_id}/status")
async def get_status(task_id: str):
    if task_id not in _task_states:
        raise HTTPException(status_code=404, detail="Task not found")
    s = _task_states[task_id]
    return {"task_id": task_id, "status": s.get("status"), "current_step": s.get("current_step", ""),
            "products_found": len(s.get("matched_products", []))}


@router.get("/{task_id}/result")
async def get_result(task_id: str):
    if task_id not in _task_states:
        raise HTTPException(status_code=404, detail="Task not found")
    s = _task_states[task_id]
    return {"task_id": task_id, "status": s.get("status"), "category_overview": s.get("category_overview", ""),
            "trends": s.get("trends", []), "scored_products": s.get("scored_products", []),
            "top_pick": s.get("top_pick", "")}


@router.websocket("/{task_id}/stream")
async def stream(websocket: WebSocket, task_id: str):
    await websocket.accept()
    try:
        import asyncio as aio
        while True:
            if task_id in _task_states:
                s = _task_states[task_id]
                await websocket.send_json({"type": "progress", "current_step": s.get("current_step", ""),
                                           "status": s.get("status", "")})
                if s.get("status") in ("completed", "failed", "awaiting_review"):
                    break
            await aio.sleep(1)
    except WebSocketDisconnect:
        pass
