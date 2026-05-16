"""
产品分析 Agent — 挖掘产品社媒营销角度。

分析产品特性、目标受众、内容调性，为社媒内容生成提供策略基础。
"""

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent


class ProductAnalysisInput(BaseModel):
    product_name: str = Field(..., min_length=1)
    category: str = ""
    features: list[str] = Field(default_factory=list)
    brand_story: str = ""
    target_markets: list[str] = Field(default_factory=list)  # e.g., ["US", "EU", "JP"]


class ProductAnalysisOutput(BaseModel):
    marketing_angles: list[str] = Field(default_factory=list)  # 营销角度
    target_audience: str = ""  # 目标受众画像
    content_tones: list[str] = Field(default_factory=list)  # 建议调性
    key_selling_points: list[str] = Field(default_factory=list)  # 核心卖点
    visual_style_suggestions: list[str] = Field(default_factory=list)  # 视觉风格建议
    hashtag_themes: list[str] = Field(default_factory=list)  # 话题标签主题


class ProductAnalysisAgent(BaseAgent[ProductAnalysisInput, ProductAnalysisOutput]):
    name = "product_analysis"
    description = "分析产品社媒营销潜力，输出营销角度、受众和调性策略"

    def build_prompt(self, input_data: ProductAnalysisInput, context: dict | None = None) -> tuple[str, str]:
        system_prompt = (
            "You are a social media marketing strategist for cross-border e-commerce. "
            "Analyze products and generate comprehensive marketing strategies.\n"
            "Rules:\n"
            "- marketing_angles: 3-5 creative angles for social content (e.g., 'unboxing', 'lifestyle', 'before/after')\n"
            "- target_audience: describe the ideal customer persona in one paragraph\n"
            "- content_tones: 2-3 tones that fit the product (e.g., 'playful', 'professional', 'aspirational')\n"
            "- key_selling_points: top 3-5 unique selling points\n"
            "- visual_style_suggestions: visual/imagery style ideas\n"
            "- hashtag_themes: 3-5 hashtag themes/topics (without # prefix)\n"
            "Think from a Western consumer perspective."
            "Output must be valid JSON."
        )

        features_text = ", ".join(input_data.features) if input_data.features else "N/A"
        brand_text = input_data.brand_story if input_data.brand_story else "N/A"
        markets_text = ", ".join(input_data.target_markets) if input_data.target_markets else "US, Global"

        user_prompt = (
            f"Product: {input_data.product_name}\n"
            f"Category: {input_data.category}\n"
            f"Features: {features_text}\n"
            f"Brand story: {brand_text}\n"
            f"Target markets: {markets_text}\n\n"
            f'Return: {{"marketing_angles": [...], "target_audience": "...", "content_tones": [...], '
            f'"key_selling_points": [...], "visual_style_suggestions": [...], "hashtag_themes": [...]}}'
        )

        return system_prompt, user_prompt

    async def run(self, input_data: ProductAnalysisInput, context: dict | None = None) -> ProductAnalysisOutput:
        import time

        system_prompt, user_prompt = self.build_prompt(input_data, context)
        start = time.time()
        raw = await self._call_llm(system_prompt, user_prompt, max_tokens=1024, temperature=0.6)
        duration_ms = int((time.time() - start) * 1000)

        data = self._parse_llm_json(raw)

        try:
            result = ProductAnalysisOutput(**data)
        except Exception:
            result = ProductAnalysisOutput(marketing_angles=[raw[:200]])

        tid = context.get("task_id") if context else None
        if tid:
            await self.log_execution(tid, input_data, result, 0, duration_ms)

        return result
