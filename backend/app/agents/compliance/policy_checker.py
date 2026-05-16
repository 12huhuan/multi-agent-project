"""
政策合规检查 Agent — 检查 Listing 是否符合 Amazon 平台政策。
"""

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent

PROHIBITED_PATTERNS = [
    "best", "#1", "top rated", "guaranteed", "100%", "never fail",
    "cure", "treat", "heal", "medical grade", "FDA approved",
    "free", "cheapest", "lowest price", "discount",
    "click here", "buy now", "limited time",
]


class PolicyCheckerInput(BaseModel):
    title: str = ""
    bullet_points: list[str] = Field(default_factory=list)
    description: str = ""
    category: str = ""
    platform: str = "amazon_us"


class PolicyIssue(BaseModel):
    location: str = ""  # title | bullets | description
    issue_type: str = ""  # prohibited_claim | pricing_policy | medical_claim | formatting
    severity: str = "medium"  # low | medium | high
    description: str = ""
    suggestion: str = ""


class PolicyCheckerOutput(BaseModel):
    issues: list[PolicyIssue] = Field(default_factory=list)
    passed_basic_check: bool = True
    summary: str = ""


class PolicyCheckerAgent(BaseAgent[PolicyCheckerInput, PolicyCheckerOutput]):
    name = "policy_checker"
    description = "检查 Listing 是否符合 Amazon 平台政策"

    def build_prompt(self, input_data: PolicyCheckerInput, context: dict | None = None) -> tuple[str, str]:
        bullets_text = "\n".join(f"- {b}" for b in input_data.bullet_points)
        system_prompt = (
            f"You are an Amazon {input_data.platform} policy compliance expert. "
            "Review the listing content and identify policy violations.\n"
            "Check for:\n"
            "- Prohibited claims (best, #1, guaranteed, etc.)\n"
            "- Pricing/promotional language in listing\n"
            "- Medical/health claims (unless approved category)\n"
            "- Formatting issues (all caps, HTML errors)\n"
            "- Category-specific restrictions\n"
            "Output must be valid JSON."
        )

        user_prompt = (
            f"Category: {input_data.category}\n"
            f"Title: {input_data.title}\n"
            f"Bullet Points:\n{bullets_text}\n"
            f"Description (first 500 chars): {input_data.description[:500]}\n\n"
            f'Return: {{"issues": [{{"location":"...","issue_type":"...","severity":"...",'
            f'"description":"...","suggestion":"..."}}], "passed_basic_check": true/false, "summary": "..."}}'
        )

        return system_prompt, user_prompt

    async def run(self, input_data: PolicyCheckerInput, context: dict | None = None) -> PolicyCheckerOutput:
        import time

        # 规则层：检查禁用词
        rule_issues = []
        all_text = f"{input_data.title} {' '.join(input_data.bullet_points)} {input_data.description}"
        all_lower = all_text.lower()
        for pattern in PROHIBITED_PATTERNS:
            if pattern.lower() in all_lower:
                rule_issues.append(PolicyIssue(
                    location="title/bullets/description",
                    issue_type="prohibited_claim",
                    severity="high" if pattern in ("cure", "treat", "heal", "FDA approved") else "medium",
                    description=f"Found prohibited term: '{pattern}'",
                    suggestion=f"Replace '{pattern}' with compliant alternative",
                ))

        # LLM 层：深层检查
        system_prompt, user_prompt = self.build_prompt(input_data, context)
        start = time.time()
        raw = await self._call_llm(system_prompt, user_prompt, max_tokens=1024, temperature=0.1)
        duration_ms = int((time.time() - start) * 1000)

        data = self._parse_llm_json(raw)
        llm_issues = [PolicyIssue(**i) for i in data.get("issues", [])]
        all_issues = rule_issues + llm_issues

        result = PolicyCheckerOutput(
            issues=all_issues,
            passed_basic_check=data.get("passed_basic_check", len(all_issues) == 0),
            summary=data.get("summary", f"Found {len(all_issues)} compliance issues"),
        )

        tid = context.get("task_id") if context else None
        if tid:
            await self.log_execution(tid, input_data, result, 0, duration_ms)
        return result
