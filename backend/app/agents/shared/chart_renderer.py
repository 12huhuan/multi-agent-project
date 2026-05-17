"""
图表渲染器 — 通过 mcp-server-chart (AntV) 生成可视化图表。

直接命令行测试通过，返回真实图片 URL。
使用 MCP stdio_client（已验证在 Windows 环境可用）。
"""

import asyncio
import json
from typing import Optional


def _to_category_value(data: dict[str, float]) -> list[dict]:
    return [{"category": k, "value": v} for k, v in data.items()]


class ChartRenderer:
    """通过 AntV mcp-server-chart 生成图表"""

    async def _call_tool(self, tool_name: str, arguments: dict) -> Optional[str]:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            server_params = StdioServerParameters(
                command="npx",
                args=["-y", "@antv/mcp-server-chart"],
            )

            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    if result and result.content:
                        text = result.content[0].text
                        # URL 可能直接返回或包在 JSON 里
                        if text.startswith("http"):
                            return text.strip()
                        try:
                            data = json.loads(text)
                            return data.get("url") or data.get("image_url") or str(data)
                        except (json.JSONDecodeError, TypeError):
                            return text.strip()
        except Exception as e:
            import logging
            logging.getLogger("chart_renderer").error(f"Chart generation failed: {e}")
        return None

    async def bar_chart(self, title: str, data: dict[str, float]) -> Optional[str]:
        return await self._call_tool("generate_bar_chart", {
            "title": title, "data": _to_category_value(data),
        })

    async def column_chart(self, title: str, data: dict[str, float]) -> Optional[str]:
        return await self._call_tool("generate_column_chart", {
            "title": title, "data": _to_category_value(data),
        })

    async def pie_chart(self, title: str, data: dict[str, float]) -> Optional[str]:
        return await self._call_tool("generate_pie_chart", {
            "title": title, "data": _to_category_value(data),
        })

    async def line_chart(self, title: str, data: dict[str, list]) -> Optional[str]:
        return await self._call_tool("generate_line_chart", {
            "title": title,
            "data": [{"category": k, "value": v} for k, v in data.items()],
        })

    async def radar_chart(self, title: str, axes: list[str],
                           series: dict[str, list[float]]) -> Optional[str]:
        return await self._call_tool("generate_radar_chart", {
            "title": title,
            "data": {"axes": axes, "series": [{"name": k, "data": v} for k, v in series.items()]},
        })

    async def word_cloud(self, title: str, data: dict[str, float]) -> Optional[str]:
        return await self._call_tool("generate_word_cloud_chart", {
            "title": title, "data": _to_category_value(data),
        })


_renderer: Optional[ChartRenderer] = None


async def get_renderer() -> ChartRenderer:
    global _renderer
    if _renderer is None:
        _renderer = ChartRenderer()
    # 每次返回新实例避免 context manager 状态问题
    return ChartRenderer()
