<template>
  <div class="app-shell">
    <header v-if="showNav" class="topbar">
      <div class="brand">
        <img class="brand-mark" src="/logo.svg" width="22" height="22" alt="" />
        <span class="brand-text">Knowledge Hub</span>
      </div>
      <nav class="nav">
        <RouterLink to="/chat">对话</RouterLink>
        <RouterLink to="/documents">文档</RouterLink>
      </nav>
      <el-dropdown
        trigger="hover"
        placement="bottom-end"
        :show-timeout="100"
        :hide-timeout="150"
        @command="onUserCommand"
      >
        <span class="user-dropdown el-dropdown-link">
          <span class="username">{{ userStore.profile?.username || '...' }}</span>
          <el-icon class="user-caret"><ArrowDown /></el-icon>
        </span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="logout">退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </header>
    <main :class="showNav ? 'main-with-nav' : 'main-full'">
      <RouterView />
    </main>
  </div>
</template>

<script setup>
/** 根布局：已登录显示顶栏；拉取 /me，失败则清 Token。 */
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown } from '@element-plus/icons-vue'
import { useUserStore } from './stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const showNav = computed(() => !route.meta.public)

/** 已登录时补拉 /me；失败则登出。 */
async function ensureProfile() {
  if (userStore.isLogin && !userStore.profile) {
    try {
      await userStore.loadMe()
    } catch {
      userStore.logout()
      router.push('/login')
    }
  }
}

/** 退出并跳转登录页。 */
function onLogout() {
  userStore.logout()
  router.push('/login')
}

/** 用户菜单命令。 */
function onUserCommand(cmd) {
  if (cmd === 'logout') onLogout()
}

onMounted(ensureProfile)
watch(() => route.fullPath, ensureProfile)
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 40;
  display: flex;
  align-items: center;
  gap: 28px;
  height: var(--topbar-h);
  padding: 0 24px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.brand-mark {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  display: block;
}

.brand-text {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.01em;
  color: var(--text);
}

.nav {
  display: flex;
  gap: 4px;
  flex: 1;
}

.nav a {
  padding: 7px 14px;
  border-radius: var(--radius-sm);
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
  transition: background 0.15s ease, color 0.15s ease;
}

.nav a:hover {
  color: var(--text);
  background: var(--bg-subtle);
}

.nav a.router-link-active {
  color: var(--accent);
  background: var(--accent-soft);
  font-weight: 600;
}

.user-dropdown {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 180px;
  padding: 5px 10px 5px 12px;
  border-radius: 999px;
  background: var(--bg-subtle);
  border: 1px solid var(--border);
  color: var(--text);
  font-size: 13px;
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.user-dropdown:hover {
  border-color: var(--accent-border);
  background: var(--accent-soft);
}

.username {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-caret {
  font-size: 12px;
  color: var(--muted);
}

.main-with-nav {
  min-height: calc(100vh - var(--topbar-h));
}

.main-full {
  min-height: 100vh;
}
</style>
