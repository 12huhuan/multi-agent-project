-- Cross-Border Agents — 初始化 SQL
-- Phase 1: Listing 任务 + 客服会话

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS vector;  -- pgvector

-- Listing 任务
CREATE TABLE IF NOT EXISTS listing_tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    target_platform TEXT NOT NULL DEFAULT 'amazon_us',
    target_language TEXT NOT NULL DEFAULT 'en',
    features JSONB DEFAULT '[]',
    brand_story TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    keywords JSONB DEFAULT '[]',
    top_keywords JSONB DEFAULT '[]',
    title_candidates JSONB DEFAULT '[]',
    bullet_points JSONB DEFAULT '[]',
    description_html TEXT DEFAULT '',
    a_plus_modules JSONB DEFAULT '[]',
    seo_report JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Agent 执行记录
CREATE TABLE IF NOT EXISTS agent_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES listing_tasks(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    input_summary TEXT,
    output JSONB DEFAULT '{}',
    tokens_used INTEGER DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 客服会话
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'web_chat',
    language TEXT NOT NULL DEFAULT 'zh',
    status TEXT NOT NULL DEFAULT 'active',
    product_context JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 消息
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('customer', 'agent', 'system')),
    content TEXT NOT NULL,
    intent TEXT,
    auto_reply BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 工单
CREATE TABLE IF NOT EXISTS tickets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    summary TEXT NOT NULL,
    suggested_action TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    assigned_to TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 知识库文档（向量检索用）
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title TEXT NOT NULL,
    source_type TEXT NOT NULL,  -- pdf, markdown, url
    source_url TEXT,
    content TEXT NOT NULL,
    chunk_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_executions_task ON agent_executions(task_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_listing_tasks_status ON listing_tasks(status);

-- 社媒图片 (独立存储，与帖子关联)
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
);

CREATE INDEX IF NOT EXISTS idx_social_images_post ON social_images(post_id);

-- Phase 2/3 增量：为 listing_tasks 补齐生成结果列 (ALTER TABLE 幂等需要手动跑，此处记录)
-- ALTER TABLE listing_tasks ADD COLUMN IF NOT EXISTS keywords JSONB DEFAULT '[]';
-- ALTER TABLE listing_tasks ADD COLUMN IF NOT EXISTS top_keywords JSONB DEFAULT '[]';
-- ALTER TABLE listing_tasks ADD COLUMN IF NOT EXISTS title_candidates JSONB DEFAULT '[]';
-- ALTER TABLE listing_tasks ADD COLUMN IF NOT EXISTS bullet_points JSONB DEFAULT '[]';
-- ALTER TABLE listing_tasks ADD COLUMN IF NOT EXISTS description_html TEXT DEFAULT '';
-- ALTER TABLE listing_tasks ADD COLUMN IF NOT EXISTS a_plus_modules JSONB DEFAULT '[]';
-- ALTER TABLE listing_tasks ADD COLUMN IF NOT EXISTS seo_report JSONB DEFAULT '{}';
