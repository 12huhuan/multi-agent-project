"""应用配置 — 从环境变量加载，支持 .env 文件覆盖"""

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Cross-Border Agents API"
    version: str = "1.0.0"
    debug: bool = False

    # LLM
    llm_provider: str = "openai"  # openai | anthropic | deepseek
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_model_simple: str = "deepseek-chat"  # 简单意图用
    llm_temperature: float = 0.3
    llm_max_tokens: int = 4096

    # Database
    database_url: str = "postgresql+asyncpg://cv_user:cv_pass_2026@localhost:5432/crossborder"
    database_url_sync: str = "postgresql://cv_user:cv_pass_2026@localhost:5432/crossborder"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Embedding (Qwen DashScope)
    embedding_api_key: str = ""

    # ChromaDB (向量数据库)
    chroma_persist_dir: str = "./chroma_data"
    chroma_collection_name: str = "knowledge_base"

    # Security
    secret_key: str = "cb-agents-secret-change-in-production"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Rate limiting
    api_rate_limit: str = "100/minute"

    model_config = {
        "extra": "ignore",
        "env_file": os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"),
        "env_file_encoding": "utf-8",
    }


settings = Settings()
