"""
上下文总线 — 在 orchestrator 和 workflow 之间建立强类型数据传递层。

组件:
  ProductContext    — 产品全生命周期数据的唯一真相来源
  ContextMapper      — 双向翻译: ProductContext ↔ Workflow State (ingest / derive)
  ContextBus         — 运行时管理器: 持久化 / 版本追踪 / HITL 恢复

背景: 旧 orchestrator 用无类型 dict 传递上下文，字段靠字符串硬编码，
拼写错误静默丢数据。ContextBus 消除此类问题。
"""

from datetime import datetime, timezone
from typing import Any
from pathlib import Path
import json
import uuid

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# Product Context 子模型
# ═══════════════════════════════════════════════════════════════

class ProductIdentity(BaseModel):
    """种子数据 — 用户最少只需填 category 和目标市场"""
    product_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    category: str = ""
    subcategory: str | None = None
    brand_name: str | None = None
    brand_story: str | None = None
    target_market: str = "US"
    language: str = "en"
    seller_budget: str = "$5000-$15000"
    seller_strengths: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)


class MarketInsight(BaseModel):
    """选品阶段产出"""
    category_overview: str = ""
    market_size_estimate: str = ""
    market_growth_trend: str = ""
    top_competitors: list[str] = Field(default_factory=list)
    recommended_niches: list[str] = Field(default_factory=list)
    top_pick_product: str = ""
    scored_alternatives: list[dict] = Field(default_factory=list)

    # 从自由文本结构化提取（由 SelectionMapper.ingest 的 LLM 调用填充）
    inferred_selling_points: list[str] = Field(default_factory=list)
    inferred_target_audience: str = ""
    inferred_price_range: str = ""
    inferred_material: str | None = None
    competitor_keywords: list[str] = Field(default_factory=list)
    differentiation_angle: str = ""

    # 提取置信度（derive 在低于阈值时回退到 _generate_*）
    extraction_confidence: float = 0.0


class ListingContent(BaseModel):
    """Listing 生成阶段产出"""
    keywords: list[dict] = Field(default_factory=list)
    top_keywords: list[str] = Field(default_factory=list)
    title_candidates: list[dict] = Field(default_factory=list)
    best_title: str = ""
    bullet_points: list[dict] = Field(default_factory=list)
    description_html: str = ""
    a_plus_modules: list[dict] = Field(default_factory=list)
    seo_report: dict = Field(default_factory=dict)
    human_approved: bool = False


class ComplianceReport(BaseModel):
    """合规审查阶段产出"""
    policy_issues: list[dict] = Field(default_factory=list)
    claim_issues: list[dict] = Field(default_factory=list)
    overall_verdict: str = ""
    risk_level: str = ""
    total_issues: int = 0
    critical_items: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    human_reviewed: bool = False


class SocialContent(BaseModel):
    """社媒内容阶段产出"""
    marketing_angles: list[str] = Field(default_factory=list)
    target_audience: str = ""
    content_tones: list[str] = Field(default_factory=list)
    key_selling_points: list[str] = Field(default_factory=list)
    visual_style: list[str] = Field(default_factory=list)
    hashtag_themes: list[str] = Field(default_factory=list)
    posts: list[dict] = Field(default_factory=list)
    human_approved: bool = False


class PlatformState(BaseModel):
    """执行网关产出 — 连接"内容生成"和"运营监控"的桥梁"""
    asin: str | None = None
    amazon_url: str | None = None
    amazon_publish_status: str = "draft"
    amazon_publish_errors: list[str] = Field(default_factory=list)
    amazon_published_at: datetime | None = None
    social_publish_status: dict[str, str] = Field(default_factory=dict)
    social_post_urls: dict[str, str] = Field(default_factory=dict)


class ReviewSnapshot(BaseModel):
    """评论监控阶段产出"""
    total_reviews: int = 0
    average_rating: float = 0.0
    sentiment_distribution: dict = Field(default_factory=dict)
    negative_alert_count: int = 0
    top_alerts: list[dict] = Field(default_factory=list)
    last_monitored_at: datetime | None = None


class AdSnapshot(BaseModel):
    """广告管理阶段产出"""
    campaigns: list[dict] = Field(default_factory=list)
    total_budget: float = 0.0
    total_spend: float = 0.0
    acos: float | None = None


# ═══════════════════════════════════════════════════════════════
# ProductContext — 顶层聚合模型
# ═══════════════════════════════════════════════════════════════

class ProductContext(BaseModel):
    """产品全生命周期数据的唯一真相来源"""
    product_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    current_stage: str = "init"  # init → analyzed → listed → compliant → published → monitored
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1

    identity: ProductIdentity = Field(default_factory=ProductIdentity)
    market_insight: MarketInsight = Field(default_factory=MarketInsight)
    listing: ListingContent = Field(default_factory=ListingContent)
    compliance: ComplianceReport = Field(default_factory=ComplianceReport)
    social: SocialContent = Field(default_factory=SocialContent)
    platform: PlatformState = Field(default_factory=PlatformState)
    reviews: ReviewSnapshot = Field(default_factory=ReviewSnapshot)
    ads: AdSnapshot = Field(default_factory=AdSnapshot)

    def bump(self) -> "ProductContext":
        """版本递增，更新时间戳"""
        self.version += 1
        self.updated_at = datetime.now(timezone.utc)
        return self

    def to_dict(self) -> dict:
        """序列化为 dict（供 JSON 持久化）"""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict) -> "ProductContext":
        return cls(**data)


# ═══════════════════════════════════════════════════════════════
# ContextMapper — 双向翻译基类
# ═══════════════════════════════════════════════════════════════

class ContextMapper:
    """
    每个业务域一个 Mapper，负责两件事：
    1. ingest()  — 上游 workflow 完成后，把结果写入 ProductContext
    2. derive()  — 下游 workflow 启动前，从 ProductContext 提取 State 输入

    三种映射策略：
    - 直接映射: 字段改名（零 LLM）
    - 结构化提取: LLM 从自由文本提取结构化字段（1次/阶段 ingest）
    - 按需生成: 字段确实缺失且无法推导时调用 LLM
    """

    domain: str = "base"

    async def ingest(self, workflow_result: dict, ctx: ProductContext) -> ProductContext:
        """上游完成 → 写入上下文"""
        raise NotImplementedError

    def derive(self, ctx: ProductContext) -> dict:
        """上游上下文 → 下游 workflow state"""
        raise NotImplementedError

    @staticmethod
    def _get_or_default(value: Any, default: Any) -> Any:
        """空值保护，避免 None 传入 workflow"""
        return value if value else default


# ═══════════════════════════════════════════════════════════════
# Domain Mappers — 5 个
# ═══════════════════════════════════════════════════════════════

class SelectionMapper(ContextMapper):
    """选品 workflow ↔ ProductContext"""
    domain = "selection"

    async def ingest(self, workflow_result: dict, ctx: ProductContext) -> ProductContext:
        ctx.market_insight = MarketInsight(
            category_overview=workflow_result.get("category_overview", ""),
            recommended_niches=workflow_result.get("recommended_niches", []),
            top_pick_product=workflow_result.get("top_pick", ""),
            scored_alternatives=workflow_result.get("scored_products", []),
        )
        ctx.current_stage = "analyzed"
        return ctx.bump()

    def derive(self, ctx: ProductContext) -> dict:
        return {
            "category": ctx.identity.category,
            "keywords": ctx.market_insight.competitor_keywords or [],
            "target_market": ctx.identity.target_market,
            "seller_budget": ctx.identity.seller_budget,
            "seller_strengths": ctx.identity.seller_strengths,
        }


class ListingMapper(ContextMapper):
    """Listing workflow ↔ ProductContext"""
    domain = "listing"

    async def ingest(self, workflow_result: dict, ctx: ProductContext) -> ProductContext:
        ctx.listing = ListingContent(
            keywords=workflow_result.get("keywords", []),
            top_keywords=workflow_result.get("top_keywords", []),
            title_candidates=workflow_result.get("title_candidates", []),
            best_title=workflow_result.get("best_title", ""),
            bullet_points=workflow_result.get("bullet_points", []),
            description_html=workflow_result.get("description_html", ""),
            a_plus_modules=workflow_result.get("a_plus_modules", []),
            seo_report=workflow_result.get("seo_report", {}),
        )
        ctx.current_stage = "listed"
        return ctx.bump()

    def derive(self, ctx: ProductContext) -> dict:
        """从 ProductContext 派生 ListingState — 零额外 LLM 调用"""
        mi = ctx.market_insight
        identity = ctx.identity

        features = mi.inferred_selling_points.copy() if mi.inferred_selling_points else []
        brand_story = identity.brand_story
        top_keywords = mi.competitor_keywords.copy() if mi.competitor_keywords else []

        return {
            "task_id": ctx.product_id,
            "product_name": mi.top_pick_product or "",
            "category": identity.category,
            "features": features,
            "brand_story": brand_story,
            "keywords": top_keywords,
            "top_keywords": top_keywords,
            "target_platform": f"amazon_{identity.target_market.lower()}",
            "target_language": identity.language,
            "image_descriptions": getattr(identity, "image_descriptions", None) or [],
        }


class ComplianceMapper(ContextMapper):
    """合规 workflow ↔ ProductContext"""
    domain = "compliance"

    async def ingest(self, workflow_result: dict, ctx: ProductContext) -> ProductContext:
        ctx.compliance = ComplianceReport(
            policy_issues=workflow_result.get("policy_issues", []),
            claim_issues=workflow_result.get("claim_issues", []),
            overall_verdict=workflow_result.get("overall_verdict", ""),
            risk_level=workflow_result.get("risk_level", ""),
            total_issues=workflow_result.get("total_issues", 0),
            critical_items=workflow_result.get("critical_items", []),
            action_items=workflow_result.get("action_items", []),
        )
        if ctx.compliance.overall_verdict == "pass":
            ctx.current_stage = "compliant"
        return ctx.bump()

    def derive(self, ctx: ProductContext) -> dict:
        bullets = [bp.get("text", "") if isinstance(bp, dict) else str(bp)
                    for bp in ctx.listing.bullet_points[:5]]
        return {
            "title": ctx.listing.best_title,
            "bullet_points": bullets,
            "description": ctx.listing.description_html,
            "category": ctx.identity.category,
            "product_features": ctx.market_insight.inferred_selling_points,
            "platform": f"amazon_{ctx.identity.target_market.lower()}",
        }


class SocialMapper(ContextMapper):
    """社媒 workflow ↔ ProductContext"""
    domain = "social"

    async def ingest(self, workflow_result: dict, ctx: ProductContext) -> ProductContext:
        posts = workflow_result.get("posts", [])
        ctx.social = SocialContent(
            marketing_angles=workflow_result.get("marketing_angles", []),
            target_audience=workflow_result.get("target_audience", ""),
            content_tones=workflow_result.get("content_tones", []),
            key_selling_points=workflow_result.get("key_selling_points", []),
            visual_style=workflow_result.get("visual_style", []),
            hashtag_themes=workflow_result.get("hashtag_themes", []),
            posts=posts,
        )
        if posts:
            ctx.current_stage = "socialized"
        return ctx.bump()

    def derive(self, ctx: ProductContext) -> dict:
        return {
            "product_name": ctx.market_insight.top_pick_product or ctx.identity.category,
            "category": ctx.identity.category,
            "features": ctx.market_insight.inferred_selling_points,
            "brand_story": self._get_or_default(
                ctx.identity.brand_story,
                f"Premium {ctx.identity.category} brand",
            ),
            "platforms": ctx.identity.platforms or ["instagram", "threads", "pinterest"],
            "language": ctx.identity.language,
            "target_markets": [ctx.identity.target_market],
        }


class ReviewMapper(ContextMapper):
    """评论 workflow ↔ ProductContext"""
    domain = "review"

    async def ingest(self, workflow_result: dict, ctx: ProductContext) -> ProductContext:
        ctx.reviews = ReviewSnapshot(
            total_reviews=workflow_result.get("total_scraped", 0),
            negative_alert_count=workflow_result.get("alert_count", 0),
            top_alerts=workflow_result.get("alerts", []),
            last_monitored_at=datetime.now(timezone.utc),
        )
        if ctx.reviews.total_reviews > 0:
            ctx.current_stage = "monitored"
        return ctx.bump()

    def derive(self, ctx: ProductContext) -> dict:
        return {
            "product_asin": ctx.platform.asin or f"B{ctx.product_id[:10]}",
            "platform": f"amazon_{ctx.identity.target_market.lower()}",
            "max_reviews": 10,
            "language": "zh",
        }


# ═══════════════════════════════════════════════════════════════
# ContextBus — 运行时管理器
# ═══════════════════════════════════════════════════════════════

class ContextBus:
    """
    管理 ProductContext 的创建、持久化、版本追踪和恢复。

    用法:
      bus = ContextBus(persist_dir="data/contexts")
      ctx = bus.create(category="Headphones", target_market="US")
      # ... 运行 pipeline ...
      bus.save(ctx)
    """

    def __init__(self, persist_dir: str = "data/contexts"):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, ProductContext] = {}

        # 注册所有 domain mapper
        self.mappers: dict[str, ContextMapper] = {
            "selection": SelectionMapper(),
            "listing": ListingMapper(),
            "compliance": ComplianceMapper(),
            "social": SocialMapper(),
            "review": ReviewMapper(),
        }

    def create(self, **kwargs) -> ProductContext:
        """创建新的产品上下文"""
        ctx = ProductContext(identity=ProductIdentity(**kwargs))
        self._cache[ctx.product_id] = ctx
        return ctx

    def get(self, product_id: str) -> ProductContext | None:
        """从缓存或磁盘获取上下文"""
        if product_id in self._cache:
            return self._cache[product_id]
        file = self.persist_dir / f"{product_id}.json"
        if file.exists():
            ctx = ProductContext.from_dict(json.loads(file.read_text(encoding="utf-8")))
            self._cache[product_id] = ctx
            return ctx
        return None

    def save(self, ctx: ProductContext) -> None:
        """持久化到磁盘"""
        self._cache[ctx.product_id] = ctx
        file = self.persist_dir / f"{ctx.product_id}.json"
        file.write_text(json.dumps(ctx.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    async def ingest(self, domain: str, workflow_result: dict, ctx: ProductContext) -> ProductContext:
        """上游 workflow 完成 → 写入 ProductContext"""
        mapper = self.mappers.get(domain)
        if mapper is None:
            raise ValueError(f"No mapper for domain: {domain}")
        return await mapper.ingest(workflow_result, ctx)

    def derive(self, domain: str, ctx: ProductContext) -> dict:
        """从 ProductContext → workflow state（零 LLM）"""
        mapper = self.mappers.get(domain)
        if mapper is None:
            raise ValueError(f"No mapper for domain: {domain}")
        return mapper.derive(ctx)

    def derive_selection(self, ctx: ProductContext) -> dict:
        return self.mappers["selection"].derive(ctx)

    def derive_listing(self, ctx: ProductContext) -> dict:
        return self.mappers["listing"].derive(ctx)

    def derive_compliance(self, ctx: ProductContext) -> dict:
        return self.mappers["compliance"].derive(ctx)

    def derive_social(self, ctx: ProductContext) -> dict:
        return self.mappers["social"].derive(ctx)

    def derive_review(self, ctx: ProductContext) -> dict:
        return self.mappers["review"].derive(ctx)
