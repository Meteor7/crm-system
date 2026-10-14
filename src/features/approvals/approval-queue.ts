import type { Capability, UserRole } from '@/types/crm'

export type ApprovalKind = 'demo' | 'quotation' | 'production' | 'visit' | 'rfq' | 'document' | 'demo-engineering' | 'test-review' | 'rfq-engineering' | 'customer-review' | 'document-upload'
export interface ApprovalViewer { id: string; name: string; role: UserRole; capabilities: readonly Capability[] }
export interface ApprovalItem {
  id: string
  kind: ApprovalKind
  title: string
  customer: string
  sourceId: string
  sourceRecordId?: string
  target?: { path: string; query?: Record<string, string> }
  stage: string
  requester: string
  requesterId: string
  sales: string
  region: string
  market: string
  equipment: string
  submittedAt: string
  submittedAtLabel?: string
  unread: boolean
  recipientId: string
  recipientRole: UserRole
  state: 'pending' | 'approved' | 'rejected' | 'cancelled'
  // These decisions must come from the authenticated business service when connected.
  canReadSource: boolean
  canHandle: boolean
  forbidSelfApproval?: boolean
  description: string
  sourceLabel: string
}

export const approvalLabels: Record<ApprovalKind, string> = {
  'document-upload': '文档上传', demo: 'Demo 申请', quotation: '报价审批', production: '生产审批', visit: '拜访纪要', rfq: 'RFQ 审批', document: '文档申请',
  'demo-engineering': 'Demo 评估', 'test-review': '测试审核', 'rfq-engineering': 'RFQ 技术评审', 'customer-review': '客户评审',
}
const capabilities: Record<ApprovalKind, readonly Capability[]> = {
  'document-upload': ['contract:view'], demo: ['demo_request:view', 'demo_request:manager_approve'], quotation: ['quotation:view', 'quotation:approve'],
  production: ['deal:view', 'deal:internal_validation_approve'], visit: ['visit:view', 'visit:review'],
  rfq: ['rfq:view', 'rfq:manager_approve'], document: ['contract:view'],
  'demo-engineering': ['demo_request:view', 'demo_request:engineering_review'],
  'test-review': ['evaluation:view', 'evaluation:write'], 'rfq-engineering': ['rfq:view', 'rfq:engineer_comment'],
  'customer-review': ['evaluation:view', 'evaluation:customer_review'],
}

export function visibleApprovals(items: readonly ApprovalItem[], viewer: ApprovalViewer): ApprovalItem[] {
  if (!viewer.id) return []
  return items.filter(item => (!['document', 'document-upload'].includes(item.kind) || viewer.role === 'Manager') && item.state === 'pending' && item.recipientId === viewer.id && item.recipientRole === viewer.role
    && item.canReadSource === true && item.canHandle === true && capabilities[item.kind]?.every(capability => viewer.capabilities.includes(capability))
    && (!item.forbidSelfApproval || item.requesterId !== viewer.id))
}

export function approvalTarget(item: ApprovalItem): { path: string; query?: Record<string, string> } {
  if (item.target) return item.target
  const source = item.sourceRecordId || item.sourceId
  const id = encodeURIComponent(source)
  switch (item.kind) {
    case 'demo': return { path: '/demo-requests', query: { focus: source, mode: 'manager' } }
    case 'demo-engineering': return { path: '/demo-requests', query: { focus: source, mode: 'engineer' } }
    case 'quotation': return { path: '/quotations/' + id }
    case 'production': return { path: '/opportunities/' + id }
    case 'visit': return { path: '/visits', query: { focus: source } }
    case 'rfq': case 'rfq-engineering': return { path: '/rfqs/' + id }
    case 'document-upload': case 'document': return { path: '/document-center', query: { workspace: 'approvals', request: source } }
    case 'test-review': case 'customer-review': return { path: '/evaluations', query: { focus: source } }
  }
}

export function approvalLabel(kind: ApprovalKind, locale: string): string {
  const english: Record<ApprovalKind, string> = {
    demo: 'Demo request', quotation: 'Quotation', production: 'Production', visit: 'Visit minutes', rfq: 'RFQ', document: 'Document access',
    'document-upload': 'Document upload', 'demo-engineering': 'Demo feasibility', 'test-review': 'Internal review', 'rfq-engineering': 'RFQ technical review', 'customer-review': 'Customer review',
  }
  return locale === 'en-US' ? english[kind] : approvalLabels[kind]
}
