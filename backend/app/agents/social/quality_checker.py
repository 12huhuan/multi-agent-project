"""
质量检查 Agent — 审核社媒文案质量。

评估文案的合规性、吸引力和可读性，确保发布前内容达标。
"""

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent


class QualityCheckerInput(BaseModel):
    copy: str = Field(..., min_length=1)
    platform: str = "instagram"
    language: str = "en"
    product_name: str = ""


class QualityCheckerOutput(BaseModel):
    overall_score: float = 7.0  # 0-10
    compliance_score: float = 7.0
    engagement_score: float = 7.0
    readability_score: float = 7.0
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    verdict: str = "approved"  # approved | needs_revision | rejected


class QualityCheckerAgent(BaseAgent[QualityCheckerInput, QualityCheckerOutput]):
    name = "quality_checker"
    description = "社媒文案质量审核，评估合规/吸引力/可读性"

    def build_prompt(self, input_data: QualityCheckerInput, context: dict | None = None) -> tuple[str, str]:
        system_prompt = (
            f"You are a social media quality reviewer for {input_data.platform.title()}. "
            "Rate the given post copy on three dimensions (0-10 each):\n"
            "- compliance_score: platform policy compliance, no misleading claims, proper disclosures\n"
            "- engagement_score: hook strength, call-to-action clarity, conversation potential\n"
            "- readability_score: grammar, structure, line breaks, emoji usage, sentence length\n"
            "Also provide:\n"
            "- overall_score: average of the three scores\n"
            "- issues: list specific problems found (empty list if none)\n"
            "- suggestions: actionable improvements\n"
            "- verdict: approved (score>=7) | needs_revision (5-7) | rejected (<5)\n"
            "Output must be valid JSON."
        )

        user_prompt = (
            f"Product: {input_data.product_name}\n"
            f"Platform: {input_data.platform}\n"
            f"Language: {input_data.language}\n"
            f'Copy to review:\n"""{input_data.copy}"""\n\n'
            f'Return: {{"overall_score": 0.0, "compliance_score": 0.0, "engagement_score": 0.0, '
            f'"readability_score": 0.0, "issues": [...], "suggestions": [...], "verdict": "..."}}'
        )

        return system_prompt, user_prompt

    async def run(self, input_data: QualityCheckerInput, context: dict | None = None) -> QualityCheckerOutput:
        import time

        # 规则层：基础检查
        rule_issues = []
        if len(input_data.copy) < 20:
            rule_issues.append("Copy too short (< 20 characters)")
        if len(input_data.copy) > 3000:
            rule_issues.append("Copy too long (> 3000 characters)")
        if "#" not in input_data.copy:
            rule_issues.append("No hashtags found")

        system_prompt, user_prompt = self.build_prompt(input_data, context)
        start = time.time()
        raw = await self._call_llm(system_prompt, user_prompt, max_tokens=512, temperature=0.2)
        duration_ms = int((time.time() - start) * 1000)

        data = self._parse_llm_json(raw)

        try:
            all_issues = rule_issues + data.get("issues", [])
            result = QualityCheckerOutput(
                overall_score=float(data.get("overall_score", 7.0)),
                compliance_score=float(data.get("compliance_score", 7.0)),
                engagement_score=float(data.get("engagement_score", 7.0)),
                readability_score=float(data.get("readability_score", 7.0)),
                issues=all_issues,
                suggestions=data.get("suggestions", []),
                verdict=data.get("verdict", "approved"),
            )
        except Exception:
            result = QualityCheckerOutput(issues=rule_issues, verdict="approved")

        tid = context.get("task_id") if context else None
        if tid:
            await self.log_execution(tid, input_data, result, 0, duration_ms)

        return result
