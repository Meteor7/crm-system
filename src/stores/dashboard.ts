import { resolveLocaleMessage, type LocaleMessage } from '@/i18n'
import { defineStore } from 'pinia'
import type { CrmApi } from '@/api'
import type { DashboardDto } from '@/types/crm'
import { mapRequestError, readRequestMeta } from '@/api/request-state'

export const useDashboardStore = defineStore('dashboard', {
  state: () => ({ data: null as DashboardDto | null, warnings: [] as string[], loading: false, errorSource: '' as LocaleMessage, requestId: '', stale: false, staleMessageSource: '' as LocaleMessage, denied: false, loadSequence: 0 }),
  getters: {
    error: (state) => resolveLocaleMessage(state.errorSource),
    staleMessage: (state) => resolveLocaleMessage(state.staleMessageSource),
  },
  actions: {
    async load(apiClient: CrmApi, range: 'month' | 'quarter' | 'year' = 'quarter') {
      const sequence = ++this.loadSequence
      this.loading = true
      this.errorSource = ''
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
        this.staleMessageSource = meta.localizedMessage ?? meta.message
      } catch (error) {
        if (sequence !== this.loadSequence) return
        const mapped = mapRequestError(error)
        this.data = null
        this.errorSource = mapped.localizedMessage ?? mapped.message
        this.requestId = mapped.requestId
        this.denied = mapped.denied
      } finally {
        if (sequence === this.loadSequence) this.loading = false
      }
    },
  },
})
