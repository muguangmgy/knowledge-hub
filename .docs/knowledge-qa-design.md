# Knowledge Hub 知识问答 — 技术方案设计文档

- **日期**：2026-10-13
- **状态**：已实现（与现网对齐；含 RBAC 菜单 / 双模式 / 投研 / SSE）
- **作者**：项目组
- **说明**：企业散落文档（PDF / docx / text / md）入库后的可问答知识库；问答管线为「混合检索 → Rerank → 带引用生成 / 规则拒答」，答案强制引用来源。

**分阶段设计文档**（按 §10 拆分，实现时按阶段阅读）：

| Phase | 文档 |
|-------|------|
| 1 基础设施 | [phase/knowledge-qa-phase1-design.md](./phase/knowledge-qa-phase1-design.md) |
| 2 认证与 JWT | [phase/knowledge-qa-phase2-design.md](./phase/knowledge-qa-phase2-design.md) |
| 3 文档入库与删除 | [phase/knowledge-qa-phase3-design.md](./phase/knowledge-qa-phase3-design.md) |
| 4 问答与前端 | [phase/knowledge-qa-phase4-design.md](./phase/knowledge-qa-phase4-design.md) |

**相关文档**：

| 文档 | 说明 |
|------|------|
| [rbac-menu-design.md](./rbac-menu-design.md) | User–Role–Menu：侧栏、系统管理、`status`/`visible` 为 `0|1` |
| [chat-dual-mode-design.md](./chat-dual-mode-design.md) | 双模式外壳：`rag` / `direct` 会话隔离、路由与 API |
| [chat-sse-design.md](./chat-sse-design.md) | 对话 SSE 事件协议与取消语义 |
| [stock-research-agent-design.md](./stock-research-agent-design.md) | **`mode=direct` 现网实现**：投研 Multi-Agent（取代原闲聊） |

---

## 1. 项目定位

Knowledge Hub（本功能短名 **knowledge-qa**）把企业文档变成可自然语言提问的知识库：用户上传文档 → 解析切分 → Embedding/BM25 索引 → 对话时混合检索与精排 → 依据不足则拒答，否则一次 LLM 生成带引用的答案。

**目标能力**（实现分步见 §10）：

- 用户**注册 / 登录**（**JWT** access token；localStorage + Bearer）
- **RBAC 表结构**：用户 / 角色 / 菜单及关联表（见 [rbac-menu-design.md](./rbac-menu-design.md)）；种子角色 `admin`、`user`；注册默认绑 `user`；业务 API **只验已登录 + status=1**
- 支持 PDF / **docx** / text / Markdown 入库与列表管理（**同步入库**）
- **文档库 = 全员共享库**：任意已登录用户可上传 / 列表 / 详情 / 删除全库文档；问答检索范围 = 全库
- **混合检索**（Chroma 向量 + 内存 BM25 → RRF）→ **BGE Rerank 分数门控** → **带引用生成**；依据不足规则拒答
- **rag 生成不带历史**；**检索用当前用户消息原文**（不改写、不拼历史）
- **双入口**：知识库问答 `/chat/rag`；投研助手 `/chat/direct`（`mode=direct` → Multi-Agent，见 [stock-research-agent-design.md](./stock-research-agent-design.md)；外壳见 [chat-dual-mode-design.md](./chat-dual-mode-design.md)）

**交付目标**：本地可启动前后端；启动后可用种子账号 **`admin` / `123456`** 登录；亦可注册新用户；RBAC 表与种子数据可查；上传→入库→带引用问答主链路可演示；依据不足时拒答。

---

## 2. 技术栈与本地开发环境

### 2.1 技术栈

| 层 | 选型 | 说明 |
|----|------|------|
| 前端 | Vue 3 + Vite + JavaScript + Element Plus + Pinia + Axios | 登录注册、知识库；知识库问答 `/chat/rag`、投研助手 `/chat/direct` |
| 投研 | LangGraph + 腾讯/新浪 HTTP + AKShare 财务要点 + 可选 Redis + SMTP | 仅 `mode=direct`；四路并行 Analyst；见投研设计文档 |
| 后端 | FastAPI + Uvicorn | REST；目录见 §2.3，模块见 §3 |
| 问答管线 | 普通服务函数（`ChatOpenAI` / `OpenAIEmbeddings` + Rerank HTTP） | **混合检索 → Rerank → 生成/拒答** |
| 关系库 | MySQL 8.0+ | 用户/RBAC、文档、chunk、会话（库名 `knowledge_hub`） |
| 鉴权 | JWT（`JWT_*`）+ RBAC 表 | 注册登录发 Token；业务 API 验登录 |
| 向量库 / 检索 | Chroma + BM25（内存） | `CHROMA_DIR`；双路 → RRF → BGE Rerank |
| LLM | SiliconFlow → `deepseek-ai/DeepSeek-V4-Flash` | 生成带引用答案 |
| Embedding | SiliconFlow → `BAAI/bge-m3` | 切片向量化 |
| Rerank | SiliconFlow → `BAAI/bge-reranker-v2-m3` | 精排；KEY/URL 空则回落 Embedding |
| 解析 | pymupdf / python-docx / 原生读 md·text | 仅 pdf/docx/md/txt；切分见 §6.4 |
| 依赖管理 | uv + `backend/requirements.txt` | 先包名安装，验证后锁版本 |
| 密码哈希 | bcrypt | |
| JWT | PyJWT | 签发 / 校验 |

**部署形态（本地）**：本机 MySQL；后端读 `backend/.env`；文件落 `KB_DIR`，向量落 `CHROMA_DIR`。

### 2.2 本地开发环境

| 项 | 要求 |
|----|------|
| Python | **3.12.9** |
| MySQL | **8.0+**（库 **`knowledge_hub` 已创建**） |
| uv | 本机已安装 |
| Node.js | **v24.15.0** |

```bash
cd backend
uv venv --python 3.12.9
# Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
```

**版本锁定**：装好并验证后，将精确版本写回 `requirements.txt`（可用 `uv pip freeze` 核对）。

**后端依赖包名清单**（与 `requirements.txt` 一致）：

| 分组 | 包名 |
|------|------|
| Web | `fastapi`、`python-multipart` |
| Config / DB | `pydantic-settings`、`sqlalchemy`、`pymysql`、`cryptography` |
| Auth | `bcrypt`、`PyJWT` |
| RAG / LLM | `langchain-core`、`langchain-openai`、`chromadb`、`rank_bm25`、`jieba` |
| Document parsing | `pymupdf`、`python-docx` |
| 投研 | `langgraph`、`requests`、`akshare`、`redis`、`markdown` |
| ASGI | `uvicorn`（已写入 `requirements.txt`） |

完整锁定版本见 `backend/requirements.txt`。

**配置键**（`backend/.env`；实现时补 `.env.example`）：

| 键 | 用途 |
|----|------|
| `DATABASE_URL` | MySQL |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | 对话模型 |
| `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` | 向量模型 |
| `KB_DIR` / `CHROMA_DIR` | 原文 / Chroma 目录 |
| `JWT_SECRET_KEY` / `JWT_ALGORITHM` / `JWT_EXPIRE_HOURS` | Access Token；过期策略见 §3.2 |
| `CORS_ORIGINS` | 默认 `http://localhost:5173` |
| `INGEST_MAX_MB` | 上传硬上限（建议默认 **50**）；超过直接 `41301` |
| `RAG_TOP_K` | 精排后最终给模型的片段条数，默认 **8** |
| `RAG_HYBRID_PATH_TOP_K` | 向量 / BM25 各路召回与 RRF 融合条数，默认 **20** |
| `RERANK_MODEL` / `RERANK_API_KEY` / `RERANK_BASE_URL` | 精排；KEY/URL 空则回落 Embedding；默认 `BAAI/bge-reranker-v2-m3` |
| `RAG_RERANK_MIN_SCORE` | 精排软地板，默认 **0.05**（见 §6.2） |
| `RAG_RERANK_RELATIVE_RATIO` | 精排相对落差：须 ≥ Top1×该比例，默认 **0.5** |
| `RAG_RERANK_KEEP_TOP1_FLOOR` | 滤空时 Top1 兜底地板，默认 **0.15** |
| `RAG_REJECT_MAX_DISTANCE` | 向量距离上限（仅 `filter_relevant` 调试用；正式问答不用） |
| `RAG_RELATIVE_MAX_GAP` | 与 Top1 距离差（同上，调试用） |
| `REDIS_URL` | 可选；投研 A 股代码表缓存；空则跳过 |
| `SMTP_*` / `RESEARCH_DEFAULT_EMAIL` / `RESEARCH_GRAPH_TIMEOUT_SEC` | 投研发信与图超时（默认 90s）；见投研设计文档 |
| （前端约定，非必须进 `.env`） | 入库 Axios `timeout` 建议 **600000**（10 分钟）；同步问答/投研 `askChat` 建议 **120000**；UI 主路径为 SSE（`askChatStream`，见 [chat-sse-design.md](./chat-sse-design.md)） |

前后端：Vite **5173** / FastAPI **8000**。CORS：`allow_origins` 读配置；`allow_headers` 含 `Authorization`；Token 在 **localStorage**（非 Cookie），`allow_credentials` 可 false。

**同步长请求**：入库（解析 + Embedding）在**单次 HTTP** 内完成。问答 UI 主路径为 SSE（`POST /api/chat/stream`，见 [chat-sse-design.md](./chat-sse-design.md)）；同步 `POST /api/chat` 仍保留供脚本/兼容。超时与前端等待见 §7.4。

### 2.3 仓库与工程目录结构

```
knowledge-hub/
├── .docs/
│   ├── knowledge-qa-design.md
│   ├── rbac-menu-design.md      # User–Role–Menu 侧栏与系统管理
│   ├── chat-dual-mode-design.md
│   ├── chat-sse-design.md
│   ├── stock-research-agent-design.md
│   └── phase/
│       ├── knowledge-qa-phase1-design.md
│       ├── knowledge-qa-phase2-design.md
│       ├── knowledge-qa-phase3-design.md
│       └── knowledge-qa-phase4-design.md
├── .cursor/rules/               # Cursor 约定（overview / backend / frontend）
├── scripts/                     # 仓库根：迁移 + verify_*.py（含 verify_rbac_menu 等）
├── backend/
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── .env
│   ├── .env.example
│   ├── scripts/                 # 部分 phase 回归脚本
│   ├── data/
│   │   ├── kb/
│   │   └── chroma/
│   └── app/
│       ├── __init__.py
│       ├── main.py
│       ├── common/
│       │   ├── config.py
│       │   ├── db.py
│       │   ├── errors.py
│       │   ├── response.py
│       │   ├── chroma.py
│       │   ├── audit.py
│       │   ├── logging_util.py
│       │   ├── redis_client.py   # 可选 Redis
│       │   └── sse.py            # SSE 帧格式
│       ├── models/
│       │   ├── user.py
│       │   ├── rbac.py          # role / menu / user_role / role_menu
│       │   ├── document.py
│       │   ├── chunk.py
│       │   ├── conversation.py
│       │   └── message.py
│       ├── schemas/
│       │   ├── auth.py
│       │   ├── chat.py
│       │   └── system.py        # 用户 / 角色 / 菜单请求体
│       ├── api/                 # HTTP 路由层（薄）
│       │   ├── auth.py          # register / login / me
│       │   ├── users.py · roles.py · menus.py
│       │   ├── documents.py
│       │   └── chat.py          # /api/chat、/api/chat/stream、/api/conversations
│       ├── services/            # 业务层
│       │   ├── auth.py
│       │   ├── user_admin.py · role_admin.py · menu_admin.py
│       │   ├── menu_tree.py     # /me 与管理端菜单树
│       │   ├── ingest.py        # 入库/列表/删除
│       │   ├── chat.py          # rag 检索生成 / direct → agent
│       │   └── qa.py            # rag 组 prompt、调 LLM
│       ├── agent/               # 投研 Multi-Agent（mode=direct）；拓扑见 graph.py
│       │   ├── graph.py         # 同步固定拓扑 + 外层超时（勿再建顶层 app/graph/）
│       │   ├── stream.py        # SSE 增量执行（stage + Writer 流）；见 chat-sse
│       │   ├── state.py
│       │   ├── logging_util.py  # 图内 deadline 辅助
│       │   ├── agents/          # coordinator / quote|market|news|finance / writer / mailer
│       │   └── tools/           # tencent / finance(AKShare) / symbol / email / report_pdf
│       ├── auth/                # 认证支撑
│       │   ├── security.py      # bcrypt + PyJWT
│       │   ├── deps.py          # JWT + 查库确认 status=1
│       │   └── seed.py          # 角色/菜单/role_menu + 默认 admin（lifespan）
│       ├── ingest/              # 入库支撑
│       │   ├── parser.py
│       │   └── chunker.py
│       ├── rag/
│       │   ├── embedding.py     # OpenAIEmbeddings（SiliconFlow BGE-M3）
│       │   ├── chroma_store.py
│       │   ├── bm25_store.py    # 内存 BM25（jieba；启动从 DB 重建）
│       │   ├── retriever.py     # 双路召回 + RRF
│       │   └── rerank.py        # BGE Rerank + 分数门控
│       └── llm/
│           └── client.py        # ChatOpenAI（SiliconFlow 对话）
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── index.html
    ├── .env.development
    └── src/
        ├── main.js              # 引入 assets/css/global.css
        ├── App.vue                  # 仅 RouterView + 登录后 loadMe
        ├── assets/
        │   └── css/
        │       └── global.css   # 全局样式唯一入口（无 styles/）
        ├── layouts/
        │   └── AppLayout.vue        # 路由父级：左侧菜单壳 + 顶栏用户区（见 rbac-menu）
        ├── api/
        │   ├── http.js            # Bearer from localStorage；401→登录
        │   ├── auth.js
        │   ├── users.js · roles.js · menus.js
        │   ├── documents.js
        │   └── chat.js
        ├── router/
        │   └── index.js
        ├── stores/
        │   ├── user.js
        │   ├── document.js
        │   ├── createChatStore.js   # rag / direct 共用工厂
        │   ├── chat.js              # 知识库问答
        │   └── directChat.js        # 投研助手
        ├── utils/
        │   ├── markdown.js          # 助手 Markdown 安全渲染
        │   └── icons.js             # Element Plus Icons 名 → 组件
        ├── views/
        │   ├── auth/
        │   │   ├── LoginView.vue
        │   │   └── RegisterView.vue
        │   ├── system/
        │   │   ├── UserManageView.vue
        │   │   ├── RoleManageView.vue
        │   │   └── MenuManageView.vue
        │   ├── documents/
        │   │   └── DocumentListView.vue
        │   └── chat/
        │       ├── ChatView.vue          # 知识库问答 /chat/rag
        │       └── DirectChatView.vue    # 投研助手 /chat/direct
        └── components/
            ├── ingest/
            │   └── UploadPanel.vue
            ├── system/
            │   └── IconSelect.vue       # 菜单图标选择
            └── chat/
                ├── ChatWorkspace.vue
                ├── MessageList.vue
                ├── CitationList.vue
                └── ChatInput.vue
```

**约定**：

| 项 | 说明 |
|----|------|
| 后端包 | `backend/app/`；启动：`uvicorn app.main:app --reload` |
| 前端 | Node v24.15.0；`npm run dev` → 5173 |
| Token | **localStorage** + `Authorization: Bearer`（JWT） |
| Token 过期 | 401 → 清 Token → 跳登录 |
| 页面 | 登录、注册、文档管理；知识库问答 `/chat/rag`、投研助手 `/chat/direct`；系统管理 `/system/users|roles|menus`（侧栏由 menus 驱动） |
| 同名文件 | **拒绝上传**；删除为**物理删除**（先 Chroma 再库/文件，见 §4.3）后再传 |

---

## 3. 后端模块拆分

### 3.1 common

统一响应、错误码、异常、Settings、DB 装配、**CORS 中间件**（读 `CORS_ORIGINS`，放行 `Authorization`）。

### 3.2 auth（JWT + RBAC）

- **注册**：用户名 + 密码（**bcrypt** 哈希）→ 建 `sys_user` → 绑定角色 **`user`**（`sys_user_role`）
- **登录**：校验密码且 `status=1` → **PyJWT** 签发 access token（`JWT_EXPIRE_HOURS`，默认 24）→ 返回 Token + 用户基本信息
- **鉴权依赖 `deps.py`**：解析 JWT → **再查库**用户存在且 `status=1`，否则 `40101`
- **RBAC**：User–Role–Menu 五表 + 种子数据（见 §5.1.1 与 [rbac-menu-design.md](./rbac-menu-design.md)）；接口只校验已登录；侧栏按菜单裁剪
- **种子（必做）**：`auth/seed.py` 在 **lifespan 启动时**幂等执行（见 §4.4）：角色/菜单/role_menu + 默认用户 **`admin` / `123456`**（bcrypt 哈希，`status=1`，绑 `admin` 角色）；已存在则跳过，不覆盖密码
- **登出**：前端删 localStorage
- **`GET /api/auth/me`**：返回 `id`、`username`、`status`、`roles[]`、`menus`（树；无 `permissions`）

### 3.3 ingest

- **共享库**：入库不绑定上传者；列表/删除/检索均不按 `user_id` 过滤（表亦无该列）
- **类型白名单**：仅 `pdf` / `docx` / `md` / `txt`（扩展名）；其它（含 `.doc`）→ `42201`
- **大小**：可先读 `Content-Length` 粗拦，**最终以实际读入字节**为准；超限 `41301`（未通过不落盘）
- **同名**：`filename` **全库** UNIQUE；已存在 → `40901`（预检 + 最终 INSERT 撞 UNIQUE 均转 `40901`）
- **`title`**：默认取文件名去扩展名
- **同步入库**：先在内存/临时区完成解析、切分、Embedding，**成功后再**写库 / 落盘 / 写 Chroma（见 §4.1）；失败清临时并回滚已写入部分 → `50001`
- 解析后**无有效正文**（空文件、纯图 PDF、坏文件等）→ `50001`（不是 `42201`）
- **删除**：见 §4.3（先 Chroma，失败整单失败）
- **重新解析**：用 `KB_DIR` 原文件按当前解析/切分规则原地重建 chunk / Chroma / BM25（保留 `document.id` 与原文件）；单文档 `POST /api/documents/{id}/reingest`，全部 `POST /api/documents/reingest-all`（见 §4.5）

### 3.4 rag

- Embedding（BGE-M3）+ Chroma 向量与 BM25 双路召回，RRF 融合（各路与融合条数读 `RAG_HYBRID_PATH_TOP_K`，默认 20）
- **向量化输入**：有实质 `heading_path`（非空且非「正文」）时拼 `heading_path + "\n" + content`；Chroma `documents` / MySQL `chunk.content` 仍存纯正文
- Rerank（BGE）取 `RAG_TOP_K`（默认 8），再按精排 **relevance_score** 做分数门控（见 §6.2）
- BM25：进程内索引；启动 lifespan 从 MySQL 全量重建；入库/删除/**重新解析**同步增删；分词 jieba + 英文小写；索引文本含 title / filename / heading_path / content
- Collection **必须** `metadata={"hnsw:space": "cosine"}`（不用默认 `l2`；建后不可改，换空间须重建 collection）
- `query` 返回的是 **distance**（越小越近）；正式拒答以精排分数为准，不用 distance 二次砍杀
- `chroma_id`：`{document_id}_{chunk_index}`（删除文档时用）
- 单 worker（多进程时各进程各自重建 BM25）

### 3.5 chat

- **会话创建（chat 懒建）**：`conversationId` **可选**；缺省 / `null` 时由 `/api/chat` **自动** `INSERT conversation`（归属当前用户，含 `mode`），响应带回 `conversationId`；前端「新对话」只清本地状态
- 已传 `conversationId`：校验 `conversation.user_id == current_user.id`，否则 `40401`；请求 `mode` 须与会话一致（见 [chat-dual-mode-design.md](./chat-dual-mode-design.md)）
- **rag 流程**：**混合检索 → Rerank 分数门控 → 空则拒答，否则 LLM 带引用生成**（生成**不带**历史）；检索与精排均用当前用户消息原文
- **direct**：跳过检索；现网为投研 Multi-Agent（无闲聊历史）；详见 [stock-research-agent-design.md](./stock-research-agent-design.md)

---

## 4. 数据流

### 4.1 文档入库（同步；先算完再落库，Chroma 最后写）

不做 `PROCESSING` 占坑，也无僵尸清理。库里有行 = 已成功入库。

```
前端上传
  → 校验类型与大小（未通过：不落盘、不入库存档）
  → filename 已存在？ → 40901
  → 读入内存或临时文件（title = 文件名去扩展名）
  → 解析 → 无有效正文？→ 清临时 → 50001
  → 切分（§6.4）→ Embedding（内存中准备好 chunks）
  → INSERT document（IntegrityError → 40901）→ 得到 documentId
  → 写 chunk；落盘 KB_DIR/{document_id}/{filename}
  → 【最后】写 Chroma（id=`{docId}_{idx}`）→ 同步 upsert 内存 BM25
  → 返回 documentId

失败回滚（保持简单）：
  → 打日志；清临时文件
  → 若已写 Chroma：按已知 chroma_id 删除
  → 若已落库：删 chunk + 文件 + DELETE document；并尽量同步删 BM25
  → 返回 50001
```

说明：耗时长的解析/Embedding 在**入库存档之前**完成，失败时通常无库行可删。整条链路仍在**同一次上传 HTTP** 内同步完成；超时策略见 §7.4。进程被杀时最多残留临时文件（可忽略或手工清 `KB_DIR` 临时目录），**不会**因半成品行占住同名 UNIQUE。

### 4.2 问答（rag：混合检索 → Rerank → 生成/拒答）

```
message + mode + 可选 conversationId（须已登录）
  → 无 conversationId：INSERT conversation（user_id=当前用户，mode）→ 得到 id
  → 有 conversationId：校验会话归属与 mode 一致，否则 40401 / 40001
  → 落库 user 消息；title 空则截断首问
  → 【rag】向量 + BM25 双路召回 → RRF 融合（RAG_HYBRID_PATH_TOP_K）
  → Rerank（送入「标题 | 小节 + 正文」）取 RAG_TOP_K → 精排分数门控（§6.2）
  → 门控后为空 → 拒答话术（rejected=true），不调 LLM
  → 否则：当前问题 + **精排后**片段 → 一次 LLM 生成带 [n] 引用的答案（**不带历史**）
  → 落库 assistant（含 citations）→ 返回（含 conversationId，供前端固定后续轮次）

LLM 失败：若本请求已建会话/已落 user，保留之；可写一条失败说明 assistant，或仅返回 50010
```

说明：会话由 `/api/chat` 懒建；列表/详情/删除走 `/api/conversations`（仅本人）。**direct** 路径（无检索、投研 Multi-Agent）见 [stock-research-agent-design.md](./stock-research-agent-design.md)；会话 mode 外壳见 [chat-dual-mode-design.md](./chat-dual-mode-design.md)。

### 4.3 删除（物理删除）

**先清 Chroma，成功后再清 MySQL / 文件**（避免已删文档仍被检索到）：

1. 查出该文档 `chroma_id` 列表
2. `chroma.delete(ids=[...])` — **失败则整单失败**（`50000`），不删库行、不删文件；客户端可重试
3. 成功后再：`DELETE chunk` → 删 `KB_DIR` 文件 → `DELETE document` → 同步从内存 BM25 移除

完成后同名可再上传。

### 4.4 启动与 health

```
lifespan：
  → 探测 MySQL 一次（失败则启动失败）
  → create_all 建表（若不存在）
  → 执行 auth/seed.py（幂等）：角色/菜单/role_menu + 默认用户 admin
  → 打开 Chroma（目录不存在则创建）
  → 从 MySQL 全量重建内存 BM25 索引
  → 预热 A 股代码表（warm_symbol_cache；失败仅 WARNING，不挡启动）
```

种子失败则**启动失败**（演示依赖可登录的 `admin`）。`/api/health`：MySQL 可达；Chroma 可打开。

### 4.5 重新解析（原地重建索引）

用于解析/切分规则升级后，让**已入库**文档吃到新逻辑，无需用户再选文件上传。

```
POST /api/documents/{id}/reingest 或 /reingest-all
  → 读 KB_DIR/{document_id}/{filename}
  → 解析 → 切分 → Embedding（同入库；失败则不动索引）
  → 删旧 Chroma ids + BM25
  → 替换 MySQL chunk 行
  → 写新 Chroma + BM25 → commit
  → 保留 document 行与原文件（id / filename 不变）
```

- 单文档失败 → `50001` / `40401` / Chroma 删失败 → `50000`（与删除语义一致）
- 全部重新解析：按 id 升序逐个执行；单项失败记入 `errors`，不中断其余；返回 `total` / `ok` / `failed`
- 前端文档列表提供「重新解析」「全部重新解析」（超时同入库 600s）

---

## 5. 数据模型与存储设计

### 5.1 MySQL

建表方式：`create_all`。

#### 5.1.1 认证与 RBAC

> **现网以 [rbac-menu-design.md](./rbac-menu-design.md) 为准**：已从 User–Role–Permission 改为 User–Role–Menu；废弃 `sys_permission` / `sys_role_permission`。下列为摘要。

**`sys_user`** — 用户

- `id` BIGINT PK
- `username` VARCHAR UNIQUE
- `password_hash` VARCHAR
- `status` SMALLINT（`1`=正常 / `0`=禁用）
- `created_at`, `updated_at` DATETIME（另有审计列，见实现）

> 角色走 `sys_user_role`。

**`sys_role`** — 角色

- `id` BIGINT PK
- `code` VARCHAR UNIQUE（`admin` / `user`）
- `name` VARCHAR
- `created_at`, `updated_at` DATETIME

**`sys_menu`** — 菜单（目录 / 菜单 / 按钮）

- `id` BIGINT PK；`parent_id`；`name`；`path`；`icon`；`type`（`catalog`/`menu`/`button`）；`perms`；`sort`；`visible`（`1`/`0`）；`status`（`1`/`0`）等（详见 rbac-menu 规格；无 `component` 列）

**`sys_user_role`** — 用户–角色

- `user_id` BIGINT
- `role_id` BIGINT
- 联合唯一 `(user_id, role_id)`

**`sys_role_menu`** — 角色–菜单（方案 A：只存勾选，多为叶子；`/me` 读时闭包补祖先）

- `role_id` BIGINT
- `menu_id` BIGINT
- 联合唯一 `(role_id, menu_id)`

**种子数据**（lifespan 启动时由 `auth/seed.py` **幂等**写入，已存在则跳过）：

| 角色 | 说明 |
|------|------|
| `admin` | 管理员；绑系统管理三菜单 + 业务三菜单（叶子） |
| `user` | 普通用户；注册默认；仅绑业务三菜单（知识库问答 / 投研助手 / 文档） |

| 种子用户 | 密码 | 状态 | 角色 |
|----------|------|------|------|
| `admin` | `123456` | `1` | `admin` |

> 密码以 **bcrypt** 写入 `password_hash`；仅本地/演示默认账号。用户名已存在时**不改密码、不重置角色**。

接口：**合法 JWT 即可访问业务 API**；`/me` 返回 roles + menus 树。管理端与侧栏细节见 [rbac-menu-design.md](./rbac-menu-design.md)。

#### 5.1.2 知识库与会话

**`document`**（**全员共享库**；**无** `user_id`；**无** `status`）

- `id` BIGINT PK
- `title` VARCHAR
- `filename` VARCHAR **UNIQUE**（全库唯一）
- `file_path` VARCHAR
- `file_type` VARCHAR（pdf/docx/md/txt）
- `size_bytes` BIGINT
- `created_at`, `updated_at` DATETIME

> 有行即表示入库成功。失败不落库行（或回滚删行）。**会话仅本人，文档全员共享**。

**`chunk`**

- `id` BIGINT PK
- `document_id` BIGINT
- `chunk_index` INT
- `heading_path` VARCHAR
- `content` TEXT
- `chroma_id` VARCHAR（格式 **`{document_id}_{chunk_index}`**）
- `created_at` DATETIME

**`conversation`**

- `id` BIGINT PK
- `user_id` BIGINT
- `title` VARCHAR（可空；首条用户消息截断写入，见 §4.2）
- `mode` VARCHAR（`rag` \| `direct`，NOT NULL，默认 `rag`）
- `created_at`, `updated_at` DATETIME

**`message`**

- `id` BIGINT PK
- `conversation_id` BIGINT
- `role` VARCHAR（user / assistant / system）
- `content` TEXT
- `citations` JSON — 只存 snippet 等短字段，见下
- `created_at` DATETIME

检索与生成只读 `content`。

`citations` 元素：

```json
{
  "doc_id": 1,
  "chunk_id": 10,
  "title": "文档标题",
  "heading_path": "章 > 节",
  "snippet": "不超过约 200 字的摘录"
}
```

### 5.2 Chroma / 本地文件

- Collection：`kh_chunks`；创建时指定 **`hnsw:space: cosine`**
- 向量元数据：`document_id`、`chunk_id`、`heading_path`、`filename`
- 路径：`KB_DIR/{document_id}/{filename}`；`CHROMA_DIR/`

---

## 6. 问答与 RAG 细则

### 6.1 管线

```
当前问题
  → 向量 + BM25 双路召回（各 RAG_HYBRID_PATH_TOP_K）
  → RRF 融合
  → BGE Rerank（文本=标题|小节+正文；取 RAG_TOP_K）
  → 精排分数门控（§6.2）
  → 为空则拒答；否则带精排后片段一次 LLM 生成（带引用）
```

正式问答路径**不再**对精排结果做向量 distance 二次过滤（BM25 捞回的正确命中常有较大 distance，会被误杀）。

### 6.2 拒答与精排分数门控

拒答依据精排 `relevance_score`（约 0~1），不是 cosine distance。对 Rerank 返回的每条按序应用：

1. **软地板**：`score < RAG_RERANK_MIN_SCORE` → 丢弃（挡近 0 噪声；默认 0.05）
2. **相对落差**：`score < top1_score × RAG_RERANK_RELATIVE_RATIO` → 丢弃（默认比例 0.5）
3. **Top1 兜底**：滤完为空且 `top1_score >= RAG_RERANK_KEEP_TOP1_FLOOR` → 至少保留 Top1（默认 0.15，避免短问误拒）

| 条件 | 行为 |
|------|------|
| 融合为空，或分数门控后为空 | 固定话术拒答，`rejected=true`，不调 LLM |
| 门控后剩余 ≥1 条 | **仅**用剩余片段进生成与 citations |

- `RAG_REJECT_MAX_DISTANCE` / `RAG_RELATIVE_MAX_GAP` 仅供 `filter_relevant` 调试/无精排场景，**正式 chat.ask 不调用**
- 生成 prompt：只依据给定片段回答；禁止编造；勿输出「原文未完整」等元说明（规则拒答为主，prompt 为辅）

### 6.3 引用

答案用 `[n]` 标注；`citations` 存 doc_id / chunk_id / title / heading_path / snippet（短摘录）。

### 6.4 切片与解析边界

切分算法四种格式共用（`chunk_text`）：先按 Markdown `#` 标题栈填 `heading_path`，再段内按字符滑窗。

- **计量**：max / overlap 按 **字符** `len(text)`；建议 max≈**800**、overlap≈**100**
- **有标题**：按标题层级切块，`heading_path` 如 `章 > 节`；无标题 → `"正文"`，按段落累积满约 800 字切一刀并 overlap
- **类型**：仅 `pdf` / `docx` / `md` / `txt`；其它（含 `.doc`）→ `42201`
- **无有效正文**（空文件、纯图 PDF、损坏等）：入库失败 → `50001`（扩展名合法时不用 `42201`）；扫描件不做 OCR

**解析如何得到标题（再进统一切分）**：

| 格式 | 行为 |
|------|------|
| **md / txt** | 解码（UTF-8 → GBK → replace）；md 自带 `#` 原样保留；txt 无 `#` 则多为「正文」 |
| **docx** | `Heading 1..6` / `标题 n` / `Title` 优先转为 `#`；否则短行 + 加粗或偏大字号启发式（≤40 字、无句末标点）→ `#`/`##`；表格摊成文本行 |
| **pdf** | 有书签（`get_toc()`）→ 按页注入书签为 `#`…；无书签 → 按 `(y,x)` 阅读顺序 + 相对正文中位字号：≥2.0× 不当标题（姓名等），≥1.4× → `#`，≥1.15× 且已有一级节 → `##`（跨页保持一级节） |

规则升级后旧文档须 **重新解析**（§4.5）才会更新 chunk / 向量。

### 6.5 多轮与双模式

- 检索 / 精排（仅 **rag**）：用**当前用户消息原文**（不改写、不拼历史）
- **rag 生成**：不带对话历史（仅当前问题 + 检索片段）
- **direct**：无检索；投研图产出 `report_md`；见 [stock-research-agent-design.md](./stock-research-agent-design.md)
- 后续可选：多轮按需 query rewrite，改写结果只用于检索

---

## 7. 错误处理与可靠性

### 7.1 入库

- 同名 / UNIQUE → `40901`；超限 → `41301`；扩展名不在白名单 → `42201`
- 解析后无有效正文 → `50001`（清临时）
- 中途失败 → §4.1 简单回滚（清临时；若已写则清向量/库行/文件）→ `50001`
- Embedding 失败可重试 1～2 次，仍失败再回滚

### 7.1.1 删除

- 按 §4.3：先 `chroma.delete`，失败 → `50000`，库与文件不动；成功后再删 MySQL / 文件

### 7.2 问答

- 规则拒答：`code=0` 且 `rejected=true`
- LLM 失败：保留 user；`50010` 或写失败说明 assistant
- 会话越权：`40401`

### 7.3 通用

- lifespan：MySQL **探测 1 次**失败即启动失败；`create_all` + **RBAC 菜单种子 / 默认 admin**；打开 Chroma；重建 BM25；可选预热代码表
- 单 worker（长入库期间其它请求会排队）
- 禁用用户：依赖层查库拦截

### 7.4 长请求：超时与前端等待

浏览器或网关默认超时（常见 60s）会先于业务失败切断连接，须**显式加长**并约定 UI。

| 环节 | 约定 |
|------|------|
| 入库 HTTP | 前端对该接口单独 `timeout = 600000`（10 分钟）；其它短接口可用默认（如 30s） |
| 问答 UI | **SSE** `POST /api/chat/stream`（见 [chat-sse-design.md](./chat-sse-design.md)）；Vite 对 `/api/chat/stream` 单独代理（关缓冲）；连接等待建议 ≥ 120s |
| 问答同步 | `POST /api/chat` 仍可供脚本；Axios `timeout = 120000`（2 分钟） |
| 本地网关 | 直连 Vite→FastAPI 即可；若加 Nginx 等，入库 `proxy_read_timeout` **≥ 600s**；SSE 须 `proxy_buffering off` / `X-Accel-Buffering: no`，读超时 ≥ 120s |
| 后端 | Uvicorn/FastAPI **不**另设更短的请求硬杀；入库 Embedding 失败走 `50001` / 回滚，问答 LLM/Embedding 失败走 `50010`；勿依赖网关超时当业务失败 |

**前端等待（入库）**：

- 上传中：按钮 loading + 禁用重复提交；文案提示「大文件解析与向量化较久，请勿关闭或刷新页面」
- 成功：提示并刷新文档列表
- 超时或网络错误：提示失败并可重试；不要假装已成功（未成功则库中无该文档，同名一般仍可再传）
- 用户刷新/离开：无法取消已在跑的后端任务；若请求最终失败则无库行

**前端等待（问答 SSE）**：

- 发送中可展示 `stage` 文案；支持「停止」（Abort）；取消不落半成品 assistant
- `done` 到达后用服务端 `answer` 覆盖本地拼接；引用在打字前经 `citations` 事件出现

**演示建议**：优先用中小文档验证主链路；接近 `INGEST_MAX_MB` 的大 PDF 允许等待数分钟，属预期而非缺陷。

---

## 8. 测试策略

- 启动后可用种子账号 `admin` / `123456` 登录拿 JWT；注册用户默认角色 `user`；禁用用户持旧 Token → 401
- `/me` 返回 roles + menus；种子 `admin` 的 roles 含 `admin`
- 同名 `40901`；并发双传同名至少一笔为 `40901`（非 500）
- 入库中途失败后同名可再传（无残留库行）
- 入库前端 timeout ≥ 业务耗时量级
- 删除：Chroma 先删成功再清库/文件；Chroma 失败则文档仍在、可重试
- 非白名单类型（如 `.doc`）→ `42201`；空文档 / 纯图 PDF → `50001` 且同名可再传
- **共享库**：用户 A 上传后，用户 B 可列表 / 删除 / 问答命中该文档
- 会话越权 `40401`
- 融合为空或精排分数门控后为空 → 拒答；否则仅带精排后片段引用问答（collection 为 cosine）

---

## 9. API 约定

| 模块 | 路径前缀 | 说明 |
|------|----------|------|
| 认证 | `/api/auth` | `POST /register`、`POST /login`、`GET /me`（roles + menus） |
| 系统管理 | `/api/users`、`/api/roles`、`/api/menus` | 用户/角色/菜单 CRUD（见 [rbac-menu](./rbac-menu-design.md)） |
| 文档 | `/api/documents` | 上传、列表、详情、**物理删除**（先 Chroma）、**重新解析**（`POST /{id}/reingest`、`POST /reingest-all`）；共享库：任意已登录用户可操作全库 |
| 会话 | `/api/conversations` | 列表 / 消息详情 / 删除；仅本人 |
| 问答 | `/api/chat` | 同步整包；`conversationId` / `mode` 可选（缺省 `rag`）；缺省则懒建会话并返回 id；已有则校验归属与 mode；rag 检索范围 = 全库；direct 见 [stock-research](./stock-research-agent-design.md) |
| 问答流式 | `/api/chat/stream` | SSE；请求体同 `/api/chat`；事件协议见 [chat-sse](./chat-sse-design.md)；UI 主路径 |
| 健康 | `/api/health` | MySQL + Chroma |

统一响应：`{ "code": 0, "message": "success", "data": {} }`

| code | 含义 |
|------|------|
| `40001` | 参数错误（含无效 `mode`、会话混聊、菜单删有子节点 / 内置节点等） |
| `40101` | 未登录 / Token 无效过期 / 用户禁用或不存在 |
| `40102` | 用户名或密码错误 |
| `40902` | 用户名已存在 |
| `40903` | 角色 code 已存在（`ROLE_EXISTS`） |
| `40401` | 文档不存在；或会话不存在 / 非本人 |
| `40901` | 同名文档已存在 |
| `41301` | 超过上传大小上限 |
| `42201` | 不支持的文件类型（仅扩展名白名单） |
| `50001` | 入库失败（已回滚；含无有效正文、入库 Embedding 失败） |
| `50010` | 问答阶段 LLM/Embedding 失败 |
| `50000` | 内部错误（含删除时 Chroma 失败） |

---

## 10. 分阶段交付

| Phase | 内容 | 完成标准 | 设计文档 |
|-------|------|----------|----------|
| 1 | 骨架 + MySQL/Chroma + CORS + lifespan（create_all + seed 落库） | health 绿；种子用户 `admin` 行存在（密码已哈希） | [phase1](./phase/knowledge-qa-phase1-design.md) |
| 2 | 注册/登录/JWT + deps 查 status=1；me；登出靠前端清 Token | `admin`/`123456` 可登录；可注册；`/me` 可见 roles + menus（见 [rbac-menu](./rbac-menu-design.md)） | [phase2](./phase/knowledge-qa-phase2-design.md) |
| 3 | 同步 ingest（先算完再落库，Chroma 最后写）+ 同名拒绝 + 简单回滚 + 物理删除（先 Chroma） | 成功可见文档；失败可重传同名；删失败文档仍在 | [phase3](./phase/knowledge-qa-phase3-design.md) |
| 4 | 检索→生成问答 + 前端（登录/文档/对话；入库长 timeout + 等待文案） | **主链路可演示**（引用/拒答） | [phase4](./phase/knowledge-qa-phase4-design.md) |

---

## 11. 待实现时核实项

- SiliconFlow 限额与延迟
- Chroma × Python 3.12.9；确认 `kh_chunks` 为 cosine（误建成 l2 须删目录重建）
- `RAG_RERANK_MIN_SCORE` / `RELATIVE_RATIO` / `KEEP_TOP1_FLOOR` 默认是否合适（应用真实问答标定）
- 切片 max/overlap 最终数（默认建议见 §6.4）
- `INGEST_MAX_MB`（建议 50）与大文件实际入库耗时（是否常顶满 10 分钟）
- 前端入库 / 问答 Axios timeout 是否与本地代理一致

---

## 12. 现网对齐清单

- [x] 入库：先算完再落库；失败回滚；同名 → 40901
- [x] 物理删除：先 Chroma（失败整单失败）再库/文件
- [x] 问答为「混合检索→Rerank→生成/拒答」；rag 生成不带历史；direct 为投研 Multi-Agent（见 [stock-research](./stock-research-agent-design.md)）；检索用当前原文
- [x] Chroma 最后写；失败简单回滚
- [x] 切分按字符；无标题按段落滑窗；仅 pdf/docx/md/txt；无正文 → 50001；pdf toc/字号启发式、docx 样式/启发式见 §6.4
- [x] Embedding 输入可拼 heading_path；重新解析原地重建索引（§4.5）
- [x] JWT + 注册/登录；RBAC 菜单五表（见 [rbac-menu](./rbac-menu-design.md)）；lifespan 幂等种子含 `admin`/`123456`；API 只验登录
- [x] 会话归属；citations 只存 snippet
- [x] 会话由 `/api/chat` 懒建；首条后响应带回 `conversationId`
- [x] 文档为全员共享库；会话仍仅本人
- [x] 长请求：入库 10min；问答 UI 走 SSE（可停止）；同步 `/api/chat` 仍可用；前端 loading / stage 与超时文案
- [x] Chroma `hnsw:space=cosine`；精排分数门控（软地板 + 相对落差 + Top1 兜底），滤完为空则拒
- [x] 投研四路 Analyst（含 finance / AKShare）；侧栏菜单导航（非顶栏三链接）

---

## 附录：拍板结论对照

| 项 | 结论 |
|----|------|
| 用户/权限 | 注册+登录+JWT；RBAC 五表（user/role/menu/user_role/role_menu，见 [rbac-menu](./rbac-menu-design.md)）；lifespan 幂等种子（角色/菜单 + 用户 `admin`/`123456` 绑 admin）；注册绑 `user`；API 只验登录；侧栏按 menus；登出前端删 Token |
| 入库 | 先解析/Embedding，成功后再写库/落盘；Chroma 最后写；失败回滚；同名→40901；无正文→50001；无 PROCESSING / 无僵尸清理 |
| 解析/切分 | 字符窗 max≈800 / overlap≈100；标题来源见 §6.4（md 原样；docx 样式+启发式；pdf toc 或字号层级）；统一 chunk_text；可重新解析 |
| 长请求超时 | 入库 Axios 600s；问答 SSE + 同步 120s；Vite/Nginx SSE 去缓冲；前端长等待 / stage 文案 |
| 文档库 | 全员共享；`document` 无 `user_id`、无 `status`；任意登录用户可列表/删/被检索 |
| 删除 | 先 Chroma（失败整单失败）再 MySQL / 文件 |
| 问答 | 混合检索 → Rerank 分数门控 → 规则拒答/一次生成；检索全库 |
| 会话 | chat 懒建；`conversationId` 可选；列表/删仅本人 |
| 多轮 | rag 生成不带历史；direct 每轮独立投研任务（见 [stock-research](./stock-research-agent-design.md)）；检索/精排用当前原文 |
| 检索 | 向量 + BM25 → RRF → BGE Rerank；collection cosine |
| 拒答 | 融合为空或精排分数门控后为空（软地板 0.05 + 相对 0.5 + Top1 兜底 0.15） |
