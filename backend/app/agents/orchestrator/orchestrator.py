"""
顶层调度 Agent — LLM 决策 + 内部工作流调用。

v2: 使用 ContextBus 替代手动 dict 传递。
    数据流向: ProductContext → derive → Workflow State → ingest → ProductContext
    消除了 _auto_fill_context 的手工映射和重复 LLM 生成。
"""

import asyncio
import json
import random
from typing import Any

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent
from backend.app.core.context_bus import (
    ProductContext, MarketInsight, ContextBus,
)


class OrchestratorInput(BaseModel):
    action: str = "auto"
    context: dict = Field(default_factory=dict)


class OrchestratorAction(BaseModel):
    action: str = ""
    reason: str = ""
    status: str = "pending"
    result: str = ""
    data: dict = Field(default_factory=dict)


class OrchestratorOutput(BaseModel):
    decisions: list[OrchestratorAction] = Field(default_factory=list)
    summary: str = ""
    notifications: list[str] = Field(default_factory=list)


class OrchestratorAgent(BaseAgent[OrchestratorInput, OrchestratorOutput]):
    name = "orchestrator"
    description = "全自动化调度 Agent — v2 ContextBus 驱动"

    def __init__(self, bus: ContextBus | None = None):
        super().__init__()
        self.bus = bus or ContextBus()

    def build_prompt(self, input_data: OrchestratorInput, context: dict | None = None) -> tuple[str, str]:
        system_prompt = (
            "You are an operations orchestrator for a cross-border e-commerce automation system. "
            "Decide what actions to take based on the current state.\n\n"
            "Available actions:\n"
            "- select_product: Run product selection analysis for a category. Needs: category, keywords, budget\n"
            "- run_listing: Optimize a product listing. Needs: product_name, category, features\n"
            "- check_compliance: Review listing compliance. Auto-triggered after listing\n"
            "- generate_social: Generate social media content. Needs: product_name, category, features\n"
            "- monitor_reviews: Scrape and analyze reviews. Needs: product_asin\n"
            "- notify: Send WeCom notification to operations team\n\n"
            "Decision rules:\n"
            "- If new product/category: select_product → if score>7: run_listing → check_compliance → generate_social\n"
            "- If review alerts: notify ops team\n"
            "- If listing awaiting_review: approve if score>7\n"
            "- If social approved: publish\n\n"
            "Output your decisions as a JSON array of actions."
        )

        ctx_str = json.dumps(input_data.context, ensure_ascii=False) if input_data.context else "auto-mode: scan status"
        user_prompt = (
            f"Requested action: {input_data.action}\n"
            f"Context: {ctx_str}\n\n"
            f'Return: {{"decisions": [{{"action":"...","reason":"..."}}], "summary": "..."}}'
        )
        return system_prompt, user_prompt

    async def run(self, input_data: OrchestratorInput, context: dict | None = None) -> OrchestratorOutput:
        if input_data.action == "auto":
            return await self._run_full_pipeline(input_data.context)

        system_prompt, user_prompt = self.build_prompt(input_data, context)
        raw = await self._call_llm(system_prompt, user_prompt, max_tokens=1024, temperature=0.2)
        data = self._parse_llm_json(raw)

        decisions = []
        for d in data.get("decisions", []):
            decisions.append(OrchestratorAction(
                action=d.get("action", ""), reason=d.get("reason", ""),
            ))

        notifications = []
        for dec in decisions:
            try:
                result, data = await self._execute_action(dec.action, input_data.context)
                dec.status = "done"
                dec.result = str(result)[:300]
                dec.data = data or {}
                if dec.action == "notify":
                    notifications.append(str(result))
            except Exception as e:
                dec.status = "failed"
                dec.result = str(e)[:200]

        return OrchestratorOutput(
            decisions=decisions, summary=data.get("summary", raw[:200]),
            notifications=notifications,
        )

    # ── ContextBus 驱动的全流程 ─────────────────────────────

    async def _run_full_pipeline(self, input_ctx: dict) -> OrchestratorOutput:
        """自动模式: 使用 ContextBus 驱动全流程"""
        decisions = []
        notifications = []
        input_ctx = dict(input_ctx)

        # 创建或恢复 ProductContext
        category = input_ctx.get("category", "")
        ctx = self.bus.create(
            category=category,
            target_market=input_ctx.get("target_market", "US"),
            seller_budget=input_ctx.get("seller_budget", "$5000-$15000"),
            brand_name=input_ctx.get("brand_name"),
        )

        # 补充 keywords / strengths（LLM 生成，仅当缺失）
        if category and not input_ctx.get("keywords"):
            input_ctx["keywords"] = await self._generate_keywords(category)
        if category and not input_ctx.get("seller_strengths"):
            input_ctx["seller_strengths"] = await self._generate_strengths(category)

        ctx.identity.seller_strengths = input_ctx.get("seller_strengths", [])
        # 把 Amazon 热词注入 ProductContext，Listing 工作流直接复用
        if input_ctx.get("keywords") and not ctx.market_insight.competitor_keywords:
            ctx.market_insight.competitor_keywords = input_ctx["keywords"]

        pipeline = [
            ("selection", "select_product", "Step 1/5: 智能选品"),
            ("listing", "run_listing", "Step 2/5: Listing优化"),
            ("compliance", "check_compliance", "Step 3/5: 合规审查"),
            ("social", "generate_social", "Step 4/5: 社媒内容"),
            ("review", "monitor_reviews", "Step 5/5: 评论监控"),
        ]

        for domain, action, reason in pipeline:
            dec = OrchestratorAction(action=action, reason=reason)
            try:
                # 1. derive: ProductContext → workflow state（零 LLM）
                state = self.bus.derive(domain, ctx)

                # 2. 缺失字段兜底 — LLM 按需生成（仅 state 中值为空时触发）
                state = await self._ensure_state_fields(domain, state, input_ctx)

                # 3. 执行 workflow
                result, data = await self._execute_with_state(domain, state)

                # 4. ingest: workflow result → ProductContext
                ctx = await self.bus.ingest(domain, data, ctx)

                dec.status = "done"
                dec.result = str(result)[:300]
                dec.data = data or {}
            except Exception as e:
                dec.status = "failed"
                dec.result = str(e)[:200]
            decisions.append(dec)

        # 保存上下文到磁盘
        self.bus.save(ctx)

        return OrchestratorOutput(
            decisions=decisions,
            summary=f"Pipeline: {sum(1 for d in decisions if d.status=='done')}/{len(decisions)} done",
            notifications=notifications,
        )

    async def _ensure_state_fields(self, domain: str, state: dict, input_ctx: dict) -> dict:
        """兜底: state 中关键字段为空时，通过 LLM 生成补充"""
        state = dict(state)

        if domain == "selection":
            if not state.get("keywords"):
                state["keywords"] = input_ctx.get("keywords", [])
            if not state.get("seller_strengths"):
                state["seller_strengths"] = input_ctx.get("seller_strengths", [])

        elif domain == "listing":
            if not state.get("product_name"):
                return state  # 没有产品名无法生成
            if not state.get("features"):
                state["features"] = await self._generate_features(
                    state["product_name"], state.get("category", "")
                )
            if not state.get("brand_story"):
                state["brand_story"] = await self._generate_brand_story(
                    state["product_name"], state.get("category", "")
                )

        elif domain == "social":
            if not state.get("features") and state.get("product_name"):
                state["features"] = await self._generate_features(
                    state["product_name"], state.get("category", "")
                )

        return state

    async def _execute_with_state(self, domain: str, state: dict) -> tuple[str, dict]:
        """使用预构建的 state dict 执行 workflow"""
        if domain == "selection":
            return await self._run_selection(state)
        elif domain == "listing":
            if not state.get("product_name"):
                return "Skipped: no product_name — needs selection first", {}
            return await self._run_listing(state)
        elif domain == "compliance":
            return await self._run_compliance(state)
        elif domain == "social":
            if not state.get("product_name"):
                return "Skipped: no product_name — needs listing first", {}
            return await self._run_social(state)
        elif domain == "review":
            if not state.get("product_asin"):
                state["product_asin"] = f"B{random.randint(1000000, 9999999)}{random.randint(1000000, 9999999)}"
            return await self._run_review_monitor(state)
        return f"Unknown domain: {domain}", {}

    # ── 兼容旧 API 的 _execute_action ────────────────────────

    async def _execute_action(self, action: str, ctx: dict) -> tuple[str, dict]:
        """兼容旧有单步调用的 API 入口"""
        ctx = dict(ctx)

        if action == "select_product":
            if not ctx.get("category"):
                return "Skipped: no category provided", {}
            return await self._run_selection(ctx)

        elif action == "run_listing":
            if not ctx.get("product_name"):
                return "Skipped: no product_name — needs selection first", {}
            return await self._run_listing(ctx)

        elif action == "check_compliance":
            return await self._run_compliance(ctx)

        elif action == "generate_social":
            if not ctx.get("product_name"):
                return "Skipped: no product_name — needs listing first", {}
            return await self._run_social(ctx)

        elif action == "monitor_reviews":
            if not ctx.get("product_asin"):
                ctx["product_asin"] = f"B{random.randint(1000000, 9999999)}{random.randint(1000000, 9999999)}"
            return await self._run_review_monitor(ctx)

        elif action == "notify":
            return await self._send_notification(ctx)

        elif action == "approve_and_publish":
            return "auto-approved chain", {}

        return f"Unknown action: {action}", {}

    # ── LLM 按需生成辅助方法 ──────────────────────────────

    async def _generate_keywords(self, category: str) -> list[str]:
        # Step 1: 从 Amazon Autocomplete 获取真实热词（免费，无需 API Key）
        try:
            from backend.app.agents.shared.amazon_keywords import get_fetcher
            fetcher = get_fetcher()

            # 中文输入 → LLM 快速翻译为英文（Amazon US 只支持英文搜索）
            async def translate(text: str) -> str:
                try:
                    sp = "Translate the following Chinese product category to English. Output ONLY the English phrase, nothing else."
                    up = f"Category: {text}"
                    en = await self._call_llm(sp, up, max_tokens=64, temperature=0.1)
                    return en.strip(' "\n')
                except Exception:
                    return text

            results = await fetcher.fetch_deep(category, max_results=15, translate_fn=translate)
            if results:
                keywords = [r["keyword"] for r in results]
                return keywords[:15]
        except Exception:
            pass

        # Step 2: 回退到 LLM 生成
        try:
            system_prompt = "You are an Amazon SEO expert. Given a product category, output the top 10 search keywords as a JSON array of strings. Keep keywords short (1-3 words)."
            user_prompt = f"Category: {category}\nOutput: JSON array of 10 keyword strings."
            raw = await self._call_llm(system_prompt, user_prompt, max_tokens=256, temperature=0.7)
            data = self._parse_llm_json(raw)
            if isinstance(data, list) and len(data) > 0:
                return data[:15]
        except Exception:
            pass
        cat = category.lower()
        return [cat, f"best {cat}", f"{cat} professional", f"premium {cat}",
                f"{cat} wireless", f"{cat} bluetooth", f"cheap {cat}",
                f"{cat} high quality", f"{cat} for sale"]

    async def _generate_strengths(self, category: str) -> list[str]:
        try:
            system_prompt = "You are an Amazon seller consultant. Given a product category, list 3-5 competitive strengths as a JSON array of strings."
            user_prompt = f"Category: {category}\nOutput: JSON array of 3-5 strings."
            raw = await self._call_llm(system_prompt, user_prompt, max_tokens=128, temperature=0.7)
            data = self._parse_llm_json(raw)
            if isinstance(data, list) and len(data) > 0:
                return data[:5]
        except Exception:
            pass
        return ["Competitive pricing", "Fast global shipping", "Quality materials",
                "Responsive customer service", "Professional packaging"]

    async def _generate_features(self, product_name: str, category: str = "") -> list[str]:
        try:
            system_prompt = "You are a product manager writing Amazon listing features. Given a product name, list 5 key features as a JSON array of strings. Each should be a complete phrase."
            user_prompt = f"Product: {product_name}\nCategory: {category}\nOutput: JSON array of 5 strings."
            raw = await self._call_llm(system_prompt, user_prompt, max_tokens=256, temperature=0.7)
            data = self._parse_llm_json(raw)
            if isinstance(data, list) and len(data) > 0:
                return data[:8]
        except Exception:
            pass
        return ["Premium quality materials", "Ergonomic design", "Easy to use",
                "Durable and long-lasting", "Eco-friendly packaging"]

    async def _generate_brand_story(self, product_name: str, category: str = "") -> str:
        try:
            system_prompt = "You are a brand copywriter. Given a product, write a 1-2 sentence authentic brand story. Output just the text."
            user_prompt = f"Product: {product_name}\nCategory: {category}\nOutput: brand story."
            raw = await self._call_llm(system_prompt, user_prompt, max_tokens=128, temperature=0.8)
            return raw.strip(' "\n')
        except Exception:
            pass
        return f"Born from a passion for quality {category or 'products'}, we craft premium solutions that enhance everyday life."

    # ── 工作流执行器 ───────────────────────────────────────

    async def _run_selection(self, state: dict) -> tuple[str, dict]:
        try:
            from backend.app.workflows.selection_workflow import selection_workflow, SelectionState
            import uuid
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
            return f"Found {count} products, top pick: {top} [{result.get('data_source', 'llm')}]", {
                "top_pick": top, "product_count": count,
                "scored_products": result.get("scored_products", []),
                "category_overview": result.get("category_overview", ""),
                "recommended_niches": result.get("recommended_niches", []),
                "trends": result.get("trends", []),
                "raw_search_data": result.get("raw_search_data", []),
                "data_source": result.get("data_source", "llm"),
            }
        except Exception as e:
            return f"Selection failed: {e}", {"error": str(e)}

    async def _run_listing(self, state: dict) -> tuple[str, dict]:
        try:
            from backend.app.workflows.listing_workflow import listing_workflow, ListingState
            import uuid
            tid = str(uuid.uuid4())
            wf_state: ListingState = {
                "task_id": tid, "product_name": state.get("product_name", ""),
                "category": state.get("category", ""),
                "features": state.get("features", []),
                "brand_story": state.get("brand_story"),
                "image_descriptions": [], "target_platform": state.get("target_platform", "amazon_us"),
                "target_language": state.get("target_language", "en"),
                "keywords": state.get("keywords", []),
                "top_keywords": state.get("top_keywords", []),
                "title_candidates": [], "best_title": "", "bullet_points": [],
                "description_html": "", "a_plus_modules": [], "seo_report": {},
                "status": "running", "error": "", "current_step": "started",
            }
            result = await listing_workflow.ainvoke(wf_state, {"configurable": {"thread_id": tid}})
            title = result.get("best_title", "N/A")
            return f"Listing generated: {title[:60]}", {
                "best_title": title,
                "keywords": result.get("keywords", []),
                "top_keywords": result.get("top_keywords", []),
                "title_candidates": result.get("title_candidates", []),
                "bullet_points": result.get("bullet_points", []),
                "description_html": result.get("description_html", ""),
                "a_plus_modules": result.get("a_plus_modules", []),
                "seo_report": result.get("seo_report", {}),
            }
        except Exception as e:
            return f"Listing failed: {e}", {"error": str(e)}

    async def _run_compliance(self, state: dict) -> tuple[str, dict]:
        try:
            from backend.app.workflows.compliance_workflow import compliance_workflow, ComplianceState
            import uuid
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
        except Exception as e:
            return f"Compliance failed: {e}", {"error": str(e)}

    async def _run_social(self, state: dict) -> tuple[str, dict]:
        try:
            from backend.app.workflows.social_workflow import social_workflow, SocialState
            import uuid
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
            return f"Generated {len(posts)} social posts", {
                "post_count": len(posts),
                "posts": [{"platform": p.get("platform", ""), "copy": p.get("copy", "")[:150],
                           "hashtags": p.get("hashtags", []),
                           "quality_score": p.get("quality_score", 0)} for p in posts],
                "marketing_angles": result.get("marketing_angles", []),
                "target_audience": result.get("target_audience", ""),
                "content_tones": result.get("content_tones", []),
                "key_selling_points": result.get("key_selling_points", []),
            }
        except Exception as e:
            return f"Social failed: {e}", {"error": str(e)}

    async def _run_review_monitor(self, state: dict) -> tuple[str, dict]:
        try:
            from backend.app.workflows.review_workflow import review_workflow, ReviewState
            import uuid
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
            if alerts > 0:
                await self._send_notification({"message": f"评论监控预警: {alerts} 条负面预警"})
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
        except Exception as e:
            return f"Review monitor failed: {e}", {"error": str(e)}

    async def _send_notification(self, ctx: dict) -> tuple[str, dict]:
        msg = ctx.get("message", ctx.get("summary", "自动化系统通知"))
        try:
            ok = await send_wecom_message(msg)
            return f"WeCom{' sent' if ok else ' unavailable'}", {"sent": ok}
        except Exception:
            return "WeCom unavailable", {"sent": False}


try:
    from backend.app.core.wecom import send_wecom_message
except ImportError:
    async def send_wecom_message(msg: str) -> bool:
        print(f"[WeCom] {msg}")
        return True
