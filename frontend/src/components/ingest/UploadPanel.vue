<template>
  <div class="upload-panel">
    <el-upload
      ref="uploadRef"
      drag
      class="uploader"
      multiple
      :limit="6"
      :auto-upload="false"
      :show-file-list="false"
      :disabled="uploading"
      accept=".pdf,.docx,.md,.txt"
      :on-exceed="onExceed"
      @change="onFileChange"
    >
      <div class="upload-inner">
        <div class="icon" aria-hidden="true">↑</div>
        <p class="lead">拖拽或点击选择文件</p>
        <p class="tip">支持 pdf / docx / md / txt · 单次最多 6 个 · 入库为同步请求，请勿刷新</p>
      </div>
    </el-upload>

    <ul v-if="entries.length" class="file-list">
      <li v-for="(entry, idx) in entries" :key="entry.key" class="file-item">
        <div class="file-meta">
          <span class="name">{{ entry.file.name }}</span>
          <span class="size">{{ formatBytes(entry.file.size) }}</span>
          <template v-if="entry.error">
            <span class="phase">{{ phaseLabel(entry.error.phase) }}</span>
            <span class="reason">{{ reasonLabel(entry.error.reason) }}</span>
            <span class="msg">{{ entry.error.message }}</span>
          </template>
        </div>
        <el-button
          v-if="!uploading"
          link
          type="danger"
          @click="removeAt(idx)"
        >
          移除
        </el-button>
      </li>
    </ul>

    <div v-if="entries.length" class="actions">
      <el-button type="primary" :loading="uploading" :disabled="uploading" @click="onUpload">
        {{ uploading ? '入库中...' : '开始入库' }}
      </el-button>
    </div>
  </div>
</template>

<script setup>
/** 同步入库：N=1 走单文件接口；N>1 走批量；失败项按 index 保留。 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useDocumentStore } from '../../stores/document'

const emit = defineEmits(['uploaded'])
const docStore = useDocumentStore()
const uploadRef = ref(null)
const entries = ref([])
const uploading = ref(false)
let keySeq = 0

/** 字节数格式化为可读大小。 */
function formatBytes(n) {
  const bytes = Number(n)
  if (!Number.isFinite(bytes) || bytes < 0) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** 批内阶段：预检未开始 / 处理中。 */
function phaseLabel(phase) {
  if (phase === 'precheck') return '未开始'
  if (phase === 'process') return '处理中'
  return phase || ''
}

/** 批内原因码 → 短标签；原文仍单独展示 message。 */
function reasonLabel(reason) {
  const map = {
    duplicate: '同名',
    too_large: '超大',
    parse_failed: '解析失败',
    other: '其他',
  }
  return map[reason] || '其他'
}

/** 超出 6 个：提示且不入队。 */
function onExceed() {
  ElMessage.warning('单次最多上传 6 个文件')
}

/**
 * 选择本地文件（未自动上传）。
 * 以 entries 为源；选完后清空 el-upload 内部列表，避免与失败残留错位。
 */
function onFileChange(uploadFile) {
  const raw = uploadFile?.raw
  if (!raw) return
  if (entries.value.length >= 6) {
    ElMessage.warning('单次最多上传 6 个文件')
    uploadRef.value?.clearFiles?.()
    return
  }
  const dup = entries.value.some(
    (e) =>
      e.file === raw ||
      (e.file.name === raw.name &&
        e.file.size === raw.size &&
        e.file.lastModified === raw.lastModified),
  )
  if (!dup) {
    entries.value.push({
      key: `f-${++keySeq}`,
      file: raw,
      error: null,
    })
  }
  uploadRef.value?.clearFiles?.()
}

/** 从已选列表移除一项（未入库）。 */
function removeAt(idx) {
  entries.value.splice(idx, 1)
}

/** 开始同步入库：1 个走原接口，多于 1 个走批量。 */
async function onUpload() {
  if (!entries.value.length || uploading.value) return
  if (entries.value.length > 6) {
    ElMessage.warning('单次最多上传 6 个文件')
    return
  }

  uploading.value = true
  try {
    if (entries.value.length === 1) {
      await docStore.upload(entries.value[0].file)
      ElMessage.success('入库成功')
      entries.value = []
      emit('uploaded', { allOk: true })
      return
    }

    const files = entries.value.map((e) => e.file)
    const summary = await docStore.uploadBatch(files)
    const failed = Number(summary.failed || 0)
    const okCount = Number(summary.ok || 0)

    if (okCount > 0) {
      await docStore.refresh()
    }

    if (failed <= 0) {
      ElMessage.success(`入库成功（${okCount}）`)
      entries.value = []
      emit('uploaded', { allOk: true })
      return
    }

    ElMessage.warning(`成功 ${okCount} 个，失败 ${failed} 个`)
    // 按本次提交的 index 保留失败项，不用文件名匹配（同名会删错）
    const errByIndex = new Map()
    for (const err of summary.errors || []) {
      errByIndex.set(Number(err.index), err)
    }
    const kept = []
    for (let i = 0; i < entries.value.length; i += 1) {
      const err = errByIndex.get(i)
      if (!err) continue
      kept.push({
        ...entries.value[i],
        error: {
          phase: err.phase,
          reason: err.reason,
          message: err.message || '',
        },
      })
    }
    entries.value = kept
    emit('uploaded', { allOk: false })
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

.file-list {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 280px;
  overflow: auto;
}

.file-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--bg-subtle);
}

.file-item:has(.msg) {
  border-color: var(--accent-border);
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

.size,
.phase,
.reason,
.msg {
  font-size: 12px;
  color: var(--muted);
}

.reason {
  color: var(--text-secondary);
  font-weight: 500;
}

.msg {
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
}

.actions {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
</style>
