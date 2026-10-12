<template>
  <div class="page fade-up">
    <div class="card panel">
      <div class="head">
        <div>
          <h1>文档管理</h1>
          <p class="sub">上传后即可在对话中检索引用</p>
        </div>
        <el-button @click="refresh" :loading="docStore.loading">刷新</el-button>
      </div>
      <UploadPanel @uploaded="refresh" />
      <div class="table-wrap">
        <el-table
          :data="docStore.items"
          v-loading="docStore.loading"
          empty-text="暂无文档"
          class="doc-table"
        >
          <el-table-column prop="id" label="ID" width="72" />
          <el-table-column prop="title" label="标题" min-width="160" show-overflow-tooltip />
          <el-table-column prop="filename" label="文件名" min-width="180" show-overflow-tooltip />
          <el-table-column label="类型" width="100">
            <template #default="{ row }">
              <span class="type-tag">{{ (row.fileType || '—').toUpperCase() }}</span>
            </template>
          </el-table-column>
          <el-table-column label="大小" width="110">
            <template #default="{ row }">
              {{ formatBytes(row.sizeBytes) }}
            </template>
          </el-table-column>
          <el-table-column prop="createdAt" label="创建时间" min-width="168" />
          <el-table-column label="操作" width="88" fixed="right">
            <template #default="{ row }">
              <el-button link type="danger" @click="onDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
/** 文档列表：上传面板 + 刷新/物理删除。 */
import { onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import UploadPanel from '../../components/ingest/UploadPanel.vue'
import { useDocumentStore } from '../../stores/document'

const docStore = useDocumentStore()

/** 字节数格式化为可读大小。 */
function formatBytes(n) {
  const bytes = Number(n)
  if (!Number.isFinite(bytes) || bytes < 0) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** 刷新文档列表。 */
async function refresh() {
  try {
    await docStore.refresh()
  } catch (err) {
    ElMessage.error(err?.message || '加载文档失败')
  }
}

/** 确认后物理删除文档。 */
async function onDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除「${row.filename}」？将物理删除索引与文件。`, '删除文档', {
      type: 'warning',
    })
    await docStore.remove(row.id)
    ElMessage.success('已删除')
  } catch (err) {
    if (err === 'cancel' || err === 'close') return
    ElMessage.error(err?.message || '删除失败')
  }
}

onMounted(refresh)
</script>

<style scoped>
.panel {
  padding: 22px 24px 20px;
}

.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.sub {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--muted);
}

.table-wrap {
  margin-top: 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.type-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.03em;
  color: var(--accent);
  background: var(--accent-soft);
  border: 1px solid var(--accent-border);
}

.doc-table {
  width: 100%;
}

:deep(.el-table) {
  --el-table-header-bg-color: var(--bg-subtle);
  --el-table-row-hover-bg-color: #f3f6f8;
  font-size: 13px;
}

:deep(.el-table th.el-table__cell) {
  font-weight: 600;
  color: var(--text-secondary);
}
</style>
