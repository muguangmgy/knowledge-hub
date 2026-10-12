/** 文档 API：列表 / 删除 / 上传（入库 timeout 10min）。 */
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
