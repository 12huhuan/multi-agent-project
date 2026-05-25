"""
路由 Agent — 自然语言理解 + 意图识别 + 链路分发。

用户输入一句话，LLM 分析意图，决定走哪条链路，提取参数，
然后交给 ChainExecutor 执行。

与旧 OrchestratorAgent 的区别:
  - 入口是自然语言，不是 action + context dict
  - LLM 真正参与路由决策，不是 hardcode if/elif
  - 支持 3 条链路 + 全链路调度，新增链路只需注册
"""

import json
from typing import Any

from pydantic import BaseModel, Field

from backend.app.agents.base import BaseAgent
from backend.app.core.context_bus import ContextBus, ProductContext
from backend.app.agents.router.chain_executor import ChainExecutor


# ── 路由决策数据模型 ────────────────────────────────

class RouteDecision(BaseModel):
    """LLM 路由决策"""
    chain: str = Field(
        default="",
        description="selection_listing | marketing | aftersales | full_pipeline | clarify",
    )
    params: dict = Field(
        default_factory=dict,
        description="提取的参数: category, target_market, platforms, product_asin, ...",
    )
    reasoning: str = Field(default="", description="路由原因(中文)")
    confidence: float = Field(default=1.0, description="置信度 0-1")


class RouterInput(BaseModel):
    message: str = ""
    context: dict = Field(default_factory=dict)


class RouterOutput(BaseModel):
    decision: RouteDecision = Field(default_factory=RouteDecision)
    chain_result: list[dict] = Field(default_factory=list)
    summary: str = ""


# ── 链路注册表 ─────────────────────────────────────

CHAIN_REGISTRY: dict[str, dict[str, Any]] = {
    "selection_listing": {
        "name": "选品上架链",
        "description": "市场分析 → 选品评分 → Listing生成 → 合规审查",
        "keywords": ["选品", "上架", "listing", "市场分析", "产品分析", "合规", "新品",
                     "卖什么", "好不好做", "选品机会", "分析一下", "调研"],
        "needs_params": ["category"],
        "optional_params": ["target_market", "brand_name", "seller_budget"],
        "examples": [
            "帮我在美国市场分析一下蓝牙耳机",
            "蓝牙耳机 美国市场 选品",
            "帮我看看瑜伽垫在德国好不好做",
            "厨房用品选品分析，目标市场日本",
        ],
    },
    "marketing": {
        "name": "营销推广链",
        "description": "社媒内容生成(Instagram/TikTok/小红书等6平台)",
        "keywords": ["营销", "推广", "社媒", "内容", "帖子", "instagram", "tiktok",
                     "小红书", "宣传", "广告文案", "发帖", "social media"],
        "needs_params": ["product_name", "category"],
        "optional_params": ["platforms", "language"],
        "examples": [
            "给我的蓝牙耳机产品生成Instagram营销内容",
            "帮我在TikTok和小红书上推广瑜伽垫",
            "厨房用具的社媒推广内容",
        ],
    },
    "aftersales": {
        "name": "售后监控链",
        "description": "评论抓取 → 情感分析 → 翻译 → 负面预警 → 回复建议",
        "keywords": ["评论", "评价", "差评", "售后", "监控", "review", "feedback",
                     "预警", "回复", "客户反馈", "评分"],
        "needs_params": [],
        "optional_params": ["product_asin", "category", "max_reviews"],
        "examples": [
            "监控ASIN B0XXXXX的差评",
            "帮我看看蓝牙耳机的客户评论情况",
            "检查一下我们产品的负面评价",
        ],
    },
    "full_pipeline": {
        "name": "全链路调度",
        "description": "选品上架 → 营销推广 → 售后监控，一站式全流程",
        "keywords": ["全流程", "全链路", "全部", "完整", "一条龙", "从零开始",
                     "从选品到", "全套", "端到端", "一条龙", "整套"],
        "needs_params": ["category"],
        "optional_params": ["target_market", "brand_name"],
        "examples": [
            "帮我做蓝牙耳机的完整运营流程",
            "从头到尾帮我跑一遍瑜伽垫的全流程",
            "厨房用品的全套运营方案",
        ],
    },
}


# ── RouterAgent ─────────────────────────────────────

class RouterAgent(BaseAgent[RouterInput, RouterOutput]):
    name = "router"
    description = "自然语言路由 Agent — NL输入 → 意图识别 → 链路分发"

    def __init__(self, bus: ContextBus | None = None):
        super().__init__()
        self.bus = bus or ContextBus()
        self.executor = ChainExecutor(bus=self.bus)

    def build_prompt(
        self, input_data: RouterInput, context: dict | None = None
    ) -> tuple[str, str]:
        # 构建链路描述
        chain_descriptions = []
        for chain_id, info in CHAIN_REGISTRY.items():
            examples = "\n".join(f"    - \"{e}\"" for e in info["examples"])
            chain_descriptions.append(
                f"### {chain_id} ({info['name']})\n"
                f"  {info['description']}\n"
                f"  必需参数: {info['needs_params']}\n"
                f"  可选参数: {info['optional_params']}\n"
                f"  示例:\n{examples}\n"
            )

        system_prompt = (
            "You are an intelligent routing agent for a cross-border e-commerce AI operations platform.\n"
            "Your job: analyze the seller's natural language request and determine which workflow chain to execute.\n\n"
            "## Available Chains\n\n"
            f"{''.join(chain_descriptions)}\n"
            "## Routing Rules\n"
            "1. If the user mentions keywords like \"选品/上架/listing/市场分析/卖什么\", "
            "route to `selection_listing`\n"
            "2. If the user mentions keywords like \"营销/推广/社媒/Instagram/TikTok/发帖\", "
            "route to `marketing`\n"
            "3. If the user mentions keywords like \"评论/差评/售后/监控/review/预警\", "
            "route to `aftersales`\n"
            "4. If the user asks for a complete process (全流程/从零开始/一条龙/全套), "
            "route to `full_pipeline`\n"
            "5. If the user's intent is unclear or missing required info, route to `clarify`\n"
            "6. If the user only says a category name (e.g. \"蓝牙耳机\"), "
            "default to `selection_listing` (选品分析是第一步)\n\n"
            "## Parameter Extraction\n"
            "- category: product category in English or Chinese\n"
            "- target_market: target country/market (US, DE, JP, etc.)\n"
            "- brand_name: brand name if mentioned\n"
            "- platforms: list of social platforms mentioned\n"
            "- product_asin: Amazon ASIN if provided\n"
            "- language: content language preference\n\n"
            "## Output Format\n"
            'Return ONLY a JSON object (no markdown, no extra text):\n'
            '{"chain": "<chain_id>", "params": {...}, "reasoning": "<Chinese>", "confidence": 0.0-1.0}'
        )

        user_prompt = f"User request: {input_data.message}"

        if input_data.context:
            user_prompt += f"\nAdditional context: {json.dumps(input_data.context, ensure_ascii=False)}"

        user_prompt += "\n\nAnalyze and return JSON:"

        return system_prompt, user_prompt

    async def run(
        self, input_data: RouterInput, context: dict | None = None
    ) -> RouterOutput:
        """NL输入 → 路由决策 → 执行链路"""
        # Step 1: LLM 意图识别
        system_prompt, user_prompt = self.build_prompt(input_data, context)
        raw = await self._call_llm(system_prompt, user_prompt, max_tokens=512, temperature=0.2)
        data = self._parse_llm_json(raw)

        decision = RouteDecision(
            chain=data.get("chain", "clarify"),
            params=data.get("params", {}),
            reasoning=data.get("reasoning", raw[:100]),
            confidence=data.get("confidence", 0.5),
        )

        # Step 2: 如果是 clarify，直接返回
        if decision.chain == "clarify":
            return RouterOutput(
                decision=decision,
                chain_result=[],
                summary="需要更多信息：" + decision.reasoning,
            )

        # Step 3: 创建 ProductContext
        params = decision.params
        ctx = self.bus.create(
            category=params.get("category", ""),
            target_market=params.get("target_market", "US"),
            brand_name=params.get("brand_name"),
            seller_budget=params.get("seller_budget", "$5000-$15000"),
        )
        if params.get("platforms"):
            ctx.identity.platforms = params["platforms"]
        if params.get("language"):
            ctx.identity.language = params["language"]

        # LLM 补充关键词
        extra = dict(params)
        if params.get("category") and not extra.get("keywords"):
            try:
                from backend.app.agents.shared.amazon_keywords import get_fetcher
                fetcher = get_fetcher()
                results = await fetcher.fetch_deep(params["category"], max_results=15, translate_fn=None)
                if results:
                    extra["keywords"] = [r["keyword"] for r in results[:15]]
            except Exception:
                pass
        if not extra.get("keywords"):
            extra["keywords"] = await self._generate_keywords(params.get("category", ""))
        if not extra.get("seller_strengths"):
            extra["seller_strengths"] = await self._generate_strengths(params.get("category", ""))

        ctx.market_insight.competitor_keywords = extra.get("keywords", [])

        # Step 4: 执行对应链路
        chain_result: list[dict] = []
        try:
            if decision.chain == "selection_listing":
                chain_result = await self.executor.run_selection_listing_chain(ctx, extra)
            elif decision.chain == "marketing":
                chain_result = await self.executor.run_marketing_chain(ctx, extra)
            elif decision.chain == "aftersales":
                chain_result = await self.executor.run_aftersales_chain(ctx, extra)
            elif decision.chain == "full_pipeline":
                chain_result = await self.executor.run_full_pipeline(ctx, extra)
            else:
                return RouterOutput(
                    decision=decision,
                    chain_result=[],
                    summary=f"Unknown chain: {decision.chain}",
                )
        except Exception as e:
            return RouterOutput(
                decision=decision,
                chain_result=[{"error": str(e)}],
                summary=f"执行失败: {e}",
            )

        # Step 5: 汇总结果
        done = sum(
            1 for d in chain_result
            if isinstance(d, dict) and d.get("status") == "done"
        )
        return RouterOutput(
            decision=decision,
            chain_result=chain_result,
            summary=f"[{decision.chain}] {len(chain_result)} steps, {done} done — {decision.reasoning}",
        )

    # ── LLM 辅助方法 ──────────────────────────────────

    async def _generate_keywords(self, category: str) -> list[str]:
        if not category:
            return []
        try:
            system_prompt = (
                "You are an Amazon SEO expert. Given a product category, "
                "output the top 10 search keywords as a JSON array of strings."
            )
            raw = await self._call_llm(
                system_prompt,
                f"Category: {category}\nOutput: JSON array of 10 keyword strings.",
                max_tokens=256, temperature=0.7,
            )
            data = self._parse_llm_json(raw)
            if isinstance(data, list):
                return data[:15]
        except Exception:
            pass
        return [category, f"best {category}", f"premium {category}"]

    async def _generate_strengths(self, category: str) -> list[str]:
        if not category:
            return []
        try:
            system_prompt = (
                "You are an Amazon seller consultant. List 3-5 competitive strengths "
                "as a JSON array of strings."
            )
            raw = await self._call_llm(
                system_prompt,
                f"Category: {category}\nOutput: JSON array of 3-5 strings.",
                max_tokens=128, temperature=0.7,
            )
            data = self._parse_llm_json(raw)
            if isinstance(data, list):
                return data[:5]
        except Exception:
            pass
        return ["Competitive pricing", "Fast global shipping", "Quality materials"]
