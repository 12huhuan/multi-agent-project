"""
小红书登录脚本 — Playwright 打开浏览器，扫码登录后自动保存 Cookie。
运行: python scripts/xhs_login.py
"""
import asyncio
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COOKIES_FILE = DATA_DIR / "xhs_mcp_cookies.json"


async def main():
    from playwright.async_api import async_playwright

    print("正在启动浏览器...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = await context.new_page()

        print("正在打开小红书创作者中心登录页...")
        await page.goto("https://creator.xiaohongshu.com", wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # 如果当前是登录页，等用户扫码
        if "login" in page.url.lower():
            print("\n请在弹出的浏览器窗口中扫码登录小红书")
            print("登录成功后 Cookie 会自动保存，请勿关闭浏览器...\n")

            # 等待登录完成（最多等 5 分钟）
            for i in range(300):
                await asyncio.sleep(1)
                current_url = page.url.lower()
                if "creator" in current_url and "login" not in current_url:
                    print("检测到登录成功！正在保存 Cookie...")
                    await asyncio.sleep(2)  # 等 cookie 写稳
                    break
            else:
                print("\n超时：5 分钟内未完成登录，请重试")
                await browser.close()
                return
        else:
            print("已处于登录状态，直接保存 Cookie...")

        cookies = await context.cookies()
        COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        COOKIES_FILE.write_text(
            json.dumps(cookies, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Cookie 已保存到: {COOKIES_FILE}")
        print(f"共保存 {len(cookies)} 条 Cookie")

        await browser.close()
        print("浏览器已关闭，登录完成！")


if __name__ == "__main__":
    asyncio.run(main())
