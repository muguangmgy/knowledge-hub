# Knowledge Hub

企业文档 RAG 问答 + 投研助手。写码细则以 `.cursor/rules/` 与当前代码为准，本文件只做路标。

## Setup

- 后端：`backend/.venv`，在 `backend/` 下启动服务（`:8000`）
- 前端：`frontend/`，`npm run dev` → `:5173`
- 回归：仓库根 `scripts/verify_*.py`

## Where things live

| 路径 | 用途 |
|------|------|
| `.cursor/rules/` | 写码约定（`project` always；`backend-fastapi` / `frontend-vue` 按 glob；`git-commit` / `interview` 按需） |
| `.docs/design/` | 历史设计规格 — **仅用户点名某篇时**才读 |
| `.docs/agents/` | Skill 配置（tracker / glossary / ADR）— 可读写 |
| `.docs/templates/` | 文档模板 |
| `.agents/skills/` | 已安装的 Matt skill 本体（日常不必翻） |
| `.scratch/` | 本地工单（可选；可不用） |

## Agent skills

### Issue tracker

Local markdown under `.scratch/<feature>/`（可不用）。See `.docs/agents/issue-tracker.md`.  
无工单时规格写在对话里即可；`/code-review` 无规格则 Spec 轴跳过。

### Domain docs

术语与 ADR 在 `.docs/agents/`（不是 `.docs/design/`）。See `.docs/agents/domain.md`.

### Commands

- `/setup-matt-pocock-skills` — 换 tracker 或重置配置时再跑
- `/grill-me` — 对齐需求
- `/tdd` — 先测后写
- `/code-review` — 对照某点审 diff
