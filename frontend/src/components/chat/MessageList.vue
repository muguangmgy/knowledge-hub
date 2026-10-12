<template>
  <div class="messages" ref="root">
    <div v-if="!messages.length" class="empty">
      <div class="empty-title">开始提问</div>
      <p>答案将附带知识库引用；依据不足时会拒答说明。</p>
    </div>
    <div
      v-for="(m, idx) in messages"
      :key="m.id || idx"
      class="bubble"
      :class="m.role"
    >
      <div class="role">{{ m.role === 'user' ? '你' : '助手' }}</div>
      <div class="content">{{ m.content }}</div>
      <div v-if="m.rejected" class="rejected">已拒答（依据不足）</div>
      <CitationList v-if="m.role === 'assistant'" :items="m.citations || []" />
    </div>
  </div>
</template>

<script setup>
/** 消息列表；助手消息可展示拒答标识与 citations。 */
import { nextTick, ref, watch } from 'vue'
import CitationList from './CitationList.vue'

const props = defineProps({
  messages: {
    type: Array,
    default: () => [],
  },
})

const root = ref(null)

watch(
  () => props.messages.length,
  async () => {
    await nextTick()
    if (root.value) {
      root.value.scrollTop = root.value.scrollHeight
    }
  },
)
</script>

<style scoped>
.messages {
  flex: 1;
  overflow: auto;
  padding: 24px 28px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.empty {
  margin: auto;
  text-align: center;
  max-width: 320px;
  color: var(--muted);
}

.empty-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.empty p {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
}

.bubble {
  max-width: min(720px, 88%);
  padding: 12px 14px 14px;
  border-radius: var(--radius-lg);
  animation: fade-up 0.22s ease-out;
}

.bubble.user {
  align-self: flex-end;
  background: var(--accent);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.bubble.user .role {
  color: rgb(255 255 255 / 72%);
}

.bubble.assistant {
  align-self: flex-start;
  background: var(--surface);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  border-bottom-left-radius: 4px;
}

.role {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--muted);
  margin-bottom: 6px;
  text-transform: uppercase;
}

.content {
  white-space: pre-wrap;
  line-height: 1.65;
  font-size: 14px;
}

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
