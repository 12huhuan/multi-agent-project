"""社媒内容 API 路由"""

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from backend.app.schemas.schemas import (
    SocialGenerateRequest,
    SocialPostResponse,
    SocialPostTranslateRequest,
)
from backend.app.workflows.social_workflow import social_workflow, SocialState
from backend.app.agents.shared.translator import TranslatorAgent, TranslatorInput

router = APIRouter(prefix="/api/v1/social", tags=["social"])

# 内存存储
_task_states: dict[str, dict] = {}
_posts: dict[str, dict] = {}  # post_id → post dict


@router.post("/generate")
async def generate_social_content(request: SocialGenerateRequest):
    """触发社媒内容生成工作流"""
    task_id = str(uuid.uuid4())

    initial_state: SocialState = {
        "task_id": task_id,
        "product_name": request.product_name,
        "category": request.category,
        "features": request.features,
        "brand_story": request.brand_story,
        "platforms": request.platforms,
        "language": request.language,
        "target_markets": request.target_markets,
        "marketing_angles": [],
        "target_audience": "",
        "content_tones": [],
        "key_selling_points": [],
        "visual_style": [],
        "hashtag_themes": [],
        "platform_requirements": [],
        "posts": [],
        "status": "running",
        "error": "",
        "current_step": "started",
    }

    _task_states[task_id] = initial_state

    import asyncio
    config = {"configurable": {"thread_id": task_id}}

    async def run_in_background():
        try:
            async for chunk in social_workflow.astream(initial_state, config):
                for node_name, node_state in chunk.items():
                    if isinstance(node_state, dict):
                        _task_states[task_id].update(node_state)
            # 将帖子存入 _posts
            for post in _task_states[task_id].get("posts", []):
                pid = str(uuid.uuid4())
                post["id"] = pid
                post["product_name"] = request.product_name
                post["status"] = "generated"
                _posts[pid] = post
        except Exception as e:
            import traceback
            traceback.print_exc()
            _task_states[task_id]["status"] = "failed"
            _task_states[task_id]["error"] = str(e)

    asyncio.create_task(run_in_background())

    return {
        "task_id": task_id,
        "product_name": request.product_name,
        "platforms": request.platforms,
        "status": "running",
        "message": f"开始为 {request.product_name} 生成社媒内容",
    }


@router.get("/{task_id}/status")
async def get_social_task_status(task_id: str):
    """查询社媒内容生成任务状态和进度"""
    if task_id not in _task_states:
        raise HTTPException(status_code=404, detail="Task not found")
    state = _task_states[task_id]
    return {
        "task_id": task_id,
        "status": state.get("status", "running"),
        "current_step": state.get("current_step", ""),
        "posts_count": len(state.get("posts", [])),
        "error": state.get("error", ""),
    }


@router.get("/{task_id}/result")
async def get_social_task_result(task_id: str):
    """获取社媒内容生成最终结果"""
    if task_id not in _task_states:
        raise HTTPException(status_code=404, detail="Task not found")
    state = _task_states[task_id]
    return {
        "task_id": task_id,
        "status": state.get("status"),
        "posts": state.get("posts", []),
        "marketing_angles": state.get("marketing_angles", []),
        "key_selling_points": state.get("key_selling_points", []),
    }


@router.get("/posts", response_model=list[SocialPostResponse])
async def list_posts(platform: str = "", status: str = ""):
    """帖子列表，支持按平台和状态筛选"""
    results = []
    for pid, p in _posts.items():
        if platform and p.get("platform", "") != platform:
            continue
        if status and p.get("status", "") != status:
            continue
        results.append(SocialPostResponse(
            id=pid,
            product_name=p.get("product_name", ""),
            platform=p.get("platform", ""),
            language=p.get("language", "en"),
            copy=p.get("copy", ""),
            short_copy=p.get("short_copy", ""),
            hashtags=p.get("hashtags", []),
            call_to_action=p.get("call_to_action", ""),
            image_urls=[img.get("url", "") for img in p.get("images", [])],
            quality_score=p.get("quality_score", 0.0),
            quality_verdict=p.get("quality_verdict", "approved"),
            status=p.get("status", "draft"),
            created_at=p.get("created_at", datetime.now().isoformat()),
        ))
    return results


@router.get("/posts/{post_id}", response_model=SocialPostResponse)
async def get_post(post_id: str):
    """帖子详情"""
    if post_id not in _posts:
        raise HTTPException(status_code=404, detail="Post not found")
    p = _posts[post_id]
    return SocialPostResponse(
        id=post_id,
        product_name=p.get("product_name", ""),
        platform=p.get("platform", ""),
        language=p.get("language", "en"),
        copy=p.get("copy", ""),
        short_copy=p.get("short_copy", ""),
        hashtags=p.get("hashtags", []),
        call_to_action=p.get("call_to_action", ""),
        image_urls=[img.get("url", "") for img in p.get("images", [])],
        quality_score=p.get("quality_score", 0.0),
        quality_verdict=p.get("quality_verdict", "approved"),
        status=p.get("status", "draft"),
        created_at=p.get("created_at", datetime.now().isoformat()),
    )


@router.post("/posts/{post_id}/translate", response_model=SocialPostResponse)
async def translate_post(post_id: str, request: SocialPostTranslateRequest):
    """翻译帖子到目标语言"""
    if post_id not in _posts:
        raise HTTPException(status_code=404, detail="Post not found")

    p = _posts[post_id]
    agent = TranslatorAgent()

    # 翻译主文案
    result = await agent.run(
        TranslatorInput(
            text=p.get("copy", ""),
            source_language=p.get("language", "en"),
            target_language=request.target_language,
            context="social media post",
        ),
        context={"task_id": post_id},
    )

    # 创建新的翻译版本帖子
    translated_id = str(uuid.uuid4())
    translated_post = {
        "id": translated_id,
        "product_name": p.get("product_name", ""),
        "platform": p.get("platform", ""),
        "language": request.target_language,
        "copy": result.translated_text,
        "short_copy": "",
        "hashtags": p.get("hashtags", []),
        "call_to_action": p.get("call_to_action", ""),
        "images": p.get("images", []),
        "quality_score": p.get("quality_score", 0),
        "quality_verdict": "pending",
        "status": "draft",
        "created_at": datetime.now().isoformat(),
    }
    _posts[translated_id] = translated_post

    return SocialPostResponse(
        id=translated_id,
        product_name=translated_post["product_name"],
        platform=translated_post["platform"],
        language=translated_post["language"],
        copy=translated_post["copy"],
        short_copy=translated_post["short_copy"],
        hashtags=translated_post["hashtags"],
        call_to_action=translated_post["call_to_action"],
        image_urls=[img.get("url", "") for img in translated_post.get("images", [])],
        quality_score=translated_post["quality_score"],
        quality_verdict=translated_post["quality_verdict"],
        status=translated_post["status"],
        created_at=translated_post["created_at"],
    )


@router.post("/posts/{post_id}/approve")
async def approve_post(post_id: str, approved: bool = True):
    """审核帖子 (approve/reject)"""
    if post_id not in _posts:
        raise HTTPException(status_code=404, detail="Post not found")
    _posts[post_id]["status"] = "approved" if approved else "rejected"
    return {"post_id": post_id, "status": _posts[post_id]["status"]}


@router.post("/posts/{post_id}/publish")
async def publish_post(post_id: str):
    """发布帖子 (对接 Social Engine/WordPress — 当前为占位)"""
    if post_id not in _posts:
        raise HTTPException(status_code=404, detail="Post not found")

    p = _posts[post_id]
    # 未来对接: 调用 WordPress REST API + Social Engine 发布到各平台
    # 目前标记为 ready_to_publish
    p["status"] = "published"

    return {
        "post_id": post_id,
        "status": "published",
        "platform": p.get("platform"),
        "message": f"帖子已标记为发布 (Social Engine 对接待实现)",
    }


@router.websocket("/{task_id}/stream")
async def social_stream(websocket: WebSocket, task_id: str):
    """WebSocket 实时推送社媒内容生成进度"""
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
                    "posts_count": len(state.get("posts", [])),
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
