import { defineStore } from 'pinia'
import type { CrmApi } from '@/api'
import type { DashboardDto } from '@/types/crm'
import { mapRequestError, readRequestMeta } from '@/api/request-state'

export const useDashboardStore = defineStore('dashboard', {
  state: () => ({ data: null as DashboardDto | null, warnings: [] as string[], loading: false, error: '', requestId: '', stale: false, staleMessage: '', denied: false, loadSequence: 0 }),
  actions: {
    async load(apiClient: CrmApi, range: 'month' | 'quarter' | 'year' = 'quarter') {
      const sequence = ++this.loadSequence
      this.loading = true
      this.error = ''
      this.requestId = ''
      this.denied = false
      try {
        const result = await apiClient.getDashboard({ range })
        if (sequence !== this.loadSequence) return
        const meta = readRequestMeta(result)
        this.data = result.data
        this.warnings = meta.warnings
        this.requestId = meta.requestId
        this.stale = meta.stale
        this.staleMessage = meta.message
      } catch (error) {
        if (sequence !== this.loadSequence) return
        const mapped = mapRequestError(error)
        this.data = null
        this.error = mapped.message
        this.requestId = mapped.requestId
        this.denied = mapped.denied
      } finally {
        if (sequence === this.loadSequence) this.loading = false
      }
    },
  },
})
