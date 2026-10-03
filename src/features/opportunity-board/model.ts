import type { Locale } from '@/i18n'
import { opportunityStageLabel } from '@/domain/opportunity-stages'
import { opportunityProbabilityLevelLabel } from '@/domain/opportunity-probability'
import { regionDepth, regionLabel } from '@/domain/regions'
import type { BoardColumn, BoardCondition, BoardDefinition, BoardField, BoardFilters, BoardGroup, BoardOperator, BoardQuery, BoardRow } from './types'

export const columnLabels: Record<BoardColumn | 'stageAgeDays', [string, string]> = {
  customerName: ['Customer', '客户'], title: ['Opportunity', '商机名称'], region: ['Region', '区域'],
  sales: ['Sales rep', '销售'], stage: ['Stage', '阶段'], stageChangedAt: ['Last stage change', '最后阶段变更'],
  stageAgeDays: ['Days in stage', '阶段停留天数'], probabilityLevel: ['Probability', '概率档位'],
  equipment: ['Equipment', '设备'], market: ['Market', '市场'], amount: ['Original amount', '原币金额'],
  amountCny: ['Value · CNY', '金额 · 人民币'], nextAction: ['Next action', '下一步行动'],
}
export const fields: BoardField[] = ['stage', 'region', 'stageChangedAt', 'sales', 'probabilityLevel', 'equipment', 'market', 'customerName', 'stageAgeDays', 'amountCny']
export const groupFields: BoardGroup[] = ['region', 'sales', 'stage', 'probabilityLevel', 'equipment', 'market']
export const defaultColumns: BoardColumn[] = ['customerName', 'region', 'sales', 'stage', 'stageChangedAt', 'probabilityLevel', 'equipment', 'market', 'amountCny', 'nextAction']
export const allColumns: BoardColumn[] = ['customerName', 'title', 'region', 'sales', 'stage', 'stageChangedAt', 'probabilityLevel', 'equipment', 'market', 'amountCny', 'amount', 'nextAction']
export const operatorLabels: Record<BoardOperator, [string, string]> = {
  in: ['is any of', '属于'], not_in: ['is none of', '不属于'], contains: ['contains', '包含'],
  before: ['before', '早于'], after: ['after', '晚于'], between: ['between (inclusive)', '介于（含两端）'],
  gt: ['greater than', '大于'], gte: ['at least', '大于或等于'], lt: ['less than', '小于'], lte: ['at most', '小于或等于'],
}
export const text = (pair: [string, string], locale: Locale) => pair[locale === 'en-US' ? 0 : 1]
export const fieldLabel = (field: BoardColumn | 'stageAgeDays', locale: Locale) => text(columnLabels[field], locale)
export function operators(field: BoardField): BoardOperator[] {
  if (field === 'customerName') return ['contains']
  if (field === 'stageChangedAt') return ['after', 'before', 'between']
  if (field === 'stageAgeDays') return ['gt', 'gte', 'lt', 'lte']
  if (field === 'amountCny') return ['gt', 'gte', 'lt', 'lte', 'between']
  return ['in', 'not_in']
}
export function condition(field: BoardField = 'stage'): BoardCondition {
  const operator = operators(field)[0]
  return { field, operator, value: operator === 'in' ? [] : field === 'stageAgeDays' ? 21 : '' }
}
export function defaultDefinition(): BoardDefinition {
  return { scope: { sales: [], regions: [], markets: [], equipment: [] }, match: 'all', conditions: [],
    sort: { field: 'stageChangedAt', direction: 'asc' }, groupBy: null, columns: [...defaultColumns] }
}
export function toQuery(definition: BoardDefinition, page = 1, pageSize = 25): BoardQuery {
  const { columns: _columns, ...query } = definition
  return JSON.parse(JSON.stringify({ ...query, page, pageSize }))
}
export function optionLabel(field: string, value: string, label: string, locale: Locale) {
  if (field === 'stage') return opportunityStageLabel(value, locale)
  if (field === 'probabilityLevel') return value === 'pending' ? text(['Pending confirmation', '待确认'], locale) : opportunityProbabilityLevelLabel(value, locale)
  if (field === 'region') return regionLabel(value, locale)
  return label
}
export function fieldOptions(field: BoardField, filters: BoardFilters, locale: Locale) {
  const choices: Partial<Record<BoardField, BoardFilters['stages']>> = { stage: filters.stages, probabilityLevel: filters.probabilityLevels, sales: filters.sales, region: filters.regions, market: filters.markets, equipment: filters.equipment }
  return (choices[field] ?? []).map(o => {
    const option = { value: o.value, label: optionLabel(field, o.value, o.label, locale) }
    // Regions are listed as the sales territory tree; a value below a territory is indented under it.
    const depth = field === 'region' ? regionDepth(o.value, filters.regionParents) : 0
    return depth ? { ...option, depth } : option
  })
}
export function validateDefinition(d: BoardDefinition, filters: BoardFilters, locale: Locale): string {
  const say = (en: string, zh: string) => text([en, zh], locale)
  if (!filters.regionReady && (d.scope.regions.length || d.groupBy === 'region' || d.conditions.some(c => c.field === 'region'))) return say('Region data is not ready. Remove the region filter or grouping.', '区域数据尚未就绪，请移除区域筛选或分组。')
  for (const [i, c] of d.conditions.entries()) {
    const prefix = say(`Condition ${i + 1}: `, `条件 ${i + 1}：`)
    if (c.operator === 'in' || c.operator === 'not_in') {
      if (!Array.isArray(c.value) || !c.value.length) return prefix + say('select at least one value.', '请至少选择一个值。')
    } else if (c.field === 'stageAgeDays') {
      if (typeof c.value !== 'number' || !Number.isInteger(c.value) || c.value < 0 || c.value > 36500) return prefix + say('enter a whole number from 0 to 36500.', '请输入 0–36500 的整数。')
    } else {
      const values = Array.isArray(c.value) ? c.value : [String(c.value)]
      if (values.some(v => !v.trim()) || (c.operator === 'between' && values.length !== 2)) return prefix + say('complete the value.', '请补全条件值。')
      if (c.field === 'amountCny' && values.some(v => !/^\d+(\.\d{1,2})?$/.test(v))) return prefix + say('enter a non-negative amount with up to two decimals.', '请输入非负金额，最多两位小数。')
      if (c.operator === 'between' && (c.field === 'amountCny' ? Number(values[0]) > Number(values[1]) : values[0] > values[1])) return prefix + say('the start must not exceed the end.', '起始值不能大于结束值。')
    }
  }
  return ''
}
export const presets = [
  { id: 'demo', label: ['Demo done', 'Demo 已完成'] as [string, string], conditions: [{ field: 'stage', operator: 'in', value: ['demo_done'] }] as BoardCondition[] },
  { id: 'stalled', label: ['Demo > 21 days', 'Demo 阶段超过 21 天'] as [string, string], conditions: [{ field: 'stage', operator: 'in', value: ['demo_done'] }, { field: 'stageAgeDays', operator: 'gt', value: 21 }] as BoardCondition[] },
  { id: 'committed', label: ['Committed · awaiting PO', 'Committed · 待 PO'] as [string, string], conditions: [{ field: 'probabilityLevel', operator: 'in', value: ['committed'] }, { field: 'stage', operator: 'in', value: ['qualified_opportunity', 'demo_done', 'customer_budget_approved', 'rfq_validated', 'quotation_sent', 'internal_validation'] }] as BoardCondition[] },
  { id: 's6', label: ['Stage 6 · awaiting PO', 'S6 · 待 PO'] as [string, string], conditions: [{ field: 'stage', operator: 'in', value: ['internal_validation'] }] as BoardCondition[] },
]
export function groupKey(row: BoardRow, group: BoardGroup): string | null {
  return group === 'sales' ? row.salesId : group === 'probabilityLevel' ? row.probabilityLevel ?? 'pending' : row[group]
}
export function money(value: string | null, locale: Locale) {
  return value == null ? '—' : '¥' + Number(value).toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
export function dateText(value: string | null, locale: Locale) {
  return value ? new Date(value).toLocaleDateString(locale, { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }) : '—'
}
export function cellText(row: BoardRow, column: BoardColumn, locale: Locale): string {
  if (column === 'stage') return opportunityStageLabel(row.stage, locale)
  if (column === 'probabilityLevel') return optionLabel(column, row.probabilityLevel ?? 'pending', '', locale)
  if (column === 'region') return row.region ? regionLabel(row.region, locale) : '—'
  if (column === 'sales') return row.salesName
  if (column === 'stageChangedAt') return dateText(row.stageChangedAt, locale) + (row.stageAgeDays == null ? '' : ` · ${row.stageAgeDays} ${text(['d', '天'], locale)}`)
  if (column === 'amountCny') return money(row.amountCny, locale)
  // A not-entered amount is a dash like a missing CNY amount, never "CNY 0.00".
  if (column === 'amount') return Number(row.amount) > 0 ? `${row.currency} ${row.amount}` : '—'
  if (column === 'nextAction') return row.nextAction ? [row.nextAction.title, row.nextAction.due].filter(Boolean).join(' · ') : '—'
  return row[column] || '—'
}
