<template>
  <div class="chat-page fade-up">
    <aside class="sidebar">
      <div class="side-head">
        <strong>会话</strong>
        <el-button type="primary" plain size="small" @click="onNew">新对话</el-button>
      </div>
      <div class="conv-list">
        <button
          v-for="c in chatStore.conversations"
          :key="c.id"
          type="button"
          class="conv"
          :class="{ active: c.id === chatStore.conversationId }"
          @click="onOpen(c.id)"
        >
          <div class="title">{{ c.title || `会话 #${c.id}` }}</div>
          <div class="time">{{ c.updatedAt || c.createdAt }}</div>
        </button>
        <div v-if="!chatStore.conversations.length" class="empty">暂无历史会话</div>
      </div>
    </aside>
    <section class="main">
      <MessageList :messages="chatStore.messages" />
      <ChatInput :disabled="chatStore.asking" @send="onSend" />
    </section>
  </div>
</template>

<script setup>
/** 对话页：左侧会话列表，右侧消息与输入；新对话只清本地。 */
import { onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import MessageList from '../../components/chat/MessageList.vue'
import ChatInput from '../../components/chat/ChatInput.vue'
import { useChatStore } from '../../stores/chat'

const chatStore = useChatStore()

/** 加载会话列表。 */
async function refreshList() {
  try {
    await chatStore.refreshConversations()
  } catch (err) {
    ElMessage.error(err?.message || '加载会话失败')
  }
}

/** 开始新对话（仅清本地）。 */
function onNew() {
  chatStore.newChat()
}

/** 打开历史会话。 */
async function onOpen(id) {
  try {
    await chatStore.openConversation(id)
  } catch (err) {
    ElMessage.error(err?.message || '打开会话失败')
  }
}

/** 发送问题。 */
async function onSend(text) {
  try {
    await chatStore.ask(text)
  } catch (err) {
    ElMessage.error(err?.message || '问答失败')
  }
}

onMounted(refreshList)
</script>

<style scoped>
.chat-page {
  display: grid;
  grid-template-columns: 268px 1fr;
  gap: 0;
  height: calc(100vh - var(--topbar-h));
  background: var(--bg);
}

.sidebar {
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border-right: 1px solid var(--border);
  overflow: hidden;
}

.main {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
  background: var(--bg-subtle);
}

.side-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
}

.side-head strong {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--text-secondary);
  text-transform: none;
}

.conv-list {
  flex: 1;
  overflow: auto;
  padding: 8px;
}

.conv {
  display: block;
  width: 100%;
  text-align: left;
  padding: 10px 12px;
  margin-bottom: 2px;
  border: 1px solid transparent;
  border-radius: var(--radius);
  background: transparent;
  cursor: pointer;
  font: inherit;
  color: inherit;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.conv:hover {
  background: var(--bg-subtle);
}

.conv.active {
  background: var(--accent-soft);
  border-color: var(--accent-border);
}

.conv .title {
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text);
}

.conv .time {
  font-size: 11px;
  color: var(--muted);
  margin-top: 4px;
}

.empty {
  padding: 20px 12px;
  color: var(--muted);
  font-size: 13px;
  text-align: center;
}

@media (max-width: 860px) {
  .chat-page {
    grid-template-columns: 1fr;
    height: auto;
    min-height: calc(100vh - var(--topbar-h));
  }

  .sidebar {
    max-height: 220px;
    border-right: none;
    border-bottom: 1px solid var(--border);
  }

  .main {
    min-height: 60vh;
  }
}
</style>
