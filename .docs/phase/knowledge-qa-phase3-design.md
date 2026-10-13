# Knowledge Hub — Phase 3 设计文档（文档入库与删除）

- **日期**：2026-10-12
- **状态**：已完成

- **对应主文档**：[../knowledge-qa-design.md](../knowledge-qa-design.md)
- **依赖**：[Phase 2](./knowledge-qa-phase2-design.md)（JWT；业务接口需登录）
- **下一阶段**：[knowledge-qa-phase4-design.md](./knowledge-qa-phase4-design.md)

---

## 1. 本阶段目标与完成标准

**目标**：同步入库（解析 → 切分 → Embedding → 写库/落盘/Chroma）与物理删除；共享文档库。

| 完成标准 | 说明 |
|----------|------|
| 入库成功 | 列表可见文档；Chroma 有对应向量 |
| 失败可重传同名 | 失败回滚无残留库行；同名 UNIQUE 释放 |
| 删除 | 先 Chroma 成功再清库/文件；Chroma 失败则文档仍在、可重试 |

---

## 2. 本阶段落地范围

### 2.1 目录与关键文件

```
backend/app/
├── api/
│   └── documents.py        # /api/documents
├── services/
│   └── ingest.py           # 入库 / 列表 / 删除
├── ingest/
│   ├── parser.py
│   └── chunker.py
└── rag/
    ├── embedding.py        # OpenAIEmbeddings（SiliconFlow BGE-M3）
    └── chroma_store.py     # collection kh_chunks；cosine；写入/按 id 删除
```

本阶段**不做**检索问答（`retriever` / chat 归 Phase 4），但入库必须写 Chroma。

### 2.2 配置键（本阶段启用）

| 键 | 用途 |
|----|------|
| `KB_DIR` / `CHROMA_DIR` | 原文 / 向量目录 |
| `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` | 向量化 |
| `INGEST_MAX_MB` | 上传上限，建议默认 50 |

前端入库 Axios timeout **600000**（10 分钟）在 Phase 4 落地；本阶段可用长超时客户端自测。

---

## 3. 产品与数据约定

- **共享库**：`kh_document` 无 `user_id`；任意已登录用户可上传 / 列表 / 详情 / 删除全库
- **有行即成功**：无 `status` / 无 PROCESSING / 无僵尸清理
- **类型**：仅 `pdf` / `docx` / `md` / `txt`；其它（含 `.doc`）→ `42201`
- **大小**：最终以实际读入字节为准；超限 → `41301`
- **同名**：`filename` 全库 UNIQUE；已存在 → `40901`
- **`title`**：文件名去扩展名
- **路径**：`KB_DIR/{document_id}/{filename}`
- **Chroma**：collection `kh_chunks`；`hnsw:space=cosine`；id = `{document_id}_{chunk_index}`；metadata：`document_id`、`chunk_id`、`heading_path`、`filename`
- **BM25**：入库成功后同步写入内存索引；删除时同步移除（启动时从 MySQL 全量重建）

### 3.1 切片（§6.4）

- 按**字符** `len(text)`；max≈800、overlap≈100
- 有标题 → `heading_path`；无标题 → 空或 `"正文"`，段落滑窗
- 无有效正文（空文件、纯图 PDF 等）→ `50001`

---

## 4. 数据流

### 4.1 入库（先算完再落库，Chroma 最后写）

```
前端上传（需登录）
  → 校验类型与大小（未通过：不落盘、不入库存档）
  → filename 已存在？ → 40901
  → 读入内存或临时文件
  → 解析 → 无有效正文？→ 清临时 → 50001
  → 切分 → Embedding（内存准备 chunks）
  → INSERT kh_document（IntegrityError → 40901）→ documentId
  → 写 kh_chunk；落盘 KB_DIR/{document_id}/{filename}
  → 【最后】写 Chroma → 同步 upsert 内存 BM25
  → 返回 documentId

失败回滚：
  → 清临时；若已写 Chroma 则删向量；若已落库则删 chunk/文件/document
  → 50001
```

Embedding 失败可重试 1～2 次，仍失败再回滚 → `50001`（非问答用的 `50010`）。

### 4.2 删除（物理删除）

1. 查出 `chroma_id` 列表  
2. `chroma.delete` — 失败整单失败 `50000`，不动库与文件  
3. 成功后：`DELETE kh_chunk` → 删文件 → `DELETE kh_document`  

完成后同名可再上传。

---

## 5. API（本阶段）

前缀：`/api/documents`（均需登录）

| 能力 | 说明 |
|------|------|
| 上传 | multipart；同步入库 |
| 列表 | 全库 |
| 详情 | 按 id；不存在 → `40401` |
| 物理删除 | 先 Chroma |

| code | 含义 |
|------|------|
| `40101` | 未登录等 |
| `40401` | 文档不存在 |
| `40901` | 同名已存在 |
| `41301` | 超过大小上限 |
| `42201` | 不支持的文件类型 |
| `50001` | 入库失败（已回滚；含无正文、入库 Embedding 失败） |
| `50000` | 删除时 Chroma 失败等内部错误 |

---

## 6. 测试要点

- 登录后上传 pdf/docx/md/txt 成功；列表可见
- 同名 → `40901`；并发双传至少一笔 `40901`
- `.doc` → `42201`；空/纯图 PDF → `50001`，同名可再传
- 入库中途失败后无残留库行，同名可再传
- 删除：Chroma 成功后库与文件消失；人为让 Chroma 失败时文档仍在

---

## 7. 本阶段不做

- 向量检索问答、会话、引用生成 → [Phase 4](./knowledge-qa-phase4-design.md)
- 前端 UploadPanel / 文档页（Phase 4）；本阶段用 API 验收即可
- 异步入库 / 进度条 / 软删除
