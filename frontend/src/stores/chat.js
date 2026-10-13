/** 对话状态：新对话只清本地；首问由后端懒建 conversationId。 */
import { defineStore } from 'pinia'
import * as chatApi from '../api/chat'

export const useChatStore = defineStore('chat', {
  state: () => ({
    conversationId: null,
    messages: [],
    conversations: [],
    asking: false,
  }),
  actions: {
    /** 新对话：只清本地状态，不调删除接口。 */
    newChat() {
      this.conversationId = null
      this.messages = []
    },
    /** 刷新会话列表。 */
    async refreshConversations() {
      const res = await chatApi.listConversations()
      this.conversations = res.data || []
    },
    /** 打开历史会话并加载消息。 */
    async openConversation(id) {
      const res = await chatApi.getConversation(id)
      this.conversationId = res.data.conversation.id
      this.messages = res.data.messages || []
    },
    /** 重命名会话标题。 */
    async renameConversation(id, title) {
      await chatApi.updateConversation(id, { title })
      await this.refreshConversations()
    },
    /** 删除会话；若正打开则清本地。 */
    async removeConversation(id) {
      await chatApi.deleteConversation(id)
      this.conversations = this.conversations.filter((c) => c.id !== id)
      if (this.conversationId === id) {
        this.newChat()
      }
    },
    /** 提问：乐观插入 user，再追加 assistant（含 citations / rejected）。 */
    async ask(text) {
      this.asking = true
      this.messages.push({ role: 'user', content: text, citations: null })
      try {
        const res = await chatApi.askChat({
          message: text,
          conversationId: this.conversationId,
        })
        this.conversationId = res.data.conversationId
        this.messages.push({
          role: 'assistant',
          content: res.data.answer,
          citations: res.data.citations || [],
          rejected: res.data.rejected,
        })
        await this.refreshConversations()
      } catch (err) {
        this.messages.push({
          role: 'assistant',
          content: err?.message || '问答失败，请稍后重试',
          citations: [],
          rejected: false,
        })
        throw err
      } finally {
        this.asking = false
      }
    },
  },
})
