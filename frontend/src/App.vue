<template>
  <RouterView />
</template>

<script setup>
/** 根组件：路由承载；已登录壳在 AppLayout，公开页无侧栏。 */
import { onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from './stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

/** 已登录时补拉 /me；失败则登出。 */
async function ensureProfile() {
  if (route.meta.public) return
  if (userStore.isLogin && !userStore.profile) {
    try {
      await userStore.loadMe()
    } catch {
      userStore.logout()
      router.push('/login')
    }
  }
}

onMounted(ensureProfile)
watch(() => route.fullPath, ensureProfile)
</script>
