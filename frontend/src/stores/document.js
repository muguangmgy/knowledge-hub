/** 文档列表状态：刷新 / 上传 / 批量 / 删除 / 重新解析。 */
import { defineStore } from 'pinia'
import * as docApi from '../api/documents'

export const useDocumentStore = defineStore('document', {
  state: () => ({
    items: [],
    loading: false,
    reingesting: false,
    batchDeleting: false,
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
    /** 批量删除后刷新列表；返回 total/ok/failed/items/errors。 */
    async removeBatch(ids) {
      this.batchDeleting = true
      try {
        const res = await docApi.deleteDocumentsBatch(ids)
        await this.refresh()
        return res.data || {}
      } finally {
        this.batchDeleting = false
      }
    },
    /** 上传入库后刷新列表。 */
    async upload(file) {
      await docApi.uploadDocument(file)
      await this.refresh()
    },
    /** 批量入库，不在此刷新；由页面按成功数决定是否刷新。 */
    async uploadBatch(files) {
      const res = await docApi.uploadDocumentsBatch(files)
      return res.data || {}
    },
    /** 单文档重新解析后刷新列表。 */
    async reingest(id) {
      await docApi.reingestDocument(id)
      await this.refresh()
    },
    /** 全部重新解析；返回汇总 data。 */
    async reingestAll() {
      this.reingesting = true
      try {
        const res = await docApi.reingestAllDocuments()
        await this.refresh()
        return res.data || {}
      } finally {
        this.reingesting = false
      }
    },
  },
})
