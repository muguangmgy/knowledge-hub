<template>
  <div class="app-layout" :class="{ 'is-collapsed': collapsed }">
    <aside class="sider">
      <div class="sider-brand">
        <img class="brand-mark" src="/logo.svg" width="22" height="22" alt="" />
        <span v-show="!collapsed" class="brand-text">Knowledge Hub</span>
      </div>
      <el-menu
        :default-active="activePath"
        :default-openeds="openedCatalogs"
        :collapse="collapsed"
        :collapse-transition="false"
        class="sider-menu"
        router
      >
        <template v-for="node in menuTree" :key="node.id">
          <el-sub-menu
            v-if="node.type === 'catalog'"
            :index="`c-${node.id}`"
            popper-class="sider-menu-popup"
          >
            <template #title>
              <el-icon><component :is="menuIcon(node)" /></el-icon>
              <span>{{ node.name }}</span>
            </template>
            <el-menu-item
              v-for="child in node.children || []"
              :key="child.id"
              :index="child.path || `m-${child.id}`"
            >
              <el-icon><component :is="menuIcon(child)" /></el-icon>
              <template #title>{{ child.name }}</template>
            </el-menu-item>
          </el-sub-menu>
          <el-menu-item
            v-else-if="node.type === 'menu' && node.path"
            :index="node.path"
          >
            <el-icon><component :is="menuIcon(node)" /></el-icon>
            <template #title>{{ node.name }}</template>
          </el-menu-item>
        </template>
      </el-menu>
    </aside>
    <div class="main-col">
      <header class="topbar">
        <el-button
          class="collapse-btn"
          text
          :title="collapsed ? '展开菜单' : '收起菜单'"
          @click="toggleCollapse"
        >
          <el-icon :size="20">
            <Expand v-if="collapsed" />
            <Fold v-else />
          </el-icon>
        </el-button>
        <div class="topbar-spacer" />
        <el-dropdown
          trigger="hover"
          placement="bottom-end"
          :show-timeout="100"
          :hide-timeout="150"
          popper-class="user-dropdown-popper"
          @command="onUserCommand"
        >
          <button type="button" class="user-chip">
            <span class="user-avatar" aria-hidden="true">{{ userInitial }}</span>
            <span class="username">{{ displayName }}</span>
            <el-icon class="user-caret"><ArrowDown /></el-icon>
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </header>
      <main class="content">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<script setup>
/** 已登录壳：左侧按 /me.menus 渲染；顶栏可折叠侧栏。 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowDown,
  ChatDotRound,
  Document,
  Expand,
  Fold,
  Menu as MenuIcon,
  Setting,
  TrendCharts,
  User,
  UserFilled,
} from '@element-plus/icons-vue'
import { resolveIcon } from '../utils/icons'
import { useUserStore } from '../stores/user'

/** localStorage：侧栏是否折叠 */
const COLLAPSE_KEY = 'kh_sidebar_collapsed'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const collapsed = ref(localStorage.getItem(COLLAPSE_KEY) === '1')

const displayName = computed(() => userStore.profile?.username || '...')
const userInitial = computed(() => {
  const name = String(userStore.profile?.username || '').trim()
  if (!name) return '?'
  return name.slice(0, 1).toUpperCase()
})

/** 侧栏数据来自 GET /me 的 menus 树 */
const menuTree = computed(() => userStore.profile?.menus || [])

const activePath = computed(() => route.path)

/** 展开所有 catalog；折叠时清空，避免 el-menu 状态错乱 */
const openedCatalogs = computed(() =>
  collapsed.value
    ? []
    : (menuTree.value || [])
        .filter((n) => n.type === 'catalog')
        .map((n) => `c-${n.id}`),
)

watch(collapsed, (v) => {
  localStorage.setItem(COLLAPSE_KEY, v ? '1' : '0')
})

function toggleCollapse() {
  collapsed.value = !collapsed.value
}

/** 优先用菜单配置的 Element Plus 图标名；否则按 path / perms 回退。 */
function menuIcon(node) {
  const fromDb = resolveIcon(node?.icon)
  if (fromDb) return fromDb
  const path = node?.path || ''
  const perms = node?.perms || ''
  if (path === '/system/users' || perms.includes('user')) return User
  if (path === '/system/roles' || perms.includes('role')) return UserFilled
  if (path === '/system/menus' || perms.includes('menu')) return MenuIcon
  if (path === '/chat/rag') return ChatDotRound
  if (path === '/chat/direct') return TrendCharts
  if (path === '/documents') return Document
  if (perms.includes('catalog') || node?.type === 'catalog') return Setting
  return MenuIcon
}

function onLogout() {
  userStore.logout()
  router.push('/login')
}

function onUserCommand(cmd) {
  if (cmd === 'logout') onLogout()
}
</script>

<style scoped>
.app-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--bg);
}

.sider {
  width: var(--sidebar-w);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border-right: 1px solid var(--border);
  transition: width 0.2s ease;
  overflow: hidden;
}

.app-layout.is-collapsed .sider {
  width: var(--sidebar-collapsed-w);
}

.sider-brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  height: var(--topbar-h);
  padding: 0 12px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.app-layout:not(.is-collapsed) .sider-brand {
  justify-content: flex-start;
  padding: 0 16px;
}

.brand-mark {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  display: block;
  flex-shrink: 0;
}

.brand-text {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
}

.sider-menu {
  border-right: none;
  flex: 1;
  overflow: auto;
  background: transparent;
  padding: 8px 0;
  width: 100%;
}

.sider-menu:not(.el-menu--collapse) :deep(.el-menu-item),
.sider-menu:not(.el-menu--collapse) :deep(.el-sub-menu__title) {
  height: 42px;
  line-height: 42px;
  margin: 0 8px;
  border-radius: var(--radius-sm);
}

.sider-menu :deep(.el-menu-item.is-active) {
  background: var(--accent-soft) !important;
  color: var(--accent);
  font-weight: 600;
}

.main-col {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.topbar {
  height: var(--topbar-h);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 16px 0 12px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}

.collapse-btn {
  color: var(--text-secondary);
  padding: 8px;
}

.collapse-btn:hover {
  color: var(--accent);
  background: var(--accent-soft);
}

.topbar-spacer {
  flex: 1;
}

.user-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 200px;
  margin: 0;
  padding: 4px 10px 4px 4px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  outline: none;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.user-chip:hover,
.user-chip:focus-visible {
  background: var(--accent-soft);
  border-color: var(--accent-border);
}

.user-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
  flex-shrink: 0;
}

.username {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-caret {
  font-size: 12px;
  color: var(--muted);
  transition: transform 0.15s ease;
}

.user-chip:hover .user-caret {
  color: var(--accent);
}

.content {
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: auto;
  background: var(--bg);
}

.content > :deep(*) {
  flex: 1 1 auto;
  min-height: 0;
  width: 100%;
}
</style>
