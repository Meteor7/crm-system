import { createFrappeApi } from './frappe-adapter'

export const usingMock = false
export const notificationDelivery = 'server' as const
export const api = createFrappeApi()
