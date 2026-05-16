"""知识检索 Agent (RAG) — Qwen 向量语义检索。

输入: 意图 + 用户问题 + 产品上下文
输出: Top-K 相关文档片段
"""

from pydantic import BaseModel, Field

from backend.app.agents.base import BaseAgent


class KnowledgeRetrievalInput(BaseModel):
    query: str
    intent: str = "other"
    product_context: dict = Field(default_factory=dict)
    top_k: int = 5


class KnowledgeChunk(BaseModel):
    chunk_id: str = ""
    content: str = ""
    score: float = 0.0
    source_title: str = ""
    source_type: str = ""


class KnowledgeRetrievalOutput(BaseModel):
    chunks: list[KnowledgeChunk] = Field(default_factory=list)
    query_rewrite: str = ""
    retrieval_method: str = "semantic_vector"


class KnowledgeRetrievalAgent(BaseAgent[KnowledgeRetrievalInput, KnowledgeRetrievalOutput]):
    name = "knowledge_retrieval"
    description = "基于 Qwen 向量的语义检索，返回 Top-K 相关文档片段"

    def build_prompt(self, input_data: KnowledgeRetrievalInput, context: dict | None = None) -> tuple[str, str]:
        return "", ""

    async def run(self, input_data: KnowledgeRetrievalInput, context: dict | None = None) -> KnowledgeRetrievalOutput:
        import time
        start = time.time()

        chunks = []
        try:
            from backend.app.core.vector_store import get_vector_store
            store = get_vector_store()
            results = store.query(input_data.query, top_k=input_data.top_k)
            for r in results:
                chunks.append(KnowledgeChunk(
                    chunk_id=r["chunk_id"],
                    content=r["content"],
                    score=r["score"],
                    source_title=r["source"],
                    source_type=r.get("source_type", ""),
                ))
        except Exception:
            pass

        duration_ms = int((time.time() - start) * 1000)
        result = KnowledgeRetrievalOutput(
            chunks=chunks,
            query_rewrite=input_data.query,
            retrieval_method="semantic_vector",
        )

        if context and "task_id" in context:
            await self.log_execution(context["task_id"], input_data, result, 0, duration_ms)

        return result
