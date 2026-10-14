/** 投研助手会话状态（mode=direct → 后端 Multi-Agent，与 rag store 隔离）。 */
import { defineStore } from 'pinia'
import { createChatStoreOptions } from './createChatStore'

export const useDirectChatStore = defineStore(
  'directChat',
  createChatStoreOptions('direct'),
)
