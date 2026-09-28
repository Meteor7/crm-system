import type { Locale } from '@/i18n'
import type { Tone } from '@/types/crm'
import {
  OPPORTUNITY_PROBABILITY_LEVELS,
  type OpportunityProbabilityLevel,
  type OpportunityProbabilityLevelFilter,
  type OpportunityProbabilityLevelValue,
} from '@/types/workspaces'

export { OPPORTUNITY_PROBABILITY_LEVELS } from '@/types/workspaces'
export type { OpportunityProbabilityLevel, OpportunityProbabilityLevelFilter, OpportunityProbabilityLevelValue } from '@/types/workspaces'

/** List filter value for Opportunities whose owner has not set a level yet. */
export const PENDING_PROBABILITY_LEVEL_FILTER = 'pending'

// Level copy stays apart from salesEnumLabel, where "Pipeline" is the retired forecast and "Low" is stakeholder influence.
const PROBABILITY_LEVEL_LABELS: Record<OpportunityProbabilityLevelValue, Record<Locale, string>> = {
  low_probability: { 'zh-CN': '低', 'en-US': 'Low probability' },
  pipeline: { 'zh-CN': '在途', 'en-US': 'Pipeline' },
  upside: { 'zh-CN': '有望', 'en-US': 'Upside' },
  committed: { 'zh-CN': '确定', 'en-US': 'Committed' },
  '': { 'zh-CN': '待销售确认', 'en-US': 'Pending sales confirmation' },
}

const PROBABILITY_LEVEL_TONES: Record<OpportunityProbabilityLevelValue, Tone> = {
  low_probability: 'danger',
  pipeline: 'info',
  upside: 'warning',
  committed: 'positive',
  '': 'neutral',
}

export function isOpportunityProbabilityLevel(value: unknown): value is OpportunityProbabilityLevel {
  return typeof value === 'string' && (OPPORTUNITY_PROBABILITY_LEVELS as readonly string[]).includes(value)
}

/** A stored level is valid when it is one of the four levels or empty (pending sales confirmation). */
export function isOpportunityProbabilityLevelValue(value: unknown): value is OpportunityProbabilityLevelValue {
  return value === '' || isOpportunityProbabilityLevel(value)
}

/** Orders levels from low to high: pending is 0, then low_probability 1 through committed 4. */
export function opportunityProbabilityLevelRank(level: OpportunityProbabilityLevelValue) {
  return level ? OPPORTUNITY_PROBABILITY_LEVELS.indexOf(level) + 1 : 0
}

export function opportunityProbabilityLevelLabel(level: string, locale: Locale) {
  return isOpportunityProbabilityLevelValue(level) ? PROBABILITY_LEVEL_LABELS[level][locale] : level
}

export function opportunityProbabilityLevelTone(level: string): Tone {
  return isOpportunityProbabilityLevelValue(level) ? PROBABILITY_LEVEL_TONES[level] : 'neutral'
}

/** Reads a list filter from untrusted input such as the route query; anything unknown means All. */
export function normalizeOpportunityProbabilityLevelFilter(value: unknown): OpportunityProbabilityLevelFilter {
  if (value === PENDING_PROBABILITY_LEVEL_FILTER) return PENDING_PROBABILITY_LEVEL_FILTER
  return isOpportunityProbabilityLevel(value) ? value : 'All'
}

export function matchesOpportunityProbabilityLevelFilter(level: OpportunityProbabilityLevelValue, filter?: OpportunityProbabilityLevelFilter) {
  if (!filter || filter === 'All') return true
  return filter === PENDING_PROBABILITY_LEVEL_FILTER ? level === '' : level === filter
}
