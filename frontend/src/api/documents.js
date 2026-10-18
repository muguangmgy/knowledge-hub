/** 文档 API：列表 / 删除 / 上传 / 批量 / 重新解析（入库 timeout 10min）。 */
import http from './http'

/** GET /api/documents */
export function listDocuments() {
  return http.get('/api/documents')
}

/** DELETE /api/documents/:id */
export function deleteDocument(id) {
  return http.delete(`/api/documents/${id}`)
}

/** POST /api/documents（multipart） */
export function uploadDocument(file, onUploadProgress) {
  const form = new FormData()
  form.append('file', file)
  return http.post('/api/documents', form, {
    timeout: 600000,
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress,
  })
}

/** POST /api/documents/batch：按列表顺序 append files，后端用该顺序编 index。 */
export function uploadDocumentsBatch(files) {
  const form = new FormData()
  for (const file of files) {
    form.append('files', file)
  }
  return http.post('/api/documents/batch', form, {
    timeout: 600000,
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** POST /api/documents/batch-delete：勾选 id，部分成功不回滚。 */
export function deleteDocumentsBatch(ids) {
  return http.post('/api/documents/batch-delete', { ids })
}

/** POST /api/documents/:id/reingest — 用服务器原文件按最新规则重建索引 */
export function reingestDocument(id) {
  return http.post(`/api/documents/${id}/reingest`, null, {
    timeout: 600000,
  })
}

/** POST /api/documents/reingest-all — 批量重新解析 */
export function reingestAllDocuments() {
  return http.post('/api/documents/reingest-all', null, {
    timeout: 600000,
  })
}
