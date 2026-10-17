/** 路由：公开页 login/register；其余需 Token，业务+系统管理挂 AppLayout。 */
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
    component: () => import('../layouts/AppLayout.vue'),
    children: [
      { path: '', redirect: '/chat/rag' },
      {
        path: 'chat',
        redirect: '/chat/rag',
      },
      {
        path: 'chat/rag',
        name: 'chat-rag',
        component: () => import('../views/chat/ChatView.vue'),
      },
      {
        path: 'chat/direct',
        name: 'chat-direct',
        component: () => import('../views/chat/DirectChatView.vue'),
      },
      {
        path: 'documents',
        name: 'documents',
        component: () => import('../views/documents/DocumentListView.vue'),
      },
      {
        path: 'system/users',
        name: 'system-users',
        component: () => import('../views/system/UserManageView.vue'),
      },
      {
        path: 'system/roles',
        name: 'system-roles',
        component: () => import('../views/system/RoleManageView.vue'),
      },
      {
        path: 'system/menus',
        name: 'system-menus',
        component: () => import('../views/system/MenuManageView.vue'),
      },
      {
        path: 'system/dev',
        name: 'system-dev',
        component: () => import('../views/system/DevDebugView.vue'),
      },
    ],
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
