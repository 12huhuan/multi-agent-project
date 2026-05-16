"""
意图识别 Agent — Few-shot prompt 分类用户消息。
支持 10+ 意图: 订单查询/退款/退货/产品咨询/物流追踪/投诉/问候/技术支持/价格咨询/库存查询
"""

from pydantic import BaseModel, Field

from backend.app.agents.base import BaseAgent

INTENT_CATEGORIES = [
    "order_inquiry", "refund_request", "return_request", "product_inquiry",
    "logistics_tracking", "complaint", "greeting", "tech_support",
    "price_inquiry", "stock_inquiry", "other",
]


class IntentRecognitionInput(BaseModel):
    message: str
    conversation_history: list[dict] = Field(default_factory=list)
    language: str = "auto"


class IntentRecognitionOutput(BaseModel):
    intent: str = "other"
    confidence: float = 0.0
    language: str = "zh"
    entities: dict = Field(default_factory=dict)
    sentiment: str = "neutral"


class IntentRecognitionAgent(BaseAgent[IntentRecognitionInput, IntentRecognitionOutput]):
    name = "intent_recognition"
    description = "识别用户消息意图、语言和关键实体"

    def build_prompt(self, input_data: IntentRecognitionInput, context: dict | None = None) -> tuple[str, str]:
        history_text = ""
        if input_data.conversation_history:
            recent = input_data.conversation_history[-5:]
            history_text = "\n".join(
                f"[{m.get('role', '?')}] {m.get('content', '')[:200]}"
                for m in recent
            )

        system_prompt = f"""你是跨境电商客服系统的意图识别模块。

支持意图类别: {", ".join(INTENT_CATEGORIES)}

Few-shot 示例:
- "我的订单什么时候到" → order_inquiry (confidence: 0.95)
- "我要退款，产品有质量问题" → refund_request (confidence: 0.92)
- "这个材质是什么" → product_inquiry (confidence: 0.90)
- "快递到哪了" → logistics_tracking (confidence: 0.88)
- "你们客服太差了我要投诉" → complaint (confidence: 0.94)
- "你好" → greeting (confidence: 0.98)

需提取的实体: order_id, product_name, tracking_number, amount, reason

输出必须是有效的 JSON 格式。"""

        user_prompt = f"""对话历史: {history_text or "无"}
用户最新消息: {input_data.message}

请识别意图并提取实体。
返回格式:
{{
  "intent": "意图类别",
  "confidence": 0.0-1.0,
  "language": "zh|en|ja|...",
  "entities": {{}},
  "sentiment": "positive|neutral|negative"
}}"""
        return system_prompt, user_prompt

    async def run(self, input_data: IntentRecognitionInput, context: dict | None = None) -> IntentRecognitionOutput:
        import json
        import time

        system_prompt, user_prompt = self.build_prompt(input_data, context)
        start = time.time()
        raw = await self._call_llm(system_prompt, user_prompt)
        duration_ms = int((time.time() - start) * 1000)

        try:
            t = raw.strip()
            if t.startswith("```"):
                end = t.find("\n", 3)
                if end > 0:
                    t = t[end + 1:]
                if t.endswith("```"):
                    t = t[:-3]
            start_pos = t.find("{")
            end_pos = t.rfind("}") + 1
            data = json.loads(t[start_pos:end_pos]) if start_pos >= 0 and end_pos > start_pos else {}
            result = IntentRecognitionOutput(**data)
        except Exception:
            result = IntentRecognitionOutput(intent="other", confidence=0.3, language=input_data.language)

        if context and "task_id" in context:
            await self.log_execution(context["task_id"], input_data, result, 0, duration_ms)

        return result
