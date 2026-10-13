/** 问答与会话 API；问答 timeout 120s。 */
import http from './http'

/** POST /api/chat */
export function askChat(payload) {
  return http.post('/api/chat', payload, { timeout: 120000 })
}

/** GET /api/conversations */
export function listConversations() {
  return http.get('/api/conversations')
}

/** GET /api/conversations/:id */
export function getConversation(id) {
  return http.get(`/api/conversations/${id}`)
}

/** PATCH /api/conversations/:id — 更新标题 */
export function updateConversation(id, payload) {
  return http.patch(`/api/conversations/${id}`, payload)
}

/** DELETE /api/conversations/:id */
export function deleteConversation(id) {
  return http.delete(`/api/conversations/${id}`)
}
