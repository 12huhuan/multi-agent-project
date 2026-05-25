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

注意: 使用 sync Playwright API + run_in_executor 运行在线程池中，
避免 Windows asyncio ProactorEventLoop 子进程兼容问题。
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from backend.app.gateway.base import GatewayResult, GatewayBase, GatewayError

_log = logging.getLogger("xiaohongshu.gateway")

DATA_DIR = Path("data")
COOKIES_FILE = DATA_DIR / "xhs_mcp_cookies.json"

def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class XiaohongshuGateway(GatewayBase):
    gateway_name = "xiaohongshu"

    def __init__(self):
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._started = False

    # ── 对外 async 接口 ──────────────────────────

    async def start(self):
        if self._started:
            return
        if not COOKIES_FILE.exists():
            raise GatewayError(self._fail(["未找到登录Cookie，请先扫码登录"]))
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._start_sync)

    async def stop(self):
        # 半自动模式：浏览器保持打开让人工点击发布，不关闭
        pass

    async def publish_post(self, title: str, content: str,
                           images: list[str], tags: list[str]) -> GatewayResult:
        if not self._page:
            return self._fail(["浏览器未启动"])
        loop = asyncio.get_running_loop()
        ok, errors = await loop.run_in_executor(
            self._executor,
            self._publish_sync,
            title, content, images, tags,
        )
        if errors:
            return self._fail(errors)
        return ok

    async def get_published_posts(self, max_count: int = 10) -> list[dict]:
        if not self._page:
            return []
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            self._get_posts_sync,
            max_count,
        )

    # ── 同步实现（运行在 ThreadPoolExecutor 线程中）─

    def _start_sync(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=False,
            slow_mo=100,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        cookies = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
        self._context.add_cookies(cookies)
        self._page = self._context.new_page()
        self._page.goto("https://creator.xiaohongshu.com", wait_until="domcontentloaded")
        time.sleep(3)
        if "login" in self._page.url:
            raise RuntimeError("Cookie已过期")
        self._started = True

    def _switch_to_image_text_tab(self, p) -> bool:
        """多种策略切换到「上传图文」tab，返回是否成功"""
        strategies = [
            # 策略 1: class 选择器（旧版 XHS）
            lambda: p.locator('.creator-tab[data-hp-bound="1"]').nth(1).click(force=True, timeout=5000),
            # 策略 2: 包含"图文"文字的 tab 按钮
            lambda: p.locator('text=上传图文').first.click(timeout=5000),
            # 策略 3: 包含"图文"的任意元素
            lambda: p.locator('[class*="tab"]:has-text("图文")').first.click(force=True, timeout=5000),
            # 策略 4: 纯"图文"文字
            lambda: p.locator('text=图文').first.click(timeout=5000),
            # 策略 5: 通过 JS 直接点击第二个 tab（兜底）
            lambda: p.evaluate('() => { const tabs = document.querySelectorAll(\'[class*="tab"]\'); for (const t of tabs) { if (t.textContent.includes("图文")) { t.click(); return true; } } return false; }'),
        ]
        for i, strategy in enumerate(strategies):
            try:
                result = strategy()
                if result is None or result:
                    time.sleep(2)
                    # 验证是否成功：检查是否有上传区域出现
                    if p.locator('input[type="file"]').count() > 0:
                        return True
            except Exception:
                continue
        return False

    def _publish_sync(self, title: str, content: str,
                      images: list[str], tags: list[str]):
        p = self._page
        errors = []

        try:
            # 1. 导航到创作者中心，点发布笔记
            p.goto("https://creator.xiaohongshu.com", wait_until="domcontentloaded")
            time.sleep(3)

            # 点击「发布笔记」按钮 — 尝试多种选择器
            try:
                p.locator("text=发布笔记").first.click()
            except Exception:
                try:
                    p.locator('[class*="publish"]:has-text("发布")').first.click()
                except Exception:
                    p.locator('span:has-text("发布笔记")').first.click()
            time.sleep(5)

            # 2. 切换到上传图文 tab（多策略 fallback）
            self._switch_to_image_text_tab(p)
            time.sleep(2)

            # 3. 上传图片
            valid = [i for i in (images or []) if Path(i).exists()]
            print(f"[xhs] images passed: {len(images or [])} URLs → {len(valid)} local files")
            for v in valid:
                print(f"[xhs]   {v} ({Path(v).stat().st_size} bytes)")
            if not valid:
                print("[xhs] NO valid images — using gray placeholder")
                from PIL import Image
                ph = DATA_DIR / "xhs_placeholder.jpg"
                if not ph.exists():
                    Image.new("RGB", (800, 800), color=(200, 200, 200)).save(ph)
                valid = [str(ph.absolute())]
            try:
                p.locator('input[type="file"]').first.set_input_files(valid)
                _log.info(f"图片已上传到小红书: {len(valid)} 张")
            except Exception as e:
                _log.error(f"图片上传失败: {e}")
            time.sleep(10)

            # 4. 填标题（最多 20 字）— 多策略 fallback
            time.sleep(1)
            try:
                p.locator('input[placeholder*="标题"]').first.click()
            except Exception:
                try:
                    p.locator('[class*="title"] input').first.click()
                except Exception:
                    p.locator('input').first.click()
            time.sleep(0.3)
            p.keyboard.type(title[:20], delay=30)

            # 5. 填正文 — 多策略 fallback
            time.sleep(0.5)
            try:
                p.locator('[contenteditable="true"]').first.click()
            except Exception:
                try:
                    p.locator('[class*="editor"]').first.click()
                except Exception:
                    p.locator('[placeholder*="正文"]').first.click()
            time.sleep(0.3)
            for line in content.split("\n"):
                if line.strip():
                    p.keyboard.type(line.strip(), delay=20)
                    p.keyboard.press("Enter")

            # 6. 加标签
            if tags:
                time.sleep(1)
                p.keyboard.press("Enter")
                for t in tags[:10]:
                    clean = t.lstrip("#").strip()
                    if clean:
                        p.keyboard.type(f"#{clean} ", delay=15)

            time.sleep(2)

            # 滚动到底部让发布按钮可见
            p.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)

            return (
                self._ok(
                    status="ready",
                    remote_url="https://creator.xiaohongshu.com/publish/publish",
                    raw={"message": "内容已填好，请在打开的浏览器中点击「发布」按钮"},
                ),
                [],
            )
        except Exception as e:
            self._save_screenshot("xhs_publish_error")
            return (None, [str(e)])

    def _get_posts_sync(self, max_count: int) -> list[dict]:
        try:
            self._page.goto(
                "https://creator.xiaohongshu.com/publish/publish",
                wait_until="domcontentloaded",
            )
            time.sleep(3)

            cards = self._page.locator(".note-item, .publish-card, [class*='note']")
            count = cards.count()
            posts = []
            for i in range(min(count, max_count)):
                try:
                    card = cards.nth(i)
                    title_el = card.locator("[class*='title'], .note-title")
                    title = title_el.first.inner_text() if title_el.count() > 0 else ""
                    posts.append({"index": i, "title": title.strip()})
                except Exception:
                    continue
            return posts
        except Exception:
            return []

    def _save_screenshot(self, label: str = "debug"):
        """保存截图用于调试"""
        try:
            if self._page:
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                path = DATA_DIR / f"xhs_{label}_{stamp}.png"
                self._page.screenshot(path=str(path), full_page=False)
        except Exception:
            pass

    @staticmethod
    def is_logged_in() -> bool:
        return COOKIES_FILE.exists()
