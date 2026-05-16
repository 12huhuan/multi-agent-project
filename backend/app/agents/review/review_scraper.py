"""
评论抓取 Agent — 抓取 Amazon 商品评论。

支持真实 web-scraping MCP 调用和模拟数据回退（开发/演示模式）。
"""

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent


class ReviewScraperInput(BaseModel):
    product_asin: str = Field(..., min_length=1, description="Amazon ASIN 或产品 URL")
    platform: str = "amazon_us"
    max_reviews: int = Field(default=20, ge=1, le=100)
    min_rating: int = Field(default=1, ge=1, le=5)


class ScrapedReview(BaseModel):
    reviewer_name: str = ""
    rating: float = 0.0
    title: str = ""
    content: str = ""
    date: str = ""
    verified_purchase: bool = False
    helpful_count: int = 0
    variant_info: str = ""


class ReviewScraperOutput(BaseModel):
    product_asin: str = ""
    reviews: list[ScrapedReview] = Field(default_factory=list)
    total_scraped: int = 0
    source: str = "simulated"  # "live" | "simulated"


class ReviewScraperAgent(BaseAgent[ReviewScraperInput, ReviewScraperOutput]):
    name = "review_scraper"
    description = "抓取 Amazon 商品评论，支持 web-scraping MCP 或模拟数据"

    def build_prompt(self, input_data: ReviewScraperInput, context: dict | None = None) -> tuple[str, str]:
        return "", ""  # 抓取类 Agent 不需要 LLM prompt

    async def run(self, input_data: ReviewScraperInput, context: dict | None = None) -> ReviewScraperOutput:
        import time
        start = time.time()

        # 尝试调用 web-scraping MCP
        reviews = await self._try_mcp_scrape(input_data)

        if not reviews:
            # 回退：生成模拟评论数据（开发/演示用）
            reviews = self._generate_mock_reviews(input_data)

        duration_ms = int((time.time() - start) * 1000)
        result = ReviewScraperOutput(
            product_asin=input_data.product_asin,
            reviews=reviews,
            total_scraped=len(reviews),
            source="simulated",
        )

        tid = context.get("task_id") if context else None
        if tid:
            await self.log_execution(tid, input_data, result, 0, duration_ms)

        return result

    async def _try_mcp_scrape(self, input_data: ReviewScraperInput) -> list[ScrapedReview]:
        """尝试通过 web-scraping MCP 抓取真实评论。不可用时返回空列表。"""
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            import asyncio

            server_params = StdioServerParameters(
                command="npx", args=["-y", "webscraping-ai-mcp"]
            )

            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    url = input_data.product_asin
                    if not url.startswith("http"):
                        url = f"https://www.amazon.com/dp/{input_data.product_asin}"

                    result = await session.call_tool("scrape", {"url": url})
                    if result and result.content:
                        return self._parse_scraped_content(result.content[0].text, input_data.max_reviews)
        except Exception:
            pass
        return []

    def _parse_scraped_content(self, html: str, max_reviews: int) -> list[ScrapedReview]:
        """从抓取的 HTML 中解析评论（简化版）"""
        import re
        reviews = []
        # 简单的正则提取，生产环境应使用 BeautifulSoup
        review_blocks = re.findall(r'data-hook="review"[^>]*>(.*?)(?=data-hook="review"|$)', html, re.DOTALL)
        for block in review_blocks[:max_reviews]:
            rating_match = re.search(r'(\d\.\d|\d)\s*out of', block)
            title_match = re.search(r'data-hook="review-title"[^>]*>(.*?)</', block)
            body_match = re.search(r'data-hook="review-body"[^>]*>(.*?)</', block)
            author_match = re.search(r'data-hook="genome-widget"[^>]*>(.*?)</', block)
            reviews.append(ScrapedReview(
                reviewer_name=author_match.group(1).strip() if author_match else "Anonymous",
                rating=float(rating_match.group(1)) if rating_match else 3.0,
                title=title_match.group(1).strip() if title_match else "",
                content=body_match.group(1).strip() if body_match else "",
            ))
        return reviews

    def _generate_mock_reviews(self, input_data: ReviewScraperInput) -> list[ScrapedReview]:
        """生成模拟评论数据用于开发演示"""
        import random
        mock_templates = [
            ("Great product, exactly as described!", 5, "Sarah M.", True),
            ("Works well but packaging could be better. The product itself is fine.", 4, "John D.", True),
            ("Not bad for the price. Delivery was fast.", 4, "Mike R.", True),
            ("Disappointed with the quality. Stopped working after 2 weeks.", 1, "Emily K.", True),
            ("Amazing value! Better than expected. Will buy again.", 5, "Lisa T.", False),
            ("Color doesn't match the photos. Returning it.", 2, "David P.", True),
            ("Good quality but a bit small. Check dimensions before buying.", 3, "Anna W.", True),
            ("Perfect gift for my friend. She loved it!", 5, "Chris B.", False),
            ("Arrived damaged. The box was crushed.", 2, "Maria G.", True),
            ("Five stars! Fast shipping and great customer service.", 5, "James L.", True),
            ("It's okay. Nothing special but does the job.", 3, "Kevin N.", False),
            ("The instructions were unclear. Took a while to figure out.", 3, "Rachel H.", True),
            ("Defective unit. Doesn't turn on.", 1, "Tom S.", True),
            ("So happy with this purchase! Highly recommend.", 5, "Jessica W.", False),
            ("Lasted about 6 months before breaking. For the price, I guess it's fine.", 3, "Robert C.", True),
        ]

        random.shuffle(mock_templates)
        count = min(input_data.max_reviews, len(mock_templates))

        return [
            ScrapedReview(
                reviewer_name=t[2],
                rating=t[1],
                title=t[0].split(".")[0],
                content=t[0],
                date="2026-05-{}".format(random.randint(1, 15)),
                verified_purchase=t[3],
                helpful_count=random.randint(0, 15),
            )
            for t in mock_templates[:count]
        ]
