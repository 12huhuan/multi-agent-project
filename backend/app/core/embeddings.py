"""
Embedding 函数 — 基于 DashScope Qwen text-embedding-v3 API。

ChromaDB EmbeddingFunction 兼容接口，调用 Qwen 远端嵌入模型。
使用 requests（非 httpx）确保 ChromaDB 线程环境下稳定。
"""

from typing import Optional

import numpy as np
import requests

QWEN_EMBEDDING_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
QWEN_EMBEDDING_MODEL = "text-embedding-v3"


class QwenEmbeddingFunction:
    """ChromaDB 兼容的嵌入函数 — 调用 Qwen DashScope API"""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, dim: Optional[int] = None):
        self._api_key_override = api_key
        self.model = model or QWEN_EMBEDDING_MODEL
        self.dim = dim or 1024

    def name(self) -> str:
        return f"qwen-{self.model}"

    def embed_query(self, input) -> list[list[float]]:
        """ChromaDB HTTP client 要求的单条查询接口。兼容 str 和 list[str]。"""
        if isinstance(input, list):
            return self(input)
        return self([input])

    def embed_documents(self, input) -> list[list[float]]:
        """ChromaDB HTTP client 要求的批量接口"""
        if not isinstance(input, list):
            input = [input]
        return self(input)

    def _api_key(self) -> str:
        if self._api_key_override:
            return self._api_key_override
        from backend.app.core.config import settings
        return settings.embedding_api_key

    def __call__(self, input: list[str]) -> list[list[float]]:
        """ChromaDB 调用接口: (list[str]) -> list[list[float]]。参数名必须是 input。"""
        if not input:
            return []

        resp = requests.post(
            QWEN_EMBEDDING_URL,
            json={
                "model": self.model,
                "input": input,
                "dimensions": self.dim,
            },
            headers={
                "Authorization": f"Bearer {self._api_key()}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )

        if resp.status_code != 200:
            raise RuntimeError(f"Qwen embedding API error {resp.status_code}: {resp.text[:500]}")

        body = resp.json()
        items = sorted(body["data"], key=lambda x: x["index"])
        return [np.array(item["embedding"], dtype=np.float32) for item in items]


_ef_instance: Optional[QwenEmbeddingFunction] = None


def get_embedding_function() -> QwenEmbeddingFunction:
    global _ef_instance
    if _ef_instance is None:
        _ef_instance = QwenEmbeddingFunction()
    return _ef_instance
