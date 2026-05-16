"""
SEO 评分 Agent — 从关键词密度、可读性、完整性、转化预期四个维度打分。

输入: 最终 Listing 全部内容
输出: 评分报告(含改进建议)
"""

from pydantic import BaseModel, Field

from backend.app.agents.base import BaseAgent


class SEOScoringInput(BaseModel):
    product_name: str
    title: str = ""
    bullet_points: list[str] = Field(default_factory=list)
    description_html: str = ""
    keywords: list[str] = Field(default_factory=list)
    target_platform: str = "amazon_us"


class DimensionScore(BaseModel):
    score: float = 0.0  # 0-100
    findings: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class SEOScoringOutput(BaseModel):
    keyword_density: DimensionScore = Field(default_factory=DimensionScore)
    readability: DimensionScore = Field(default_factory=DimensionScore)
    completeness: DimensionScore = Field(default_factory=DimensionScore)
    conversion_potential: DimensionScore = Field(default_factory=DimensionScore)
    overall_score: float = 0.0
    improvement_priority: list[str] = Field(default_factory=list)


class SEOScoringAgent(BaseAgent[SEOScoringInput, SEOScoringOutput]):
    name = "seo_scoring"
    description = "从四个维度对Listing进行评分，给出改进建议"

    def build_prompt(self, input_data: SEOScoringInput, context: dict | None = None) -> tuple[str, str]:
        system_prompt = f"""你是{input_data.target_platform}平台的Listing质量审核专家。

评分四维度(每项0-100):
1. 关键词密度 — 核心关键词在标题/BP/描述中的出现频率是否合理(不堆砌)
2. 可读性 — 语言流畅度、信息层次、扫描友好度(标题≤200字符/BP≤500字符等)
3. 完整性 — 是否涵盖了所有必要的信息模块(标题/五点/描述/A+)
4. 转化预期 — 从买家视角评估是否能促成购买决策

输出必须是有效的 JSON 格式。"""

        user_prompt = f"""产品名称: {input_data.product_name}
标题: {input_data.title}
五点描述: {chr(10).join(f"- {bp}" for bp in input_data.bullet_points) if input_data.bullet_points else "无"}
长描述(HTML): {input_data.description_html[:500] if input_data.description_html else "无"}
目标关键词: {", ".join(input_data.keywords) if input_data.keywords else "无"}

请评分并给出改进建议。
返回格式:
{{
  "keyword_density": {{"score": 0-100, "findings": [], "suggestions": []}},
  "readability": {{"score": 0-100, "findings": [], "suggestions": []}},
  "completeness": {{"score": 0-100, "findings": [], "suggestions": []}},
  "conversion_potential": {{"score": 0-100, "findings": [], "suggestions": []}},
  "overall_score": 0-100,
  "improvement_priority": ["最优先改进项1", "2", "3"]
}}"""
        return system_prompt, user_prompt

    async def run(self, input_data: SEOScoringInput, context: dict | None = None) -> SEOScoringOutput:
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
            result = SEOScoringOutput(**data)
        except Exception:
            result = SEOScoringOutput(overall_score=0)

        if context and "task_id" in context:
            await self.log_execution(context["task_id"], input_data, result, 0, duration_ms)

        return result
