"""
小红书发布 Gateway — Playwright 自动填充内容，人工最后点击发布。

已验证 (2025-05-17):
  1. 导航到创作者中心 ✅
  2. 点击侧边栏"发布笔记" ✅
  3. JS 切换到上传图文 tab ✅
  4. 上传图片 ✅
  5. 填标题（keyboard.type 模拟打字）✅
  6. 填正文（keyboard.type 模拟打字）✅
  7. 点击发布 ❌ (xhs-publish-btn 使用 closed Shadow DOM，自动化无法穿透)

半自动方案: 自动完成 1-6，浏览器窗口保持打开，用户手动点击发布。
"""

import asyncio, json
from pathlib import Path
from datetime import datetime, timezone
from backend.app.gateway.base import GatewayResult, GatewayBase, GatewayError

DATA_DIR = Path("data")
COOKIES_FILE = DATA_DIR / "xhs_mcp_cookies.json"

def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

class XiaohongshuGateway(GatewayBase):
    gateway_name = "xiaohongshu"

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    async def start(self):
        from playwright.async_api import async_playwright
        if not COOKIES_FILE.exists():
            raise GatewayError(self._fail(["未找到登录Cookie，请先扫码登录"]))
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=False, slow_mo=100,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1440, "height": 900}, locale="zh-CN",
        )
        cookies = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
        await self._context.add_cookies(cookies)
        self._page = await self._context.new_page()
        await self._page.goto("https://creator.xiaohongshu.com", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        if "login" in self._page.url:
            raise GatewayError(self._fail(["Cookie已过期"]))

    async def stop(self):
        # XHS 采用半自动模式：内容填好后浏览器保持打开
        # 让用户手动点击发布，因此 stop() 不关闭浏览器
        pass

    async def publish_post(self, title: str, content: str,
                           images: list[str], tags: list[str]) -> GatewayResult:
        if not self._page:
            return self._fail(["浏览器未启动"])

        async def _do():
            p = self._page
            # 1. 点侧边栏发布笔记
            await p.goto("https://creator.xiaohongshu.com", wait_until="domcontentloaded")
            await asyncio.sleep(3)
            await p.locator("text=发布笔记").first.click()
            await asyncio.sleep(4)
            # 2. 切上传图文
            tabs = p.locator('.creator-tab[data-hp-bound="1"]')
            if await tabs.count() > 1:
                await tabs.nth(1).click(force=True, timeout=5000)
            await asyncio.sleep(3)
            # 3. 上传图片
            valid = [i for i in (images or []) if Path(i).exists()]
            if not valid:
                from PIL import Image
                ph = DATA_DIR / "xhs_placeholder.jpg"
                if not ph.exists():
                    Image.new("RGB", (800, 800), color=(200, 200, 200)).save(ph)
                valid = [str(ph.absolute())]
            await p.locator('input[type="file"]').first.set_input_files(valid)
            await asyncio.sleep(10)
            # 4. 填标题
            await p.locator('input[placeholder*="标题"]').first.click()
            await asyncio.sleep(0.3)
            await p.keyboard.type(title[:20], delay=30)
            # 5. 填正文
            await p.locator('[contenteditable="true"]').first.click()
            await asyncio.sleep(0.3)
            for line in content.split("\n"):
                if line.strip():
                    await p.keyboard.type(line.strip(), delay=20)
                    await p.keyboard.press("Enter")
            # 6. 加标签
            if tags:
                await asyncio.sleep(1)
                await p.keyboard.press("Enter")
                for t in tags[:10]:
                    clean = t.lstrip("#").strip()
                    if clean:
                        await p.keyboard.type(f"#{clean} ", delay=15)
            await asyncio.sleep(2)

            # 滚动到底部让发布按钮可见
            await p.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)

            return self._ok(status="ready",
                           remote_url="https://creator.xiaohongshu.com/publish/publish",
                           raw={"message": "内容已填好，请在打开的浏览器中点击「发布」按钮。发布完成后手动关闭浏览器窗口。"})
        return await self._retry(_do)

    @staticmethod
    def is_logged_in() -> bool:
        return COOKIES_FILE.exists()
