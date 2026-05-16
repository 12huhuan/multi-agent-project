"""
回复生成 Agent — 基于品牌语调、政策、检索知识生成多语言回复。

输入: 意图 + 知识片段 + 对话历史
输出: 多语言回复草稿
"""

from typing import AsyncIterator

from pydantic import BaseModel, Field

from backend.app.agents.base import BaseAgent


class ReplyGenerationInput(BaseModel):
    user_message: str
    intent: str = "other"
    knowledge_chunks: list[str] = Field(default_factory=list)
    conversation_history: list[dict] = Field(default_factory=list)
    language: str = "zh"
    brand_tone: str = "professional"  # professional | friendly | luxury | budget


class ReplyGenerationOutput(BaseModel):
    reply: str = ""
    citations: list[str] = Field(default_factory=list)
    tone_used: str = ""
    follow_up_questions: list[str] = Field(default_factory=list)


class ReplyGenerationAgent(BaseAgent[ReplyGenerationInput, ReplyGenerationOutput]):
    name = "reply_generation"
    description = "生成品牌语调一致的多语言客服回复"

    def build_prompt(self, input_data: ReplyGenerationInput, context: dict | None = None) -> tuple[str, str]:
        knowledge_text = "\n---\n".join(input_data.knowledge_chunks) if input_data.knowledge_chunks else "无相关知识"

        history_text = ""
        if input_data.conversation_history:
            recent = input_data.conversation_history[-5:]
            history_text = "\n".join(
                f"[{m.get('role', '?')}] {m.get('content', '')[:200]}"
                for m in recent
            )

        system_prompt = f"""你是跨境电商客服回复专家。

核心规则:
- 严格基于提供的知识库内容回复，禁止编造信息
- 品牌语调: {input_data.brand_tone}
- 回复语言: {input_data.language}
- 引用知识来源时标注 [来源]
- 回复要简洁、有同理心、解决问题导向
- 如果信息不足以回答，诚实告知并建议升级到人工客服
- 涉及退款/投诉/法律问题时，不要自行承诺，引导到人工客服

输出必须是有效的 JSON 格式。"""

        user_prompt = f"""对话历史: {history_text or "无"}
用户消息: {input_data.user_message}
意图: {input_data.intent}

知识库检索结果:
{knowledge_text}

请生成回复。
返回格式:
{{
  "reply": "完整回复文本",
  "citations": ["引用的知识来源"],
  "tone_used": "使用的语调风格",
  "follow_up_questions": ["可能的追问列表"]
}}"""
        return system_prompt, user_prompt

    async def run(self, input_data: ReplyGenerationInput, context: dict | None = None) -> ReplyGenerationOutput:
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
            result = ReplyGenerationOutput(**data)
        except Exception:
            result = ReplyGenerationOutput(reply=raw[:500] if raw else "抱歉，我暂时无法处理您的请求。")

        if context and "task_id" in context:
            await self.log_execution(context["task_id"], input_data, result, 0, duration_ms)

        return result

    async def reply_stream(self, input_data: ReplyGenerationInput, context: dict | None = None) -> AsyncIterator[str]:
        """流式生成回复 — 逐 token yield 纯文本，不做 JSON 包裹。"""
        knowledge_text = "\n---\n".join(input_data.knowledge_chunks) if input_data.knowledge_chunks else "无相关知识"

        history_text = ""
        if input_data.conversation_history:
            recent = input_data.conversation_history[-5:]
            history_text = "\n".join(
                f"[{m.get('role', '?')}] {m.get('content', '')[:200]}"
                for m in recent
            )

        system_prompt = f"""你是跨境电商客服回复专家。

核心规则:
- 严格基于提供的知识库内容回复，禁止编造信息
- 品牌语调: {input_data.brand_tone}
- 回复语言: {input_data.language}
- 引用知识来源时标注 [来源]
- 回复要简洁、有同理心、解决问题导向
- 如果信息不足以回答，诚实告知并建议升级到人工客服
- 涉及退款/投诉/法律问题时，不要自行承诺，引导到人工客服
- 直接输出回复文本，不要输出 JSON 或其他格式"""

        user_prompt = f"""对话历史: {history_text or "无"}
用户消息: {input_data.user_message}
意图: {input_data.intent}

知识库检索结果:
{knowledge_text}

请直接输出回复内容（纯文本，不要 JSON）："""

        full_reply = ""
        async for token in self._call_llm_stream(system_prompt, user_prompt):
            full_reply += token
            yield token

        self._last_full_reply = full_reply
        self._last_citations: list[str] = []
