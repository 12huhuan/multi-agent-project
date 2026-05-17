# 项目经历

## 跨境电商全自动化多智能体系统

**技术栈**：LangGraph · FastAPI · React · TypeScript · PostgreSQL (pgvector) · ChromaDB · Redis · Docker · Pydantic · SSE/WebSocket · WordPress REST API · Prompt Engineering · RAG · ContextBus

---

### 项目背景

面向中小跨境电商卖家（日均处理数百条评论、数十款SKU Listing），解决从选品、Listing 优化、合规审查、社媒营销到评论监控与智能客服的**全链路运营自动化**难题。传统人工运营效率低下、多语种内容生产成本高、各环节数据割裂无法联动——本系统通过 **32 个 LLM Agent + 顶层调度 Agent** 实现一站式运营闭环，将卖家操作从"逐条手工处理"降维为"一键触发 + 关键节点人工决策"。

---

### 项目要点

1. **32 Agent 分层协作体系**：基于 **LangGraph StateGraph** 构建 8 大业务域（选品 / Listing / 合规 / 社媒 / 评论 / 客服 / 广告 / 调度），每域 Agent 链式串联、域间通过 **ContextBus** 强类型上下文总线自动流转数据，消除硬编码 dict 传递，实现产品全生命周期数据的一致性传递。

2. **RAG 多语种智能客服**：集成 ChromaDB 向量数据库 + Qwen Embedding 构建知识库检索增强生成管线，客服链通过 Intent Recognition → Knowledge Retrieval → Reply Generation → Escalation Decision → Ticket Generation 五步流水线处理，SSE 流式输出逐 token 返回，支持 **10+ 语种**意图自动检测与目标语种回复生成。

3. **Listing 六步优化管线 + HITL 审核**：关键词研究 → 标题生成 → 五点描述 → HTML 长描述 → A+ 内容 → SEO 评分，LangGraph 的 **MemorySaver Checkpoint** 实现流程暂停/恢复，Human-in-the-Loop 审核节点在关键环节等待人工决策后继续执行。

4. **顶层调度 Agent 全流程自动编排**：Orchestrator Agent 通过 LLM 决策引擎自动规划执行序列（选品→Listing→合规→社媒→评论），后端异步执行 + 前端轮询进度，每步结果展开完整数据，TaskStore 实现 **跨页面任务状态持久化**（localStorage），页面切换/刷新不丢失运行中的任务。

5. **LLM Provider 可拔插架构**：基于 OpenAI-compatible 协议抽象 BaseLLMProvider，通过统一接口（chat / chat_stream）屏蔽厂商差异，支持 DeepSeek / OpenAI / Anthropic / 本地模型热切换，**零代码改动的模型迁移**。

6. **多平台社媒内容生成与发布**：Product Analysis → Platform Adapter → Copy Generator → Image Generator（Pollinations.ai 免费生成）→ Quality Checker 五步社媒管线，通过 WordPress REST API 自定义插件实现**跨平台内容一键发布**，文案语言按目标市场自动适配。

7. **评论智能监控与预警**：Review Scraper（Amazon 评论抓取）→ Sentiment Analyzer（情感分析）→ Translator（LLM 多语种翻译）→ Negative Alert（分级预警）→ Reply Suggestion（回复模板生成），**日均处理 500+ 评论**，负面评论识别后自动推送预警通知。

---

### 项目优化点

1. **上下文总线（ContextBus）重构**：用 Pydantic 强类型模型（ProductIdentity / MarketInsight / ListingOutput / ComplianceReport 等子模型）替代 orchestrator 中零散的 `dict` 传递，通过 `ContextMapper.derive()` 和 `ContextMapper.ingest()` 双向映射实现 Workflow State ↔ ProductContext 的自动转换，消除了 30+ 处字符串硬编码和重复 LLM 调用补全数据的开销。

2. **执行网关层抽象**：将 WordPress、小红书等外部平台的发布能力抽象为 `SocialPublisherGateway` 接口层，各平台适配器（WordPressGateway / XiaohongshuGateway）统一实现 `publish()` / `check_status()` 方法，新增平台只需实现接口而无需修改核心业务逻辑，符合开闭原则。

3. **客服 SSE 流式 + 语种智能路由**：客服 SSE 端点根据 Intent Recognition 检测到的语种（`detected_language`）动态选择回复语言，非英文 prompt 增加 `lang_directive` 约束防止 LLM 回退到英文，实现英文输入→英文回复、中文输入→中文回复的语种保真。

4. **ConversationStore 会话持久化**：客服页面集成 localStorage 持久化存储，历史会话列表支持会话恢复和删除，**页面刷新/浏览器重启后会话完整保留**，避免了传统 in-memory 存储导致用户上下文丢失的问题。

5. **调度中心异步化改造**：将 orchestrator 从 HTTP 同步等待改造为后台任务异步执行 + 前端轮询进度的模式，避免全流程 5 步顺序执行导致的请求超时（单次最长 90s → 无阻塞），同时通过进度轮询让用户实时感知每步执行状态。

---

### 项目成果

1. **全链路自动化闭环**：系统覆盖选品→Listing→合规→社媒发布→评论监控→智能客服→广告管理 7 个业务环节，全部通过 Agent 链式调用 + 顶层调度 Agent 实现自动化执行，用户只需输入产品品类与目标市场即可触发全流程。

2. **Agent Agent 自评测体系**：通过 SEO Scoring Agent 对 Listing 优化结果进行**自动量化评分**（关键词覆盖度 / 标题吸引力 / 描述完整度 / A+ 内容质量四个维度），Quality Checker Agent 对社媒文案进行**自动化质量审核**（语言流畅度 / 卖点覆盖率 / 平台适配度），实现了 Agent 输出质量的闭环评估。

3. **10 前端页面 + 8 API 路由**：Dashboard / Listing / 客服 / 知识库 / 评论 / 社媒 / 选品 / 合规 / 广告 / 调度中心 全部由 React + TypeScript + Tailwind CSS 构建，TaskStore 跨页面任务状态同步，社交媒体动态展示页采用小红书卡片风格。

4. **多语种覆盖**：智能客服与 Listing 内容支持中文、英文、日语、德语、法语、西班牙语等 10+ 语种的输入理解和目标语言输出，翻译模块基于 LLM（DeepSeek）替代 DeepL API，翻译质量通过人工抽检达到商用水平。

5. **容器化一键部署**：Docker Compose 编排 PostgreSQL + Redis + ChromaDB + WordPress 四项基础设施，前端 Vite 开发服务器 + 后端 Uvicorn 统一通过 docker-compose up -d 启动，降低部署门槛至 1 条命令。
