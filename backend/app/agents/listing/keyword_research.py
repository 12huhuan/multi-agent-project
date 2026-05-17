"""
关键词研究 Agent — 基于 LLM 内置知识分析搜索意图，输出结构化关键词列表。

输入: 产品名称、品类、核心卖点
输出: 关键词列表（词 / 搜索量级别 / 竞争度 / 相关性）
"""

from pydantic import BaseModel, Field

from backend.app.agents.base import BaseAgent


class KeywordResearchInput(BaseModel):
    product_name: str
    category: str
    features: list[str] = Field(default_factory=list)
    target_platform: str = "amazon_us"
    target_language: str = "en"
    seed_keywords: list[str] = Field(default_factory=list)  # Amazon Autocomplete 真实热词


class KeywordItem(BaseModel):
    keyword: str
    search_volume_level: str = "medium"  # high | medium | low
    competition_level: str = "medium"    # high | medium | low
    relevance_score: float = 0.0         # 0-100


class KeywordResearchOutput(BaseModel):
    keywords: list[KeywordItem] = Field(default_factory=list)
    top_keywords: list[str] = Field(default_factory=list)
    analysis_notes: str = ""


class KeywordResearchAgent(BaseAgent[KeywordResearchInput, KeywordResearchOutput]):
    name = "keyword_research"
    description = "基于产品信息和品类，分析搜索意图，输出结构化关键词列表"

    def build_prompt(self, input_data: KeywordResearchInput, context: dict | None = None) -> tuple[str, str]:
        system_prompt = f"""你是一个亚马逊{input_data.target_platform}平台的SEO关键词研究专家。
你需要基于产品信息分析用户搜索意图，输出高质量的关键词列表。

要求:
1. 关键词用{input_data.target_language}语言
2. 覆盖不同类型: 品类大词、长尾词、场景词、竞品词、属性词
3. 按搜索意图分类: 信息型、导航型、交易型
4. 评估搜索量级别(high/medium/low)和竞争度(high/medium/low)
5. 给每个关键词打相关性分数(0-100)

输出必须是有效的 JSON 格式。"""

        seed_text = ""
        if input_data.seed_keywords:
            seed_text = f"""\n=== 以下是从 Amazon 搜索自动补全获取的真实热门搜索词（按搜索量排序）===
{", ".join(input_data.seed_keywords[:15])}
请基于这些真实关键词进行分析，不要凭空编造。补充长尾词和变体，但 top_keywords 优先从上面的词中选取。
"""

        user_prompt = f"""产品名称: {input_data.product_name}
品类: {input_data.category}
核心卖点: {", ".join(input_data.features) if input_data.features else "无"}
目标平台: {input_data.target_platform}
目标语言: {input_data.target_language}
{seed_text}
请分析并输出至少15个关键词（包含种子词+补充长尾词），按相关性排序。
返回格式:
{{
  "keywords": [
    {{"keyword": "...", "search_volume_level": "high|medium|low", "competition_level": "high|medium|low", "relevance_score": 0-100}}
  ],
  "top_keywords": ["top1", "top2", "top3", "top4", "top5"],
  "analysis_notes": "简要分析说明"
}}"""
        return system_prompt, user_prompt

    async def run(self, input_data: KeywordResearchInput, context: dict | None = None) -> KeywordResearchOutput:
        import json
        import time

        system_prompt, user_prompt = self.build_prompt(input_data, context)
        start = time.time()
        raw = await self._call_llm(system_prompt, user_prompt)
        duration_ms = int((time.time() - start) * 1000)

        try:
            data = self._parse_json(raw)
            result = KeywordResearchOutput(**data)
        except Exception:
            result = KeywordResearchOutput(
                keywords=[],
                top_keywords=[],
                analysis_notes=raw,
            )

        if context and "task_id" in context:
            await self.log_execution(context["task_id"], input_data, result, 0, duration_ms)

        return result

    @staticmethod
    def _parse_json(text: str) -> dict:
        import json
        t = text.strip()
        if t.startswith("```"):
            end = t.find("\n", 3)
            if end > 0:
                t = t[end + 1:]
            if t.endswith("```"):
                t = t[:-3]
        start = t.find("{")
        end = t.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(t[start:end])
        return {}
