import { describe, expect, it } from 'vitest'
import { accounts, actions, bookings, demoRequests, evaluations, opportunities, requirements } from '@/api/mock-data'
import { buildManagementDashboard } from './dashboard'
import { addMoney } from './money'

describe('management dashboard aggregation', () => {
  const dashboard = buildManagementDashboard({
    asOf: '2026-07-17 10:30', accounts, actions, bookings,
    demoRequests, evaluations, opportunities, requirements, visits: [],
  })

  it('uses opportunity and booking records as the source of truth', () => {
    expect(dashboard.kpis.moneyByCurrency).toEqual([{
      currency: 'CNY', openPipeline: '97100000.00', weightedPipeline: '69219000.00',
      confirmedBooking: '22400000.00', cumulativeWon: '18800000.00',
    }])
  })

  it('groups bookings by their real booking date', () => {
    expect(dashboard.bookingByMonth).toEqual([
      { label: '2026-06', currency: 'CNY', amount: '3600000.00', count: 1 },
      { label: '2026-07', currency: 'CNY', amount: '18800000.00', count: 1 },
    ])
  })

  it('builds traceable owner, customer and process breakdowns', () => {
    expect(dashboard.ownerPerformance.map((item) => item.owner)).toEqual(['Demo Staff 01', 'Demo Staff 02'])
    expect(dashboard.topAccounts.find((item) => item.accountId === 'ACC-002')).toMatchObject({ currency: 'CNY', pipeline: '32500000.00' })
    expect(dashboard.attentionAccounts.find((item) => item.id === 'ACC-002')?.pipelineAmount).toBe(0)
    expect(addMoney(dashboard.segmentDistribution.map((item) => item.pipeline))).toBe('97100000.00')
    expect(dashboard.process.requirementsByStatus.reduce((sum, item) => sum + item.count, 0)).toBe(requirements.length)
    expect(dashboard.process.demoByStatus.reduce((sum, item) => sum + item.count, 0)).toBe(demoRequests.length)
    expect(dashboard.process.demoByPriority.reduce((sum, item) => sum + item.count, 0)).toBe(demoRequests.length)
    expect(dashboard.process.evaluationRunResults.reduce((sum, item) => sum + item.count, 0)).toBe(evaluations.flatMap((item) => item.runs).length)
    expect(dashboard.kpis).not.toHaveProperty('contractsAtRisk')
    expect(dashboard.process).not.toHaveProperty('contractsByStatus')
    expect(dashboard.process).not.toHaveProperty('contractsByType')
    expect(dashboard.process).not.toHaveProperty('contractsByRisk')
    expect(dashboard.deliveryAlerts).not.toContainEqual(expect.objectContaining({ type: 'Contract' }))
  })
})
