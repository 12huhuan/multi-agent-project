"""
负面评论预警 Agent — Rules-first 引擎。

根据情感分析结果生成分级预警：info / warning / alert / critical。
纯规则驱动，不调用 LLM，保证快速响应。
"""

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent

# 严重关键词：命中任一即触发预警
CRITICAL_KEYWORDS = ["broken", "defective", "scam", "dangerous", "injury", "fire", "electric shock", "burned",
                     "fraud", "fake", "counterfeit", "lawsuit", "lawyer", "refund refused", "return rejected"]
HIGH_KEYWORDS = ["damaged", "stopped working", "poor quality", "disappointed", "waste of money", "don't buy",
                 "returning", "refund", "not as described", "misleading", "terrible", "horrible", "awful"]


class NegativeAlertInput(BaseModel):
    review_content: str = ""
    review_title: str = ""
    rating: float = 3.0
    sentiment: str = "neutral"
    sentiment_score: float = 5.0
    urgency_level: str = "normal"
    reviewer_name: str = ""


class NegativeAlertOutput(BaseModel):
    alert_level: str = "none"  # none | info | warning | alert | critical
    alert_title: str = ""
    alert_description: str = ""
    requires_reply: bool = False
    requires_escalation: bool = False
    suggested_priority: str = "low"


class NegativeAlertAgent(BaseAgent[NegativeAlertInput, NegativeAlertOutput]):
    name = "negative_alert"
    description = "负面评论分级预警，纯规则引擎，不调用 LLM"

    def build_prompt(self, input_data: NegativeAlertInput, context: dict | None = None) -> tuple[str, str]:
        return "", ""  # Rules-first agent, no LLM needed

    async def run(self, input_data: NegativeAlertInput, context: dict | None = None) -> NegativeAlertOutput:
        content_lower = (input_data.review_content + " " + input_data.review_title).lower()
        alert_level = "none"
        alert_title = ""
        alert_description = ""
        requires_reply = False
        requires_escalation = False
        priority = "low"

        # 检查严重关键词
        critical_hits = [kw for kw in CRITICAL_KEYWORDS if kw in content_lower]
        high_hits = [kw for kw in HIGH_KEYWORDS if kw in content_lower]

        if critical_hits:
            alert_level = "critical"
            alert_title = f"严重预警: {', '.join(critical_hits[:3])}"
            alert_description = f"评论包含严重关键词: {', '.join(critical_hits)}"
            requires_reply = True
            requires_escalation = True
            priority = "urgent"
        elif high_hits:
            alert_level = "alert"
            alert_title = f"负面预警: {', '.join(high_hits[:3])}"
            alert_description = f"评论包含负面关键词: {', '.join(high_hits)}"
            requires_reply = True
            requires_escalation = input_data.rating <= 2
            priority = "high"
        elif input_data.rating <= 2:
            alert_level = "warning"
            alert_title = f"低评分评论 ({input_data.rating}/5)"
            alert_description = f"用户 {input_data.reviewer_name} 给出了 {input_data.rating} 星低评分"
            requires_reply = True
            requires_escalation = False
            priority = "medium"
        elif input_data.rating == 3:
            alert_level = "info"
            alert_title = "中性评论提醒"
            alert_description = f"3星评论，可选择性回复"
            requires_reply = input_data.sentiment == "negative"
            requires_escalation = False
            priority = "low"

        return NegativeAlertOutput(
            alert_level=alert_level,
            alert_title=alert_title,
            alert_description=alert_description,
            requires_reply=requires_reply,
            requires_escalation=requires_escalation,
            suggested_priority=priority,
        )
