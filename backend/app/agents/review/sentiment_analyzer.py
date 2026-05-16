"""
情感分析 Agent — 分析评论情感和紧急度。

使用 LLM 做精细化情感分类，输出正面/中性/负面 + 0-10 评分 + 关键短语。
"""

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent


class SentimentAnalyzerInput(BaseModel):
    review_title: str = ""
    review_content: str = ""
    rating: float = 3.0
    platform: str = "amazon_us"


class SentimentAnalyzerOutput(BaseModel):
    sentiment: str = "neutral"  # positive | neutral | negative
    score: float = 5.0  # 0=very negative, 10=very positive
    urgency_level: str = "normal"  # low | normal | high | critical
    key_phrases: list[str] = Field(default_factory=list)
    topics_mentioned: list[str] = Field(default_factory=list)
    analysis_brief: str = ""


class SentimentAnalyzerAgent(BaseAgent[SentimentAnalyzerInput, SentimentAnalyzerOutput]):
    name = "sentiment_analyzer"
    description = "评论情感分析，识别正面/中性/负面 + 紧急度评分"

    def build_prompt(self, input_data: SentimentAnalyzerInput, context: dict | None = None) -> tuple[str, str]:
        system_prompt = (
            "You are a customer review analyst for e-commerce. "
            "Analyze the sentiment and urgency of product reviews.\n"
            "Rules:\n"
            "- sentiment: positive | neutral | negative\n"
            "- score: 0-10, where 0=extremely negative, 10=extremely positive\n"
            "- urgency: low | normal | high | critical (based on anger/refund/fault/safety mentions)\n"
            "- key_phrases: 2-4 important phrases from the review\n"
            "- topics_mentioned: key topics like 'quality', 'shipping', 'price', 'packaging', 'support', etc.\n"
            "- analysis_brief: one-sentence summary\n"
            "Output must be valid JSON."
        )

        user_prompt = (
            f"Review title: {input_data.review_title}\n"
            f"Review content: {input_data.review_content}\n"
            f"Star rating: {input_data.rating}/5\n\n"
            f'Return: {{"sentiment": "...", "score": 0.0, "urgency_level": "...", '
            f'"key_phrases": [...], "topics_mentioned": [...], "analysis_brief": "..."}}'
        )

        return system_prompt, user_prompt

    async def run(self, input_data: SentimentAnalyzerInput, context: dict | None = None) -> SentimentAnalyzerOutput:
        import time

        # 规则层快速判断
        if input_data.rating <= 2:
            default_sentiment, default_score, default_urgency = "negative", float(input_data.rating) * 1.5, "high"
        elif input_data.rating >= 4:
            default_sentiment, default_score, default_urgency = "positive", min(float(input_data.rating) * 2.0, 10), "low"
        else:
            default_sentiment, default_score, default_urgency = "neutral", 5.0, "normal"

        system_prompt, user_prompt = self.build_prompt(input_data, context)
        start = time.time()
        raw = await self._call_llm(system_prompt, user_prompt, max_tokens=512, temperature=0.1)
        duration_ms = int((time.time() - start) * 1000)

        data = self._parse_llm_json(raw)

        try:
            result = SentimentAnalyzerOutput(
                sentiment=data.get("sentiment", default_sentiment),
                score=float(data.get("score", default_score)),
                urgency_level=data.get("urgency_level", default_urgency),
                key_phrases=data.get("key_phrases", []),
                topics_mentioned=data.get("topics_mentioned", []),
                analysis_brief=data.get("analysis_brief", raw[:100]),
            )
        except Exception:
            result = SentimentAnalyzerOutput(
                sentiment=default_sentiment,
                score=default_score,
                urgency_level=default_urgency,
            )

        tid = context.get("task_id") if context else None
        if tid:
            await self.log_execution(tid, input_data, result, 0, duration_ms)

        return result
