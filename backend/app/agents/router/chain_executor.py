"""
链路执行器 — 执行3条预定义工作流链路 + 全链路调度。

3条链路:
  1. 选品上架: selection → listing → compliance
  2. 营销推广: social (6平台内容生成)
  3. 售后监控: review (抓取→情感→翻译→预警→回复)

全链路调度器: 依次执行3条链路，ContextBus 贯穿始终。
"""

import asyncio
import uuid
import random
from typing import Any

from backend.app.core.context_bus import ProductContext, ContextBus


class ChainExecutor:
    """执行预定义的工作流链路"""

    def __init__(self, bus: ContextBus | None = None):
        self.bus = bus or ContextBus()

    # ═══════════════════════════════════════════════════════════
    # 链路 1: 选品上架 (selection → listing → compliance)
    # ═══════════════════════════════════════════════════════════

    async def run_selection_listing_chain(
        self, ctx: ProductContext, extra: dict | None = None
    ) -> list[dict]:
        """选品上架链: 市场分析 → Listing优化 → 合规审查"""
        extra = extra or {}
        decisions: list[dict] = []

        pipeline = [
            ("selection", "Step 1/3: 智能选品"),
            ("listing", "Step 2/3: Listing生成"),
            ("compliance", "Step 3/3: 合规审查"),
        ]

        for domain, label in pipeline:
            dec = {"domain": domain, "label": label, "status": "running"}
            try:
                state = self.bus.derive(domain, ctx)
                state = await self._ensure_fields(domain, state, extra)
                result_str, data = await self._execute_domain(domain, state)
                ctx = await self.bus.ingest(domain, data, ctx)
                dec["status"] = "done"
                dec["result"] = str(result_str)[:300]
                dec["data"] = data or {}
            except Exception as e:
                dec["status"] = "failed"
                dec["result"] = str(e)[:200]
            decisions.append(dec)

        self.bus.save(ctx)
        return decisions

    # ═══════════════════════════════════════════════════════════
    # 链路 2: 营销推广 (social)
    # ═══════════════════════════════════════════════════════════

    async def run_marketing_chain(
        self, ctx: ProductContext, extra: dict | None = None
    ) -> list[dict]:
        """营销推广链: 社媒内容生成(6平台)"""
        extra = extra or {}
        decisions: list[dict] = []

        pipeline = [
            ("social", "Step 1/1: 社媒内容生成"),
        ]

        for domain, label in pipeline:
            dec = {"domain": domain, "label": label, "status": "running"}
            try:
                state = self.bus.derive(domain, ctx)
                state = await self._ensure_fields(domain, state, extra)
                result_str, data = await self._execute_domain(domain, state)
                ctx = await self.bus.ingest(domain, data, ctx)
                dec["status"] = "done"
                dec["result"] = str(result_str)[:300]
                dec["data"] = data or {}
            except Exception as e:
                dec["status"] = "failed"
                dec["result"] = str(e)[:200]
            decisions.append(dec)

        self.bus.save(ctx)
        return decisions

    # ═══════════════════════════════════════════════════════════
    # 链路 3: 售后监控 (review)
    # ═══════════════════════════════════════════════════════════

    async def run_aftersales_chain(
        self, ctx: ProductContext, extra: dict | None = None
    ) -> list[dict]:
        """售后监控链: 评论抓取→情感分析→翻译→预警→回复"""
        extra = extra or {}
        decisions: list[dict] = []

        pipeline = [
            ("review", "Step 1/1: 评论监控"),
        ]

        for domain, label in pipeline:
            dec = {"domain": domain, "label": label, "status": "running"}
            try:
                state = self.bus.derive(domain, ctx)
                state = await self._ensure_fields(domain, state, extra)
                result_str, data = await self._execute_domain(domain, state)
                ctx = await self.bus.ingest(domain, data, ctx)
                dec["status"] = "done"
                dec["result"] = str(result_str)[:300]
                dec["data"] = data or {}
            except Exception as e:
                dec["status"] = "failed"
                dec["result"] = str(e)[:200]
            decisions.append(dec)

        self.bus.save(ctx)
        return decisions

    # ═══════════════════════════════════════════════════════════
    # 全链路调度器
    # ═══════════════════════════════════════════════════════════

    async def run_full_pipeline(
        self, ctx: ProductContext, extra: dict | None = None
    ) -> list[dict]:
        """全链路: 选品上架 → 营销推广 → 售后监控"""
        extra = extra or {}
        all_decisions: list[dict] = []

        chains = [
            ("selection_listing", "选品上架链", self.run_selection_listing_chain),
            ("marketing", "营销推广链", self.run_marketing_chain),
            ("aftersales", "售后监控链", self.run_aftersales_chain),
        ]

        for chain_id, chain_name, chain_fn in chains:
            try:
                decisions = await chain_fn(ctx, extra)
                all_decisions.append({
                    "chain": chain_id,
                    "chain_name": chain_name,
                    "status": "done",
                    "steps": decisions,
                })
            except Exception as e:
                all_decisions.append({
                    "chain": chain_id,
                    "chain_name": chain_name,
                    "status": "failed",
                    "error": str(e),
                    "steps": [],
                })

        self.bus.save(ctx)
        return all_decisions

    # ═══════════════════════════════════════════════════════════
    # 内部方法
    # ═══════════════════════════════════════════════════════════

    async def _execute_domain(self, domain: str, state: dict) -> tuple[str, dict]:
        """执行单个 domain 的 workflow"""
        if domain == "selection":
            return await self._run_selection(state)
        elif domain == "listing":
            if not state.get("product_name"):
                return "Skipped: no product_name", {}
            return await self._run_listing(state)
        elif domain == "compliance":
            return await self._run_compliance(state)
        elif domain == "social":
            if not state.get("product_name"):
                return "Skipped: no product_name", {}
            return await self._run_social(state)
        elif domain == "review":
            if not state.get("product_asin"):
                state["product_asin"] = f"B{random.randint(1000000, 9999999)}{random.randint(1000000, 9999999)}"
            return await self._run_review_monitor(state)
        return f"Unknown domain: {domain}", {}

    async def _ensure_fields(self, domain: str, state: dict, extra: dict) -> dict:
        """兜底: 关键字段为空时从 extra 补充"""
        state = dict(state)
        for key in ("keywords", "features", "seller_strengths", "brand_story",
                     "image_descriptions", "platforms", "product_asin", "max_reviews"):
            if not state.get(key) and extra.get(key):
                state[key] = extra[key]
        return state

    # ── workflow runners ──────────────────────────────────────

    async def _run_selection(self, state: dict) -> tuple[str, dict]:
        from backend.app.workflows.selection_workflow import selection_workflow, SelectionState
        tid = str(uuid.uuid4())
        wf_state: SelectionState = {
            "task_id": tid, "category": state.get("category", ""),
            "keywords": state.get("keywords", []),
            "target_market": state.get("target_market", "US"),
            "seller_budget": state.get("seller_budget", "$5000-$15000"),
            "seller_strengths": state.get("seller_strengths", []),
            "category_overview": "", "trends": [], "recommended_niches": [],
            "matched_products": [], "scored_products": [], "top_pick": "",
            "raw_search_data": [], "data_source": "",
            "status": "running", "error": "", "current_step": "started",
        }
        result = await selection_workflow.ainvoke(wf_state, {"configurable": {"thread_id": tid}})
        top = result.get("top_pick", "none")
        count = len(result.get("scored_products", []))
        return f"Found {count} products, top pick: {top}", {
            "top_pick": top, "product_count": count,
            "scored_products": result.get("scored_products", []),
            "category_overview": result.get("category_overview", ""),
            "recommended_niches": result.get("recommended_niches", []),
            "trends": result.get("trends", []),
            "raw_search_data": result.get("raw_search_data", []),
            "data_source": result.get("data_source", "llm"),
        }

    async def _run_listing(self, state: dict) -> tuple[str, dict]:
        from backend.app.workflows.listing_workflow import listing_workflow, ListingState
        tid = str(uuid.uuid4())
        wf_state: ListingState = {
            "task_id": tid, "product_name": state.get("product_name", ""),
            "category": state.get("category", ""),
            "features": state.get("features", []),
            "brand_story": state.get("brand_story"),
            "image_descriptions": state.get("image_descriptions", []),
            "target_platform": state.get("target_platform", "amazon_us"),
            "target_language": state.get("target_language", "en"),
            "keywords": state.get("keywords", []),
            "top_keywords": state.get("top_keywords", []),
            "title_candidates": [], "best_title": "", "bullet_points": [],
            "description_html": "", "a_plus_modules": [], "seo_report": {},
            "status": "running", "error": "", "current_step": "started",
        }
        result = await listing_workflow.ainvoke(wf_state, {"configurable": {"thread_id": tid}})
        title = result.get("best_title", "N/A")
        data = {
            "listing_task_id": tid,
            "best_title": title,
            "keywords": result.get("keywords", []),
            "top_keywords": result.get("top_keywords", []),
            "title_candidates": result.get("title_candidates", []),
            "bullet_points": result.get("bullet_points", []),
            "description_html": result.get("description_html", ""),
            "a_plus_modules": result.get("a_plus_modules", []),
            "seo_report": result.get("seo_report", {}),
            "product_images": result.get("product_images", []),
        }
        await self._save_listing_result(tid, result, state)
        return f"Listing generated: {title[:60]}", data

    async def _run_compliance(self, state: dict) -> tuple[str, dict]:
        from backend.app.workflows.compliance_workflow import compliance_workflow, ComplianceState
        tid = str(uuid.uuid4())
        wf_state: ComplianceState = {
            "task_id": tid, "title": state.get("title", ""),
            "bullet_points": state.get("bullet_points", []),
            "description": state.get("description", ""),
            "category": state.get("category", ""),
            "product_features": state.get("product_features", []),
            "platform": state.get("platform", "amazon_us"),
            "policy_issues": [], "claim_issues": [],
            "overall_verdict": "", "risk_level": "", "total_issues": 0,
            "critical_items": [], "action_items": [], "summary": "",
            "status": "running", "error": "", "current_step": "started",
        }
        result = await compliance_workflow.ainvoke(wf_state, {"configurable": {"thread_id": tid}})
        return f"Compliance: {result.get('overall_verdict', 'N/A')}, {result.get('total_issues', 0)} issues", {
            "verdict": result.get("overall_verdict", ""),
            "risk_level": result.get("risk_level", ""),
            "total_issues": result.get("total_issues", 0),
            "policy_issues": result.get("policy_issues", []),
            "claim_issues": result.get("claim_issues", []),
            "critical_items": result.get("critical_items", []),
            "action_items": result.get("action_items", []),
        }

    async def _run_social(self, state: dict) -> tuple[str, dict]:
        from backend.app.workflows.social_workflow import social_workflow, SocialState
        tid = str(uuid.uuid4())
        wf_state: SocialState = {
            "task_id": tid, "product_name": state.get("product_name", ""),
            "category": state.get("category", ""),
            "features": state.get("features", []),
            "brand_story": state.get("brand_story", ""),
            "platforms": state.get("platforms", ["instagram", "threads", "pinterest"]),
            "language": state.get("language", "en"),
            "target_markets": state.get("target_markets", ["US"]),
            "marketing_angles": [], "target_audience": "", "content_tones": [],
            "key_selling_points": [], "visual_style": [], "hashtag_themes": [],
            "platform_requirements": [], "posts": [],
            "status": "running", "error": "", "current_step": "started",
        }
        result = await social_workflow.ainvoke(wf_state, {"configurable": {"thread_id": tid}})
        posts = result.get("posts", [])
        data = {
            "post_count": len(posts),
            "posts": [{"platform": p.get("platform", ""), "copy": p.get("copy", "")[:150],
                       "hashtags": p.get("hashtags", []),
                       "quality_score": p.get("quality_score", 0)} for p in posts],
            "marketing_angles": result.get("marketing_angles", []),
            "target_audience": result.get("target_audience", ""),
            "content_tones": result.get("content_tones", []),
            "key_selling_points": result.get("key_selling_points", []),
        }
        await self._save_social_result(tid, result, state)
        return f"Generated {len(posts)} social posts", data

    async def _run_review_monitor(self, state: dict) -> tuple[str, dict]:
        from backend.app.workflows.review_workflow import review_workflow, ReviewState
        tid = str(uuid.uuid4())
        wf_state: ReviewState = {
            "task_id": tid, "product_asin": state.get("product_asin", ""),
            "platform": state.get("platform", "amazon_us"),
            "max_reviews": state.get("max_reviews", 10),
            "language": state.get("language", "zh"),
            "reviews": [], "total_scraped": 0, "analyzed_count": 0,
            "negative_count": 0, "alert_count": 0,
            "status": "running", "error": "", "current_step": "started",
        }
        result = await review_workflow.ainvoke(wf_state, {"configurable": {"thread_id": tid}})
        alerts = result.get("alert_count", 0)
        reviews = result.get("reviews", [])
        return f"Scraped {result.get('total_scraped', 0)} reviews, {alerts} alerts", {
            "total_scraped": result.get("total_scraped", 0),
            "negative_count": result.get("negative_count", 0),
            "alert_count": alerts,
            "alerts": [{"reviewer": r.get("reviewer_name", ""),
                        "content": r.get("content", "")[:100],
                        "alert_level": r.get("alert_level", "none")}
                       for r in reviews if r.get("alert_level") in ("alert", "critical")][:5],
        }

    # ── persistence helpers ───────────────────────────────────

    async def _save_listing_result(self, task_id: str, result: dict, state: dict):
        try:
            from backend.app.core.db import async_session
            from backend.app.models.models import ListingTask
            from sqlalchemy import select
            import uuid as _uuid
            from datetime import datetime

            async with async_session() as session:
                stmt = select(ListingTask).where(ListingTask.id == _uuid.UUID(task_id))
                r = await session.execute(stmt)
                existing = r.scalar_one_or_none()

                if existing:
                    existing.keywords = result.get("keywords", []) or []
                    existing.top_keywords = result.get("top_keywords", []) or []
                    existing.title_candidates = result.get("title_candidates", []) or []
                    existing.bullet_points = result.get("bullet_points", []) or []
                    existing.description_html = result.get("description_html", "") or ""
                    existing.a_plus_modules = result.get("a_plus_modules", []) or []
                    existing.seo_report = result.get("seo_report", {}) or {}
                    existing.product_images = result.get("product_images", []) or []
                    existing.status = "awaiting_review"
                    existing.updated_at = datetime.utcnow()
                else:
                    task = ListingTask(
                        id=_uuid.UUID(task_id),
                        product_name=result.get("product_name", state.get("product_name", "")),
                        category=result.get("category", state.get("category", "")),
                        status="awaiting_review",
                        keywords=result.get("keywords", []) or [],
                        top_keywords=result.get("top_keywords", []) or [],
                        title_candidates=result.get("title_candidates", []) or [],
                        bullet_points=result.get("bullet_points", []) or [],
                        description_html=result.get("description_html", "") or "",
                        a_plus_modules=result.get("a_plus_modules", []) or [],
                        seo_report=result.get("seo_report", {}) or {},
                        product_images=result.get("product_images", []) or [],
                    )
                    session.add(task)
                await session.commit()
        except Exception:
            import traceback
            traceback.print_exc()

    async def _save_social_result(self, task_id: str, result: dict, state: dict):
        try:
            from backend.app.core.db import async_session
            from backend.app.models.models import SocialTask, SocialPost, SocialImage
            from sqlalchemy import select
            import uuid as _uuid
            from datetime import datetime

            async with async_session() as session:
                r = await session.execute(
                    select(SocialTask).where(SocialTask.id == _uuid.UUID(task_id))
                )
                existing = r.scalar_one_or_none()

                if existing:
                    existing.status = "completed"
                else:
                    s_task = SocialTask(
                        id=_uuid.UUID(task_id),
                        product_name=state.get("product_name", ""),
                        category=state.get("category", ""),
                        status="completed",
                    )
                    session.add(s_task)

                for post_data in result.get("posts", []):
                    pid = _uuid.uuid4()
                    post = SocialPost(
                        id=pid,
                        task_id=_uuid.UUID(task_id),
                        platform=post_data.get("platform", ""),
                        language=post_data.get("language", state.get("language", "en")),
                        copy=post_data.get("copy", ""),
                        short_copy=post_data.get("short_copy", ""),
                        hashtags=post_data.get("hashtags", []),
                        call_to_action=post_data.get("call_to_action", ""),
                        image_urls=[img.get("url", "") for img in post_data.get("images", [])],
                        quality_score=post_data.get("quality_score", 0.0),
                        quality_verdict=post_data.get("quality_verdict", "approved"),
                        status="generated",
                    )
                    session.add(post)
                    await session.flush()

                    for img_data in post_data.get("images", []):
                        if img_data.get("url"):
                            img = SocialImage(
                                post_id=pid,
                                url=img_data.get("url", ""),
                                alt_text=img_data.get("alt_text", img_data.get("description", "")),
                                prompt=img_data.get("prompt", img_data.get("description", "")),
                            )
                            session.add(img)

                await session.commit()
        except Exception:
            import traceback
            traceback.print_exc()
