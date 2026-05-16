"""合规审查 API 路由"""

import uuid
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from backend.app.schemas.schemas import ComplianceReviewRequest
from backend.app.workflows.compliance_workflow import compliance_workflow, ComplianceState

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])
_task_states: dict[str, dict] = {}


@router.post("/review")
async def review_compliance(request: ComplianceReviewRequest):
    """触发合规审查"""
    task_id = str(uuid.uuid4())

    initial_state: ComplianceState = {
        "task_id": task_id, "title": request.title,
        "bullet_points": request.bullet_points, "description": request.description,
        "category": request.category, "product_features": request.product_features,
        "platform": request.platform, "policy_issues": [], "claim_issues": [],
        "overall_verdict": "", "risk_level": "", "total_issues": 0,
        "critical_items": [], "action_items": [], "summary": "",
        "status": "running", "error": "", "current_step": "started",
    }

    _task_states[task_id] = initial_state

    import asyncio
    config = {"configurable": {"thread_id": task_id}}

    async def run():
        try:
            async for chunk in compliance_workflow.astream(initial_state, config):
                for _, node_state in chunk.items():
                    if isinstance(node_state, dict):
                        _task_states[task_id].update(node_state)
        except Exception as e:
            _task_states[task_id]["status"] = "failed"
            _task_states[task_id]["error"] = str(e)

    asyncio.create_task(run())
    return {"task_id": task_id, "status": "running"}


@router.get("/{task_id}/status")
async def get_status(task_id: str):
    if task_id not in _task_states:
        raise HTTPException(status_code=404, detail="Task not found")
    s = _task_states[task_id]
    return {"task_id": task_id, "status": s.get("status"), "current_step": s.get("current_step", ""),
            "issues_found": s.get("total_issues", 0)}


@router.get("/{task_id}/result")
async def get_result(task_id: str):
    if task_id not in _task_states:
        raise HTTPException(status_code=404, detail="Task not found")
    s = _task_states[task_id]
    return {"task_id": task_id, "verdict": s.get("overall_verdict"), "risk_level": s.get("risk_level"),
            "total_issues": s.get("total_issues"), "critical_items": s.get("critical_items", []),
            "action_items": s.get("action_items", []), "summary": s.get("summary", ""),
            "policy_issues": s.get("policy_issues", []), "claim_issues": s.get("claim_issues", [])}


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
