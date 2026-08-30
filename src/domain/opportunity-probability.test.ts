import { describe, expect, it } from 'vitest'
import { calculateOpportunityProbability, opportunityProbabilityExplanation } from './opportunity-probability'

describe('Opportunity purchase-intent probability', () => {
  it.each([
    ['需求发现', 50, 29],
    ['Wafer Demo确认', 80, 65],
    ['预算审批', 80, 74],
    ['设备规格确认', 80, 77],
    ['报价', 80, 80],
    ['采购流程', 86, 88],
  ] as const)('combines the %s stage base with purchase intent', (stage, intent, expected) => {
    expect(calculateOpportunityProbability(stage, intent)).toBe(expected)
  })

  it('keeps closed opportunities fixed regardless of purchase intent', () => {
    expect(calculateOpportunityProbability('Won', 0)).toBe(100)
    expect(calculateOpportunityProbability('Lost', 100)).toBe(0)
  })

  it('bounds the output for canonical stages', () => {
    expect(calculateOpportunityProbability('需求发现', -500)).toBe(0)
    expect(calculateOpportunityProbability('采购流程', 500)).toBe(100)
  })

  it('explains the two inputs used by the calculation', () => {
    expect(opportunityProbabilityExplanation('采购流程', 86)).toBe('阶段基础概率 90% × 60% + 购买意愿 86 × 40%')
  })
})
