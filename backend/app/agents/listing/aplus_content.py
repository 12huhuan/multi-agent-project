"""
A+ 内容 Agent — 建议图片类型 + 对应文案布局。

输入: 品牌素材 + 产品图片描述
输出: A+ 图文模块布局建议(JSON)
"""

from pydantic import BaseModel, Field

from backend.app.agents.base import BaseAgent


class APlusContentInput(BaseModel):
    product_name: str
    category: str
    features: list[str] = Field(default_factory=list)
    brand_story: str | None = None
    image_descriptions: list[str] = Field(default_factory=list)
    target_language: str = "en"


class APlusModule(BaseModel):
    module_type: str = ""  # hero_banner | comparison_chart | image_text | spec_table
    title: str = ""
    description: str = ""
    image_suggestion: str = ""
    copy_text: str = ""


class APlusContentOutput(BaseModel):
    modules: list[APlusModule] = Field(default_factory=list)
    total_modules: int = 0
    layout_flow: str = ""


class APlusContentAgent(BaseAgent[APlusContentInput, APlusContentOutput]):
    name = "aplus_content"
    description = "生成A+内容图文模块布局建议"

    def build_prompt(self, input_data: APlusContentInput, context: dict | None = None) -> tuple[str, str]:
        system_prompt = f"""你是亚马逊 A+ Content (EBC) 设计专家。

A+ 模块类型:
- hero_banner: 顶部大图(960x600) + 品牌标语
- comparison_chart: 竞品对比表
- image_text: 左图右文 / 左文右图 模块
- spec_table: 规格参数表

最佳实践:
- 前1-2个模块最重要(首屏可见)
- 用{input_data.target_language}语言
- 每个模块需要有明确的转化目的

输出必须是有效的 JSON 格式。"""

        user_prompt = f"""产品名称: {input_data.product_name}
品类: {input_data.category}
核心卖点: {", ".join(input_data.features) if input_data.features else "无"}
品牌故事: {input_data.brand_story or "无"}
可用图片描述: {", ".join(input_data.image_descriptions) if input_data.image_descriptions else "无"}

请设计5-7个A+内容模块。
返回格式:
{{
  "modules": [
    {{
      "module_type": "hero_banner|comparison_chart|image_text|spec_table",
      "title": "模块标题",
      "description": "模块说明",
      "image_suggestion": "建议图片类型和内容",
      "copy_text": "对应的文案"
    }}
  ],
  "total_modules": 数字,
  "layout_flow": "整体布局流程说明"
}}"""
        return system_prompt, user_prompt

    async def run(self, input_data: APlusContentInput, context: dict | None = None) -> APlusContentOutput:
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
            result = APlusContentOutput(**data)
        except Exception:
            result = APlusContentOutput(modules=[])

        if context and "task_id" in context:
            await self.log_execution(context["task_id"], input_data, result, 0, duration_ms)

        return result
