"""
平台适配 Agent — 根据各社交媒体平台规则适配内容格式。

支持: Instagram, Threads, Pinterest, Facebook, TikTok
"""

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent

PLATFORM_RULES = {
    "instagram": {
        "max_length": 2200,
        "hashtag_limit": 30,
        "best_practices": "Visual-first, 5-10 hashtags, emoji-friendly, call to action in caption, "
                          "use line breaks for readability, @mentions for collabs",
    },
    "threads": {
        "max_length": 500,
        "hashtag_limit": 5,
        "best_practices": "Conversational tone, short paragraphs, 1-2 hashtags max, "
                          "text-focused, can be more casual and authentic",
    },
    "pinterest": {
        "max_length": 500,
        "hashtag_limit": 5,
        "best_practices": "SEO-optimized description, 3-5 keywords, 2-3 hashtags, "
                          "inspirational tone, 'save for later' CTAs, vertical image 2:3 ratio",
    },
    "facebook": {
        "max_length": 2000,
        "hashtag_limit": 5,
        "best_practices": "Engagement-focused, ask questions, 1-2 hashtags, "
                          "link-friendly, community-building tone",
    },
    "tiktok": {
        "max_length": 2200,
        "hashtag_limit": 10,
        "best_practices": "Trend-focused, short catchy sentences, 3-5 trending hashtags, "
                          "emoji-heavy, viral hooks, casual fun tone",
    },
}


class PlatformAdapterInput(BaseModel):
    product_name: str = ""
    key_selling_points: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)  # e.g., ["instagram", "threads", "pinterest"]
    content_tone: str = "professional"


class PlatformRequirement(BaseModel):
    platform: str = ""
    max_chars: int = 500
    hashtag_suggestion: str = "3-5 hashtags"
    format_tips: str = ""
    content_angle: str = ""


class PlatformAdapterOutput(BaseModel):
    platform_requirements: list[PlatformRequirement] = Field(default_factory=list)


class PlatformAdapterAgent(BaseAgent[PlatformAdapterInput, PlatformAdapterOutput]):
    name = "platform_adapter"
    description = "根据社交媒体平台规则适配内容格式和策略"

    def build_prompt(self, input_data: PlatformAdapterInput, context: dict | None = None) -> tuple[str, str]:
        return "", ""  # 规则+LLM 混合

    async def run(self, input_data: PlatformAdapterInput, context: dict | None = None) -> PlatformAdapterOutput:
        requirements = []

        for platform in input_data.platforms:
            rules = PLATFORM_RULES.get(platform, PLATFORM_RULES["instagram"])

            # Rules layer: 构建基础适配
            base_req = PlatformRequirement(
                platform=platform,
                max_chars=rules["max_length"],
                hashtag_suggestion=f"{rules['hashtag_limit']} max hashtags",
                format_tips=rules["best_practices"],
                content_angle=f"Promote {input_data.product_name} with {input_data.content_tone} tone",
            )

            # LLM layer: 为每个平台生成更精准的内容角度
            try:
                system_prompt = (
                    f"You are a {platform.title()} content strategist. "
                    "Suggest the best content approach for this product on this platform."
                    "Output must be valid JSON."
                )
                user_prompt = (
                    f"Product: {input_data.product_name}\n"
                    f"Platform: {platform}\n"
                    f"Platform rules: {rules['best_practices']}\n"
                    f"Selling points: {', '.join(input_data.key_selling_points)}\n"
                    f"Tone: {input_data.content_tone}\n\n"
                    f'Return: {{"content_angle": "...", "format_tips": "..."}}'
                )
                raw = await self._call_llm(system_prompt, user_prompt, max_tokens=256, temperature=0.4)
                data = self._parse_llm_json(raw)

                if data.get("content_angle"):
                    base_req.content_angle = data["content_angle"]
                if data.get("format_tips"):
                    base_req.format_tips = data["format_tips"]
            except Exception:
                pass

            requirements.append(base_req)

        return PlatformAdapterOutput(platform_requirements=requirements)
