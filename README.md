# Knowledge Hub

企业文档知识库问答 + 股票投研助手：

- **知识库问答（`mode=rag`）**：上传 PDF / docx / md / txt → 解析切分 → Embedding 入库 → 向量+BM25 混合检索（RRF）→ BGE Rerank → 依据不足拒答，否则一次 LLM 生成带引用答案。
- **投研助手（`mode=direct`）**：一句话任务 → LangGraph 固定拓扑 Multi-Agent（Coordinator → 并行 Analyst → Writer → Mailer）→ Markdown 报告；可选 SMTP 发 PDF 附件。

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Vue 3 + Vite + Pinia + Element Plus + Axios |
| 后端 | FastAPI + SQLAlchemy + MySQL |
| 向量 / 模型 | Chroma（本地）+ 内存 BM25 + SiliconFlow（Embedding / Rerank / Chat） |
| 投研 | LangGraph + 腾讯行情/资讯 HTTP + 新浪 A 股代码表（可选 Redis 缓存）+ SMTP |

## 环境要求

- Python **3.12.9**
- Node.js **18+**（推荐与本机已装版本一致）
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
开发时 `VITE_API_BASE` 留空，由 Vite 将 `/api` 代理到 `127.0.0.1:8000`。

### 3. 种子账号

启动后端后自动幂等写入：

| 用户名 | 密码 |
|--------|------|
| `admin` | `123456` |

已存在则不覆盖密码。

## 主要能力

- 注册 / 登录（JWT Bearer）；业务接口验登录 + ACTIVE
- 文档共享库：上传、列表、详情、物理删除
- **知识库问答**（`/chat/rag`）：向量+BM25 → RRF → Rerank 分数门控 → 规则拒答或带 `citations` 生成；每轮独立，生成不带闲聊历史
- **投研助手**（`/chat/direct`）：Multi-Agent 近 30 日行情报告；助手消息 Markdown 渲染；话术邮箱优先，否则 `RESEARCH_DEFAULT_EMAIL`；邮件为 PDF 附件（不含聊天投递说明）
- 会话按 `mode` 隔离，禁止混聊

## 目录结构（摘要）

```
knowledge-hub/
├── .docs/                         # 主规格 + phase + 双模式 / 投研
├── .cursor/rules/                 # Cursor 约定
├── scripts/                       # 迁移 + verify_*.py（仓库根）
├── backend/
│   ├── app/
│   │   ├── main.py                # 入口、lifespan、CORS
│   │   ├── api/                   # HTTP 路由（薄）
│   │   ├── services/              # 业务（auth / ingest / chat / qa）
│   │   ├── agent/                 # 投研：graph.py · state · agents/ · tools/
│   │   ├── auth/ · ingest/ · rag/ · llm/
│   │   ├── models/ · schemas/
│   │   └── common/                # config、db、errors、chroma、redis、logging
│   ├── scripts/                   # 部分 phase 回归脚本
│   ├── data/kb/ · data/chroma/
│   ├── .env.example
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── main.js · App.vue
    │   ├── assets/css/global.css  # 全局样式（唯一入口）
    │   ├── api/ · stores/ · router/ · utils/
    │   ├── views/{auth,documents,chat}
    │   └── components/{chat,ingest}
    └── vite.config.js
```

规格详见 `.docs/`（含 [投研 Multi-Agent](.docs/stock-research-agent-design.md)）。

## 常用配置（`backend/.env`）

| 键 | 说明 |
|----|------|
| `DATABASE_URL` | MySQL 连接串 |
| `JWT_SECRET_KEY` | JWT 签名密钥 |
| `CORS_ORIGINS` | 默认 `http://localhost:5173` |
| `LLM_*` | SiliconFlow 对话模型 |
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
```

## License

Private / 内部项目，按团队约定使用。
