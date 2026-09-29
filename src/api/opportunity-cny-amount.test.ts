import { describe, expect, it } from 'vitest'
import { createMemorySalesRepository } from '@/demo/sales-repository'
import { createMockApi } from './mock-adapter'

const input = {
  accountId: 'ACC-001', siteId: 'SITE-001', title: 'Priced in USD', owner: 'person002@crm.example.invalid', amount: '30000.00',
  intentScore: 50, poDate: '2026-12-31', toolType: 'AOI', saleType: 'New Equipment', subRegion: 'East China', currency: 'USD',
  probabilityLevel: 'pipeline' as const, qualificationConfirmed: true, amountCny: '213000.5',
}

function cachedWithoutCnyAmounts() {
  const cached = structuredClone(createMemorySalesRepository().snapshot)
  cached.opportunities.forEach((item) => { delete (item as { amountCny?: string }).amountCny })
  return cached
}

describe('mock Opportunity amount in CNY', () => {
  it('requires a positive CNY amount on every new Opportunity and stores it normalized', async () => {
    const api = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01' })

    await expect(api.createStrategyOpportunity({ ...input, amountCny: '' }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR', fieldErrors: { amountCny: 'Required' } })
    for (const amountCny of ['0', '-5', '1.234', 'abc']) {
      await expect(api.createStrategyOpportunity({ ...input, amountCny }))
        .rejects.toMatchObject({ code: 'VALIDATION_ERROR', fieldErrors: { amountCny: 'Invalid amount' } })
    }

    const created = (await api.createStrategyOpportunity(input)).data
    expect(created).toMatchObject({ currency: 'USD', amount: '30000.00', amountCny: '213000.50' })
  })

  it('asks for the CNY amount before any other edit of an Opportunity that has none', async () => {
    const cached = cachedWithoutCnyAmounts()
    cached.opportunities.find((item) => item.id === 'OPP-003')!.currency = 'USD'
    const api = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01', salesRepository: createMemorySalesRepository(cached) })
    expect((await api.getStrategyOpportunity('OPP-003')).data.amountCny).toBe('')

    await expect(api.updateStrategyOpportunity('OPP-003', { title: 'Renamed without CNY' }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR', fieldErrors: { amountCny: 'Required' } })

    const updated = (await api.updateStrategyOpportunity('OPP-003', { amountCny: '2200000' })).data
    expect(updated.amountCny).toBe('2200000.00')
    expect(updated.history[0]).toMatchObject({ field: 'amountCny', from: '', to: '2200000.00' })
    // Entering the same amount again is not a change.
    const again = (await api.updateStrategyOpportunity('OPP-003', { amountCny: '2200000.00' })).data
    expect(again.history.filter((entry) => entry.field === 'amountCny')).toHaveLength(1)
  })

  it('gives cached CNY Opportunities their amount once and leaves other currencies empty', () => {
    const cached = cachedWithoutCnyAmounts()
    const foreign = cached.opportunities[1]!
    foreign.currency = 'EUR'

    const migrated = createMemorySalesRepository(cached).snapshot
    const byId = new Map(migrated.opportunities.map((item) => [item.id, item]))
    expect(byId.get(foreign.id)!.amountCny).toBe('')
    migrated.opportunities.filter((item) => item.currency === 'CNY').forEach((item) => {
      expect(item.amountCny).toBe(item.amount)
    })

    const remigrated = createMemorySalesRepository(structuredClone(migrated)).snapshot
    expect(remigrated.opportunities).toEqual(migrated.opportunities)
  })

  it('requires the CNY amount when a Lead becomes an Opportunity', async () => {
    const salesRepository = createMemorySalesRepository()
    const api = createMockApi({ latency: 0, salesRepository })
    const conversion = {
      opportunityTitle: '线索转商机', opportunityAmount: '9800000.00', opportunityCloseDate: '2026-12-31',
      opportunityOwner: 'person002@crm.example.invalid', opportunityProbabilityLevel: 'pipeline' as const, toolType: 'Inspect X',
      qualificationConfirmed: true as const,
    }
    const before = salesRepository.snapshot.opportunities.length

    await expect(api.convertLead('LEAD-002', { ...conversion, opportunityAmountCny: '' }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR', fieldErrors: { opportunityAmountCny: 'Required' } })
    expect(salesRepository.snapshot.opportunities).toHaveLength(before)

    const converted = (await api.convertLead('LEAD-002', { ...conversion, opportunityAmountCny: '9800000' })).data
    expect((await api.getStrategyOpportunity(converted.opportunityId)).data.amountCny).toBe('9800000.00')
  })
})
