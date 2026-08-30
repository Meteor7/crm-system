import { describe, expect, it } from 'vitest'
import type { ContactDto } from '@/types/crm'
import { buildStakeholderForest, validateReportingLine } from './stakeholders'

const rows: ContactDto[] = [
  { id: 'CON-001', accountId: 'ACC-001', name: '负责人', title: 'VP', department: '制造', relationship: 'Strong', owner: 'person002@crm.example.invalid', status: 'Active', dataQuality: 'Complete', updatedAt: '2026-07-28' },
  { id: 'CON-002', accountId: 'ACC-001', name: '工程经理', title: 'Manager', department: '工程', relationship: 'Developing', owner: 'person002@crm.example.invalid', status: 'Active', dataQuality: 'Complete', updatedAt: '2026-07-28', reportsToContactId: 'CON-001' },
  { id: 'CON-003', accountId: 'ACC-001', name: '工程师', title: 'Engineer', department: '工程', relationship: 'Developing', owner: 'person002@crm.example.invalid', status: 'Active', dataQuality: 'Complete', updatedAt: '2026-07-28', reportsToContactId: 'CON-002' },
]

describe('stakeholder organization tree', () => {
  it('builds a nested forest without inventing relations', () => {
    expect(buildStakeholderForest(rows)[0].children[0].contact.id).toBe('CON-002')
    expect(buildStakeholderForest([{ ...rows[1], reportsToContactId: 'MISSING' }])[0].dataQuality).toBe('missing-parent')
    const cyclic = buildStakeholderForest([{ ...rows[0], reportsToContactId: 'CON-002' }, rows[1]])
    expect(cyclic).toHaveLength(2)
    expect(cyclic.every((node) => node.dataQuality === 'cycle')).toBe(true)
  })

  it('rejects self and circular reporting lines', () => {
    expect(() => validateReportingLine(rows, 'CON-001', 'CON-001')).toThrowError(/不能汇报给自己/)
    expect(() => validateReportingLine(rows, 'CON-001', 'CON-003')).toThrowError(/循环汇报/)
  })

  it('rejects a reporting parent from another account', () => {
    const otherAccountParent = { ...rows[0], id: 'CON-OTHER', accountId: 'ACC-002' }
    expect(() => validateReportingLine([...rows, otherAccountParent], 'CON-002', 'CON-OTHER')).toThrowError(/同一客户/)
  })
})
