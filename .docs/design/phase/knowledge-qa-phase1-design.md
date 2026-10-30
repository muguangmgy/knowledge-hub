# Knowledge Hub — Phase 1 设计文档（基础设施）

- **日期**：2026-10-12
- **状态**：已完成（历史阶段文档）
- **对应主文档**：[../knowledge-qa-design.md](../knowledge-qa-design.md)
- **依赖**：无（首阶段）
- **下一阶段**：[knowledge-qa-phase2-design.md](./knowledge-qa-phase2-design.md)
- **现网说明**：用户 `status` 为 `0|1`（非 ACTIVE 字符串）；RBAC 已改为 User–Role–Menu，见 [../rbac-menu-design.md](../rbac-menu-design.md)。下文保留阶段当时设计措辞。

---

## 1. 本阶段目标与完成标准

**目标**：搭好后端骨架，接通 MySQL / Chroma，lifespan 建表并幂等写入 RBAC 种子与默认 `admin` 用户；健康检查可用。

| 完成标准 | 说明 |
|----------|------|
| `/api/health` 绿 | MySQL 可达；Chroma 可打开 |
| 种子落库 | 角色 `admin`/`user`、权限关联存在；用户 `admin` 行存在且 `password_hash` 为 bcrypt（明文密码约定为 `123456`，本阶段**不提供**登录 API） |

---

## 2. 本阶段落地范围

### 2.1 目录与关键文件

```
backend/
├── pyproject.toml
├── requirements.txt
├── .env / .env.example
├── data/kb/ 、 data/chroma/
└── app/
    ├── main.py                 # FastAPI + lifespan + CORS + health
    ├── common/
    │   ├── config.py           # Settings（pydantic-settings）
    │   ├── db.py               # Engine / Session
    │   ├── errors.py
    │   └── response.py
    ├── models/                 # 全表模型，供 create_all
    │   ├── user.py
    │   ├── rbac.py
    │   ├── document.py
    │   ├── chunk.py
    │   ├── conversation.py
    │   └── message.py
    └── auth/
        └── seed.py             # 幂等种子（角色/权限/关联 + admin 用户）
```

本阶段**不实现** `api/` 路由、`services/` 业务、ingest、chat、前端。

### 2.2 依赖与环境

| 项 | 要求 |
|----|------|
| Python | 3.12.9 |
| MySQL | 8.0+（库 `knowledge_hub` 已创建） |
| 安装 | `uv venv --python 3.12.9` + `uv pip install -r requirements.txt` |

本阶段至少用到的包：`fastapi`、`python-multipart`、`pydantic-settings`、`sqlalchemy`、`pymysql`、`cryptography`、`bcrypt`、`chromadb`。  
（`PyJWT` / `langchain-core` / `langchain-openai` / 解析库可一并装进 `requirements.txt`，本阶段可不调用。）

**配置键（本阶段必用）**：`DATABASE_URL`、`KB_DIR`、`CHROMA_DIR`、`CORS_ORIGINS`。  
其余 LLM/JWT/RAG 键可在 `.env.example` 预留，Phase 2+ 再用。

默认：`KB_DIR` → `backend/data/kb/`，`CHROMA_DIR` → `backend/data/chroma/`；CORS 默认 `http://localhost:5173`；`allow_headers` 含 `Authorization`。

启动：`uvicorn app.main:app --reload`（端口 8000）。

---

## 3. 模块约定

### 3.1 common

- Settings、DB Session、统一响应 `{ code, message, data }`、错误码基座、CORS 中间件（读 `CORS_ORIGINS`）。

### 3.2 数据模型（create_all）

本阶段建**全部**业务表（与主文档 §5.1 一致），即使业务 API 尚未实现，避免后续反复迁表。

**认证 / RBAC**（摘要）：

- `kh_user`：`username` UNIQUE、`password_hash`、`status`（ACTIVE/DISABLED）
- `kh_role`：`code` UNIQUE（`admin` / `user`）
- `kh_permission`：`code` UNIQUE；本版种子 `type=api`
- `kh_user_role`、`kh_role_permission`：联合唯一

**知识库 / 会话**（建表即可，本阶段无业务写入）：

- `document`：无 `user_id`、无 `status`；`filename` UNIQUE
- `chunk`：`chroma_id` = `{document_id}_{chunk_index}`
- `conversation`、`message`

建表方式：`create_all`。

### 3.3 种子（auth/seed.py）

lifespan 启动时**幂等**执行：

| 角色 | 说明 |
|------|------|
| `admin` | 关联文档/问答相关 api 码 |
| `user` | 注册默认角色；关联文档/问答相关 api 码 |

| 种子用户 | 密码（明文约定） | 状态 | 角色 |
|----------|------------------|------|------|
| `admin` | `123456` | `ACTIVE` | `admin` |

- 密码以 bcrypt 写入；用户名已存在则**跳过**（不改密码、不重置角色）
- 种子失败 → **启动失败**

权限码示例（实现时列全即可）：`doc:upload`、`chat:ask` 等；本版接口不按 permission 拦截。

### 3.4 lifespan 与 health

```
lifespan：
  → 探测 MySQL 一次（失败则启动失败）
  → create_all 建表（若不存在）
  → 执行 auth/seed.py（幂等）
  → 打开 Chroma（目录不存在则创建；collection 名预留 kh_chunks，cosine 空间可在 Phase 3 正式创建）
```

`GET /api/health`：MySQL 可达；Chroma 可打开。可不要求登录。

---

## 4. API（本阶段）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | MySQL + Chroma |

统一响应：`{ "code": 0, "message": "success", "data": {} }`

---

## 5. 测试要点

- 启动成功；`GET /api/health` 返回成功
- 库中存在角色 `admin`/`user`、用户 `admin`，且 `password_hash` 非明文
- 再次启动不报错、不重复插入（幂等）
- MySQL 不可达时进程启动失败

---

## 6. 本阶段不做

- 注册 / 登录 / JWT / `/me` → [Phase 2](./knowledge-qa-phase2-design.md)
- 文档上传 / 删除 / Embedding → [Phase 3](./knowledge-qa-phase3-design.md)
- 问答与前端页面 → [Phase 4](./knowledge-qa-phase4-design.md)
