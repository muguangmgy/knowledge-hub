/** 用户状态：Token、资料、登录/注册/登出。 */
import { defineStore } from 'pinia'
import { clearToken, getToken, setToken } from '../api/http'
import * as authApi from '../api/auth'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: getToken(),
    profile: null,
  }),
  getters: {
    /** 是否已持有 Token。 */
    isLogin: (s) => Boolean(s.token),
  },
  actions: {
    /** 登录并拉取 /me。 */
    async login(form) {
      const res = await authApi.login(form)
      this.token = res.data.accessToken
      setToken(this.token)
      await this.loadMe()
    },
    /** 注册（不自动登录）。 */
    async register(form) {
      await authApi.register(form)
    },
    /** 拉取当前用户资料（含 roles + menus 树，供侧栏）。 */
    async loadMe() {
      if (!this.token) {
        this.profile = null
        return
      }
      const res = await authApi.fetchMe()
      this.profile = res.data
    },
    /** 登出：仅清本地 Token 与资料。 */
    logout() {
      this.token = ''
      this.profile = null
      clearToken()
    },
  },
})
