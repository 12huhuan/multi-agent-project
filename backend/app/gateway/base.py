"""执行网关基类 — 统一结果类型和错误处理"""

import asyncio
import time
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field


class GatewayResult(BaseModel):
    """所有 Gateway 方法返回的统一结果类型"""
    success: bool = False
    remote_id: str | None = None       # ASIN / post_id / campaign_id
    remote_url: str | None = None      # 外部可访问 URL
    status: str = "unknown"            # live | pending | draft | published | error
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    raw_response: dict | None = None   # 调试用


class GatewayError(Exception):
    """网关错误，携带 GatewayResult"""
    def __init__(self, result: GatewayResult):
        self.result = result
        super().__init__("; ".join(result.errors))


class GatewayBase(ABC):
    """
    网关基类，提供统一的重试和错误处理。

    所有对外部平台的 HTTP/MCP/REST 调用集中在这一层。
    Workflow 和 Agent 永远不直接调外部 API。
    """

    max_retries: int = 2
    retry_delay: float = 1.0
    gateway_name: str = "base"

    async def _retry(self, fn, *args, **kwargs) -> GatewayResult:
        """带指数退避的重试循环"""
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                result = await fn(*args, **kwargs)
                if result.success:
                    return result
                last_error = result
            except Exception as e:
                last_error = GatewayResult(
                    success=False,
                    status="error",
                    errors=[str(e)],
                )

            if attempt < self.max_retries:
                delay = self.retry_delay * (2 ** attempt)
                await asyncio.sleep(delay)

        return last_error or GatewayResult(
            success=False,
            status="error",
            errors=["max retries exceeded"],
        )

    def _ok(self, remote_id: str = "", remote_url: str = "",
            status: str = "published", raw: dict | None = None) -> GatewayResult:
        return GatewayResult(
            success=True,
            remote_id=remote_id,
            remote_url=remote_url,
            status=status,
            raw_response=raw,
        )

    def _fail(self, errors: list[str], warnings: list[str] | None = None,
              status: str = "error") -> GatewayResult:
        return GatewayResult(
            success=False,
            status=status,
            errors=errors,
            warnings=warnings or [],
        )
