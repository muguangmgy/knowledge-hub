/** 按 mode 生成对话 Pinia store 配置（rag / direct 各一份，状态隔离）。 */
import * as chatApi from '../api/chat'
import { isChatStreamEnabled } from '../utils/chatStreamPref'

/** AbortController 不进 Pinia state，避免被 Proxy 包裹。 */
const abortByMode = new Map()

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
      stageMessage: '',
      mode,
    }),
    actions: {
      /** 新对话：只清本地状态，不调删除接口。 */
      newChat() {
        this.stopAsking()
        this.conversationId = null
        this.messages = []
        this.stageMessage = ''
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
        this.stopAsking()
        const res = await chatApi.getConversation(id)
        const conv = res.data.conversation
        if (conv.mode !== mode) {
          const err = new Error('会话模式不匹配，已返回列表')
          err.code = 40001
          throw err
        }
        this.conversationId = conv.id
        this.messages = res.data.messages || []
        this.stageMessage = ''
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
      /** 停止当前问答（Abort）；流式/同步共用。 */
      stopAsking() {
        const ac = abortByMode.get(mode)
        if (ac) {
          ac.abort()
          abortByMode.delete(mode)
        }
      },
      /**
       * 提问：按开发调试开关走 SSE 或同步整包。
       * asking 期间直接 return；Abort/取消则收回 assistant 气泡。
       * @param {string} text
       */
      async ask(text) {
        if (this.asking) return
        this.asking = true
        this.stageMessage = ''
        this.messages.push({ role: 'user', content: text, citations: null })
        const assistantIdx = this.messages.length
        this.messages.push({
          role: 'assistant',
          content: '',
          citations: [],
          rejected: false,
          streaming: true,
        })

        const ac = new AbortController()
        abortByMode.set(mode, ac)
        let gotDone = false
        let cancelled = false

        try {
          if (isChatStreamEnabled()) {
            await this._askStream(text, assistantIdx, ac, () => {
              gotDone = true
            })
            if (!gotDone && ac.signal.aborted) {
              cancelled = true
            } else if (!gotDone) {
              const m = this.messages[assistantIdx]
              if (m && !(m.content || '').trim()) {
                this.messages.splice(assistantIdx, 1)
              } else if (m) {
                m.streaming = false
              }
            }
          } else {
            await this._askSync(text, assistantIdx, ac)
            gotDone = true
          }
        } catch (err) {
          if (err?.name === 'AbortError' || err?.code === 'ERR_CANCELED' || ac.signal.aborted) {
            cancelled = true
          } else {
            const m = this.messages[assistantIdx]
            if (m && m.streaming) {
              m.content = err?.message || '问答失败，请稍后重试'
              m.citations = []
              m.streaming = false
            }
            throw err
          }
        } finally {
          if (cancelled) {
            if (
              this.messages[assistantIdx] &&
              this.messages[assistantIdx].role === 'assistant'
            ) {
              this.messages.splice(assistantIdx, 1)
            }
            this.stageMessage = ''
          }
          if (abortByMode.get(mode) === ac) {
            abortByMode.delete(mode)
          }
          this.asking = false
          try {
            await this.refreshConversations()
          } catch {
            /* ignore */
          }
        }
      },
      /**
       * SSE 主路径：meta/stage/citations/delta/done/error。
       * @param {string} text
       * @param {number} assistantIdx
       * @param {AbortController} ac
       * @param {() => void} markDone
       */
      async _askStream(text, assistantIdx, ac, markDone) {
        await chatApi.askChatStream(
          {
            message: text,
            conversationId: this.conversationId,
            mode,
          },
          {
            onMeta: (data) => {
              if (data.conversationId != null) {
                this.conversationId = data.conversationId
              }
            },
            onStage: (data) => {
              this.stageMessage = data.message || data.stage || ''
            },
            onCitations: (data) => {
              const m = this.messages[assistantIdx]
              if (m) m.citations = data.citations || []
            },
            onDelta: (data) => {
              const m = this.messages[assistantIdx]
              if (m) m.content = (m.content || '') + (data.text || '')
            },
            onDone: (data) => {
              markDone()
              this.conversationId = data.conversationId ?? this.conversationId
              const m = this.messages[assistantIdx]
              if (m) {
                m.content = data.answer ?? m.content
                m.citations = data.citations || []
                m.rejected = !!data.rejected
                m.id = data.messageId
                m.streaming = false
              }
              this.stageMessage = ''
            },
            onError: (data) => {
              const m = this.messages[assistantIdx]
              if (m) {
                m.content = data.message || '问答失败，请稍后重试'
                m.citations = []
                m.rejected = false
                m.streaming = false
              }
              this.stageMessage = ''
            },
          },
          ac.signal,
        )
      },
      /**
       * 同步整包：一次填满 assistant；无 stage 增量。
       * @param {string} text
       * @param {number} assistantIdx
       * @param {AbortController} ac
       */
      async _askSync(text, assistantIdx, ac) {
        this.stageMessage = '正在生成…'
        const res = await chatApi.askChat(
          {
            message: text,
            conversationId: this.conversationId,
            mode,
          },
          { signal: ac.signal },
        )
        const data = res.data || {}
        this.conversationId = data.conversationId ?? this.conversationId
        const m = this.messages[assistantIdx]
        if (m) {
          m.content = data.answer ?? ''
          m.citations = data.citations || []
          m.rejected = !!data.rejected
          m.id = data.messageId
          m.streaming = false
        }
        this.stageMessage = ''
      },
    },
  }
}
