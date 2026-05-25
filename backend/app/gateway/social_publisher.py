"""
统一社媒发布入口 — 按平台路由到不同 Gateway。

支持:
  - WordPress: Instagram / Facebook / Threads / Pinterest / TikTok
  - 小红书: XiaohongshuGateway (Playwright 浏览器模拟)

使用:
  publisher = SocialPublisher()
  result = await publisher.publish(post_data, product_context)
"""

import asyncio
from pathlib import Path
from typing import Optional

from backend.app.gateway.base import GatewayResult
from backend.app.gateway.wordpress_gateway import WordPressGateway
from backend.app.gateway.xiaohongshu_gateway import XiaohongshuGateway

# 平台 → Gateway 映射
WP_PLATFORMS = {"instagram", "facebook", "threads", "pinterest", "tiktok"}
XHS_PLATFORMS = {"xiaohongshu", "xhs", "小红书"}


class SocialPublisher:
    """统一社媒发布入口"""

    def __init__(self):
        self.wordpress: Optional[WordPressGateway] = None
        self.xiaohongshu: Optional[XiaohongshuGateway] = None
        self._xhs_started = False

    async def _get_wordpress(self) -> WordPressGateway:
        if self.wordpress is None:
            self.wordpress = WordPressGateway()
        return self.wordpress

    async def _get_xiaohongshu(self) -> XiaohongshuGateway:
        if self.xiaohongshu is None:
            self.xiaohongshu = XiaohongshuGateway()
        if not self._xhs_started:
            await self.xiaohongshu.start()
            self._xhs_started = True
        return self.xiaohongshu

    async def publish(self, post: dict, product_name: str = "",
                      category: str = "") -> GatewayResult:
        """
        根据 post 的 platform 字段路由到对应 Gateway。

        post 格式:
          {
            "platform": "instagram" | "xiaohongshu" | ...,
            "copy": "...",
            "hashtags": [...],
            "image_urls": [...],
            "short_copy": "..."
          }
        """
        platform = (post.get("platform") or "").lower().strip()
        copy_text = post.get("copy", "") or post.get("short_copy", "") or ""
        hashtags = post.get("hashtags", []) or []
        # 兼容两种图片格式: image_urls (list of str) 或 images (list of {url, ...})
        raw_img = post.get("image_urls") or post.get("images") or []
        if raw_img and isinstance(raw_img[0], dict):
            image_urls = [img.get("url", "") for img in raw_img if img.get("url")]
        else:
            image_urls = raw_img

        # 生成标题
        title = post.get("short_copy", "") or copy_text[:80]
        if not title and product_name:
            title = f"{product_name} - {platform.title()}"

        if platform in WP_PLATFORMS:
            wp = await self._get_wordpress()
            return await wp.publish_post(
                title=title,
                content=copy_text,
                image_urls=image_urls,
                status="publish",
            )

        elif platform in XHS_PLATFORMS:
            xhs = await self._get_xiaohongshu()
            # 下载远程图片到本地
            local_images = await self._download_images(image_urls)
            return await xhs.publish_post(
                title=title,
                content=copy_text,
                images=local_images,
                tags=hashtags,
            )

        else:
            return GatewayResult(
                success=False,
                status="error",
                errors=[f"Unsupported platform: {platform}"],
            )

    async def publish_batch(self, posts: list[dict],
                            product_name: str = "") -> list[GatewayResult]:
        """批量发布（串行，带间隔控制）"""
        results = []
        for i, post in enumerate(posts):
            result = await self.publish(post, product_name)
            results.append(result)

            # 发帖间隔 5-10 分钟（模拟人类）
            if i < len(posts) - 1:
                await asyncio.sleep(300)  # 5 min minimum
        return results

    async def _download_images(self, urls: list[str]) -> list[str]:
        """下载远程图片到本地临时目录，失败时记录日志并跳过"""
        import httpx
        import logging
        logger = logging.getLogger("social.publisher")
        _D = print  # debug helper — 确保输出到控制台

        local_paths = []
        tmp_dir = Path("data/tmp_images")
        tmp_dir.mkdir(parents=True, exist_ok=True)

        # 清空上轮旧图片
        for old in tmp_dir.glob("social_img_*"):
            try:
                old.unlink()
            except Exception:
                pass

        async with httpx.AsyncClient(timeout=60, follow_redirects=True, verify=False) as client:
            for i, url in enumerate(urls):
                if not url or "[image-gen]" in url:
                    print(f"[download] SKIP invalid URL: {url[:100] if url else 'None'}")
                    continue
                try:
                    print(f"[download] [{i}] fetching: {url[:150]}...")
                    resp = await client.get(url)
                    if resp.status_code == 200 and len(resp.content) > 500:
                        ext = ".jpg"
                        content_type = resp.headers.get("content-type", "")
                        if "png" in content_type:
                            ext = ".png"
                        elif "webp" in content_type:
                            ext = ".webp"

                        path = tmp_dir / f"social_img_{i}{ext}"
                        path.write_bytes(resp.content)
                        local_paths.append(str(path.as_posix()))
                        print(f"[download] [{i}] OK: {path} ({len(resp.content)} bytes)")
                    else:
                        print(f"[download] [{i}] FAIL: HTTP {resp.status_code} size={len(resp.content)}")
                except Exception as e:
                    print(f"[download] [{i}] EXCEPTION: {type(e).__name__}: {e}")
                    continue
        return local_paths

    async def stop(self):
        """关闭所有 gateway"""
        if self.xiaohongshu and self._xhs_started:
            await self.xiaohongshu.stop()
            self._xhs_started = False
