<template>
  <ChatWorkspace
    :store="directChatStore"
    empty-title="自由对话"
    empty-hint="不检索知识库，支持多轮闲聊与常识问答。"
  />
</template>

<script setup>
/** 自由对话页（mode=direct）；不引入 CitationList / 拒答 UI。 */
import ChatWorkspace from '../../components/chat/ChatWorkspace.vue'
import { useDirectChatStore } from '../../stores/directChat'

const directChatStore = useDirectChatStore()
</script>
