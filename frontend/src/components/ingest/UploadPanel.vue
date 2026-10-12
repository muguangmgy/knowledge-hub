<template>
  <div class="upload-panel">
    <el-upload
      drag
      class="uploader"
      :auto-upload="false"
      :show-file-list="false"
      :disabled="uploading"
      accept=".pdf,.docx,.md,.txt"
      @change="onFileChange"
    >
      <div class="upload-inner">
        <div class="icon" aria-hidden="true">↑</div>
        <p class="lead">拖拽或点击选择文件</p>
        <p class="tip">支持 pdf / docx / md / txt · 入库为同步请求，请勿刷新</p>
      </div>
    </el-upload>
    <div v-if="file" class="selected">
      <div class="file-meta">
        <span class="name">{{ file.name }}</span>
        <span class="size">{{ formatBytes(file.size) }}</span>
      </div>
      <el-button type="primary" :loading="uploading" :disabled="uploading" @click="onUpload">
        {{ uploading ? '入库中...' : '开始入库' }}
      </el-button>
    </div>
  </div>
</template>

<script setup>
/** 同步入库上传；loading 期间禁重复提交。 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useDocumentStore } from '../../stores/document'

const emit = defineEmits(['uploaded'])
const docStore = useDocumentStore()
const file = ref(null)
const uploading = ref(false)

/** 字节数格式化为可读大小。 */
function formatBytes(n) {
  const bytes = Number(n)
  if (!Number.isFinite(bytes) || bytes < 0) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** 选择本地文件（未自动上传）。 */
function onFileChange(uploadFile) {
  file.value = uploadFile.raw || null
}

/** 开始同步入库。 */
async function onUpload() {
  if (!file.value || uploading.value) return
  uploading.value = true
  try {
    await docStore.upload(file.value)
    ElMessage.success('入库成功')
    file.value = null
    emit('uploaded')
  } catch (err) {
    ElMessage.error(err?.message || '入库失败')
  } finally {
    uploading.value = false
  }
}
</script>

<style scoped>
.upload-panel {
  width: 100%;
}

.uploader {
  width: 100%;
}

:deep(.el-upload) {
  width: 100%;
}

:deep(.el-upload-dragger) {
  width: 100%;
  padding: 0;
  border-radius: var(--radius);
  border: 1.5px dashed var(--border-strong);
  background: var(--bg-subtle);
  transition: border-color 0.15s ease, background 0.15s ease;
}

:deep(.el-upload-dragger:hover) {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.upload-inner {
  padding: 28px 16px;
  color: var(--text-secondary);
}

.icon {
  width: 36px;
  height: 36px;
  margin: 0 auto 10px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--accent);
  font-size: 16px;
  font-weight: 700;
}

.lead {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
}

.tip {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--muted);
}

.selected {
  margin-top: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-radius: var(--radius);
  border: 1px solid var(--accent-border);
  background: var(--accent-soft);
}

.file-meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.name {
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.size {
  font-size: 12px;
  color: var(--muted);
}
</style>
