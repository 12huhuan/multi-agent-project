"""
Amazon 数据收集器 — 通过 Playwright 实时抓取 Amazon 搜索结果。

数据流:
  品类 + 关键词 → Playwright → Amazon.com/s?k=xxx → 结构化提取 → TrendAnalyzerAgent

回退: Playwright 不可用时使用模拟数据。
"""

import re
import asyncio
import random
import time
from typing import Optional
from pydantic import BaseModel, Field


# ── 全局单例（避免每次选品都冷启动浏览器） ──
_collector_instance: Optional["AmazonDataCollector"] = None


async def get_collector() -> "AmazonDataCollector":
    global _collector_instance
    if _collector_instance is None or not _collector_instance._started:
        if _collector_instance:
            try:
                await _collector_instance.stop()
            except Exception:
                pass
        _collector_instance = AmazonDataCollector()
        await _collector_instance.start()
    return _collector_instance


class AmazonProductCard(BaseModel):
    title: str = ""
    price: str = ""
    original_price: str = ""
    rating: float = 0.0
    review_count: int = 0
    is_sponsored: bool = False
    is_best_seller: bool = False
    is_amazon_choice: bool = False
    url_suffix: str = ""


class BSRInfo(BaseModel):
    """Best Sellers Rank 条目"""
    rank: int = 0
    category: str = ""
    subcategory: str = ""


class AmazonProductDetail(BaseModel):
    """商品详情页数据"""
    asin: str = ""
    title: str = ""
    price: str = ""
    rating: float = 0.0
    review_count: int = 0
    bsr_rankings: list[BSRInfo] = Field(default_factory=list)
    first_available: str = ""


class AmazonSearchResult(BaseModel):
    keyword: str = ""
    total_results_estimate: str = ""
    products: list[AmazonProductCard] = Field(default_factory=list)
    source: str = "live"  # "live" | "simulated"
    extra: dict = Field(default_factory=dict)  # BSR details, etc.


class AmazonDataCollector:
    """
    通过 Playwright 浏览器抓取 Amazon 搜索数据。

    使用方式:
      collector = AmazonDataCollector()
      result = await collector.search("wireless headphones")
      for p in result.products:
          print(p.title, p.price, p.rating, p.review_count)

    Playwright 上下文是共享的（复用浏览器实例），调用方负责 start/stop 生命周期。
    """

    SEARCH_URL = "https://www.amazon.com/s"
    MAX_RETRIES = 2

    def __init__(self):
        self._browser: Optional["Browser"] = None
        self._context: Optional["BrowserContext"] = None
        self._started = False

    async def start(self):
        """启动浏览器（调用方负责）"""
        if self._started:
            return
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )
            self._started = True
        except Exception:
            self._started = False

    async def stop(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._started = False

    async def search(self, keyword: str, num_pages: int = 2) -> AmazonSearchResult:
        """
        搜索 Amazon US，返回产品卡片列表。

        Args:
            keyword: 搜索关键词
            num_pages: 抓取变体关键词数（每个变体一个页面）
        """
        # 生成变体关键词覆盖不同搜索角度
        variants = self._keyword_variants(keyword)[:num_pages]
        all_products = []
        source = "simulated"

        for kw in variants:
            try:
                products = await self._scrape_keyword(kw)
                if products:
                    all_products.extend(products)
                    source = "live"
                    # 随机延迟 1-3 秒，模拟人类浏览
                    await asyncio.sleep(random.uniform(1.0, 3.0))
            except Exception:
                continue

        # 去重
        seen = set()
        unique = []
        for p in all_products:
            key = p.title[:60]
            if key not in seen:
                seen.add(key)
                unique.append(p)

        if source == "simulated":
            unique = self._generate_mock(keyword)

        return AmazonSearchResult(
            keyword=keyword,
            total_results_estimate=f"{len(unique)} products",
            products=unique[:30],
            source=source,
        )

    async def search_multi(self, keywords: list[str]) -> dict[str, AmazonSearchResult]:
        """批量搜索多个关键词"""
        results = {}
        for kw in keywords[:5]:
            results[kw] = await self.search(kw, num_pages=1)
        return results

    # ── 商品详情页抓取（BSR / 类目排名） ─────────

    async def get_product_detail(self, asin: str) -> AmazonProductDetail:
        """抓取单个 ASIN 的商品详情页，提取 BSR 和类目排名"""
        await self._ensure_started()
        if not self._started or not self._browser:
            return AmazonProductDetail(asin=asin, title="(browser not available)")

        url = f"https://www.amazon.com/dp/{asin}"
        page = None

        for attempt in range(self.MAX_RETRIES):
            try:
                page = await self._context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(1.5)

                detail = await page.evaluate("""() => {
                    const result = { bsr_rankings: [], first_available: '' };

                    // ----- 1. 提取标题 -----
                    const titleEl = document.querySelector('#productTitle');
                    result.title = titleEl ? titleEl.textContent.trim() : '';

                    // ----- 2. 提取价格 -----
                    const priceWhole = document.querySelector('.a-price-whole');
                    const priceFraction = document.querySelector('.a-price-fraction');
                    if (priceWhole) {
                        result.price = '$' + priceWhole.textContent.trim();
                        if (priceFraction) result.price += '.' + priceFraction.textContent.trim();
                    }

                    // ----- 3. 提取评分和评论数 -----
                    const ratingEl = document.querySelector('#acrPopover .a-icon-alt, [data-hook="rating-out-of-text"]');
                    if (ratingEl) {
                        const m = ratingEl.textContent.match(/(\\d+(\\.\\d+)?)/);
                        result.rating = m ? parseFloat(m[1]) : 0;
                    }
                    const reviewsEl = document.querySelector('#acrCustomerReviewText');
                    if (reviewsEl) {
                        const m = reviewsEl.textContent.match(/([\\d,]+)/);
                        result.review_count = m ? parseInt(m[1].replace(/,/g, '')) : 0;
                    }

                    // ----- 4. 提取 BSR（Best Sellers Rank） -----
                    // BSR 可能出现在多个位置：detailBullets, productDetails_techSpec, 或 #detailBulletsWrapper_feature_div
                    const containers = [
                        document.querySelector('#detailBulletsWrapper_feature_div'),
                        document.querySelector('#productDetails_detailBullets_sections1'),
                        document.querySelector('#productDetails_techSpec_section_1'),
                        document.querySelector('#detailBullets_feature_div'),
                    ];

                    for (const container of containers) {
                        if (!container) continue;
                        const text = container.textContent;
                        if (!text.includes('Best Sellers Rank') && !text.includes('Best Sellersランク')) continue;

                        // 解析 BSR 行: "#1,234 in Category (See Top 100)"
                        const bsrLines = text.split(/\\n/);
                        for (const line of bsrLines) {
                            // 匹配 "Best Sellers Rank" 那行及其后续行
                            const rankMatch = line.match(/#([\\d,]+)\\s+in\\s+(.+?)(?:\\s*\\(See Top 100\\))?$/);
                            if (rankMatch) {
                                const rank = parseInt(rankMatch[1].replace(/,/g, ''));
                                const category = rankMatch[2].trim();
                                result.bsr_rankings.push({
                                    rank: rank,
                                    category: category,
                                    subcategory: ''
                                });
                            }
                        }
                    }

                    // 备用：直接从整个页面文本中正则提取 BSR
                    if (result.bsr_rankings.length === 0) {
                        const bodyText = document.body.textContent;
                        const bsrSectionMatch = bodyText.match(/Best Sellers Rank[:\\s]*([\\s\\S]*?)(?=\\n\\n|$)/);
                        if (bsrSectionMatch) {
                            const bsrText = bsrSectionMatch[1];
                            const rankRegex = /#([\\d,]+)\\s+in\\s+(.+?)(?=\\s+(?:#\\d|$))/g;
                            let m;
                            while ((m = rankRegex.exec(bsrText)) !== null) {
                                result.bsr_rankings.push({
                                    rank: parseInt(m[1].replace(/,/g, '')),
                                    category: m[2].trim(),
                                    subcategory: ''
                                });
                            }
                        }
                    }

                    // 如果只有一个 BSR 条目，第一个是大类，后面的（#开头的）是子类
                    const bsrs = result.bsr_rankings;
                    if (bsrs.length > 1) {
                        for (let i = 1; i < bsrs.length; i++) {
                            bsrs[i].subcategory = bsrs[i].category;
                            bsrs[i].category = bsrs[0].category;
                        }
                    }

                    // ----- 5. 提取首次上架时间 -----
                    const availEl = document.querySelector('#productDetails_detailBullets_sections1 tr:last-child td, #detailBullets_feature_div .a-row:last-child');
                    if (availEl) {
                        const dateMatch = availEl.textContent.match(/\\d{4}/);
                        if (dateMatch) result.first_available = dateMatch[0];
                    }

                    return result;
                }""")

                await page.close()
                return AmazonProductDetail(asin=asin, **detail)

            except Exception:
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(2 * (attempt + 1))
                continue

        return AmazonProductDetail(asin=asin)

    async def enrich_search_results(
        self, keyword: str, num_pages: int = 1, enrich_count: int = 10
    ) -> AmazonSearchResult:
        """
        搜索 + 自动为前 N 个产品抓取 BSR 详情，一步到位拿到完整的选品数据。

        Args:
            keyword: 搜索关键词
            num_pages: 搜索页数
            enrich_count: 要抓详情页的产品数量（取搜索结果前 N 个）
        """
        result = await self.search(keyword, num_pages=num_pages)

        if result.source != "live":
            return result

        details = []
        for p in result.products[:enrich_count]:
            if not p.url_suffix:
                continue
            asin = p.url_suffix.replace("/dp/", "").split("?")[0].split("/")[0]
            if len(asin) < 8:
                continue
            detail = await self.get_product_detail(asin)
            details.append(detail)
            await asyncio.sleep(random.uniform(0.5, 1.5))

        result.products = result.products  # keep original cards, BSR attached via detail lookup
        # 将 BSR 注入到 product card 的扩展属性中
        result.extra = {
            "bsr_details": {d.asin: d.model_dump() for d in details if d.bsr_rankings},
        }
        return result

    # ── Playwright 实时抓取 ─────────────────────────

    async def _ensure_started(self):
        """自动启动浏览器（首次使用时）"""
        if not self._started:
            await self.start()

    async def _scrape_keyword(self, keyword: str) -> list[AmazonProductCard]:
        """通过 Playwright 抓取单个关键词的 Amazon 搜索结果"""
        await self._ensure_started()
        if not self._started or not self._browser:
            return []

        url = f"{self.SEARCH_URL}?k={keyword.replace(' ', '+')}"
        page = None

        for attempt in range(self.MAX_RETRIES):
            try:
                page = await self._context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)

                # 等待搜索结果加载
                try:
                    await page.wait_for_selector('[data-component-type="s-search-result"]', timeout=10000)
                except Exception:
                    pass

                await asyncio.sleep(1)  # 等 JS 渲染完成

                # 提取产品卡片数据
                products = await page.evaluate("""() => {
                    const cards = document.querySelectorAll('[data-component-type="s-search-result"]');
                    const results = [];
                    cards.forEach((card, i) => {
                        if (i >= 25) return;
                        try {
                            const asin = card.getAttribute('data-asin');
                            if (!asin || asin === 'null') return;

                            const titleEl = card.querySelector('h2 a span, h2 span, [class*="title"]');
                            const title = titleEl ? titleEl.textContent.trim() : '';

                            const priceWhole = card.querySelector('.a-price-whole');
                            const priceFraction = card.querySelector('.a-price-fraction');
                            let price = '';
                            if (priceWhole) {
                                price = '$' + priceWhole.textContent.trim();
                                if (priceFraction) price += '.' + priceFraction.textContent.trim();
                            }

                            const ratingEl = card.querySelector('.a-icon-alt, [class*="rating"]');
                            const ratingText = ratingEl ? ratingEl.textContent : '';
                            const ratingMatch = ratingText.match(/(\\d+(\\.\\d+)?)/);
                            const rating = ratingMatch ? parseFloat(ratingMatch[1]) : 0;

                            const reviewEl = card.querySelector('[class*="review"] span, .a-size-base.s-underline-text');
                            const reviewText = reviewEl ? reviewEl.textContent : '';
                            const reviewMatch = reviewText.match(/([\\d,]+)/);
                            const reviewCount = reviewMatch ? parseInt(reviewMatch[1].replace(/,/g, '')) : 0;

                            const isSponsored = card.textContent.includes('Sponsored');
                            const isBestSeller = card.textContent.includes('Best Seller');
                            const isAmazonChoice = card.textContent.includes("Amazon's Choice") || card.textContent.includes('Overall Pick');

                            results.push({
                                title: title,
                                price: price,
                                original_price: '',
                                rating: rating,
                                review_count: reviewCount,
                                is_sponsored: isSponsored,
                                is_best_seller: isBestSeller,
                                is_amazon_choice: isAmazonChoice,
                                url_suffix: '/dp/' + asin
                            });
                        } catch(e) {}
                    });
                    return results;
                }""")

                await page.close()
                if products:
                    return [AmazonProductCard(**p) for p in products]

            except Exception as e:
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(2 * (attempt + 1))
                continue

        return []

    def _keyword_variants(self, keyword: str) -> list[str]:
        return [
            keyword,
            f"best {keyword}",
            f"{keyword} top rated",
        ]

    # ── 模拟数据回退 ──────────────────────────────

    def _generate_mock(self, keyword: str) -> list[AmazonProductCard]:
        import random as rnd
        mock_products = []
        price_points = [14.99, 19.99, 24.99, 29.99, 34.99, 39.99, 49.99, 59.99, 79.99, 99.99]
        variations = [
            "Premium", "Pro", "Ultra", "Classic", "Max",
            "Essential", "Elite", "Mini", "Plus", "Pro Max",
        ]
        for i in range(min(12, len(variations))):
            mock_products.append(AmazonProductCard(
                title=f"{keyword.title()} - {variations[i]} Edition",
                price=f"${rnd.choice(price_points):.2f}",
                rating=round(rnd.uniform(3.5, 4.8), 1),
                review_count=rnd.randint(100, 8000),
                is_best_seller=(i == 0),
                is_amazon_choice=(i == 1),
                url_suffix=f"/dp/B0EXAMPLE{i}",
            ))
        return mock_products
