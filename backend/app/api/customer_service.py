"""智能客服 API 路由 — 纯内存模式，无需 PostgreSQL"""

import asyncio
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from backend.app.schemas.schemas import (
    ConversationCreate,
    ConversationResponse,
    MessageCreate,
    MessageResponse,
    TicketResponse,
)
from backend.app.workflows.cs_workflow import cs_workflow, CustomerServiceState
from backend.app.agents.customer_service.intent_recognition import IntentRecognitionAgent, IntentRecognitionInput
from backend.app.agents.customer_service.knowledge_retrieval import KnowledgeRetrievalAgent, KnowledgeRetrievalInput
from backend.app.agents.customer_service.reply_generation import ReplyGenerationAgent, ReplyGenerationInput
from backend.app.agents.customer_service.escalation_decision import EscalationDecisionAgent, EscalationDecisionInput
from backend.app.agents.customer_service.ticket_generation import TicketGenerationAgent, TicketGenerationInput

router = APIRouter(prefix="/api/v1/conversations", tags=["customer_service"])

# 内存存储
_conversations: dict[str, dict] = {}  # conversation_id -> {customer_id, platform, language, status, created_at}
_messages: dict[str, list[dict]] = {}  # conversation_id -> [{id, role, content, intent, auto_reply, created_at}]
_tickets: dict[str, dict] = {}  # ticket_id -> {conversation_id, priority, summary, suggested_action, status, created_at}


@router.post("/", response_model=ConversationResponse)
async def create_conversation(request: ConversationCreate):
    """创建客服会话"""
    conv_id = str(uuid.uuid4())
    now = datetime.now()
    _conversations[conv_id] = {
        "customer_id": request.customer_id,
        "platform": request.platform,
        "language": request.language,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    _messages[conv_id] = []

    return ConversationResponse(
        id=conv_id,
        customer_id=request.customer_id,
        platform=request.platform,
        language=request.language,
        status="active",
        created_at=now,
        updated_at=now,
    )


@router.post("/{conversation_id}/messages", response_model=MessageResponse)
async def send_message(conversation_id: str, request: MessageCreate):
    """发送消息并触发智能客服工作流"""
    if conversation_id not in _conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    now = datetime.now()

    # 保存用户消息
    user_msg_id = str(uuid.uuid4())
    user_msg = {
        "id": user_msg_id,
        "role": "customer",
        "content": request.content,
        "intent": None,
        "auto_reply": False,
        "created_at": now,
    }
    _messages[conversation_id].append(user_msg)

    # 获取对话历史（最近10轮）
    history = _messages[conversation_id][-20:]

    # 启动 LangGraph 客服工作流
    initial_state: CustomerServiceState = {
        "conversation_id": conversation_id,
        "user_message": request.content,
        "conversation_history": [{"role": m["role"], "content": m["content"]} for m in history],
        "language": request.language if request.language != "auto" else "zh",
        "product_context": {},
        "intent": "",
        "confidence": 0.0,
        "entities": {},
        "sentiment": "neutral",
        "knowledge_chunks": [],
        "reply_draft": "",
        "escalation_action": "",
        "escalation_reason": "",
        "ticket": None,
        "status": "running",
        "error": "",
        "current_step": "started",
    }

    config = {"configurable": {"thread_id": conversation_id}}
    try:
        final_state = await cs_workflow.ainvoke(initial_state, config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow error: {str(e)}")

    # 保存 Agent 回复
    reply_content = final_state.get("reply_draft", "") or "抱歉，我暂时无法处理您的请求，请稍后重试。"
    intent = final_state.get("intent", "")
    escalation_action = final_state.get("escalation_action", "")

    agent_msg_id = str(uuid.uuid4())
    agent_msg = {
        "id": agent_msg_id,
        "role": "agent",
        "content": reply_content,
        "intent": intent,
        "auto_reply": escalation_action == "auto_reply",
        "created_at": datetime.now(),
    }
    _messages[conversation_id].append(agent_msg)

    # 如果需要升级，创建工单
    if escalation_action in ("escalate", "suggest_human"):
        ticket_data = final_state.get("ticket", {}) or {}
        ticket_id = str(uuid.uuid4())
        _tickets[ticket_id] = {
            "conversation_id": conversation_id,
            "priority": ticket_data.get("priority", "medium"),
            "summary": ticket_data.get("summary", final_state.get("escalation_reason", "")),
            "suggested_action": ticket_data.get("suggested_action"),
            "status": "open",
            "assigned_to": None,
            "created_at": datetime.now(),
        }

    return MessageResponse(
        id=agent_msg_id,
        conversation_id=conversation_id,
        role="agent",
        content=reply_content,
        intent=intent or None,
        auto_reply=escalation_action == "auto_reply",
        created_at=agent_msg["created_at"],
    )


@router.post("/{conversation_id}/messages/stream")
async def send_message_stream(conversation_id: str, request: MessageCreate):
    """流式发送消息 — SSE 逐 token 推送回复生成，体感延迟降低 50%+"""
    if conversation_id not in _conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    now = datetime.now()

    # 保存用户消息
    user_msg_id = str(uuid.uuid4())
    user_msg = {
        "id": user_msg_id,
        "role": "customer",
        "content": request.content,
        "intent": None,
        "auto_reply": False,
        "created_at": now,
    }
    _messages[conversation_id].append(user_msg)

    history = _messages[conversation_id][-20:]
    language = request.language if request.language != "auto" else "zh"

    async def event_stream():
        # Phase 1 — 意图识别
        intent_agent = IntentRecognitionAgent()
        intent_result = await intent_agent.run(
            IntentRecognitionInput(
                message=request.content,
                conversation_history=[{"role": m["role"], "content": m["content"]} for m in history],
                language=language,
            ),
            context={"task_id": conversation_id},
        )
        yield f"event: progress\ndata: {json.dumps({'step': 'intent_done', 'intent': intent_result.intent, 'confidence': intent_result.confidence, 'sentiment': intent_result.sentiment}, ensure_ascii=False)}\n\n"

        # Phase 2 — 知识检索
        rag_agent = KnowledgeRetrievalAgent()
        rag_result = await rag_agent.run(
            KnowledgeRetrievalInput(
                query=request.content,
                intent=intent_result.intent,
            ),
            context={"task_id": conversation_id},
        )
        chunk_texts = [c.content for c in rag_result.chunks]
        yield f"event: progress\ndata: {json.dumps({'step': 'rag_done', 'chunks_found': len(chunk_texts)}, ensure_ascii=False)}\n\n"

        # Phase 3 — 流式回复生成
        reply_agent = ReplyGenerationAgent()
        history_dicts = [{"role": m["role"], "content": m["content"]} for m in history]
        full_reply = ""
        async for token in reply_agent.reply_stream(
            ReplyGenerationInput(
                user_message=request.content,
                intent=intent_result.intent,
                knowledge_chunks=chunk_texts,
                conversation_history=history_dicts,
                language=language,
            ),
            context={"task_id": conversation_id},
        ):
            full_reply += token
            yield f"event: token\ndata: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

        # Phase 4 — 升级决策
        escalation_agent = EscalationDecisionAgent()
        escalation_result = await escalation_agent.run(
            EscalationDecisionInput(
                intent=intent_result.intent,
                confidence=intent_result.confidence,
                user_message=request.content,
                reply_draft=full_reply,
                sentiment=intent_result.sentiment,
                conversation_history=history_dicts,
            ),
            context={"task_id": conversation_id},
        )

        # 保存 Agent 回复
        agent_msg_id = str(uuid.uuid4())
        agent_msg = {
            "id": agent_msg_id,
            "role": "agent",
            "content": full_reply,
            "intent": intent_result.intent,
            "auto_reply": escalation_result.action == "auto_reply",
            "created_at": datetime.now(),
        }
        _messages[conversation_id].append(agent_msg)

        # Phase 5 — 工单生成（仅在需要升级时）
        ticket_id = None
        if escalation_result.action in ("escalate", "suggest_human"):
            ticket_agent = TicketGenerationAgent()
            summary = f"用户询问: {request.content[:100]}\n意图: {intent_result.intent}"
            ticket_result = await ticket_agent.run(
                TicketGenerationInput(
                    conversation_summary=summary,
                    escalation_reason=escalation_result.reason,
                    user_message=request.content,
                    intent=intent_result.intent,
                ),
                context={"task_id": conversation_id},
            )
            ticket_id = str(uuid.uuid4())
            _tickets[ticket_id] = {
                "conversation_id": conversation_id,
                "priority": escalation_result.priority,
                "summary": escalation_result.reason,
                "suggested_action": ticket_result.suggested_action,
                "status": "open",
                "assigned_to": None,
                "created_at": datetime.now(),
            }

        yield f"event: done\ndata: {json.dumps({'message_id': agent_msg_id, 'intent': intent_result.intent, 'auto_reply': escalation_result.action == 'auto_reply', 'ticket_id': ticket_id, 'escalation_action': escalation_result.action}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_messages(conversation_id: str):
    """获取会话消息历史"""
    msgs = _messages.get(conversation_id, [])
    return [
        MessageResponse(
            id=m["id"],
            conversation_id=conversation_id,
            role=m["role"],
            content=m["content"],
            intent=m.get("intent"),
            auto_reply=m.get("auto_reply", False),
            created_at=m["created_at"],
        )
        for m in msgs
    ]


@router.post("/{conversation_id}/resolve")
async def resolve_conversation(conversation_id: str):
    """关闭会话"""
    if conversation_id in _conversations:
        _conversations[conversation_id]["status"] = "resolved"
    return {"conversation_id": conversation_id, "status": "resolved"}


@router.get("/tickets", response_model=list[TicketResponse])
async def list_tickets():
    """工单列表"""
    return [
        TicketResponse(
            id=tid,
            conversation_id=t.get("conversation_id"),
            priority=t["priority"],
            summary=t["summary"],
            suggested_action=t.get("suggested_action"),
            status=t["status"],
            assigned_to=t.get("assigned_to"),
            created_at=t["created_at"],
        )
        for tid, t in _tickets.items()
    ]


@router.patch("/tickets/{ticket_id}", response_model=TicketResponse)
async def update_ticket(ticket_id: str, update: dict):
    """更新工单状态"""
    if ticket_id not in _tickets:
        raise HTTPException(status_code=404, detail="Ticket not found")

    allowed_fields = {"status", "assigned_to", "priority"}
    for k, v in update.items():
        if k in allowed_fields:
            _tickets[ticket_id][k] = v

    t = _tickets[ticket_id]
    return TicketResponse(
        id=ticket_id,
        conversation_id=t.get("conversation_id"),
        priority=t["priority"],
        summary=t["summary"],
        suggested_action=t.get("suggested_action"),
        status=t["status"],
        assigned_to=t.get("assigned_to"),
        created_at=t["created_at"],
    )
