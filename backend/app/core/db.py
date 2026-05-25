"""数据库连接管理 — SQLAlchemy async + PostgreSQL"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.app.core.config import settings

engine = create_async_engine(settings.database_url, echo=settings.debug, pool_size=20, max_overflow=10)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """创建所有表（开发环境使用，生产用 alembic）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def run_migrations():
    """幂等迁移：补齐 Phase 2/3 新增列和表"""
    async with engine.begin() as conn:
        # listing_tasks 新增生成结果列
        for col, col_type in [
            ("keywords", "JSONB DEFAULT '[]'"),
            ("top_keywords", "JSONB DEFAULT '[]'"),
            ("title_candidates", "JSONB DEFAULT '[]'"),
            ("bullet_points", "JSONB DEFAULT '[]'"),
            ("description_html", "TEXT DEFAULT ''"),
            ("a_plus_modules", "JSONB DEFAULT '[]'"),
            ("seo_report", "JSONB DEFAULT '{}'"),
            ("product_images", "JSONB DEFAULT '[]'"),
        ]:
            await conn.execute(text(
                f"ALTER TABLE listing_tasks ADD COLUMN IF NOT EXISTS {col} {col_type}"
            ))
        # orchestrator_runs 表 — 持久化调度结果
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS orchestrator_runs (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                action VARCHAR(50) DEFAULT 'auto',
                category VARCHAR(200),
                target_market VARCHAR(10),
                context JSONB DEFAULT '{}',
                status VARCHAR(30) DEFAULT 'running',
                progress VARCHAR(200),
                decisions JSONB DEFAULT '[]',
                summary TEXT,
                total_steps INTEGER DEFAULT 0,
                completed_steps INTEGER DEFAULT 0,
                error TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        # social_images 表
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS social_images (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                post_id UUID REFERENCES social_posts(id) ON DELETE CASCADE,
                url TEXT DEFAULT '',
                alt_text TEXT,
                prompt TEXT,
                storage_path TEXT,
                width INTEGER,
                height INTEGER,
                format TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
