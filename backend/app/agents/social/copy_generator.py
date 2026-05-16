"""
文案生成 Agent — 为各社交媒体平台生成帖子文案和话题标签。

基于产品分析和平台适配结果，生成可直接发布的社媒内容。
"""

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent


class CopyGeneratorInput(BaseModel):
    product_name: str = ""
    platform: str = "instagram"
    language: str = "en"
    selling_points: list[str] = Field(default_factory=list)
    content_angle: str = ""
    content_tone: str = "professional"
    target_audience: str = ""


class CopyGeneratorOutput(BaseModel):
    copy: str = ""
    short_copy: str = ""  # 短版 (用于图片 overlay)
    hashtags: list[str] = Field(default_factory=list)
    call_to_action: str = ""
    emoji_suggestions: list[str] = Field(default_factory=list)


class CopyGeneratorAgent(BaseAgent[CopyGeneratorInput, CopyGeneratorOutput]):
    name = "copy_generator"
    description = "生成社交媒体平台文案，包含长短版文案、话题标签和行动号召"

    def build_prompt(self, input_data: CopyGeneratorInput, context: dict | None = None) -> tuple[str, str]:
        lang_names = {"en": "English", "zh": "Simplified Chinese", "ja": "Japanese", "ko": "Korean",
                      "fr": "French", "de": "German", "es": "Spanish"}
        lang_name = lang_names.get(input_data.language, input_data.language.upper())
        lang_directive = (
            f"IMPORTANT: You MUST write ALL output in {lang_name}. "
            f"All copy, hashtags, CTAs, and content must be in {lang_name}. "
            f"Do NOT write in English. "
        ) if input_data.language != "en" else ""

        system_prompt = (
            f"You are a social media copywriter for cross-border e-commerce brands. "
            f"Write engaging, platform-optimized copy for {input_data.platform.title()}. "
            f"Target language: {lang_name}. "
            f"Tone: {input_data.content_tone}. "
            f"{lang_directive}"
            f"Rules:\n"
            f"- copy: main post copy, 2-4 paragraphs with line breaks, IN {lang_name}\n"
            f"- short_copy: 1-2 sentences for image overlay, IN {lang_name}\n"
            f"- hashtags: 5-10 trending hashtags (mix of {lang_name} and English tags)\n"
            f"- call_to_action: clear CTA IN {lang_name}\n"
            f"- emoji_suggestions: 3-5 emojis that fit the vibe\n"
            f"- Write naturally, avoid sounding like an ad\n"
            f"Output must be valid JSON."
        )

        user_prompt = (
            f"Product name: {input_data.product_name}\n"
            f"Selling points: {', '.join(input_data.selling_points) if input_data.selling_points else 'N/A'}\n"
            f"Content angle: {input_data.content_angle or 'General product promotion'}\n"
            f"Target audience: {input_data.target_audience or 'General consumers'}\n\n"
            f'Return: {{"copy": "...", "short_copy": "...", "hashtags": [...], '
            f'"call_to_action": "...", "emoji_suggestions": [...]}}'
        )

        return system_prompt, user_prompt

    async def run(self, input_data: CopyGeneratorInput, context: dict | None = None) -> CopyGeneratorOutput:
        import time

        system_prompt, user_prompt = self.build_prompt(input_data, context)
        start = time.time()
        raw = await self._call_llm(system_prompt, user_prompt, max_tokens=1024, temperature=0.7)
        duration_ms = int((time.time() - start) * 1000)

        data = self._parse_llm_json(raw)

        try:
            result = CopyGeneratorOutput(**data)
        except Exception:
            result = CopyGeneratorOutput(copy=raw)

        tid = context.get("task_id") if context else None
        if tid:
            await self.log_execution(tid, input_data, result, 0, duration_ms)

        return result
