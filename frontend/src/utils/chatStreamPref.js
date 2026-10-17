/**
 * 对话是否走 SSE：localStorage 覆盖 > VITE_CHAT_STREAM 默认。
 * 键缺省时默认开流式（与线上主路径一致）；仅当 env 显式为 'false' 时默认关。
 */
const STORAGE_KEY = 'kh_chat_stream'

/** 构建时默认：VITE_CHAT_STREAM !== 'false' 则为开。 */
export function getEnvChatStreamDefault() {
  return import.meta.env.VITE_CHAT_STREAM !== 'false'
}

/** 当前是否启用流式（含本地覆盖）。 */
export function isChatStreamEnabled() {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (raw === '1') return true
  if (raw === '0') return false
  return getEnvChatStreamDefault()
}

/** 写入本地覆盖（仅影响本浏览器）。 */
export function setChatStreamEnabled(enabled) {
  localStorage.setItem(STORAGE_KEY, enabled ? '1' : '0')
}

/** 是否已有本地覆盖（相对 env 默认）。 */
export function hasChatStreamOverride() {
  const raw = localStorage.getItem(STORAGE_KEY)
  return raw === '1' || raw === '0'
}

/** 清除本地覆盖，回退到 env 默认。 */
export function clearChatStreamOverride() {
  localStorage.removeItem(STORAGE_KEY)
}
