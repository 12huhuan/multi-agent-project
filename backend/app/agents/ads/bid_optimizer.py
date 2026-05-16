"""
竞价优化 Agent — 自动调整关键词竞价，降低 ACOS 增长 ROAS。
"""

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent


class KeywordMetric(BaseModel):
    keyword: str = ""
    campaign_id: str = ""
    match_type: str = "broad"  # broad | phrase | exact
    current_bid: float = 1.0
    spend: float = 0.0
    sales: float = 0.0
    acos: float = 0.0
    clicks: int = 0
    orders: int = 0
    conversion_rate: float = 0.0


class BidOptimizerInput(BaseModel):
    keywords: list[KeywordMetric] = Field(default_factory=list)
    target_acos: float = 30.0
    max_bid: float = 5.0
    min_bid: float = 0.1


class BidSuggestion(BaseModel):
    keyword: str = ""
    current_bid: float = 0.0
    suggested_bid: float = 0.0
    action: str = "keep"  # increase | decrease | keep | pause
    reason: str = ""
    estimated_savings: float = 0.0


class BidOptimizerOutput(BaseModel):
    suggestions: list[BidSuggestion] = Field(default_factory=list)
    total_estimated_savings: float = 0.0
    keywords_to_pause: list[str] = Field(default_factory=list)
    summary: str = ""


class BidOptimizerAgent(BaseAgent[BidOptimizerInput, BidOptimizerOutput]):
    name = "bid_optimizer"
    description = "自动调整关键词竞价，优化 ACOS 和 ROAS"

    def build_prompt(self, input_data: BidOptimizerInput, context: dict | None = None) -> tuple[str, str]:
        kw_text = "\n".join(
            f"- {k.keyword}: bid=${k.current_bid}, spend=${k.spend}, sales=${k.sales}, "
            f"ACOS={k.acos}%, conv={k.conversion_rate}%, orders={k.orders}"
            for k in input_data.keywords
        )

        system_prompt = (
            f"You are a PPC bid manager. Target ACOS: <{input_data.target_acos}%. "
            f"Bid range: ${input_data.min_bid}-${input_data.max_bid}.\n"
            "Rules:\n"
            "- ACOS > 2x target + low orders: pause keyword\n"
            "- ACOS > target + some orders: decrease bid by 15-30%\n"
            "- ACOS < target/2 + good conversion: increase bid by 10-20%\n"
            "- ACOS near target: keep bid\n"
            "Output must be valid JSON."
        )

        user_prompt = (
            f"Keywords to optimize:\n{kw_text}\n\n"
            f'Return: {{"suggestions": [{{"keyword":"...","current_bid":0.0,"suggested_bid":0.0,'
            f'"action":"...","reason":"...","estimated_savings":0.0}}],'
            f'"keywords_to_pause": [...], "summary": "..."}}'
        )

        return system_prompt, user_prompt

    async def run(self, input_data: BidOptimizerInput, context: dict | None = None) -> BidOptimizerOutput:
        import time

        # 规则层：快速判断
        rule_suggestions = []
        keywords_to_pause = []
        total_savings = 0.0

        for kw in input_data.keywords:
            if kw.spend > 20 and kw.orders == 0:
                keywords_to_pause.append(kw.keyword)
                total_savings += kw.spend
                rule_suggestions.append(BidSuggestion(
                    keyword=kw.keyword, current_bid=kw.current_bid,
                    suggested_bid=0, action="pause",
                    reason=f"Spent ${kw.spend:.0f} with 0 orders", estimated_savings=kw.spend,
                ))
            elif kw.acos > input_data.target_acos * 1.5 and kw.conversion_rate < 2:
                new_bid = max(round(kw.current_bid * 0.7, 2), input_data.min_bid)
                savings = kw.spend * 0.3 if kw.spend > 0 else 0
                rule_suggestions.append(BidSuggestion(
                    keyword=kw.keyword, current_bid=kw.current_bid,
                    suggested_bid=new_bid, action="decrease",
                    reason=f"High ACOS ({kw.acos}%) with low conversion", estimated_savings=savings,
                ))
                total_savings += savings

        # LLM 层：精细调整
        system_prompt, user_prompt = self.build_prompt(input_data, context)
        start = time.time()
        raw = await self._call_llm(system_prompt, user_prompt, max_tokens=2048, temperature=0.2)
        duration_ms = int((time.time() - start) * 1000)

        data = self._parse_llm_json(raw)
        llm_suggestions = [BidSuggestion(**s) for s in data.get("suggestions", [])]
        all_keywords_to_pause = keywords_to_pause + data.get("keywords_to_pause", [])

        result = BidOptimizerOutput(
            suggestions=rule_suggestions + llm_suggestions,
            total_estimated_savings=round(total_savings, 2),
            keywords_to_pause=list(set(all_keywords_to_pause)),
            summary=data.get("summary", f"Optimized {len(rule_suggestions + llm_suggestions)} keywords"),
        )

        tid = context.get("task_id") if context else None
        if tid:
            await self.log_execution(tid, input_data, result, 0, duration_ms)
        return result
