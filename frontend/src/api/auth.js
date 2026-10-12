/** 认证 API：登录 / 注册 / 当前用户。 */
import http from './http'

/** POST /api/auth/login */
export function login(payload) {
  return http.post('/api/auth/login', payload)
}

/** POST /api/auth/register */
export function register(payload) {
  return http.post('/api/auth/register', payload)
}

/** GET /api/auth/me */
export function fetchMe() {
  return http.get('/api/auth/me')
}
