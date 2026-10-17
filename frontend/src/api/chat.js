/**
 * 问答与会话 API。
 * UI 默认 askChatStream；开发调试关流式或脚本场景走 askChat。
 */
import http, { clearToken, getToken } from './http'
import router from '../router'

/**
 * POST /api/chat（同步整包）
 * @param {{ message: string, conversationId?: number|null, mode?: 'rag'|'direct'|null }} payload
 * @param {{ signal?: AbortSignal }} [config]
 */
export function askChat(payload, config = {}) {
  return http.post('/api/chat', payload, { timeout: 120000, ...config })
}

/**
 * POST /api/chat/stream（SSE，UI 问答主路径）。
 * 用 fetch + ReadableStream 解析事件；Bearer 自 getToken。
 * 建流前 HTTP 错误抛 Error（含 code）；流内 error 事件亦抛。
 * AbortSignal 中止时停止读流（对应「停止」按钮）。
 *
 * @param {{ message: string, conversationId?: number|null, mode?: 'rag'|'direct'|null }} payload
 * @param {{
 *   onMeta?: (data: object) => void,
 *   onStage?: (data: object) => void,
 *   onCitations?: (data: object) => void,
 *   onDelta?: (data: object) => void,
 *   onDone?: (data: object) => void,
 *   onError?: (data: object) => void,
 * }} handlers
 * @param {AbortSignal} [signal]
 */
export async function askChatStream(payload, handlers = {}, signal) {
  const base = import.meta.env.VITE_API_BASE || ''
  const res = await fetch(`${base}/api/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify({
      message: payload.message,
      conversationId: payload.conversationId ?? null,
      mode: payload.mode,
    }),
    signal,
  })

  if (!res.ok) {
    let body = null
    try {
      body = await res.json()
    } catch {
      /* ignore */
    }
    _handleAuthError(body)
    const err = new Error(body?.message || `请求失败 (${res.status})`)
    err.code = body?.code
    err.status = res.status
    throw err
  }

  const contentType = res.headers.get('content-type') || ''
  if (!contentType.includes('text/event-stream') || !res.body) {
    const body = await res.json().catch(() => null)
    _handleAuthError(body)
    const err = new Error(body?.message || '响应不是 SSE 流')
    err.code = body?.code
    throw err
  }

  await _readSse(res.body, handlers, signal)
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

/** 业务码 40101 时清 Token 并跳转登录（对齐 http.js 拦截器）。 */
function _handleAuthError(body) {
  if (body?.code === 40101) {
    clearToken()
    if (router.currentRoute.value.path !== '/login') {
      router.push({
        path: '/login',
        query: { redirect: router.currentRoute.value.fullPath },
      })
    }
  }
}

/**
 * 解析 text/event-stream：按空行拆帧，分发 meta/stage/citations/delta/done/error。
 * comment（`: ping`）忽略；signal 中止时 cancel reader。
 *
 * @param {ReadableStream<Uint8Array>} body
 * @param {object} handlers
 * @param {AbortSignal} [signal]
 */
async function _readSse(body, handlers, signal) {
  const reader = body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let eventName = 'message'
  let dataLines = []

  /** 将已缓冲的 event/data 交给对应 handler；error 帧会 throw。 */
  const flush = () => {
    if (!dataLines.length && eventName === 'message') return
    const raw = dataLines.join('\n')
    dataLines = []
    const name = eventName
    eventName = 'message'
    if (!raw) return
    let data = {}
    try {
      data = JSON.parse(raw)
    } catch {
      data = { raw }
    }
    if (name === 'meta') handlers.onMeta?.(data)
    else if (name === 'stage') handlers.onStage?.(data)
    else if (name === 'citations') handlers.onCitations?.(data)
    else if (name === 'delta') handlers.onDelta?.(data)
    else if (name === 'done') handlers.onDone?.(data)
    else if (name === 'error') {
      handlers.onError?.(data)
      const err = new Error(data.message || '问答失败')
      err.code = data.code
      throw err
    }
  }

  try {
    while (true) {
      if (signal?.aborted) {
        try {
          await reader.cancel()
        } catch {
          /* ignore */
        }
        break
      }
      const { done, value } = await reader.read()
      if (done) {
        flush()
        break
      }
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n')
      buffer = parts.pop() ?? ''
      for (const line of parts) {
        if (line === '') {
          flush()
          continue
        }
        if (line.startsWith(':')) {
          // heartbeat comment
          continue
        }
        if (line.startsWith('event:')) {
          eventName = line.slice(6).trim()
          continue
        }
        if (line.startsWith('data:')) {
          dataLines.push(line.slice(5).trimStart())
        }
      }
    }
  } finally {
    try {
      reader.releaseLock()
    } catch {
      /* ignore */
    }
  }
}
