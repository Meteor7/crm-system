import { CrmApiError } from '@/api/contracts'
import type { BootstrapDto, Capability, UserRole } from '@/types/crm'

export interface RoleProfile {
  label: string
  scope: 'all' | 'own' | 'assigned'
  capabilities: Capability[]
}

export const ALL_CAPABILITIES: Capability[] = [
  'cockpit:view',
  'dashboard:view', 'account:view', 'account:write',
  'stakeholder:view', 'stakeholder:write', 'requirement:view', 'deal:view', 'deal:write',
  'deal:rollback', 'deal:internal_validation_approve',
  'contact:view', 'contact:write', 'contact:merge', 'contact:delete',
  'visit:view', 'visit:create', 'visit:write', 'visit:review', 'event:view', 'event:write', 'demo_request:view', 'demo_request:create',
  'demo_request:engineering_review', 'demo_request:manager_approve',
  'evaluation:view', 'evaluation:write',
  'installed_tool:write',
  'service:view', 'contract:view',
  'quotation:view', 'quotation:write', 'quotation:submit', 'quotation:approve', 'quotation:publish',
  'rfq:view', 'rfq:create', 'rfq:engineer_comment', 'rfq:manager_approve',
]

const SALES_CAPABILITIES: Capability[] = [
  'dashboard:view', 'account:view', 'account:write', 'stakeholder:view', 'stakeholder:write',
  'contact:view', 'contact:write',
  'requirement:view', 'deal:view', 'deal:write', 'visit:view', 'visit:create', 'visit:write', 'event:view', 'event:write',
  'demo_request:view', 'demo_request:create', 'evaluation:view', 'service:view', 'contract:view',
  'quotation:view', 'quotation:write', 'quotation:submit',
  'rfq:view', 'rfq:create',
]

const ENGINEERING_CAPABILITIES: Capability[] = [
  'dashboard:view', 'account:view', 'requirement:view', 'deal:view', 'demo_request:view',
  'demo_request:engineering_review', 'evaluation:view', 'evaluation:write', 'service:view',
  'installed_tool:write',
  'rfq:view', 'rfq:engineer_comment',
]

export const ROLE_PROFILES: Record<UserRole, RoleProfile> = {
  Manager: { label: 'Manager', scope: 'all', capabilities: ALL_CAPABILITIES },
  Sales: { label: 'Sales', scope: 'own', capabilities: SALES_CAPABILITIES },
  Engineer: { label: 'Engineer', scope: 'assigned', capabilities: ENGINEERING_CAPABILITIES },
}

export function hasCapability(
  bootstrap: Pick<BootstrapDto, 'capabilities'> | null | undefined,
  capability: Capability,
) {
  return Boolean(bootstrap?.capabilities.includes(capability))
}

export function assertCapability(capabilities: readonly Capability[], capability: Capability) {
  if (!capabilities.includes(capability)) {
    throw new CrmApiError('PERMISSION_DENIED', `当前角色无权执行 ${capability}`, 'req_permission_denied', false)
  }
}

export function assertAnyCapability(capabilities: readonly Capability[], required: readonly Capability[]) {
  if (!required.some((capability) => capabilities.includes(capability))) {
    throw new CrmApiError('PERMISSION_DENIED', `当前角色缺少所需权限：${required.join(' / ')}`, 'req_permission_denied', false)
  }
}
