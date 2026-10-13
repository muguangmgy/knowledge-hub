<template>
  <div class="chat-page fade-up">
    <aside class="sidebar">
      <div class="side-head">
        <strong>会话</strong>
        <el-button type="primary" plain size="small" @click="onNew">新对话</el-button>
      </div>
      <div class="conv-list">
        <div
          v-for="c in chatStore.conversations"
          :key="c.id"
          class="conv"
          :class="{
            active: c.id === chatStore.conversationId,
            'menu-open': openMenuId === c.id,
          }"
          @click="onOpen(c.id)"
        >
          <div class="conv-body">
            <div class="title">{{ c.title || `会话 #${c.id}` }}</div>
            <div class="time">{{ c.updatedAt || c.createdAt }}</div>
          </div>
          <el-dropdown
            trigger="click"
            placement="bottom-start"
            :teleported="true"
            :popper-options="convMenuPopperOptions"
            popper-class="conv-menu-popper"
            @command="(cmd) => onConvCommand(cmd, c)"
            @visible-change="(v) => onMenuVisible(v, c.id)"
          >
            <button
              type="button"
              class="more-btn"
              title="更多"
              @click.stop
            >
              <el-icon :size="14"><MoreFilled /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="rename">
                  <el-icon><EditPen /></el-icon>
                  <span>重命名</span>
                </el-dropdown-item>
                <el-dropdown-item command="delete" class="conv-menu-danger">
                  <el-icon><Delete /></el-icon>
                  <span>删除</span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
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
/** 对话页：左侧会话列表（··· 菜单改名/删除），右侧消息与输入；新对话只清本地。 */
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, EditPen, MoreFilled } from '@element-plus/icons-vue'
import MessageList from '../../components/chat/MessageList.vue'
import ChatInput from '../../components/chat/ChatInput.vue'
import { useChatStore } from '../../stores/chat'

const chatStore = useChatStore()
const openMenuId = ref(null)
/** 菜单贴在 ··· 右下角，尽量不翻到左侧。 */
const convMenuPopperOptions = {
  modifiers: [
    { name: 'offset', options: { offset: [0, 6] } },
    {
      name: 'flip',
      options: { fallbackPlacements: ['top-end', 'bottom-start'] },
    },
  ],
}

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

/** 记录当前展开的 ··· 菜单，便于保持按钮可见。 */
function onMenuVisible(visible, id) {
  openMenuId.value = visible ? id : null
}

/** 会话 ··· 菜单命令。 */
function onConvCommand(cmd, c) {
  if (cmd === 'rename') onRename(c)
  else if (cmd === 'delete') onDelete(c)
}

/** 重命名会话标题。 */
async function onRename(c) {
  try {
    const { value } = await ElMessageBox.prompt('请输入新标题', '重命名会话', {
      inputValue: c.title || '',
      inputPlaceholder: '会话标题',
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValidator: (v) => {
        if (!v || !String(v).trim()) return '标题不能为空'
        if (String(v).trim().length > 512) return '标题过长'
        return true
      },
    })
    await chatStore.renameConversation(c.id, String(value).trim())
    ElMessage.success('已更新标题')
  } catch (err) {
    if (err === 'cancel' || err === 'close') return
    ElMessage.error(err?.message || '重命名失败')
  }
}

/** 确认后删除会话。 */
async function onDelete(c) {
  const label = c.title || `会话 #${c.id}`
  try {
    await ElMessageBox.confirm(`确认删除「${label}」？消息将一并删除。`, '删除会话', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    await chatStore.removeConversation(c.id)
    ElMessage.success('已删除')
  } catch (err) {
    if (err === 'cancel' || err === 'close') return
    ElMessage.error(err?.message || '删除失败')
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
  display: flex;
  align-items: center;
  gap: 2px;
  margin-bottom: 2px;
  padding: 8px 6px 8px 12px;
  border: 1px solid transparent;
  border-radius: var(--radius);
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.conv:hover {
  background: var(--bg-subtle);
}

.conv.active {
  background: var(--accent-soft);
  border-color: var(--accent-border);
}

.conv-body {
  flex: 1;
  min-width: 0;
}

.conv .title {
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text);
  line-height: 1.35;
}

.conv .time {
  font-size: 11px;
  color: var(--muted);
  margin-top: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.more-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  margin: 0;
  padding: 0;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s ease, background 0.15s ease, color 0.15s ease;
}

.conv:hover .more-btn,
.conv.active .more-btn,
.conv.menu-open .more-btn {
  opacity: 1;
  pointer-events: auto;
}

.more-btn:hover {
  background: var(--border);
  color: var(--text);
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

  .more-btn {
    opacity: 1;
    pointer-events: auto;
  }
}
</style>

<!-- 下拉挂到 body，需非 scoped -->
<style>
.conv-menu-popper.el-popper {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
}

.conv-menu-popper .el-popper__arrow {
  display: none;
}

.conv-menu-popper .el-dropdown-menu {
  min-width: 148px;
  padding: 6px;
  margin: 0;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--surface);
  box-shadow: var(--shadow);
}

.conv-menu-popper .el-dropdown-menu__item {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 36px;
  padding: 0 12px;
  margin: 0;
  border-radius: 8px;
  color: var(--text);
  font-size: 14px;
  line-height: 1;
}

.conv-menu-popper .el-dropdown-menu__item .el-icon {
  font-size: 16px;
  color: var(--text-secondary);
}

.conv-menu-popper .el-dropdown-menu__item:not(.is-disabled):hover,
.conv-menu-popper .el-dropdown-menu__item:not(.is-disabled):focus {
  background: var(--bg-subtle) !important;
  color: var(--text) !important;
  border-radius: 8px;
}

.conv-menu-popper .el-dropdown-menu__item:not(.is-disabled):hover .el-icon,
.conv-menu-popper .el-dropdown-menu__item:not(.is-disabled):focus .el-icon {
  color: var(--text);
}

.conv-menu-popper .conv-menu-danger,
.conv-menu-popper .conv-menu-danger .el-icon {
  color: var(--danger) !important;
}

.conv-menu-popper .conv-menu-danger:not(.is-disabled):hover,
.conv-menu-popper .conv-menu-danger:not(.is-disabled):focus {
  background: #fef2f2 !important;
  color: var(--danger) !important;
  border-radius: 8px;
}

.conv-menu-popper .conv-menu-danger:not(.is-disabled):hover .el-icon,
.conv-menu-popper .conv-menu-danger:not(.is-disabled):focus .el-icon {
  color: var(--danger) !important;
}
</style>
