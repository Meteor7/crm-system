import { createMockApi } from './mock-adapter'
import { getSharedDemoRepository } from '@/demo/demo-repository'
import { getSharedSalesRepository } from '@/demo/sales-repository'
import { getSharedContactFileRepository } from '@/demo/contact-file-repository'

export const usingMock = true
export const notificationDelivery = 'local' as const
export const api = createMockApi({
  repository: getSharedDemoRepository(),
  salesRepository: getSharedSalesRepository(),
  contactFileRepository: getSharedContactFileRepository(),
})
