# Knowledge Hub — Phase 4 设计文档（问答与前端）

- **日期**：2026-10-13
- **状态**：已完成（RAG：混合检索 + Rerank 分数门控，与实现对齐）
- **对应主文档**：[../knowledge-qa-design.md](../knowledge-qa-design.md)
- **依赖**：[Phase 3](./knowledge-qa-phase3-design.md)（文档已可入库并写入 Chroma）
- **上一阶段**：[knowledge-qa-phase3-design.md](./knowledge-qa-phase3-design.md)

---

## 1. 本阶段目标与完成标准

**目标**：混合检索 → Rerank 分数门控 → 规则拒答 / 一次 LLM 带引用生成；会话懒建；前端主链路可演示。

| 完成标准 | 说明 |
|----------|------|
| 带引用问答 | 精排分数门控后有保留片段时返回答案与 citations |
| 拒答 | 融合为空或精排分数门控后为空 → `rejected=true` |
| 前端主链路 | 登录 → 上传/列表 → 对话提问可见引用或拒答 |

---

## 2. 本阶段落地范围

### 2.1 后端

```
backend/app/
├── api/
│   └── chat.py          # /api/chat、/api/conversations
├── services/
│   ├── chat.py          # 检索 → 拒答/生成
│   └── qa.py            # 组 prompt、调 LLM
├── rag/
│   ├── embedding.py
│   ├── chroma_store.py
│   ├── bm25_store.py    # 内存 BM25
│   ├── retriever.py     # 双路 + RRF
│   └── rerank.py        # BGE Rerank + 分数门控
└── llm/
    └── client.py        # ChatOpenAI（SiliconFlow OpenAI 兼容）
```

### 2.2 前端

```
frontend/
├── package.json 、 vite.config.js 、 index.html 、 .env.development
└── src/
    ├── api/http.js      # Bearer from localStorage；401→登录
    ├── api/auth.js 、 documents.js 、 chat.js
    ├── stores/user.js 、 document.js 、 chat.js
    ├── views/auth/LoginView.vue 、 RegisterView.vue
    ├── views/documents/DocumentListView.vue
    ├── views/chat/ChatView.vue
    └── components/ingest/UploadPanel.vue
        components/chat/MessageList.vue 、 CitationList.vue 、 ChatInput.vue
```

栈：Vue 3 + Vite + JavaScript + Element Plus + Pinia + Axios；开发端口 **5173**。

### 2.3 配置键（本阶段启用）

| 键 | 用途 |
|----|------|
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | 对话生成 |
| `RAG_TOP_K` | 精排后最终给模型条数，默认 8 |
| `RAG_HYBRID_PATH_TOP_K` | 向量 / BM25 各路召回与 RRF 融合，默认 20 |
| `RERANK_MODEL` | 默认 `BAAI/bge-reranker-v2-m3` |
| `RAG_RERANK_MIN_SCORE` | 精排软地板，默认 0.05 |
| `RAG_RERANK_RELATIVE_RATIO` | 精排相对落差，默认 0.5 |
| `RAG_RERANK_KEEP_TOP1_FLOOR` | Top1 兜底地板，默认 0.15 |
| `RAG_REJECT_MAX_DISTANCE` / `RAG_RELATIVE_MAX_GAP` | 仅 `filter_relevant` 调试用；正式问答不用 |

前端约定（可写 `.env.development`）：入库 Axios timeout **600000**；问答 **120000**。

---

## 3. 问答管线

```
当前问题
  → 向量 + BM25 双路召回 → RRF 融合（RAG_HYBRID_PATH_TOP_K）
  → BGE Rerank（标题|小节+正文；RAG_TOP_K）→ 精排分数门控
  → 为空则拒答；否则带精排后片段一次 LLM 生成（带引用）
```

- Collection 必须为 **cosine**；distance 仅作调试参考，正式拒答看精排分数
- 分数门控：软地板 `RAG_RERANK_MIN_SCORE` + 相对落差 `RAG_RERANK_RELATIVE_RATIO` + Top1 兜底 `RAG_RERANK_KEEP_TOP1_FLOOR`
- 融合为空或门控后为空 → 固定话术，`rejected=true`，不调 LLM
- 否则**仅**带精排后片段生成；答案用 `[n]`；`citations` 含 doc_id / chunk_id / title / heading_path / snippet
- 检索/精排：当前用户消息**原文**；生成：拼「当前之前最近 6 条」历史
- 检索范围 = **全库**文档

### 3.1 会话（chat 懒建）

- `POST /api/chat`：`conversationId` 可选；缺省则 `INSERT kh_conversation`（归属当前用户）并返回 id
- 已传 id：校验 `conversation.user_id == current_user.id`，否则 `40401`
- 前端「新对话」只清本地状态
- `GET/DELETE /api/conversations`：列表 / 消息详情 / 删除；**仅本人**

LLM 失败：保留已落 user 消息；`50010` 或写失败说明 assistant。

---

## 4. API（本阶段）

| 模块 | 路径 | 说明 |
|------|------|------|
| 问答 | `POST /api/chat` | 懒建会话；返回答案 / rejected / citations / conversationId |
| 会话 | `/api/conversations` | 列表、消息详情、删除；仅本人 |
| 健康 / 认证 / 文档 | 沿用 Phase 1–3 | |

| code | 含义 |
|------|------|
| `40401` | 会话不存在 / 非本人 |
| `50010` | 问答阶段 LLM/Embedding 失败 |
| `0` + `rejected=true` | 规则拒答（业务成功） |

---

## 5. 前端约定

| 项 | 说明 |
|----|------|
| Token | localStorage + Bearer；401 清 Token 跳登录 |
| 登出 | 前端删 Token（无后端 logout） |
| 入库 UI | loading + 禁用重复提交；提示勿刷新；超时勿假装成功 |
| 页面 | 登录、注册、文档管理（含上传）、对话（消息 + 引用列表） |

---

## 6. 测试要点

- 入库文档后提问：精排通过则带 citations；无关问题拒答
- 无 `conversationId` 首问返回 id；后续轮次带上 id；他人会话 id → `40401`
- 前端：`admin`/`123456` 登录 → 上传 → 对话主链路
- 入库/问答 timeout 与文案符合约定

---

## 7. 本阶段不做

- 问题改写 LLM、Router/Verification 多节点（BM25 + Rerank 已接入）
- 异步 SSE、按钮级权限、私有文档库

主链路演示通过即本规格交付完成。完整拍板见 [主文档](../knowledge-qa-design.md)。
