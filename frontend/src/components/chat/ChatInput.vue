<template>
  <div class="chat-input">
    <div v-if="stageMessage" class="stage-hint">{{ stageMessage }}</div>
    <div class="composer">
      <el-input
        v-model="text"
        type="textarea"
        :rows="2"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="asking"
        :placeholder="placeholder"
        resize="none"
        @keydown.enter.exact.prevent="onSend"
      />
      <el-button
        v-if="asking"
        type="danger"
        plain
        @click="emit('stop')"
      >
        停止
      </el-button>
      <el-button
        v-else
        type="primary"
        :disabled="!text.trim()"
        @click="onSend"
      >
        发送
      </el-button>
    </div>
  </div>
</template>

<script setup>
/** 输入框：Enter 发送；asking 时展示停止与 stage 文案。 */
import { ref } from 'vue'

defineProps({
  asking: {
    type: Boolean,
    default: false,
  },
  stageMessage: {
    type: String,
    default: '',
  },
  placeholder: {
    type: String,
    default: '输入问题，Enter 发送，Shift+Enter 换行',
  },
})

const emit = defineEmits(['send', 'stop'])
const text = ref('')

/** 发送当前输入并清空。 */
function onSend() {
  const value = text.value.trim()
  if (!value) return
  emit('send', value)
  text.value = ''
}
</script>

<style scoped>
.chat-input {
  padding: 12px 24px 20px;
  background: linear-gradient(to top, var(--bg-subtle) 70%, transparent);
}

.stage-hint {
  max-width: 860px;
  margin: 0 auto 8px;
  padding: 0 4px;
  font-size: 12px;
  color: var(--muted);
}

.composer {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 12px;
  align-items: end;
  max-width: 860px;
  margin: 0 auto;
  padding: 12px 12px 12px 14px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow);
}

:deep(.el-textarea__inner) {
  box-shadow: none !important;
  border: none !important;
  background: transparent;
  padding: 6px 4px;
  font-size: 14px;
  line-height: 1.55;
}
</style>
