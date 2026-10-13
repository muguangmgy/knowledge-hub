# Knowledge Hub

企业文档知识库问答：上传 PDF / docx / md / txt → 解析切分 → Embedding 入库 → 问答侧向量+BM25 混合检索（RRF）→ BGE Rerank → 依据不足拒答，否则一次 LLM 生成带引用答案。

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Vue 3 + Vite + Pinia + Element Plus + Axios |
| 后端 | FastAPI + SQLAlchemy + MySQL |
| 向量 / 模型 | Chroma（本地）+ 内存 BM25 + SiliconFlow（Embedding / Rerank / Chat） |

## 环境要求

- Python **3.12.9**
- Node.js **18+**（推荐与本机已装版本一致）
- MySQL **8.0+**（提前创建库 `knowledge_hub`）
- [uv](https://github.com/astral-sh/uv)（推荐，用于安装后端依赖）
- SiliconFlow API Key（Embedding + Rerank + LLM）

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
- 知识问答：向量+BM25 → RRF → Rerank 分数门控 → 规则拒答或带 `citations` 生成；会话懒建；检索用当前原问，历史仅进生成

## 目录结构（摘要）

```
knowledge-hub/
├── backend/
│   ├── app/
│   │   ├── api/          # HTTP 路由
│   │   ├── services/     # 业务逻辑
│   │   ├── auth/         # JWT / seed
│   │   ├── ingest/       # 解析 / 切分
│   │   ├── rag/          # Embedding / Chroma / BM25 / RRF / Rerank |
│   │   ├── llm/          # ChatOpenAI
│   │   ├── models/ · schemas/ · common/
│   │   └── main.py
│   ├── data/kb/ · data/chroma/
│   ├── .env.example
│   └── requirements.txt
└── frontend/
    ├── src/api · stores · views · components
    └── vite.config.js
```

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
| `RAG_REJECT_MAX_DISTANCE` | 向量距离上限（仅 `filter_relevant` 调试用；正式问答以精排分数为准） |
| `RAG_RELATIVE_MAX_GAP` | 与 Top1 距离差（同上，调试用） |

完整示例见 `backend/.env.example`。

## 回归脚本（可选）

后端已启动在 `127.0.0.1:8000` 时：

```bash
cd backend
.\.venv\Scripts\python.exe ..\scripts\verify_phase1_4.py
```

## License

Private / 内部项目，按团队约定使用。
