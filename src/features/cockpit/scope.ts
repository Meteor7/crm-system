// One navigation contract for the cockpit tabs (Review, Warnings, Plan, Opportunities).
// The global scope is a single value per dimension (empty = all), plus the period granularity and the anchor of the
// Review period. Review and Warnings query that Review period; Plan queries the next period of the same granularity,
// derived here once, and keeps the Review anchor as `reviewAnchor` so every way back restores it.
// Dates are business dates (YYYY-MM-DD) on the Shanghai calendar with ISO (Monday) weeks, as in the backend.
import type { LocationQuery } from 'vue-router'
import type { BoardScope } from '@/features/opportunity-board/types'
import type { PeriodKind } from './types'

export type ScopeKey = 'sales' | 'region' | 'market' | 'equipment'
export type CockpitScope = Record<ScopeKey, string>
export interface CockpitContext extends CockpitScope { period: PeriodKind; reviewAnchor: string }
export type CockpitPage = 'review' | 'warnings' | 'plan' | 'board'
export interface CockpitRoute { path: string; query: Record<string, string> }

// URL order; Review and Warnings have always written the scope in this order.
export const scopeKeys: readonly ScopeKey[] = ['sales', 'market', 'region', 'equipment']
export const periodKinds: readonly PeriodKind[] = ['week', 'month', 'quarter', 'year']
// Opportunities keeps a multi-select list per dimension under a plural name.
const boardKeys: Record<ScopeKey, keyof BoardScope> = { sales: 'sales', region: 'regions', market: 'markets', equipment: 'equipment' }
const paths: Record<CockpitPage, string> = { review: '/dashboard', warnings: '/warnings', plan: '/plan', board: '/opportunity-board' }

function parseDay(value: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  const date = new Date(`${value}T00:00:00Z`)
  return Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== value ? null : date
}
const dayText = (date: Date) => date.toISOString().slice(0, 10)
export const isBusinessDate = (value: string) => parseDay(value) !== null

// Today on the Shanghai calendar: at 17:00 UTC it is already tomorrow there.
export function shanghaiDate(now = new Date()): string {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' })
    .formatToParts(now).map(part => [part.type, part.value]))
  return `${parts.year}-${parts.month}-${parts.day}`
}

// First day of the period containing a business date; '' for anything that is not one.
export function periodStartOf(period: PeriodKind, value: string): string {
  const date = parseDay(value)
  if (!date) return ''
  if (period === 'week') date.setUTCDate(date.getUTCDate() - (date.getUTCDay() + 6) % 7)
  else date.setUTCDate(1)
  if (period === 'quarter') date.setUTCMonth(Math.floor(date.getUTCMonth() / 3) * 3)
  if (period === 'year') date.setUTCMonth(0)
  return dayText(date)
}
function shiftPeriod(period: PeriodKind, value: string, step: 1 | -1): string {
  const start = periodStartOf(period, value)
  if (!start) return ''
  const date = new Date(`${start}T00:00:00Z`)
  if (period === 'week') date.setUTCDate(date.getUTCDate() + 7 * step)
  else date.setUTCMonth(date.getUTCMonth() + { month: 1, quarter: 3, year: 12 }[period] * step)
  return dayText(date)
}
// First day of the period after / before the one containing the date.
export const nextPeriodAfter = (period: PeriodKind, value: string) => shiftPeriod(period, value, 1)
export const previousPeriodBefore = (period: PeriodKind, value: string) => shiftPeriod(period, value, -1)

// What Review shows without an anchor (backend: Monday of last week, whatever the granularity).
export function defaultReviewAnchor(now = new Date()): string {
  return previousPeriodBefore('week', shanghaiDate(now))
}

const text = (query: LocationQuery, key: string) => typeof query[key] === 'string' ? (query[key] as string).trim() : ''
export function pickScope(source: Partial<Record<ScopeKey, string | undefined>>): CockpitScope {
  return { sales: source.sales ?? '', region: source.region ?? '', market: source.market ?? '', equipment: source.equipment ?? '' }
}
// Incoming query of any cockpit page. A repeated or blank value is no value; the backend validates the rest.
export function readCockpitQuery(query: LocationQuery) {
  const period = text(query, 'period')
  return {
    scope: pickScope(Object.fromEntries(scopeKeys.map(key => [key, text(query, key)]))),
    period: periodKinds.includes(period as PeriodKind) ? period as PeriodKind : null,
    anchor: text(query, 'anchor'),
    reviewAnchor: text(query, 'reviewAnchor'),
  }
}
export type CockpitQuery = ReturnType<typeof readCockpitQuery>

// Plan's own period: an explicit anchor already names the Plan period and is never advanced again;
// otherwise the period after the Review anchor, or after today (Shanghai) without any context.
export function planStart(incoming: CockpitQuery, now = new Date()): { period: PeriodKind; anchor: string } {
  const period = incoming.period ?? 'week'
  const anchor = isBusinessDate(incoming.anchor) ? incoming.anchor
    : isBusinessDate(incoming.reviewAnchor) ? nextPeriodAfter(period, incoming.reviewAnchor) : nextPeriodAfter(period, shanghaiDate(now))
  return { period, anchor }
}
// The Review period that belongs to the Plan period on show: the originating Review anchor while Plan still shows
// the period right after it, otherwise the preceding period of Plan's granularity. Review and Warnings refuse a
// period that has not started yet, so when Plan is paged two or more periods ahead this stays on the current period.
export function reviewAnchorForPlan(period: PeriodKind, planAnchor: string, retained: string, now = new Date()): string {
  const current = periodStartOf(period, shanghaiDate(now))
  const planPeriod = periodStartOf(period, planAnchor)
  // Plan's date is unusable (a cleared field): keep the originating Review anchor only if that period has started.
  if (!planPeriod) return isBusinessDate(retained) && periodStartOf(period, retained) <= current ? retained : ''
  const belonging = isBusinessDate(retained) && nextPeriodAfter(period, retained) === planPeriod ? retained : previousPeriodBefore(period, planPeriod)
  // Only a period that really has not started is cut back; a date inside the current period stays as it was.
  return periodStartOf(period, belonging) > current ? current : belonging
}

export function cockpitRoute(page: CockpitPage, context: CockpitContext): CockpitRoute {
  const planAnchor = page === 'plan' ? nextPeriodAfter(context.period, context.reviewAnchor) : ''
  const period: Record<string, string> = page === 'plan'
    ? { anchor: planAnchor, reviewAnchor: planAnchor ? context.reviewAnchor : '' }
    : page === 'board' ? { reviewAnchor: context.reviewAnchor } : { anchor: context.reviewAnchor }
  const query = { period: context.period, ...period, ...Object.fromEntries(scopeKeys.map(key => [key, context[key]])) }
  return { path: paths[page], query: Object.fromEntries(Object.entries(query).filter(([, value]) => value)) }
}

// Opportunities: a global single value becomes a one-element list.
export function toBoardScope(scope: CockpitScope): BoardScope {
  const result: BoardScope = { sales: [], regions: [], markets: [], equipment: [] }
  for (const key of scopeKeys) if (scope[key]) result[boardKeys[key]] = [scope[key]]
  return result
}
// Back from Opportunities: a list of one is that value, none is all. More than one value cannot be expressed on the
// other pages; those dimensions are reported so the caller withholds navigation instead of widening to all.
export function fromBoardScope(scope: BoardScope): { scope: CockpitScope; blocked: ScopeKey[] } {
  const result = pickScope({}), blocked: ScopeKey[] = []
  for (const key of ['sales', 'region', 'market', 'equipment'] as const) {
    const values = [...new Set(scope[boardKeys[key]])]
    if (values.length > 1) blocked.push(key)
    else result[key] = values[0] ?? ''
  }
  return { scope: result, blocked }
}
