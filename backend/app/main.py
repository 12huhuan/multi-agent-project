"""
Cross-Border Agents — FastAPI 主入口

Phase 1: Listing 优化 + 智能客服
提供 REST API + WebSocket 实时推送
"""

import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api.listing import router as listing_router
from backend.app.api.customer_service import router as cs_router
from backend.app.api.knowledge_base import router as kb_router
from backend.app.core.config import settings
from backend.app.core.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    # 启动时初始化数据库表
    if settings.debug:
        try:
            await init_db()
        except Exception:
            pass
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="跨境电商多 Agent 系统 — Phase 1: Listing 优化 + 智能客服",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(listing_router)
app.include_router(cs_router)
app.include_router(kb_router)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": settings.version,
        "services": {"database": "postgresql", "vector_db": "chromadb", "cache": "redis"},
    }


@app.get("/api/agents")
async def list_agents():
    return {
        "agents": [
            {"name": "keyword_research", "workflow": "listing", "description": "关键词研究与搜索意图分析"},
            {"name": "title_generation", "workflow": "listing", "description": "标题生成与合规检查"},
            {"name": "bullet_points", "workflow": "listing", "description": "五点描述生成"},
            {"name": "description", "workflow": "listing", "description": "HTML长描述生成"},
            {"name": "aplus_content", "workflow": "listing", "description": "A+内容布局设计"},
            {"name": "seo_scoring", "workflow": "listing", "description": "SEO质量评分"},
            {"name": "intent_recognition", "workflow": "customer_service", "description": "用户意图识别"},
            {"name": "knowledge_retrieval", "workflow": "customer_service", "description": "RAG知识检索"},
            {"name": "reply_generation", "workflow": "customer_service", "description": "多语言回复生成"},
            {"name": "escalation_decision", "workflow": "customer_service", "description": "升级决策"},
            {"name": "ticket_generation", "workflow": "customer_service", "description": "工单生成"},
        ],
        "total": 11,
        "version": settings.version,
    }


# WebSocket — 通用工作流进度推送
@app.websocket("/ws/workflows/{task_id}")
async def workflow_socket(websocket: WebSocket, task_id: str):
    await websocket.accept()
    try:
        from backend.app.api.listing import _task_states
        import asyncio
        while True:
            if task_id in _task_states:
                state = _task_states[task_id]
                await websocket.send_json({"type": "progress", "data": state.get("current_step", "")})
                if state.get("status") in ("completed", "failed", "awaiting_review"):
                    await websocket.send_json({"type": "done", "status": state["status"]})
                    break
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass


# 通用工作流触发
@app.post("/api/v1/workflows/{workflow_type}/run")
async def trigger_workflow(workflow_type: str):
    """通用工作流触发入口"""
    return {
        "workflow_type": workflow_type,
        "message": f"请使用专用端点: /api/v1/{workflow_type}/run",
        "supported": ["listing", "customer_service"],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
