<template>
  <div class="page admin-page fade-up">
    <el-card shadow="never" class="panel">
      <div class="toolbar">
        <el-button type="primary" @click="uploadVisible = true">上传文档</el-button>
        <el-button @click="refresh" :loading="docStore.loading">刷新</el-button>
      </div>
      <div class="table-wrap">
        <el-table
          :data="docStore.items"
          v-loading="docStore.loading"
          empty-text="暂无文档"
          stripe
          border
          height="100%"
          class="doc-table fill-table"
        >
          <el-table-column prop="title" label="标题" min-width="160" align="center" show-overflow-tooltip />
          <el-table-column prop="filename" label="文件名" min-width="180" align="center" show-overflow-tooltip />
          <el-table-column label="类型" width="100" align="center">
            <template #default="{ row }">
              <el-tag size="small" type="info">{{ (row.fileType || '—').toUpperCase() }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="大小" width="110" align="center">
            <template #default="{ row }">
              {{ formatBytes(row.sizeBytes) }}
            </template>
          </el-table-column>
          <el-table-column prop="createdAt" label="创建时间" min-width="168" align="center" />
          <el-table-column label="操作" width="88" fixed="right" align="center">
            <template #default="{ row }">
              <el-button link type="danger" @click="onDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <el-dialog
      v-model="uploadVisible"
      title="上传文档"
      width="520px"
      destroy-on-close
    >
      <UploadPanel @uploaded="onUploaded" />
    </el-dialog>
  </div>
</template>

<script setup>
/** 文档列表：上传走弹窗；刷新/物理删除。 */
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import UploadPanel from '../../components/ingest/UploadPanel.vue'
import { useDocumentStore } from '../../stores/document'

const docStore = useDocumentStore()
const uploadVisible = ref(false)

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

/** 入库成功：关弹窗并刷新列表。 */
async function onUploaded() {
  uploadVisible.value = false
  await refresh()
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
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: none;
}

.panel :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 16px 20px;
}

.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.table-wrap {
  flex: 1;
  min-height: 0;
}

.doc-table {
  width: 100%;
}

.fill-table {
  flex: 1;
}
</style>
