"""知识库管理 API 路由 — PostgreSQL 存储 + Qwen 向量检索。支持 Markdown / PDF / URL。"""

import io
import uuid
from datetime import datetime

import requests as http_requests
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from PyPDF2 import PdfReader
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.db import get_db
from backend.app.core.vector_store import get_vector_store
from backend.app.models.models import KnowledgeDocument
from backend.app.schemas.schemas import (
    KnowledgeDocCreate,
    KnowledgeDocResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge_base"])


async def _save_and_index(title: str, content: str, source_type: str, source_url: str | None, db: AsyncSession) -> KnowledgeDocResponse:
    """保存文档到 PostgreSQL 并索引到 ChromaDB"""
    doc = KnowledgeDocument(
        title=title,
        source_type=source_type,
        source_url=source_url,
        content=content,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    store = get_vector_store()
    doc.chunk_count = store.add(
        doc_id=str(doc.id),
        content=content,
        title=title,
        source_type=source_type,
    )
    await db.commit()
    await db.refresh(doc)

    return KnowledgeDocResponse(
        id=doc.id,
        title=doc.title,
        source_type=doc.source_type,
        source_url=doc.source_url,
        chunk_count=doc.chunk_count,
        created_at=doc.created_at,
    )


@router.post("/documents", response_model=KnowledgeDocResponse)
async def upload_document(request: KnowledgeDocCreate, db: AsyncSession = Depends(get_db)):
    """上传 Markdown / Text 文档"""
    return await _save_and_index(request.title, request.content, request.source_type, request.source_url, db)


@router.post("/documents/upload", response_model=KnowledgeDocResponse)
async def upload_file(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """上传文件 — 支持 .md .txt .pdf"""
    content_bytes = await file.read()
    filename = file.filename or "uploaded_file"

    if filename.lower().endswith(".pdf"):
        text = _parse_pdf(content_bytes)
        source_type = "pdf"
    else:
        try:
            text = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="仅支持 UTF-8 文本文件及 PDF")
        source_type = "markdown" if filename.endswith(".md") else "text"

    if not text.strip():
        raise HTTPException(status_code=400, detail="无法从文件中提取文本内容")

    return await _save_and_index(filename, text, source_type, None, db)


@router.post("/documents/import-url", response_model=KnowledgeDocResponse)
async def import_url(url: str, db: AsyncSession = Depends(get_db)):
    """导入网页内容"""
    try:
        resp = http_requests.get(url, timeout=15, headers={"User-Agent": "CrossBorder-Agents/1.0"})
        resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法获取 URL: {e}")

    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned = "\n\n".join(lines)

    if not cleaned.strip():
        raise HTTPException(status_code=400, detail="网页内容为空")

    title = soup.title.string.strip() if soup.title else url
    return await _save_and_index(title, cleaned, "url", url, db)


def _parse_pdf(content_bytes: bytes) -> str:
    """从 PDF 字节中提取文本"""
    reader = PdfReader(io.BytesIO(content_bytes))
    pages = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            pages.append(t)
    return "\n\n".join(pages)


@router.get("/documents", response_model=list[KnowledgeDocResponse])
async def list_documents(db: AsyncSession = Depends(get_db)):
    """文档列表"""
    result = await db.execute(select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc()))
    docs = result.scalars().all()
    return [
        KnowledgeDocResponse(
            id=d.id,
            title=d.title,
            source_type=d.source_type,
            source_url=d.source_url,
            chunk_count=d.chunk_count,
            created_at=d.created_at,
        )
        for d in docs
    ]


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    """删除文档"""
    result = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await db.execute(delete(KnowledgeDocument).where(KnowledgeDocument.id == doc_id))
    await db.commit()

    get_vector_store().delete_doc(doc_id)
    return {"deleted": doc_id}


@router.get("/vectors")
async def inspect_vectors(limit: int = 50, offset: int = 0):
    """查看向量存储详情 — 文档片段 + 元数据预览"""
    store = get_vector_store()
    col = store._get_collection()
    total = col.count()

    r = col.get(limit=limit, offset=offset, include=["documents", "metadatas"])
    items = []
    for i, doc_id in enumerate(r.get("ids", [])):
        meta = r["metadatas"][i] if r.get("metadatas") else {}
        text = r["documents"][i] if r.get("documents") else ""
        items.append({
            "chunk_id": doc_id,
            "doc_id": meta.get("doc_id", ""),
            "source": meta.get("source_title", ""),
            "source_type": meta.get("source_type", ""),
            "content_preview": text[:200],
        })

    return {
        "total_vectors": total,
        "offset": offset,
        "limit": limit,
        "items": items,
    }


@router.post("/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(request: KnowledgeSearchRequest):
    """向量检索知识库（无需 DB，纯向量匹配）"""
    results = get_vector_store().query(request.query, top_k=request.top_k)
    return KnowledgeSearchResponse(query=request.query, results=results)
