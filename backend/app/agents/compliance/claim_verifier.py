"""
声明验证 Agent — 验证产品功能声明是否有夸大或虚假宣传。
"""

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent


class ClaimVerifierInput(BaseModel):
    title: str = ""
    bullet_points: list[str] = Field(default_factory=list)
    description: str = ""
    product_features: list[str] = Field(default_factory=list)
    category: str = ""


class ClaimIssue(BaseModel):
    claim_text: str = ""
    issue: str = ""  # unsubstantiated | exaggerated | misleading | false_comparison
    risk_level: str = "medium"
    explanation: str = ""
    fix_suggestion: str = ""


class ClaimVerifierOutput(BaseModel):
    claims_found: list[ClaimIssue] = Field(default_factory=list)
    risk_score: float = 0.0  # 0=safe, 10=extremely risky
    overall_verdict: str = "pass"  # pass | review | high_risk


class ClaimVerifierAgent(BaseAgent[ClaimVerifierInput, ClaimVerifierOutput]):
    name = "claim_verifier"
    description = "验证 Listing 中的产品声明是否有夸大或虚假"

    def build_prompt(self, input_data: ClaimVerifierInput, context: dict | None = None) -> tuple[str, str]:
        bullets_text = "\n".join(f"- {b}" for b in input_data.bullet_points)
        features_text = ", ".join(input_data.product_features) if input_data.product_features else "N/A"

        system_prompt = (
            "You are a consumer protection and advertising compliance reviewer. "
            "Identify unsubstantiated or misleading claims in product listings.\n"
            "Types of issues:\n"
            "- unsubstantiated: claim without evidence (e.g., 'best sounding headphones')\n"
            "- exaggerated: overstated benefits (e.g., 'perfect audio quality')\n"
            "- misleading: technically true but deceptive (e.g., '50hr battery' when only at min volume)\n"
            "- false_comparison: unfair competitor comparisons\n"
            "Output must be valid JSON."
        )

        user_prompt = (
            f"Category: {input_data.category}\n"
            f"Actual product features: {features_text}\n"
            f"Title: {input_data.title}\n"
            f"Bullet Points:\n{bullets_text}\n"
            f"Description (first 500): {input_data.description[:500]}\n\n"
            f'Return: {{"claims_found": [{{"claim_text":"...","issue":"...","risk_level":"...",'
            f'"explanation":"...","fix_suggestion":"..."}}], "risk_score": 0.0, "overall_verdict": "pass"}}'
        )

        return system_prompt, user_prompt

    async def run(self, input_data: ClaimVerifierInput, context: dict | None = None) -> ClaimVerifierOutput:
        import time
        system_prompt, user_prompt = self.build_prompt(input_data, context)
        start = time.time()
        raw = await self._call_llm(system_prompt, user_prompt, max_tokens=1024, temperature=0.1)
        duration_ms = int((time.time() - start) * 1000)

        data = self._parse_llm_json(raw)
        try:
            claims = [ClaimIssue(**c) for c in data.get("claims_found", [])]
            result = ClaimVerifierOutput(
                claims_found=claims,
                risk_score=float(data.get("risk_score", 0)),
                overall_verdict=data.get("overall_verdict", "pass"),
            )
        except Exception:
            result = ClaimVerifierOutput()

        tid = context.get("task_id") if context else None
        if tid:
            await self.log_execution(tid, input_data, result, 0, duration_ms)
        return result
