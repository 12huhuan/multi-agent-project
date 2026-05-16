"""
评论翻译 Agent — 将英文评论翻译为中文（卖家视角）。

薄封装 shared TranslatorAgent，专用于评论翻译场景。
"""

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent
from backend.app.agents.shared.translator import TranslatorAgent, TranslatorInput


class ReviewTranslatorInput(BaseModel):
    review_content: str = Field(..., min_length=1)
    review_title: str = ""
    source_language: str = "en"
    target_language: str = "zh"


class ReviewTranslatorOutput(BaseModel):
    original_content: str = ""
    original_title: str = ""
    translated_content: str = ""
    translated_title: str = ""
    source_language: str = "en"
    target_language: str = "zh"


class ReviewTranslatorAgent(BaseAgent[ReviewTranslatorInput, ReviewTranslatorOutput]):
    name = "review_translator"
    description = "评论翻译 Agent，将英文评论翻译为中文"

    def build_prompt(self, input_data: ReviewTranslatorInput, context: dict | None = None) -> tuple[str, str]:
        return "", ""  # 委托给共享 TranslatorAgent

    async def run(self, input_data: ReviewTranslatorInput, context: dict | None = None) -> ReviewTranslatorOutput:
        import time
        start = time.time()

        translator = TranslatorAgent()

        # 翻译评论正文
        content_result = await translator.run(
            TranslatorInput(
                text=input_data.review_content,
                source_language=input_data.source_language,
                target_language=input_data.target_language,
                context="Amazon product review",
            ),
            context=context,
        )

        # 翻译评论标题
        title_translated = ""
        if input_data.review_title:
            title_result = await translator.run(
                TranslatorInput(
                    text=input_data.review_title,
                    source_language=input_data.source_language,
                    target_language=input_data.target_language,
                    context="Amazon product review title",
                ),
                context=context,
            )
            title_translated = title_result.translated_text

        duration_ms = int((time.time() - start) * 1000)
        result = ReviewTranslatorOutput(
            original_content=input_data.review_content,
            original_title=input_data.review_title,
            translated_content=content_result.translated_text,
            translated_title=title_translated,
            source_language=input_data.source_language,
            target_language=input_data.target_language,
        )

        return result
