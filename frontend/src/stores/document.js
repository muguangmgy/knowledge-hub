/** 文档列表状态：刷新 / 上传 / 删除。 */
import { defineStore } from 'pinia'
import * as docApi from '../api/documents'

export const useDocumentStore = defineStore('document', {
  state: () => ({
    items: [],
    loading: false,
  }),
  actions: {
    /** 刷新文档列表。 */
    async refresh() {
      this.loading = true
      try {
        const res = await docApi.listDocuments()
        this.items = res.data || []
      } finally {
        this.loading = false
      }
    },
    /** 删除文档后刷新列表。 */
    async remove(id) {
      await docApi.deleteDocument(id)
      await this.refresh()
    },
    /** 上传入库后刷新列表。 */
    async upload(file) {
      await docApi.uploadDocument(file)
      await this.refresh()
    },
  },
})
