"""
顶层调度 Agent — LLM 决策 + 内部工作流调用。

全自动化闭环:
  crontab 定时触发 → Orchestrator.auto() → 分析状态 → 决策 → 调用工作流 → 通知

不通过 HTTP 调自己，直接 import 工作流的 ainvoke。
"""

import asyncio
import json
from typing import Any

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent


class OrchestratorInput(BaseModel):
    action: str = "auto"  # auto | select_product | run_listing | check_compliance | generate_social | monitor_reviews
    context: dict = Field(default_factory=dict)


class OrchestratorAction(BaseModel):
    action: str = ""
    reason: str = ""
    status: str = "pending"  # pending | running | done | failed
    result: str = ""
    data: dict = Field(default_factory=dict)  # 完整结果数据


class OrchestratorOutput(BaseModel):
    decisions: list[OrchestratorAction] = Field(default_factory=list)
    summary: str = ""
    notifications: list[str] = Field(default_factory=list)


class OrchestratorAgent(BaseAgent[OrchestratorInput, OrchestratorOutput]):
    name = "orchestrator"
    description = "全自动化调度 Agent，LLM 决策 + 内部工作流调用"

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
            "- notify: Send WeCom notification to operations team\n"
            "- approve_and_publish: Approve listing → approve social → publish\n\n"
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
            f'Return: {{"decisions": [{{"action":"...","reason":"..."}}], '
            f'"summary": "..."}}'
        )

        return system_prompt, user_prompt

    async def run(self, input_data: OrchestratorInput, context: dict | None = None) -> OrchestratorOutput:
        system_prompt, user_prompt = self.build_prompt(input_data, context)
        raw = await self._call_llm(system_prompt, user_prompt, max_tokens=1024, temperature=0.2)
        data = self._parse_llm_json(raw)

        decisions = []
        for d in data.get("decisions", []):
            decisions.append(OrchestratorAction(
                action=d.get("action", ""),
                reason=d.get("reason", ""),
            ))

        # 执行每个决策
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
            decisions=decisions,
            summary=data.get("summary", raw[:200]),
            notifications=notifications,
        )

    async def _execute_action(self, action: str, ctx: dict) -> tuple[str, dict]:
        """执行具体的调度动作 — 直接调用内部工作流，返回 (摘要, 完整数据)"""
        if action == "select_product":
            if not ctx.get("category"):
                return "Skipped: no category", {}
            return await self._run_selection(ctx)

        elif action == "run_listing":
            if not ctx.get("product_name"):
                return "Skipped: no product_name", {}
            return await self._run_listing(ctx)

        elif action == "check_compliance":
            return await self._run_compliance(ctx)

        elif action == "generate_social":
            if not ctx.get("product_name"):
                return "Skipped: no product_name", {}
            return await self._run_social(ctx)

        elif action == "monitor_reviews":
            if not ctx.get("product_asin"):
                return "Skipped: no product_asin", {}
            return await self._run_review_monitor(ctx)

        elif action == "notify":
            return await self._send_notification(ctx)

        elif action == "approve_and_publish":
            return "auto-approved chain", {}

        return f"Unknown action: {action}", {}

    async def _run_selection(self, ctx: dict) -> tuple[str, dict]:
        try:
            from backend.app.workflows.selection_workflow import selection_workflow, SelectionState
            import uuid
            tid = str(uuid.uuid4())
            state: SelectionState = {
                "task_id": tid, "category": ctx.get("category", ""),
                "keywords": ctx.get("keywords", []), "target_market": ctx.get("target_market", "US"),
                "seller_budget": ctx.get("seller_budget", "$5000-$15000"),
                "seller_strengths": ctx.get("seller_strengths", []),
                "category_overview": "", "trends": [], "recommended_niches": [],
                "matched_products": [], "scored_products": [], "top_pick": "",
                "status": "running", "error": "", "current_step": "started",
            }
            result = await selection_workflow.ainvoke(state, {"configurable": {"thread_id": tid}})
            top = result.get("top_pick", "none")
            count = len(result.get("scored_products", []))
            return f"Found {count} products, top pick: {top}", {
                "top_pick": top, "product_count": count,
                "scored_products": result.get("scored_products", []),
                "category_overview": result.get("category_overview", ""),
            }
        except Exception as e:
            return f"Selection failed: {e}", {"error": str(e)}

    async def _run_listing(self, ctx: dict) -> tuple[str, dict]:
        try:
            from backend.app.workflows.listing_workflow import listing_workflow, ListingState
            import uuid
            tid = str(uuid.uuid4())
            state: ListingState = {
                "task_id": tid, "product_name": ctx.get("product_name", ""),
                "category": ctx.get("category", ""),
                "features": ctx.get("features", []),
                "brand_story": ctx.get("brand_story"),
                "image_descriptions": [], "target_platform": "amazon_us",
                "target_language": "en", "keywords": [], "top_keywords": [],
                "title_candidates": [], "best_title": "", "bullet_points": [],
                "description_html": "", "a_plus_modules": [], "seo_report": {},
                "status": "running", "error": "", "current_step": "started",
            }
            result = await listing_workflow.ainvoke(state, {"configurable": {"thread_id": tid}})
            title = result.get("best_title", "N/A")
            return f"Listing generated: {title[:60]}", {
                "best_title": title,
                "bullet_points": result.get("bullet_points", []),
                "seo_score": result.get("seo_report", {}).get("overall_score", 0),
            }
        except Exception as e:
            return f"Listing failed: {e}", {"error": str(e)}

    async def _run_compliance(self, ctx: dict) -> tuple[str, dict]:
        try:
            from backend.app.workflows.compliance_workflow import compliance_workflow, ComplianceState
            import uuid
            tid = str(uuid.uuid4())
            state: ComplianceState = {
                "task_id": tid, "title": ctx.get("title", ""),
                "bullet_points": ctx.get("bullet_points", []),
                "description": ctx.get("description", ""),
                "category": ctx.get("category", ""),
                "product_features": ctx.get("features", []),
                "platform": "amazon_us", "policy_issues": [], "claim_issues": [],
                "overall_verdict": "", "risk_level": "", "total_issues": 0,
                "critical_items": [], "action_items": [], "summary": "",
                "status": "running", "error": "", "current_step": "started",
            }
            result = await compliance_workflow.ainvoke(state, {"configurable": {"thread_id": tid}})
            return f"Compliance: {result.get('overall_verdict', 'N/A')}, {result.get('total_issues', 0)} issues", {
                "verdict": result.get("overall_verdict", ""),
                "risk_level": result.get("risk_level", ""),
                "total_issues": result.get("total_issues", 0),
                "critical_items": result.get("critical_items", []),
                "action_items": result.get("action_items", []),
            }
        except Exception as e:
            return f"Compliance failed: {e}", {"error": str(e)}

    async def _run_social(self, ctx: dict) -> tuple[str, dict]:
        try:
            from backend.app.workflows.social_workflow import social_workflow, SocialState
            import uuid
            tid = str(uuid.uuid4())
            state: SocialState = {
                "task_id": tid, "product_name": ctx.get("product_name", ""),
                "category": ctx.get("category", ""),
                "features": ctx.get("features", []),
                "brand_story": ctx.get("brand_story", ""),
                "platforms": ctx.get("platforms", ["instagram", "threads", "pinterest"]),
                "language": ctx.get("language", "en"),
                "target_markets": ctx.get("target_markets", ["US"]),
                "marketing_angles": [], "target_audience": "", "content_tones": [],
                "key_selling_points": [], "visual_style": [], "hashtag_themes": [],
                "platform_requirements": [], "posts": [],
                "status": "running", "error": "", "current_step": "started",
            }
            result = await social_workflow.ainvoke(state, {"configurable": {"thread_id": tid}})
            posts = result.get("posts", [])
            return f"Generated {len(posts)} social posts", {
                "post_count": len(posts),
                "posts": [{"platform": p.get("platform", ""), "copy": p.get("copy", "")[:150],
                           "hashtags": p.get("hashtags", []), "quality_score": p.get("quality_score", 0)}
                          for p in posts],
            }
        except Exception as e:
            return f"Social failed: {e}", {"error": str(e)}

    async def _run_review_monitor(self, ctx: dict) -> tuple[str, dict]:
        try:
            from backend.app.workflows.review_workflow import review_workflow, ReviewState
            import uuid
            tid = str(uuid.uuid4())
            state: ReviewState = {
                "task_id": tid, "product_asin": ctx.get("product_asin", ""),
                "platform": "amazon_us", "max_reviews": 15, "language": "zh",
                "reviews": [], "total_scraped": 0, "analyzed_count": 0,
                "negative_count": 0, "alert_count": 0,
                "status": "running", "error": "", "current_step": "started",
            }
            result = await review_workflow.ainvoke(state, {"configurable": {"thread_id": tid}})
            alerts = result.get("alert_count", 0)
            if alerts > 0:
                await self._send_notification({"message": f"评论监控预警: {alerts} 条负面预警，请及时处理"})
            reviews = result.get("reviews", [])
            return f"Reviews: {result.get('total_scraped', 0)} scraped, {alerts} alerts", {
                "total_scraped": result.get("total_scraped", 0),
                "negative_count": result.get("negative_count", 0),
                "alert_count": alerts,
                "alerts": [{"reviewer": r.get("reviewer_name", ""), "content": r.get("content", "")[:100],
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
