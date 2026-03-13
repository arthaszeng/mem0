# OpenMemory Release Roadmap

<!-- 
  格式说明：
  - 每个版本用 ## 开头，格式为：## version | title | status | date | icon
  - status: completed / in_progress / upcoming
  - icon: lucide 图标名 (kebab-case)，如 layers, shield, sparkles, globe 等
  - 版本描述紧跟在 ## 下一行
  - Feature 用 checkbox 表示状态：[x] = completed, [-] = in_progress, [ ] = upcoming
  - Feature 格式：- [x] **名称** — 描述
  
  编辑此文件后重新构建 UI 即可自动更新 Dashboard 的 Release Tree。
-->

## v0.1 | Core Foundation | completed | 2026-01 | layers

记忆系统基础架构：双存储引擎 + 语义搜索 + MCP Server

- [x] **Qdrant + SQLite 双存储** — Qdrant 存向量用于语义搜索，SQLite 存元数据用于管理和过滤
- [x] **CRUD + 语义搜索** — 完整的记忆增删改查 REST API，基于 embedding 余弦相似度的语义搜索
- [x] **MCP Server (SSE)** — SSE 传输协议的 MCP Server，支持 Cursor / Claude Desktop / Cline 等客户端直接接入
- [x] **Custom Instructions** — DB 持久化 + UI 编辑面板，自定义 Fact Extraction 和 Categorization 规则
- [x] **导出 / 导入** — ZIP 格式完整备份（SQLite 数据 + 记忆 JSON），支持跨实例数据迁移
- [x] **Next.js 管理界面** — Dashboard + 记忆表格 + 详情页 + 设置页，Tailwind + Radix UI 暗色主题

## v0.2 | Cross-SDK Interop | completed | 2026-02 | link-2

JS/Python 双 SDK 互通 — OpenClaw 插件实现跨客户端记忆共享

- [x] **OpenClaw mem0 插件** — 基于 mem0ai JS SDK 的 OpenClaw 插件，实现 auto-capture 和 auto-recall
- [x] **Payload 字段统一** — JS SDK 和 Python SDK 统一为 snake_case（user_id, created_at），解决跨 SDK 数据不互通
- [x] **SQLite 自动注册** — JS SDK 写入 Qdrant 后自动注册到 SQLite 元数据库，UI 和 API 均可管理
- [x] **双向数据互通** — Python SDK 写的记忆 JS 能读，JS 写的记忆 Python 能查，完全双向兼容

## v0.3 | Smart Classification | completed | 2026-02 | sparkles

LLM 智能分类 + 敏感信息脱敏 + 批量修复历史数据

- [x] **Domain 智能识别** — LLM 驱动的 domain 识别 + 关键词快速匹配双通道，自动归类到注册域
- [x] **Category 自动标注** — LLM 根据内容自动标注 category，支持字符串→列表解析和域名兜底
- [x] **后台异步分类** — MCP 写入后台线程触发分类，不阻塞主请求，提升响应速度
- [x] **Backfill 批量回填** — backfill-categories 端点一次性回填 179 条无分类历史记忆
- [x] **敏感信息脱敏** — 两阶段检测：关键词快筛 + 正则脱敏，覆盖 API Key / 连接串 / PEM / Token 等
- [x] **循环调用 Bug 修复** — 修复分类过程中触发二次写入导致的无限循环问题

## v0.4 | Cloud Deployment | completed | 2026-03 | globe

从本地到云端 — 阿里云部署 + LLM 升级 + 向量库扩容

- [x] **阿里云 Docker 部署** — Docker Compose 一键部署到阿里云 ECS（2vCPU/2GB），包含 Qdrant / API / UI / Nginx
- [x] **Nginx 反向代理** — 统一入口网关，路由 /memory-mcp/ 和 /concierge-mcp/ 到不同后端服务
- [x] **SSL / HTTPS** — arthaszeng.top 域名 + Let's Encrypt 证书，全链路 HTTPS 加密
- [x] **LLM 升级 gpt-4o-mini** — 从本地 Ollama qwen2.5:7b 迁移到 gpt-4o-mini，分类和提取质量大幅提升
- [x] **Embedding 升级 1536d** — 从 nomic-embed-text (768d) 升级到 text-embedding-3-small (1536d)，搜索精度提升
- [x] **Qdrant Collection 迁移** — openmemory_768 → openmemory (1536d)，全量数据重建向量索引

## v0.5 | Multi-Client Hub | completed | 2026-03 | messages-square

一套记忆，多端共享 — MCP Prompts + ChatGPT + Concierge Agent

- [x] **6 个 MCP Prompts** — recall / briefing / project-context / who-am-i / review-memories / custom-instructions
- [x] **ChatGPT Custom GPT** — OpenAPI Schema 定义 Actions，ChatGPT 直接读写 OpenMemory
- [x] **GPT 公开版 + 私有版** — 公开版仅记忆 (OAuth2)，私有版含 Concierge (Bearer JWT)，双 schema 双 prompt
- [x] **Concierge LangGraph Agent** — 独立的 AI 代理服务，通过 LangGraph 编排多步对话和记忆操作
- [x] **Chrome 扩展** — Concierge 浏览器扩展，popup 界面连接云端 MCP，随时随地对话

## v0.6 | Multi-User Auth | completed | 2026-03 | shield

多用户认证体系 + 项目级权限隔离 + 安全加固

- [x] **OAuth2 + Session** — 完整的 OAuth2 认证流程 + Session 会话管理，支持多客户端登录
- [x] **Nginx Auth 网关** — Nginx 注入 X-Auth-User / X-Auth-Project 头部，后端透明鉴权
- [x] **项目级记忆隔离** — 每个项目独立的 Qdrant namespace + SQLite 过滤，记忆完全隔离
- [x] **4 级角色系统** — Owner(3) > Admin(2) > ReadWrite(1) > ReadOnly(0)，细粒度权限控制
- [x] **项目邀请系统** — 可分享链接邀请用户加入项目，支持指定角色和过期时间
- [x] **数据隔离安全修复** — 修复 archive 无认证 / delete 无所有权校验 / global_pause 影响全局 三个安全漏洞
- [x] **Chrome 扩展 OAuth** — Concierge 浏览器扩展集成 OAuth 认证流程，支持多用户切换
- [x] **OAuth Client Secret** — 动态注册支持 client_secret 生成，兼容 ChatGPT 等需要密钥的 OAuth 客户端
- [x] **Token 端点 Form 兼容** — /auth/token 同时支持 JSON 和 x-www-form-urlencoded，符合 OAuth2 标准

## v0.7 | Memory Quality | completed | 2026-03 | brain

记忆质量升级 — 测试基线 + 版本管理 + 更精准的提取

- [x] **测试基线** — pytest 回归测试框架：health / CRUD / search 覆盖，`make test` 一键运行
- [x] **版本管理** — API `app/version.py` + UI `package.json` 统一版本号，`/health` 端点暴露版本
- [x] **Fact Extraction 增强** — 丰富 few-shot 正负例，过滤闲聊 / 推测 / 调试输出，"宁缺勿滥" 策略
- [x] **Confidence Threshold** — 置信度门控 (0.0-1.0)，模糊表述自动过滤，DB 配置持久化
- [x] **Per-Call Instructions** — MCP add_memories 支持 `infer` 和 `instructions` 参数，按需覆盖全局规则

## v0.8 | Memory Lifecycle | completed | 2026-03 | clock

记忆不再永久堆积 — 自动过期、类型分层

- [x] **TTL 自动过期** — Memory 新增 expires_at 列，后台每 5 分钟扫描并标记过期记忆为 expired 状态
- [x] **Memory Type 分层** — session / preference / fact / episodic 四类标签，MCP add_memories 支持 memory_type 参数
- [x] **MCP 生命周期参数** — add_memories 新增 expires_at 和 memory_type，支持 ISO 8601 过期时间
- [x] **Alembic 迁移** — v0_8_lifecycle 迁移添加 expires_at / memory_type 列和索引
- [x] **ArchivePolicy 自动化** — REST API + 后台每小时自动执行归档策略，支持 global / app 两种粒度

## v0.9 | Advanced Retrieval | completed | 2026-03 | search

从「能搜到」到「搜得准」— 混合检索 + 过滤

- [x] **Keyword + Vector 混合检索** — 向量搜索 + SQLite LIKE 关键词搜索 + 域增强三通道，合并去重按 score 排序
- [x] **MCP Search 增强** — search_memory 支持 limit / categories / memory_type 参数，结果可精确过滤
- [x] **Category 过滤** — 按逗号分隔的 category 名称过滤搜索结果
- [x] **Memory Type 过滤** — 按 fact / preference / session / episodic 类型过滤
- [x] **Reranking 重排序** — 支持 Jina / Cohere / cross-encoder 三种后端，环境变量配置，搜索自动集成
- [x] **Memory Filtering** — LLM 批量相关性打分 0–1，可配置阈值过滤低相关结果

## v1.0 | Graph Memory | completed | 2026-03 | git-branch

从扁平记忆到结构化知识网络 — Kuzu 图数据库 + 实体关系

- [x] **Kuzu Graph Store** — 嵌入式图数据库集成，零运维，无 pandas 依赖，原生 cursor API
- [x] **实体关系提取** — gpt-4o-mini 自动提取 person/project/technology/organization/concept/place 实体及关系
- [x] **后台自动建图** — 写入记忆时后台线程自动提取实体写入 Kuzu 图
- [x] **MCP Entity Tools** — search_entities + list_graph_entities 两个新 MCP 工具
- [x] **Graph-Enhanced Search** — search_memory 结果融合图谱关联实体（v1.1 已实现，score 0.6 融合）
- [x] **知识图谱可视化** — 力导向图 UI，节点按实体类型着色，Dashboard 集成

## v1.1 | Entity Scoping | completed | 2026-03 | layers

更细粒度的记忆隔离 — 会话级 + AI 角色级 + 图谱增强搜索

- [x] **agent_id + run_id** — Memory 模型新增字段 + 索引，MCP add_memories 支持传入
- [x] **agent_id 搜索过滤** — search_memory 支持 agent_id 参数，按 AI 角色过滤结果
- [x] **Graph-Enhanced Search** — search_memory 自动查询 Kuzu 图谱关联实体的记忆，融入搜索结果 (score 0.6)
- [x] **Agent Memory** — 每个 AI 角色独立 Custom Instructions，DB 持久化 + MCP/REST API 管理

## v1.2 | MCP Complete | completed | 2026-03 | wrench

MCP 工具集追平 REST API — 更新、归档、结构化导出

- [x] **MCP Update Tool** — update_memory(memory_id, new_content)，更新后自动触发重分类+实体提取
- [x] **Archive / Restore Tools** — archive_memories + restore_memories，MCP 端批量归档和恢复
- [x] **Structured Export** — export_memories(format) 支持 JSON 和 text 两种格式，按 category 分组导出

## v1.3 | Intelligence | completed | 2026-03 | zap

记忆系统从被动存储走向主动智能

- [x] **Memory Consolidation** — MCP consolidate_memories 工具，SequenceMatcher 发现相似记忆 + LLM 合并，支持 dry_run
- [x] **Contradiction Detection** — MCP check_contradiction 工具，LLM 对比新记忆与已有记忆检测冲突
- [ ] **Memory Insights** — 用户画像摘要 + 主题趋势分析 + 知识覆盖度（延至 v2.x）
