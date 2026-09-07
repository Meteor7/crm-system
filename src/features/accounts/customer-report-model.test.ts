import { describe, expect, it } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { buildCustomerReportModel, type CustomerWorkbookSpec } from './customer-report-model'

function values(spec: CustomerWorkbookSpec, sheetName: string) {
  return spec.sheets.find((sheet) => sheet.name === sheetName)?.rows.flat().map((cell) => cell?.v) ?? []
}

describe('customer report model', () => {
  it('builds the five prototype sheets from the selected account only', async () => {
    const detail = (await createMockApi({ latency: 0 }).getAccount360('ACC-001')).data
    const spec = buildCustomerReportModel(detail, '2026-07-17')

    expect(spec.sheets.map((sheet) => sheet.name)).toEqual([
      '客户全貌 Overview', '商机 Opportunities', '需求与行动 Actions', '关键人与拜访 People', 'Demo与合同 Demo',
    ])
    expect(spec.fileName).toMatch(/^CUSTOMER06_Customer_360_2026-07-17\.xlsx$/)
    expect(values(spec, '客户全貌 Overview')).toContain('Confirmed Booking')
    expect(values(spec, '客户全貌 Overview')).toContain('CNY 16,800,000.00')
    expect(values(spec, '关键人与拜访 People')).toContain('演示员工36')
    expect(values(spec, '关键人与拜访 People')).toContain('V-001')
    expect(values(spec, '关键人与拜访 People')).toContain('—')
    expect(values(spec, '商机 Opportunities')).not.toContain('示例企业027有限公司')
  })

  it('stores percentages as numeric decimals and current detail counts as numbers', async () => {
    const detail = (await createMockApi({ latency: 0 }).getAccount360('ACC-001')).data
    const spec = buildCustomerReportModel(detail, '2026-07-17')
    const percentageCells = spec.sheets
      .flatMap((sheet) => sheet.rows.flat())
      .filter((cell) => cell?.s === 7)
    const dateCells = spec.sheets.flatMap((sheet) => sheet.rows.flat()).filter((cell) => cell?.s === 12)

    expect(percentageCells.some((cell) => typeof cell?.v === 'number' && cell.v > 0 && cell.v < 1)).toBe(true)
    expect(dateCells.some((cell) => typeof cell?.v === 'number' && cell.v > 45_000)).toBe(true)
    expect(values(spec, '客户全貌 Overview')).toContain(detail.contacts.length)
  })

  it('deduplicates equivalent actions and includes opportunity next actions', async () => {
    const detail = (await createMockApi({ latency: 0 }).getAccount360('ACC-001')).data
    const spec = buildCustomerReportModel(detail, '2026-07-17')
    const actionValues = values(spec, '需求与行动 Actions')
    const actionRows = spec.sheets.find((sheet) => sheet.name === '需求与行动 Actions')?.rows ?? []
    const queueStart = actionRows.findIndex((row) => row.some((cell) => cell?.v === '统一行动队列 / Consolidated Action Queue'))
    const queueValues = actionRows.slice(queueStart).flat().map((cell) => cell?.v)
    expect(queueValues.filter((value) => value === '确认 Demo wafer 与验收阈值')).toHaveLength(1)
    expect(actionValues).toContain('商机 / Opportunity')
    expect(actionValues).toContain('确认第二批样片物流')
  })
})


it('uses English report labels and generated risk copy while preserving business data', async () => {
  const detail = (await createMockApi({ latency: 0 }).getAccount360('ACC-001')).data
  const empty = { ...detail, account: { ...detail.account, name: 'Acme', city: 'Shanghai', region: 'East', owner: 'Sales', risk: '高风险' as const, nextAction: 'Follow up' }, sites: [], contacts: [], requirements: [], opportunities: [], bookings: [], actions: [], visits: [], demoRequests: [], evaluations: [], contracts: [] }
  const report = buildCustomerReportModel(empty, '2026-09-07', 'en-US')
  expect(report.sheets.map(sheet => sheet.name)).toEqual(['Overview', 'Opportunities', 'Actions', 'People', 'Demo and contracts'])
  for (const sheet of report.sheets) for (const cell of sheet.rows.flat()) expect(String(cell.v)).not.toMatch(/\p{Script=Han}/u)
  const businessText = '当前规则未识别到异常'
  empty.account.name = businessText
  empty.account.nextAction = businessText
  const original = structuredClone(empty)
  expect(buildCustomerReportModel(empty, '2026-09-07', 'en-US').sheets[0].rows.flat().map(cell => cell.v)).toContain(businessText)
  expect(empty).toEqual(original)
})


it('uses English generated booking titles in reports without modifying the booking', async () => {
  const detail = (await createMockApi({ latency: 0 }).getAccount360('ACC-001')).data
  detail.bookings = [{ id: 'B-1', accountId: 'ACC-001', accountName: 'Acme', primaryContactId: 'CON-001', customerContact: 'Customer', amount: '1000.00', currency: 'CNY', bookingDate: '2026-09-07', owner: 'Sales', source: 'Upsell', sourceOpportunityId: '', note: '', ddl: '2026-10-01', equipment: 'Tool X', quantity: 2, bookingType: 'Equipment', title: 'Tool X · 2 台', status: 'Confirmed' }]
  const reportValues = values(buildCustomerReportModel(detail, '2026-09-07', 'en-US'), 'Opportunities')
  expect(reportValues).toContain('Tool X · 2 units')
  expect(reportValues).not.toContain('Tool X · 2 台')
  expect(detail.bookings[0].title).toBe('Tool X · 2 台')
})
