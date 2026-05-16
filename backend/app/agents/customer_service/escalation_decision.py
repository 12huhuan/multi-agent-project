"""
升级决策 Agent — 规则 + LLM 双判：高风险场景强制 escalate。

规则:
- intent ∈ {refund_request, complaint, legal_threat} → escalate（强制人工）
- confidence < 0.7 → suggest_human（建议人工）
- intent ∈ {order_inquiry, logistics_tracking, greeting} → auto_reply（自动回复）
- 其他 → LLM 判断
"""

from pydantic import BaseModel, Field

from backend.app.agents.base import BaseAgent

FORCE_ESCALATE_INTENTS = {"refund_request", "complaint", "legal_threat"}
AUTO_REPLY_INTENTS = {"order_inquiry", "logistics_tracking", "greeting", "stock_inquiry"}


class EscalationDecisionInput(BaseModel):
    intent: str
    confidence: float = 0.0
    user_message: str
    reply_draft: str = ""
    sentiment: str = "neutral"
    conversation_history: list[dict] = Field(default_factory=list)


class EscalationDecisionOutput(BaseModel):
    action: str = "auto_reply"  # auto_reply | suggest_human | escalate
    reason: str = ""
    priority: str = "medium"
    escalation_category: str = ""


class EscalationDecisionAgent(BaseAgent[EscalationDecisionInput, EscalationDecisionOutput]):
    name = "escalation_decision"
    description = "判断是否需要升级到人工客服"

    def build_prompt(self, input_data: EscalationDecisionInput, context: dict | None = None) -> tuple[str, str]:
        return "", ""

    async def run(self, input_data: EscalationDecisionInput, context: dict | None = None) -> EscalationDecisionOutput:
        # 规则层 — 快速路径
        if input_data.intent in FORCE_ESCALATE_INTENTS:
            return EscalationDecisionOutput(
                action="escalate",
                reason=f"高风险意图 {input_data.intent}，强制升级",
                priority="high" if input_data.intent in ("complaint", "legal_threat") else "medium",
                escalation_category=input_data.intent,
            )

        if input_data.confidence < 0.7:
            return EscalationDecisionOutput(
                action="suggest_human",
                reason=f"意图置信度过低 ({input_data.confidence:.2f})",
                priority="medium",
            )

        if input_data.intent in AUTO_REPLY_INTENTS:
            return EscalationDecisionOutput(
                action="auto_reply",
                reason=f"标准可自动处理意图: {input_data.intent}",
                priority="low",
            )

        # LLM 判断层 — 边界场景
        import json
        try:
            raw = await self._call_llm(
                "你是客服升级决策专家。判断是否需要人工介入。返回JSON: "
                '{"action":"auto_reply|suggest_human|escalate","reason":"...","priority":"low|medium|high"}',
                f"意图: {input_data.intent}\n置信度: {input_data.confidence}\n"
                f"用户消息: {input_data.user_message[:300]}\n"
                f"情感: {input_data.sentiment}\n"
                f"回复草稿: {input_data.reply_draft[:200]}",
            )
            t = raw.strip()
            if t.startswith("{"):
                data = json.loads(t[t.find("{"):t.rfind("}") + 1])
                return EscalationDecisionOutput(**data)
        except Exception:
            pass

        return EscalationDecisionOutput(action="auto_reply", reason="默认自动回复", priority="low")
