/** 问答与会话 API；问答 timeout 120s。 */
import http from './http'

/**
 * POST /api/chat
 * @param {{ message: string, conversationId?: number|null, mode?: 'rag'|'direct'|null }} payload
 */
export function askChat(payload) {
  return http.post('/api/chat', payload, { timeout: 120000 })
}

/**
 * GET /api/conversations；显式传 mode（rag|direct），与后端列表过滤对齐
 * @param {'rag'|'direct'} mode
 */
export function listConversations(mode) {
  return http.get('/api/conversations', { params: { mode } })
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
