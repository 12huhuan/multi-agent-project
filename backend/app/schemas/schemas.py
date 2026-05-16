"""Phase 1 Pydantic Schema — API 请求/响应模型"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════
# Listing 优化
# ═══════════════════════════════════════════════════════════

class ListingTaskCreate(BaseModel):
    product_name: str = Field(..., min_length=1, max_length=500)
    category: str = Field(..., min_length=1, max_length=200)
    target_platform: str = Field(default="amazon_us")
    target_language: str = Field(default="en")
    features: list[str] = Field(default_factory=list)
    brand_story: str | None = None
    product_images_descriptions: list[str] = Field(default_factory=list)


class ListingTaskResponse(BaseModel):
    id: UUID
    product_name: str
    category: str
    target_platform: str
    target_language: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ListingTaskStatus(BaseModel):
    task_id: UUID
    status: str
    progress: str
    completed_agents: list[str] = []
    pending_agents: list[str] = []
    intermediate_results: dict = {}
    final_result: dict | None = None


class AgentExecutionResponse(BaseModel):
    id: UUID
    task_id: UUID
    agent_name: str
    input_summary: str | None
    output: dict
    tokens_used: int
    duration_ms: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ListingResultResponse(BaseModel):
    task_id: UUID
    title_candidates: list[dict] = []
    bullet_points: list[str] = []
    description_html: str = ""
    a_plus_content: dict = {}
    seo_score: dict = {}
    keywords: list[dict] = []


# ═══════════════════════════════════════════════════════════
# 智能客服
# ═══════════════════════════════════════════════════════════

class ConversationCreate(BaseModel):
    customer_id: str = Field(..., min_length=1)
    platform: str = "web_chat"
    language: str = "zh"
    product_context: dict = Field(default_factory=dict)


class ConversationResponse(BaseModel):
    id: UUID
    customer_id: str
    platform: str
    language: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1)
    language: str = "auto"


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    intent: str | None
    auto_reply: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TicketResponse(BaseModel):
    id: UUID
    conversation_id: UUID | None
    priority: str
    summary: str
    suggested_action: str | None
    status: str
    assigned_to: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════
# 知识库
# ═══════════════════════════════════════════════════════════

class KnowledgeDocCreate(BaseModel):
    title: str
    source_type: str = "markdown"  # pdf | markdown | url
    source_url: str | None = None
    content: str = Field(..., min_length=1)


class KnowledgeDocResponse(BaseModel):
    id: UUID
    title: str
    source_type: str
    source_url: str | None
    chunk_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class KnowledgeSearchResponse(BaseModel):
    query: str
    results: list[dict]  # [{chunk_id, content, score}]


# ═══════════════════════════════════════════════════════════
# 通用
# ═══════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None
    workflow_type: str | None = None  # "listing" | "customer_service"


class ChatResponse(BaseModel):
    response: str
    task_id: str | None = None
    agents_used: list[str] = []
    agent_interactions: list[dict] = []


class AsyncTaskResponse(BaseModel):
    task_id: str
    status: str
    poll_url: str


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "1.0.0"
    services: dict = {}


class WorkflowApproveRequest(BaseModel):
    approved: bool
    modifications: dict = Field(default_factory=dict)
    comment: str | None = None
