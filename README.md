# Cross-Border Agents — 跨境电商多 Agent 系统

Phase 1 MVP: Listing 优化 + 智能客服

## 技术栈

- **Agent 编排**: LangGraph (StateGraph + Conditional Edge + HITL)
- **后端**: Python FastAPI + WebSocket
- **前端**: React + Vite + TypeScript + Tailwind CSS
- **数据库**: PostgreSQL (pgvector) + ChromaDB + Redis
- **LLM**: 可拔插 Provider (DeepSeek / OpenAI / Anthropic)

## 快速开始

```bash
# 1. 安装后端依赖
cd backend
pip install -r requirements.txt

# 2. 安装前端依赖
cd ../frontend
npm install

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 LLM API Key

# 4. 启动服务
docker-compose up -d postgres redis chromadb  # 基础设施
cd backend && uvicorn app.main:app --reload   # 后端
cd frontend && npm run dev                    # 前端
```

## 目录结构

```
cross-border-agents/
├── backend/
│   ├── app/
│   │   ├── agents/          # Agent 定义 (11个)
│   │   │   ├── listing/     # 6 个 Listing Agent
│   │   │   └── customer_service/  # 5 个客服 Agent
│   │   ├── workflows/       # LangGraph 工作流图
│   │   ├── api/             # FastAPI 路由
│   │   ├── core/            # 配置/DB/LLM Provider
│   │   ├── models/          # SQLAlchemy 模型
│   │   └── schemas/         # Pydantic Schema
│   └── requirements.txt
├── frontend/                # React + Vite
├── docker/                  # Dockerfiles + init.sql
└── docker-compose.yml
```

## Phase 1 工作流

### Listing 优化 (6 Agents)
产品输入 → 关键词研究 → 标题生成 → 五点描述 → 长描述 → A+内容 → SEO评分 → 人工审核

### 智能客服 (5 Agents)
用户消息 → 意图识别 → 知识检索(RAG) → 回复生成 → 升级决策 → 自动回复/工单生成
