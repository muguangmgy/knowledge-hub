<template>
  <ChatWorkspace
    :store="chatStore"
    empty-title="开始提问"
    empty-hint="答案将附带知识库引用；依据不足时会拒答说明。每轮独立检索，不以上文指代续问。"
  >
    <template #assistant-extra="{ message }">
      <template v-if="message.role === 'assistant'">
        <div v-if="message.rejected" class="rejected">已拒答（依据不足）</div>
        <CitationList :items="message.citations || []" />
      </template>
    </template>
  </ChatWorkspace>
</template>

<script setup>
/** 知识库问答页（mode=rag）。 */
import ChatWorkspace from '../../components/chat/ChatWorkspace.vue'
import CitationList from '../../components/chat/CitationList.vue'
import { useChatStore } from '../../stores/chat'

const chatStore = useChatStore()
</script>

<style scoped>
.rejected {
  margin-top: 10px;
  display: inline-block;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 500;
  color: var(--warning);
  background: var(--warning-soft);
  border: 1px solid #fed7aa;
}
</style>
