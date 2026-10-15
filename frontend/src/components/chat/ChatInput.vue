<template>
  <div class="chat-input">
    <div v-if="stageMessage" class="stage-hint">{{ stageMessage }}</div>
    <div class="composer">
      <el-input
        v-model="text"
        type="textarea"
        :autosize="{ minRows: 1, maxRows: 5 }"
        :disabled="asking"
        :placeholder="placeholder"
        resize="none"
        class="composer-textarea"
        @keydown.enter.exact.prevent="onSend"
      />
      <div class="composer-bar">
        <div class="bar-spacer" />
        <button
          v-if="asking"
          type="button"
          class="send-btn is-stop"
          title="停止"
          @click="emit('stop')"
        >
          <span class="stop-icon" />
        </button>
        <button
          v-else
          type="button"
          class="send-btn"
          :class="{ 'is-ready': canSend }"
          :disabled="!canSend"
          title="发送"
          @click="onSend"
        >
          <!-- Material arrow_upward：浅灰圆 + 白箭头，与常见对话产品一致 -->
          <svg class="send-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path
              fill="currentColor"
              d="M4 12l1.41 1.41L11 7.83V20h2V7.83l5.58 5.59L20 12l-8-8-8 8z"
            />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
/** 输入框：矮圆角卡片；Enter 发送；右下角圆形上箭头。 */
import { computed, ref } from 'vue'

const props = defineProps({
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

const canSend = computed(() => Boolean(text.value.trim()) && !props.asking)

/** 发送当前输入并清空。 */
function onSend() {
  const value = text.value.trim()
  if (!value || props.asking) return
  emit('send', value)
  text.value = ''
}
</script>

<style scoped>
.chat-input {
  padding: 10px 24px 16px;
  background: linear-gradient(to top, var(--bg-subtle) 70%, transparent);
}

.stage-hint {
  max-width: 860px;
  margin: 0 auto 6px;
  padding: 0 4px;
  font-size: 12px;
  color: var(--muted);
}

.composer {
  display: flex;
  flex-direction: column;
  max-width: 860px;
  margin: 0 auto;
  padding: 10px 12px 8px;
  background: var(--bg-subtle);
  border: 1px solid var(--border);
  border-radius: 16px;
  box-shadow: var(--shadow-sm);
}

.composer-textarea {
  width: 100%;
}

.composer-textarea :deep(.el-textarea__inner) {
  box-shadow: none !important;
  border: none !important;
  background: transparent;
  padding: 2px 4px 4px;
  min-height: 24px !important;
  font-size: 14px;
  line-height: 1.5;
  color: var(--text);
}

.composer-textarea :deep(.el-textarea__inner::placeholder) {
  color: var(--muted);
}

.composer-bar {
  display: flex;
  align-items: center;
  min-height: 28px;
  padding: 0 2px;
}

.bar-spacer {
  flex: 1;
}

.send-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  margin: 0;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: #d0d3db;
  color: #fff;
  cursor: not-allowed;
  transition: background 0.15s ease;
}

.send-btn.is-ready {
  background: var(--accent);
  cursor: pointer;
}

.send-btn.is-ready:hover {
  background: var(--accent-hover);
}

.send-btn.is-stop {
  background: var(--danger);
  cursor: pointer;
}

.send-btn.is-stop:hover {
  opacity: 0.9;
}

.send-icon {
  width: 18px;
  height: 18px;
  display: block;
}

.stop-icon {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  background: #fff;
}
</style>
