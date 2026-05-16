"""
标题生成 Agent — 遵循平台规则生成多个候选标题，含评分。

输入: Top5 关键词 + 产品信息 + 目标平台
输出: 3 个标题候选 + 评分(0-100)，每个含合规性检查
"""

from pydantic import BaseModel, Field

from backend.app.agents.base import BaseAgent


class TitleGenerationInput(BaseModel):
    product_name: str
    category: str
    top_keywords: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    target_platform: str = "amazon_us"
    target_language: str = "en"


class TitleCandidate(BaseModel):
    title: str
    score: int = 0
    char_count: int = 0
    keyword_coverage: list[str] = Field(default_factory=list)
    compliance_issues: list[str] = Field(default_factory=list)


class TitleGenerationOutput(BaseModel):
    candidates: list[TitleCandidate] = Field(default_factory=list)
    best_title: str = ""


class TitleGenerationAgent(BaseAgent[TitleGenerationInput, TitleGenerationOutput]):
    name = "title_generation"
    description = "基于关键词和产品信息生成多个标题候选，遵循平台规则"

    def build_prompt(self, input_data: TitleGenerationInput, context: dict | None = None) -> tuple[str, str]:
        platform_rules = "字符数 ≤200，禁止全大写，禁止促销信息(如'Best Seller'/'100%')，禁止主观夸大宣称" \
            if "amazon" in input_data.target_platform else "字符数 ≤80"

        system_prompt = f"""你是跨境电商{input_data.target_platform}平台的Listing标题撰写专家。

平台规则:
- {platform_rules}
- 融入主关键词，但避免关键词堆砌
- 格式: [品牌] + [核心词] + [属性词] + [场景/人群]
- 用{input_data.target_language}语言
- 标题应促进点击率和转化率

输出必须是有效的 JSON 格式。"""

        user_prompt = f"""产品名称: {input_data.product_name}
品类: {input_data.category}
核心关键词: {", ".join(input_data.top_keywords)}
产品特性: {", ".join(input_data.features) if input_data.features else "无"}

请生成3个候选标题，每个都要评分(0-100分，基于关键词覆盖/可读性/合规性/转化预期)。
返回格式:
{{
  "candidates": [
    {{
      "title": "...",
      "score": 0-100,
      "char_count": 数字,
      "keyword_coverage": ["覆盖的关键词"],
      "compliance_issues": []
    }}
  ],
  "best_title": "推荐的最佳标题"
}}"""
        return system_prompt, user_prompt

    async def run(self, input_data: TitleGenerationInput, context: dict | None = None) -> TitleGenerationOutput:
        import time

        system_prompt, user_prompt = self.build_prompt(input_data, context)
        start = time.time()
        raw = await self._call_llm(system_prompt, user_prompt, max_tokens=2000)
        duration_ms = int((time.time() - start) * 1000)

        data = self._parse_llm_json(raw)

        if data:
            try:
                result = TitleGenerationOutput(**data)
            except Exception:
                result = self._fallback_parse(raw)
        else:
            result = self._fallback_parse(raw)

        if context and "task_id" in context:
            await self.log_execution(context["task_id"], input_data, result, 0, duration_ms)

        return result

    def _fallback_parse(self, raw: str) -> TitleGenerationOutput:
        """当 JSON 解析失败时，从原始文本中提取标题"""
        import re
        titles = []
        # 尝试匹配被引号包裹的标题文本(150-200字符的句子)
        for match in re.finditer(r'"title"\s*:\s*"([^"]{50,220})"', raw):
            title_text = match.group(1)
            if "http" not in title_text and len(title_text) > 30:
                titles.append(title_text)

        # 如果正则也失败，取 raw 中看起来像标题的长文本行
        if not titles:
            for line in raw.split("\n"):
                line = line.strip().strip('"').strip("'")
                if 50 < len(line) < 250 and not line.startswith("{") and not line.startswith("["):
                    titles.append(line)

        candidates = []
        for t in titles[:3]:
            candidates.append({"title": t, "score": 70, "char_count": len(t),
                               "keyword_coverage": [], "compliance_issues": []})

        return TitleGenerationOutput(
            candidates=candidates,
            best_title=titles[0] if titles else raw[:200],
        )
