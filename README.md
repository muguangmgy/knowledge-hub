# Knowledge Hub

企业文档知识库问答 + 股票投研助手：

- **知识库问答（`mode=rag`）**：上传 PDF / docx / md / txt → 解析切分 → Embedding 入库 → 向量+BM25 混合检索（RRF）→ BGE Rerank → 依据不足拒答，否则一次 LLM 生成带引用答案。
- **投研助手（`mode=direct`）**：一句话任务 → LangGraph 固定拓扑 Multi-Agent（Coordinator → 并行 quote/market/news/finance → Writer → Mailer）→ Markdown 报告；可选 SMTP 发 PDF 附件。
- **菜单型 RBAC**：JWT + User–Role–Menu；侧栏按 `/me.menus` 渲染；系统管理（用户 / 角色 / 菜单）。
- **对话 SSE**：UI 主路径 `POST /api/chat/stream`（打字流 + 投研阶段进度含财务 + 可停止）；同步 `POST /api/chat` 仍保留供脚本/兼容。

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Vue 3 + Vite + Pinia + Element Plus + Axios（短请求）+ `fetch` SSE（问答流） |
| 后端 | FastAPI + SQLAlchemy + MySQL |
| 向量 / 模型 | Chroma（本地）+ 内存 BM25 + SiliconFlow（Embedding / Rerank / Chat） |
| 投研 | LangGraph + 腾讯行情/资讯 + AKShare 财务要点 + 新浪代码表（可选 Redis）+ SMTP |

## 环境要求

- Python **3.12.9**
- Node.js **18+**（主规格锁定示例为 **v24.15.0**）
- MySQL **8.0+**（提前创建库 `knowledge_hub`）
- [uv](https://github.com/astral-sh/uv)（推荐，用于安装后端依赖）
- SiliconFlow API Key（Embedding + Rerank + LLM）
- （可选）Redis：加速 A 股代码表缓存；未配则每次冷启较慢
- （可选）SMTP：投研报告发信

## 快速开始

### 1. 后端

```bash
cd backend
uv venv --python 3.12.9
# Windows
.\.venv\Scripts\activate
uv pip install -r requirements.txt

copy .env.example .env
# 编辑 .env：DATABASE_URL、LLM_API_KEY、EMBEDDING_API_KEY 等
# 投研发信另配 SMTP_*、RESEARCH_DEFAULT_EMAIL；可选 REDIS_URL

uvicorn app.main:app --host 127.0.0.1 --port 8000
```

健康检查：http://127.0.0.1:8000/api/health

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

浏览器打开：http://localhost:5173  
开发时 `VITE_API_BASE` 留空，由 Vite 将 `/api` 代理到 `127.0.0.1:8000`；其中 `/api/chat/stream` 单独配置（关缓冲、拉长超时）以支持 SSE。

### 3. 种子账号

启动后端后自动幂等写入：

| 用户名 | 密码 |
|--------|------|
| `admin` | `123456` |

已存在则不覆盖密码。

## 主要能力

- 注册 / 登录（JWT Bearer）；业务接口验登录 + `status=1`（`1`=正常 / `0`=禁用）
- **菜单型 RBAC**：User–Role–Menu；侧栏按 `/me.menus` 渲染；系统管理三页（用户 / 角色 / 菜单）
- 文档共享库：上传、列表、详情、物理删除
- **知识库问答**（`/chat/rag`）：向量+BM25 → RRF → Rerank 分数门控 → 规则拒答或带 `citations` 生成；每轮独立，生成不带闲聊历史；SSE 打字流，引用先出
- **投研助手**（`/chat/direct`）：Multi-Agent 近 30 日报告（行情/走势/资讯/财务要点）；SSE 阶段进度 + Writer 打字流；助手 Markdown 渲染；话术邮箱优先，否则 `RESEARCH_DEFAULT_EMAIL`；邮件为 PDF 附件（不含聊天投递说明；PDF 换行与网页 `breaks` 对齐）
- 会话按 `mode` 隔离，禁止混聊；发送中可「停止」（取消不落半成品 assistant，投研不发信）

## 目录结构（摘要）

```
knowledge-hub/
├── .docs/                         # 主规格 + phase + 双模式 / 投研 / SSE / RBAC
├── .cursor/rules/                 # Cursor 约定
├── scripts/                       # 迁移 + verify_*.py（仓库根）
├── backend/
│   ├── app/
│   │   ├── main.py                # 入口、lifespan、CORS、挂路由
│   │   ├── api/                   # auth / documents / chat[+stream] / users / roles / menus
│   │   ├── services/              # auth · ingest · chat · qa · user/role/menu_admin · menu_tree
│   │   ├── agent/                 # 投研：graph.py · stream.py · agents/ · tools/
│   │   ├── auth/ · ingest/ · rag/ · llm/
│   │   ├── models/ · schemas/     # 含 rbac / system
│   │   └── common/                # config、db、errors、chroma、redis、sse、logging
│   ├── scripts/                   # 部分 phase 回归脚本
│   ├── data/kb/ · data/chroma/
│   ├── .env.example
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── main.js · App.vue
    │   ├── assets/css/global.css  # 全局样式（唯一入口）
    │   ├── layouts/AppLayout.vue  # 左侧菜单壳 + 顶栏用户区
    │   ├── api/ · stores/ · router/ · utils/
    │   ├── views/{auth,documents,chat,system}
    │   └── components/{chat,ingest,system}
    └── vite.config.js             # /api 与 /api/chat/stream 代理
```

规格详见 `.docs/`：

- [主规格](.docs/knowledge-qa-design.md)
- [菜单型 RBAC](.docs/rbac-menu-design.md)
- [双模式外壳](.docs/chat-dual-mode-design.md)
- [投研 Multi-Agent](.docs/stock-research-agent-design.md)
- [对话 SSE](.docs/chat-sse-design.md)

## 常用配置（`backend/.env`）

| 键 | 说明 |
|----|------|
| `DATABASE_URL` | MySQL 连接串 |
| `JWT_SECRET_KEY` | JWT 签名密钥 |
| `CORS_ORIGINS` | 默认 `http://localhost:5173` |
| `LLM_*` | SiliconFlow 对话模型（支持 `stream: true`） |
| `EMBEDDING_*` | SiliconFlow 向量模型 |
| `RAG_TOP_K` | 精排后最终给模型的片段条数，默认 8 |
| `RAG_HYBRID_PATH_TOP_K` | 向量 / BM25 各路召回与 RRF 融合条数，默认 20 |
| `RAG_RERANK_MIN_SCORE` | 精排软地板，默认 0.05 |
| `RAG_RERANK_RELATIVE_RATIO` | 精排相对落差（≥ Top1×比例），默认 0.5 |
| `RAG_RERANK_KEEP_TOP1_FLOOR` | 滤空时 Top1 兜底地板，默认 0.15 |
| `RERANK_MODEL` | 精排模型，默认 `BAAI/bge-reranker-v2-m3` |
| `REDIS_URL` | 可选，如 `redis://127.0.0.1:6379/0`；空则跳过 Redis |
| `SMTP_*` | 投研发信（HOST/PORT/USER/PASSWORD/FROM/USE_SSL） |
| `RESEARCH_DEFAULT_EMAIL` | 话术未写邮箱时的默认收件人 |
| `RESEARCH_GRAPH_TIMEOUT_SEC` | 投研图超时秒数，默认 90 |

完整示例见 `backend/.env.example`。

## 回归脚本（可选）

后端已启动在 `127.0.0.1:8000` 时：

```bash
cd backend
.\.venv\Scripts\python.exe ..\scripts\verify_phase1_4.py

# 对话 SSE 冒烟（A6/A7/A8 + 流式 meta/done）
.\.venv\Scripts\python.exe ..\scripts\verify_chat_sse.py --user admin --password 123456

# 菜单型 RBAC 冒烟
.\.venv\Scripts\python.exe ..\scripts\verify_rbac_menu.py

# 投研 Multi-Agent 冒烟
.\.venv\Scripts\python.exe ..\scripts\verify_stock_research_agent.py

# 双模式外壳（可选）
.\.venv\Scripts\python.exe ..\scripts\verify_chat_dual_mode.py
```

旧库若仍有 `sys_permission` / `sys_role_permission`，可先跑 `..\scripts\migrate_rbac_menu.py` 再重启后端。

## License

Private / 内部项目，按团队约定使用。
