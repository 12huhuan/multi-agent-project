"""
工单生成 Agent — 生成结构化工单 JSON，含优先级、摘要、建议处理方案。

仅在升级决策为 escalate/suggest_human 时触发。
"""

from pydantic import BaseModel, Field

from backend.app.agents.base import BaseAgent


class TicketGenerationInput(BaseModel):
    conversation_summary: str
    escalation_reason: str
    user_message: str
    intent: str
    priority: str = "medium"


class TicketGenerationOutput(BaseModel):
    summary: str = ""
    priority: str = "medium"
    suggested_action: str = ""
    tags: list[str] = Field(default_factory=list)
    related_order_id: str | None = None
    related_product: str | None = None


class TicketGenerationAgent(BaseAgent[TicketGenerationInput, TicketGenerationOutput]):
    name = "ticket_generation"
    description = "生成需人工处理的工单"

    def build_prompt(self, input_data: TicketGenerationInput, context: dict | None = None) -> tuple[str, str]:
        system_prompt = """你是跨境电商客服工单系统。生成结构化工单以便人工客服快速处理。

输出必须是有效的 JSON 格式。"""

        user_prompt = f"""对话摘要: {input_data.conversation_summary}
升级原因: {input_data.escalation_reason}
用户消息: {input_data.user_message}
意图: {input_data.intent}
建议优先级: {input_data.priority}

生成工单:
{{
  "summary": "1-2句简洁摘要",
  "priority": "low|medium|high|urgent",
  "suggested_action": "建议人工客服采取的行动",
  "tags": ["标签1", "标签2"],
  "related_order_id": null,
  "related_product": null
}}"""
        return system_prompt, user_prompt

    async def run(self, input_data: TicketGenerationInput, context: dict | None = None) -> TicketGenerationOutput:
        import json
        import time

        system_prompt, user_prompt = self.build_prompt(input_data, context)
        start = time.time()
        raw = await self._call_llm(system_prompt, user_prompt)
        duration_ms = int((time.time() - start) * 1000)

        try:
            t = raw.strip()
            start_pos = t.find("{")
            end_pos = t.rfind("}") + 1
            data = json.loads(t[start_pos:end_pos]) if start_pos >= 0 and end_pos > start_pos else {}
            result = TicketGenerationOutput(**data)
        except Exception:
            result = TicketGenerationOutput(
                summary=input_data.conversation_summary,
                priority=input_data.priority,
                suggested_action="请人工客服查看",
            )

        if context and "task_id" in context:
            await self.log_execution(context["task_id"], input_data, result, 0, duration_ms)

        return result
