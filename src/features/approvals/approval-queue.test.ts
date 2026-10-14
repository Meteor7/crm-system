import { describe, expect, it } from 'vitest'
import { demoApprovals, demoViewer } from '../../../previews/approvals/demo-fixtures'
import { approvalTarget, visibleApprovals } from './approval-queue'

describe('Approval queue visibility', () => {
  it.each([['Manager', 6], ['Sales', 2], ['Engineer', 4]] as const)('only returns pending items addressed to %s with current permissions', (role, count) => {
    const viewer = demoViewer(role), visible = visibleApprovals(demoApprovals(), viewer)
    expect(visible).toHaveLength(count)
    expect(visible.every(item => item.recipientId === viewer.id && item.recipientRole === role)).toBe(true)
    expect(visible.some(item => item.id.startsWith('DENIED') || item.id === 'FINISHED')).toBe(false)
  })
  it('rejects an unknown viewer, revoked handling permission, and lost source access', () => {
    const viewer = demoViewer('Manager'), item = demoApprovals()[0]!
    expect(visibleApprovals([item], { ...viewer, id: '' })).toEqual([])
    expect(visibleApprovals([{ ...item, canHandle: false }], viewer)).toEqual([])
    expect(visibleApprovals([{ ...item, canReadSource: false }], viewer)).toEqual([])
    expect(visibleApprovals([item], { ...viewer, capabilities: [] })).toEqual([])
  })
  it('does not reuse a queue after the same account changes role or approves its own restricted request', () => {
    const viewer = demoViewer('Manager'), items = demoApprovals()
    expect(visibleApprovals(items, { ...viewer, role: 'Sales' })).toEqual([])
    const request = items.find(item => item.kind === 'production')!
    expect(visibleApprovals([{ ...request, requesterId: viewer.id }], viewer)).toEqual([])
  })
  it('does not treat document read permission as approval authority', () => {
    const viewer = demoViewer('Sales'), document = demoApprovals().find(item => item.kind === 'document')!
    expect(visibleApprovals([{ ...document, recipientId: viewer.id, recipientRole: viewer.role }], viewer)).toEqual([])
  })
  it.each(['approved', 'rejected', 'cancelled'] as const)('drops %s tasks even when their notification is unread', state => {
    const item = { ...demoApprovals()[0]!, state, unread: true }
    expect(visibleApprovals([item], demoViewer('Manager'))).toEqual([])
  })
})

describe('Approval destinations', () => {
  it.each([
    ['demo', { path: '/demo-requests', query: { focus: 'CRM-DR-04182', mode: 'manager' } }],
    ['quotation', { path: '/quotations/CRM-QTN-04103' }],
    ['production', { path: '/opportunities/CRM-OPP-03276' }],
    ['visit', { path: '/visits', query: { focus: 'CRM-VIS-02641' } }],
    ['rfq', { path: '/rfqs/CRM-RFQ-01037' }],
    ['document', { path: '/document-center', query: { workspace: 'approvals', request: 'DOC-REQ-00216' } }],
    ['demo-engineering', { path: '/demo-requests', query: { focus: 'CRM-DR-04183', mode: 'engineer' } }],
    ['test-review', { path: '/evaluations', query: { focus: 'CRM-EVAL-02945' } }],
    ['rfq-engineering', { path: '/rfqs/CRM-RFQ-01038' }],
    ['customer-review', { path: '/evaluations', query: { focus: 'CRM-EVAL-02942' } }],
  ] as const)('locates the %s business record and approval workspace', (kind, expected) => {
    const item = demoApprovals().find(item => item.kind === kind)!
    expect(approvalTarget(item)).toEqual(expected)
  })
})
