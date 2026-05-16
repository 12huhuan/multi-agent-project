"""
共享翻译 Agent — 基于 deepseek-chat LLM 的多语言翻译。

支持 20+ 语言对，评论监控和社媒内容两个模块共享。
Phase 2 用此 Agent 替代 DeepL MCP，开发阶段零成本。
"""

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent

SUPPORTED_LANGUAGES = {
    "zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean",
    "fr": "French", "de": "German", "es": "Spanish", "it": "Italian",
    "pt": "Portuguese", "ru": "Russian", "ar": "Arabic", "th": "Thai",
    "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay", "nl": "Dutch",
    "pl": "Polish", "tr": "Turkish", "hi": "Hindi", "tl": "Filipino",
}


class TranslatorInput(BaseModel):
    text: str = Field(..., min_length=1)
    source_language: str = "auto"
    target_language: str = "zh"
    context: str = ""  # 可选：翻译上下文（如 "Amazon product review", "social media post"）


class TranslatorOutput(BaseModel):
    original_text: str = ""
    translated_text: str = ""
    source_language: str = ""
    target_language: str = ""
    confidence_note: str = ""


class TranslatorAgent(BaseAgent[TranslatorInput, TranslatorOutput]):
    name = "translator"
    description = "多语言翻译 Agent，基于 DeepSeek LLM，支持 20+ 语言对"

    def build_prompt(self, input_data: TranslatorInput, context: dict | None = None) -> tuple[str, str]:
        src_label = SUPPORTED_LANGUAGES.get(input_data.source_language, input_data.source_language)
        tgt_label = SUPPORTED_LANGUAGES.get(input_data.target_language, input_data.target_language)

        system_prompt = (
            f"You are a professional translator specializing in e-commerce content. "
            f"Translate from {src_label} to {tgt_label}. "
            f"Rules:\n"
            f"- Preserve the original tone and intent\n"
            f"- Keep product names, brand names, and URLs untranslated\n"
            f"- For colloquial expressions, find natural equivalents in the target language\n"
            f"- Preserve emojis and special characters\n"
            f"- Output must be valid JSON."
        )

        ctx_line = f"\nContext/domain: {input_data.context}" if input_data.context else ""
        user_prompt = (
            f"Translate the following text from {src_label} to {tgt_label}.{ctx_line}\n\n"
            f'Text to translate:\n"""{input_data.text}"""\n\n'
            f'Return format: {{"translated_text": "...", "confidence_note": "..."}}'
        )

        return system_prompt, user_prompt

    async def run(self, input_data: TranslatorInput, context: dict | None = None) -> TranslatorOutput:
        import time

        system_prompt, user_prompt = self.build_prompt(input_data, context)
        start = time.time()
        raw = await self._call_llm(system_prompt, user_prompt, max_tokens=2048, temperature=0.2)
        duration_ms = int((time.time() - start) * 1000)

        data = self._parse_llm_json(raw)
        translated = data.get("translated_text", raw)

        # 回退：如果 JSON 解析失败，将原始输出作为译文
        if not translated or translated == raw:
            translated = raw.strip().strip('"')

        result = TranslatorOutput(
            original_text=input_data.text,
            translated_text=translated,
            source_language=input_data.source_language,
            target_language=input_data.target_language,
            confidence_note=data.get("confidence_note", "llm-translated"),
        )

        tid = context.get("task_id") if context else None
        if tid:
            await self.log_execution(tid, input_data, result, 0, duration_ms)

        return result
