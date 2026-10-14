/** 知识库问答（rag）会话状态。 */
import { defineStore } from 'pinia'
import { createChatStoreOptions } from './createChatStore'

export const useChatStore = defineStore('chat', createChatStoreOptions('rag'))
