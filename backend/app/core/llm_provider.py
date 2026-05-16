"""LLM Provider 可拔插抽象层

支持 OpenAI / Anthropic / DeepSeek / 本地模型，
通过统一接口切换，不锁定厂商。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from backend.app.core.config import settings


@dataclass
class LLMResponse:
    content: str
    model: str
    tokens_used: int = 0
    finish_reason: str = "stop"


class BaseLLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> LLMResponse:
        """同步对话，返回完整响应"""

    @abstractmethod
    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        """流式对话，逐 token 返回"""


class OpenAICompatibleProvider(BaseLLMProvider):
    """通用 OpenAI 兼容接口 — 适配 DeepSeek / Qwen / vLLM / Ollama 等"""

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        model: str = "",
    ):
        import httpx

        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self._client = httpx.AsyncClient(timeout=120.0)

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def chat(self, messages: list[dict], **kwargs) -> LLMResponse:
        resp = await self._client.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": kwargs.get("model", self.model),
                "messages": messages,
                "temperature": kwargs.get("temperature", settings.llm_temperature),
                "max_tokens": kwargs.get("max_tokens", settings.llm_max_tokens),
            },
            headers=self._headers(),
        )
        resp.raise_for_status()
        body = resp.json()
        choice = body["choices"][0]
        content = choice["message"].get("content") or ""
        return LLMResponse(
            content=content,
            model=body.get("model", self.model),
            tokens_used=body.get("usage", {}).get("total_tokens", 0),
            finish_reason=choice.get("finish_reason", "stop"),
        )

    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        async with self._client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            json={
                "model": kwargs.get("model", self.model),
                "messages": messages,
                "temperature": kwargs.get("temperature", settings.llm_temperature),
                "max_tokens": kwargs.get("max_tokens", settings.llm_max_tokens),
                "stream": True,
            },
            headers=self._headers(),
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    import json
                    chunk = json.loads(data)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    if content := delta.get("content"):
                        yield content

    async def close(self):
        await self._client.aclose()


def get_llm() -> BaseLLMProvider:
    """工厂函数 — 根据配置返回对应的 LLM Provider"""
    return OpenAICompatibleProvider()
