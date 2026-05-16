"""
预算分配 Agent — 根据 Campaign 表现智能分配广告预算。
"""

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent


class BudgetAllocatorInput(BaseModel):
    campaigns: list[dict] = Field(default_factory=list)
    total_budget: float = 500.0
    target_acos: float = 30.0


class BudgetAllocation(BaseModel):
    campaign_name: str = ""
    current_budget: float = 0.0
    suggested_budget: float = 0.0
    change_percent: float = 0.0
    reason: str = ""


class BudgetAllocatorOutput(BaseModel):
    allocations: list[BudgetAllocation] = Field(default_factory=list)
    total_allocated: float = 0.0
    summary: str = ""


class BudgetAllocatorAgent(BaseAgent[BudgetAllocatorInput, BudgetAllocatorOutput]):
    name = "budget_allocator"
    description = "根据 Campaign 表现智能分配广告预算"

    def build_prompt(self, input_data: BudgetAllocatorInput, context: dict | None = None) -> tuple[str, str]:
        camp_text = "\n".join(
            f"- {c.get('name','')}: budget=${c.get('budget',0)}, spend=${c.get('spend',0)}, "
            f"sales=${c.get('sales',0)}, ACOS={c.get('acos',0)}%, ROAS={c.get('roas',0)}"
            for c in input_data.campaigns
        )

        system_prompt = (
            f"You are an ad budget allocation specialist. Total budget: ${input_data.total_budget}. "
            f"Target ACOS: <{input_data.target_acos}%.\n"
            "Rules:\n"
            "- High ROAS + low ACOS campaigns → increase budget\n"
            "- High ACOS + low ROAS campaigns → decrease or pause\n"
            "- Keep total allocated within total_budget\n"
            "Output must be valid JSON."
        )

        user_prompt = (
            f"Campaigns:\n{camp_text}\n\n"
            f'Return: {{"allocations": [{{"campaign_name":"...","current_budget":0.0,'
            f'"suggested_budget":0.0,"change_percent":0.0,"reason":"..."}}],'
            f'"total_allocated": 0.0, "summary": "..."}}'
        )

        return system_prompt, user_prompt

    async def run(self, input_data: BudgetAllocatorInput, context: dict | None = None) -> BudgetAllocatorOutput:
        import time

        # 规则层：ROAS 加权分配
        total_roas = sum(max(c.get("roas", 0), 0.1) for c in input_data.campaigns)
        allocations = []

        for c in input_data.campaigns:
            roas = max(c.get("roas", 0), 0.1)
            weight = roas / total_roas if total_roas > 0 else 1.0 / len(input_data.campaigns)
            suggested = round(input_data.total_budget * weight, 2)

            current = float(c.get("budget", 0))
            change = round((suggested - current) / current * 100, 1) if current > 0 else 0

            reason = "High ROAS" if roas >= 3 else "Moderate ROAS" if roas >= 1.5 else "Low ROAS"
            allocations.append(BudgetAllocation(
                campaign_name=c.get("name", ""),
                current_budget=current,
                suggested_budget=suggested,
                change_percent=change,
                reason=reason,
            ))

        # LLM 润色
        system_prompt, user_prompt = self.build_prompt(input_data, context)
        start = time.time()
        raw = await self._call_llm(system_prompt, user_prompt, max_tokens=1024, temperature=0.2)
        duration_ms = int((time.time() - start) * 1000)

        data = self._parse_llm_json(raw)
        result = BudgetAllocatorOutput(
            allocations=allocations,
            total_allocated=sum(a.suggested_budget for a in allocations),
            summary=data.get("summary", raw[:200]),
        )

        tid = context.get("task_id") if context else None
        if tid:
            await self.log_execution(tid, input_data, result, 0, duration_ms)
        return result
