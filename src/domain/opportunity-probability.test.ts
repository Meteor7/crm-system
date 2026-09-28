import { describe, expect, it } from 'vitest'
import type { OpportunityProbabilityLevelValue } from '@/types/workspaces'
import {
  OPPORTUNITY_PROBABILITY_LEVELS,
  isOpportunityProbabilityLevel,
  isOpportunityProbabilityLevelValue,
  matchesOpportunityProbabilityLevelFilter,
  normalizeOpportunityProbabilityLevelFilter,
  opportunityProbabilityLevelLabel,
  opportunityProbabilityLevelRank,
  opportunityProbabilityLevelTone,
} from './opportunity-probability'

describe('Opportunity success probability levels', () => {
  it('orders the four owner-set levels from low to high after pending', () => {
    const shuffled: OpportunityProbabilityLevelValue[] = ['committed', '', 'upside', 'low_probability', 'pipeline']

    expect(OPPORTUNITY_PROBABILITY_LEVELS).toEqual(['low_probability', 'pipeline', 'upside', 'committed'])
    expect([...shuffled].sort((left, right) => opportunityProbabilityLevelRank(left) - opportunityProbabilityLevelRank(right)))
      .toEqual(['', 'low_probability', 'pipeline', 'upside', 'committed'])
    expect(OPPORTUNITY_PROBABILITY_LEVELS.map((level) => opportunityProbabilityLevelRank(level))).toEqual([1, 2, 3, 4])
  })

  it('accepts only the four levels, plus empty as the stored pending value', () => {
    for (const level of OPPORTUNITY_PROBABILITY_LEVELS) {
      expect(isOpportunityProbabilityLevel(level)).toBe(true)
      expect(isOpportunityProbabilityLevelValue(level)).toBe(true)
    }
    expect(isOpportunityProbabilityLevel('')).toBe(false)
    expect(isOpportunityProbabilityLevelValue('')).toBe(true)
    for (const invalid of ['certain', 'Pipeline', 'Commit', 'pending', 88, null, undefined]) {
      expect(isOpportunityProbabilityLevelValue(invalid)).toBe(false)
    }
  })

  it('labels each level and the pending state in Chinese and English', () => {
    expect(OPPORTUNITY_PROBABILITY_LEVELS.map((level) => opportunityProbabilityLevelLabel(level, 'zh-CN'))).toEqual(['低', '在途', '有望', '确定'])
    expect(OPPORTUNITY_PROBABILITY_LEVELS.map((level) => opportunityProbabilityLevelLabel(level, 'en-US'))).toEqual(['Low probability', 'Pipeline', 'Upside', 'Committed'])
    expect(opportunityProbabilityLevelLabel('', 'zh-CN')).toBe('待销售确认')
    expect(opportunityProbabilityLevelLabel('', 'en-US')).toBe('Pending sales confirmation')
    expect(opportunityProbabilityLevelLabel('Best Case', 'en-US')).toBe('Best Case')
  })

  it('gives every level its own badge tone', () => {
    expect(['', ...OPPORTUNITY_PROBABILITY_LEVELS].map((level) => opportunityProbabilityLevelTone(level)))
      .toEqual(['neutral', 'danger', 'info', 'warning', 'positive'])
    expect(opportunityProbabilityLevelTone('Commit')).toBe('neutral')
  })

  it('reads list filters safely and matches pending to an empty level', () => {
    expect(normalizeOpportunityProbabilityLevelFilter('upside')).toBe('upside')
    expect(normalizeOpportunityProbabilityLevelFilter('pending')).toBe('pending')
    expect(normalizeOpportunityProbabilityLevelFilter('Commit')).toBe('All')
    expect(normalizeOpportunityProbabilityLevelFilter(['upside'])).toBe('All')
    expect(normalizeOpportunityProbabilityLevelFilter(undefined)).toBe('All')

    expect(matchesOpportunityProbabilityLevelFilter('', 'pending')).toBe(true)
    expect(matchesOpportunityProbabilityLevelFilter('pipeline', 'pending')).toBe(false)
    expect(matchesOpportunityProbabilityLevelFilter('pipeline', 'pipeline')).toBe(true)
    expect(matchesOpportunityProbabilityLevelFilter('upside', 'committed')).toBe(false)
    expect(matchesOpportunityProbabilityLevelFilter('', 'All')).toBe(true)
    expect(matchesOpportunityProbabilityLevelFilter('committed', undefined)).toBe(true)
  })
})
