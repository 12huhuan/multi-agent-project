"""
路由 API — 自然语言入口，LLM 意图识别 + 链路分发。

POST /api/v1/router/chat  — 发送自然语言消息，LLM同步决策，链路异步执行
GET  /api/v1/router/{task_id}/status  — 轮询任务进度
GET  /api/v1/router/{task_id}/result  — 获取任务结果
"""

import asyncio
import uuid
import traceback
from datetime import datetime

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from backend.app.agents.router.router_agent import RouterAgent, RouterInput, RouteDecision
from backend.app.core.context_bus import ContextBus
from backend.app.core.db import async_session
from backend.app.models.models import OrchestratorRun

router = APIRouter(prefix="/api/v1/router", tags=["router"])

_task_states: dict[str, dict] = {}
_bus = ContextBus()

CHAIN_NAME_MAP = {
    "selection_listing": "选品上架链",
    "marketing": "营销推广链",
    "aftersales": "售后监控链",
    "full_pipeline": "全链路调度",
    "clarify": "需要更多信息",
}


class ChatRequest(BaseModel):
    message: str = Field(..., description="自然语言输入，例如: '帮我在美国市场分析蓝牙耳机'")


class ChatResponse(BaseModel):
    task_id: str
    chain: str
    chain_name: str
    reasoning: str
    params: dict = Field(default_factory=dict)
    confidence: float = 0.0
    status: str = "running"


@router.post("/chat", response_model=ChatResponse)
async def router_chat(request: ChatRequest):
    """自然语言入口 — LLM同步决策路由 + 后台执行链路"""
    task_id = str(uuid.uuid4())
    message = request.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    # Step 1: LLM 意图识别（同步，快速返回）
    agent = RouterAgent(bus=_bus)
    system_prompt, user_prompt = agent.build_prompt(RouterInput(message=message))

    try:
        raw = await agent._call_llm(system_prompt, user_prompt, max_tokens=512, temperature=0.2)
        data = agent._parse_llm_json(raw)
        decision = RouteDecision(
            chain=data.get("chain", "clarify"),
            params=data.get("params", {}),
            reasoning=data.get("reasoning", raw[:100]),
            confidence=data.get("confidence", 0.5),
        )
    except Exception as e:
        decision = RouteDecision(
            chain="clarify",
            reasoning=f"LLM调用失败: {e}",
            confidence=0.0,
        )

    chain_name = CHAIN_NAME_MAP.get(decision.chain, decision.chain)

    # 初始化任务状态
    _task_states[task_id] = {
        "task_id": task_id,
        "message": message,
        "chain": decision.chain,
        "chain_name": chain_name,
        "reasoning": decision.reasoning,
        "confidence": decision.confidence,
        "params": decision.params,
        "status": "running",
        "progress": "链路执行中...",
        "chain_result": [],
        "summary": "",
    }

    # Step 2: 如果是 clarify，直接返回
    if decision.chain == "clarify":
        _task_states[task_id].update({
            "status": "clarify",
            "progress": "done",
        })
        return ChatResponse(
            task_id=task_id,
            chain=decision.chain,
            chain_name=chain_name,
            reasoning=decision.reasoning,
            params=decision.params,
            confidence=decision.confidence,
            status="clarify",
        )

    # Step 3: 后台执行链路
    asyncio.ensure_future(_execute_chain(task_id, decision, message))

    return ChatResponse(
        task_id=task_id,
        chain=decision.chain,
        chain_name=chain_name,
        reasoning=decision.reasoning,
        params=decision.params,
        confidence=decision.confidence,
        status="running",
    )


async def _execute_chain(task_id: str, decision: RouteDecision, message: str):
    """后台执行链路（独立 async 函数，避免闭包引用问题）"""
    try:
        params = decision.params
        ctx = _bus.create(
            category=params.get("category", ""),
            target_market=params.get("target_market", "US"),
            brand_name=params.get("brand_name"),
            seller_budget=params.get("seller_budget", "$5000-$15000"),
        )
        if params.get("platforms"):
            ctx.identity.platforms = params["platforms"]
        if params.get("language"):
            ctx.identity.language = params["language"]

        # LLM 补充关键词
        extra = dict(params)
        if params.get("category") and not extra.get("keywords"):
            try:
                from backend.app.agents.shared.amazon_keywords import get_fetcher
                fetcher = get_fetcher()
                results = await fetcher.fetch_deep(params["category"], max_results=15, translate_fn=None)
                if results:
                    extra["keywords"] = [r["keyword"] for r in results[:15]]
            except Exception:
                pass

        agent = RouterAgent(bus=_bus)
        if not extra.get("keywords"):
            extra["keywords"] = await agent._generate_keywords(params.get("category", ""))
        if not extra.get("seller_strengths"):
            extra["seller_strengths"] = await agent._generate_strengths(params.get("category", ""))
        ctx.market_insight.competitor_keywords = extra.get("keywords", [])

        # 执行链路
        chain_result: list[dict] = []
        if decision.chain == "selection_listing":
            chain_result = await agent.executor.run_selection_listing_chain(ctx, extra)
        elif decision.chain == "marketing":
            chain_result = await agent.executor.run_marketing_chain(ctx, extra)
        elif decision.chain == "aftersales":
            chain_result = await agent.executor.run_aftersales_chain(ctx, extra)
        elif decision.chain == "full_pipeline":
            chain_result = await agent.executor.run_full_pipeline(ctx, extra)

        done = sum(
            1 for d in chain_result
            if isinstance(d, dict) and d.get("status") == "done"
        )
        summary = f"[{decision.chain}] {len(chain_result)} steps, {done} done — {decision.reasoning}"

        _task_states[task_id].update({
            "status": "completed",
            "progress": "done",
            "chain_result": chain_result,
            "summary": summary,
        })

        await _save_router_run(task_id, message, decision.chain, summary)

    except Exception as e:
        traceback.print_exc()
        _task_states[task_id].update({
            "status": "failed",
            "progress": "failed",
            "error": str(e),
        })


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
        pass
