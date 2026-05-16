"""顶层调度 API 路由 — 手动触发或 crontab webhook"""

import uuid
from fastapi import APIRouter, HTTPException

from backend.app.schemas.schemas import OrchestratorRunRequest
from backend.app.agents.orchestrator.orchestrator import OrchestratorAgent, OrchestratorInput

router = APIRouter(prefix="/api/v1/orchestrator", tags=["orchestrator"])

# 调度执行日志
_logs: list[dict] = []


@router.post("/run")
async def run_orchestrator(request: OrchestratorRunRequest = None):
    """手动触发一次调度循环"""
    if request is None:
        request = OrchestratorRunRequest()

    agent = OrchestratorAgent()
    result = await agent.run(OrchestratorInput(
        action=request.action,
        context=request.context,
    ))

    log_entry = {
        "id": str(uuid.uuid4())[:8],
        "action": request.action,
        "decisions": [d.model_dump() for d in result.decisions],
        "summary": result.summary,
        "notifications": result.notifications,
    }
    _logs.insert(0, log_entry)
    if len(_logs) > 50:
        _logs.pop()

    return log_entry


@router.post("/webhook")
async def orchestrator_webhook(request: dict = {}):
    """crontab 定时调用的 webhook 入口"""
    agent = OrchestratorAgent()
    result = await agent.run(OrchestratorRunRequest(
        action=request.get("action", "auto"),
        context=request.get("context", {}),
    ))

    return {
        "status": "ok",
        "decisions": [d.model_dump() for d in result.decisions],
        "summary": result.summary,
    }


@router.get("/logs")
async def get_logs():
    """查看调度日志"""
    return _logs


@router.get("/status")
async def get_status():
    """当前调度状态概览"""
    return {
        "orchestrator": "active",
        "total_runs": len(_logs),
        "last_run": _logs[0] if _logs else None,
        "supported_actions": [
            "auto", "select_product", "run_listing", "check_compliance",
            "generate_social", "monitor_reviews",
        ],
    }
