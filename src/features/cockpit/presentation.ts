import type { Metric, ReviewRow } from './types'

export const labels: Record<string, [string, string]> = {
  followups: ['完成报价跟进', 'Quote follow-ups completed'],
  visits_existing: ['老客户拜访', 'Existing customer visits'], visits_prospect: ['潜在客户拜访', 'Prospect visits'], visits_unclassified: ['未分类拜访', 'Unclassified visits'],
  visits: ['客户沟通', 'Customer visits'], leads: ['新增合格线索', 'New qualified leads'],
  tests: ['Demo测试完成', 'Demo Test Run'], quotes: ['首次发布报价', 'Quotes sent'], orders: ['年度订单金额', 'Annual orders'],
  qualified_opportunity: ['合格商机', 'Qualified opportunity'], demo_done: ['Demo 完成', 'Demo done'],
  customer_budget_approved: ['客户预算批准', 'Budget approved'], rfq_validated: ['RFQ 确认', 'RFQ validated'],
  quotation_sent: ['报价已发出', 'Quotation sent'], internal_validation: ['内部验证（可选）', 'Internal validation · optional'],
  po_missing_date: ['PO 日期待补录', 'PO dates to backfill'], po_missing_amount: ['人民币金额待补录', 'CNY amounts to backfill'],
  po_received: ['已收到 PO', 'PO received'],
  po: ['已收到 PO · 年累计', 'PO received · YTD'], lost: ['丢单', 'Lost'], overdue: ['行动逾期', 'Overdue actions'],
  quotation_expiry: ['报价即将到期', 'Quotes expiring soon'], warnings: ['预警', 'Warnings'],
  demo_resources: ['Demo 设备风险 · 当前', 'Demo resource risks · current'],
  close_date_slip: ['预计 PO 跨季度推迟', 'Expected PO postponed to a later quarter'],
  red_flags: ['当前未解决红旗', 'Current open red flags'],
  other_alerts: ['其他提醒', 'Other alerts'], stage6_no_po: ['第 6 阶段超期无 PO', 'Stage 6 overdue, no PO'],
  downgrade: ['待处理降档', 'Pending downgrades'], downgrade_history: ['本期降档记录', 'Downgrade history'], stalled: ['行动久未更新', 'Stalled opportunities'], losses: ['近 12 个月丢单', 'Losses · last 12 months'],
  low_probability: ['Low probability', 'Low probability'], pipeline: ['Pipeline', 'Pipeline'], upside: ['Upside', 'Upside'], committed: ['Committed', 'Committed'],
  week: ['周', 'Week'], month: ['月', 'Month'], quarter: ['季度', 'Quarter'], year: ['年', 'Year'], weekly_default: ['默认周目标', 'Default weekly target'],
  'East China': ['华东', 'East China'], 'South China': ['华南', 'South China'], 'West China': ['华西', 'West China'],
  'North China': ['华北', 'North China'], 'Central China': ['华中', 'Central China'],
}
export function metricText(metric: Metric, locale: string, money = false): string {
  const en = locale === 'en-US'
  if (metric.state !== 'ready' || metric.value === null) return { insufficient: en ? 'Insufficient data' : '数据不足', not_applicable: en ? 'N/A' : '不适用', not_set: en ? 'Not set' : '未设置', ready: '—' }[metric.state]
  return `${money ? '¥' : ''}${Number(metric.value).toLocaleString(locale, { maximumFractionDigits: money ? 2 : 0 })}`
}
export function detailRoute(row: ReviewRow) {
  if (row.kind === 'followup' && row.quotationId) return { path: `/quotations/${encodeURIComponent(row.quotationId)}`, query: row.quotationVersionId ? { version: row.quotationVersionId } : {} }
  if (row.kind === 'quotation' && row.quotationVersionId) {
    return { path: `/quotations/${encodeURIComponent(row.id)}`, query: { version: row.quotationVersionId } }
  }
  if (row.kind === 'opportunity' && row.fromLevel && row.eventId) {
    return { path: `/opportunities/${encodeURIComponent(row.id)}`, query: { probabilityEvent: row.eventId } }
  }
  const path = { visit: '/visits/', lead: '/leads/', quotation: '/quotations/', opportunity: '/opportunities/', booking: '/booking/' }[row.kind as Exclude<ReviewRow['kind'], 'test' | 'followup'>]
  return row.kind === 'test' ? { path: '/evaluations', query: { evaluationId: row.evaluationId } } : { path: `${path}${encodeURIComponent(row.id)}` }
}
const shanghaiToday = (now: Date) => new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Shanghai' }))
const localDay = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
export function nextMonday(now = new Date()) {
  const today = shanghaiToday(now)
  today.setDate(today.getDate() + ((8 - today.getDay()) % 7 || 7))
  return localDay(today)
}
// First day of the period after the one containing today (Shanghai), so Plan always opens on what comes next.
export function nextPeriodStart(period: 'week' | 'month' | 'quarter' | 'year', now = new Date()) {
  if (period === 'week') return nextMonday(now)
  const today = shanghaiToday(now), year = today.getFullYear(), month = today.getMonth()
  if (period === 'month') return localDay(new Date(year, month + 1, 1))
  if (period === 'quarter') return localDay(new Date(year, Math.floor(month / 3) * 3 + 3, 1))
  return localDay(new Date(year + 1, 0, 1))
}
export function targetStart(anchor: string, period: 'week' | 'month' | 'quarter' | 'year') {
  const date = new Date(`${anchor}T00:00:00Z`)
  if (period === 'week') date.setUTCDate(date.getUTCDate() - (date.getUTCDay() + 6) % 7)
  else date.setUTCDate(1)
  if (period === 'quarter') date.setUTCMonth(Math.floor(date.getUTCMonth() / 3) * 3)
  if (period === 'year') date.setUTCMonth(0)
  return date.toISOString().slice(0, 10)
}

// A smooth line through cumulative points: monotone cubic Hermite with d3 curveMonotoneX
// tangents, so the curve passes through every point, never rises above the next one or dips
// below the previous one, and stays flat where the data are flat.
export function monotoneCurvePath(points: { x: number; y: number }[]): string {
  const p: { x: number; y: number }[] = []
  for (const point of [...points].filter(q => Number.isFinite(q.x) && Number.isFinite(q.y)).sort((a, b) => a.x - b.x)) {
    if (p.length && point.x === p[p.length - 1].x) p[p.length - 1] = point
    else p.push(point)
  }
  const at = (value: number) => value.toFixed(1)
  if (!p.length) return ''
  if (p.length === 1) return `M${at(p[0].x)} ${at(p[0].y)}`
  if (p.length === 2) return `M${at(p[0].x)} ${at(p[0].y)}L${at(p[1].x)} ${at(p[1].y)}`
  const last = p.length - 1
  const width = Array.from({ length: last }, (_, i) => p[i + 1].x - p[i].x)
  const slope = width.map((dx, i) => (p[i + 1].y - p[i].y) / dx)
  const tangent = new Array<number>(p.length).fill(0)
  for (let i = 1; i < last; i++) {
    if (slope[i - 1] * slope[i] <= 0) continue
    const parabola = (slope[i - 1] * width[i] + slope[i] * width[i - 1]) / (width[i - 1] + width[i])
    tangent[i] = Math.sign(slope[i]) * 2 * Math.min(Math.abs(slope[i - 1]), Math.abs(slope[i]), Math.abs(parabola) / 2)
  }
  tangent[0] = (3 * slope[0] - tangent[1]) / 2
  tangent[last] = (3 * slope[last - 1] - tangent[last - 1]) / 2
  let path = `M${at(p[0].x)} ${at(p[0].y)}`
  for (let i = 0; i < last; i++) {
    const third = width[i] / 3
    path += `C${at(p[i].x + third)} ${at(p[i].y + third * tangent[i])}`
      + ` ${at(p[i + 1].x - third)} ${at(p[i + 1].y - third * tangent[i + 1])} ${at(p[i + 1].x)} ${at(p[i + 1].y)}`
  }
  return path
}
