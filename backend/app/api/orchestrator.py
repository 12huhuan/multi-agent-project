"""顶层调度 API 路由 — 异步模式: 触发→轮询→结果"""

import asyncio
import uuid
from fastapi import APIRouter, HTTPException

from backend.app.schemas.schemas import OrchestratorRunRequest
from backend.app.agents.orchestrator.orchestrator import OrchestratorAgent, OrchestratorInput

router = APIRouter(prefix="/api/v1/orchestrator", tags=["orchestrator"])

_task_states: dict[str, dict] = {}
_logs: list[dict] = []


def _merge_result_to_ctx(pipeline_ctx: dict, action: str, data: dict) -> dict:
    """将当前步骤的结果合并到 pipeline 上下文，供下一步使用"""
    if action == "select_product" and data.get("top_pick"):
        pipeline_ctx["product_name"] = data["top_pick"]
        # 提取选品报告中的 features
        products = data.get("scored_products", [])
        if products and isinstance(products[0], dict):
            first = products[0]
            if first.get("features"):
                pipeline_ctx["features"] = first["features"]

    if action == "run_listing":
        if data.get("best_title"):
            pipeline_ctx["title"] = data["best_title"]
            pipeline_ctx["best_title"] = data["best_title"]
        if data.get("bullet_points"):
            pipeline_ctx["bullet_points"] = [
                bp.get("text", "") if isinstance(bp, dict) else str(bp)
                for bp in data["bullet_points"][:5]
            ]
        if data.get("description"):
            pipeline_ctx["description"] = data["description"]
        if data.get("seo_score"):
            pipeline_ctx["seo_score"] = data["seo_score"]

    if action == "generate_social" and data.get("posts"):
        pipeline_ctx["social_posts"] = data["posts"]

    return pipeline_ctx


@router.post("/run")
async def run_orchestrator(request: OrchestratorRunRequest = None):
    """触发调度 (异步后台执行, 立即返回 task_id)"""
    if request is None:
        request = OrchestratorRunRequest()
    task_id = str(uuid.uuid4())

    _task_states[task_id] = {
        "task_id": task_id, "action": request.action,
        "status": "running", "progress": "starting", "result": None,
    }

    async def background():
        try:
            agent = OrchestratorAgent()
            req_input = OrchestratorInput(action=request.action, context=request.context)

            if request.action == "auto":
                ctx = dict(request.context) if request.context else {}
                pipeline_ctx = await agent._auto_fill_context(ctx, "select_product")

                decisions = []
                pipeline = [
                    ("select_product", "Step 1/5: 智能选品"),
                    ("run_listing", "Step 2/5: Listing优化"),
                    ("check_compliance", "Step 3/5: 合规审查"),
                    ("generate_social", "Step 4/5: 社媒内容"),
                    ("monitor_reviews", "Step 5/5: 评论监控"),
                ]
                for action, label in pipeline:
                    _task_states[task_id]["progress"] = label
                    # 每步前自动补全上下文
                    pipeline_ctx = await agent._auto_fill_context(pipeline_ctx, action)

                    dec = {"action": action, "reason": label, "status": "running"}
                    try:
                        result_str, data = await agent._execute_action(action, pipeline_ctx)
                        dec["status"] = "done"
                        dec["result"] = str(result_str)[:300]
                        dec["data"] = data or {}
                        # 传递结果到下游
                        pipeline_ctx = _merge_result_to_ctx(pipeline_ctx, action, data)
                    except Exception as e:
                        dec["status"] = "failed"
                        dec["result"] = str(e)[:200]
                    decisions.append(dec)

                result_data = {
                    "id": task_id[:8], "action": request.action,
                    "decisions": decisions,
                    "summary": f"Pipeline: {sum(1 for d in decisions if d.get('status')=='done')}/{len(decisions)} done",
                    "notifications": [],
                }
            else:
                result = await agent.run(req_input)
                result_data = {
                    "id": task_id[:8], "action": request.action,
                    "decisions": [d.model_dump() for d in result.decisions],
                    "summary": result.summary,
                    "notifications": result.notifications,
                }

            _task_states[task_id]["status"] = "completed"
            _task_states[task_id]["progress"] = "done"
            _task_states[task_id]["result"] = result_data
            _logs.insert(0, result_data)
            if len(_logs) > 50:
                _logs.pop()
        except Exception as e:
            _task_states[task_id]["status"] = "failed"
            _task_states[task_id]["error"] = str(e)

    asyncio.create_task(background())
    return {"task_id": task_id, "action": request.action, "status": "running"}


@router.get("/{task_id}/status")
async def get_task_status(task_id: str):
    """查询调度任务进度"""
    if task_id not in _task_states:
        raise HTTPException(status_code=404, detail="Task not found")
    t = _task_states[task_id]
    return {
        "task_id": task_id, "status": t.get("status", "running"),
        "progress": t.get("progress", ""),
        "completed_steps": len(t.get("result", {}).get("decisions", [])) if t.get("result") else 0,
        "error": t.get("error", ""),
    }


@router.get("/{task_id}/result")
async def get_task_result(task_id: str):
    """获取调度完整结果"""
    if task_id not in _task_states:
        raise HTTPException(status_code=404, detail="Task not found")
    t = _task_states[task_id]
    if t.get("status") not in ("completed", "failed"):
        raise HTTPException(status_code=425, detail="Task still running")
    return t.get("result", t)


@router.post("/webhook")
async def orchestrator_webhook(request: dict = {}):
    """crontab 定时调用的入口"""
    agent = OrchestratorAgent()
    result = await agent.run(OrchestratorInput(
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
    return _logs


@router.get("/status")
async def get_status():
    return {
        "orchestrator": "active",
        "total_runs": len(_logs),
        "last_run": _logs[0] if _logs else None,
        "supported_actions": ["auto", "select_product", "run_listing", "check_compliance", "generate_social", "monitor_reviews"],
    }
