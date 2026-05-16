"""
智能客服工作流 — LangGraph StateGraph。

Agent 链:
用户消息 → [1.意图识别] → [2.知识检索(RAG)] → [3.回复生成] → [4.升级决策] → 自动回复 / [5.工单生成]
"""

from typing import TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from backend.app.agents.customer_service.intent_recognition import IntentRecognitionAgent, IntentRecognitionInput
from backend.app.agents.customer_service.knowledge_retrieval import KnowledgeRetrievalAgent, KnowledgeRetrievalInput
from backend.app.agents.customer_service.reply_generation import ReplyGenerationAgent, ReplyGenerationInput
from backend.app.agents.customer_service.escalation_decision import EscalationDecisionAgent, EscalationDecisionInput
from backend.app.agents.customer_service.ticket_generation import TicketGenerationAgent, TicketGenerationInput


class CustomerServiceState(TypedDict):
    # 输入
    conversation_id: str
    user_message: str
    conversation_history: list[dict]
    language: str
    product_context: dict

    # 中间结果
    intent: str
    confidence: float
    entities: dict
    sentiment: str
    knowledge_chunks: list[dict]
    reply_draft: str
    escalation_action: str
    escalation_reason: str
    ticket: dict | None

    # 状态
    status: str
    error: str
    current_step: str


# Agent 实例
intent_agent = IntentRecognitionAgent()
rag_agent = KnowledgeRetrievalAgent()
reply_agent = ReplyGenerationAgent()
escalation_agent = EscalationDecisionAgent()
ticket_agent = TicketGenerationAgent()


async def intent_recognition_node(state: CustomerServiceState) -> CustomerServiceState:
    try:
        result = await intent_agent.run(
            IntentRecognitionInput(
                message=state["user_message"],
                conversation_history=state["conversation_history"],
                language=state.get("language", "auto"),
            ),
            context={"task_id": state["conversation_id"]},
        )
        state["intent"] = result.intent
        state["confidence"] = result.confidence
        state["entities"] = result.entities
        state["sentiment"] = result.sentiment
        state["language"] = result.language
        state["current_step"] = "intent_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def knowledge_retrieval_node(state: CustomerServiceState) -> CustomerServiceState:
    if state["status"] == "failed":
        return state
    try:
        result = await rag_agent.run(
            KnowledgeRetrievalInput(
                query=state["user_message"],
                intent=state["intent"],
                product_context=state.get("product_context", {}),
            ),
            context={"task_id": state["conversation_id"]},
        )
        state["knowledge_chunks"] = [c.model_dump() for c in result.chunks]
        state["current_step"] = "rag_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def reply_generation_node(state: CustomerServiceState) -> CustomerServiceState:
    if state["status"] == "failed":
        return state
    try:
        chunk_texts = [c.get("content", "") for c in state["knowledge_chunks"]]
        result = await reply_agent.run(
            ReplyGenerationInput(
                user_message=state["user_message"],
                intent=state["intent"],
                knowledge_chunks=chunk_texts,
                conversation_history=state["conversation_history"],
                language=state.get("language", "zh"),
            ),
            context={"task_id": state["conversation_id"]},
        )
        state["reply_draft"] = result.reply
        state["current_step"] = "reply_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def escalation_decision_node(state: CustomerServiceState) -> CustomerServiceState:
    if state["status"] == "failed":
        return state
    try:
        result = await escalation_agent.run(
            EscalationDecisionInput(
                intent=state["intent"],
                confidence=state["confidence"],
                user_message=state["user_message"],
                reply_draft=state.get("reply_draft", ""),
                sentiment=state.get("sentiment", "neutral"),
                conversation_history=state["conversation_history"],
            ),
            context={"task_id": state["conversation_id"]},
        )
        state["escalation_action"] = result.action
        state["escalation_reason"] = result.reason
        state["current_step"] = "escalation_done"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


async def ticket_generation_node(state: CustomerServiceState) -> CustomerServiceState:
    if state["status"] == "failed":
        return state
    try:
        recent = state["conversation_history"][-3:] if state["conversation_history"] else []
        summary = f"用户询问: {state['user_message'][:100]}\n意图: {state['intent']}"
        result = await ticket_agent.run(
            TicketGenerationInput(
                conversation_summary=summary,
                escalation_reason=state["escalation_reason"],
                user_message=state["user_message"],
                intent=state["intent"],
            ),
            context={"task_id": state["conversation_id"]},
        )
        state["ticket"] = result.model_dump()
        state["current_step"] = "ticket_done"
        state["status"] = "completed"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "failed"
    return state


def route_after_escalation(state: CustomerServiceState) -> str:
    """条件路由: 根据升级决策决定下一步"""
    if state.get("status") == "failed":
        return END
    if state["escalation_action"] in ("escalate", "suggest_human"):
        return "ticket_generation"
    return END


def build_cs_workflow() -> StateGraph:
    """构建智能客服 LangGraph 工作流"""
    workflow = StateGraph(CustomerServiceState)

    workflow.add_node("intent_recognition", intent_recognition_node)
    workflow.add_node("knowledge_retrieval", knowledge_retrieval_node)
    workflow.add_node("reply_generation", reply_generation_node)
    workflow.add_node("escalation_decision", escalation_decision_node)
    workflow.add_node("ticket_generation", ticket_generation_node)

    workflow.set_entry_point("intent_recognition")
    workflow.add_edge("intent_recognition", "knowledge_retrieval")
    workflow.add_edge("knowledge_retrieval", "reply_generation")
    workflow.add_edge("reply_generation", "escalation_decision")

    workflow.add_conditional_edges(
        "escalation_decision",
        route_after_escalation,
        {
            "ticket_generation": "ticket_generation",
            END: END,
        },
    )
    workflow.add_edge("ticket_generation", END)

    return workflow


cs_workflow = build_cs_workflow().compile(checkpointer=MemorySaver())
