"""
风险报告 Agent — 汇总合规检查结果，生成分级风险报告。
"""

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent


class RiskReporterInput(BaseModel):
    policy_issues: list[dict] = Field(default_factory=list)
    claim_issues: list[dict] = Field(default_factory=list)
    listing_content: dict = Field(default_factory=dict)


class RiskReporterOutput(BaseModel):
    overall_verdict: str = "pass"  # pass | warning | violation
    risk_level: str = "low"  # low | medium | high | critical
    total_issues: int = 0
    critical_items: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    summary: str = ""


class RiskReporterAgent(BaseAgent[RiskReporterInput, RiskReporterOutput]):
    name = "risk_reporter"
    description = "汇总生成分级风险报告"

    def build_prompt(self, input_data: RiskReporterInput, context: dict | None = None) -> tuple[str, str]:
        return "", ""  # 规则为主，LLM 只做润色

    async def run(self, input_data: RiskReporterInput, context: dict | None = None) -> RiskReporterOutput:
        # 规则层计算
        total = len(input_data.policy_issues) + len(input_data.claim_issues)
        high_severity = sum(
            1 for i in input_data.policy_issues if i.get("severity") == "high"
        ) + sum(
            1 for i in input_data.claim_issues if i.get("risk_level") == "high"
        )

        if high_severity >= 2:
            verdict, risk = "violation", "critical"
        elif high_severity >= 1:
            verdict, risk = "warning", "high"
        elif total >= 3:
            verdict, risk = "warning", "medium"
        elif total > 0:
            verdict, risk = "pass", "low"
        else:
            verdict, risk = "pass", "low"

        # 提取关键问题
        critical_items = []
        for i in input_data.policy_issues:
            if i.get("severity") == "high":
                critical_items.append(f"[Policy] {i.get('description', '')}")
        for i in input_data.claim_issues:
            if i.get("risk_level") == "high":
                critical_items.append(f"[Claim] {i.get('explanation', '')}")

        action_items = []
        for i in input_data.policy_issues:
            s = i.get("suggestion", "")
            if s:
                action_items.append(s)
        for i in input_data.claim_issues:
            s = i.get("fix_suggestion", "")
            if s:
                action_items.append(s)

        # LLM 润色 summary
        summary = f"Found {total} issues ({high_severity} high severity). Verdict: {verdict.upper()}."
        if critical_items:
            try:
                items_text = "; ".join(critical_items[:5])
                raw = await self._call_llm(
                    "Summarize compliance issues in Chinese for the seller. Keep it under 100 chars.",
                    f"Issues: {items_text}\nVerdict: {verdict}\nRisk: {risk}",
                    max_tokens=200, temperature=0.1,
                )
                summary = raw[:200]
            except Exception:
                pass

        return RiskReporterOutput(
            overall_verdict=verdict,
            risk_level=risk,
            total_issues=total,
            critical_items=critical_items,
            action_items=action_items,
            summary=summary,
        )
