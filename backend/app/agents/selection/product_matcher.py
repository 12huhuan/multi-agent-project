"""
产品匹配 Agent — 根据卖家资源和市场机会匹配潜力产品。
"""

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent


class ProductMatcherInput(BaseModel):
    category: str = ""
    recommended_niches: list[str] = Field(default_factory=list)
    seller_budget: str = "$5000-$15000"
    seller_strengths: list[str] = Field(default_factory=list)
    target_market: str = "US"


class MatchedProduct(BaseModel):
    product_name: str = ""
    niche: str = ""
    estimated_cost: str = ""
    estimated_price: str = ""
    estimated_margin: str = ""
    differentiation_angle: str = ""
    difficulty_level: str = "medium"


class ProductMatcherOutput(BaseModel):
    matched_products: list[MatchedProduct] = Field(default_factory=list)
    overall_recommendation: str = ""


class ProductMatcherAgent(BaseAgent[ProductMatcherInput, ProductMatcherOutput]):
    name = "product_matcher"
    description = "根据卖家资源和市场机会匹配具体产品方案"

    def build_prompt(self, input_data: ProductMatcherInput, context: dict | None = None) -> tuple[str, str]:
        system_prompt = (
            f"You are a product sourcing specialist for cross-border e-commerce. "
            f"Match product opportunities to the seller's capabilities for {input_data.target_market} market.\n"
            "For each product:\n"
            "- product_name: specific, action-oriented\n"
            "- estimated_cost: factory/wholesale per unit\n"
            "- estimated_price: sell price on Amazon\n"
            "- estimated_margin: percentage after fees\n"
            "- differentiation_angle: how to stand out\n"
            "Output must be valid JSON."
        )

        strengths = ", ".join(input_data.seller_strengths) if input_data.seller_strengths else "general e-commerce"
        niches = ", ".join(input_data.recommended_niches) if input_data.recommended_niches else input_data.category

        user_prompt = (
            f"Category: {input_data.category}\n"
            f"Niches to target: {niches}\n"
            f"Budget: {input_data.seller_budget}\n"
            f"Strengths: {strengths}\n\n"
            f'Return: {{"matched_products": [{{"product_name":"...","niche":"...",...}}], '
            f'"overall_recommendation": "..."}}'
        )

        return system_prompt, user_prompt

    async def run(self, input_data: ProductMatcherInput, context: dict | None = None) -> ProductMatcherOutput:
        import time
        system_prompt, user_prompt = self.build_prompt(input_data, context)
        start = time.time()
        raw = await self._call_llm(system_prompt, user_prompt, max_tokens=2048, temperature=0.5)
        duration_ms = int((time.time() - start) * 1000)

        data = self._parse_llm_json(raw)
        try:
            products = [MatchedProduct(**p) for p in data.get("matched_products", [])]
            result = ProductMatcherOutput(
                matched_products=products,
                overall_recommendation=data.get("overall_recommendation", ""),
            )
        except Exception:
            result = ProductMatcherOutput(overall_recommendation=raw[:200])

        tid = context.get("task_id") if context else None
        if tid:
            await self.log_execution(tid, input_data, result, 0, duration_ms)
        return result
