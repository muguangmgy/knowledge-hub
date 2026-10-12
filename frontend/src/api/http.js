/** Axios 封装：Bearer from localStorage；业务 code≠0 或 401 → 清 Token 跳登录。 */
import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'

const TOKEN_KEY = 'kh_token'

/** 读取本地 Token。 */
export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

/** 写入本地 Token。 */
export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

/** 清除本地 Token。 */
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '',
  timeout: 30000,
})

http.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (resp) => {
    const body = resp.data
    if (body && typeof body.code === 'number' && body.code !== 0) {
      if (body.code === 40101) {
        clearToken()
        if (router.currentRoute.value.path !== '/login') {
          router.push({ path: '/login', query: { redirect: router.currentRoute.value.fullPath } })
        }
      }
      return Promise.reject(body)
    }
    return body
  },
  (err) => {
    const status = err.response?.status
    const body = err.response?.data
    if (status === 401 || body?.code === 40101) {
      clearToken()
      router.push('/login')
    }
    if (!err.response) {
      ElMessage.error('网络错误或请求超时')
    }
    return Promise.reject(body || err)
  },
)

export default http
