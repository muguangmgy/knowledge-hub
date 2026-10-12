/** 路由：公开页 login/register；其余需 Token，否则跳登录。 */
import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '../api/http'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/auth/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('../views/auth/RegisterView.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    redirect: '/chat',
  },
  {
    path: '/documents',
    name: 'documents',
    component: () => import('../views/documents/DocumentListView.vue'),
  },
  {
    path: '/chat',
    name: 'chat',
    component: () => import('../views/chat/ChatView.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

/** 非公开页无 Token 时跳转登录并带回跳地址。 */
router.beforeEach((to) => {
  if (to.meta.public) return true
  if (!getToken()) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
