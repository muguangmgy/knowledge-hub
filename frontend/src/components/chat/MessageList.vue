<template>
  <div class="messages" ref="root">
    <div v-if="!messages.length" class="empty">
      <div class="empty-title">{{ emptyTitle }}</div>
      <p>{{ emptyHint }}</p>
    </div>
    <div
      v-for="(m, idx) in messages"
      :key="m.id || idx"
      class="bubble"
      :class="m.role"
    >
      <div class="role">{{ m.role === 'user' ? '你' : '助手' }}</div>
      <div
        v-if="m.role === 'assistant'"
        class="content md-body"
        v-html="renderMarkdown(m.content)"
      />
      <div v-else class="content plain">{{ m.content }}</div>
      <slot name="assistant-extra" :message="m" />
    </div>
  </div>
</template>

<script setup>
/**
 * 通用消息列表（无 store / 无 CitationList）；空态与助手附加区由父级传入。
 * 助手消息走 Markdown 安全渲染（投研报告表格/标题）；用户消息保持纯文本。
 */
import { nextTick, ref, watch } from 'vue'
import { renderMarkdown } from '../../utils/markdown.js'

const props = defineProps({
  messages: {
    type: Array,
    default: () => [],
  },
  emptyTitle: {
    type: String,
    default: '开始提问',
  },
  emptyHint: {
    type: String,
    default: '',
  },
})

const root = ref(null)

watch(
  () => [
    props.messages.length,
    props.messages.map((m) => (m.content || '').length).join(','),
  ],
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
  max-width: min(780px, 92%);
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
  line-height: 1.65;
  font-size: 14px;
}

.content.plain {
  white-space: pre-wrap;
}

/* Markdown 正文（助手） */
.md-body :deep(> :first-child) {
  margin-top: 0;
}

.md-body :deep(> :last-child) {
  margin-bottom: 0;
}

.md-body :deep(h1),
.md-body :deep(h2),
.md-body :deep(h3),
.md-body :deep(h4) {
  margin: 1em 0 0.45em;
  line-height: 1.35;
  color: var(--text);
  font-weight: 650;
}

.md-body :deep(h1) {
  font-size: 1.35em;
}

.md-body :deep(h2) {
  font-size: 1.18em;
}

.md-body :deep(h3) {
  font-size: 1.05em;
}

.md-body :deep(p) {
  margin: 0.55em 0;
}

.md-body :deep(ul),
.md-body :deep(ol) {
  margin: 0.45em 0;
  padding-left: 1.35em;
}

.md-body :deep(li) {
  margin: 0.2em 0;
}

.md-body :deep(strong) {
  font-weight: 650;
  color: var(--text);
}

.md-body :deep(a) {
  color: var(--accent);
  text-decoration: none;
}

.md-body :deep(a:hover) {
  text-decoration: underline;
}

.md-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--border);
  margin: 1em 0;
}

.md-body :deep(blockquote) {
  margin: 0.6em 0;
  padding: 0.35em 0 0.35em 0.85em;
  border-left: 3px solid var(--accent-border);
  color: var(--text-secondary);
}

.md-body :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.9em;
  padding: 0.1em 0.35em;
  border-radius: 4px;
  background: var(--bg-subtle);
  border: 1px solid var(--border);
}

.md-body :deep(pre) {
  margin: 0.65em 0;
  padding: 10px 12px;
  overflow-x: auto;
  border-radius: var(--radius-sm);
  background: var(--bg-subtle);
  border: 1px solid var(--border);
}

.md-body :deep(pre code) {
  padding: 0;
  border: none;
  background: transparent;
}

.md-body :deep(.table-wrap),
.md-body :deep(table) {
  display: block;
  width: 100%;
  overflow-x: auto;
  margin: 0.75em 0;
  border-collapse: collapse;
  font-size: 13px;
}

.md-body :deep(table) {
  display: table;
  min-width: 100%;
}

.md-body :deep(thead th) {
  background: var(--bg-subtle);
  font-weight: 600;
  color: var(--text-secondary);
}

.md-body :deep(th),
.md-body :deep(td) {
  border: 1px solid var(--border);
  padding: 8px 10px;
  vertical-align: middle;
  text-align: center;
}

.md-body :deep(th[align='left']),
.md-body :deep(td[align='left']) {
  text-align: left;
}

.md-body :deep(th[align='right']),
.md-body :deep(td[align='right']) {
  text-align: right;
}

.md-body :deep(tbody tr:nth-child(even)) {
  background: rgb(247 248 250 / 55%);
}
</style>
