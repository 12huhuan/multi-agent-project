"""
机会评分 Agent — 综合评分各潜力产品的市场机会。
"""

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent


class OpportunityScorerInput(BaseModel):
    products: list[dict] = Field(default_factory=list)
    trend_data: list[dict] = Field(default_factory=list)


class ScoredProduct(BaseModel):
    product_name: str = ""
    competition_score: float = 5.0  # 0=extreme competition, 10=blue ocean
    margin_score: float = 5.0       # 0=no profit, 10=high margin
    trend_score: float = 5.0         # 0=declining, 10=surging
    risk_score: float = 5.0          # 0=high risk, 10=low risk
    overall_score: float = 5.0
    verdict: str = "consider"        # strong_buy | buy | consider | skip
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)


class OpportunityScorerOutput(BaseModel):
    scored_products: list[ScoredProduct] = Field(default_factory=list)
    top_pick: str = ""
    summary: str = ""


class OpportunityScorerAgent(BaseAgent[OpportunityScorerInput, OpportunityScorerOutput]):
    name = "opportunity_scorer"
    description = "综合评分产品市场机会，输出推荐排名"

    def build_prompt(self, input_data: OpportunityScorerInput, context: dict | None = None) -> tuple[str, str]:
        products_text = "\n".join(
            f"- {p.get('product_name', '')} (cost: {p.get('estimated_cost', '?')}, "
            f"price: {p.get('estimated_price', '?')}, margin: {p.get('estimated_margin', '?')})"
            for p in input_data.products
        )

        system_prompt = (
            "You are a product opportunity evaluator for Amazon sellers. "
            "Score each product on 4 dimensions (0-10):\n"
            "- competition_score: 10=no competition, 0=oversaturated\n"
            "- margin_score: 10=high profit margin, 0=no profit\n"
            "- trend_score: 10=strong upward trend, 0=declining\n"
            "- risk_score: 10=very low risk, 0=extreme risk\n"
            "- overall_score: weighted average\n"
            "- verdict: strong_buy (>8) | buy (6.5-8) | consider (5-6.5) | skip (<5)\n"
            "Output must be valid JSON."
        )

        user_prompt = (
            f"Products to evaluate:\n{products_text}\n\n"
            f'Trend data: {input_data.trend_data}\n\n'
            f'Return: {{"scored_products": [{{"product_name":"...","competition_score":0.0,...}}], '
            f'"top_pick": "...", "summary": "..."}}'
        )

        return system_prompt, user_prompt

    async def run(self, input_data: OpportunityScorerInput, context: dict | None = None) -> OpportunityScorerOutput:
        import time
        system_prompt, user_prompt = self.build_prompt(input_data, context)
        start = time.time()
        raw = await self._call_llm(system_prompt, user_prompt, max_tokens=2048, temperature=0.2)
        duration_ms = int((time.time() - start) * 1000)

        data = self._parse_llm_json(raw)
        try:
            scored = [ScoredProduct(**s) for s in data.get("scored_products", [])]
            result = OpportunityScorerOutput(
                scored_products=scored,
                top_pick=data.get("top_pick", ""),
                summary=data.get("summary", raw[:200]),
            )
        except Exception:
            result = OpportunityScorerOutput(summary=raw[:200])

        tid = context.get("task_id") if context else None
        if tid:
            await self.log_execution(tid, input_data, result, 0, duration_ms)
        return result
