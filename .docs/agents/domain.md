# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

This repo keeps Matt Pocock skill domain docs under `.docs/agents/` (business design specs live in `.docs/design/`).

## Before exploring, read these

- **`.docs/agents/GLOSSARY.md`** if it exists
- **`.docs/agents/GLOSSARY-MAP.md`** if it exists: it points at one glossary per context. Read each one relevant to the topic.
- **`.docs/agents/adr/`**: read ADRs that touch the area you're about to work in.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. Domain docs are created lazily when terms or decisions actually get resolved.

## 不要和这些混淆

- `.docs/design/*.md`（含 `phase/`）：**历史设计规格**，只有用户明确点名某篇时才打开。
- 不要把历史设计里的接口字段当成现行实现依据；现行以代码 + `.cursor/rules` 为准。

## File structure

```
.docs/
├── design/                 ← 历史业务设计（点名才读）
│   ├── *.md
│   └── phase/
├── agents/                 ← Agent / Skill 资产（可读写）
│   ├── issue-tracker.md
│   ├── domain.md
│   ├── GLOSSARY.md         ← 有再写
│   └── adr/                ← 有再写
└── templates/              ← 文档模板
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `.docs/agents/GLOSSARY.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for later domain-modeling).

## Flag ADR conflicts

If your output contradicts an existing ADR under `.docs/agents/adr/`, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (…), but worth reopening because…_
