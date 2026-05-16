"""企微通知工具 — 通过 wecom-bot MCP 发送消息"""

import asyncio
import json


async def send_wecom_message(content: str, msg_type: str = "text") -> bool:
    """通过 wecom-bot MCP 发送企微群消息"""
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server_params = StdioServerParameters(
            command="npx",
            args=["-y", "wecom-bot-mcp-server"],
        )

        async with asyncio.timeout(10):
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool("send_message", {
                        "content": content,
                        "msg_type": msg_type,
                    })
                    return result is not None
    except Exception:
        return False


def send_wecom_sync(content: str) -> bool:
    """同步版本（用于不需要 await 的上下文）"""
    try:
        return asyncio.run(send_wecom_message(content))
    except Exception:
        return False
