"""
广告效果分析 Agent — 分析广告活动 KPI，识别问题和优化机会。

支持 Amazon Ads / Facebook Ads / Google Ads 数据格式。
"""

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent


class AdCampaign(BaseModel):
    id: str = ""
    name: str = ""
    platform: str = "amazon"
    budget: float = 0.0
    spend: float = 0.0
    sales: float = 0.0
    impressions: int = 0
    clicks: int = 0
    orders: int = 0
    acos: float = 0.0  # Advertising Cost of Sales
    roas: float = 0.0  # Return on Ad Spend
    ctr: float = 0.0  # Click Through Rate
    cpc: float = 0.0  # Cost Per Click
    conversion_rate: float = 0.0
    status: str = "active"


class PerformanceAnalyzerInput(BaseModel):
    campaigns: list[AdCampaign] = Field(default_factory=list)
    target_acos: float = 30.0
    target_roas: float = 3.0
    date_range: str = "last_7_days"


class CampaignInsight(BaseModel):
    campaign_id: str = ""
    campaign_name: str = ""
    status: str = "healthy"  # healthy | warning | critical
    issues: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    suggested_bid_adjustment: str = "keep"  # increase | keep | decrease


class PerformanceAnalyzerOutput(BaseModel):
    overall_health: str = "healthy"
    total_spend: float = 0.0
    total_sales: float = 0.0
    overall_acos: float = 0.0
    overall_roas: float = 0.0
    campaign_insights: list[CampaignInsight] = Field(default_factory=list)
    summary: str = ""


class PerformanceAnalyzerAgent(BaseAgent[PerformanceAnalyzerInput, PerformanceAnalyzerOutput]):
    name = "performance_analyzer"
    description = "分析广告效果 KPI，识别问题 Campaign 和优化机会"

    def build_prompt(self, input_data: PerformanceAnalyzerInput, context: dict | None = None) -> tuple[str, str]:
        campaigns_text = "\n".join(
            f"- {c.name}: spend=${c.spend}, sales=${c.sales}, ACOS={c.acos}%, ROAS={c.roas}, "
            f"CTR={c.ctr}%, CPC=${c.cpc}, conv={c.conversion_rate}%, orders={c.orders}"
            for c in input_data.campaigns
        )

        system_prompt = (
            f"You are an Amazon Ads optimization expert. "
            f"Target ACOS: <{input_data.target_acos}%, Target ROAS: >{input_data.target_roas}x\n"
            "For each campaign, identify:\n"
            "- health status: healthy (meets targets) | warning (slightly off) | critical (way off)\n"
            "- issues: specific problems (high ACOS, low CTR, poor conversion, overspending)\n"
            "- opportunities: actionable improvements\n"
            "- suggested_bid_adjustment: increase | keep | decrease\n"
            "Output must be valid JSON."
        )

        user_prompt = (
            f"Date range: {input_data.date_range}\n"
            f"Campaigns:\n{campaigns_text}\n\n"
            f'Return: {{"overall_health": "...", "campaign_insights": ['
            f'{{"campaign_id":"...","campaign_name":"...","status":"...",'
            f'"issues":[...],"opportunities":[...],"suggested_bid_adjustment":"..."}}],'
            f'"summary": "..."}}'
        )

        return system_prompt, user_prompt

    async def run(self, input_data: PerformanceAnalyzerInput, context: dict | None = None) -> PerformanceAnalyzerOutput:
        import time

        total_spend = sum(c.spend for c in input_data.campaigns)
        total_sales = sum(c.sales for c in input_data.campaigns)
        overall_acos = (total_spend / total_sales * 100) if total_sales > 0 else 0
        overall_roas = (total_sales / total_spend) if total_spend > 0 else 0

        system_prompt, user_prompt = self.build_prompt(input_data, context)
        start = time.time()
        raw = await self._call_llm(system_prompt, user_prompt, max_tokens=2048, temperature=0.2)
        duration_ms = int((time.time() - start) * 1000)

        data = self._parse_llm_json(raw)
        try:
            insights = [CampaignInsight(**i) for i in data.get("campaign_insights", [])]
            result = PerformanceAnalyzerOutput(
                overall_health=data.get("overall_health", "healthy"),
                total_spend=total_spend, total_sales=total_sales,
                overall_acos=round(overall_acos, 1), overall_roas=round(overall_roas, 2),
                campaign_insights=insights,
                summary=data.get("summary", raw[:200]),
            )
        except Exception:
            result = PerformanceAnalyzerOutput(
                total_spend=total_spend, total_sales=total_sales,
                overall_acos=round(overall_acos, 1), overall_roas=round(overall_roas, 2),
                summary=raw[:200],
            )

        tid = context.get("task_id") if context else None
        if tid:
            await self.log_execution(tid, input_data, result, 0, duration_ms)
        return result
