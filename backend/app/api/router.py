"""
路由 API — 自然语言入口，LLM 意图识别 + 链路分发。

POST /api/v1/router/chat  — 发送自然语言消息，返回 task_id
GET  /api/v1/router/{task_id}/status  — 轮询任务进度
GET  /api/v1/router/{task_id}/result  — 获取任务结果
"""

import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.agents.router.router_agent import RouterAgent, RouterInput
from backend.app.core.context_bus import ContextBus
from backend.app.core.db import async_session
from backend.app.models.models import OrchestratorRun

router = APIRouter(prefix="/api/v1/router", tags=["router"])

_task_states: dict[str, dict] = {}
_bus = ContextBus()


class ChatRequest(BaseModel):
    message: str = Field(..., description="自然语言输入，例如: '帮我在美国市场分析蓝牙耳机'")


class ChatResponse(BaseModel):
    task_id: str
    chain: str
    chain_name: str
    reasoning: str
    status: str = "running"


@router.post("/chat", response_model=ChatResponse)
async def router_chat(request: ChatRequest):
    """自然语言入口 — LLM 分析意图 → 路由到对应链路 → 异步执行"""
    task_id = str(uuid.uuid4())
    message = request.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    _task_states[task_id] = {
        "task_id": task_id,
        "status": "analyzing",
        "progress": "LLM 分析意图中...",
        "message": message,
    }

    # 后台异步执行
    async def background():
        try:
            _task_states[task_id]["progress"] = "意图识别中..."
            agent = RouterAgent(bus=_bus)
            result = await agent.run(RouterInput(message=message))

            decision = result.decision
            chain_name_map = {
                "selection_listing": "选品上架链",
                "marketing": "营销推广链",
                "aftersales": "售后监控链",
                "full_pipeline": "全链路调度",
                "clarify": "需要更多信息",
            }

            _task_states[task_id].update({
                "status": "completed" if decision.chain != "clarify" else "clarify",
                "progress": "done",
                "chain": decision.chain,
                "chain_name": chain_name_map.get(decision.chain, decision.chain),
                "reasoning": decision.reasoning,
                "confidence": decision.confidence,
                "params": decision.params,
                "chain_result": result.chain_result,
                "summary": result.summary,
            })

            # 持久化到 DB
            await _save_router_run(task_id, message, decision.chain, result.summary)

        except Exception as e:
            _task_states[task_id].update({
                "status": "failed",
                "progress": "failed",
                "error": str(e),
            })

    asyncio.create_task(background())

    return ChatResponse(
        task_id=task_id,
        chain="analyzing",
        chain_name="分析中",
        reasoning="正在分析您的需求...",
        status="running",
    )


@router.get("/chains")
async def list_chains():
    """列出所有可用链路"""
    from backend.app.agents.router.router_agent import CHAIN_REGISTRY

    return {
        "chains": [
            {
                "id": chain_id,
                "name": info["name"],
                "description": info["description"],
                "examples": info["examples"][:2],
            }
            for chain_id, info in CHAIN_REGISTRY.items()
        ],
    }


@router.get("/{task_id}/status")
async def get_router_task_status(task_id: str):
    """轮询路由任务进度"""
    if task_id in _task_states:
        t = _task_states[task_id]
        return {
            "task_id": task_id,
            "status": t.get("status", "running"),
            "progress": t.get("progress", ""),
            "chain": t.get("chain", ""),
            "chain_name": t.get("chain_name", ""),
            "reasoning": t.get("reasoning", ""),
            "error": t.get("error", ""),
        }
    raise HTTPException(status_code=404, detail="Task not found")


@router.get("/{task_id}/result")
async def get_router_task_result(task_id: str):
    """获取路由任务完整结果"""
    if task_id in _task_states:
        t = _task_states[task_id]
        if t.get("status") not in ("completed", "failed", "clarify"):
            raise HTTPException(status_code=425, detail="Task still running")
        return {
            "task_id": task_id,
            "message": t.get("message", ""),
            "chain": t.get("chain", ""),
            "chain_name": t.get("chain_name", ""),
            "reasoning": t.get("reasoning", ""),
            "confidence": t.get("confidence", 0),
            "params": t.get("params", {}),
            "chain_result": t.get("chain_result", []),
            "summary": t.get("summary", ""),
            "status": t.get("status", ""),
            "error": t.get("error", ""),
        }
    raise HTTPException(status_code=404, detail="Task not found")


async def _save_router_run(task_id: str, message: str, chain: str, summary: str):
    """持久化路由记录到 DB"""
    try:
        import uuid as _uuid
        async with async_session() as session:
            run = OrchestratorRun(
                id=_uuid.UUID(task_id),
                action=f"router:{chain}",
                category=message[:100],
                context={"message": message, "chain": chain},
                status="completed",
                progress="done",
                summary=summary,
                total_steps=1,
                completed_steps=1,
            )
            session.add(run)
            await session.commit()
    except Exception:
        import traceback
        traceback.print_exc()
