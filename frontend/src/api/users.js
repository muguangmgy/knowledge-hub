/** 用户管理 API。 */
import http from './http'

/** GET /api/users — 分页；params: page / pageSize / username / status */
export function listUsers(params) {
  return http.get('/api/users', { params })
}

/** GET /api/users/:id */
export function getUser(id) {
  return http.get(`/api/users/${id}`)
}

/** POST /api/users */
export function createUser(body) {
  return http.post('/api/users', body)
}

/** PATCH /api/users/:id — 状态 / 角色 / 重置密码 */
export function updateUser(id, body) {
  return http.patch(`/api/users/${id}`, body)
}

/** DELETE /api/users/:id — 不能删当前登录用户 */
export function deleteUser(id) {
  return http.delete(`/api/users/${id}`)
}
