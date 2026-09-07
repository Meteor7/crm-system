import { defineStore } from 'pinia'
import type { AppNotification, NotificationDto, NotificationInput } from '@/types/notifications'
import type { RequirementDto, UserRole } from '@/types/crm'
import { personnelDisplayName } from '@/demo/personnel'

let sequence = 0

function isVisibleToRecipient(item: AppNotification, recipientId: string) {
  if (!item.recipientId) return true
  return item.recipientId === recipientId
}

export const useNotificationStore = defineStore('notifications', {
  state: () => ({
    items: [] as AppNotification[],
    activeRecipient: '',
    activeRecipientId: '',
    serverTotal: 0,
    serverUnreadTotal: null as number | null,
  }),
  getters: {
    visibleItems: (state) => state.items.filter((item) =>
      isVisibleToRecipient(item, state.activeRecipientId)),
    unreadCount: (state) => state.serverUnreadTotal ?? state.items.filter((item) =>
      !item.read && isVisibleToRecipient(item, state.activeRecipientId)).length,
  },
  actions: {
    setActiveRecipient(userId: string, _role?: UserRole) {
      this.activeRecipientId = userId
      this.activeRecipient = personnelDisplayName(userId)
    },
    replaceRequirementNotifications(requirements: RequirementDto[]) {
      const requirementItems = requirements.slice(0, 3).map((requirement) => ({
        id: `requirement-${requirement.id.toLowerCase()}`,
        category: 'Requirement' as const,
        generatedLocally: true,
        title: '需求待跟进',
        message: `${requirement.id} · ${requirement.accountName} · ${requirement.title}`,
        route: requirement.linkedDealId
          ? `/opportunities/${requirement.linkedDealId}`
          : `/accounts?search=${encodeURIComponent(requirement.accountName)}`,
        createdAt: '当前待办',
        read: false,
      }))
      this.items = [...this.items.filter((item) => item.category !== 'Requirement'), ...requirementItems]
    },
    replaceAll(notifications: NotificationDto[], total = notifications.length, unreadTotal?: number) {
      this.items = notifications.map((notification) => ({
        id: notification.id,
        category: notification.category,
        title: notification.title,
        message: notification.message,
        route: notification.route,
        recipientId: notification.recipientId,
        createdAt: notification.createdAt,
        read: notification.read,
      }))
      this.serverTotal = total
      this.serverUnreadTotal = unreadTotal ?? null
    },
    appendPage(notifications: NotificationDto[], total: number) {
      const known = new Set(this.items.map((item) => item.id))
      this.items.push(...notifications.filter((item) => !known.has(item.id)).map((notification) => ({
        id: notification.id,
        category: notification.category,
        title: notification.title,
        message: notification.message,
        route: notification.route,
        recipientId: notification.recipientId,
        createdAt: notification.createdAt,
        read: notification.read,
      })))
      this.serverTotal = total
    },
    add(input: NotificationInput) {
      sequence += 1
      this.items.unshift({
        ...input,
        generatedLocally: true,
        id: `notification-${Date.now()}-${sequence}`,
        createdAt: '刚刚',
        read: false,
      })
    },
    markRead(id: string) {
      const item = this.items.find((notification) =>
        notification.id === id
        && isVisibleToRecipient(notification, this.activeRecipientId))
      if (item && !item.read) {
        item.read = true
        if (this.serverUnreadTotal !== null) this.serverUnreadTotal = Math.max(0, this.serverUnreadTotal - 1)
      }
    },
    markAllRead() {
      this.items.forEach((item) => {
        if (isVisibleToRecipient(item, this.activeRecipientId)) item.read = true
      })
      if (this.serverUnreadTotal !== null) this.serverUnreadTotal = 0
    },
  },
})
