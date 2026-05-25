"""社媒内容 API 路由"""

import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from backend.app.core.db import async_session
from backend.app.models.models import SocialTask, SocialPost, SocialImage
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


async def _save_social_to_db(task_id: str, request: SocialGenerateRequest, state: dict):
    """将社媒内容生成结果持久化到数据库"""
    import uuid as _uuid
    try:
        async with async_session() as session:
            # 检查是否已存在
            from sqlalchemy import select
            r = await session.execute(
                select(SocialTask).where(SocialTask.id == _uuid.UUID(task_id))
            )
            existing = r.scalar_one_or_none()

            if existing:
                existing.status = state.get("status", "completed")
            else:
                s_task = SocialTask(
                    id=_uuid.UUID(task_id),
                    product_name=request.product_name,
                    category=request.category,
                    platforms=request.platforms,
                    target_languages=request.target_markets,
                    status=state.get("status", "completed"),
                )
                session.add(s_task)

            # 保存帖子
            for post_data in state.get("posts", []):
                pid = _uuid.uuid4()
                post = SocialPost(
                    id=pid,
                    task_id=_uuid.UUID(task_id),
                    platform=post_data.get("platform", ""),
                    language=post_data.get("language", request.language),
                    copy=post_data.get("copy", ""),
                    short_copy=post_data.get("short_copy", ""),
                    hashtags=post_data.get("hashtags", []),
                    call_to_action=post_data.get("call_to_action", ""),
                    image_urls=[img.get("url", "") for img in post_data.get("images", [])],
                    quality_score=post_data.get("quality_score", 0.0),
                    quality_verdict=post_data.get("quality_verdict", "approved"),
                    status="generated",
                )
                session.add(post)
                await session.flush()  # 获取 post.id

                # 保存图片关联
                for img_data in post_data.get("images", []):
                    if img_data.get("url"):
                        img = SocialImage(
                            post_id=pid,
                            url=img_data.get("url", ""),
                            alt_text=img_data.get("alt_text", img_data.get("description", "")),
                            prompt=img_data.get("prompt", img_data.get("description", "")),
                            storage_path=img_data.get("storage_path"),
                            width=img_data.get("width"),
                            height=img_data.get("height"),
                            format=img_data.get("format"),
                        )
                        session.add(img)

            await session.commit()
    except Exception:
        import traceback
        traceback.print_exc()


async def _update_post_status_in_db(post_id: str, status: str):
    """更新帖子的数据库状态"""
    try:
        import uuid as _uuid
        async with async_session() as session:
            from sqlalchemy import select
            r = await session.execute(
                select(SocialPost).where(SocialPost.id == _uuid.UUID(post_id))
            )
            post = r.scalar_one_or_none()
            if post:
                post.status = status
                await session.commit()
    except Exception:
        pass


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
            # 将帖子存入 _posts (内存) + 持久化到数据库
            await _save_social_to_db(task_id, request, _task_states[task_id])
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
    import uuid as _uuid
    if post_id not in _posts:
        raise HTTPException(status_code=404, detail="Post not found")
    new_status = "approved" if approved else "rejected"
    _posts[post_id]["status"] = new_status
    # 同步数据库
    try:
        async with async_session() as session:
            from sqlalchemy import select
            r = await session.execute(
                select(SocialPost).where(SocialPost.id == _uuid.UUID(post_id))
            )
            post = r.scalar_one_or_none()
            if post:
                post.status = new_status
                await session.commit()
    except Exception:
        pass
    return {"post_id": post_id, "status": new_status}


@router.post("/posts/{post_id}/publish")
async def publish_post(post_id: str):
    """发布帖子 — 通过 SocialPublisher 路由到 WordPress / 小红书"""
    if post_id not in _posts:
        raise HTTPException(status_code=404, detail="Post not found")

    p = _posts[post_id]
    platform = p.get("platform", "").lower().strip()

    # 小红书走浏览器发布通道
    if platform in ("xiaohongshu", "xhs", "小红书"):
        return await _publish_to_xiaohongshu(post_id, p)

    # 其他平台走 WordPress
    try:
        from backend.app.gateway.social_publisher import SocialPublisher
        publisher = SocialPublisher()
        result = await publisher.publish(p, product_name=p.get("product_name", ""))
        if result.success:
            p["status"] = "published"
            p["wp_post_id"] = result.remote_id
            p["wp_url"] = result.remote_url
            # 同步数据库
            await _update_post_status_in_db(post_id, "published")
            wp_result = result.raw_response or {"wordpress_post_id": result.remote_id, "wordpress_url": result.remote_url}
            return {
                "post_id": post_id,
                "status": "published",
                "platform": p.get("platform"),
                "wordpress": wp_result,
                "message": f"已发布到 WordPress",
            }
        else:
            p["status"] = "failed"
            raise HTTPException(
                status_code=500,
                detail=f"WordPress 发布失败: {'; '.join(result.errors)}",
            )
    except HTTPException:
        raise
    except Exception as e:
        p["status"] = "failed"
        raise HTTPException(status_code=500, detail=f"WordPress 发布异常: {str(e)}")


async def _publish_to_xiaohongshu(post_id: str, p: dict) -> dict:
    """发布到小红书（Playwright 浏览器自动化）"""
    try:
        from backend.app.gateway.social_publisher import SocialPublisher
        publisher = SocialPublisher()
        result = await publisher.publish(p, product_name=p.get("product_name", ""))

        if result.success:
            p["status"] = "published"
            p["xhs_url"] = result.remote_url
            await _update_post_status_in_db(post_id, "published")
            return {
                "post_id": post_id,
                "status": "published",
                "platform": "xiaohongshu",
                "remote_url": result.remote_url,
                "message": "已发布到小红书",
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"小红书发布失败: {'; '.join(result.errors)}",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"小红书发布异常: {str(e)}")
    # 注意：不调用 publisher.stop()，浏览器保持打开让人工点击发布按钮


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


# ── 小红书专用端点 ────────────────────────────

@router.get("/xiaohongshu/health")
async def xiaohongshu_health():
    """检查小红书 MCP Gateway 状态"""
    from backend.app.gateway.xiaohongshu_gateway import XiaohongshuGateway

    has_cookies = XiaohongshuGateway.is_logged_in()
    return {
        "status": "ok" if has_cookies else "need_login",
        "has_cookies": has_cookies,
        "logged_in": has_cookies,
        "cookie_file": str(Path("data/xhs_mcp_cookies.json")),
        "hint": "未登录请 POST /api/v1/social/xiaohongshu/login 获取登录命令",
    }


@router.post("/xiaohongshu/login")
async def xiaohongshu_login(request: dict = {}):
    """小红书登录 — 返回登录命令，用户在终端执行后输入验证码"""
    from backend.app.gateway.xiaohongshu_gateway import XiaohongshuGateway

    phone = request.get("phone", "")
    if not phone:
        return {
            "status": "error",
            "message": "请提供手机号",
            "hint": "POST /api/v1/social/xiaohongshu/login  Body: {\"phone\": \"13800138000\"}",
        }

    cookie_path = str(Path("data/xhs_mcp_cookies.json").absolute())
    cmd = f'env phone={phone} json_path={cookie_path} uvx --from xhs_mcp_server@latest login'

    return {
        "status": "pending",
        "message": "请在终端执行以下命令完成登录（输入手机验证码）",
        "command": cmd,
        "steps": [
            "1. 复制上面的 command，在终端粘贴执行",
            "2. 手机会收到验证码，输入验证码",
            "3. 看到 'login success' 即完成",
            "4. 之后回到社媒页面点击「发布」即可",
        ],
    }


@router.get("/xiaohongshu/posts")
async def xiaohongshu_posts():
    """获取已发布的小红书笔记列表"""
    try:
        from backend.app.gateway.xiaohongshu_gateway import XiaohongshuGateway
        gw = XiaohongshuGateway()
        await gw.start()
        posts = await gw.get_published_posts(max_count=10)
        await gw.stop()
        return {"posts": posts}
    except Exception as e:
        return {"posts": [], "error": str(e)}


@router.post("/xiaohongshu/publish")
async def xiaohongshu_publish(request: dict = {}):
    """直接发布到小红书（测试用）"""
    try:
        from backend.app.gateway.social_publisher import SocialPublisher
        publisher = SocialPublisher()

        post = {
            "platform": "xiaohongshu",
            "copy": request.get("copy", request.get("content", "")),
            "short_copy": request.get("title", ""),
            "hashtags": request.get("hashtags", []),
            "image_urls": request.get("image_urls", []),
        }

        result = await publisher.publish(post, product_name=request.get("product_name", ""))
        await publisher.stop()

        return {
            "success": result.success,
            "status": result.status,
            "errors": result.errors,
            "remote_url": result.remote_url,
        }
    except Exception as e:
        return {"success": False, "status": "error", "errors": [str(e)]}
