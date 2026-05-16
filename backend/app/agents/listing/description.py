"""
长描述 Agent — 生成 HTML 格式产品描述，包含品牌故事、产品参数、使用场景。

输入: 全部前置输出 + 品牌故事 + 使用场景
输出: HTML 格式完整产品描述
"""

from pydantic import BaseModel, Field

from backend.app.agents.base import BaseAgent


class DescriptionInput(BaseModel):
    product_name: str
    category: str
    features: list[str] = Field(default_factory=list)
    bullet_points: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    brand_story: str | None = None
    use_scenarios: list[str] = Field(default_factory=list)
    target_platform: str = "amazon_us"
    target_language: str = "en"


class DescriptionOutput(BaseModel):
    html_content: str = ""
    sections: list[str] = Field(default_factory=list)
    keyword_density: dict[str, float] = Field(default_factory=dict)


class DescriptionAgent(BaseAgent[DescriptionInput, DescriptionOutput]):
    name = "description"
    description = "生成SEO友好的HTML格式产品长描述"

    def build_prompt(self, input_data: DescriptionInput, context: dict | None = None) -> tuple[str, str]:
        system_prompt = f"""你是跨境电商{input_data.target_platform}平台的产品描述撰写专家。

要求:
- 输出纯 HTML (不含 <html>/<body> 标签)，使用 <p>/<h3>/<ul>/<li>/<b>/<br>
- 结构: 品牌介绍 → 产品参数 → 核心卖点 → 使用场景 → 质量保证
- SEO 友好：自然融入关键词
- 用{input_data.target_language}语言
- 禁止: JavaScript、外部链接、CSS class、促销限时信息

输出必须是有效的 JSON 格式。"""

        user_prompt = f"""产品名称: {input_data.product_name}
品类: {input_data.category}
核心卖点: {", ".join(input_data.features) if input_data.features else "无"}
Bullet Points: {", ".join(input_data.bullet_points) if input_data.bullet_points else "无"}
关键词: {", ".join(input_data.keywords) if input_data.keywords else "无"}
品牌故事: {input_data.brand_story or "无"}
使用场景: {", ".join(input_data.use_scenarios) if input_data.use_scenarios else "无"}

请生成完整产品描述 HTML。
返回格式:
{{
  "html_content": "<p>...</p><h3>...</h3>...",
  "sections": ["品牌介绍", "产品参数", "核心卖点", "使用场景", "质量保证"],
  "keyword_density": {{"keyword1": 0.5, "keyword2": 0.3}}
}}"""
        return system_prompt, user_prompt

    async def run(self, input_data: DescriptionInput, context: dict | None = None) -> DescriptionOutput:
        import time

        system_prompt, user_prompt = self.build_prompt(input_data, context)
        start = time.time()
        raw = await self._call_llm(system_prompt, user_prompt, max_tokens=3000)
        duration_ms = int((time.time() - start) * 1000)

        data = self._parse_llm_json(raw)

        if data and "html_content" in data:
            try:
                result = DescriptionOutput(**data)
            except Exception:
                result = self._fallback_parse(raw)
        else:
            result = self._fallback_parse(raw)

        if context and "task_id" in context:
            await self.log_execution(context["task_id"], input_data, result, 0, duration_ms)

        return result

    def _fallback_parse(self, raw: str) -> DescriptionOutput:
        """当 JSON 解析失败时，从原始文本中提取 HTML"""
        import re
        # 尝试提取 "html_content" 字段的值
        html = ""
        m = re.search(r'"html_content"\s*:\s*"', raw)
        if m:
            start = m.end()
            # 找到对应的未转义结束引号
            i = start
            while i < len(raw):
                if raw[i] == '"' and (i == 0 or raw[i-1] != '\\'):
                    html = raw[start:i]
                    break
                i += 1

        if not html:
            # 直接检查 raw 是否包含 HTML 标签
            if any(tag in raw for tag in ["<p>", "<h3>", "<ul>", "<li>", "<br"]):
                html = raw

        return DescriptionOutput(html_content=html or raw[:1000], sections=[], keyword_density={})
