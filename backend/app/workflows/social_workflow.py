"""
社媒内容工作流 — LangGraph StateGraph。

Agent 链:
产品信息 → [1.产品分析] → [2.平台适配] → [3.文案生成] → [4.图片生成] → [5.质量检查] → Human Preview
"""

from typing import TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from backend.app.agents.social.product_analysis import ProductAnalysisAgent, ProductAnalysisInput
from backend.app.agents.social.platform_adapter import PlatformAdapterAgent, PlatformAdapterInput
from backend.app.agents.social.copy_generator import CopyGeneratorAgent, CopyGeneratorInput
from backend.app.agents.social.image_generator import ImageGeneratorAgent, ImageGeneratorInput
from backend.app.agents.social.quality_checker import QualityCheckerAgent, QualityCheckerInput
from backend.app.agents.shared.translator import TranslatorAgent, TranslatorInput


class SocialState(TypedDict):
    # 输入
    task_id: str
    product_name: str
    category: str
    features: list[str]
    brand_story: str
    platforms: list[str]
    language: str
    target_markets: list[str]

    # 中间结果
    marketing_angles: list[str]
    target_audience: str
    content_tones: list[str]
    key_selling_points: list[str]
    visual_style: list[str]
    hashtag_themes: list[str]
    platform_requirements: list[dict]
    posts: list[dict]  # [{platform, language, copy, hashtags, images, quality}]

    # 状态
    status: str
    error: str
    current_step: str


pa_agent = ProductAnalysisAgent()
pad_agent = PlatformAdapterAgent()
copy_agent = CopyGeneratorAgent()
img_agent = ImageGeneratorAgent()
qc_agent = QualityCheckerAgent()
translator_agent = TranslatorAgent()


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
            context={"task_id": state["task_id"]},
        )
        state["platform_requirements"] = [r.model_dump() for r in result.platform_requirements]
        state["current_step"] = "adapter_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def copy_generator_node(state: SocialState) -> SocialState:
    if state["status"] == "failed":
        return state
    try:
        tone = state["content_tones"][0] if state["content_tones"] else "professional"
        posts = []

        for req in state["platform_requirements"]:
            result = await copy_agent.run(
                CopyGeneratorInput(
                    product_name=state["product_name"],
                    platform=req["platform"],
                    language=state["language"],
                    selling_points=state["key_selling_points"],
                    content_angle=req.get("content_angle", ""),
                    content_tone=tone,
                    target_audience=state.get("target_audience", ""),
                ),
                context={"task_id": state["task_id"]},
            )

            posts.append({
                "platform": req["platform"],
                "language": state["language"],
                "copy": result.copy,
                "short_copy": result.short_copy,
                "hashtags": result.hashtags,
                "call_to_action": result.call_to_action,
                "emoji_suggestions": result.emoji_suggestions,
                "images": [],
                "quality_score": 0.0,
                "quality_verdict": "pending",
                "status": "draft",
            })

        state["posts"] = posts
        state["current_step"] = "copy_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def image_generator_node(state: SocialState) -> SocialState:
    if state["status"] == "failed":
        return state
    try:
        for post in state["posts"]:
            visual_hint = state["visual_style"][0] if state["visual_style"] else "product photography"
            result = await img_agent.run(
                ImageGeneratorInput(
                    prompt=f"{state['product_name']} - {post.get('copy', '')[:200]}",
                    style=visual_hint,
                    platform=post["platform"],
                    image_size="instagram_post" if post["platform"] == "instagram" else "generic_square",
                    num_images=1,
                ),
                context={"task_id": state["task_id"]},
            )
            post["images"] = [img.model_dump() for img in result.images]

        state["current_step"] = "image_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def quality_checker_node(state: SocialState) -> SocialState:
    if state["status"] == "failed":
        return state
    try:
        for post in state["posts"]:
            result = await qc_agent.run(
                QualityCheckerInput(
                    copy=post.get("copy", ""),
                    platform=post["platform"],
                    language=state["language"],
                    product_name=state["product_name"],
                ),
                context={"task_id": state["task_id"]},
            )
            post["quality_score"] = result.overall_score
            post["quality_verdict"] = result.verdict
            post["quality_issues"] = result.issues
            post["quality_suggestions"] = result.suggestions

        state["current_step"] = "quality_done"
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
    workflow.add_node("image_generator", image_generator_node)
    workflow.add_node("quality_checker", quality_checker_node)

    workflow.set_entry_point("product_analysis")
    workflow.add_edge("product_analysis", "platform_adapter")
    workflow.add_edge("platform_adapter", "copy_generator")
    workflow.add_edge("copy_generator", "image_generator")
    workflow.add_edge("image_generator", "quality_checker")
    workflow.add_edge("quality_checker", END)

    return workflow


social_workflow = build_social_workflow().compile(
    checkpointer=MemorySaver(),
    interrupt_after=["quality_checker"],
)
