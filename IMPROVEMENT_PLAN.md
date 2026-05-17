# 跨境电商多 Agent 系统 — 改进方案文档

## 目录

1. [项目现状与核心问题](#1-项目现状与核心问题)
2. [改进一：上下文总线](#2-改进一上下文总线)
3. [改进二：执行网关](#3-改进二执行网关)
4. [改进三：批量上架与并发控制](#4-改进三批量上架与并发控制)
5. [改进四：Listing 去重机制](#5-改进四listing-去重机制)
6. [改进五：UGC 素材利用](#6-改进五ugc-素材利用)
7. [改进六：前端整合与管线视图](#7-改进六前端整合与管线视图)
8. [实施路线图](#8-实施路线图)
9. [总结](#9-总结)

---

## 1. 项目现状与核心问题

### 1.1 项目概述

本系统是一个跨境电商全自动化多 Agent 系统，涵盖 7 个业务域、22 个 Agent、10 个前端页面。核心目标是将卖家从选品到售后的一整条运营链路自动化。

### 1.2 核心问题诊断

当前系统存在一个根本性架构假设的错位：**每个环节被设计为可被 AI 独立完成，人是最后的审批者**。但实际跨境电商运营中，**人是决策者，AI 是辅助工具**。这一错位导致了四个结构性问题：

#### 问题一：上下文断裂 — 数据在各模块间无法自动流转

`orchestrator.py` 的 `_run_full_pipeline` 是整个系统的调度中枢，但其上下文传递机制存在三个缺陷：

- **数据被重复生成**：selection 已分析过产品特征，但 listing 阶段用 `_generate_features()` 重新生成，两次 LLM 调用无关联，可能产生矛盾。
- **ctx 是无类型 dict**：字段靠字符串硬编码（`pipeline_ctx["product_name"] = data["top_pick"]`），拼写错误静默丢数据。
- **映射逻辑硬编码在 orchestrator 里**：每加一个 workflow 就多一段 `if action == "xxx"` 的手动映射，最终变为巨型 if-else。

```python
# 现状 — 数据传递靠逐行手工赋值
if action == "select_product" and data.get("top_pick"):
    pipeline_ctx["product_name"] = data["top_pick"]

if action == "run_listing":
    if data.get("best_title"):
        pipeline_ctx["title"] = data["best_title"]
        pipeline_ctx["best_title"] = data["best_title"]

# _auto_fill_context 在缺失时额外调 LLM 补数据
if not ctx.get("features") and ctx.get("product_name"):
    ctx["features"] = await self._generate_features(...)   # 又是一次 LLM
```

#### 问题二：执行断桥 — 没有发布能力，上下游行不成闭环

系统生成了 Listing 内容，但没有调用 Amazon SP-API 去真正创建商品。评论监控需要 ASIN，而 ASIN 只存在于真实发布之后。广告模块全部使用 mock 数据。系统是"内容生产线"，缺少"执行层"。

```text
现状: 选品 → Listing生成 → 合规审查 → 社媒内容 → ❌ 断
                                                   ↓ 没有 ASIN
                                        评论监控 ← 无数据源（mock ASIN）
                                        广告分析 ← 无数据源（mock 数据）
```

#### 问题三：单产品架构 — 无法支持批量上架

一个品类下 5 种颜色 × 3 种尺码 = 15 个 SKU。当前每次只能处理一个产品，没有品类模板复用、变体批量生成、并发控制能力。

#### 问题四：前端平铺 — 11 个页面无层次，用户不知从哪开始

侧边栏把所有功能平铺展示，模块之间的上下游关系（选品→Listing→合规→社媒）对用户不可见。

---

## 2. 改进一：上下文总线

### 2.1 做什么

在 orchestrator 和各 workflow 之间增加一层 **Context Bus**，使数据在各模块间像水流一样自动找路。每个模块只关心自己的输入输出，不关心上游输出长什么样。

### 2.2 架构

上下文总线由三部分组成：

```
┌──────────────────────────────────────────────────┐
│                   ContextBus                     │
│  (运行时管理器：持久化、版本追踪、HITL 恢复)        │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │              ProductContext                 │  │
│  │  (唯一的真相来源 — Pydantic 强类型模型)       │  │
│  │                                            │  │
│  │  ProductIdentity (种子数据)                  │  │
│  │  MarketInsight   (选品产出)                  │  │
│  │  ListingContent  (Listing 产出)             │  │
│  │  ComplianceReport(合规产出)                  │  │
│  │  SocialContent   (社媒产出)                  │  │
│  │  PlatformState   (执行网关产出)              │  │
│  │  ReviewSnapshot  (评论产出)                  │  │
│  │  AdSnapshot      (广告产出)                  │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │              ContextMapper                  │  │
│  │  (双向翻译：ProductContext ↔ Workflow I/O)   │  │
│  │                                            │  │
│  │  SelectionMapper    ComplianceMapper        │  │
│  │  ListingMapper      SocialMapper            │  │
│  │  ReviewMapper       AdsMapper               │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

### 2.3 ProductContext 字段设计

```python
class ProductIdentity(BaseModel):
    """种子数据 — 用户最少只需填 2 个字段"""
    product_id: str
    category: str                         # 必填：品类
    subcategory: str | None
    brand_name: str | None
    brand_story: str | None
    target_market: str = "US"             # 必填：目标市场
    language: str = "en"
    seller_budget: str = "$5000-$15000"
    seller_strengths: list[str] = []
    platforms: list[str] = []             # 社媒平台选择

class MarketInsight(BaseModel):
    """选品阶段产出 — 整个上下文的信息发动机"""
    category_overview: str                 # 品类市场概况
    market_size_estimate: str              # 市场规模
    market_growth_trend: str               # rising | stable | declining
    top_competitors: list[str]             # 头部竞品品牌
    recommended_niches: list[str]          # 推荐细分方向
    top_pick_product: str                  # 首推产品名
    scored_alternatives: list[dict]        # 备选产品及评分
    # 以下字段由 ContextMapper 从 selection 自由文本中结构化提取
    inferred_selling_points: list[str]     # 推断的核心卖点 → Listing.features
    inferred_target_audience: str          # 推断的人群画像 → Listing/Social
    inferred_price_range: str              # 推断定价 → Ads 预算
    inferred_material: str | None          # 推断材质 → Listing
    competitor_keywords: list[str]         # 竞品关键词 → Listing 种子词
    differentiation_angle: str             # 差异化切入点

class ListingContent(BaseModel):
    """Listing 阶段产出"""
    keywords: list[dict]                   # 结构化关键词
    top_keywords: list[str]
    title_candidates: list[dict]
    best_title: str
    bullet_points: list[dict]
    description_html: str
    a_plus_modules: list
    seo_report: dict
    human_approved: bool = False

class ComplianceReport(BaseModel):
    """合规阶段产出"""
    policy_issues: list[dict]
    claim_issues: list
    overall_verdict: str                   # approved | needs_revision | rejected
    risk_level: str                        # low | medium | high | critical
    total_issues: int
    critical_items: list[str]
    action_items: list[str]
    human_reviewed: bool = False

class SocialContent(BaseModel):
    """社媒阶段产出"""
    marketing_angles: list[str]
    target_audience: str
    content_tones: list[str]
    key_selling_points: list[str]
    visual_style: list[str]
    hashtag_themes: list[str]
    posts: list[dict]                      # 各平台帖子 (copy, image_url, hashtags...)
    human_approved: bool = False

class PlatformState(BaseModel):
    """执行网关产出 — 连接"内容生成"和"运营监控"的桥梁"""
    asin: str | None                       # Amazon 发布后获得
    amazon_url: str | None
    amazon_publish_status: str             # draft | pending | live | error
    amazon_publish_errors: list[str] = []
    amazon_published_at: datetime | None
    social_publish_status: dict[str, str]  # {platform: "published"|"error"}
    social_post_urls: dict[str, str]       # {platform: post_url}

class ReviewSnapshot(BaseModel):
    """评论阶段产出 — 触发条件: PlatformState.asin 不为空"""
    total_reviews: int = 0
    average_rating: float = 0.0
    sentiment_distribution: dict = {}      # {positive: N, neutral: N, negative: N}
    negative_alert_count: int = 0
    top_alerts: list = []
    last_monitored_at: datetime | None

class AdSnapshot(BaseModel):
    """广告阶段产出 — 触发条件: PlatformState.asin 不为空"""
    campaigns: list = []
    total_budget: float = 0.0
    total_spend: float = 0.0
    acos: float | None = None
```

### 2.4 ContextMapper 的三种映射策略

| 策略 | 说明 | LLM 调用 | 例子 |
|------|------|---------|------|
| **直接映射** | 字段改名、规则提取 | 无 | `ctx.top_pick_product → state.product_name` |
| **结构化提取** | 上游自由文本 → 提取为结构化字段 | 1次/阶段 ingest | `category_overview` → 提取 `inferred_selling_points` 等 6 个字段 |
| **按需生成** | 字段确实缺失且无法推导 | 仅当缺失 | `brand_story` 为空时调一次 LLM |

### 2.5 数据流向示例

以"选品 → Listing"这一最关键的对接点为例：

**Step 1: Selection 完成，ingest 将输出写入上下文**

```python
# SelectionMapper.ingest()
async def ingest(self, result: dict, ctx: ProductContext) -> ProductContext:
    # A. 直接映射 — 字段改名
    ctx.market_insight = MarketInsight(
        category_overview = result["category_overview"],
        market_growth_trend = self._extract_trend_direction(result["trends"]),
        top_pick_product = result["top_pick"],
        scored_alternatives = result["scored_products"],
        top_competitors = self._extract_competitors(result["category_overview"]),
    )

    # B. 结构化提取 — 一次 LLM，自由文本 → 6 个字段
    extracted = await self._extract_market_insights(
        category_overview = result["category_overview"],
        trends = result["trends"],
        scored_products = result["scored_products"],
    )
    # extracted = {
    #   "inferred_selling_points": ["高腰压缩设计", "四向弹力面料", ...],
    #   "inferred_target_audience": "25-40岁女性健身爱好者...",
    #   "inferred_material": "Nylon 80% + Spandex 20% blend",
    #   "inferred_price_range": "$25-$45",
    #   "competitor_keywords": ["yoga pants high waist", "lululemon dupe", ...],
    #   "differentiation_angle": "Lululemon Align 平替，同等品质售价仅 1/3"
    # }

    ctx.market_insight.inferred_selling_points = extracted["inferred_selling_points"]
    ctx.market_insight.inferred_target_audience = extracted["inferred_target_audience"]
    # ... 其余赋值

    ctx.current_stage = "analyzed"
    return ctx
```

**Step 2: Listing 启动前，derive 从上下文提取输入**

```python
# ListingMapper.derive() — 零 LLM 调用
def derive(self, ctx: ProductContext) -> ListingState:
    return ListingState(
        product_name    = ctx.market_insight.top_pick_product,        # 改名
        category        = ctx.identity.category,                      # 直接拿
        features        = ctx.market_insight.inferred_selling_points, # 改名
        brand_story     = ctx.identity.brand_story
                       or self._get_or_create_brand_story(ctx),      # 缺失才生成
        seed_keywords   = ctx.market_insight.competitor_keywords,    # 复用
        target_audience = ctx.market_insight.inferred_target_audience,# 复用
    )
```

对比改进前后的效果：

| | 改进前 | 改进后 |
|---|---|---|
| 手动填写字段 | 不确定，看 ctx dict 缺什么 | 固定 2-8 个种子字段 |
| `features` 来源 | `_auto_fill_context` 每次额外调 LLM | selection 提取一次，全程复用 |
| `brand_story` 来源 | 同上 | 生成一次写入 ctx，不再重复 |
| 数据一致性风险 | 高（两次独立 LLM 可能矛盾） | 低（一次提取，多处引用） |
| 可调试性 | ctx 是黑盒 dict | Pydantic 强类型，IDE 有补全 |

### 2.6 批量场景的层级上下文

```python
# 品类模板 — 一个品类一份，包含所有共享字段
template = ProductContext(
    identity=ProductIdentity(
        category="瑜伽裤", brand_name="ZenFlex",
        brand_story="Born from a passion...",  # 一次生成
    ),
    market_insight=MarketInsight(
        inferred_selling_points=["高腰压缩", "四向弹力", "深蹲不透"],
        inferred_target_audience="25-40岁女性健身爱好者",
        inferred_material="Nylon-Spandex blend",
        competitor_keywords=["yoga pants high waist", ...],
    ),
)

# 变体上下文 — 每个 SKU 独立实例，从模板原型继承
variants = create_variants(template, [
    VariantSpec(color="黑色", size="S"),
    VariantSpec(color="黑色", size="M"),
    VariantSpec(color="深蓝", size="S"),
    # ... 共 15 个
])
# 变体继承模板所有字段，各自独立跑 listing，类别共享信息只生成一次
```

### 2.7 可行性

- **技术依赖**：仅依赖项目中已有的 Pydantic v2，无新增外部依赖
- **改造成本**：新增 `backend/app/core/context_bus.py`（约 300 行），修改 `orchestrator.py` 约 30% 的代码
- **向后兼容**：各 workflow 不感知 ContextBus，仍使用自己的 input/output schema
- **可测试性**：每个 `derive()` 和 `ingest()` 都是纯函数，可独立单元测试

---

## 3. 改进二：执行网关

### 3.1 做什么

增加执行网关层，将系统从"内容生成工具"升级为"真正能发布到外部平台"的执行系统。所有对外部平台的 HTTP/MCP/REST 调用集中在这一层，workflow 和 Agent 永远不直接调外部 API。

### 3.2 架构

```text
所有 Workflow ←→ 执行网关 ←→ 外部平台
              │
           唯一出口
           所有对外调用集中在这
```

```python
# 统一结果类型 — 所有 Gateway 方法返回此类型
class GatewayResult(BaseModel):
    success: bool
    remote_id: str | None       # ASIN / post_id / campaign_id
    remote_url: str | None      # 外部可访问 URL
    status: str                  # "live" | "pending" | "error" | "draft"
    errors: list[str] = []
    warnings: list[str] = []
    raw_response: dict | None = None  # 调试用
```

### 3.3 Amazon Gateway

对接 Amazon SP-API，封装系统实际需要的 4 个操作：

| 操作 | SP-API Endpoint | 输入 | 输出到 ProductContext |
|------|----------------|------|----------------------|
| `create_listing` | `/feeds/2021-06-30/feeds` | ProductContext 全部字段 | `PlatformState.asin`, `amazon_url` |
| `get_listing_status` | `/listings/2021-08-01/items/{asin}` | ASIN | `amazon_publish_status` |
| `update_listing` | 同 create（UPDATE 模式） | ASIN + 修改后的 ProductContext | 更新后的状态 |
| `get_reviews` | Product Reviews API | ASIN + max_count | `ReviewSnapshot` |

```python
class AmazonGateway:
    def __init__(self, config: GatewayConfig):
        self.config = config
        self._token: str | None = None

    async def create_listing(self, ctx: ProductContext) -> GatewayResult:
        """把 ProductContext → Amazon JSON_LISTINGS_FEED → 发布"""
        if self.config.mode == "mock":
            return self._mock_create_listing(ctx)

        feed_body = self._build_listing_feed(ctx)
        feed_id = await self._create_feed("JSON_LISTINGS_FEED", feed_body)
        result = await self._poll_feed(feed_id)

        return GatewayResult(
            success=result.success,
            remote_id=result.asin,
            remote_url=f"https://amazon.com/dp/{result.asin}",
            status="live" if result.success else "error",
            errors=result.errors,
        )
```

**Mock 模式**：开发阶段 `AMAZON_SP_API_MODE=mock`，生成格式合法的 mock ASIN（`B0XXXXXXX`），让下游评论监控和广告分析能完整跑通数据流。切换到 `live` 后同一代码走真实 API。

### 3.4 小红书浏览器发布 Gateway（演示用）

由于 Amazon SP-API 需要品牌备案等现实门槛，对于演示场景，通过 Playwright 模拟人类操作发布到小红书，实现可视化、可演示的全自动化链路。

```python
class XiaohongshuGateway:
    """
    通过 Playwright 模拟人类操作发布小红书笔记。
    首次使用弹出浏览器窗口供用户扫码登录，
    之后 Cookie 持久化，后续运行自动登录。
    """

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.cookies_file = Path("data/xiaohongshu_cookies.json")

    async def start(self):
        """启动浏览器，加载或获取登录态"""
        self.browser = await playwright.chromium.launch(
            headless=self.headless,
            slow_mo=300,  # 每个操作间隔 300ms，模拟人类速度
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1440, "height": 900}, locale="zh-CN"
        )

        # 尝试加载已有 Cookie
        if self.cookies_file.exists():
            cookies = json.loads(self.cookies_file.read_text())
            await self.context.add_cookies(cookies)

        self.page = await self.context.new_page()
        await self.page.goto("https://creator.xiaohongshu.com")

        if "login" in self.page.url:
            if self.headless:
                raise GatewayError("Cookie 过期，请先以非 headless 模式登录")
            print(">>> 请在弹出的浏览器中扫码登录小红书 <<<")
            await self._wait_for_login(timeout=120)

            # 保存 Cookie 供后续使用
            cookies = await self.context.cookies()
            self.cookies_file.parent.mkdir(parents=True, exist_ok=True)
            self.cookies_file.write_text(json.dumps(cookies))

    async def publish_post(
        self, title: str, content: str,
        image_paths: list[str], tags: list[str]
    ) -> GatewayResult:
        """模拟操作：创作者中心 → 发布笔记 → 上传图片 → 填表单 → 发布"""
        await self.page.goto("https://creator.xiaohongshu.com")

        # 点击「发布笔记」
        publish_btn = self.page.locator("text=发布笔记").first
        box = await publish_btn.bounding_box()
        await self.page.mouse.click(box["x"] + box["width"] / 2,
                                      box["y"] + box["height"] / 2)

        # 上传图片
        file_input = self.page.locator('input[type="file"]').first
        await file_input.set_input_files(image_paths)
        await self._wait_for_upload_complete(timeout=60)

        # 填写标题（最多 20 字）
        await self.page.locator('[placeholder*="标题"]').first.fill(title[:20])

        # 填写正文（模拟打字速度）
        content_editor = self.page.locator('[placeholder*="输入正文"]').first
        await content_editor.click()
        for paragraph in content.split("\n\n"):
            await content_editor.type(paragraph, delay=50)
            await content_editor.press("Enter")

        # 添加话题标签
        for tag in tags:
            await content_editor.type(f"#{tag} ", delay=30)

        # 点击发布
        submit_btn = self.page.locator("text=发布").last
        box = await submit_btn.bounding_box()
        await self.page.mouse.click(box["x"] + box["width"] / 2,
                                      box["y"] + box["height"] / 2)

        await self.page.wait_for_timeout(3000)
        return GatewayResult(success=True, status="published")
```

### 3.5 WordPress Gateway

复用已有的 `cb-social-publisher.php` 插件：

```python
class WordPressGateway:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def publish_post(
        self, title: str, content: str,
        featured_image_url: str | None = None, status: str = "publish"
    ) -> GatewayResult:
        """通过 WordPress REST API 发布帖子"""
        # 有图片先上传
        image_id = None
        if featured_image_url:
            img_resp = await self._http.post(
                f"{self.base_url}/wp-json/cb/v1/upload-image",
                headers={"X-CB-API-Key": self.api_key},
                json={"image_url": featured_image_url},
            )
            image_id = img_resp.json().get("id")

        # 发布帖子
        resp = await self._http.post(
            f"{self.base_url}/wp-json/cb/v1/publish",
            headers={"X-CB-API-Key": self.api_key},
            json={"title": title, "content": content, "status": status},
        )
        data = resp.json()
        return GatewayResult(
            success=True,
            remote_id=str(data["id"]),
            remote_url=data["url"],
            status=data["status"],
        )
```

### 3.6 Social Publisher — 统一发布入口

按平台路由到不同 Gateway：

```python
class SocialPublisher:
    def __init__(self):
        self.wordpress = WordPressGateway(...)
        self.xiaohongshu = XiaohongshuGateway(headless=False)

    async def publish(self, post: dict, ctx: ProductContext) -> GatewayResult:
        match post["platform"]:
            case "instagram" | "facebook" | "threads" | "pinterest" | "tiktok":
                return await self.wordpress.publish_post(...)
            case "xiaohongshu":
                images = await self._download_images(post["image_urls"])
                return await self.xiaohongshu.publish_post(
                    title=post["short_copy"],
                    content=post["copy"],
                    image_paths=images,
                    tags=post["hashtags"],
                )
```

### 3.7 统一错误处理

| 失败类型 | HTTP 码 | 策略 |
|---------|--------|------|
| 网络超时 | — | 重试 2 次，指数退避 |
| 限流 | 429 | 等待 Retry-After header，放回队列 |
| 认证失败 | 401/403 | 刷新 Token 后重试 1 次 |
| 数据校验失败 | 400 | 不重试，记录错误到 PlatformState |
| 平台内部错 | 500 | 5 分钟后重试 |

### 3.8 可行性

- **Amazon SP-API**：需要品牌备案 + 开发者账号，门槛较高但生产环境必经之路。mock 模式下可先跑通全链路验证架构。
- **小红书浏览器发布**：演示场景完全可行。选择器用文本定位（`text=发布笔记`）比 CSS class 更稳。风险包括页面结构变更和偶发验证码，通过 `slow_mo` 模拟人类速度和 Cookie 持久化可缓解。
- **WordPress**：已有插件，可直接对接。
- **已有依赖**：项目中已有 `httpx`，Playwright 需新增（`pip install playwright`）。

---

## 4. 改进三：批量上架与并发控制

### 4.1 做什么

支持一次处理一个品类下的多个变体（5颜色 × 3尺码 = 15 SKU），在 LLM API 和 SP-API 的双重限流约束下安全并发执行。

### 4.2 架构

```text
Step 1: 品类分析（跑 1 次）
  selection → 品类模板 CategoryContext
  ├── 市场洞察（所有变体共享）
  ├── 材质、品牌故事（所有变体共享）
  └── 关键词策略分区（15 个变体不冲突）

Step 2: 变体生成（15 个并发，semaphore 控制上限=5）
  Variant[0-14]: 品类模板 + {color, size} → listing → compliance

Step 3: 去重检查（15 个变体 embedding 互相对比）

Step 4: 批量发布（按 SP-API 的 TPS 限流排队）
```

### 4.3 三层并发控制

| 层次 | 约束来源 | 机制 | 工具 |
|------|---------|------|------|
| 业务并发 | 同时处理的 SKU 数 | Semaphore(N) | `asyncio.Semaphore(5)` |
| LLM 限流 | DeepSeek ~60 RPM | Token Bucket | 自定义 `LLMRateLimiter` |
| SP-API 限流 | Amazon 按 endpoint 不同 TPS | 多 Token Bucket + Retry-After | 自定义 `SPAPIRateLimiter` |

### 4.4 令牌桶实现

```python
class LLMRateLimiter:
    """令牌桶算法 — 保持 LLM 调用平滑，避免触发 429"""

    def __init__(self, rate_per_minute: int = 60, burst: int = 10):
        self.rate = rate_per_minute / 60.0  # 1 token/秒
        self.burst = burst
        self.tokens = burst
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        """获取一次调用许可，返回等待时长（秒）"""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens >= 1:
                self.tokens -= 1
                return 0.0  # 无需等待

            wait_time = (1 - self.tokens) / self.rate
            self.tokens = 0
            self.last_update = now + wait_time

        await asyncio.sleep(wait_time)
        return wait_time
```

### 4.5 批量编排器

```python
class BatchListingOrchestrator:
    def __init__(self, max_concurrency: int = 5):
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.llm_limiter = LLMRateLimiter()
        self.progress = BatchProgress()

    async def run(
        self, template: ProductContext, variants: list[ProductContext]
    ) -> BatchResult:
        # 每个变体作为独立 task，受 semaphore 控制并发上限
        tasks = [
            self._process_one(i, v) for i, v in enumerate(variants)
        ]

        # return_exceptions=True 确保单个失败不影响其他
        raw = await asyncio.gather(*tasks, return_exceptions=True)

        results, failed = [], []
        for i, r in enumerate(raw):
            if isinstance(r, Exception):
                failed.append(VariantResult(
                    variant_id=variants[i].identity.product_id, error=str(r)
                ))
            else:
                results.append(r)

        # 全批量完成后去重检查
        duplicates = await self._check_cross_variant_similarity(results)

        return BatchResult(
            total=len(variants), succeeded=len(results), failed=len(failed),
            results=results, failed=failed, duplicate_pairs=duplicates,
        )

    async def _process_one(self, index: int, variant: ProductContext) -> VariantResult:
        async with self.semaphore:
            # 将限流器注入 Agent 上下文
            variant.context["llm_limiter"] = self.llm_limiter

            # 依次执行 keyword → title → bullets → description → aplus → seo
            variant = await self._run_keyword_research(variant)
            # ... 其余步骤 ...
            return VariantResult(variant_id=variant.identity.product_id, success=True)
```

Agent 层改造（`BaseAgent._call_llm` 加一行）：

```python
async def _call_llm(self, system_prompt, user_prompt, **kwargs):
    # 注入：上下文中有限流器时，先获取许可
    limiter = self._context.get("llm_limiter") if self._context else None
    if limiter:
        wait = await limiter.acquire()
        if wait > 0.5:
            logger.debug(f"LLM rate limited: waited {wait:.1f}s")

    # 原有逻辑不变
    response = await self.llm.chat(...)
    return response
```

### 4.6 错误隔离

```python
# 三类异常的差异化处理
async def _process_one_with_retry(self, index, variant, max_retries=2):
    for attempt in range(max_retries + 1):
        try:
            return await self._process_one(index, variant)
        except LLMFormatError:
            # JSON 解析失败 → 可重试（LLM 不稳定是常态）
            if attempt < max_retries:
                await asyncio.sleep(1 * (2 ** attempt)); continue
            raise
        except RateLimitExceeded:
            # 429 → 指数退避
            if attempt < max_retries:
                await asyncio.sleep(5 * (2 ** attempt)); continue
            raise
        except (AuthenticationError, ValidationError):
            # 不可重试 → 直接标记失败
            raise
```

### 4.7 并发策略自动选择

```python
def auto_strategy(api_keys: list, llm_rpm: int) -> int:
    """根据可用 API Key 数量和 LLM 限制自动决定并发度"""
    total_capacity = sum(k.rpm for k in api_keys if k.is_active()) * 0.8
    max_skus = total_capacity / 6  # 6 次 LLM 调用/SKU
    return min(int(max_skus), len(api_keys) * 5)
```

### 4.8 前端批量视图

```
┌──────────────────────────────────────────────┐
│  批量上架                                      │
│                                              │
│  品类: [瑜伽裤]  变体: 5颜色×3尺码 = 15 SKU    │
│                                              │
│  SKU-000 黑色 S  ████████████████  ✅ 87分    │
│  SKU-001 黑色 M  ████████████████  ✅ 82分    │
│  SKU-002 黑色 L  ██████████████░░  ⏳ 描述中   │
│  SKU-003 深蓝 S  ██████████░░░░░░  ⏳ 标题中   │
│  SKU-004 深蓝 M  ████░░░░░░░░░░░░  ⏳ 关键词   │
│  SKU-005+        ○○○○○○○○○○○○○○○○  等待中     │
│                                              │
│  进度: 4/15 完成 | 去重警告: 1 对相似          │
└──────────────────────────────────────────────┘
```

### 4.9 可行性

- **依赖**：无新增外部依赖，`asyncio.Semaphore` 和 `asyncio.gather` 为标准库
- **与现有代码关系**：Agent 层仅需 `BaseAgent._call_llm` 加 4 行限流器检查
- **风险**：并发下 LLM 返回格式不稳定（JSON 解析失败），通过错误隔离+重试机制应对

---

## 5. 改进四：Listing 去重机制

### 5.1 问题描述

亚马逊的重复 Listing 检测是算法驱动的。如果两个同品类变体的标题、五点描述文本相似度太高，可能被合并或降权。不能靠"加随机性"解决——Listing 质量要求精准，不能乱换词。

### 5.2 三道防线

```text
               事前                      事中                    事后
         ┌──────────────┐    ┌──────────────────┐    ┌──────────────┐
         │  关键词避让    │ →  │  差异化生成       │ →  │  embedding   │
         │  关键词分区    │    │  锚定真实差异      │    │  相似度门禁   │
         └──────────────┘    └──────────────────┘    └──────────────┘
         品类模板阶段          单个变体生成时            所有变体完成后
```

### 5.3 防线一：关键词策略分区（事前）

品类模板生成时为每个变体规划不同的关键词策略：

```python
# 关键词分区规划
category_keyword_map = {
    "黑色系": ["gym leggings", "workout pants", "fitness wear"],
    "深蓝系": ["yoga studio", "pilates pants", "studio wear"],
    "灰色系": ["everyday leggings", "casual wear", "lounge pants"],
    "酒红系": ["fall fashion", "winter leggings", "autumn style"],
    "军绿系": ["outdoor yoga", "hiking leggings", "adventure wear"],
}

# 注入 keyword_research Agent
class KeywordResearchInput(BaseModel):
    product_name: str
    category: str
    features: list[str]
    reserved_keywords: list[str] = []   # 新增：其他变体已占用的关键词
    keyword_strategy: str = "explore"   # 新增：explore | avoid_conflict
```

关键词不撞车 → 标题自然不撞车。

### 5.4 防线二：差异化生成（事中）

生成时把真实的产品差异作为锚点：

```python
# 给 LLM 的 prompt 注入变体属性差异
user_prompt = f"""
产品名称: {product_name}
变体属性: 颜色=酒红, 尺码=XXL

请在标题和描述中围绕"酒红色"的视觉特点展开：
  - 优雅、显白、秋冬搭配
  - 大码身材的穿着体验（高腰收腹、不卷边、加长裆部）

请在标题和描述中围绕"黑色"的视觉特点展开：
  - 百搭、显瘦、经典
  - 适合高强度训练（深蹲、HIIT）
"""
```

本质是把两个 SKU 之间的**实质性差异放大**，而不是凭空制造不同。

### 5.5 防线三：Embedding 相似度门禁（事后）

所有变体生成完毕后，批量做相似度检查：

```python
async def check_batch_similarity(
    variants: list[ProductContext],
    threshold: float = 0.85,
) -> list[DuplicatePair]:
    """
    对 N 个变体两两比较标题+五点的 embedding 相似度。
    项目中已有 ChromaDB + embedding 能力，直接复用。
    """
    texts = [
        v.listing.best_title + " " + " ".join(
            bp.text for bp in v.listing.bullet_points
        )
        for v in variants
    ]

    embeddings = await embedding_service.embed_batch(texts)

    duplicates = []
    for i in range(len(embeddings)):
        for j in range(i + 1, len(embeddings)):
            sim = cosine_similarity(embeddings[i], embeddings[j])
            if sim > threshold:
                duplicates.append(DuplicatePair(
                    variant_a=variants[i].identity.product_id,
                    variant_b=variants[j].identity.product_id,
                    similarity=sim,
                ))

    return duplicates
```

前端在批量视图中标红高相似度对，人一眼看到哪两个需要改。

### 5.6 可行性

- 依赖：项目中已有的 ChromaDB + Qwen embedding，直接复用。无新增外部依赖。
- 计算量：15 个 SKU 两两比较 = 105 次 cosine 计算，毫秒级完成。
- 阈值可配：`threshold` 从小开始（0.90），根据实际效果逐步收紧。

---

## 6. 改进五：UGC 素材利用

### 6.1 问题描述

系统社媒模块的 `copy_generator` 产出的文案是 LLM "编"出来的——根据产品信息推测使用场景。但真实的买家评论里有一些东西 LLM 编不出来：

```
LLM 编的:  "这款瑜伽裤采用四向弹力面料，提供卓越的穿着体验"
买家说的:  "作为一个大腿围68cm的梨形身材，我终于找到一条深蹲不透的瑜伽裤了"
```

买家原话里有具体的痛点、真实的场景、有辨识度的语言。这三个东西 LLM 有能力模仿，但它不知道哪个才是"你的产品"真正打动人的点。

### 6.2 架构

在 Review workflow 和 Social workflow 之间加一个轻量的 UGC 管道：

```text
Review Monitor
  │
  ├─ 抓取评论
  ├─ 情感分析
  ├─ 翻译
  ├─ 差评告警
  └─ 优质评论 → 流入 UGC 管道 (*新增*)
                   │
UGCCurator Agent (*新增*)         UGCTransformer (*新增*)
  │                                 │
  ├─ 规则筛选（秒级）                 ├─ 按平台适配格式
  ├─ 故事性评分（LLM 1次评N条）       ├─ 匿名化处理
  └─ 入选 → ContentPool              ├─ 配图生成
                                     └─ 流入 Social workflow

Social Media Workflow  ← UGC 帖子注入
  │
  ├─ 产品分析
  ├─ 平台适配
  ├─ 文案生成 ← （UGC 替代这一步）
  ├─ 图片生成
  ├─ 质量审核
  └─ 发布
```

关键设计：UGC 替换了 Social workflow 的文案生成这一步，但复用其后的图片生成、质量审核和发布。不是另起炉灶，是在现有流程上插入一条更优的内容来源。

### 6.3 UGC 筛选标准

| 维度 | 筛选标准 | 原因 |
|------|---------|------|
| 评分 | ≥ 4 星 | 差评不能做宣传 |
| 内容长度 | ≥ 40 词 | 太短无叙事价值 |
| 故事性 | 含具体场景/痛点 | 有叙事才有传播力 |
| 淘宝/Amazon 可验证 | verified_purchase=True | 标识真实买家 |
| 有用票数 | helpful_count ≥ 2 | 已被其他买家验证过质量 |

### 6.4 UGCCurator Agent

```python
class UGCCuratorAgent(BaseAgent):
    """从评论池中筛选高质量 UGC"""

    # 规则层 — 零 LLM，秒级过滤
    FILTER_RULES = {
        "min_rating": 4,
        "min_content_length": 40,
        "min_sentences": 2,
        "min_helpful_count": 2,
        "verified_purchase_only": True,
        "exclude_patterns": [
            r"退款|退货|客服|<script>|http",
            r"还行|一般|凑合|差不多",
        ],
    }

    async def curate(self, reviews: list[ScrapedReview]) -> CurationResult:
        # Step 1: 规则层过滤
        candidates = [r for r in reviews if self._passes_rules(r)]

        # Step 2: LLM 批量评分 — 一次调用评所有候选
        # 输入: 候选评论列表
        # 输出: [7.5, 4.0, 9.0, ...] 对应每条的故事性分数
        scores = await self._batch_score_narrative(candidates)

        # Step 3: 排序 + 去重
        selected = self._dedup_and_rank(candidates, scores)
        return CurationResult(
            selected=[
                UGCCandidate(
                    review=r,
                    narrative_score=scores[i],
                    suggested_angle=self._infer_angle(r),  # 规则推断：gifting/comparison/solution/...
                )
                for i, r in enumerate(selected)
            ],
        )

    def _infer_angle(self, review) -> str:
        """根据评论内容推断营销角度 — 规则，零 LLM"""
        if any(w in review.content.lower() for w in ["gift", "送给", "礼物"]):
            return "gifting"       # 送礼场景
        if any(w in review.content.lower() for w in ["终于", "找到", "再也不"]):
            return "solution"      # 痛点解决
        if any(w in review.content.lower() for w in ["以前", "对比", "compared"]):
            return "comparison"    # 对比测评
        return "testimonial"       # 通用好评
```

### 6.5 匿名化处理

```python
def anonymize_review(review: ScrapedReview) -> str:
    """把买家身份脱敏，保留内容价值"""
    name = review.reviewer_name
    if len(name) <= 2:
        return "一位买家"
    elif name[0].isalpha():
        return f"{name[0]}***"    # "Sarah M." → "S***"
    else:
        return f"一位{name[0]}***的买家"
```

### 6.6 UGC 内容特征

| | 品牌自产内容 | UGC 转化内容 |
|---|---|---|
| 语气 | 专业、营销感 | 真实、口语化 |
| 图片风格 | 精修产品图 | 生活场景、买家秀风格 |
| 信任度 | 品牌在说 | 一个真实的买家在说 |
| 标签 | #品牌标签为主 | 混入 #真实评价 #买家秀 |
| 发布频率 | 每天可发 | 有真的才发（稀缺性即价值） |

**内容模板 — "引用 + 认同"结构：**

> "S*** 买了我们的瑜伽裤后说：'深蹲完全不透，腰部也不会往下滑'——这条评价让我们团队特别开心，因为'不卷边'正是我们改了 7 版设计才做到的。"

### 6.7 可行性

- **改动量**：新增 1 个 Agent（`UGCCuratorAgent`，~120 行）+ 1 个 Transformer（~80 行，大量复用 social workflow）
- **性能**：筛选阶段 LLM 调用 1 次/N 条候选（而非 N 次），与其他 workflow 相比开销极小
- **数据质量**：筛选条件确保入选评论的质量，匿名化确保伦理合规
- **与现有模块关系**：Review workflow 增加可选下游节点；Social 页面增加 `[UGC 内容]` Tab

---

## 7. 改进六：前端整合与管线视图

### 7.1 问题描述

前端 11 个页面在侧边栏平铺，各模块之间的上下游关系（选品 → Listing → 合规 → 社媒 → 评论）对用户不可见。用户打开系统不知道从哪开始、下一步去哪。

### 7.2 核心思路

不改后端，只改前端组织方式。从"工具列表"变成"产品流水线"——给每个功能加上**位置感**。

### 7.3 三层重组

**第一层：侧边栏按业务阶段分组**

```text
📦 产品上架
  ├── 选品分析
  ├── Listing 生成
  └── 合规审查

📣 内容营销
  ├── 社媒内容
  ├── UGC 内容
  └── 内容日历

📊 运营监控
  ├── 评论监控
  ├── 广告分析
  └── 客服对话

⚙️ 系统
  ├── 全自动编排
  ├── 产品动态流
  └── 知识库
```

实现方式：修改 `frontend/src/components/Layout.tsx`，把导航数组从平铺改成嵌套结构，每个分组渲染一个 Section header。

**第二层：仪表盘改成管线视图**

```text
┌─────────────────────────────────────────────────────────────┐
│  产品管线                                      [+新建产品]    │
│                                                             │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐ │
│  │ 📊 选品   │──→│ 📝 Listing│──→│ 🔍 合规  │──→│ 📣 社媒  │ │
│  │ 3 个待定  │   │ 2 个草稿  │   │ 1 个审查  │   │ 4 条待发  │ │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘ │
│                                                             │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐                │
│  │ ⭐ 评论   │   │ 📈 广告  │   │ 💬 客服   │                │
│  │ 2条告警   │   │ 3 个活动  │   │ 0 条未读  │                │
│  └──────────┘   └──────────┘   └──────────┘                │
│                                                             │
│  🔥 最近活动                                                 │
│  10:32  「瑜伽裤-黑色M」通过合规审查 ✅                        │
│  10:28  「瑜伽裤-深蓝S」Listing 审批通过，SEO 87 分           │
│  10:15  「瑜伽裤」选品完成，首推"高腰压缩款"                  │
└─────────────────────────────────────────────────────────────┘
```

实现方式：修改 `frontend/src/pages/DashboardPage.tsx`，从两张卡片改成管线组件 + 产品状态追踪（`frontend/src/lib/TaskStore.ts` 新增 `ProductPipelineStore`）。

**第三层：每个页面顶部加步骤导航条**

```
Listing 页面顶部:
┌──────────────────────────────────────────┐
│ 产品: 瑜伽裤-黑色S    当前阶段: 上架准备   │
│                                          │
│ ● 选品分析 → ◉ Listing → ○ 合规 → ○ 社媒 │
│   (已完成)    (当前)       (待开始)  (待开始)│
└──────────────────────────────────────────┘
```

新增组件 `PipelineBreadcrumb`，每个 workflow 页面引用。它接收当前阶段参数，自动判断前后节点状态。

### 7.4 整合后的用户体验

1. 打开系统 → **仪表盘**显示管线，看到选品阶段有 3 个品类在分析
2. 点击「瑜伽裤-黑色S」→ 进入 **Listing 页面**
3. 页面顶部导航条显示：`选品 ✓ → Listing ◉ → 合规 ○`
4. 审批通过 → 状态自动流转到合规阶段
5. 管线视图里，「瑜伽裤-黑色S」从 Listing 列消失，出现在合规列
6. 合规通过 → 自动触发生成社媒内容
7. 仪表盘社媒列出现新数字

从头到尾，用户不需要知道"接下来该点哪个菜单"——管线自己驱动。

### 7.5 可行性

- **改动范围**：仅前端，0 后端改动
- **改动文件**：
  - `Layout.tsx` — 侧边栏分组（导航数组从平铺改嵌套）
  - `DashboardPage.tsx` — 仪表盘管线组件
  - `TaskStore.ts` — 新增 `ProductPipelineStore`
  - 新增 `PipelineBreadcrumb.tsx` 组件
  - 各 workflow 页面引用 PipelineBreadcrumb
- **风险**：低。纯前端 UI 重组，不碰数据和 API。

---

## 8. 实施路线图

### Phase 1：架构基础（建议先做）

| 任务 | 改动范围 | 预估工作量 |
|------|---------|-----------|
| 实现 ProductContext 模型 | 新增 `backend/app/core/context_bus.py` | 2-3天 |
| 实现 ContextMapper（5个 domain mapper） | 同上 | 2-3天 |
| 改造 orchestrator（替换 _auto_fill_context） | 修改 `orchestrator.py` | 1天 |
| 实现 ContextBus（持久化、版本追踪） | 同上 + 数据库迁移 | 1天 |

Phase 1 是其他所有改进的**前提**——没有上下文总线，批量、去重、UGC 管道都会在数据传递上再次踩坑。

### Phase 2：执行层

| 任务 | 改动范围 | 预估工作量 |
|------|---------|-----------|
| Gateway 基类和统一结果类型 | 新增 `backend/app/gateway/` | 0.5天 |
| WordPress Gateway | 封装已有 PHP 插件 | 0.5天 |
| Amazon Gateway（mock 模式） | 新增大文件 | 1天 |
| 小红书浏览器发布 Gateway | 新增 + Playwright 脚本 | 1-2天 |
| Social Publisher 统一入口 | 新增 | 0.5天 |
| orchestrator 集成发布步骤 | 修改 `orchestrator.py` | 0.5天 |

### Phase 3：批量能力

| 任务 | 改动范围 | 预估工作量 |
|------|---------|-----------|
| 令牌桶限流器 | 新增工具类 | 0.5天 |
| 批量编排器 | 新增类 | 1天 |
| Agent 层注入限流器 | 修改 `base.py`（4行） | 0.5天 |
| 前端批量视图 | 修改 Listing 页面 | 1天 |
| 错误隔离 + 重试 | 编排器内 | 0.5天 |
| 去重三道防线 | 关键词 Agent + embedding 检查 | 1-2天 |

### Phase 4：UGC + 前端整合

| 任务 | 改动范围 | 预估工作量 |
|------|---------|-----------|
| UGCCurator Agent | 新增 Agent | 1天 |
| UGCTransformer | 新增（复用 social workflow） | 1天 |
| 侧边栏分组 | 修改 `Layout.tsx` | 0.5天 |
| 仪表盘管线视图 | 修改 `DashboardPage.tsx` | 1天 |
| PipelineBreadcrumb 组件 | 新增组件 | 0.5天 |
| 各页面集成导航条 | 各页面引用新组件 | 0.5天 |

---

## 9. 总结

本项目从内容生成工具向全自动运营系统演进的路径，核心不是增加更多 Agent，而是补上三个缺失的架构层：

| 缺失层 | 解决什么问题 | 核心交付 |
|--------|------------|---------|
| **上下文总线** | 数据在模块间自动流转 | ProductContext + ContextMapper + ContextBus |
| **执行网关** | 内容能真正发布到外部 | Amazon GW + WordPress GW + 小红书浏览器 GW |
| **批量编排** | 一次处理多个变体 | Semaphore + TokenBucket + 错误隔离 |

辅以 **去重机制**（事前关键词避让 + 事中差异化生成 + 事后 embedding 门禁）、**UGC 管道**（评论→筛选→转化→发布）和 **前端管线视图**（侧边栏分组 + 仪表盘 + 步骤导航条），实现从"辅助生成工具"到"AI 运营系统"的升级。

---

*文档基于 2026-05-17 的代码库分析，各改进项的可行性已针对项目现有技术栈（LangGraph + FastAPI + React + Pydantic v2 + ChromaDB）进行评估。*
