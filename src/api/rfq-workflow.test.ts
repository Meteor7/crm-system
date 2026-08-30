import { describe, expect, it } from 'vitest'
import { createMockApi } from './mock-adapter'
import { createMemorySalesRepository } from '@/demo/sales-repository'
import type { MultipartFilePart } from './binary-transport'

function pdf(name = 'customer-rfq.pdf'): MultipartFilePart {
  const blob = new Blob(['%PDF-1.7 mock'], { type: 'application/pdf' })
  return { blob, fileName: name, mimeType: 'application/pdf', size: blob.size }
}

describe('RFQ workflow', () => {
  it('enforces role scope, revision approval, and the Opportunity quotation gate', async () => {
    const repository = createMemorySalesRepository()
    const opportunity = repository.snapshot.opportunities.find((item) => item.owner === 'person002@crm.example.invalid')!
    opportunity.stage = '预算审批'
    repository.save()

    const sales = createMockApi({ latency: 0, role: 'Sales', userId: 'person002@crm.example.invalid', salesRepository: repository })
    const otherSales = createMockApi({ latency: 0, role: 'Sales', userId: 'person005@crm.example.invalid', salesRepository: repository })
    const engineer = createMockApi({ latency: 0, role: 'Engineer', userId: 'person077@crm.example.invalid', salesRepository: repository })
    const otherEngineer = createMockApi({ latency: 0, role: 'Engineer', userId: 'person053@crm.example.invalid', salesRepository: repository })
    const manager = createMockApi({ latency: 0, role: 'Manager', userId: 'person029@crm.example.invalid', salesRepository: repository })

    const specified = await sales.updateStrategyOpportunity(opportunity.id, { stage: '设备规格确认' })
    expect(specified.data.stage).toBe('设备规格确认')
    await expect(sales.updateStrategyOpportunity(opportunity.id, { stage: '报价' })).rejects.toMatchObject({ code: 'INVALID_TRANSITION' })
    const created = await sales.createRfq({ opportunityId: opportunity.id, engineerId: 'person077@crm.example.invalid', note: 'Customer specification' }, pdf())
    expect(created.data.status).toBe('Engineer Review')
    await expect(sales.createRfq({ opportunityId: opportunity.id, engineerId: 'person077@crm.example.invalid' }, pdf('duplicate.pdf'))).rejects.toMatchObject({ code: 'CONFLICT' })
    expect((await engineer.listRfqs()).data.items).toHaveLength(1)
    expect((await manager.listRfqs()).data.items).toHaveLength(1)
    expect((await otherSales.listRfqs()).data.items).toHaveLength(0)
    expect((await otherEngineer.listRfqs()).data.items).toHaveLength(0)

    await expect(sales.updateStrategyOpportunity(opportunity.id, { stage: '报价' })).rejects.toMatchObject({ code: 'INVALID_TRANSITION' })
    const commented = await engineer.submitRfqEngineerComment(created.data.id, 'Specification is feasible.', created.data.modified)
    expect(commented.data.status).toBe('Manager Approval')
    await expect(engineer.downloadRfqFile(created.data.id)).rejects.toMatchObject({ code: 'PERMISSION_DENIED' })

    const returned = await manager.reviewRfq(created.data.id, { decision: 'Returned', comment: 'Use the revised customer sheet.' }, commented.data.modified)
    expect(returned.data.status).toBe('Sales Revision')
    const revised = await sales.reviseRfq(created.data.id, pdf('customer-rfq-r2.pdf'), returned.data.modified)
    expect(revised.data.versions).toHaveLength(2)
    expect(revised.data.currentVersion.engineerComment).toBe('')
    expect(revised.data.versions[1].engineerComment).toBe('Specification is feasible.')

    const recommmented = await engineer.submitRfqEngineerComment(created.data.id, 'Revised specification confirmed.', revised.data.modified)
    const approved = await manager.reviewRfq(created.data.id, { decision: 'Approved', comment: '' }, recommmented.data.modified)
    expect(approved.data.status).toBe('Approved')
    await expect(sales.reviseRfq(created.data.id, pdf('late-change.pdf'), approved.data.modified)).rejects.toMatchObject({ code: 'INVALID_TRANSITION' })

    expect((await sales.getStrategyOpportunity(opportunity.id)).data.stage).toBe('报价')
  })
})
