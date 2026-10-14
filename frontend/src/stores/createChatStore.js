/** 按 mode 生成对话 Pinia store 配置（rag / direct 各一份，状态隔离）。 */
import * as chatApi from '../api/chat'

/**
 * @param {'rag' | 'direct'} mode 固定写入本 store 的问答与列表过滤模式
 * @returns {object} Pinia defineStore 用的 options（state + actions）
 */
export function createChatStoreOptions(mode) {
  return {
    state: () => ({
      conversationId: null,
      messages: [],
      conversations: [],
      asking: false,
      mode,
    }),
    actions: {
      /** 新对话：只清本地状态，不调删除接口。 */
      newChat() {
        this.conversationId = null
        this.messages = []
      },
      /** 刷新本 mode 下的会话列表。 */
      async refreshConversations() {
        const res = await chatApi.listConversations(mode)
        this.conversations = res.data || []
      },
      /**
       * 打开历史会话；若详情 conversation.mode 与本页不一致则抛错（A5b）。
       * @param {number} id
       */
      async openConversation(id) {
        const res = await chatApi.getConversation(id)
        const conv = res.data.conversation
        if (conv.mode !== mode) {
          const err = new Error('会话模式不匹配，已返回列表')
          err.code = 40001
          throw err
        }
        this.conversationId = conv.id
        this.messages = res.data.messages || []
      },
      /** 重命名会话标题后刷新列表。 */
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
      /**
       * 提问：乐观插入 user，再追加 assistant；请求体始终带本 store 的 mode。
       * @param {string} text
       */
      async ask(text) {
        this.asking = true
        this.messages.push({ role: 'user', content: text, citations: null })
        try {
          const res = await chatApi.askChat({
            message: text,
            conversationId: this.conversationId,
            mode,
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
  }
}
