"""
平台适配 Agent — 根据各社交媒体平台规则适配内容格式。

纯规则驱动，不含 LLM 调用。5 个平台的规则内嵌，极速输出。
"""

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent

PLATFORM_RULES = {
    "instagram": {
        "max_length": 2200, "hashtag_limit": 30,
        "best_practices": "Visual-first, 5-10 hashtags, emoji-friendly, call to action in caption, "
                          "use line breaks for readability, @mentions for collabs",
    },
    "threads": {
        "max_length": 500, "hashtag_limit": 5,
        "best_practices": "Conversational tone, short paragraphs, 1-2 hashtags max, "
                          "text-focused, can be more casual and authentic",
    },
    "pinterest": {
        "max_length": 500, "hashtag_limit": 5,
        "best_practices": "SEO-optimized description, 3-5 keywords, 2-3 hashtags, "
                          "inspirational tone, 'save for later' CTAs, vertical image 2:3 ratio",
    },
    "facebook": {
        "max_length": 2000, "hashtag_limit": 5,
        "best_practices": "Engagement-focused, ask questions, 1-2 hashtags, "
                          "link-friendly, community-building tone",
    },
    "tiktok": {
        "max_length": 2200, "hashtag_limit": 10,
        "best_practices": "Trend-focused, short catchy sentences, 3-5 trending hashtags, "
                          "emoji-heavy, viral hooks, casual fun tone",
    },
}

ANGLE_TEMPLATES = {
    "instagram": "Lifestyle showcase — visually highlight the product in real use scenarios with aspirational vibe",
    "threads": "Authentic conversation — share a genuine take on why this product matters, casual and relatable",
    "pinterest": "Inspiration board — position as a solution to a problem, with aesthetic appeal and save-worthy tips",
    "facebook": "Community story — tell the brand story and invite discussion, focus on value and community",
    "tiktok": "Trend hook — quick attention-grabbing angle, show transformation or surprise element",
}


class PlatformAdapterInput(BaseModel):
    product_name: str = ""
    key_selling_points: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    content_tone: str = "professional"


class PlatformRequirement(BaseModel):
    platform: str = ""
    max_chars: int = 500
    hashtag_suggestion: str = ""
    format_tips: str = ""
    content_angle: str = ""


class PlatformAdapterOutput(BaseModel):
    platform_requirements: list[PlatformRequirement] = Field(default_factory=list)


class PlatformAdapterAgent(BaseAgent[PlatformAdapterInput, PlatformAdapterOutput]):
    name = "platform_adapter"
    description = "规则引擎 — 根据平台规则极速适配，无 LLM 调用"

    def build_prompt(self, input_data: PlatformAdapterInput, context: dict | None = None) -> tuple[str, str]:
        return "", ""

    async def run(self, input_data: PlatformAdapterInput, context: dict | None = None) -> PlatformAdapterOutput:
        requirements = []

        for platform in input_data.platforms:
            rules = PLATFORM_RULES.get(platform, PLATFORM_RULES["instagram"])
            angle = ANGLE_TEMPLATES.get(platform, ANGLE_TEMPLATES["instagram"])

            requirements.append(PlatformRequirement(
                platform=platform,
                max_chars=rules["max_length"],
                hashtag_suggestion=f"{rules['hashtag_limit']} max hashtags",
                format_tips=rules["best_practices"],
                content_angle=f"{angle} — product: {input_data.product_name}, tone: {input_data.content_tone}",
            ))

        return PlatformAdapterOutput(platform_requirements=requirements)
