/** 角色管理 API（含勾选菜单）。 */
import http from './http'

/** GET /api/roles */
export function listRoles() {
  return http.get('/api/roles')
}

/** GET /api/roles/:id */
export function getRole(id) {
  return http.get(`/api/roles/${id}`)
}

/** POST /api/roles */
export function createRole(body) {
  return http.post('/api/roles', body)
}

/** PATCH /api/roles/:id — 可改名称与 menuIds */
export function updateRole(id, body) {
  return http.patch(`/api/roles/${id}`, body)
}

/** DELETE /api/roles/:id — 内置 admin/user 不可删 */
export function deleteRole(id) {
  return http.delete(`/api/roles/${id}`)
}
