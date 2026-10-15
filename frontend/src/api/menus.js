/** 菜单管理 API（树 CRUD）。 */
import http from './http'

/** GET /api/menus/tree — 全量菜单树（管理端） */
export function fetchMenuTree() {
  return http.get('/api/menus/tree')
}

/** POST /api/menus */
export function createMenu(body) {
  return http.post('/api/menus', body)
}

/** PATCH /api/menus/:id */
export function updateMenu(id, body) {
  return http.patch(`/api/menus/${id}`, body)
}

/** DELETE /api/menus/:id — 内置系统管理节点不可删 */
export function deleteMenu(id) {
  return http.delete(`/api/menus/${id}`)
}
