"""
趋势分析 Agent — 分析品类市场趋势。

根据品类/关键词分析热度、竞争度和增长潜力。
"""

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent


class TrendAnalyzerInput(BaseModel):
    category: str = Field(..., min_length=1)
    keywords: list[str] = Field(default_factory=list)
    target_market: str = "US"
    platform: str = "amazon_us"


class TrendItem(BaseModel):
    keyword: str = ""
    search_trend: str = "stable"  # rising | stable | declining
    competition_level: str = "medium"  # low | medium | high
    avg_price_range: str = "$20-$50"
    growth_potential: str = "medium"  # low | medium | high
    seasonality: str = "year-round"


class TrendAnalyzerOutput(BaseModel):
    category_overview: str = ""
    trends: list[TrendItem] = Field(default_factory=list)
    market_size_estimate: str = ""
    top_competitors: list[str] = Field(default_factory=list)
    recommended_niches: list[str] = Field(default_factory=list)


class TrendAnalyzerAgent(BaseAgent[TrendAnalyzerInput, TrendAnalyzerOutput]):
    name = "trend_analyzer"
    description = "分析 Amazon 品类市场趋势，识别热门关键词和蓝海机会"

    def build_prompt(self, input_data: TrendAnalyzerInput, context: dict | None = None) -> tuple[str, str]:
        system_prompt = (
            f"You are an Amazon market research expert for cross-border e-commerce sellers. "
            f"Analyze product categories and identify market trends for {input_data.target_market} market.\n"
            "Rules:\n"
            "- category_overview: 1-paragraph summary of the current market state\n"
            "- trends: 5-8 keyword trends with search_volume, competition, price range, growth, seasonality\n"
            "- market_size_estimate: rough estimate (e.g. '$500M/year, growing 15% YoY')\n"
            "- top_competitors: 3-5 leading brands/products\n"
            "- recommended_niches: 3-5 underserved sub-niches with opportunity\n"
            "Output must be valid JSON."
        )

        kw_text = ", ".join(input_data.keywords) if input_data.keywords else "auto-discover"
        user_prompt = (
            f"Category: {input_data.category}\n"
            f"Keywords to analyze: {kw_text}\n"
            f"Platform: {input_data.platform}\n"
            f"Target market: {input_data.target_market}\n\n"
            f'Return: {{"category_overview": "...", "trends": [{{"keyword":"...","search_trend":"...",...}}], '
            f'"market_size_estimate": "...", "top_competitors": [...], "recommended_niches": [...]}}'
        )

        return system_prompt, user_prompt

    async def run(self, input_data: TrendAnalyzerInput, context: dict | None = None) -> TrendAnalyzerOutput:
        import time
        system_prompt, user_prompt = self.build_prompt(input_data, context)
        start = time.time()
        raw = await self._call_llm(system_prompt, user_prompt, max_tokens=2048, temperature=0.3)
        duration_ms = int((time.time() - start) * 1000)

        data = self._parse_llm_json(raw)
        try:
            trends = [TrendItem(**t) for t in data.get("trends", [])]
            result = TrendAnalyzerOutput(
                category_overview=data.get("category_overview", raw[:200]),
                trends=trends,
                market_size_estimate=data.get("market_size_estimate", ""),
                top_competitors=data.get("top_competitors", []),
                recommended_niches=data.get("recommended_niches", []),
            )
        except Exception:
            result = TrendAnalyzerOutput(category_overview=raw[:200])

        tid = context.get("task_id") if context else None
        if tid:
            await self.log_execution(tid, input_data, result, 0, duration_ms)
        return result
