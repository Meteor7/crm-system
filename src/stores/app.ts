import { defineStore } from 'pinia'
import { markRaw } from 'vue'
import { api, notificationDelivery, usingMock } from '@/api'
import type { CrmApi } from '@/api'
import type { BootstrapDto } from '@/types/crm'
import type { Capability } from '@/types/crm'
import { hasCapability } from '@/domain/permissions'
import { createNotifyingApi, type NotificationDelivery } from '@/api/notifying-api'
import { useNotificationStore } from '@/stores/notifications'
import { initializePersonnelDirectory } from '@/demo/personnel'

function connectNotifications(apiClient: CrmApi, delivery: NotificationDelivery = notificationDelivery) {
  const notifications = useNotificationStore()
  return markRaw(createNotifyingApi(apiClient, (message) => notifications.add(message), delivery))
}

function usesServerNotificationDelivery(delivery: NotificationDelivery = notificationDelivery as NotificationDelivery) {
  return delivery === 'server'
}

export const useAppStore = defineStore('app', {
  state: () => ({
    bootstrap: null as BootstrapDto | null,
    activeApi: markRaw(api) as CrmApi,
    identityId: 'administrator',
    identityRevision: 0,
    sessionRequestRevision: 0,
    notificationPage: 1,
    notificationPageSize: 50,
    loading: false,
    error: '',
    bootstrapPromise: null as Promise<void> | null,
  }),
  actions: {
    can(capability: Capability) {
      return hasCapability(this.bootstrap, capability)
    },
    async loadBootstrap(apiClient?: CrmApi) {
      if (this.bootstrap) {
        this.activeApi = connectNotifications(this.activeApi)
        return
      }
      if (this.bootstrapPromise) {
        await this.bootstrapPromise
        this.activeApi = connectNotifications(this.activeApi)
        return
      }
      const sourceApi = apiClient ?? this.activeApi
      const connectedApi = connectNotifications(sourceApi)
      this.activeApi = connectedApi
      const revision = ++this.sessionRequestRevision
      this.loading = true
      this.error = ''
      const request = (async () => {
        try {
          const result = await connectedApi.getBootstrap()
          if (revision !== this.sessionRequestRevision) return
          if (result.data.csrfToken && typeof window !== 'undefined') {
            const target = window as Window & { frappe?: { csrf_token?: string } }
            target.frappe ??= {}
            target.frappe.csrf_token = result.data.csrfToken
          }
          if (result.data.personnel) initializePersonnelDirectory(result.data.personnel)
          this.bootstrap = result.data
          const notifications = useNotificationStore()
          notifications.setActiveRecipient(result.data.user.id, result.data.user.role)
          if (usesServerNotificationDelivery()) {
            try {
              await this.refreshNotifications()
            } catch {
              // Bootstrap remains usable when the notification service is temporarily unavailable.
            }
          } else {
            const requirementResult = await connectedApi.listRequirements({ page: 1, pageSize: 3 })
            if (revision !== this.sessionRequestRevision) return
            notifications.replaceRequirementNotifications(requirementResult.data.items)
          }
        } catch (error) {
          if (revision !== this.sessionRequestRevision) return
          this.error = error instanceof Error ? error.message : '无法读取当前用户信息'
        } finally {
          if (revision === this.sessionRequestRevision) this.loading = false
        }
      })()
      this.bootstrapPromise = request
      try {
        await request
      } finally {
        if (this.bootstrapPromise === request) this.bootstrapPromise = null
      }
    },
    async refreshNotifications() {
      if (!usesServerNotificationDelivery() || !this.bootstrap) return
      const notifications = useNotificationStore()
      const [result, unread] = await Promise.all([
        this.activeApi.listNotifications({ page: 1, pageSize: this.notificationPageSize }),
        this.activeApi.listNotifications({ page: 1, pageSize: 1, unreadOnly: true }),
      ])
      this.notificationPage = 1
      notifications.replaceAll(result.data.items, result.meta?.total ?? result.data.items.length, unread.meta?.total ?? unread.data.items.length)
    },
    async loadMoreNotifications() {
      if (!usesServerNotificationDelivery() || !this.bootstrap) return
      const notifications = useNotificationStore()
      if (notifications.items.length >= notifications.serverTotal) return
      const page = this.notificationPage + 1
      const result = await this.activeApi.listNotifications({ page, pageSize: this.notificationPageSize })
      this.notificationPage = page
      notifications.appendPage(result.data.items, result.meta?.total ?? notifications.serverTotal)
    },
    async switchDemoIdentity(identityId: string) {
      if (!usingMock) throw new Error('真实后端身份由 Frappe 会话管理，不能在浏览器内切换。')
      const revision = ++this.sessionRequestRevision
      this.loading = true
      this.error = ''
      try {
        const { createDemoIdentityApi } = await import('@/api/identity-switch')
        const { api: nextApi, identity } = createDemoIdentityApi(identityId)
        const result = await nextApi.getBootstrap()
        const requirementResult = await nextApi.listRequirements({ page: 1, pageSize: 3 })
        if (revision !== this.sessionRequestRevision) return
        useNotificationStore().replaceRequirementNotifications(requirementResult.data.items)
        this.activeApi = connectNotifications(nextApi)
        this.bootstrap = {
          ...result.data,
          user: { ...result.data.user, name: identity.name, initials: identity.initials, team: identity.team },
        }
        useNotificationStore().setActiveRecipient(identity.id, identity.role)
        this.identityId = identity.demoIdentityId ?? 'administrator'
        this.identityRevision += 1
      } catch (error) {
        if (revision !== this.sessionRequestRevision) return
        this.error = error instanceof Error ? error.message : 'Demo 身份切换失败'
        throw error
      } finally {
        if (revision === this.sessionRequestRevision) this.loading = false
      }
    },
    async markNotificationRead(id: string) {
      const notifications = useNotificationStore()
      if (usesServerNotificationDelivery()) await this.activeApi.markNotificationRead(id)
      notifications.markRead(id)
    },
    async markAllNotificationsRead() {
      const notifications = useNotificationStore()
      if (usesServerNotificationDelivery()) await this.activeApi.markAllNotificationsRead()
      notifications.markAllRead()
    },
  },
})
