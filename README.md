# Cross-Border Agents — 跨境电商多 Agent 系统

基于 Python LangGraph 的全链路跨境电商自动化系统，覆盖从选品到售后的完整运营闭环。

## 技术栈

- **Agent 编排**: LangGraph (StateGraph + Conditional Edge + HITL)
- **后端**: Python FastAPI + WebSocket + SSE
- **前端**: React + Vite + TypeScript + Tailwind CSS
- **数据**: PostgreSQL (pgvector) + ChromaDB + Redis
- **LLM**: DeepSeek-chat (OpenAI Compatible Provider)
- **Embedding**: Qwen text-embedding-v3 (DashScope)

## 快速开始

```bash
# 1. 启动基础设施
docker-compose up -d postgres redis chromadb wordpress wordpress-db

# 2. 后端 (端口 8000)
pip install -r requirements.txt
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

# 3. 前端 (端口 5173)
cd frontend && npm install && npm run dev -- --host 0.0.0.0
```

## 功能模块

| Phase | 模块 | Agent | 功能 |
|---|---|---|---|
| 1 | Listing 优化 | 6 | 关键词研究 → 标题生成 → 五点描述 → 详情 → A+内容 → SEO评分 |
| 1 | 智能客服 | 5 | 意图识别 → RAG检索 → 回复生成(SSE流式) → 升级决策 → 工单 |
| 1 | 知识库 | 0 | ChromaDB 向量检索, Markdown/PDF/URL 导入 |
| 2 | 评论监控 | 5 | 抓取 → 情感分析 → 翻译 → 预警 → 回复建议 |
| 2 | 社媒内容 | 5 | 产品分析 → 多平台适配 → 文案+图片生成 → 质检 |
| 3 | 智能选品 | 3 | 趋势分析 → 产品匹配 → 4维评分 |
| 3 | 合规审查 | 3 | 政策检查 → 声明验证 → 风险报告 |
| 3 | 广告管理 | 3 | 效果分析 → 竞价优化 → 预算分配 |
| 3 | 调度中心 | 1 | 5步全流程自动编排 (选品→Listing→合规→社媒→评论) |
| - | 共享 | 1 | 翻译 Agent (20+语言) |

**Agent 总数: 32 | 前端页面: 10 | API 路由: 9**

## 前端页面

| 页面 | 路由 | 功能 |
|---|---|---|
| 仪表盘 | `/` | 管线视图 + 流程分布图 + 最近活动 |
| Listing | `/listing` | 产品输入 → 异步生成 → 审核/编辑 |
| 智能客服 | `/customer-service` | 对话/工单双 Tab + 语音输入 |
| 知识库 | `/knowledge-base` | 文档 CRUD + 语义搜索 |
| 评论监控 | `/reviews` | ASIN 输入 → 评论列表 + 情感分布图 |
| 社媒内容 | `/social` | 多平台生成 → 通过 → 发布 |
| 智能选品 | `/selection` | 品类分析 → 机会评分 + 图表 |
| 合规审查 | `/compliance` | Listing 内容 → 合规报告 |
| 调度中心 | `/orchestrator` | 输入品类 → 一键全流程 |
| 广告管理 | `/ads` | Dashboard + 一键全优化 |
| 社媒动态 | `/feed` | 已发布内容展示 |

## 目录结构

```
cross-border-agents/
├── backend/
│   └── app/
│       ├── agents/            # 32 Agent (9个子包)
│       │   ├── listing/       # 6: 关键词/标题/五点/描述/A+/SEO
│       │   ├── customer_service/  # 5: 意图/RAG/回复/升级/工单
│       │   ├── review/        # 5: 抓取/情感/翻译/预警/回复
│       │   ├── social/        # 5: 分析/适配/文案/图片/质检
│       │   ├── selection/     # 3: 趋势/匹配/评分 + Amazon数据收集器
│       │   ├── compliance/    # 3: 政策/声明/风险
│       │   ├── ads/           # 3: 分析/竞价/预算
│       │   ├── orchestrator/  # 1: 全流程调度
│       │   └── shared/        # 翻译/Amazon关键词/图表渲染
│       ├── workflows/         # 6 LangGraph StateGraph
│       ├── api/               # 9 FastAPI 路由
│       ├── core/              # 配置/DB/LLM/向量存储/通知/上下文总线
│       ├── gateway/           # 执行网关层(WordPress/小红书)
│       ├── models/            # SQLAlchemy ORM
│       └── schemas/           # Pydantic Schema
├── frontend/
│   └── src/
│       ├── components/        # Layout / ChartWidget
│       ├── pages/             # 11 页面
│       └── lib/               # utils / TaskStore
├── docker/                    # Dockerfiles + WordPress 插件
├── data/                      # 上下文持久化 + Cookie
└── docker-compose.yml         # 8 服务
```

## 架构亮点

- **ContextBus**: ProductContext 强类型模型 + derive/ingest 双向映射，数据在模块间零 LLM 调用流转
- **Gateway 层**: 统一对外发布入口，WordPress + 小红书(半自动)路由
- **Amazon Autocomplete**: 真实搜索热词替代 LLM 编造，中文自动翻译后搜索
- **AntV 图表**: 26种图表类型，零 API Key 免费使用
- **通知系统**: Server酱 + 邮件双通道，工单/预警自动推送

## 许可证

MIT License
