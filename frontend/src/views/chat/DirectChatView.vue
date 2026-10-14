<template>
  <ChatWorkspace
    :store="directChatStore"
    empty-title="投研助手"
    empty-hint="例：分析贵州茅台近日行情发到我邮箱"
    input-placeholder="分析贵州茅台近日行情发到我邮箱"
  />
</template>

<script setup>
/**
 * 投研助手页（mode=direct → Multi-Agent）。
 * 不挂 CitationList / 拒答条；示例话术可带邮箱以触发发信。
 */
import ChatWorkspace from '../../components/chat/ChatWorkspace.vue'
import { useDirectChatStore } from '../../stores/directChat'

const directChatStore = useDirectChatStore()
</script>
