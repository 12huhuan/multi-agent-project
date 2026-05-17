"""顶层调度 API 路由 — v2 ContextBus 驱动"""

import asyncio
import uuid
from fastapi import APIRouter, HTTPException

from backend.app.schemas.schemas import OrchestratorRunRequest
from backend.app.agents.orchestrator.orchestrator import OrchestratorAgent, OrchestratorInput
from backend.app.core.context_bus import ContextBus

router = APIRouter(prefix="/api/v1/orchestrator", tags=["orchestrator"])

_task_states: dict[str, dict] = {}
_logs: list[dict] = []
_bus = ContextBus()


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
            agent = OrchestratorAgent(bus=_bus)
            req_input = OrchestratorInput(action=request.action, context=request.context)

            if request.action == "auto":
                ctx = dict(request.context) if request.context else {}
                category = ctx.get("category", "")
                pctx = _bus.create(
                    category=category,
                    target_market=ctx.get("target_market", "US"),
                    seller_budget=ctx.get("seller_budget", "$5000-$15000"),
                )

                # Pre-fill keywords / strengths（Amazon Autocomplete 真实热词 + LLM 兜底）
                if category and not ctx.get("keywords"):
                    ctx["keywords"] = await agent._generate_keywords(category)
                if category and not ctx.get("seller_strengths"):
                    ctx["seller_strengths"] = await agent._generate_strengths(category)
                if ctx.get("seller_strengths"):
                    pctx.identity.seller_strengths = ctx["seller_strengths"]
                # 把 Amazon 热词注入 ProductContext，让 Listing 工作流直接使用
                if ctx.get("keywords") and not pctx.market_insight.competitor_keywords:
                    pctx.market_insight.competitor_keywords = ctx["keywords"]

                decisions = []
                pipeline = [
                    ("selection", "select_product", "Step 1/5: 智能选品"),
                    ("listing", "run_listing", "Step 2/5: Listing优化"),
                    ("compliance", "check_compliance", "Step 3/5: 合规审查"),
                    ("social", "generate_social", "Step 4/5: 社媒内容"),
                    ("review", "monitor_reviews", "Step 5/5: 评论监控"),
                ]

                for domain, action, label in pipeline:
                    _task_states[task_id]["progress"] = label
                    dec = {"action": action, "reason": label, "status": "running"}

                    try:
                        # derive → ensure → execute → ingest
                        state = _bus.derive(domain, pctx)
                        state = await agent._ensure_state_fields(domain, state, ctx)
                        result_str, data = await agent._execute_with_state(domain, state)
                        pctx = await _bus.ingest(domain, data, pctx)

                        dec["status"] = "done"
                        dec["result"] = str(result_str)[:300]
                        dec["data"] = data or {}
                    except Exception as e:
                        dec["status"] = "failed"
                        dec["result"] = str(e)[:200]
                    decisions.append(dec)

                _bus.save(pctx)

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
    if task_id not in _task_states:
        raise HTTPException(status_code=404, detail="Task not found")
    t = _task_states[task_id]
    if t.get("status") not in ("completed", "failed"):
        raise HTTPException(status_code=425, detail="Task still running")
    return t.get("result", t)


@router.post("/webhook")
async def orchestrator_webhook(request: dict = {}):
    agent = OrchestratorAgent(bus=_bus)
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


# ── 企微通知端点 ─────────────────────────────

@router.post("/notify/test")
async def test_notification():
    """测试通知是否连通"""
    from backend.app.core.wecom import send_notification, SERVERCHAN_SENDKEY, WECOM_WEBHOOK_URL, PUSHPLUS_TOKEN
    if not any([SERVERCHAN_SENDKEY, WECOM_WEBHOOK_URL, PUSHPLUS_TOKEN]):
        return {
            "status": "not_configured",
            "message": "未配置任何通知渠道，请在 .env 中设置 SERVERCHAN_SENDKEY / WECOM_WEBHOOK_URL / PUSHPLUS_TOKEN",
        }
    ok = await send_notification("✅ CrossBorder Agents 通知测试", "通知功能已正常连通。")
    return {"status": "ok" if ok else "failed", "sent": ok}


@router.post("/notify/alert")
async def send_manual_alert(request: dict = {}):
    """手动发送一条预警通知"""
    from backend.app.core.wecom import send_notification
    msg = request.get("message", "预警通知: 请检查系统状态")
    ok = await send_notification("⚠️ 系统预警", msg)
    return {"status": "ok" if ok else "failed", "sent": ok}


@router.get("/notify/config")
async def get_notification_config():
    """查看通知配置状态"""
    import os
    return {
        "configured": any([
            os.getenv("SERVERCHAN_SENDKEY", ""),
            os.getenv("WECOM_WEBHOOK_URL", ""),
            os.getenv("PUSHPLUS_TOKEN", ""),
        ]),
        "channels": {
            "serverchan": bool(os.getenv("SERVERCHAN_SENDKEY", "")),
            "wecom": bool(os.getenv("WECOM_WEBHOOK_URL", "")),
            "pushplus": bool(os.getenv("PUSHPLUS_TOKEN", "")),
        },
    }
