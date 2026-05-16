"""
向量存储 — ChromaDB HTTP 客户端模式（Docker 部署），持久化向量索引。

连接 Docker chromadb/chroma 容器，避开 Windows 本地 C 扩展问题。
Qwen embedding 做语义编码，向量持久存在 ChromaDB 中，重启不丢失。
"""

from typing import Optional

import chromadb
from chromadb.api.types import EmbeddingFunction

from backend.app.core.embeddings import get_embedding_function

CHROMA_HOST = "localhost"
CHROMA_PORT = 8001
COLLECTION_NAME = "knowledge_base"


class VectorStore:
    """ChromaDB HTTP 客户端封装"""

    def __init__(self):
        self._client: Optional[chromadb.HttpClient] = None
        self._col: Optional[chromadb.Collection] = None
        self._ef: Optional[EmbeddingFunction] = None

    @property
    def client(self) -> chromadb.HttpClient:
        if self._client is None:
            self._client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        return self._client

    @property
    def ef(self) -> EmbeddingFunction:
        if self._ef is None:
            self._ef = get_embedding_function()
        return self._ef

    def _get_collection(self) -> chromadb.Collection:
        if self._col is not None:
            try:
                self._col.count()
                return self._col
            except Exception:
                self._col = None

        self._col = self.client.get_or_create_collection(COLLECTION_NAME, embedding_function=self.ef)
        return self._col

    def add(self, doc_id: str, content: str, title: str = "", source_type: str = "") -> int:
        """文档分块并存储到 ChromaDB。返回 chunk 数量。"""
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        if not paragraphs:
            return 0

        col = self._get_collection()
        chunk_ids = [f"{doc_id}_chunk_{i}" for i in range(len(paragraphs))]
        col.add(
            documents=paragraphs,
            metadatas=[{"source_title": title, "source_type": source_type, "doc_id": doc_id}] * len(paragraphs),
            ids=chunk_ids,
        )
        return len(paragraphs)

    def query(self, query_text: str, top_k: int = 5) -> list[dict]:
        """向量检索 Top-K。"""
        try:
            col = self._get_collection()
            results = col.query(query_texts=[query_text], n_results=top_k, include=["metadatas", "documents", "distances"])

            items = []
            if results and results.get("ids") and results["ids"][0]:
                for i, chunk_id in enumerate(results["ids"][0]):
                    items.append({
                        "chunk_id": chunk_id,
                        "content": results["documents"][0][i] if results.get("documents") else "",
                        "score": round(1.0 - (results["distances"][0][i] if results.get("distances") else 0.0), 4),
                        "source": results.get("metadatas", [[{}]])[0][i].get("source_title", ""),
                        "source_type": results.get("metadatas", [[{}]])[0][i].get("source_type", ""),
                    })
            return items
        except Exception:
            return []

    def delete_doc(self, doc_id: str):
        """删除文档的所有 chunk。"""
        try:
            col = self._get_collection()
            # 获取该文档的所有 chunk IDs
            results = col.get(where={"doc_id": doc_id})
            if results and results.get("ids"):
                col.delete(ids=results["ids"])
        except Exception:
            pass


# 全局单例
_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store
