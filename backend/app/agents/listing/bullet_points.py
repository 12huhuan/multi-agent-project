"""
五点描述 Agent — 突出功能+利益，遵循平台规则。

输入: 产品卖点 + 关键词 + 目标用户画像
输出: 5 条 Bullet Points (每条 ≤500 字符)
"""

from pydantic import BaseModel, Field

from backend.app.agents.base import BaseAgent


class BulletPointsInput(BaseModel):
    product_name: str
    features: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    target_audience: str = "general"
    target_platform: str = "amazon_us"
    target_language: str = "en"


class BulletPoint(BaseModel):
    text: str
    feature_highlighted: str = ""
    benefit_highlighted: str = ""


class BulletPointsOutput(BaseModel):
    bullet_points: list[BulletPoint] = Field(default_factory=list)


class BulletPointsAgent(BaseAgent[BulletPointsInput, BulletPointsOutput]):
    name = "bullet_points"
    description = "生成5条高转化Bullet Points，每条突出功能+利益"

    def build_prompt(self, input_data: BulletPointsInput, context: dict | None = None) -> tuple[str, str]:
        system_prompt = f"""你是跨境电商{input_data.target_platform}平台的Listing文案专家。

Bullet Points 写作规则:
- 每条 ≤500 字符
- 首字母大写
- 突出功能(function) + 利益(benefit)，不是纯形容词堆砌
- 融入相关关键词自然出现
- 前2条最重要（出现在折叠前）
- 用{input_data.target_language}语言
- 禁止: HTML标签、全大写、促销价格、运费信息

输出必须是有效的 JSON 格式。"""

        user_prompt = f"""产品名称: {input_data.product_name}
核心卖点: {", ".join(input_data.features) if input_data.features else "无"}
关键词: {", ".join(input_data.keywords) if input_data.keywords else "无"}
目标用户: {input_data.target_audience}

请生成5条 Bullet Points。
返回格式:
{{
  "bullet_points": [
    {{"text": "完整bullets文案", "feature_highlighted": "突出的功能", "benefit_highlighted": "对应的利益"}}
  ]
}}"""
        return system_prompt, user_prompt

    async def run(self, input_data: BulletPointsInput, context: dict | None = None) -> BulletPointsOutput:
        import json
        import time

        system_prompt, user_prompt = self.build_prompt(input_data, context)
        start = time.time()
        raw = await self._call_llm(system_prompt, user_prompt)
        duration_ms = int((time.time() - start) * 1000)

        try:
            t = raw.strip()
            if t.startswith("```"):
                end = t.find("\n", 3)
                if end > 0:
                    t = t[end + 1:]
                if t.endswith("```"):
                    t = t[:-3]
            start_pos = t.find("{")
            end_pos = t.rfind("}") + 1
            data = json.loads(t[start_pos:end_pos]) if start_pos >= 0 and end_pos > start_pos else {}
            result = BulletPointsOutput(**data)
        except Exception:
            result = BulletPointsOutput(bullet_points=[])

        if context and "task_id" in context:
            await self.log_execution(context["task_id"], input_data, result, 0, duration_ms)

        return result
