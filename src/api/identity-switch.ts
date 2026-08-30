import type { CrmApi } from './contracts'
import type { DemoIdentity } from '@/demo/identities'

export function createDemoIdentityApi(_identityId: string): { api: CrmApi; identity: DemoIdentity } {
  throw new Error('Frappe session controls identity; browser impersonation is disabled.')
}
