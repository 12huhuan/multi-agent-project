"""WordPress Gateway — 通过自定义 REST API 发布内容"""

from backend.app.gateway.base import GatewayResult, GatewayBase
from backend.app.core.wordpress import get_wp_client


class WordPressGateway(GatewayBase):
    """封装已有的 WordPress REST API 客户端为 Gateway 接口"""
    gateway_name = "wordpress"

    async def publish_post(
        self, title: str, content: str, image_urls: list[str] | None = None,
        status: str = "publish",
    ) -> GatewayResult:
        wp = get_wp_client()

        async def _do():
            try:
                result = await wp.publish_social_post(
                    platform="wordpress",
                    copy_text=content,
                    hashtags=[],
                    image_urls=image_urls or [],
                    product_name=title,
                )
                return self._ok(
                    remote_id=str(result.get("wordpress_post_id", "")),
                    remote_url=result.get("wordpress_url", ""),
                    status=result.get("status", "published"),
                    raw=result,
                )
            except Exception as e:
                return self._fail([str(e)])

        return await self._retry(_do)

    async def health_check(self) -> bool:
        try:
            wp = get_wp_client()
            return await wp.test_connection()
        except Exception:
            return False
