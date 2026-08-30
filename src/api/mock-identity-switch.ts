import { createMockApi } from './mock-adapter'
import { getDemoIdentity } from '@/demo/identities'
import { getSharedDemoRepository } from '@/demo/demo-repository'
import { getSharedSalesRepository } from '@/demo/sales-repository'

export function createDemoIdentityApi(identityId: string) {
  const identity = getDemoIdentity(identityId)
  const api = createMockApi({
    repository: getSharedDemoRepository(),
    salesRepository: getSharedSalesRepository(),
    latency: 0,
    role: identity.role,
    userId: identity.id,
    userName: identity.name,
    teamOwners: identity.teamOwners,
    assignedAccountIds: identity.assignedAccountIds,
  })
  return { api, identity }
}
