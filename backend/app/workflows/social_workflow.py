"""
社媒内容工作流 — LangGraph StateGraph (Phase 2 优化版)

Agent 链:
产品信息 → [1.产品分析] → [2.平台适配·规则] → [3.文案生成×N·并行]
                                                    ↓
          [5.质量检查×N·并行] ← → [4.图片生成×N·并行]
                    ↓
              Human Preview

优化点:
- PlatformAdapter: 纯规则, 0 LLM
- CopyGenerator: asyncio.gather 并行 N 个平台
- ImageGenerator + QualityChecker: 同一节点内并行
"""

import asyncio
from typing import TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from backend.app.agents.social.product_analysis import ProductAnalysisAgent, ProductAnalysisInput
from backend.app.agents.social.platform_adapter import PlatformAdapterAgent, PlatformAdapterInput
from backend.app.agents.social.copy_generator import CopyGeneratorAgent, CopyGeneratorInput
from backend.app.agents.social.image_generator import ImageGeneratorAgent, ImageGeneratorInput
from backend.app.agents.social.quality_checker import QualityCheckerAgent, QualityCheckerInput


class SocialState(TypedDict):
    task_id: str
    product_name: str
    category: str
    features: list[str]
    brand_story: str
    platforms: list[str]
    language: str
    target_markets: list[str]

    marketing_angles: list[str]
    target_audience: str
    content_tones: list[str]
    key_selling_points: list[str]
    visual_style: list[str]
    hashtag_themes: list[str]
    platform_requirements: list[dict]
    posts: list[dict]

    status: str
    error: str
    current_step: str


pa_agent = ProductAnalysisAgent()
pad_agent = PlatformAdapterAgent()


async def product_analysis_node(state: SocialState) -> SocialState:
    try:
        result = await pa_agent.run(
            ProductAnalysisInput(
                product_name=state["product_name"],
                category=state["category"],
                features=state["features"],
                brand_story=state.get("brand_story", ""),
                target_markets=state.get("target_markets", ["US"]),
            ),
            context={"task_id": state["task_id"]},
        )
        state["marketing_angles"] = result.marketing_angles
        state["target_audience"] = result.target_audience
        state["content_tones"] = result.content_tones
        state["key_selling_points"] = result.key_selling_points
        state["visual_style"] = result.visual_style_suggestions
        state["hashtag_themes"] = result.hashtag_themes
        state["current_step"] = "analysis_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def platform_adapter_node(state: SocialState) -> SocialState:
    if state["status"] == "failed":
        return state
    try:
        tone = state["content_tones"][0] if state["content_tones"] else "professional"
        result = await pad_agent.run(
            PlatformAdapterInput(
                product_name=state["product_name"],
                key_selling_points=state["key_selling_points"],
                platforms=state["platforms"],
                content_tone=tone,
            ),
        )
        state["platform_requirements"] = [r.model_dump() for r in result.platform_requirements]
        state["current_step"] = "adapter_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def _generate_one_copy(
    product_name: str, language: str, selling_points: list[str],
    req: dict, tone: str, audience: str, task_id: str
) -> dict:
    agent = CopyGeneratorAgent()
    result = await agent.run(
        CopyGeneratorInput(
            product_name=product_name,
            platform=req["platform"],
            language=language,
            selling_points=selling_points,
            content_angle=req.get("content_angle", ""),
            content_tone=tone,
            target_audience=audience,
        ),
        context={"task_id": task_id},
    )
    return {
        "platform": req["platform"],
        "language": language,
        "copy": result.copy,
        "short_copy": result.short_copy,
        "hashtags": result.hashtags,
        "call_to_action": result.call_to_action,
        "emoji_suggestions": result.emoji_suggestions,
        "images": [],
        "quality_score": 0.0,
        "quality_verdict": "pending",
        "status": "draft",
    }


async def copy_generator_node(state: SocialState) -> SocialState:
    if state["status"] == "failed":
        return state
    try:
        tone = state["content_tones"][0] if state["content_tones"] else "professional"
        audience = state.get("target_audience", "")

        # 并行生成所有平台的文案
        tasks = [
            _generate_one_copy(
                state["product_name"], state["language"],
                state["key_selling_points"], req, tone, audience,
                state["task_id"],
            )
            for req in state["platform_requirements"]
        ]
        state["posts"] = await asyncio.gather(*tasks)
        state["current_step"] = "copy_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def _generate_one_image(
    product_name: str, post: dict, visual_hint: str, task_id: str
) -> list[dict]:
    agent = ImageGeneratorAgent()
    size = "instagram_post" if post["platform"] == "instagram" else "generic_square"
    result = await agent.run(
        ImageGeneratorInput(
            prompt=f"{product_name} product photo, {visual_hint}",
            style=visual_hint,
            platform=post["platform"],
            image_size=size,
            num_images=1,
        ),
        context={"task_id": task_id},
    )
    return [img.model_dump() for img in result.images]


async def _check_one_post(
    post: dict, language: str, product_name: str, task_id: str
) -> dict:
    agent = QualityCheckerAgent()
    result = await agent.run(
        QualityCheckerInput(
            copy=post.get("copy", ""),
            platform=post["platform"],
            language=language,
            product_name=product_name,
        ),
        context={"task_id": task_id},
    )
    return {
        "quality_score": result.overall_score,
        "quality_verdict": result.verdict,
        "quality_issues": result.issues,
        "quality_suggestions": result.suggestions,
    }


async def media_and_quality_node(state: SocialState) -> SocialState:
    """图片生成和质量检查并行运行"""
    if state["status"] == "failed":
        return state
    try:
        visual_hint = state["visual_style"][0] if state["visual_style"] else "product photography"
        posts = state["posts"]
        task_id = state["task_id"]
        product_name = state["product_name"]
        language = state["language"]

        # 并行：所有平台的图片 + 所有平台的质量检查
        img_tasks = [
            _generate_one_image(product_name, post, visual_hint, task_id)
            for post in posts
        ]
        qc_tasks = [
            _check_one_post(post, language, product_name, task_id)
            for post in posts
        ]

        all_img_results, all_qc_results = await asyncio.gather(
            asyncio.gather(*img_tasks),
            asyncio.gather(*qc_tasks),
        )

        # 合并结果
        for i, post in enumerate(posts):
            post["images"] = all_img_results[i]
            post.update(all_qc_results[i])

        state["current_step"] = "media_quality_done"
        state["status"] = "awaiting_review"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


def build_social_workflow() -> StateGraph:
    workflow = StateGraph(SocialState)

    workflow.add_node("product_analysis", product_analysis_node)
    workflow.add_node("platform_adapter", platform_adapter_node)
    workflow.add_node("copy_generator", copy_generator_node)
    workflow.add_node("media_and_quality", media_and_quality_node)

    workflow.set_entry_point("product_analysis")
    workflow.add_edge("product_analysis", "platform_adapter")
    workflow.add_edge("platform_adapter", "copy_generator")
    workflow.add_edge("copy_generator", "media_and_quality")
    workflow.add_edge("media_and_quality", END)

    return workflow


social_workflow = build_social_workflow().compile(
    checkpointer=MemorySaver(),
    interrupt_after=["media_and_quality"],
)
