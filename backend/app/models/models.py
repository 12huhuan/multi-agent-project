"""Phase 1 数据模型 — Listing 生成 + 智能客服"""

import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Boolean, Text, ForeignKey, DateTime, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.db import Base


def gen_uuid():
    return uuid.uuid4()


class ListingTask(Base):
    """Listing 生成任务（含生成结果持久化）"""
    __tablename__ = "listing_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(200), nullable=False)
    target_platform: Mapped[str] = mapped_column(String(50), default="amazon_us")
    target_language: Mapped[str] = mapped_column(String(10), default="en")
    features: Mapped[dict] = mapped_column(JSONB, default=list)
    brand_story: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    # 生成结果持久化
    keywords: Mapped[dict] = mapped_column(JSONB, default=list)
    top_keywords: Mapped[dict] = mapped_column(JSONB, default=list)
    title_candidates: Mapped[dict] = mapped_column(JSONB, default=list)
    bullet_points: Mapped[dict] = mapped_column(JSONB, default=list)
    description_html: Mapped[str] = mapped_column(Text, default="")
    a_plus_modules: Mapped[dict] = mapped_column(JSONB, default=list)
    seo_report: Mapped[dict] = mapped_column(JSONB, default=dict)
    product_images: Mapped[dict] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    executions: Mapped[list["AgentExecution"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class AgentExecution(Base):
    """Agent 单次执行记录"""
    __tablename__ = "agent_executions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("listing_tasks.id", ondelete="CASCADE"))
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[dict] = mapped_column(JSONB, default=dict)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    task: Mapped["ListingTask"] = relationship(back_populates="executions")


class Conversation(Base):
    """客服会话"""
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    customer_id: Mapped[str] = mapped_column(String(200), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), default="web_chat")
    language: Mapped[str] = mapped_column(String(10), default="zh")
    status: Mapped[str] = mapped_column(String(30), default="active")
    product_context: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    """会话消息"""
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    auto_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    __table_args__ = (
        CheckConstraint("role IN ('customer', 'agent', 'system')", name="check_message_role"),
    )


class Ticket(Base):
    """工单"""
    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="open")
    assigned_to: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("priority IN ('low', 'medium', 'high', 'urgent')", name="check_ticket_priority"),
    )


class KnowledgeDocument(Base):
    """知识库文档"""
    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


# ═══════════════════════════════════════════════════════════
# Phase 2: 评论监控
# ═══════════════════════════════════════════════════════════

class ReviewTask(Base):
    """评论抓取任务"""
    __tablename__ = "review_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    product_asin: Mapped[str] = mapped_column(String(100), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), default="amazon_us")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    total_scraped: Mapped[int] = mapped_column(Integer, default=0)
    average_rating: Mapped[float] = mapped_column(default=0.0)
    alerts_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    reviews: Mapped[list["Review"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class Review(Base):
    """单条评论"""
    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("review_tasks.id", ondelete="CASCADE"))
    reviewer_name: Mapped[str] = mapped_column(String(200), default="Anonymous")
    rating: Mapped[float] = mapped_column(default=3.0)
    title: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    verified_purchase: Mapped[bool] = mapped_column(default=False)
    helpful_count: Mapped[int] = mapped_column(Integer, default=0)
    translated_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    translated_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentiment: Mapped[str] = mapped_column(String(20), default="neutral")
    sentiment_score: Mapped[float] = mapped_column(default=5.0)
    urgency_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    alert_level: Mapped[str] = mapped_column(String(20), default="none")
    reply_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_status: Mapped[str] = mapped_column(String(20), default="none")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    task: Mapped["ReviewTask"] = relationship(back_populates="reviews")


# ═══════════════════════════════════════════════════════════
# Phase 2: 社媒内容
# ═══════════════════════════════════════════════════════════

class SocialTask(Base):
    """社媒内容生成任务"""
    __tablename__ = "social_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(200), default="")
    platforms: Mapped[dict] = mapped_column(JSONB, default=list)
    target_languages: Mapped[dict] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    posts: Mapped[list["SocialPost"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class SocialPost(Base):
    """社媒帖子"""
    __tablename__ = "social_posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("social_tasks.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(String(30), default="instagram")
    language: Mapped[str] = mapped_column(String(10), default="en")
    copy: Mapped[str] = mapped_column(Text, default="")
    short_copy: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashtags: Mapped[dict] = mapped_column(JSONB, default=list)
    call_to_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_urls: Mapped[dict] = mapped_column(JSONB, default=list)
    quality_score: Mapped[float] = mapped_column(default=0.0)
    quality_verdict: Mapped[str] = mapped_column(String(20), default="approved")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    task: Mapped["SocialTask"] = relationship(back_populates="posts")
    images: Mapped[list["SocialImage"]] = relationship(back_populates="post", cascade="all, delete-orphan")


class OrchestratorRun(Base):
    """调度运行记录 — 持久化所有步骤结果"""
    __tablename__ = "orchestrator_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    action: Mapped[str] = mapped_column(String(50), default="auto")
    category: Mapped[str | None] = mapped_column(String(200), nullable=True)
    target_market: Mapped[str | None] = mapped_column(String(10), nullable=True)
    context: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="running")
    progress: Mapped[str | None] = mapped_column(String(200), nullable=True)
    decisions: Mapped[dict] = mapped_column(JSONB, default=list)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    completed_steps: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class SocialImage(Base):
    """社媒图片 — 独立存储，与帖子关联"""
    __tablename__ = "social_images"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    post_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("social_posts.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(Text, default="")
    alt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    format: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    post: Mapped["SocialPost"] = relationship(back_populates="images")
