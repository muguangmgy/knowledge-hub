# Knowledge Hub — Phase 2 设计文档（认证与 JWT）

- **日期**：2026-10-12
- **状态**：已完成（历史阶段文档）
- **对应主文档**：[../knowledge-qa-design.md](../knowledge-qa-design.md)
- **依赖**：[Phase 1](./knowledge-qa-phase1-design.md)（表结构 + 种子 `admin` 已落库）
- **下一阶段**：[knowledge-qa-phase3-design.md](./knowledge-qa-phase3-design.md)
- **现网说明**：鉴权验 `status=1`；`/me` 返回 `roles` + `menus`（无 `permissions`），见 [../rbac-menu-design.md](../rbac-menu-design.md)。下文保留阶段当时设计措辞。

---

## 1. 本阶段目标与完成标准

**目标**：实现注册 / 登录 / JWT 鉴权与 `/me`；业务 API 依赖统一验登录 + ACTIVE（现网为 `status=1`）。

| 完成标准 | 说明 |
|----------|------|
| 种子可登录 | `admin` / `123456` 登录成功，拿到 access token |
| 可注册 | 新用户注册成功，默认角色 `user` |
| `/me` | 阶段目标为 `roles` + `permissions`；**现网**为 `roles` + `menus`（见 rbac-menu） |

---

## 2. 本阶段落地范围

### 2.1 目录与关键文件

```
backend/app/
├── api/
│   └── auth.py          # POST /register、POST /login、GET /me
├── services/
│   └── auth.py          # 注册 / 登录 /me 业务
└── auth/
    ├── security.py      # bcrypt + PyJWT
    ├── deps.py          # 解析 JWT → 查库确认 ACTIVE
    └── seed.py          # Phase 1 已有；本阶段不改语义
```

前端登录/注册**页面**归 Phase 4；本阶段可先用 HTTP 客户端验收。登出：前端删 localStorage，**无**后端 `/logout`。

### 2.2 配置键（本阶段启用）

| 键 | 用途 |
|----|------|
| `JWT_SECRET_KEY` | 签名密钥 |
| `JWT_ALGORITHM` | 如 HS256 |
| `JWT_EXPIRE_HOURS` | Access Token 有效期，默认 24 |

Token：`Authorization: Bearer <token>`；前端约定存 localStorage（Phase 4 实现）。

---

## 3. 模块约定

### 3.1 注册

- 入参：用户名 + 密码
- bcrypt 哈希 → `INSERT kh_user`（`ACTIVE`）→ `kh_user_role` 绑角色 **`user`**
- 用户名冲突 → `40902`

### 3.2 登录

- 校验密码且 `status=ACTIVE` → PyJWT 签发 access token
- 返回 Token + 用户基本信息
- 用户名或密码错误 → `40102`（不区分「无用户 / 密码错」亦可，保持安全习惯）

### 3.3 鉴权依赖 deps.py

- 解析 JWT → **再查库**用户存在且 `ACTIVE`，否则 `40101`
- 业务 API（Phase 3/4）统一依赖此 deps；**不按 permission 拦截接口**

### 3.4 GET /api/auth/me

返回：`id`、`username`、`status`、`roles[]`、`permissions[]`（权限码列表；前端本版可忽略显隐）。

### 3.5 RBAC 使用方式（本版）

- 五表 + 种子已在 Phase 1 落库
- 接口：**合法 JWT 即可**访问后续业务 API
- 注册只绑 `user`；`admin` 角色仅种子用户（及日后手工调整）

---

## 4. API（本阶段）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 注册 |
| POST | `/api/auth/login` | 登录，发 Token |
| GET | `/api/auth/me` | 需登录；roles + permissions |

统一响应：`{ "code": 0, "message": "success", "data": {} }`

| code | 含义 |
|------|------|
| `40101` | 未登录 / Token 无效过期 / 用户禁用或不存在 |
| `40102` | 用户名或密码错误 |
| `40902` | 用户名已存在 |

Token 过期：前端清 Token → 跳登录（Phase 4）。

---

## 5. 测试要点

- `admin` / `123456` 登录成功；错误密码 → `40102`
- 注册新用户成功；默认角色为 `user`；重复用户名 → `40902`
- 持 Token 调 `/me` 成功；种子 admin 的 `roles` 含 `admin`
- 无 Token / 坏 Token → `40101`
- 将用户标为 `DISABLED` 后，持旧 Token → `40101`

---

## 6. 本阶段不做

- 文档上传 / 删除 → [Phase 3](./knowledge-qa-phase3-design.md)
- 问答管线、会话、前端页面 → [Phase 4](./knowledge-qa-phase4-design.md)
- 按钮/菜单权限拦截（表结构保留即可）
