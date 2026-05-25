"""顶层调度 API 路由 — v2 ContextBus 驱动 + DB 持久化"""

import asyncio
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from sqlalchemy import select, desc

from backend.app.schemas.schemas import OrchestratorRunRequest
from backend.app.agents.orchestrator.orchestrator import OrchestratorAgent, OrchestratorInput
from backend.app.core.context_bus import ContextBus
from backend.app.core.db import async_session
from backend.app.models.models import OrchestratorRun

router = APIRouter(prefix="/api/v1/orchestrator", tags=["orchestrator"])

_task_states: dict[str, dict] = {}
_logs: list[dict] = []  # 内存缓存，兼容旧调用
_bus = ContextBus()


async def _save_orchestrator_run(
    task_id: str, action: str, status: str, category: str = "",
    progress: str = "", decisions: list | None = None,
    summary: str = "", total_steps: int = 0, completed_steps: int = 0,
    error: str = "", context: dict | None = None,
):
    """持久化/更新调度运行记录到 PostgreSQL"""
    try:
        import uuid as _uuid
        async with async_session() as session:
            result = await session.execute(
                select(OrchestratorRun).where(OrchestratorRun.id == _uuid.UUID(task_id))
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.status = status
                if progress:
                    existing.progress = progress
                if decisions is not None:
                    existing.decisions = [d.model_dump() if hasattr(d, 'model_dump') else d for d in decisions]
                if summary:
                    existing.summary = summary
                if total_steps:
                    existing.total_steps = total_steps
                existing.completed_steps = completed_steps
                if error:
                    existing.error = error
                existing.updated_at = datetime.utcnow()
            else:
                run = OrchestratorRun(
                    id=_uuid.UUID(task_id),
                    action=action,
                    category=category,
                    context=context or {},
                    status=status,
                    progress=progress,
                    decisions=[d.model_dump() if hasattr(d, 'model_dump') else d for d in (decisions or [])],
                    summary=summary,
                    total_steps=total_steps,
                    completed_steps=completed_steps,
                    error=error,
                )
                session.add(run)
            await session.commit()
    except Exception:
        import traceback
        traceback.print_exc()


async def _load_orchestrator_logs_from_db() -> list[dict]:
    try:
        async with async_session() as session:
            result = await session.execute(
                select(OrchestratorRun).order_by(desc(OrchestratorRun.created_at)).limit(50)
            )
            rows = result.scalars().all()
            return [
                {
                    "id": str(r.id)[:8],
                    "action": r.action,
                    "category": r.category,
                    "status": r.status,
                    "summary": r.summary or "",
                    "decisions": r.decisions or [],
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                }
                for r in rows
            ]
    except Exception:
        return []


@router.post("/run")
async def run_orchestrator(request: OrchestratorRunRequest = None):
    """触发调度 (异步后台执行, 立即返回 task_id)"""
    if request is None:
        request = OrchestratorRunRequest()
    task_id = str(uuid.uuid4())
    ctx_input = dict(request.context) if request.context else {}
    category = ctx_input.get("category", "")

    _task_states[task_id] = {
        "task_id": task_id, "action": request.action,
        "status": "running", "progress": "starting", "result": None,
    }

    # 立即创建 DB 记录
    await _save_orchestrator_run(
        task_id=task_id, action=request.action, status="running",
        category=category, progress="starting",
        total_steps=5 if request.action == "auto" else 1,
        context=ctx_input,
    )

    async def background():
        try:
            agent = OrchestratorAgent(bus=_bus)
            req_input = OrchestratorInput(action=request.action, context=request.context)

            if request.action == "auto":
                ctx = ctx_input
                pctx = _bus.create(
                    category=category,
                    target_market=ctx.get("target_market", "US"),
                    seller_budget=ctx.get("seller_budget", "$5000-$15000"),
                )

                if category and not ctx.get("keywords"):
                    ctx["keywords"] = await agent._generate_keywords(category)
                if category and not ctx.get("seller_strengths"):
                    ctx["seller_strengths"] = await agent._generate_strengths(category)
                if ctx.get("seller_strengths"):
                    pctx.identity.seller_strengths = ctx["seller_strengths"]
                if ctx.get("keywords") and not pctx.market_insight.competitor_keywords:
                    pctx.market_insight.competitor_keywords = ctx["keywords"]

                decisions = []
                pipeline = [
                    ("selection", "select_product", "Step 1/5: 智能选品"),
                    ("listing", "run_listing", "Step 2/5: Listing生成"),
                    ("compliance", "check_compliance", "Step 3/5: 合规审查"),
                    ("social", "generate_social", "Step 4/5: 社媒内容"),
                    ("review", "monitor_reviews", "Step 5/5: 评论监控"),
                ]

                for i, (domain, action, label) in enumerate(pipeline):
                    _task_states[task_id]["progress"] = label
                    dec = {"action": action, "reason": label, "status": "running"}

                    try:
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

                    # 每个步骤完成后更新 DB
                    await _save_orchestrator_run(
                        task_id=task_id, action=request.action, status="running",
                        category=category, progress=label,
                        decisions=decisions, completed_steps=i + 1, total_steps=5,
                    )

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
                decisions = result_data["decisions"]

            _task_states[task_id]["status"] = "completed"
            _task_states[task_id]["progress"] = "done"
            _task_states[task_id]["result"] = result_data

            # 写入内存日志缓存
            _logs.insert(0, result_data)
            if len(_logs) > 50:
                _logs.pop()

            # 写入 DB 最终状态
            await _save_orchestrator_run(
                task_id=task_id, action=request.action, status="completed",
                category=category, progress="done",
                decisions=decisions, summary=result_data.get("summary", ""),
                completed_steps=len(decisions), total_steps=len(decisions),
            )
        except Exception as e:
            _task_states[task_id]["status"] = "failed"
            _task_states[task_id]["error"] = str(e)
            await _save_orchestrator_run(
                task_id=task_id, action=request.action, status="failed",
                category=category, error=str(e),
            )

    asyncio.create_task(background())
    return {"task_id": task_id, "action": request.action, "status": "running"}


@router.get("/{task_id}/status")
async def get_task_status(task_id: str):
    # 先查内存
    if task_id in _task_states:
        t = _task_states[task_id]
        return {
            "task_id": task_id, "status": t.get("status", "running"),
            "progress": t.get("progress", ""),
            "completed_steps": len(t.get("result", {}).get("decisions", [])) if t.get("result") else 0,
            "error": t.get("error", ""),
        }
    # DB fallback
    try:
        import uuid as _uuid
        async with async_session() as session:
            result = await session.execute(
                select(OrchestratorRun).where(OrchestratorRun.id == _uuid.UUID(task_id))
            )
            row = result.scalar_one_or_none()
            if row:
                return {
                    "task_id": task_id, "status": row.status,
                    "progress": row.progress or "",
                    "completed_steps": row.completed_steps,
                    "error": row.error or "",
                }
    except Exception:
        pass
    raise HTTPException(status_code=404, detail="Task not found")


@router.get("/{task_id}/result")
async def get_task_result(task_id: str):
    # 先查内存
    if task_id in _task_states:
        t = _task_states[task_id]
        if t.get("status") not in ("completed", "failed"):
            raise HTTPException(status_code=425, detail="Task still running")
        return t.get("result", t)
    # DB fallback
    try:
        import uuid as _uuid
        async with async_session() as session:
            result = await session.execute(
                select(OrchestratorRun).where(OrchestratorRun.id == _uuid.UUID(task_id))
            )
            row = result.scalar_one_or_none()
            if row:
                if row.status not in ("completed", "failed"):
                    raise HTTPException(status_code=425, detail="Task still running")
                return {
                    "id": str(row.id)[:8],
                    "action": row.action,
                    "decisions": row.decisions or [],
                    "summary": row.summary or "",
                    "status": row.status,
                    "notifications": [],
                }
    except Exception:
        pass
    raise HTTPException(status_code=404, detail="Task not found")


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
    """获取调度历史 (DB 优先，内存兜底)"""
    db_logs = await _load_orchestrator_logs_from_db()
    if db_logs:
        return db_logs
    return _logs


@router.get("/status")
async def get_status():
    db_logs = await _load_orchestrator_logs_from_db()
    total_runs = len(db_logs) if db_logs else len(_logs)
    return {
        "orchestrator": "active",
        "total_runs": total_runs,
        "last_run": (db_logs or _logs)[0] if (db_logs or _logs) else None,
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
