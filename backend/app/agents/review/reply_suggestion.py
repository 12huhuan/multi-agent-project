"""
回复建议 Agent — 为负面评论生成客服回复模板。

生成多语言、品牌友好的回复建议，卖家审核后可直接使用。
"""

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent


class ReplySuggestionInput(BaseModel):
    review_content: str = ""
    review_title: str = ""
    reviewer_name: str = "Customer"
    rating: float = 3.0
    sentiment: str = "neutral"
    alert_level: str = "none"
    brand_name: str = ""
    language: str = "en"  # 回复语言
    reply_tone: str = "professional"  # professional | empathetic | apologetic | grateful


class ReplySuggestionOutput(BaseModel):
    subject: str = ""
    reply_text: str = ""
    alternative_reply: str = ""
    tone: str = "professional"
    key_points_addressed: list[str] = Field(default_factory=list)


class ReplySuggestionAgent(BaseAgent[ReplySuggestionInput, ReplySuggestionOutput]):
    name = "reply_suggestion"
    description = "为评论生成品牌友好的回复模板，支持多语言和多种语调"

    def build_prompt(self, input_data: ReplySuggestionInput, context: dict | None = None) -> tuple[str, str]:
        tone_guide = {
            "professional": "Polite, formal, solution-oriented",
            "empathetic": "Warm, understanding, emotionally supportive",
            "apologetic": "Sincere apology, taking responsibility, offering compensation",
            "grateful": "Thankful, appreciative, encouraging continued support",
        }

        system_prompt = (
            "You are a customer service reply specialist for an e-commerce brand. "
            "Write professional, helpful replies to customer reviews.\n"
            "Rules:\n"
            "- Never be defensive or argumentative\n"
            "- Address specific concerns mentioned in the review\n"
            "- If the review is negative, apologize sincerely and offer a solution\n"
            "- If the review is positive, thank the customer warmly\n"
            f"- Tone: {tone_guide.get(input_data.reply_tone, 'professional')}\n"
            "- Keep under 500 characters\n"
            "- Include a call to action (contact support email, visit help page, etc.)\n"
            "- Output must be valid JSON."
        )

        brand_line = f"Brand: {input_data.brand_name}\n" if input_data.brand_name else ""
        user_prompt = (
            f"{brand_line}"
            f"Reviewer: {input_data.reviewer_name}\n"
            f"Rating: {input_data.rating}/5\n"
            f"Title: {input_data.review_title}\n"
            f"Content: {input_data.review_content}\n"
            f"Language: {input_data.language}\n\n"
            f'Return: {{"subject": "...", "reply_text": "...", "alternative_reply": "...", '
            f'"key_points_addressed": [...]}}'
        )

        return system_prompt, user_prompt

    async def run(self, input_data: ReplySuggestionInput, context: dict | None = None) -> ReplySuggestionOutput:
        import time

        system_prompt, user_prompt = self.build_prompt(input_data, context)
        start = time.time()
        raw = await self._call_llm(system_prompt, user_prompt, max_tokens=1024, temperature=0.5)
        duration_ms = int((time.time() - start) * 1000)

        data = self._parse_llm_json(raw)

        try:
            result = ReplySuggestionOutput(
                subject=data.get("subject", "Re: Your review"),
                reply_text=data.get("reply_text", raw),
                alternative_reply=data.get("alternative_reply", ""),
                tone=input_data.reply_tone,
                key_points_addressed=data.get("key_points_addressed", []),
            )
        except Exception:
            result = ReplySuggestionOutput(
                subject="Re: Your review",
                reply_text=raw,
                tone=input_data.reply_tone,
            )

        tid = context.get("task_id") if context else None
        if tid:
            await self.log_execution(tid, input_data, result, 0, duration_ms)

        return result
