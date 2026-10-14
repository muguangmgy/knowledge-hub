/** 自由对话（direct）会话状态。 */
import { defineStore } from 'pinia'
import { createChatStoreOptions } from './createChatStore'

export const useDirectChatStore = defineStore(
  'directChat',
  createChatStoreOptions('direct'),
)
