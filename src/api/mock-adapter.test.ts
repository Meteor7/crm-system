import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMockApi } from './mock-adapter'
import type { MultipartFilePart } from './binary-transport'
import { createEmptyDemoRequestFormData } from '@/domain/demo-request-form'
import { createDemoRepository, createMemoryDemoStorage, seedDemoSnapshot } from '@/demo/demo-repository'
import { createMemorySalesRepository } from '@/demo/sales-repository'
import { createMemoryContactFileRepository } from '@/demo/contact-file-repository'
import type { ContactDto } from '@/types/crm'
import { addMoney } from '@/domain/money'

type TestDashboardMoney = { currency: string; openPipeline: string; confirmedBooking: string; cumulativeWon: string }
type TestPipelineMoney = { currency: string; openPipeline: string; confirmedBooking: string }
const cnyKpis = (dashboard: { kpis: { moneyByCurrency: TestDashboardMoney[] } }) =>
  dashboard.kpis.moneyByCurrency.find((item) => item.currency === 'CNY')!
const cnyTotals = (pipeline: { totals: TestPipelineMoney[] }) =>
  pipeline.totals.find((item) => item.currency === 'CNY')!

function multipartFile(fileName: string, content: string, mimeType = 'application/pdf'): MultipartFilePart {
  const blob = new Blob([content], { type: mimeType })
  return { fileName, mimeType, size: blob.size, blob }
}

function reportFiles(fileName: string, content: string, mimeType = 'application/pdf', expectedRound = 1) {
  return {
    internalFile: multipartFile(fileName, content, mimeType),
    externalFile: multipartFile(`customer-${fileName}`, content, mimeType),
    expectedRound,
  }
}

function completeDemoRequestForm() {
  const form = createEmptyDemoRequestFormData('person002@crm.example.invalid')
  Object.assign(form, {
    contactPerson: '王工, Process Manager, wang@example.com, +86 21 5555 1234',
    industry: 'Frontend Fab',
    demoOwner: 'person077@crm.example.invalid',
    sizeShape: '300 mm, 775 μm, notch',
    material: 'Golden wafer',
    specificRequest: 'No front-side contact',
    detectMeasure: '补齐标准样片后重新评估',
    expectedResults: 'KLARF and report PDF',
    otherTools: 'Customer tool of record',
    primaryTool: 'Macro Inspection X8',
    timing: '2026-09-01',
    keySuccessFactors: '覆盖客户缺陷库',
    internalQuestions: '确认标准样片数量',
    customerQuestions: '确认已知缺陷坐标',
  })
  form.wafers[0] = {
    slotId: '1',
    wid: 'DR-003-W01',
    waferSpecificity: '300 mm Golden wafer',
    notchFlat: 'Notch up',
    doiMetrologyItems: 'Known defects',
    resultFileProvided: 'KLARF and PDF',
  }
  return form
}

async function createEligibleDemoOpportunity(api: ReturnType<typeof createMockApi>, suffix = '') {
  return (await api.createStrategyOpportunity({
    accountId: 'ACC-001', siteId: 'SITE-001', title: `Demo Request Opportunity ${suffix || Date.now()}`,
    owner: 'person002@crm.example.invalid', qualificationConfirmed: true, probabilityLevel: 'pipeline', amount: '4860000.00', amountCny: '4860000.00',
    intentScore: 60, poDate: '2026-12-31', toolType: 'Defect Inspection', saleType: 'New Equipment',
    subRegion: 'East China', currency: 'CNY',
  })).data
}

function contactInput(overrides: Record<string, unknown> = {}) {
  return {
    accountId: 'ACC-001',
    name: 'Contact',
    title: 'Manager',
    department: 'Engineering',
    relationship: 'Developing' as const,
    owner: 'person002@crm.example.invalid',
    status: 'Active' as const,
    ...overrides,
  }
}

function contactUpdateInput(contact: ContactDto, overrides: Record<string, unknown> = {}) {
  const { id: _id, dataQuality: _dataQuality, updatedAt: _updatedAt, modified: _modified, ...input } = contact
  return { ...input, ...overrides }
}

describe('mock CRM API', () => {
  let api: ReturnType<typeof createMockApi>

  beforeEach(() => {
    api = createMockApi({ latency: 0, role: 'Manager', today: '2026-07-17' })
  })

  it('enforces the three role data scopes from the active person', async () => {
    const manager = createMockApi({ latency: 0, role: 'Manager', userName: '演示经理01' })
    const sales = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01' })
    const engineer = createMockApi({ latency: 0, role: 'Engineer', userName: '演示员工14', assignedAccountIds: ['ACC-001', 'ACC-003'] })

    expect((await manager.listAccounts({ pageSize: 100 })).data.items).toHaveLength(7)
    expect((await sales.listAccounts({ pageSize: 100 })).data.items).toHaveLength(3)
    expect((await engineer.listAccounts({ pageSize: 100 })).data.items.map((item) => item.id)).toEqual(['ACC-001', 'ACC-003'])
  })

  it('leaves the Sites of every Account to the business API', async () => {
    await expect(createMockApi({ latency: 0 }).listAccountSites()).rejects.toMatchObject({ code: 'BACKEND_NOT_CONNECTED' })
  })

  it('keeps Public visibility limited to Account data while honoring child owners', async () => {
    const salesRepository = createMemorySalesRepository()
    salesRepository.snapshot.accounts.find((item) => item.id === 'ACC-006')!.visibility = 'Public'
    salesRepository.snapshot.opportunities.find((item) => item.accountId === 'ACC-006')!.owner = 'person034@crm.example.invalid'
    salesRepository.snapshot.bookings.find((item) => item.accountId === 'ACC-006')!.owner = 'person034@crm.example.invalid'
    salesRepository.snapshot.visits.find((item) => item.accountId === 'ACC-006')!.owner = 'person034@crm.example.invalid'
    salesRepository.snapshot.installedTools[0].salesOwner = 'person034@crm.example.invalid'
    const contactFileRepository = createMemoryContactFileRepository()
    const manager = createMockApi({ latency: 0, role: 'Manager', salesRepository, contactFileRepository })
    const sales = createMockApi({
      latency: 0, role: 'Sales', userId: 'person034@crm.example.invalid', salesRepository, contactFileRepository,
    })
    const contact = salesRepository.snapshot.contacts.find((item) => item.accountId === 'ACC-006')!
    const blob = new Blob(['private attachment'], { type: 'application/pdf' })
    await manager.uploadContactFiles(contact.id, [{ fileName: 'private.pdf', mimeType: blob.type, size: blob.size, blob }])

    expect((await sales.listAccounts({ pageSize: 100 })).data.items.map((item) => item.id)).toContain('ACC-006')
    expect((await sales.listContacts({ accountId: 'ACC-006', pageSize: 100 })).data.items.length).toBeGreaterThan(0)
    expect((await sales.listStrategyOpportunities({ accountId: 'ACC-006', pageSize: 100 })).data.items).toHaveLength(1)
    expect((await sales.listBookings({ accountId: 'ACC-006', pageSize: 100 })).data.items).toHaveLength(1)
    expect((await sales.listInstalledTools({ pageSize: 100 })).data.items.map((item) => item.id)).toContain('TOOL-001')
    expect((await sales.listVisits({ accountId: 'ACC-006', pageSize: 100 })).data.items).toHaveLength(1)
    expect((await sales.listDemoRequests({ accountId: 'ACC-006', pageSize: 100 })).data.items).toEqual([])
    expect((await sales.listEvaluations({ accountId: 'ACC-006', pageSize: 100 })).data.items).toEqual([])
    await expect(sales.listContactFiles(contact.id)).rejects.toMatchObject({ code: 'SCOPE_DENIED' })

    const account = (await sales.getAccount360('ACC-006')).data
    expect(account.contacts.length).toBeGreaterThan(0)
    expect(account.sites).toEqual([])
    expect(account.account.pipelineAmount).toBe(0)
    expect(account.account.intentScore).toBe(0)
    expect(account.account.nextAction).toBe('')

    expect(account.opportunities).toHaveLength(1)
    expect(account.bookings).toHaveLength(1)
    expect(account.demoRequests).toEqual([])
    expect(account.evaluations).toEqual([])
    expect(account.visits).toHaveLength(1)

    const contactDetail = (await sales.getContact(contact.id)).data
    expect(contactDetail.opportunities).toEqual([])
    expect(contactDetail.bookings).toHaveLength(1)
    expect(contactDetail.demoRequests).toEqual([])
    expect(contactDetail.visits).toHaveLength(1)
    expect(contactDetail.timeline.length).toBeGreaterThan(0)
  })

  it('rejects owner assignments outside the required personnel category', async () => {
    const manager = createMockApi({ latency: 0, role: 'Manager', userName: '演示员工24' })

    await expect(manager.createAccount({
      name: 'Invalid owner account', shortName: 'INVALID', segment: 'Frontend', tier: 'B', city: '上海', region: '华东', owner: 'person077@crm.example.invalid',
    })).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    await expect(manager.createVisit({
      accountId: 'ACC-001', subject: 'Invalid owner visit', date: '2026-08-03', type: 'Phone', owner: 'person053@crm.example.invalid', objective: 'Verify owner contract',
    })).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
  })

  it('rejects a non-Sales owner for Contacts and Leads', async () => {
    const manager = createMockApi({ latency: 0, role: 'Manager', userName: '演示员工24' })

    await expect(manager.createContact(contactInput({ name: 'Invalid contact owner', owner: 'person077@crm.example.invalid' })))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    await expect(manager.createLead({
      name: 'Invalid lead owner', company: 'Owner Contract Co.', title: 'Manager', phone: '13800000002',
      source: 'Other', status: 'New', owner: 'person053@crm.example.invalid', interest: 'Inspection', firstContactNote: '',
      nextAction: 'Call', nextActionDue: '2026-08-10',
    })).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
  })

  it('rejects a non-Sales owner for Opportunities and Bookings', async () => {
    const manager = createMockApi({ latency: 0, role: 'Manager', userName: '演示员工24' })
    const contact = (await manager.listContacts({ accountId: 'ACC-001', pageSize: 100 })).data.items[0]

    await expect(manager.createStrategyOpportunity({
      accountId: 'ACC-001', siteId: 'SITE-001', title: 'Invalid owner opportunity', owner: 'person077@crm.example.invalid',
      qualificationConfirmed: true, probabilityLevel: 'pipeline', amount: '1000000.00', amountCny: '1000000.00', intentScore: 30, poDate: '2026-12-31',
      toolType: 'Inspection', saleType: 'New Tool', subRegion: '华东', currency: 'CNY',
    })).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    await expect(manager.createBooking({
      accountId: 'ACC-001', primaryContactId: contact.id, equipment: 'Invalid owner tool', quantity: 1,
      ddl: '2026-12-31', amount: '1000000.00', currency: 'CNY', status: 'Pending', owner: 'person053@crm.example.invalid', source: 'Upsell',
      sourceOpportunityId: '', note: '',
    })).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
  })

  it('rejects invalid owners in Lead conversion, Visit edits and Opportunity actions', async () => {
    const manager = createMockApi({ latency: 0, role: 'Manager', userName: '演示员工24' })

    await expect(manager.convertLead('LEAD-002', {
      opportunityTitle: 'Invalid conversion owner', opportunityAmount: '1000000.00', opportunityAmountCny: '1000000.00',
      opportunityCloseDate: '2026-12-31', opportunityOwner: 'person077@crm.example.invalid', opportunityProbabilityLevel: 'pipeline', toolType: 'Inspection', qualificationConfirmed: true,
    })).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    await expect(manager.createOpportunityAction('OPP-001', {
      title: 'Invalid action owner', owner: '演示经理01', due: '2026-08-10', status: 'Open',
    })).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
  })

  it('keeps confirmed booking separate from open pipeline', async () => {
    const dashboard = await api.getDashboard({ range: 'quarter' })

    const kpis = cnyKpis(dashboard.data)
    expect(BigInt(kpis.openPipeline.replace('.', ''))).toBeGreaterThan(0n)
    expect(BigInt(kpis.confirmedBooking.replace('.', ''))).toBeGreaterThan(0n)
    expect(kpis.openPipeline).not.toBe(kpis.confirmedBooking)
    expect(kpis).not.toHaveProperty('weightedPipeline')
  })

  it('uses the injected business date for metadata, writes and DDL validation', async () => {
    const dated = createMockApi({ latency: 0, today: '2026-08-03' })
    const dashboard = await dated.getDashboard({ range: 'quarter' })
    const contact = await dated.createContact(contactInput({ name: 'Dated Contact' }))

    expect(dashboard.meta?.generatedAt).toBe('2026-08-03T10:30:00+08:00')
    expect(dashboard.meta).not.toHaveProperty('staleAt')
    expect(contact.data.updatedAt).toBe('2026-08-03')

    const fae = createMockApi({
      latency: 0,
      role: 'Engineer',
      userName: '演示员工14',
      today: '2026-08-03',
    })
    await expect(fae.setEvaluationTestRunDeadline('EVAL-103', { testRunDeadline: '2026-08-02' }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
  })

  it('counts only Confirmed records in Pipeline confirmed Booking', async () => {
    const before = await api.listPipeline({})
    const contact = (await api.listContacts({ accountId: 'ACC-001', pageSize: 100 })).data.items[0]
    await api.createBooking({
      accountId: 'ACC-001', primaryContactId: contact.id, equipment: 'Pending test tool', quantity: 1,
      ddl: '2026-09-30', amount: '1000000.00', currency: 'CNY', status: 'Pending', owner: 'person002@crm.example.invalid', source: 'Upsell', sourceOpportunityId: '', note: '',
    })
    const after = await api.listPipeline({})

    expect(cnyTotals(after.data).confirmedBooking).toBe(cnyTotals(before.data).confirmedBooking)
  })

  it('recalculates dashboard opportunity metrics from the writable sales repository', async () => {
    const before = await api.getDashboard({ range: 'quarter' })
    const beforeAccount = before.data.topAccounts.find((item) => item.accountId === 'ACC-001')
    const created = await api.createStrategyOpportunity({
      accountId: 'ACC-001',
      siteId: 'SITE-001',
      title: 'Dashboard 数据联通验证',
      owner: 'person002@crm.example.invalid',
      qualificationConfirmed: true, probabilityLevel: 'pipeline',
      amount: '9800000.00', amountCny: '9800000.00',
      intentScore: 35,
      poDate: '2026-11-30',
      toolType: 'Defect Inspection',
      saleType: 'New Tool',
      subRegion: '华东',
      currency: 'CNY',
    })

    const afterCreate = await api.getDashboard({ range: 'quarter' })
    expect(cnyKpis(afterCreate.data).openPipeline).toBe(addMoney([cnyKpis(before.data).openPipeline, '9800000.00']))
    expect(afterCreate.data.topAccounts.find((item) => item.accountId === 'ACC-001' && item.currency === 'CNY')?.pipeline)
      .toBe(addMoney([beforeAccount?.pipeline ?? '0.00', '9800000.00']))

    await expect(api.markOpportunityLost(created.data.id, { lostReason: ' ' }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    await api.markOpportunityLost(created.data.id, { lostReason: '预算冻结' })
    const afterClosed = await api.getDashboard({ range: 'quarter' })
    expect(cnyKpis(afterClosed.data).openPipeline).toBe(cnyKpis(before.data).openPipeline)
    expect(cnyKpis(afterClosed.data).cumulativeWon).toBe(cnyKpis(before.data).cumulativeWon)
  })

  it('filters and paginates accounts like a server list endpoint', async () => {
    const result = await api.listAccounts({ search: '示例企业044', page: 1, pageSize: 2 })

    expect(result.data.items).toHaveLength(1)
    expect(result.data.items[0].name).toContain('示例企业044')
    expect(result.meta?.total).toBe(1)
  })

  it('aggregates a traceable account 360 view', async () => {
    const result = await api.getAccount360('ACC-001')

    expect(result.data.account.name).toContain('示例企业015')
    expect(result.data.sites.length).toBeGreaterThan(0)
    expect(result.data.requirements.every((item) => item.accountId === 'ACC-001')).toBe(true)
    expect(result.data.demoRequests.every((item) => item.accountId === 'ACC-001')).toBe(true)
    expect(result.data.evaluations.every((item) => item.accountId === 'ACC-001')).toBe(true)
    expect(result.data.contracts.every((item) => item.accountId === 'ACC-001')).toBe(true)
  })

  it('filters, creates and reviews visits with account linkage and role enforcement', async () => {
    const contact = (await api.listContacts({ accountId: 'ACC-001', pageSize: 100 })).data.items[0]
    const filtered = await api.listVisits({ accountId: 'ACC-001', contactId: 'CON-001', status: 'Manager Reviewed', owner: 'person002@crm.example.invalid', dateFrom: '2026-07-01', dateTo: '2026-07-31' })
    expect(filtered.data.items.map((item) => item.id)).toEqual(['V-001'])

    const created = await api.createVisit({ accountId: 'ACC-001', primaryContactId: contact.id, subject: 'Demo 前置沟通', date: '2026-07-21', type: 'Video', owner: 'person002@crm.example.invalid', objective: '确认样片与参会人' })
    expect(created.data).toMatchObject({ status: 'Planned', primaryContactId: contact.id })
    const detail = await api.getAccount360('ACC-001')
    expect(detail.data.visits.some((item) => item.id === created.data.id)).toBe(true)
    const contactDetail = await api.getContact(contact.id)
    expect(contactDetail.data.visits).toContainEqual(expect.objectContaining({ id: created.data.id }))
    expect(contactDetail.data.timeline).toContainEqual(expect.objectContaining({ id: `visit:${created.data.id}` }))

    const management = createMockApi({ latency: 0, role: 'Manager', userName: '演示经理01' })
    await expect(management.createVisit({
      accountId: 'ACC-001',
      subject: 'Boss 客户沟通',
      date: '2026-07-21',
      type: 'Phone',
      owner: 'person002@crm.example.invalid',
      objective: '确认客户决策时间',
    })).resolves.toMatchObject({ data: { status: 'Planned', subject: 'Boss 客户沟通' } })
    const sales = createMockApi({ latency: 0, role: 'Sales' })
    await expect(sales.reviewVisit('V-001'))
      .rejects.toMatchObject({ code: 'PERMISSION_DENIED' })
  })

  it('lets Sales edit the basic fields of their own Visit until the Manager has reviewed it', async () => {
    const salesRepository = createMemorySalesRepository()
    const sales = createMockApi({ latency: 0, role: 'Sales', userId: 'person002@crm.example.invalid', salesRepository })
    const created = await sales.createVisit({ accountId: 'ACC-001', subject: '原定拜访', date: '2026-07-21', type: 'Video', owner: 'person002@crm.example.invalid', objective: '确认样片' })

    // Customers reschedule: date, subject, type and objective all change in one edit.
    const edited = await sales.updateVisit(created.data.id, { subject: '改期后拜访', date: '2026-07-28', type: 'On-site', owner: 'person002@crm.example.invalid', objective: '确认样片与参会人' }, created.data.modified)
    expect(edited.data).toMatchObject({ id: created.data.id, subject: '改期后拜访', date: '2026-07-28', type: 'On-site', objective: '确认样片与参会人', status: 'Planned' })
    expect(edited.data.modified).toBeTruthy()
    expect((await sales.getVisit(created.data.id)).data).toMatchObject({ subject: '改期后拜访', date: '2026-07-28' })

    // A stale modified token is rejected, the same as the Frappe optimistic lock.
    await expect(sales.updateVisit(created.data.id, { subject: '再改', date: '2026-07-29', type: 'Phone', owner: 'person002@crm.example.invalid', objective: '确认' }, '2000-01-01 00:00:00.000000'))
      .rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
    await expect(sales.updateVisit(created.data.id, { subject: '  ', date: '2026-07-29', type: 'Phone', owner: 'person002@crm.example.invalid', objective: '确认' }, edited.data.modified))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    await expect(sales.updateVisit(created.data.id, { subject: '转给同事', date: '2026-07-29', type: 'Phone', owner: 'person034@crm.example.invalid', objective: '确认' }, edited.data.modified))
      .rejects.toMatchObject({ code: 'SCOPE_DENIED' })

    // Reviewed Visits are frozen for everyone, and Engineers never hold visit:write.
    const manager = createMockApi({ latency: 0, role: 'Manager', userName: '演示经理01', salesRepository })
    await expect(manager.updateVisit('V-001', { subject: '事后改动', date: '2026-07-12', type: 'On-site', owner: 'person002@crm.example.invalid', objective: '确认' }))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION' })
    const engineer = createMockApi({ latency: 0, role: 'Engineer', salesRepository })
    await expect(engineer.updateVisit(created.data.id, { subject: '工程师改动', date: '2026-07-29', type: 'Phone', owner: 'person002@crm.example.invalid', objective: '确认' }))
      .rejects.toMatchObject({ code: 'PERMISSION_DENIED' })
  })

  it('persists stakeholder edits, derives detail counts and blocks read-only writes', async () => {
    const sales = createMockApi({ latency: 0, role: 'Sales' })
    const saved = await sales.updateStakeholder('CON-002', {
      accountId: 'ACC-001', name: '演示员工22', title: '良率提升负责人', department: '制程整合',
      role: 'Technical Champion', influence: 'High', relationship: 'Strong', reportsTo: 'CON-003', email: 'lin@example.com',
    })
    expect(saved.data).toMatchObject({ id: 'CON-002', reportsTo: 'CON-003', email: 'lin@example.com' })
    const detail = await sales.getAccount360('ACC-001')
    expect(detail.data.account.stakeholderCount).toBe(detail.data.contacts.length)

    const management = createMockApi({ latency: 0, role: 'Engineer' })
    await expect(management.createStakeholder({
      accountId: 'ACC-001', name: '越权', title: '测试', department: '测试', role: 'User', influence: 'Low', relationship: 'Weak',
    })).rejects.toMatchObject({ code: 'PERMISSION_DENIED' })
  })

  it('lists role-visible contacts and writes within the sales account scope', async () => {
    const sales = createMockApi({ latency: 0, role: 'Sales' })
    const listed = await sales.listContacts({ accountId: 'ACC-001' })
    expect(listed.data.items).not.toHaveLength(0)
    expect(listed.data.items.every((item) => item.accountId === 'ACC-001')).toBe(true)

    const created = await sales.createContact({
      accountId: 'ACC-001',
      name: 'Xu Gong',
      title: 'Equipment Manager',
      department: 'Engineering',
      relationship: 'Developing',
      owner: 'person002@crm.example.invalid',
      status: 'Active',
    })
    expect((await sales.getContact(created.data.id)).data.contact.name).toBe('Xu Gong')
  })

  it('rejects a Contact site or reporting parent from another account', async () => {
    const admin = createMockApi({ latency: 0, role: 'Manager' })
    await expect(admin.createContact({
      accountId: 'ACC-001', siteId: 'SITE-005', name: 'Cross account', title: 'Manager',
      department: 'Procurement', relationship: 'Developing', owner: 'person002@crm.example.invalid', status: 'Active',
    })).rejects.toMatchObject({ code: 'CONFLICT' })

    await expect(admin.createContact({
      accountId: 'ACC-001', reportsToContactId: 'CON-004', name: 'Wrong parent', title: 'Manager',
      department: 'Procurement', relationship: 'Developing', owner: 'person002@crm.example.invalid', status: 'Active',
    })).rejects.toMatchObject({ code: 'CONFLICT' })
  })

  it('merges a duplicate by rewriting Contact-ID references without deleting the duplicate', async () => {
    const admin = createMockApi({ latency: 0, role: 'Manager' })
    const duplicate = await admin.createContact({
      accountId: 'ACC-001', name: 'Duplicate Wang', title: 'Equipment VP',
      department: 'Manufacturing Operations', relationship: 'Developing', owner: 'person002@crm.example.invalid', status: 'Active',
    })
    await admin.mergeContacts({ survivorId: 'CON-001', duplicateId: duplicate.data.id })

    const archived = (await admin.getContact(duplicate.data.id)).data.contact
    expect(archived).toMatchObject({ status: 'Archived', mergedIntoContactId: 'CON-001' })
  })

  it('rewrites Opportunity and reporting Contact-ID references during a merge', async () => {
    const admin = createMockApi({ latency: 0, role: 'Manager' })
    const duplicate = await admin.createContact(contactInput({ name: 'Duplicate' }))
    const directReport = await admin.createContact(contactInput({ name: 'Report', reportsToContactId: duplicate.data.id }))
    const link = await admin.createOpportunityStakeholder('OPP-001', {
      contactId: duplicate.data.id, role: 'Technical Champion', influence: 'High', stance: 'Support', coverage: 'Direct coverage',
    })
    const visit = await admin.createVisit({
      accountId: 'ACC-001', primaryContactId: duplicate.data.id, subject: 'Merge linked visit', date: '2026-07-21',
      type: 'Phone', owner: 'person002@crm.example.invalid', objective: 'Verify merge linkage',
    })

    await admin.mergeContacts({ survivorId: 'CON-001', duplicateId: duplicate.data.id })

    const opportunity = (await admin.listStrategyOpportunities()).data.items.find((item) => item.id === 'OPP-001')!
    expect(opportunity.stakeholders.find((item) => item.id === link.data.id)).toMatchObject({ contactId: 'CON-001' })
    expect((await admin.getContact(directReport.data.id)).data.reportsTo?.id).toBe('CON-001')
    expect((await admin.listVisits({ contactId: 'CON-001' })).data.items).toContainEqual(expect.objectContaining({ id: visit.data.id }))
  })

  it('rejects a merge when both Contacts are already linked to one Opportunity', async () => {
    const admin = createMockApi({ latency: 0, role: 'Manager' })
    const duplicate = await admin.createContact(contactInput({ name: 'Duplicate' }))
    await admin.createOpportunityStakeholder('OPP-001', {
      contactId: 'CON-001', role: 'Economic Buyer', influence: 'High', stance: 'Support', coverage: 'Executive sponsor',
    })
    await admin.createOpportunityStakeholder('OPP-001', {
      contactId: duplicate.data.id, role: 'Technical Champion', influence: 'High', stance: 'Support', coverage: 'Technical sponsor',
    })

    await expect(admin.mergeContacts({ survivorId: 'CON-001', duplicateId: duplicate.data.id }))
      .rejects.toMatchObject({ code: 'CONFLICT' })
  })

  it('denies a non-administrator Contact merge', async () => {
    const sales = createMockApi({ latency: 0, role: 'Sales' })
    await expect(sales.mergeContacts({ survivorId: 'CON-001', duplicateId: 'CON-002' }))
      .rejects.toMatchObject({ code: 'PERMISSION_DENIED' })
  })

  it('uploads, reads and deletes Contact files with role-aware access', async () => {
    const contactFileRepository = createMemoryContactFileRepository()
    const admin = createMockApi({ latency: 0, role: 'Manager', contactFileRepository })
    const viewer = createMockApi({ latency: 0, role: 'Manager', contactFileRepository })
    const blob = new Blob(['contact pdf'], { type: 'application/pdf' })

    const uploaded = await admin.uploadContactFiles('CON-001', [{
      fileName: 'contact-profile.pdf',
      mimeType: blob.type,
      size: blob.size,
      blob,
    }])
    const fileId = uploaded.data[0].id

    expect((await viewer.listContactFiles('CON-001')).data.items).toContainEqual(expect.objectContaining({
      id: fileId,
      fileName: 'contact-profile.pdf',
    }))
    const downloaded = await viewer.getContactFile(fileId)
    expect(downloaded).toMatchObject({ fileName: 'contact-profile.pdf', mimeType: 'application/pdf' })
    expect(await downloaded.blob.text()).toBe('contact pdf')
    const bossUpload = await viewer.uploadContactFiles('CON-001', [{
      fileName: 'blocked.pdf',
      mimeType: blob.type,
      size: blob.size,
      blob,
    }])
    await viewer.deleteContactFile(bossUpload.data[0].id)

    await admin.deleteContactFile(fileId)
    expect((await admin.listContactFiles('CON-001')).data.items).toEqual([])
  })

  it('validates Contact file type and migrates files through merge and hard delete', async () => {
    const contactFileRepository = createMemoryContactFileRepository()
    const admin = createMockApi({ latency: 0, role: 'Manager', contactFileRepository })
    const duplicate = await admin.createContact(contactInput({ name: 'Duplicate with file' }))
    const blob = new Blob(['notes'], { type: 'text/plain' })

    await expect(admin.uploadContactFiles(duplicate.data.id, [{
      fileName: 'malware.exe',
      mimeType: 'application/octet-stream',
      size: blob.size,
      blob,
    }])).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })

    const uploaded = await admin.uploadContactFiles(duplicate.data.id, [{
      fileName: 'notes.txt',
      mimeType: blob.type,
      size: blob.size,
      blob,
    }])
    await admin.mergeContacts({ survivorId: 'CON-001', duplicateId: duplicate.data.id })
    expect((await admin.listContactFiles('CON-001')).data.items.map((file) => file.id)).toContain(uploaded.data[0].id)
    expect((await admin.listContactFiles(duplicate.data.id)).data.items).toEqual([])

    await admin.deleteContact('CON-001')
    expect(await contactFileRepository.get(uploaded.data[0].id)).toBeUndefined()
  })

  it('physically deletes a Contact and removes its Opportunity and reporting links', async () => {
    const salesRepository = createMemorySalesRepository()
    const admin = createMockApi({ latency: 0, role: 'Manager', salesRepository })
    const target = await admin.createContact(contactInput({ name: 'Delete Me' }))
    const directReport = await admin.createContact(contactInput({ name: 'Direct Report', reportsToContactId: target.data.id }))
    await admin.createOpportunityStakeholder('OPP-001', {
      contactId: target.data.id,
      role: 'Coach',
      influence: 'Medium',
      stance: 'Support',
      coverage: 'Temporary link',
    })
    const visit = await admin.createVisit({
      accountId: 'ACC-001', primaryContactId: target.data.id, subject: 'Delete linked visit', date: '2026-07-21',
      type: 'Phone', owner: 'person002@crm.example.invalid', objective: 'Verify delete linkage',
    })

    await expect(admin.deleteContact(target.data.id)).resolves.toMatchObject({ data: { id: target.data.id, status: 'Deleted' } })

    await expect(admin.getContact(target.data.id)).rejects.toMatchObject({ code: 'NOT_FOUND' })
    await expect(admin.deleteContact(target.data.id)).rejects.toMatchObject({ code: 'NOT_FOUND' })
    expect((await admin.getContact(directReport.data.id)).data.reportsTo).toBeUndefined()
    const opportunity = (await admin.listStrategyOpportunities()).data.items.find((item) => item.id === 'OPP-001')!
    expect(opportunity.stakeholders.map((item) => item.contactId)).not.toContain(target.data.id)
    expect(salesRepository.snapshot.visits.find((item) => item.id === visit.data.id)?.primaryContactId).not.toBe(target.data.id)
  })

  it('rolls back Contact merge links and files when Demo synchronization fails', async () => {
    const baseRepository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    let failTransactions = false
    const repository = {
      read: () => baseRepository.read(),
      transact: <T>(change: Parameters<typeof baseRepository.transact<T>>[0]) => {
        if (failTransactions) return Promise.reject(new Error('demo storage unavailable'))
        return baseRepository.transact(change)
      },
    }
    const salesRepository = createMemorySalesRepository()
    const contactFileRepository = createMemoryContactFileRepository()
    const admin = createMockApi({ latency: 0, role: 'Manager', repository, salesRepository, contactFileRepository })
    const duplicate = await admin.createContact(contactInput({ name: 'Rollback Duplicate' }))
    const stakeholder = await admin.createOpportunityStakeholder('OPP-001', {
      contactId: duplicate.data.id, role: 'Coach', influence: 'Medium', stance: 'Support', coverage: 'Rollback test',
    })
    const uploaded = await admin.uploadContactFiles(duplicate.data.id, [{
      fileName: 'rollback.pdf', mimeType: 'application/pdf', size: 8, blob: new Blob(['rollback'], { type: 'application/pdf' }),
    }])
    await admin.listContacts({ pageSize: 100 })
    failTransactions = true

    await expect(admin.mergeContacts({ survivorId: 'CON-001', duplicateId: duplicate.data.id })).rejects.toThrow('demo storage unavailable')

    const opportunity = salesRepository.snapshot.opportunities.find((item) => item.id === 'OPP-001')!
    expect(opportunity.stakeholders.find((item) => item.id === stakeholder.data.id)?.contactId).toBe(duplicate.data.id)
    expect(salesRepository.snapshot.contacts.find((item) => item.id === duplicate.data.id)?.status).toBe('Active')
    expect((await contactFileRepository.get(uploaded.data[0].id))?.contactId).toBe(duplicate.data.id)
  })

  it('rolls back Contact deletion when Demo synchronization fails', async () => {
    const baseRepository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    let failTransactions = false
    const repository = {
      read: () => baseRepository.read(),
      transact: <T>(change: Parameters<typeof baseRepository.transact<T>>[0]) => {
        if (failTransactions) return Promise.reject(new Error('demo storage unavailable'))
        return baseRepository.transact(change)
      },
    }
    const salesRepository = createMemorySalesRepository()
    const admin = createMockApi({ latency: 0, role: 'Manager', repository, salesRepository })
    const target = await admin.createContact(contactInput({ name: 'Rollback Delete' }))
    const stakeholder = await admin.createOpportunityStakeholder('OPP-001', {
      contactId: target.data.id, role: 'Coach', influence: 'Medium', stance: 'Support', coverage: 'Rollback test',
    })
    await admin.listContacts({ pageSize: 100 })
    failTransactions = true

    await expect(admin.deleteContact(target.data.id)).rejects.toThrow('demo storage unavailable')

    expect(salesRepository.snapshot.contacts).toContainEqual(expect.objectContaining({ id: target.data.id }))
    const opportunity = salesRepository.snapshot.opportunities.find((item) => item.id === 'OPP-001')!
    expect(opportunity.stakeholders.find((item) => item.id === stakeholder.data.id)?.contactId).toBe(target.data.id)
  })

  it('does not recreate retired Demo Contact placeholders from stale Demo Request links', async () => {
    const salesRepository = createMemorySalesRepository()
    const placeholder = {
      id: 'CT-DR-STALE',
      accountId: 'ACC-005',
      name: '示例企业040有限公司 Demo Contact',
      title: '',
      department: '',
      relationship: 'Developing' as const,
      owner: 'person005@crm.example.invalid',
      status: 'Active' as const,
      dataQuality: 'Needs Review' as const,
      updatedAt: '2026-07-28',
    }
    salesRepository.snapshot.contacts.push(placeholder)
    const staleSnapshot = seedDemoSnapshot()
    const staleRequest = staleSnapshot.demoRequests.find((request) => request.accountId === placeholder.accountId)!
    staleRequest.primaryContactId = placeholder.id
    const storage = createMemoryDemoStorage()
    await storage.save(staleSnapshot)
    const repository = createDemoRepository(storage, seedDemoSnapshot)
    const admin = createMockApi({ latency: 0, role: 'Manager', salesRepository, repository })

    const contacts = (await admin.listContacts({ contactStatus: 'All', pageSize: 500 })).data.items
    const refreshedRequest = (await repository.read()).demoRequests.find((request) => request.id === staleRequest.id)!

    expect(contacts.map((contact) => contact.name)).not.toContain(placeholder.name)
    expect(refreshedRequest.primaryContactId).toBe('CON-008')
  })

  it('denies non-administrator delete attempts and reports an unknown Contact', async () => {
    const deniedStorage = createMemoryDemoStorage()
    const deniedSalesRepository = createMemorySalesRepository()
    const deniedStorageSave = vi.spyOn(deniedStorage, 'save')
    const deniedSalesSave = vi.spyOn(deniedSalesRepository, 'save')
    const sales = createMockApi({
      latency: 0,
      role: 'Sales',
      repository: createDemoRepository(deniedStorage, seedDemoSnapshot),
      salesRepository: deniedSalesRepository,
    })
    const missingStorage = createMemoryDemoStorage()
    const missingSalesRepository = createMemorySalesRepository()
    const missingStorageSave = vi.spyOn(missingStorage, 'save')
    const missingSalesSave = vi.spyOn(missingSalesRepository, 'save')
    const admin = createMockApi({
      latency: 0,
      role: 'Manager',
      repository: createDemoRepository(missingStorage, seedDemoSnapshot),
      salesRepository: missingSalesRepository,
    })

    await expect(sales.deleteContact('CON-001')).rejects.toMatchObject({ code: 'PERMISSION_DENIED' })
    await expect(admin.deleteContact('CON-404')).rejects.toMatchObject({ code: 'NOT_FOUND' })
    expect(deniedStorageSave).not.toHaveBeenCalled()
    expect(deniedSalesSave).not.toHaveBeenCalled()
    expect(missingStorageSave).not.toHaveBeenCalled()
    expect(missingSalesSave).not.toHaveBeenCalled()
  })

  it('rejects a merge that would make the survivor report to itself', async () => {
    const admin = createMockApi({ latency: 0, role: 'Manager' })
    const duplicate = await admin.createContact(contactInput({ name: 'Duplicate' }))
    const survivor = (await admin.getContact('CON-001')).data.contact
    await admin.updateContact(survivor.id, contactUpdateInput(survivor, { reportsToContactId: duplicate.data.id }))

    await expect(admin.mergeContacts({ survivorId: survivor.id, duplicateId: duplicate.data.id }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
  })

  it('rejects a merge that would form an indirect reporting cycle', async () => {
    const admin = createMockApi({ latency: 0, role: 'Manager' })
    const duplicate = await admin.createContact(contactInput({ name: 'Duplicate' }))
    const bridge = await admin.createContact(contactInput({ name: 'Bridge', reportsToContactId: duplicate.data.id }))
    const survivor = (await admin.getContact('CON-001')).data.contact
    await admin.updateContact(survivor.id, contactUpdateInput(survivor, { reportsToContactId: bridge.data.id }))

    await expect(admin.mergeContacts({ survivorId: survivor.id, duplicateId: duplicate.data.id }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
  })


  it('filters confirmed bookings and keeps dashboard values traceable across range requests', async () => {
    const pipeline = await api.listPipeline({ search: '示例企业027' })
    const month = await api.getDashboard({ range: 'month' })
    const quarter = await api.getDashboard({ range: 'quarter' })
    const year = await api.getDashboard({ range: 'year' })

    expect(pipeline.data.bookings).toHaveLength(1)
    expect(pipeline.data.bookings[0].status).toBe('Confirmed')
    expect(pipeline.data.bookings[0].accountName).toContain('示例企业027')
    expect(month.data.bookingByMonth).toEqual([
      { label: '2026-06', currency: 'CNY', amount: '3600000.00', count: 1 },
      { label: '2026-07', currency: 'CNY', amount: '18800000.00', count: 1 },
    ])
    expect(cnyKpis(month.data).openPipeline).toBe(cnyKpis(quarter.data).openPipeline)
    expect(cnyKpis(quarter.data).openPipeline).toBe(cnyKpis(year.data).openPipeline)
  })

  it('stores Booking primary Contact by ID and derives the display name', async () => {
    const bookingApi = createMockApi({ latency: 0 })
    const contact = (await bookingApi.listContacts({ accountId: 'ACC-002' })).data.items[0]
    const created = await bookingApi.createBooking({
      accountId: 'ACC-002', primaryContactId: contact.id, equipment: 'FastScan 1200',
      quantity: 1, ddl: '2026-09-30', amount: '1000000.00', currency: 'CNY', status: 'Pending',
      owner: 'person002@crm.example.invalid', source: 'Upsell', sourceOpportunityId: '', note: '',
    })
    expect(created.data).toMatchObject({ primaryContactId: contact.id, customerContact: contact.name })
  })

  it('blocks a Sales-owned Booking from moving to another private customer account', async () => {
    const salesRepository = createMemorySalesRepository()
    const sales = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01', salesRepository })
    const ownContact = salesRepository.snapshot.contacts.find((item) => item.accountId === 'ACC-001' && item.status === 'Active')!
    const foreignContact = salesRepository.snapshot.contacts.find((item) => item.accountId === 'ACC-006' && item.status === 'Active')!
    const created = await sales.createBooking({
      accountId: 'ACC-001', primaryContactId: ownContact.id, equipment: 'Scope Test Tool', quantity: 1,
      ddl: '2026-09-30', amount: '1000000.00', currency: 'CNY', status: 'Pending', owner: 'person002@crm.example.invalid', source: 'Upsell', sourceOpportunityId: '', note: '',
    })

    await expect(sales.updateBooking(created.data.id, {
      accountId: 'ACC-006', primaryContactId: foreignContact.id, equipment: 'Scope Test Tool', quantity: 1,
      ddl: '2026-09-30', amount: '1000000.00', currency: 'CNY', status: 'Pending', owner: 'person002@crm.example.invalid', source: 'Upsell', sourceOpportunityId: '', note: '',
    })).rejects.toMatchObject({ code: 'SCOPE_DENIED' })
    expect(salesRepository.snapshot.bookings.find((item) => item.id === created.data.id)?.accountId).toBe('ACC-001')
  })

  it('stores Demo Request primary Contact by ID and derives its document snapshot', async () => {
    const contact = (await api.listContacts({ accountId: 'ACC-001' })).data.items[0]
    const opportunity = await createEligibleDemoOpportunity(api, 'primary-contact')
    const created = await api.createDemoRequest({
      accountId: 'ACC-001', primaryContactId: contact.id, opportunityId: opportunity.id, formData: completeDemoRequestForm(),
      requestMode: 'Opportunity', customerExpectedDate: '2026-09-01', submit: false,
    })
    expect(created.data.primaryContactId).toBe(contact.id)
    expect(created.data.formData?.contactPerson).toContain(contact.name)
  })

  it('rejects a Demo Request without an Opportunity link', async () => {
    const contact = (await api.listContacts({ accountId: 'ACC-001' })).data.items[0]
    await expect(api.createDemoRequest({
      accountId: 'ACC-001', primaryContactId: contact.id, formData: completeDemoRequestForm(),
      customerExpectedDate: '2026-09-01', submit: false,
    } as never)).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
  })

  it('rejects missing, cross-account and inactive primary Contacts', async () => {
    const crossAccount = (await api.listContacts({ accountId: 'ACC-002' })).data.items[0]
    const inactive = await api.createContact(contactInput({ name: 'Former buyer', status: 'Left Company' }))
    const booking = (primaryContactId: string) => api.createBooking({
      accountId: 'ACC-001', primaryContactId, equipment: 'FastScan 1200', quantity: 1,
      ddl: '2026-09-30', amount: '1000000.00', currency: 'CNY', status: 'Pending', owner: 'person002@crm.example.invalid',
      source: 'Upsell', sourceOpportunityId: '', note: '',
    })
    await expect(booking('missing-contact')).rejects.toMatchObject({ code: 'NOT_FOUND' })
    await expect(booking(crossAccount.id)).rejects.toMatchObject({ code: 'CONFLICT' })
    await expect(booking(inactive.data.id)).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
  })

  it('enforces the Demo Request approval state machine', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    const sales = createMockApi({ repository, latency: 0 })
    const opportunity = await createEligibleDemoOpportunity(sales, 'approval-machine')
    const created = await sales.createDemoRequest({
      accountId: 'ACC-001',
      primaryContactId: 'CON-001',
      opportunityId: opportunity.id,
      formData: completeDemoRequestForm(),
      requestMode: 'Opportunity',
      customerExpectedDate: '2026-09-01',
      submit: false,
    })
    const submitted = await sales.transitionDemoRequest(created.data.id, { type: 'submit' })
    expect(submitted.data.request.status).toBe('Engineer Review')

    const boss = createMockApi({ repository, latency: 0, role: 'Manager' })
    await expect(boss.transitionDemoRequest(created.data.id, { type: 'manager_approve', comment: '越级批准' }))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION' })
  })

  it('persists one Sales owner and one concrete Engineer owner at creation', async () => {
    const opportunity = await createEligibleDemoOpportunity(api, 'owners')
    const created = await api.createDemoRequest({
      accountId: 'ACC-001',
      primaryContactId: 'CON-001',
      opportunityId: opportunity.id,
      formData: completeDemoRequestForm(),
      requestMode: 'Opportunity',
      customerExpectedDate: '2026-09-01',
      submit: true,
    })

    expect(created.data.salesOwner).toBe('person002@crm.example.invalid')
    expect(created.data.engineerOwner).toBe('person077@crm.example.invalid')
  })

  it('moves the linked Opportunity to Demo done only when its Demo reaches Customer Review', async () => {
    const opportunity = await createEligibleDemoOpportunity(api, 'complete-auto-chain')
    expect(opportunity.stageHistory).toEqual([expect.objectContaining({ from: '', to: 'qualified_opportunity', source: 'creation', event: 'created' })])
    const created = await api.createDemoRequest({
      accountId: 'ACC-001', primaryContactId: 'CON-001', opportunityId: opportunity.id,
      requestMode: 'Opportunity', formData: completeDemoRequestForm(), customerExpectedDate: '2026-09-01', submit: true,
    })
    expect((await api.getStrategyOpportunity(opportunity.id)).data.stage).toBe('qualified_opportunity')

    await api.transitionDemoRequest(created.data.id, {
      type: 'engineer_approve', engineerOwner: 'person077@crm.example.invalid', testPlan: 'CIS defect recipe',
      assignedEquipment: 'Macro Inspection Lab-01', resourceWindow: '2026-08-15 ~ 2026-08-20',
      estimatedCompletionDate: '2026-08-21', technicalRisk: 'Low', comment: 'Technical scope confirmed',
    })
    const approved = await api.transitionDemoRequest(created.data.id, { type: 'manager_approve', comment: 'Approved' })
    expect((await api.getStrategyOpportunity(opportunity.id)).data.stage).toBe('qualified_opportunity')

    const evaluationId = approved.data.evaluation!.id
    await api.completeEvaluationPreparation(evaluationId, 'wafer', '')
    await api.completeEvaluationPreparation(evaluationId, 'test', '')
    await api.updateEvaluationStatus(evaluationId, { status: 'Testing' })
    await api.addEvaluationRun(evaluationId, {
      date: '2026-08-20', lot: 'CIS-LOT-300MM', wafers: 12,
      capture: 96.8, falsePositive: 1.1, wph: 18.5, summary: 'Acceptance criteria met',
    })
    await api.releaseDemoTestReport(evaluationId, reportFiles('cis-demo-report.pdf', 'report'))
    await api.updateEvaluationStatus(evaluationId, { status: 'Internal Review' })
    expect((await api.getStrategyOpportunity(opportunity.id)).data.stage).toBe('qualified_opportunity')
    await api.updateEvaluationStatus(evaluationId, { status: 'Customer Review' })
    const reviewed = (await api.getStrategyOpportunity(opportunity.id)).data
    expect(reviewed.stage).toBe('demo_done')
    expect(reviewed.stageHistory[0]).toMatchObject({
      from: 'qualified_opportunity', to: 'demo_done', source: 'event', event: 'demo_customer_review',
      referenceDoctype: 'CRM Evaluation', referenceName: evaluationId,
    })
    await api.updateEvaluationStatus(evaluationId, { status: 'Accepted', customerComment: '客户确认留痕' })
    expect((await api.getStrategyOpportunity(opportunity.id)).data.stage).toBe('demo_done')
  })

  it('archives a Demo Test whose Opportunity has left the Demo gate', async () => {
    async function inCustomerReview(suffix: string) {
      const opportunity = await createEligibleDemoOpportunity(api, suffix)
      const created = await api.createDemoRequest({
        accountId: 'ACC-001', primaryContactId: 'CON-001', opportunityId: opportunity.id,
        requestMode: 'Opportunity', formData: completeDemoRequestForm(), customerExpectedDate: '2026-09-01', submit: true,
      })
      await api.transitionDemoRequest(created.data.id, {
        type: 'engineer_approve', engineerOwner: 'person077@crm.example.invalid', testPlan: 'CIS defect recipe',
        assignedEquipment: 'Macro Inspection Lab-01', resourceWindow: '2026-08-15 ~ 2026-08-20',
        estimatedCompletionDate: '2026-08-21', technicalRisk: 'Low', comment: 'Technical scope confirmed',
      })
      const approved = await api.transitionDemoRequest(created.data.id, { type: 'manager_approve', comment: 'Approved' })
      const evaluationId = approved.data.evaluation!.id
      await api.completeEvaluationPreparation(evaluationId, 'wafer', '')
      await api.completeEvaluationPreparation(evaluationId, 'test', '')
      await api.updateEvaluationStatus(evaluationId, { status: 'Testing' })
      await api.addEvaluationRun(evaluationId, {
        date: '2026-08-20', lot: `CIS-LOT-${suffix}`, wafers: 12,
        capture: 60, falsePositive: 9, wph: 18.5, summary: 'Below acceptance criteria',
      })
      await api.releaseDemoTestReport(evaluationId, reportFiles('cis-demo-report.pdf', 'report'))
      await api.updateEvaluationStatus(evaluationId, { status: 'Internal Review' })
      await api.updateEvaluationStatus(evaluationId, { status: 'Customer Review' })
      return { opportunityId: opportunity.id, evaluationId }
    }
    // With Reject gone, archiving is the only way out of Customer Review. An Opportunity
    // closed as Lost, or moved back once the Demo Request was converted, must not hold it.
    const lost = await inCustomerReview('archive-lost')
    await api.markOpportunityLost(lost.opportunityId, { lostReason: '客户不认可 Demo' })
    const rolledBack = await inCustomerReview('archive-rolled-back')
    await api.rollbackOpportunityStage(rolledBack.opportunityId, { targetStage: 'qualified_opportunity', reason: '客户预算冻结，重新评估需求' })

    for (const [scenario, stage] of [[lost, 'lost'], [rolledBack, 'qualified_opportunity']] as const) {
      const archived = await api.updateEvaluationStatus(scenario.evaluationId, { status: 'Accepted', customerComment: '客户不认可检出率，项目关闭' })
      expect(archived.data.status).toBe('Accepted')
      expect((await api.getStrategyOpportunity(scenario.opportunityId)).data.stage).toBe(stage)
    }
  })

  it('runs a Self Test through the complete Demo flow without changing Opportunities', async () => {
    const before = (await api.listStrategyOpportunities({ accountId: 'ACC-001' })).data.items
      .map((item) => [item.id, item.stage])
    const formData = completeDemoRequestForm()
    formData.industry = ''
    const created = await api.createDemoRequest({
      accountId: 'ACC-001', requestMode: 'Self Test',
      formData, customerExpectedDate: '2026-09-01', submit: true,
    })
    expect(created.data).toMatchObject({ requestMode: 'Self Test', opportunityId: undefined, primaryContactId: '' })
    await api.transitionDemoRequest(created.data.id, {
      type: 'engineer_approve', engineerOwner: 'person077@crm.example.invalid', testPlan: 'Self-test recipe',
      assignedEquipment: 'Lab-01', resourceWindow: '2026-08-15 ~ 2026-08-20',
      estimatedCompletionDate: '2026-08-21', technicalRisk: 'Low', comment: 'Ready',
    })
    const approved = await api.transitionDemoRequest(created.data.id, { type: 'manager_approve', comment: 'Approved' })
    const evaluationId = approved.data.evaluation!.id
    await api.completeEvaluationPreparation(evaluationId, 'wafer', '')
    await api.completeEvaluationPreparation(evaluationId, 'test', '')
    await api.updateEvaluationStatus(evaluationId, { status: 'Testing' })
    await api.addEvaluationRun(evaluationId, {
      date: '2026-08-20', lot: 'SELF-TEST', wafers: 1, capture: 99, falsePositive: 1, wph: 10, summary: 'Passed',
    })
    await api.releaseDemoTestReport(evaluationId, reportFiles('self-test.pdf', 'report'))
    await api.updateEvaluationStatus(evaluationId, { status: 'Internal Review' })
    await api.updateEvaluationStatus(evaluationId, { status: 'Customer Review' })
    await api.updateEvaluationStatus(evaluationId, { status: 'Accepted', customerComment: '客户确认留痕' })
    expect((await api.listStrategyOpportunities({ accountId: 'ACC-001' })).data.items.map((item) => [item.id, item.stage])).toEqual(before)
  })

  it('allows only one active Demo Request per Opportunity', async () => {
    const opportunity = await createEligibleDemoOpportunity(api, 'single-active-request')
    const input = {
      accountId: 'ACC-001', primaryContactId: 'CON-001', opportunityId: opportunity.id,
      requestMode: 'Opportunity' as const, formData: completeDemoRequestForm(), customerExpectedDate: '2026-09-01', submit: false,
    }
    const first = await api.createDemoRequest(input)
    await expect(api.createDemoRequest(input)).rejects.toMatchObject({ code: 'CONFLICT' })
    await api.transitionDemoRequest(first.data.id, { type: 'cancel', comment: 'Replacement requested' })
    await expect(api.createDemoRequest(input)).resolves.toBeDefined()
  })

  it('rolls back only to earlier milestones and records why in the stage history', async () => {
    const manager = createMockApi({ latency: 0, role: 'Manager' })
    await expect(manager.rollbackOpportunityStage('OPP-003', { targetStage: 'quotation_sent', reason: 'Same stage' }))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION', message: 'Rollback target must be an earlier stage.' })
    await expect(manager.rollbackOpportunityStage('OPP-003', { targetStage: 'lost' as never, reason: 'Not a milestone' }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR', message: 'targetStage is invalid.' })
    await expect(manager.rollbackOpportunityStage('OPP-003', { targetStage: 'demo_done', reason: ' ' }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR', message: 'reason is required.' })

    const rolledBack = (await manager.rollbackOpportunityStage('OPP-003', { targetStage: 'demo_done', reason: 'Customer re-runs the demo' })).data
    expect(rolledBack).toMatchObject({ stage: 'demo_done', budgetApprovedOn: '', stageChangedAt: rolledBack.stageHistory[0]!.recordedAt })
    expect(rolledBack.stageHistory[0]).toMatchObject({
      from: 'quotation_sent', to: 'demo_done', source: 'rollback', event: 'rollback', reason: 'Customer re-runs the demo', actor: 'person029@crm.example.invalid',
    })
    await expect(manager.rollbackOpportunityStage('OPP-003', { targetStage: 'qualified_opportunity', reason: 'Stale page' }, 'stale-version'))
      .rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
    await expect(manager.rollbackOpportunityStage('OPP-003', { targetStage: 'qualified_opportunity', reason: 'Fresh page' }, rolledBack.modified))
      .resolves.toMatchObject({ data: { stage: 'qualified_opportunity' } })

    const sales = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01' })
    await expect(sales.rollbackOpportunityStage('OPP-003', { targetStage: 'qualified_opportunity', reason: 'Not a Manager' }))
      .rejects.toMatchObject({ code: 'PERMISSION_DENIED' })
  })

  it('enforces role capabilities in the Mock API', async () => {
    const boss = createMockApi({ latency: 0, role: 'Manager' })
    await expect(boss.transitionDemoRequest('DR-104', { type: 'manager_approve', comment: 'Approved' }))
      .resolves.toBeDefined()

    const sales = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01' })
    await expect(sales.getDashboard({ range: 'quarter' })).resolves.toBeDefined()
    await expect(sales.getAccount360('ACC-001')).resolves.toBeDefined()
    await expect(sales.transitionDemoRequest('DR-104', { type: 'manager_approve', comment: '越权' }))
      .rejects.toMatchObject({ code: 'PERMISSION_DENIED' })

    const fae = createMockApi({ latency: 0, role: 'Engineer' })
    await expect(fae.transitionDemoRequest('DR-104', { type: 'manager_approve', comment: '越权' }))
      .rejects.toMatchObject({ code: 'PERMISSION_DENIED' })
  })

  it('allows only Manager to delete top-level Sales records', async () => {
    const sales = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01' })
    await expect(sales.deleteAccount('ACC-001')).rejects.toMatchObject({ code: 'PERMISSION_DENIED' })

    const manager = createMockApi({ latency: 0, role: 'Manager' })
    const accountId = (await manager.listAccounts({ pageSize: 1 })).data.items[0].id

    await expect(manager.deleteAccount(accountId)).resolves.toMatchObject({ data: { id: accountId, status: 'Deleted' } })
  })

  it('gives equipment engineers assigned technical access without CRM write access', async () => {
    const engineer = createMockApi({
      latency: 0,
      role: 'Engineer',
      userName: '演示员工15',
      assignedAccountIds: ['ACC-001'],
    })

    const bootstrap = await engineer.getBootstrap()
    expect(bootstrap.data.capabilities).toEqual(expect.arrayContaining([
      'account:view', 'deal:view', 'demo_request:view', 'evaluation:view', 'evaluation:write',
    ]))
    expect(bootstrap.data.capabilities).not.toContain('account:write')
    expect(bootstrap.data.capabilities).not.toContain('deal:write')

    const accounts = await engineer.listAccounts({ page: 1, pageSize: 100 })
    expect(accounts.data.items.map((account) => account.id)).toEqual(['ACC-001'])
  })

  it('persists customer and opportunity changes inside one Mock session', async () => {
    const existing = await api.listStrategyOpportunities()
    expect(existing.data.items.find((item) => item.id === 'OPP-003')).toMatchObject({
      stage: 'quotation_sent',
      score: 86,
      probabilityLevel: 'committed',
    })

    const customer = await api.createAccount({
      name: '示例企业037有限公司', shortName: 'Demo Fab', segment: 'Frontend', tier: 'A',
      city: '苏州', region: '华东', owner: 'person002@crm.example.invalid',
    })
    expect(customer.data.id).toMatch(/^ACC-/)
    const customerList = await api.listAccounts({ search: 'Demo Fab', page: 1, pageSize: 20 })
    expect(customerList.data.items.map((item) => item.id)).toContain(customer.data.id)

    const updatedCustomer = await api.updateAccount(customer.data.id, {
      name: '示例企业038有限公司', shortName: 'Demo Fab+', segment: 'Advanced Packaging', tier: 'S',
      city: '无锡', region: '华东', owner: 'person005@crm.example.invalid',
    }, customer.data.modified)
    expect(updatedCustomer.data).toMatchObject({ name: '示例企业038有限公司', shortName: 'Demo Fab+', city: '无锡', updatedAt: '刚刚' })
    expect((await api.getAccount360(customer.data.id)).data.account.name).toBe('示例企业038有限公司')

    const created = await api.createStrategyOpportunity({
      accountId: 'ACC-001', siteId: 'SITE-001', title: '新增缺陷检测机会', owner: 'person002@crm.example.invalid',
      qualificationConfirmed: true, probabilityLevel: 'pipeline', amount: '9800000.00', amountCny: '9800000.00', intentScore: 35,
      poDate: '2026-11-30', toolType: 'Defect Inspection', saleType: 'New Tool', subRegion: '华东', currency: 'CNY',
    })
    expect(created.data).toMatchObject({
      account: '示例企业014有限公司',
      site: '南京 12-inch Fab',
      score: 35,
      probabilityLevel: 'pipeline',
      probabilityHistory: [expect.objectContaining({ from: '', to: 'pipeline' })],
    })
    expect(created.data).not.toHaveProperty('probability')
    expect(created.data).not.toHaveProperty('forecast')

    const updated = await api.updateStrategyOpportunity(created.data.id, {
      title: '新增缺陷检测机会（更新）', intentScore: 55,
    })
    expect(updated.data).toMatchObject({
      title: '新增缺陷检测机会（更新）',
      score: 55,
      probabilityLevel: 'pipeline',
      stage: 'qualified_opportunity',
    })
    expect(updated.data.history[0]).toMatchObject({ actor: 'person029@crm.example.invalid' })

    const listed = await api.listStrategyOpportunities()
    expect(listed.data.items.find((item) => item.id === created.data.id)?.title).toBe('新增缺陷检测机会（更新）')
  })

  it('lets the opener set the first success probability, then only the owner, and audits each level change', async () => {
    const salesRepository = createMemorySalesRepository()
    const owner = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01', salesRepository, today: '2026-07-17' })
    const manager = createMockApi({ latency: 0, role: 'Manager', salesRepository, today: '2026-07-17' })
    const input = {
      accountId: 'ACC-001', siteId: 'SITE-001', owner: 'person002@crm.example.invalid', qualificationConfirmed: true,
      amount: '1200000.00', amountCny: '1200000.00', intentScore: 40, poDate: '2026-12-31', toolType: 'Inspection', saleType: 'New Equipment',
      subRegion: 'East China', currency: 'CNY',
    }

    const created = (await owner.createStrategyOpportunity({ ...input, title: 'Owner sets a level', probabilityLevel: 'pipeline' })).data
    expect(created).toMatchObject({
      probabilityLevel: 'pipeline',
      probabilityHistory: [{ from: '', to: 'pipeline', actor: 'person002@crm.example.invalid', at: '2026-07-17T02:30:00.000Z' }],
    })
    expect(created).not.toHaveProperty('probability')
    expect(created).not.toHaveProperty('forecast')

    const raised = (await owner.updateStrategyOpportunity(created.id, { probabilityLevel: 'upside' })).data
    expect(raised.probabilityHistory.map((entry) => [entry.from, entry.to])).toEqual([['pipeline', 'upside'], ['', 'pipeline']])
    expect(raised.history.map((entry) => entry.field)).not.toContain('probabilityLevel')

    const intentOnly = (await owner.updateStrategyOpportunity(created.id, { intentScore: 95 })).data
    expect(intentOnly).toMatchObject({ score: 95, probabilityLevel: 'upside' })
    expect(intentOnly.probabilityHistory).toHaveLength(2)

    await expect(owner.updateStrategyOpportunity(created.id, { probabilityLevel: 'certain' as never }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    await expect(manager.updateStrategyOpportunity(created.id, { probabilityLevel: 'low_probability' }))
      .rejects.toMatchObject({ code: 'PERMISSION_DENIED', message: 'Only the Opportunity owner can set the probability level.' })
    expect((await manager.updateStrategyOpportunity(created.id, { title: 'Manager edit keeps the level' })).data)
      .toMatchObject({ title: 'Manager edit keeps the level', probabilityLevel: 'upside' })
    // A Manager opening an Opportunity for Sales sets its first level; a new one is never left pending.
    expect((await manager.createStrategyOpportunity({ ...input, title: 'Manager picks a level', probabilityLevel: 'committed' })).data)
      .toMatchObject({ owner: 'person002@crm.example.invalid', probabilityLevel: 'committed', probabilityHistory: [{ from: '', to: 'committed', actor: 'person029@crm.example.invalid' }] })
    await expect(manager.createStrategyOpportunity({ ...input, title: 'No level', probabilityLevel: '' }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR', fieldErrors: { probabilityLevel: 'Required' } })
    expect((await owner.getStrategyOpportunity(created.id)).data.probabilityHistory).toHaveLength(2)

    // A set level never returns to pending, even at the first milestone.
    expect((await owner.getStrategyOpportunity(created.id)).data.stage).toBe('qualified_opportunity')
    await expect(owner.updateStrategyOpportunity(created.id, { probabilityLevel: '' }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR', fieldErrors: { probabilityLevel: 'Required' } })
    // Lowering it needs a reason, which is kept on the level history row and nowhere else.
    await expect(owner.updateStrategyOpportunity(created.id, { probabilityLevel: 'pipeline', probabilityReason: '   ' }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR', fieldErrors: { probabilityReason: 'Required' } })
    const lowered = (await owner.updateStrategyOpportunity(created.id, { probabilityLevel: 'pipeline', probabilityReason: ' 客户预算推迟 ', probabilityActionPlan: 'Meet procurement' }, (await owner.getStrategyOpportunity(created.id)).data.modified)).data
    expect(lowered.probabilityHistory).toHaveLength(3)
    expect(lowered.probabilityHistory[0]).toMatchObject({ from: 'upside', to: 'pipeline', reason: '客户预算推迟' })
    expect(lowered).not.toHaveProperty('probabilityReason')
    expect(lowered.history.map((entry) => entry.field)).not.toContain('probabilityReason')
  })

  it('keeps the success probability when the stage advances or rolls back', async () => {
    const before = (await api.getStrategyOpportunity('OPP-003')).data
    const levelHistory = structuredClone(before.probabilityHistory)
    expect(before.probabilityLevel).toBe('committed')
    expect(levelHistory).toHaveLength(2)
    const contact = (await api.listContacts({ accountId: 'ACC-002', pageSize: 100 })).data.items.find((item) => item.status === 'Active')!

    const received = (await api.confirmPo('OPP-003', {
      booking: { primaryContactId: contact.id, equipment: 'HBM AOI', quantity: 1, ddl: '2026-11-12', amount: '32500000.00', currency: 'CNY', owner: 'person002@crm.example.invalid', note: '' }, actualPoDate: '2026-07-15',
    })).data
    expect(received).toMatchObject({ stage: 'po_received', probabilityLevel: 'committed', liveBooking: { status: 'Confirmed' } })
    expect(received.probabilityHistory).toEqual(levelHistory)

    await expect(api.rollbackOpportunityStage('OPP-003', { targetStage: 'quotation_sent', reason: '客户撤回 PO' }))
      .rejects.toMatchObject({ code: 'CONFLICT', message: 'Cancel the Booking before rolling the Opportunity back.' })
    const booking = (await api.listBookings({ pageSize: 100 })).data.items.find((item) => item.id === received.liveBooking!.id)!
    await api.updateBooking(booking.id, { ...booking, status: 'Cancelled' } as never)
    const rolledBack = (await api.rollbackOpportunityStage('OPP-003', { targetStage: 'quotation_sent', reason: '客户撤回 PO' })).data
    expect(rolledBack).toMatchObject({ stage: 'quotation_sent', probabilityLevel: 'committed', liveBooking: null })
    expect(rolledBack.probabilityHistory).toEqual(levelHistory)
    expect(rolledBack.history.map((entry) => entry.field)).not.toContain('probability')
  })

  it('filters by success probability and keeps weighted values out of pipeline and dashboard reads', async () => {
    const ids = async (probabilityLevel: 'All' | 'pending' | 'upside' | 'committed') =>
      (await api.listStrategyOpportunities({ probabilityLevel, pageSize: 100 })).data.items.map((item) => item.id).sort()

    expect(await ids('committed')).toEqual(['OPP-003'])
    expect(await ids('upside')).toEqual(['OPP-001'])
    expect(await ids('pending')).toEqual(['OPP-006', 'OPP-007'])
    expect(await ids('All')).toEqual((await api.listStrategyOpportunities({ pageSize: 100 })).data.items.map((item) => item.id).sort())

    const pipeline = (await api.listPipeline({})).data
    expect(pipeline.opportunities.find((item) => item.id === 'OPP-001')).toMatchObject({ probabilityLevel: 'upside' })
    expect(pipeline.opportunities.every((item) => !('probability' in item))).toBe(true)
    expect(cnyTotals(pipeline)).not.toHaveProperty('weightedPipeline')

    const dashboard = (await api.getDashboard({ range: 'quarter' })).data
    expect(cnyKpis(dashboard)).not.toHaveProperty('weightedPipeline')
    expect(dashboard.funnel.every((row) => !('weightedAmount' in row))).toBe(true)
    expect(dashboard.ownerPerformance.every((row) => !('weightedPipeline' in row))).toBe(true)
  })

  it('registers trimmed custom account segments globally without duplicates', async () => {
    const customSegment = 'Power Semiconductor'
    const first = await api.createAccount({
      name: '功率半导体客户一', shortName: 'Power One', segment: `  ${customSegment}  `, tier: 'A',
      city: '上海', region: '华东', owner: 'person002@crm.example.invalid',
    })
    expect(first.data.segment).toBe(customSegment)
    expect((await api.listAccountSegments()).data.filter((item) => item === customSegment)).toHaveLength(1)

    const second = await api.createAccount({
      name: '功率半导体客户二', shortName: 'Power Two', segment: customSegment, tier: 'B',
      city: '苏州', region: '华东', owner: 'person005@crm.example.invalid',
    })
    await api.updateAccount(second.data.id, {
      name: second.data.name, shortName: second.data.shortName, segment: ` ${customSegment} `, tier: second.data.tier,
      city: second.data.city, region: second.data.region, owner: second.data.owner,
    }, second.data.modified)
    expect((await api.listAccountSegments()).data.filter((item) => item === customSegment)).toHaveLength(1)

    await expect(api.createAccount({
      name: '空领域客户', shortName: 'Blank Segment', segment: '   ', tier: 'A',
      city: '上海', region: '华东', owner: 'person002@crm.example.invalid',
    })).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
  })

  it('stores regions in English, shares custom regions and filters by any spelling', async () => {
    const east = await api.createAccount({
      name: '区域客户华东', shortName: 'Region East', segment: 'Frontend', tier: 'A',
      city: '上海', region: '华东区', owner: 'person002@crm.example.invalid',
    })
    expect(east.data.region).toBe('East China')

    const custom = await api.createAccount({
      name: '区域客户东南亚', shortName: 'Region SEA', segment: 'Frontend', tier: 'B',
      city: 'Singapore', region: '  Southeast   Asia ', owner: 'person005@crm.example.invalid',
    })
    const updated = await api.updateAccount(custom.data.id, {
      name: custom.data.name, shortName: custom.data.shortName, segment: custom.data.segment, tier: custom.data.tier,
      city: custom.data.city, region: 'south-east asia', owner: custom.data.owner,
    }, custom.data.modified)
    expect(updated.data.region).toBe('Southeast Asia')
    const regions = (await api.listAccountRegions()).data
    expect(regions.slice(0, 5)).toEqual(['East China', 'South China', 'West China', 'North China', 'Central China'])
    expect(regions.filter((item) => item === 'Southeast Asia')).toHaveLength(1)

    await expect(api.createAccount({
      name: '区域客户东北', shortName: 'Region NE', segment: 'Frontend', tier: 'A',
      city: '沈阳', region: '东北', owner: 'person002@crm.example.invalid',
    })).rejects.toMatchObject({ code: 'VALIDATION_ERROR', fieldErrors: { region: 'Use an English region name' } })
    const filtered = (await api.listAccounts({ search: 'Region', region: 'southeast asia', pageSize: 100 })).data.items
    expect(filtered.map((item) => item.id)).toEqual([custom.data.id])

    const opportunity = await api.createStrategyOpportunity({
      accountId: 'ACC-001', siteId: 'SITE-001', title: '区域归一商机', owner: 'person002@crm.example.invalid',
      qualificationConfirmed: true, probabilityLevel: 'pipeline', amount: '1000000.00', amountCny: '1000000.00', intentScore: 30,
      poDate: '2026-12-31', toolType: 'Inspection', saleType: 'New Tool', subRegion: '华北区', currency: 'CNY',
    })
    expect(opportunity.data.subRegion).toBe('North China')
    await expect(api.updateStrategyOpportunity(opportunity.data.id, { subRegion: 'Mars' }, opportunity.data.modified))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR', fieldErrors: { subRegion: 'Unknown region' } })
  })

  it('completes opportunity stakeholder and action CRUD with stable ids', async () => {
    const stakeholder = await api.createOpportunityStakeholder('OPP-001', {
      contactId: 'CON-001',
      role: 'Technical Champion', influence: 'High', stance: 'Support', coverage: 'Strong',
    })
    expect(stakeholder.data.id).toMatch(/^STK-/)
    const { id: stakeholderId, name: _stakeholderName, title: _stakeholderTitle, ...stakeholderInput } = stakeholder.data
    const editedStakeholder = await api.updateOpportunityStakeholder('OPP-001', stakeholderId, { ...stakeholderInput, stance: 'Neutral' })
    expect(editedStakeholder.data.stance).toBe('Neutral')

    const action = await api.createOpportunityAction('OPP-001', {
      title: '确认客户验收窗口', owner: 'person002@crm.example.invalid', due: '2026-08-01', status: 'Open',
    })
    expect(action.data.id).toMatch(/^ACT-/)
    const { id: actionId, ...actionInput } = action.data
    const editedAction = await api.updateOpportunityAction('OPP-001', actionId, { ...actionInput, status: 'Done' })
    expect(editedAction.data.status).toBe('Done')

    await api.deleteOpportunityStakeholder('OPP-001', stakeholder.data.id)
    await api.deleteOpportunityAction('OPP-001', action.data.id)
    const opportunity = (await api.listStrategyOpportunities()).data.items.find((item) => item.id === 'OPP-001')!
    expect(opportunity.stakeholders.some((item) => item.id === stakeholder.data.id)).toBe(false)
    expect(opportunity.actions.some((item) => item.id === action.data.id)).toBe(false)
  })

  it('expands Opportunity people from the Contact master after edits', async () => {
    const admin = createMockApi({ role: 'Manager', latency: 0 })
    const opportunity = (await admin.listStrategyOpportunities()).data.items[0]
    const contact = (await admin.createContact(contactInput({ accountId: opportunity.accountId, name: 'Original master contact' }))).data
    const person = (await admin.createOpportunityStakeholder(opportunity.id, {
      contactId: contact.id,
      role: 'Coach',
      influence: 'Medium',
      stance: 'Support',
      coverage: 'Direct access',
    })).data

    await admin.updateContact(contact.id, {
      accountId: contact.accountId,
      ...(contact.siteId ? { siteId: contact.siteId } : {}),
      name: 'Updated master contact',
      title: contact.title,
      department: contact.department || 'Migrated data review',
      ...(contact.phone ? { phone: contact.phone } : {}),
      ...(contact.email ? { email: contact.email } : {}),
      ...(contact.reportsToContactId ? { reportsToContactId: contact.reportsToContactId } : {}),
      relationship: contact.relationship,
      owner: contact.owner,
      status: contact.status,
    })

    const refreshed = (await admin.listStrategyOpportunities()).data.items.find((item) => item.id === opportunity.id)!
    expect(refreshed.stakeholders.find((item) => item.contactId === person.contactId)?.name)
      .toBe('Updated master contact')
  })

  it('rejects duplicate or inactive Contact links for one Opportunity', async () => {
    const admin = createMockApi({ role: 'Manager', latency: 0 })
    const opportunity = (await admin.listStrategyOpportunities()).data.items[0]
    const active = await admin.createContact(contactInput({ accountId: opportunity.accountId, name: 'Existing stakeholder' }))
    const existing = (await admin.createOpportunityStakeholder(opportunity.id, {
      contactId: active.data.id,
      role: 'Coach',
      influence: 'Medium',
      stance: 'Support',
      coverage: 'Direct access',
    })).data
    const inactive = await admin.createContact(contactInput({ accountId: opportunity.accountId, name: 'Former employee', status: 'Left Company' }))

    await expect(admin.createOpportunityStakeholder(opportunity.id, {
      contactId: existing.contactId,
      role: 'Influencer', influence: 'Medium', stance: 'Neutral', coverage: 'Duplicate check',
    })).rejects.toMatchObject({ code: 'CONFLICT' })
    await expect(admin.createOpportunityStakeholder(opportunity.id, {
      contactId: inactive.data.id,
      role: 'Influencer', influence: 'Medium', stance: 'Neutral', coverage: 'Inactive check',
    })).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
  })

  it('rejects invalid Opportunity Contact links and keeps the Contact master after link deletion', async () => {
    const admin = createMockApi({ role: 'Manager', latency: 0 })
    const opportunity = (await admin.listStrategyOpportunities()).data.items[0]
    const contacts = (await admin.listContacts({ page: 1, pageSize: 100 })).data.items
    const crossAccount = contacts.find((contact) => contact.accountId !== opportunity.accountId)!

    await expect(admin.createOpportunityStakeholder(opportunity.id, {
      contactId: 'missing-contact', role: 'Influencer', influence: 'Medium', stance: 'Neutral', coverage: 'Missing contact',
    })).rejects.toMatchObject({ code: 'NOT_FOUND' })
    await expect(admin.createOpportunityStakeholder(opportunity.id, {
      contactId: crossAccount.id, role: 'Influencer', influence: 'Medium', stance: 'Neutral', coverage: 'Cross account',
    })).rejects.toMatchObject({ code: 'CONFLICT' })

    const linkedContact = await admin.createContact(contactInput({ accountId: opportunity.accountId, name: 'Linked master' }))
    const link = (await admin.createOpportunityStakeholder(opportunity.id, {
      contactId: linkedContact.data.id,
      role: 'Coach',
      influence: 'Medium',
      stance: 'Support',
      coverage: 'Direct access',
    })).data
    await admin.deleteOpportunityStakeholder(opportunity.id, link.id)
    await expect(admin.getContact(link.contactId)).resolves.toMatchObject({ data: { contact: { id: link.contactId } } })
  })

  it('clears Contact links that become invalid after an Opportunity account change', async () => {
    const admin = createMockApi({ role: 'Manager', latency: 0 })
    const opportunity = (await admin.listStrategyOpportunities()).data.items[0]
    const nextAccount = (await admin.listAccounts({ page: 1, pageSize: 100 })).data.items
      .find((account) => account.id !== opportunity.accountId)!
    const nextSite = (await admin.getAccount360(nextAccount.id)).data.sites[0]

    await admin.updateStrategyOpportunity(opportunity.id, { accountId: nextAccount.id, siteId: nextSite.id })

    const updated = (await admin.listStrategyOpportunities()).data.items.find((item) => item.id === opportunity.id)!
    expect(updated.stakeholders).toEqual([])
  })

  it('blocks CRM writes for equipment engineers', async () => {
    const engineer = createMockApi({ latency: 0, role: 'Engineer', assignedAccountIds: ['ACC-001'] })
    await expect(engineer.createStrategyOpportunity({
      accountId: 'ACC-001', siteId: 'SITE-001', title: '越权商机', owner: 'person053@crm.example.invalid', qualificationConfirmed: true,
      amount: '1.00', amountCny: '1.00', intentScore: 10, poDate: '2026-12-01', toolType: 'AOI', saleType: 'New Tool', subRegion: '华东', currency: 'CNY',
    })).rejects.toMatchObject({ code: 'PERMISSION_DENIED' })
  })

  it('enforces own and assigned record scopes while Manager remains global', async () => {
    const sales = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01' })
    const salesAccounts = await sales.listAccounts({ page: 1, pageSize: 100 })
    expect(salesAccounts.data.items.length).toBeGreaterThan(0)
    expect(salesAccounts.data.items).toHaveLength(3)
    await expect(sales.getAccount360('ACC-006')).rejects.toMatchObject({ code: 'SCOPE_DENIED' })
    await expect(sales.createVisit({ accountId: 'ACC-006', subject: '越权', date: '2026-07-21', type: 'Phone', owner: 'person002@crm.example.invalid', objective: '越权' }))
      .rejects.toMatchObject({ code: 'SCOPE_DENIED' })

    const manager = createMockApi({ latency: 0, role: 'Manager', userName: 'Demo Staff 06' })

    const fae = createMockApi({ latency: 0, role: 'Engineer', assignedAccountIds: ['ACC-001'] })
    const evaluations = await fae.listEvaluations({})
    expect(evaluations.data.items.map((item) => item.id)).toEqual(['EVAL-101', 'EVAL-103', 'EVAL-105'])
    await expect(fae.addEvaluationRun('EVAL-102', { date: '2026-07-17', lot: 'LOT-SCOPE', wafers: 1, capture: null, falsePositive: null, wph: null, summary: '' }))
      .rejects.toMatchObject({ code: 'SCOPE_DENIED' })
  })

  it('keeps Private Accounts hidden from non-owner Sales', async () => {
    const sales = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01' })
    const accounts = (await sales.listAccounts({ page: 1, pageSize: 100 })).data.items
    expect(accounts.some((account) => account.id === 'ACC-003')).toBe(false)
    await expect(sales.getAccount360('ACC-003')).rejects.toMatchObject({ code: 'SCOPE_DENIED' })
  })
  it('adds a newly created customer city to the shared city dictionary', async () => {
    const sales = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01' })
    await sales.createAccount({
      name: '昆山城市联动客户', shortName: '昆山联动', segment: 'Frontend', tier: 'A',
      city: '昆山', region: '华东', owner: 'person002@crm.example.invalid',
    })

    expect((await sales.listAccountCities()).data).toContain('昆山')
  })

  it('scopes the full Demo lifecycle by its unique Sales and Engineer owners', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)

    const sales = createMockApi({ repository, latency: 0, role: 'Sales', userName: 'Demo Staff 01' })
    const salesWorkflows = (await sales.listDemoWorkflows()).data.items
    expect(salesWorkflows).toHaveLength(5)
    expect(salesWorkflows.every((item) => item.salesOwner === 'person002@crm.example.invalid')).toBe(true)

    const fae = createMockApi({
      repository,
      latency: 0,
      role: 'Engineer',
      userName: '演示员工14',
      assignedAccountIds: ['ACC-001', 'ACC-005', 'ACC-006'],
    })
    const faeWorkflows = (await fae.listDemoWorkflows()).data.items
    expect(faeWorkflows).toHaveLength(5)
    expect(faeWorkflows.every((item) => item.engineerOwner === 'person077@crm.example.invalid')).toBe(true)
    expect((await fae.listDemoRequests({})).data.items.every((item) => item.engineerOwner === 'person077@crm.example.invalid')).toBe(true)
    expect((await fae.listEvaluations({})).data.items.every((item) => item.owner === 'person077@crm.example.invalid')).toBe(true)

    expect(salesWorkflows[0]).toEqual(expect.objectContaining({
      salesOwner: expect.any(String),
      engineerOwner: expect.any(String),
      equipment: expect.any(String),
    }))
  })

  it('persists scoped Demo comments with the active user and newest-first order', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    const administrator = createMockApi({
      repository,
      latency: 0,
      role: 'Manager',
      userName: '演示员工24',
    })

    const seeded = await administrator.listDemoComments('DR-105')
    expect(seeded.data.items.length).toBeGreaterThanOrEqual(2)

    const created = await administrator.addDemoComment('DR-105', { body: '  内部评审材料已准备完成。  ' })
    expect(created.data).toMatchObject({
      demoRequestId: 'DR-105',
      author: 'person029@crm.example.invalid',
      role: 'Manager',
      body: '内部评审材料已准备完成。',
    })

    const reloaded = createMockApi({ repository, latency: 0, role: 'Manager' })
    expect((await reloaded.listDemoComments('DR-105')).data.items[0].id).toBe(created.data.id)
    await expect(administrator.addDemoComment('DR-105', { body: '   ' }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    await expect(administrator.listDemoComments('DR-NOT-FOUND'))
      .rejects.toMatchObject({ code: 'NOT_FOUND' })
  })

  it('uses the two real engineer identities and excludes every legacy archive case', async () => {
    const zhou = createMockApi({ latency: 0, role: 'Engineer' })
    const sun = createMockApi({ latency: 0, role: 'Engineer', userName: '演示员工15' })
    const administrator = createMockApi({ latency: 0, role: 'Manager' })

    expect((await zhou.listDemoRequests({})).data.items).toHaveLength(5)
    expect((await zhou.listEvaluations({})).data.items.map((item) => item.id)).toEqual(['EVAL-101', 'EVAL-103', 'EVAL-105'])
    expect((await sun.listDemoRequests({})).data.items).toHaveLength(5)
    expect((await sun.listEvaluations({})).data.items.map((item) => item.id)).toEqual(['EVAL-102', 'EVAL-104', 'EVAL-106'])
    expect((await administrator.listDemoWorkflows()).data.items.map((item) => item.id)).toEqual([
      'DR-101', 'DR-102', 'DR-103', 'DR-104', 'DR-105',
      'DR-106', 'DR-107', 'DR-108', 'DR-109', 'DR-110',
    ])
  })

  it('rejects free-text owner values at the API boundary', async () => {
    const invalidEngineer = completeDemoRequestForm()
    invalidEngineer.demoOwner = 'FAE Mia'
    const invalidSales = completeDemoRequestForm()
    invalidSales.salesContact = 'Other Sales'

    const engineerOpportunity = await createEligibleDemoOpportunity(api, 'invalid-engineer')
    const salesOpportunity = await createEligibleDemoOpportunity(api, 'invalid-sales')
    await expect(api.createDemoRequest({
      accountId: 'ACC-001', primaryContactId: 'CON-001', opportunityId: engineerOpportunity.id, requestMode: 'Opportunity', formData: invalidEngineer, customerExpectedDate: '2026-09-01', submit: true,
    })).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    await expect(api.createDemoRequest({
      accountId: 'ACC-001', primaryContactId: 'CON-001', opportunityId: salesOpportunity.id, requestMode: 'Opportunity', formData: invalidSales, customerExpectedDate: '2026-09-01', submit: true,
    })).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })

    await expect(api.transitionDemoRequest('DR-101', {
      type: 'engineer_approve',
      engineerOwner: 'FAE Mia',
      testPlan: 'Baseline recipe',
      assignedEquipment: 'Lab-01',
      resourceWindow: '2026-08-01 ~ 2026-08-10',
      estimatedCompletionDate: '2026-08-12',
      technicalRisk: 'Low',
      comment: 'Ready',
    })).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
  })

  it('does not let an engineer transfer an assigned Demo to the other engineer', async () => {
    const zhou = createMockApi({ latency: 0, role: 'Engineer', userName: '演示员工14' })

    await expect(zhou.transitionDemoRequest('DR-101', {
      type: 'engineer_approve',
      engineerOwner: 'person053@crm.example.invalid',
      testPlan: 'Baseline recipe',
      assignedEquipment: 'Lab-01',
      resourceWindow: '2026-08-01 ~ 2026-08-10',
      estimatedCompletionDate: '2026-08-12',
      technicalRisk: 'Low',
      comment: 'Ready',
    })).rejects.toMatchObject({ code: 'SCOPE_DENIED' })
  })

  it('converts one approved Demo Request into exactly one Evaluation', async () => {
    api = createMockApi({ latency: 0, role: 'Manager', today: '2026-07-17' })
    const approved = await api.transitionDemoRequest('DR-104', { type: 'manager_approve', comment: '批准进入 Demo' })

    expect(approved.data.request.status).toBe('Converted')
    expect(approved.data.request.approvedBy).toBe('person029@crm.example.invalid')
    expect(approved.data.request.approvedDate).toBe('2026-07-17')
    expect(approved.data.evaluation?.demoRequestId).toBe('DR-104')
    expect(approved.data.evaluation?.wafers).toBe(0)
    await expect(api.transitionDemoRequest('DR-104', { type: 'manager_approve', comment: '再次批准' }))
      .rejects.toMatchObject({ code: 'REPORT_NOT_READY' })
  })

  it('updates a Draft Demo Request before submission and allows cancellation', async () => {
    const editableOpportunity = await createEligibleDemoOpportunity(api, 'editable')
    const editable = await api.createDemoRequest({
      accountId: 'ACC-001', primaryContactId: 'CON-001', opportunityId: editableOpportunity.id, requestMode: 'Opportunity', formData: completeDemoRequestForm(), customerExpectedDate: '2026-09-01', submit: false,
    })
    const updated = await api.updateDemoRequest(editable.data.id, {
      accountId: 'ACC-001', primaryContactId: 'CON-001', opportunityId: editableOpportunity.id, requestMode: 'Opportunity', formData: completeDemoRequestForm(), customerExpectedDate: '', submit: true,
    })
    expect(updated.data).toMatchObject({
      status: 'Engineer Review',
      sampleQuantity: 1,
      title: '示例企业014有限公司 · Macro Inspection X8 Demo',
      preparedBy: 'person029@crm.example.invalid',
      preparedDate: '2026-07-17',
    })

    const cancellableOpportunity = await createEligibleDemoOpportunity(api, 'cancellable')
    const cancellable = await api.createDemoRequest({
      accountId: 'ACC-001', primaryContactId: 'CON-001', opportunityId: cancellableOpportunity.id, requestMode: 'Opportunity', formData: completeDemoRequestForm(), customerExpectedDate: '2026-09-01', submit: false,
    })
    const cancelled = await api.transitionDemoRequest(cancellable.data.id, { type: 'cancel', comment: '客户暂缓' })
    expect(cancelled.data.request.status).toBe('Cancelled')
  })

  it('rejects illegal Evaluation jumps and keeps terminal acceptance consistent', async () => {
    await expect(api.updateEvaluationStatus('EVAL-103', { status: 'Requested' }))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION' })

    await api.releaseDemoTestReport('EVAL-103', reportFiles('results.txt', 'capture=96', 'text/plain'))
    const internal = await api.updateEvaluationStatus('EVAL-103', { status: 'Internal Review' })
    const review = await api.updateEvaluationStatus('EVAL-103', { status: 'Customer Review' })
    const accepted = await api.updateEvaluationStatus('EVAL-103', { status: 'Accepted', customerComment: '客户确认留痕' })
    expect(internal.data.acceptance).toBe('Pending')
    expect(review.data.acceptance).toBe('Pending')
    expect(accepted.data.acceptance).toBe('Accepted')
    await expect(api.updateEvaluationStatus('EVAL-103', { status: 'Testing' }))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION' })
  })

  it('adds a traceable wafer Test Run and recomputes the wafer total', async () => {
    const result = await api.addEvaluationRun('EVAL-103', {
      date: '2026-07-17', lot: 'LOT-03', wafers: 4,
      capture: 97, falsePositive: 2.1, wph: 35, summary: '达标',
    })

    expect(result.data.runs.at(-1)).toMatchObject({ id: 'EVAL-103-R03', status: 'Completed' })
    expect(result.data.wafers).toBe(result.data.runs.reduce((sum, run) => sum + run.wafers, 0))
  })

  it('keeps empty-metric runs Planned and requires a summary for completed runs', async () => {
    const planned = await api.addEvaluationRun('EVAL-103', {
      date: '2026-07-17', lot: 'LOT-PLANNED', wafers: 1,
      capture: null, falsePositive: null, wph: null, summary: '',
    })
    expect(planned.data.runs.at(-1)?.status).toBe('Planned')

    await expect(api.addEvaluationRun('EVAL-103', {
      date: '2026-07-17', lot: 'LOT-COMPLETE', wafers: 1,
      capture: 97, falsePositive: 2.1, wph: 35, summary: '   ',
    })).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
  })

  it('rejects invalid or incomplete Test Run metrics', async () => {
    const base = { date: '2026-07-17', lot: 'LOT-BAD', wafers: 1, capture: 101, falsePositive: 2, wph: 35, summary: '' }
    await expect(api.addEvaluationRun('EVAL-103', base)).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    await expect(api.addEvaluationRun('EVAL-103', { ...base, capture: 95, falsePositive: null, wph: null })).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    await expect(api.addEvaluationRun('EVAL-103', { ...base, capture: null, falsePositive: null, wph: null, wafers: Number.NaN })).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    await expect(api.addEvaluationRun('EVAL-103', { ...base, date: '2026-02-31', capture: null, falsePositive: null, wph: null })).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
  })

  it('shows all requests to Manager and allows only Manager approval across API clients', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    const manager = createMockApi({ repository, latency: 0, role: 'Manager', userName: '演示经理01' })
    const sales = createMockApi({ repository, latency: 0, role: 'Sales', userName: 'Demo Staff 01' })

    const managerRequests = (await manager.listDemoRequests({})).data.items
    const salesRequests = (await sales.listDemoRequests({})).data.items
    expect(managerRequests.length).toBeGreaterThan(salesRequests.length)
    await expect(sales.transitionDemoRequest('DR-104', { type: 'manager_approve', comment: 'Unauthorized' }))
      .rejects.toMatchObject({ code: 'PERMISSION_DENIED' })

    const approved = await manager.transitionDemoRequest('DR-104', { type: 'manager_approve', comment: 'Approved' })
    expect(approved.data.request.approvedBy).toBe('person073@crm.example.invalid')
    expect(approved.data.request.history[0]).toMatchObject({ actor: 'person073@crm.example.invalid' })
    expect((await manager.listEvaluations({})).data.items.some((item) => item.demoRequestId === 'DR-104')).toBe(true)
  })

  it('allows the Demo-only Administrator exception to approve and upload reports', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    const administrator = createMockApi({ repository, latency: 0, role: 'Manager', userName: 'Demo Staff 04' })

    const approved = await administrator.transitionDemoRequest('DR-104', { type: 'manager_approve', comment: 'Admin approval' })
    expect(approved.data.request).toMatchObject({ status: 'Converted', approvedBy: 'person029@crm.example.invalid' })

    const uploaded = await administrator.releaseDemoTestReport('EVAL-103', reportFiles('admin-report.pdf', 'pdf'))
    await administrator.updateEvaluationStatus('EVAL-103', { status: 'Internal Review' })
    await administrator.updateEvaluationStatus('EVAL-103', { status: 'Customer Review' })
    expect(uploaded.data.internalReportArtifact).toMatchObject({ createdBy: 'person029@crm.example.invalid', type: 'Test Report', visibility: 'Internal' })
  })

  it('constructs the application Mock API with the shared repository singleton', async () => {
    vi.resetModules()
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    const createMockApiSpy = vi.fn(() => ({ source: 'shared-mock' }))
    vi.doMock('@/demo/demo-repository', async (importOriginal) => ({
      ...await importOriginal<typeof import('@/demo/demo-repository')>(),
      getSharedDemoRepository: () => repository,
    }))
    vi.doMock('./mock-adapter', () => ({ createMockApi: createMockApiSpy }))

    const applicationApi = (await import('./index')).api

    expect(createMockApiSpy).toHaveBeenCalledWith(expect.objectContaining({ repository }))
    expect(applicationApi).toEqual({ source: 'shared-mock' })
    vi.doUnmock('@/demo/demo-repository')
    vi.doUnmock('./mock-adapter')
    vi.resetModules()
  })

  it('persists Test Run DDL with validation and a customer-date warning', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    const fae = createMockApi({ repository, latency: 0, role: 'Engineer', assignedAccountIds: ['ACC-001'] })
    const sales = createMockApi({ repository, latency: 0, role: 'Sales', userName: 'Demo Staff 02' })

    for (const testRunDeadline of ['', '2026-07-16', '2026-09-31', '2026-13-01']) {
      await expect(fae.setEvaluationTestRunDeadline('EVAL-103', { testRunDeadline }))
        .rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    }
    // Far in the future: a fixed near date stops being valid once that day is past in Shanghai.
    const saved = await fae.setEvaluationTestRunDeadline('EVAL-103', { testRunDeadline: '2099-12-31' })
    expect(saved.data.testRunDeadline).toBe('2099-12-31')
    expect(saved.warnings).toContain('Test Run DDL 晚于客户预期时间，请 Sales 与客户沟通')
    expect((await sales.listEvaluations({})).data.items.find((item) => item.id === 'EVAL-103')?.testRunDeadline)
      .toBe('2099-12-31')
  })

  it('does not warn when the customer expected date is empty or invalid', async () => {
    for (const customerExpectedDate of ['', '2026-09-31']) {
      const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
      await repository.transact((snapshot) => {
        snapshot.demoRequests.find((item) => item.id === 'DR-107')!.customerExpectedDate = customerExpectedDate
      })
      const fae = createMockApi({ repository, latency: 0, role: 'Engineer', assignedAccountIds: ['ACC-001'] })

      const saved = await fae.setEvaluationTestRunDeadline('EVAL-103', { testRunDeadline: '2099-12-31' })
      expect(saved.warnings).toEqual([])
    }
  })

  it('keeps FAE and Engineer Evaluation writes equivalent', async () => {
    for (const role of ['Engineer'] as const) {
      const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
      const targetId = role === 'Engineer' ? 'EVAL-103' : 'EVAL-102'
      const owner = role === 'Engineer' ? '演示员工14' : '演示员工15'
      await repository.transact((snapshot) => {
        snapshot.evaluations.find((item) => item.id === targetId)!.status = 'Testing'
      })
      const engineer = createMockApi({ repository, latency: 0, role, userName: owner, assignedAccountIds: ['ACC-001'] })

      await expect(engineer.addEvaluationRun(targetId, {
        date: '2026-07-17', lot: 'LOT-ROLE', wafers: 1,
        capture: null, falsePositive: null, wph: null, summary: '',
      })).resolves.toBeDefined()
      await expect(engineer.setEvaluationTestRunDeadline(targetId, { testRunDeadline: '2099-08-20' }))
        .resolves.toBeDefined()
    }
  })

  it('requires both Test Reports and a completed Test Run before Internal Review', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      const evaluation = snapshot.evaluations.find((item) => item.id === 'EVAL-103')!
      evaluation.status = 'Testing'
      evaluation.runs = []
    })
    const engineer = createMockApi({ repository, latency: 0, role: 'Engineer', userName: '演示员工14', assignedAccountIds: ['ACC-001', 'ACC-006'] })

    await expect(engineer.updateEvaluationStatus('EVAL-103', { status: 'Internal Review' }))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION', message: '请先完成第 1 轮 Test Run，之前轮次的 Test Run 不计入。' })
    await engineer.releaseDemoTestReport('EVAL-103', reportFiles('results.csv', 'metric,value\ncapture,96', 'text/csv'))
    await expect(engineer.updateEvaluationStatus('EVAL-103', { status: 'Internal Review' }))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION', message: '请先完成第 1 轮 Test Run，之前轮次的 Test Run 不计入。' })
    await engineer.addEvaluationRun('EVAL-103', {
      date: '2026-08-20', lot: 'LOT-COMPLETE', wafers: 1,
      capture: 96, falsePositive: 1, wph: 12, summary: 'Passed',
    })
    await expect(engineer.updateEvaluationStatus('EVAL-103', { status: 'Internal Review' }))
      .resolves.toMatchObject({ data: { status: 'Internal Review' } })
  })

  it('persists artifacts, enforces visibility, and uploads versioned arbitrary Test Reports', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      snapshot.evaluations.find((item) => item.id === 'EVAL-104')!.status = 'Testing'
    })
    const sales = createMockApi({ repository, latency: 0, role: 'Sales', userName: 'Demo Staff 01' })
    const outOfScopeSales = createMockApi({ repository, latency: 0, role: 'Sales', userName: 'Demo Staff 02' })
    const engineer = createMockApi({ repository, latency: 0, role: 'Engineer', userName: '演示员工15', assignedAccountIds: ['ACC-005'] })
    const boss = createMockApi({ repository, latency: 0, role: 'Manager', userName: 'Demo Staff 09' })

    const docx = await sales.saveDemoArtifact({
      demoRequestId: 'DR-108', type: 'Demo Request DOCX', visibility: 'Internal',
      file: multipartFile('request.docx', 'docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
    })
    expect(docx.data).toMatchObject({ version: 1, createdBy: 'person002@crm.example.invalid' })
    expect((await sales.getDemoArtifact(docx.data.id)).blob.size).toBe(4)
    await expect(outOfScopeSales.getDemoArtifact(docx.data.id)).rejects.toMatchObject({ code: 'SCOPE_DENIED' })
    await expect(sales.releaseDemoTestReport('EVAL-104', reportFiles('report.pdf', 'pdf')))
      .rejects.toMatchObject({ code: 'PERMISSION_DENIED' })

    const released = await boss.releaseDemoTestReport('EVAL-104', reportFiles('report.csv', 'metric,value', 'text/csv'))
    expect(released.data.internalReportArtifact).toMatchObject({ type: 'Test Report', version: 1, createdBy: 'person073@crm.example.invalid', visibility: 'Internal' })
    const evaluation = (await boss.listEvaluations({})).data.items.find((item) => item.id === 'EVAL-104')!
    expect(evaluation).toMatchObject({ reportStatus: 'Ready', reportArtifactId: released.data.internalReportArtifact.id, reportVersion: 1 })
  })

  it('derives all scoped non-cancelled archives and classifies terminal tests as completed', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      snapshot.demoRequests.find((item) => item.id === 'DR-102')!.title = 'Repository-derived title'
      snapshot.demoRequests.find((item) => item.id === 'DR-104')!.status = 'Cancelled'
    })
    const apiClient = createMockApi({ repository, latency: 0 })

    const workflows = (await apiClient.listDemoWorkflows()).data.items
    expect(workflows.some((item) => item.id === 'DR-102' && item.title === 'Repository-derived title')).toBe(true)
    expect(workflows.find((item) => item.id === 'DR-101')?.archiveCategory).toBe('In Progress')
    expect(workflows.find((item) => item.id === 'DR-109')?.archiveCategory).toBe('Completed')
    expect(workflows.find((item) => item.id === 'DR-110')?.archiveCategory).toBe('Completed')
    expect(workflows.some((item) => item.id === 'DR-104')).toBe(false)
    expect(workflows.some((item) => item.id.startsWith('DEMO-'))).toBe(false)
  })

  it('does not expose a never-submitted request that was cancelled from Draft', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      const request = snapshot.demoRequests.find((item) => item.id === 'DR-101')!
      request.status = 'Cancelled'
      request.history = []
      request.history.push({ at: '2026-07-17T10:30:00+08:00', actor: 'person002@crm.example.invalid', from: 'Draft', to: 'Cancelled', comment: '取消未提交草稿' })
      snapshot.artifacts.push({
        id: 'ART-NEVER-SUBMITTED', demoRequestId: request.id, type: 'Demo Request DOCX', fileName: 'never-submitted.docx',
        mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', version: 1, createdBy: 'person002@crm.example.invalid',
        createdAt: '2026-07-17T10:30:00+08:00', visibility: 'Internal', blob: new Blob(['draft']),
      })
    })
    const boss = createMockApi({ repository, latency: 0, role: 'Manager' })

    expect((await boss.listDemoRequests({})).data.items.some((item) => item.id === 'DR-101')).toBe(true)
    expect((await boss.listDemoWorkflows()).data.items.some((item) => item.id === 'DR-101')).toBe(false)
    await expect(boss.getDemoArtifact('ART-NEVER-SUBMITTED')).rejects.toMatchObject({ code: 'PERMISSION_DENIED' })
  })

  it('authorizes direct artifact reads with the same release rules as the archive', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      const request = snapshot.demoRequests.find((item) => item.id === 'DR-108')!
      const evaluation = snapshot.evaluations.find((item) => item.demoRequestId === request.id)!
      request.salesOwner = 'person005@crm.example.invalid'
      snapshot.artifacts.push(
        { id: 'ART-SECRET', demoRequestId: request.id, type: 'Demo Request DOCX', fileName: 'someone-else.docx', mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', version: 1, createdBy: 'person005@crm.example.invalid', createdAt: '2026-07-16T10:30:00+08:00', visibility: 'Internal', blob: new Blob(['secret']) },
        { id: 'ART-OLD-REPORT', demoRequestId: request.id, evaluationId: evaluation.id, type: 'Test Report', fileName: 'old-report.pdf', mimeType: 'application/pdf', version: 1, createdBy: 'person029@crm.example.invalid', createdAt: '2026-07-16T10:30:00+08:00', visibility: 'Internal', blob: new Blob(['old']) },
        { id: 'ART-CURRENT-REPORT', demoRequestId: request.id, evaluationId: evaluation.id, type: 'Test Report', fileName: 'current-report.pdf', mimeType: 'application/pdf', version: 2, createdBy: 'person029@crm.example.invalid', createdAt: '2026-07-17T10:30:00+08:00', visibility: 'Internal', blob: new Blob(['current']) },
      )
      evaluation.reportStatus = 'Ready'
      evaluation.reportArtifactId = 'ART-CURRENT-REPORT'
      evaluation.reportVersion = 2
    })
    const sales = createMockApi({ repository, latency: 0, role: 'Sales', userName: 'Demo Staff 01' })

    await expect(sales.getDemoArtifact('ART-SECRET')).rejects.toMatchObject({ code: 'SCOPE_DENIED' })
    await expect(sales.getDemoArtifact('ART-CURRENT-REPORT')).rejects.toMatchObject({ code: 'SCOPE_DENIED' })
    await repository.transact((snapshot) => {
      const evaluation = snapshot.evaluations.find((item) => item.id === 'EVAL-104')!
      snapshot.demoRequests.find((item) => item.id === 'DR-108')!.salesOwner = 'person002@crm.example.invalid'
      evaluation.status = 'Testing'
    })
    await expect(sales.getDemoArtifact('ART-OLD-REPORT')).resolves.toMatchObject({ fileName: 'old-report.pdf' })
    await expect(sales.getDemoArtifact('ART-CURRENT-REPORT')).resolves.toMatchObject({
      fileName: 'current-report.pdf',
      mimeType: 'application/pdf',
      blob: expect.any(Blob),
    })
  })

  it('keeps report readiness independent from optional Test Run writes', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    const fae = createMockApi({ repository, latency: 0, role: 'Engineer', userName: '演示员工14', assignedAccountIds: ['ACC-001', 'ACC-006'] })

    expect((await fae.listEvaluations({})).data.items.find((item) => item.id === 'EVAL-103')?.reportStatus).toBe('Not Ready')
    await fae.updateEvaluationStatus('EVAL-103', { status: 'Testing' })
    const completed = await fae.addEvaluationRun('EVAL-103', {
      date: '2026-07-22', lot: 'LOT-COMPLETE', wafers: 2,
      capture: 96, falsePositive: 2, wph: 30, summary: 'Targets met.',
    })
    expect(completed.data.reportStatus).toBe('Not Ready')
  })

  it('allows Customer Review when completed runs and an uploaded report are ready', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      const evaluation = snapshot.evaluations.find((item) => item.id === 'EVAL-103')!
      evaluation.status = 'Testing'
      evaluation.reportStatus = 'Ready'
    })
    const administrator = createMockApi({ repository, latency: 0, role: 'Manager' })

    await administrator.releaseDemoTestReport('EVAL-103', reportFiles('results.txt', 'passed', 'text/plain'))
    await expect(administrator.updateEvaluationStatus('EVAL-103', { status: 'Internal Review' })).resolves.toBeDefined()
    await expect(administrator.updateEvaluationStatus('EVAL-103', { status: 'Customer Review' })).resolves.toBeDefined()
    expect((await administrator.listEvaluations({})).data.items.find((item) => item.id === 'EVAL-103')).toMatchObject({
      status: 'Customer Review', reportStatus: 'Ready',
    })
  })

  it('uploads corrected versions during Testing and blocks upload outside that stage', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      const request = snapshot.demoRequests.find((item) => item.id === 'DR-107')!
      const evaluation = snapshot.evaluations.find((item) => item.id === 'EVAL-103')!
      evaluation.status = 'Testing'
      evaluation.reportStatus = 'Ready'
      evaluation.reportVersion = 2
      evaluation.reportArtifactId = 'ART-PRIOR'
      snapshot.artifacts.push({
        id: 'ART-PRIOR', demoRequestId: request.id, evaluationId: evaluation.id,
        type: 'Test Report', fileName: 'prior.pdf', mimeType: 'application/pdf',
        version: 2, createdBy: 'person029@crm.example.invalid', createdAt: '2026-07-17T10:30:00+08:00',
        visibility: 'Internal', blob: new Blob(['prior']),
      })
    })
    const boss = createMockApi({ repository, latency: 0, role: 'Manager', userName: 'Boss' })

    const released = await boss.releaseDemoTestReport('EVAL-103', reportFiles('new.pdf', 'new'))
    expect(released.data).toMatchObject({ version: 3 })
    let snapshot = await repository.read()
    expect(snapshot.evaluations.find((item) => item.id === 'EVAL-103')).toMatchObject({
      status: 'Testing', reportStatus: 'Ready', reportVersion: 3, reportArtifactId: released.data.internalReportArtifact.id,
    })
    expect(snapshot.artifacts.filter((artifact) => artifact.type === 'Test Report')).toHaveLength(3)

    await repository.transact((draft) => {
      draft.evaluations.find((item) => item.id === 'EVAL-103')!.status = 'Customer Review'
    })
    await expect(boss.releaseDemoTestReport('EVAL-103', reportFiles('new.pdf', 'new')))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION' })
    snapshot = await repository.read()
    expect(snapshot.evaluations.find((item) => item.id === 'EVAL-103')).toMatchObject({ reportVersion: 3, reportArtifactId: released.data.internalReportArtifact.id })
    expect(snapshot.artifacts).toHaveLength(3)
  })

  it('opens a new round on retest without overwriting the previous round reports', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    const boss = createMockApi({ repository, latency: 0, role: 'Manager', userName: 'Boss' })

    await boss.releaseDemoTestReport('EVAL-103', reportFiles('round1.pdf', 'round one'))
    await boss.updateEvaluationStatus('EVAL-103', { status: 'Internal Review' })
    await boss.updateEvaluationStatus('EVAL-103', { status: 'Customer Review' })

    const retested = await boss.updateEvaluationStatus('EVAL-103', { status: 'Testing', customerComment: '误报率仍偏高，请重测' })
    expect(retested.data).toMatchObject({ status: 'Testing', testRound: 2, reportStatus: 'Not Ready' })
    // The round-1 DDL would otherwise flag the new round as overdue on day one.
    expect(retested.data.testRunDeadline).toBe('')
    // Clearing it is still a deadline change, so it leaves a Deadline row behind the retest.
    expect(retested.data.history?.[0]).toMatchObject({ eventType: 'Status', to: 'Testing' })
    expect(retested.data.history?.[1]).toMatchObject({
      eventType: 'Deadline', from: '2026-08-01', to: '', summary: 'Cleared round 1 Test Run deadline for retest',
    })
    expect(retested.data.internalReportArtifactId).toBeUndefined()
    expect(retested.data.externalReportArtifactId).toBeUndefined()
    expect(retested.data.customerReviews).toEqual([
      expect.objectContaining({ round: 1, comment: '误报率仍偏高，请重测' }),
    ])

    // The round-1 reports must survive untouched; the gate has to close again.
    let snapshot = await repository.read()
    expect(snapshot.artifacts.filter((item) => item.type === 'Test Report')).toHaveLength(2)
    await expect(boss.updateEvaluationStatus('EVAL-103', { status: 'Internal Review' }))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION' })

    await boss.releaseDemoTestReport('EVAL-103', reportFiles('round2.pdf', 'round two', 'application/pdf', 2))
    snapshot = await repository.read()
    const reports = snapshot.artifacts.filter((item) => item.type === 'Test Report')
    expect(reports).toHaveLength(4)
    expect(reports.filter((item) => item.round === 1)).toHaveLength(2)
    expect(reports.filter((item) => item.round === 2)).toHaveLength(2)
    expect(reports.map((item) => item.fileName)).toContain('[Internal] round1.pdf')
    expect(reports.map((item) => item.fileName)).toContain('[Internal] round2.pdf')

    // Round-2 reports alone are not enough: the round-1 Completed run is history,
    // so Internal Review stays closed until a run is completed in round 2.
    expect(retested.data.runs.map((run) => run.round)).toEqual([1, 1])
    await expect(boss.updateEvaluationStatus('EVAL-103', { status: 'Internal Review' }))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION' })
    const rerun = await boss.addEvaluationRun('EVAL-103', {
      date: '2026-07-30', lot: 'LOT-RETEST', wafers: 2,
      capture: 97, falsePositive: 2, wph: 36, summary: '重测通过',
    })
    expect(rerun.data.runs.map((run) => run.round)).toEqual([1, 1, 2])
    const reviewed = await boss.updateEvaluationStatus('EVAL-103', { status: 'Internal Review' })
    expect(reviewed.data).toMatchObject({ status: 'Internal Review', testRound: 2 })
  })

  it('refuses a report uploaded from a window opened before the retest', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    const boss = createMockApi({ repository, latency: 0, role: 'Manager', userName: 'Boss' })

    await boss.releaseDemoTestReport('EVAL-103', reportFiles('round1.pdf', 'round one'))
    await boss.updateEvaluationStatus('EVAL-103', { status: 'Internal Review' })
    await boss.updateEvaluationStatus('EVAL-103', { status: 'Customer Review' })
    await boss.updateEvaluationStatus('EVAL-103', { status: 'Testing', customerComment: '误报率仍偏高，请重测' })

    // The upload window still names round 1, so filing it would label round-2 work as round 1.
    await expect(boss.releaseDemoTestReport('EVAL-103', reportFiles('stale.pdf', 'from the old tab')))
      .rejects.toMatchObject({ code: 'CONFLICT' })
    let snapshot = await repository.read()
    expect(snapshot.artifacts.filter((item) => item.type === 'Test Report')).toHaveLength(2)

    await boss.releaseDemoTestReport('EVAL-103', reportFiles('round2.pdf', 'round two', 'application/pdf', 2))
    await boss.addEvaluationRun('EVAL-103', {
      date: '2026-07-30', lot: 'LOT-RETEST', wafers: 2, capture: 97, falsePositive: 2, wph: 36, summary: '重测通过',
    })
    await boss.updateEvaluationStatus('EVAL-103', { status: 'Internal Review' })
    await boss.updateEvaluationStatus('EVAL-103', { status: 'Customer Review' })

    await expect(boss.uploadCustomerReport('EVAL-103', { expectedRound: 1, file: multipartFile('stale-feedback.pdf', 'from the old tab') }))
      .rejects.toMatchObject({ code: 'CONFLICT' })
    snapshot = await repository.read()
    expect(snapshot.artifacts.filter((item) => item.type === 'Customer Report')).toHaveLength(0)

    const reloaded = await boss.uploadCustomerReport('EVAL-103', { expectedRound: 2, file: multipartFile('feedback.pdf', 'from the reloaded tab') })
    expect(reloaded.data).toMatchObject({ round: 2, version: 1 })
  })

  it('requires a customer comment to leave Customer Review', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    const boss = createMockApi({ repository, latency: 0, role: 'Manager', userName: 'Boss' })
    await boss.releaseDemoTestReport('EVAL-103', reportFiles('results.pdf', 'ok'))
    await boss.updateEvaluationStatus('EVAL-103', { status: 'Internal Review' })
    await boss.updateEvaluationStatus('EVAL-103', { status: 'Customer Review' })

    for (const status of ['Accepted', 'Testing'] as const) {
      await expect(boss.updateEvaluationStatus('EVAL-103', { status }))
        .rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
      await expect(boss.updateEvaluationStatus('EVAL-103', { status, customerComment: '   ' }))
        .rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    }

    const archived = await boss.updateEvaluationStatus('EVAL-103', { status: 'Accepted', customerComment: '客户验收通过' })
    expect(archived.data).toMatchObject({ status: 'Accepted', acceptance: 'Accepted' })
    expect(archived.data.customerReviews).toEqual([
      expect.objectContaining({ round: 1, comment: '客户验收通过' }),
    ])
  })

  it('stores Customer Reports per round and only during Customer Review', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    const boss = createMockApi({ repository, latency: 0, role: 'Manager', userName: 'Boss' })

    // contracts.ts normalizes INVALID_REPORT_STAGE to INVALID_TRANSITION at the public boundary.
    await expect(boss.uploadCustomerReport('EVAL-103', { expectedRound: 1, file: multipartFile('early.pdf', 'too early') }))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION' })

    await boss.releaseDemoTestReport('EVAL-103', reportFiles('results.pdf', 'ok'))
    await boss.updateEvaluationStatus('EVAL-103', { status: 'Internal Review' })
    await boss.updateEvaluationStatus('EVAL-103', { status: 'Customer Review' })

    const first = await boss.uploadCustomerReport('EVAL-103', { expectedRound: 1, file: multipartFile('feedback.pdf', 'customer feedback') })
    expect(first.data).toMatchObject({ round: 1, version: 1 })
    expect(first.data.artifact).toMatchObject({ type: 'Customer Report', fileName: '[Customer] feedback.pdf', round: 1 })

    await expect(boss.uploadCustomerReport('EVAL-103', { expectedRound: 1, file: multipartFile('empty.pdf', '') }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR' })

    const second = await boss.uploadCustomerReport('EVAL-103', { expectedRound: 1, file: multipartFile('feedback-v2.pdf', 'revised') })
    expect(second.data).toMatchObject({ round: 1, version: 2 })
    const snapshot = await repository.read()
    expect(snapshot.artifacts.filter((item) => item.type === 'Customer Report')).toHaveLength(2)

    // The [Customer] marker is a literal prefix, never a character class: names that
    // merely start with those letters stay intact and a re-upload is not double-tagged.
    const essentials = await boss.uploadCustomerReport('EVAL-103', { expectedRound: 1, file: multipartFile('essentials.pdf', 'plain name') })
    expect(essentials.data.artifact.fileName).toBe('[Customer] essentials.pdf')
    const reupload = await boss.uploadCustomerReport('EVAL-103', { expectedRound: 1, file: multipartFile('[Customer] feedback.pdf', 'already tagged') })
    expect(reupload.data.artifact.fileName).toBe('[Customer] feedback.pdf')
  })

  it('blocks Planned and Completed Runs after Test Execution', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      const request = snapshot.demoRequests.find((item) => item.id === 'DR-107')!
      const evaluation = snapshot.evaluations.find((item) => item.id === 'EVAL-103')!
      evaluation.status = 'Customer Review'
      evaluation.reportStatus = 'Ready'
      evaluation.reportVersion = 2
      evaluation.reportArtifactId = 'ART-LOCKED'
      snapshot.artifacts.push({
        id: 'ART-LOCKED', demoRequestId: request.id, evaluationId: evaluation.id,
        type: 'Test Report', fileName: 'locked.pdf', mimeType: 'application/pdf',
        version: 2, createdBy: 'person029@crm.example.invalid', createdAt: '2026-07-17T10:30:00+08:00',
        visibility: 'Internal', blob: new Blob(['locked report']),
      })
    })
    const before = await repository.read()
    const administrator = createMockApi({ repository, latency: 0, role: 'Manager' })
    const writes = [
      () => administrator.addEvaluationRun('EVAL-103', {
        date: '2026-07-22', lot: 'LOT-PLANNED', wafers: 1,
        capture: null, falsePositive: null, wph: null, summary: '',
      }),
      () => administrator.addEvaluationRun('EVAL-103', {
        date: '2026-07-22', lot: 'LOT-COMPLETED', wafers: 1,
        capture: 98, falsePositive: 1, wph: 35, summary: 'Completed after release.',
      }),
    ]

    for (const write of writes) {
      await expect(write()).rejects.toMatchObject({ code: 'INVALID_TRANSITION' })
    }

    const after = await repository.read()
    expect(after.evaluations.find((item) => item.id === 'EVAL-103'))
      .toEqual(before.evaluations.find((item) => item.id === 'EVAL-103'))
    expect(after.artifacts.map(({ blob: _blob, ...artifact }) => artifact))
      .toEqual(before.artifacts.map(({ blob: _blob, ...artifact }) => artifact))
    expect(await after.artifacts[0].blob.text()).toBe('locked report')

    const workflow = (await administrator.listDemoWorkflows()).data.items.find((item) => item.id === 'DR-107')!
    expect(workflow.artifacts).toContainEqual(expect.objectContaining({ id: 'ART-LOCKED', fileName: 'locked.pdf', version: 2 }))
    const direct = await administrator.getDemoArtifact('ART-LOCKED')
    expect(await direct.blob.text()).toBe('locked report')
  })

  it.each(['Accepted', 'Rejected'] as const)('locks Run writes in terminal %s state even without a released report', async (status) => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      const evaluation = snapshot.evaluations.find((item) => item.id === 'EVAL-103')!
      evaluation.status = status
      evaluation.reportStatus = 'Not Ready'
    })
    const before = await repository.read()
    const administrator = createMockApi({ repository, latency: 0, role: 'Manager' })
    const writes = [
      () => administrator.addEvaluationRun('EVAL-103', {
        date: '2026-07-22', lot: 'LOT-PLANNED', wafers: 1,
        capture: null, falsePositive: null, wph: null, summary: '',
      }),
      () => administrator.addEvaluationRun('EVAL-103', {
        date: '2026-07-22', lot: 'LOT-COMPLETED', wafers: 1,
        capture: 98, falsePositive: 1, wph: 35, summary: 'Terminal completion.',
      }),
    ]

    for (const write of writes) {
      await expect(write()).rejects.toMatchObject({ code: 'INVALID_TRANSITION' })
    }

    const after = await repository.read()
    expect(after.evaluations.find((item) => item.id === 'EVAL-103'))
      .toEqual(before.evaluations.find((item) => item.id === 'EVAL-103'))
  })

  it('blocks new Test Runs in Customer Review', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      snapshot.evaluations.find((item) => item.id === 'EVAL-103')!.status = 'Customer Review'
    })
    const administrator = createMockApi({ repository, latency: 0, role: 'Manager' })

    await expect(administrator.addEvaluationRun('EVAL-103', {
      date: '2026-07-22', lot: 'LOT-PLANNED', wafers: 1,
      capture: null, falsePositive: null, wph: null, summary: '',
    })).rejects.toMatchObject({ code: 'INVALID_TRANSITION' })
  })

  it('shows an uploaded Test Report in lists and direct reads during Testing', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      const request = snapshot.demoRequests.find((item) => item.id === 'DR-107')!
      const evaluation = snapshot.evaluations.find((item) => item.id === 'EVAL-103')!
      evaluation.status = 'Testing'
      evaluation.reportStatus = 'Ready'
      evaluation.reportVersion = 1
      evaluation.reportArtifactId = 'ART-EARLY'
      snapshot.artifacts.push({
        id: 'ART-EARLY', demoRequestId: request.id, evaluationId: evaluation.id,
        type: 'Test Report', fileName: 'early.pdf', mimeType: 'application/pdf',
        version: 1, createdBy: 'person029@crm.example.invalid', createdAt: '2026-07-17T10:30:00+08:00',
        visibility: 'Internal', blob: new Blob(['early']),
      })
    })
    const administrator = createMockApi({ repository, latency: 0, role: 'Manager' })

    const workflow = (await administrator.listDemoWorkflows()).data.items.find((item) => item.id === 'DR-107')!
    expect(workflow.artifacts).toContainEqual(expect.objectContaining({ id: 'ART-EARLY', type: 'Test Report' }))
    await expect(administrator.getDemoArtifact('ART-EARLY')).resolves.toMatchObject({ fileName: 'early.pdf' })
  })

  it('filters contracts by status and exposes expiry risk inputs', async () => {
    const result = await api.listContracts({ status: 'Unsigned' })

    expect(result.data.items).toHaveLength(1)
    expect(result.data.items[0]).toMatchObject({ id: 'CON-003', signed: false })
  })

  it('filters Leads by search, status, source, and owner', async () => {
    const result = await api.listLeads({
      search: '示例企业016',
      status: 'Qualified',
      source: 'Trade Show',
      owner: 'person002@crm.example.invalid',
    })

    expect(result.data.items).toHaveLength(1)
    expect(result.data.items[0]).toMatchObject({
      id: 'LEAD-001',
      company: '示例企业016有限公司',
      status: 'Qualified',
    })
  })

  it('creates and updates Leads while keeping write permissions role-aware', async () => {
    const created = await api.createLead({
      name: '韩宁',
      company: '北京示例半导体有限公司',
      title: '工艺经理',
      phone: '+86 10 5555 0101',
      email: 'ning.han@example.com',
      source: 'Website',
      status: 'New',
      owner: 'person002@crm.example.invalid',
      interest: '缺陷检测',
      firstContactNote: '',
      nextAction: '首次联系',
      nextActionDue: '2026-08-03',
    })
    expect(created.data.id).toMatch(/^LEAD-/)

    const { id: leadId, createdAt: _createdAt, updatedAt: _updatedAt, modified: _modified, ...leadInput } = created.data
    const updated = await api.updateLead(leadId, { ...leadInput, status: 'Working', firstContactNote: '已完成首次沟通' })
    expect(updated.data).toMatchObject({ id: created.data.id, status: 'Working', firstContactNote: '已完成首次沟通' })
    await expect(api.getLead(created.data.id)).resolves.toMatchObject({ data: { company: '北京示例半导体有限公司' } })

    const management = createMockApi({ latency: 0, role: 'Engineer' })
    await expect(management.createLead({
      name: '越权',
      company: '无权限客户',
      title: '经理',
      source: 'Other',
      status: 'New',
      owner: 'person002@crm.example.invalid',
      interest: '',
      firstContactNote: '',
      nextAction: '',
      nextActionDue: '',
    })).rejects.toMatchObject({ code: 'PERMISSION_DENIED' })
  })

  it('converts Leads without a status gate and makes conversion idempotent', async () => {
    const salesRepository = createMemorySalesRepository()
    const conversionApi = createMockApi({ latency: 0, salesRepository })
    const beforeContacts = salesRepository.snapshot.contacts.length
    const beforeOpportunities = salesRepository.snapshot.opportunities.length
    const lead = (await conversionApi.getLead('LEAD-002')).data

    await expect(conversionApi.convertLead('LEAD-002', {
      opportunityTitle: '未确认需求的商机', opportunityAmount: '9800000.00', opportunityAmountCny: '9800000.00', opportunityCloseDate: '2026-12-31',
      opportunityOwner: 'person002@crm.example.invalid', opportunityProbabilityLevel: 'pipeline', toolType: 'Inspect X',
    })).rejects.toMatchObject({ code: 'VALIDATION_ERROR', fieldErrors: { qualificationConfirmed: 'Required' } })
    expect(salesRepository.snapshot.opportunities).toHaveLength(beforeOpportunities)
    const first = await conversionApi.convertLead('LEAD-002', {
      opportunityTitle: '新线索直接创建商机',
      opportunityAmount: '9800000.00', opportunityAmountCny: '9800000.00',
      opportunityCloseDate: '2026-12-31',
      opportunityOwner: 'person002@crm.example.invalid',
      opportunityProbabilityLevel: 'pipeline', toolType: 'Inspect X',
      qualificationConfirmed: true,
    })
    const second = await conversionApi.convertLead('LEAD-002', {
      opportunityTitle: '重复提交不会再创建',
      opportunityAmount: '1.00', opportunityAmountCny: '1.00',
      opportunityCloseDate: '2027-01-01',
      opportunityOwner: 'person005@crm.example.invalid',
      opportunityProbabilityLevel: 'pipeline', toolType: 'Other',
      qualificationConfirmed: true,
    })

    expect(first.data).toEqual(second.data)
    expect(first.data).toMatchObject({ reusedAccount: false, reusedContact: false })
    expect(first.data.lead).toMatchObject({
      status: 'Converted',
      convertedAccountId: first.data.accountId,
      convertedContactId: first.data.contactId,
      convertedOpportunityId: first.data.opportunityId,
    })
    expect(salesRepository.snapshot.contacts).toHaveLength(beforeContacts + 1)
    expect(salesRepository.snapshot.opportunities).toHaveLength(beforeOpportunities + 1)
    const opportunity = salesRepository.snapshot.opportunities.find((item) => item.id === first.data.opportunityId)!
    expect(opportunity.stakeholders).toContainEqual(expect.objectContaining({ contactId: first.data.contactId }))
    expect(opportunity).toMatchObject({ stage: 'qualified_opportunity', sourceLeadId: 'LEAD-002' })
    expect(opportunity.stageHistory).toEqual([expect.objectContaining({
      from: '', to: 'qualified_opportunity', source: 'creation', event: 'lead_converted', referenceDoctype: 'Lead', referenceName: 'LEAD-002',
    })])
    expect((await conversionApi.getContact(first.data.contactId)).data.opportunities)
      .toContainEqual(expect.objectContaining({ id: first.data.opportunityId }))
  })

  it('derives Account summary metrics from current linked records', async () => {
    const salesRepository = createMemorySalesRepository()
    const accountApi = createMockApi({ latency: 0, salesRepository })
    const before = (await accountApi.listAccounts({ page: 1, pageSize: 100 })).data.items.find((item) => item.id === 'ACC-001')!
    const created = await accountApi.createStrategyOpportunity({
      accountId: 'ACC-001', siteId: 'SITE-001', title: 'Account summary sync', owner: 'person002@crm.example.invalid',
      qualificationConfirmed: true, probabilityLevel: 'pipeline', amount: '9800000.00', amountCny: '9800000.00', intentScore: 99, poDate: '2026-12-31',
      toolType: 'Inspect X', saleType: 'New Equipment', subRegion: 'East China', currency: 'CNY',
    })

    const afterCreate = (await accountApi.listAccounts({ page: 1, pageSize: 100 })).data.items.find((item) => item.id === 'ACC-001')!
    expect(afterCreate.pipelineAmount).toBe(before.pipelineAmount + 9800000)
    expect(afterCreate.intentScore).toBe(99)

    await accountApi.markOpportunityLost(created.data.id, { lostReason: '客户延期' })
    const afterClosed = (await accountApi.getAccount360('ACC-001')).data.account
    expect(afterClosed.pipelineAmount).toBe(before.pipelineAmount)
  })

  it('keeps a converted Account and Site available after recreating the Mock API', async () => {
    const salesRepository = createMemorySalesRepository()
    const conversionApi = createMockApi({ latency: 0, salesRepository })
    const lead = (await conversionApi.getLead('LEAD-002')).data

    const converted = await conversionApi.convertLead(lead.id, {
      qualificationConfirmed: true,
      opportunityTitle: '跨角色客户联通验证',
      opportunityAmount: '9800000.00', opportunityAmountCny: '9800000.00',
      opportunityCloseDate: '2026-12-31',
      opportunityOwner: 'person002@crm.example.invalid',
      opportunityProbabilityLevel: 'pipeline', toolType: 'Inspect X',
    })

    const recreatedApi = createMockApi({
      latency: 0,
      role: 'Manager',
      salesRepository,
    })
    const accounts = (await recreatedApi.listAccounts({ page: 1, pageSize: 100 })).data.items
    const account = accounts.find((item) => item.id === converted.data.accountId)
    const account360 = await recreatedApi.getAccount360(converted.data.accountId)
    const dashboard = await recreatedApi.getDashboard({ range: 'quarter' })

    expect(account?.name).toBe(lead.company)
    expect(account360.data.sites).toHaveLength(1)
    expect(account360.data.opportunities).toContainEqual(expect.objectContaining({
      id: converted.data.opportunityId,
      accountId: converted.data.accountId,
      accountName: lead.company,
    }))
    expect(dashboard.data.topAccounts).toContainEqual(expect.objectContaining({
      accountId: converted.data.accountId,
      accountName: lead.company,
    }))
  })

  it('uses the standard Account, Site and Contact drafts when a Lead has no reusable master data', async () => {
    const salesRepository = createMemorySalesRepository()
    const conversionApi = createMockApi({ latency: 0, salesRepository })

    const converted = await conversionApi.convertLead('LEAD-002', {
      qualificationConfirmed: true,
      opportunityTitle: '武汉新厂 AOI 项目',
      opportunityAmount: '9800000.00', opportunityAmountCny: '9800000.00',
      opportunityCloseDate: '2026-12-31',
      opportunityOwner: 'person002@crm.example.invalid',
      opportunityProbabilityLevel: 'pipeline', toolType: 'Inspect X',
      newAccount: {
        name: '示例企业026有限公司',
        shortName: '武汉新芯',
        segment: 'Frontend',
        tier: 'A',
        city: '武汉',
        region: '华中',
        owner: 'person002@crm.example.invalid',
      },
      newSite: {
        name: '武汉二厂',
        city: '武汉',
        type: '晶圆制造',
        process: '28nm',
        status: '建设中',
      },
      newContact: {
        name: '李倩',
        title: '设备经理',
        department: '设备工程',
        phone: '13800000002',
        email: 'li.qian@example.com',
        relationship: 'Developing',
        owner: 'person002@crm.example.invalid',
        status: 'Active',
      },
    })

    const detail = await conversionApi.getAccount360(converted.data.accountId)
    expect(detail.data.account).toMatchObject({ shortName: '武汉新芯', tier: 'A', city: '武汉', region: 'Central China' })
    expect(detail.data.sites).toContainEqual(expect.objectContaining({ name: '武汉二厂', process: '28nm', status: '建设中' }))
    expect(detail.data.contacts).toContainEqual(expect.objectContaining({
      id: converted.data.contactId,
      name: '李倩',
      title: '设备经理',
      department: '设备工程',
    }))
    const strategy = (await conversionApi.listStrategyOpportunities()).data.items
    expect(strategy).toContainEqual(expect.objectContaining({
      id: converted.data.opportunityId,
      title: '武汉新厂 AOI 项目',
      site: '武汉二厂',
    }))
  })

  it('lets the Boss create and update records across every customer', async () => {
    const boss = createMockApi({ latency: 0, role: 'Manager', userName: '演示经理01' })
    const account = await boss.createAccount({
      name: '老板新建客户', shortName: '老板客户', segment: 'Frontend', tier: 'A', city: '上海', region: '华东', owner: 'person005@crm.example.invalid',
    })
    const contact = await boss.createContact({
      accountId: account.data.id, name: '王经理', title: '设备经理', department: '设备部',
      relationship: 'Strong', owner: 'person005@crm.example.invalid', status: 'Active',
    })

    expect(contact.data.accountId).toBe(account.data.id)
    await expect(boss.updateStrategyOpportunity('OPP-003', { title: '老板更新的商机' }))
      .resolves.toMatchObject({ data: { title: '老板更新的商机', stage: 'quotation_sent' } })
  })

  it('creates Opportunity Bookings only through the Opportunity workflow while Upsell Booking can be created directly', async () => {
    const salesRepository = createMemorySalesRepository()
    const bookingApi = createMockApi({ latency: 0, salesRepository })
    const contact = (await bookingApi.listContacts({ accountId: 'ACC-002' })).data.items.find((item) => item.status === 'Active')!
    const base = {
      accountId: 'ACC-002',
      primaryContactId: contact.id,
      equipment: 'FastScan 1200',
      quantity: 1,
      ddl: '2026-10-30',
      amount: '9000000.00',
      currency: 'CNY',
      status: 'Pending' as const,
      owner: 'person002@crm.example.invalid',
      note: '',
    }

    await expect(bookingApi.createBooking({ ...base, source: 'Opportunity', sourceOpportunityId: 'OPP-003' }))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION', message: 'Opportunity Bookings are created by confirming the PO or approving an internal validation.' })
    await expect(bookingApi.createBooking({ ...base, source: 'Upsell', sourceOpportunityId: 'OPP-003' }))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION', message: 'Upsell Booking must not reference an Opportunity.' })
    await expect(bookingApi.createBooking({ ...base, source: 'Upsell', sourceOpportunityId: '' }))
      .resolves.toMatchObject({ data: { source: 'Upsell', sourceOpportunityId: '' } })

    // BKG-003 was created by the approved internal validation of OPP-008.
    const pending = (await bookingApi.listBookings({ pageSize: 100 })).data.items.find((item) => item.id === 'BKG-003')!
    expect(pending).toMatchObject({ source: 'Opportunity', sourceOpportunityId: 'OPP-008', status: 'Pending' })
    await expect(bookingApi.updateBooking('BKG-003', { ...pending, accountId: 'ACC-001' } as never))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION', message: 'Account, source, Opportunity and type of an Opportunity Booking cannot change.' })
    await expect(bookingApi.updateBooking('BKG-003', { ...pending, source: 'Upsell', sourceOpportunityId: '' } as never))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION' })
    await expect(bookingApi.updateBooking('BKG-003', { ...pending, status: 'Confirmed' } as never))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION', message: 'An Opportunity Booking can only be changed to Cancelled.' })
    await expect(bookingApi.updateBooking('BKG-003', { ...pending, quantity: 3, note: 'Customer asked for a third tool' } as never))
      .resolves.toMatchObject({ data: { quantity: 3, status: 'Pending', sourceOpportunityId: 'OPP-008' } })
    const cancelled = await bookingApi.updateBooking('BKG-003', { ...pending, quantity: 3, status: 'Cancelled' } as never)
    expect(cancelled.data.status).toBe('Cancelled')
    await expect(bookingApi.updateBooking('BKG-003', { ...pending, quantity: 3, status: 'Pending' } as never))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION', message: 'An Opportunity Booking can only be changed to Cancelled.' })
    expect((await bookingApi.getStrategyOpportunity('OPP-008')).data).toMatchObject({ stage: 'internal_validation', liveBooking: null })
  })

  it('converts confirmed Opportunity and Upsell Bookings once and keeps completed archive records', async () => {
    const salesRepository = createMemorySalesRepository()
    const bookingApi = createMockApi({ latency: 0, salesRepository })

    const opportunityResult = await bookingApi.convertBookingToInstalledTool('BKG-001', {
      siteId: 'SITE-006',
      engineerOwner: 'person077@crm.example.invalid',
      serial: 'IGNORED-BY-SERVER',
      model: 'FastScan 1200',
      location: 'AOI Bay 3',
      salesOrder: 'SO-260101',
      contract: 'CTR-260101',
      software: '待确认',
      firmware: '待确认',
      configuration: '2 cameras',
    })
    expect(opportunityResult.data.booking).toMatchObject({
      id: 'BKG-001',
      status: 'Completed',
      installedToolId: opportunityResult.data.installedTool.id,
    })
    expect(opportunityResult.data.installedTool).toMatchObject({
      sourceBookingId: 'BKG-001',
      sourceOpportunityId: 'OPP-006',
      accountId: 'ACC-006',
      siteId: 'SITE-006',
      salesOwner: 'person005@crm.example.invalid',
      engineerOwner: 'person077@crm.example.invalid',
      status: 'Delivery Preparation',
      serial: expect.stringMatching(/^CRM-SN-\d{5}$/),
    })
    expect(opportunityResult.data.installedTool.milestones).toEqual([
      expect.objectContaining({ label: 'FAT', state: 'Current' }),
      expect.objectContaining({ label: 'Shipment', state: 'Waiting' }),
      expect.objectContaining({ label: 'Installation', state: 'Waiting' }),
      expect.objectContaining({ label: 'SAT', state: 'Waiting' }),
      expect.objectContaining({ label: 'Warranty', state: 'Waiting' }),
    ])

    const serviceResult = await bookingApi.completeServiceBooking('BKG-002')
    expect(serviceResult.data).toMatchObject({ source: 'Upsell', bookingType: 'Service', status: 'Completed' })
    expect(serviceResult.data.installedToolId).toBeUndefined()

    await expect(bookingApi.convertBookingToInstalledTool('BKG-001', {
      siteId: 'SITE-006',
      engineerOwner: 'person077@crm.example.invalid',
      serial: 'FS12-CN-260103',
      model: 'FastScan 1200',
    })).rejects.toMatchObject({ code: 'CONFLICT' })

    expect((await bookingApi.listInstalledTools()).data.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: opportunityResult.data.installedTool.id }),
    ]))
  })

  it('rejects conversion for a non-confirmed Booking or invalid Site', async () => {
    const salesRepository = createMemorySalesRepository()
    salesRepository.snapshot.bookings[0].status = 'Pending'
    const bookingApi = createMockApi({ latency: 0, salesRepository })
    const input = {
      siteId: 'SITE-006',
      engineerOwner: 'person077@crm.example.invalid',
      serial: 'AX9-CN-260018',
      model: 'FastScan 1200',
    }

    await expect(bookingApi.convertBookingToInstalledTool('BKG-001', input))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION' })
    salesRepository.snapshot.bookings[0].status = 'Confirmed'
    await expect(bookingApi.convertBookingToInstalledTool('BKG-001', { ...input, siteId: 'SITE-001', serial: 'UNIQUE-260101' }))
      .rejects.toMatchObject({ code: 'CONFLICT' })
  })

  it('lets administrators and Boss update any Installed Tool master data', async () => {
    const administrator = createMockApi({ latency: 0 })
    const boss = createMockApi({ latency: 0, role: 'Manager', userName: '演示经理01' })
    const input = {
      siteId: 'SITE-003',
      serial: 'AX9-CN-260018-ADMIN',
      model: 'AX-9000 Plus',
      location: 'Bay B8',
      status: 'Production',
      engineerOwner: 'person053@crm.example.invalid',
      software: '6.5.0',
      firmware: '1.9.0',
      configuration: '3 cameras · 300 mm',
      warrantyEnd: '2027-06-30',
      ownershipType: 'Customer Owned',
      salesOrder: 'SO-260018-A',
      contract: 'CTR-2026-018-A',
    }

    const administratorModified = (await administrator.getInstalledTool('TOOL-001')).data.modified!
    await expect(administrator.updateInstalledTool('TOOL-001', input, administratorModified)).resolves.toMatchObject({
      data: {
        id: 'TOOL-001',
        accountId: 'ACC-002',
        siteId: 'SITE-003',
        site: '武汉一厂',
        serial: 'AX9-CN-260018',
        engineerOwner: 'person053@crm.example.invalid',
        sourceOpportunityId: 'OPP-003',
        salesOwner: 'person005@crm.example.invalid',
      },
    })
    const bossModified = (await boss.getInstalledTool('TOOL-003')).data.modified!
    await expect(boss.updateInstalledTool('TOOL-003', {
      ...input,
      siteId: 'SITE-005',
      serial: 'AX7-CN-260041-BOSS',
      engineerOwner: 'person077@crm.example.invalid',
    }, bossModified)).resolves.toMatchObject({
      data: {
        id: 'TOOL-003',
        accountId: 'ACC-005',
        site: '南通工厂',
        engineerOwner: 'person077@crm.example.invalid',
      },
    })
  })

  it('lets an assigned engineer edit only their own Installed Tool and never reassign it', async () => {
    const fae = createMockApi({
      latency: 0,
      role: 'Engineer',
      userName: '演示员工14',
      assignedAccountIds: [],
    })
    const input = {
      siteId: 'SITE-004',
      serial: 'AX9-CN-260018',
      model: 'AX-9000',
      location: 'Bay A5',
      status: 'Production',
      engineerOwner: 'person077@crm.example.invalid',
      software: '6.4.3',
      firmware: '1.8.1',
      configuration: '2 cameras · 300 mm · HBM recipe pack',
      warrantyEnd: '2027-03-31',
      ownershipType: 'Customer Owned',
      salesOrder: 'SO-260018',
      contract: 'CTR-2026-018',
    }

    const ownModified = (await fae.getInstalledTool('TOOL-001')).data.modified!
    const updated = await fae.updateInstalledTool('TOOL-001', input, ownModified)
    expect(updated).toMatchObject({
      data: { location: 'Bay A5', software: '6.4.2', engineerOwner: 'person077@crm.example.invalid' },
    })
    await expect(fae.updateInstalledTool('TOOL-002', {
      ...input,
      siteId: 'SITE-001',
      serial: 'VI6-CN-250104',
      engineerOwner: 'person053@crm.example.invalid',
    }, ownModified)).rejects.toMatchObject({ code: 'SCOPE_DENIED' })
    await expect(fae.updateInstalledTool('TOOL-001', {
      ...input,
      engineerOwner: 'person053@crm.example.invalid',
    }, updated.data.modified!)).rejects.toMatchObject({ code: 'SCOPE_DENIED' })
    await expect(fae.listInstalledTools()).resolves.toMatchObject({
      data: { items: [expect.objectContaining({ id: 'TOOL-001', engineerOwner: 'person077@crm.example.invalid' })] },
    })
  })

  it('denies Sales edits, keeps the system serial and validates customer Site', async () => {
    const sales = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01' })
    const administrator = createMockApi({ latency: 0 })
    const input = {
      siteId: 'SITE-004',
      serial: 'AX9-CN-260018',
      model: 'AX-9000',
      location: 'Bay A3',
      status: 'Production',
      engineerOwner: 'person077@crm.example.invalid',
      software: '6.4.2',
      firmware: '1.8.0',
      configuration: '2 cameras · 300 mm · HBM recipe pack',
      warrantyEnd: '2027-03-31',
      ownershipType: 'Customer Owned',
      salesOrder: 'SO-260018',
      contract: 'CTR-2026-018',
    }

    await expect(sales.updateInstalledTool('TOOL-001', input, 'permission-check'))
      .rejects.toMatchObject({ code: 'PERMISSION_DENIED' })
    const administratorModified = (await administrator.getInstalledTool('TOOL-001')).data.modified!
    const serialAttempt = await administrator.updateInstalledTool('TOOL-001', { ...input, serial: 'VI6-CN-250104' }, administratorModified)
    expect(serialAttempt).toMatchObject({ data: { serial: 'AX9-CN-260018' } })
    await expect(administrator.updateInstalledTool('TOOL-001', { ...input, siteId: 'SITE-001' }, serialAttempt.data.modified))
      .rejects.toMatchObject({ code: 'CONFLICT' })
  })
})

describe('Installed Tool audit mock parity', () => {
  it('enforces four-role permissions, CAS, ordered lifecycle, version and service snapshots', async () => {
    const salesRepository = createMemorySalesRepository()
    salesRepository.snapshot.accounts.find((item) => item.id === 'ACC-006')!.visibility = 'Public'
    const engineer = createMockApi({ latency: 0, role: 'Engineer', userId: 'person077@crm.example.invalid', salesRepository })
    const otherEngineer = createMockApi({ latency: 0, role: 'Engineer', userId: 'person053@crm.example.invalid', salesRepository })
    const sales = createMockApi({ latency: 0, role: 'Sales', userId: 'person002@crm.example.invalid', assignedAccountIds: ['ACC-001', 'ACC-006'], salesRepository })
    const manager = createMockApi({ latency: 0, role: 'Manager', salesRepository })
    const created = await sales.convertBookingToInstalledTool('BKG-001', {
      siteId: 'SITE-006', engineerOwner: 'person077@crm.example.invalid', serial: 'AUDIT-MOCK-001', model: 'FastScan 1200', software: '6.4.2',
    })
    const toolId = created.data.installedTool.id

    const before = (await engineer.getInstalledTool(toolId)).data
    expect(before).toMatchObject({ canOperate: true, canReassign: false, lifecycleStage: 'FAT' })
    await expect(otherEngineer.getInstalledTool(toolId)).rejects.toMatchObject({ code: 'SCOPE_DENIED' })
    await expect(sales.transitionInstalledTool(toolId, {
      completedAt: '2026-08-12', result: 'Passed', openIssues: 'None', customerSignoff: 'Signed', comment: 'Done', evidence: [],
    }, before.modified!)).rejects.toMatchObject({ code: 'PERMISSION_DENIED' })

    const transitioned = (await engineer.transitionInstalledTool(toolId, {
      completedAt: '2026-08-12', result: 'Passed', openIssues: 'None', customerSignoff: 'Signed', comment: 'FAT complete', evidence: ['fat.pdf'],
    }, before.modified!)).data
    expect(transitioned).toMatchObject({ lifecycleStage: 'Shipment', status: 'Shipment' })
    expect(transitioned.lifecycleHistory[0]).toMatchObject({ fromStage: 'FAT', toStage: 'Shipment', actor: 'person077@crm.example.invalid' })
    await expect(engineer.transitionInstalledTool(toolId, {
      completedAt: '2026-08-13', result: 'Again', openIssues: 'None', customerSignoff: 'Signed', comment: 'Stale', evidence: [],
    }, before.modified!)).rejects.toMatchObject({ code: 'VERSION_CONFLICT' })

    const versioned = (await engineer.addInstalledToolVersionRecord(toolId, {
      changeDate: '2026-08-13', changeType: 'Software', toValue: '6.5.0', reason: 'Release', comment: 'Approved',
    }, transitioned.modified!)).data
    expect(versioned.software).toBe('6.5.0')
    expect(versioned.versionHistory[0]).toMatchObject({ fromValue: '6.4.2', toValue: '6.5.0' })

    const serviced = (await manager.addInstalledToolServiceRecord(toolId, {
      serviceDate: '2026-08-14', serviceType: 'Warranty Activation', result: 'Activated', openIssues: 'None',
      warrantyStart: '2026-08-14', warrantyEnd: '2027-08-13', serviceContract: 'SC-001', pmCycle: '6 months',
    }, versioned.modified!)).data
    expect(serviced).toMatchObject({ lastService: '2026-08-14', warrantyStart: '2026-08-14', warrantyEnd: '2027-08-13', canReassign: true })
    expect(serviced.serviceHistory[0]).toMatchObject({ serviceType: 'Warranty Activation', actor: expect.any(String) })
  })

  it('rejects interface values that the real Installed Tool endpoints reject', async () => {
    const manager = createMockApi({ latency: 0, role: 'Manager' })
    const tool = (await manager.getInstalledTool('TOOL-001')).data
    const service = {
      serviceDate: '2026-08-14', serviceType: 'Preventive Maintenance' as const,
      result: 'Checked', openIssues: 'None',
    }

    await expect(manager.addInstalledToolServiceRecord('TOOL-001', {
      ...service, serviceType: 'Unsupported Service' as never,
    }, tool.modified!)).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    await expect(manager.addInstalledToolServiceRecord('TOOL-001', {
      ...service, nextAction: 'Follow up', actionOwner: 'missing@example.com', due: '2026-08-20',
    }, tool.modified!)).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    await expect(manager.addInstalledToolServiceRecord('TOOL-001', {
      ...service, warrantyStart: '2027-08-13', warrantyEnd: '2026-08-14',
    }, tool.modified!)).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })

    const master = {
      siteId: tool.siteId, serial: tool.serial, model: tool.model, location: tool.location,
      engineerOwner: tool.engineerOwner, operatingSystem: tool.operatingSystem,
      warrantyStart: tool.warrantyStart, warrantyEnd: tool.warrantyEnd,
      serviceContract: tool.serviceContract, pmCycle: tool.pmCycle,
      ownershipType: tool.ownershipType, salesOrder: tool.salesOrder, contract: tool.contract,
    }
    await expect(manager.updateInstalledTool('TOOL-001', {
      ...master, engineerOwner: 'person002@crm.example.invalid',
    }, tool.modified!)).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    await expect(manager.updateInstalledTool('TOOL-001', {
      ...master, ownershipType: '',
    }, tool.modified!)).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
  })
})

describe('mock lost-deal post-mortems (services.loss_review parity)', () => {
  const deal = {
    accountId: 'ACC-001', siteId: 'SITE-001', title: '丢单复盘 mock', owner: 'person002@crm.example.invalid',
    qualificationConfirmed: true, probabilityLevel: 'pipeline' as const, amount: '1000.00', amountCny: '1000.00',
    intentScore: 35, poDate: '2026-11-30', toolType: 'Defect Inspection', saleType: 'New Tool' as const, subRegion: '华东', currency: 'CNY',
  }

  it('creates one pending review per loss, keeps it on reopen and lists the newest first', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager', today: '2026-07-17' })
    const created = await api.createStrategyOpportunity(deal)
    const lost = await api.markOpportunityLost(created.data.id, { lostReason: '预算冻结' })
    const event = lost.data.stageHistory.find((row) => row.event === 'marked_lost')!
    expect(lost.data.lossReviews).toHaveLength(1)
    expect(lost.data.lossReviews![0]).toMatchObject({
      opportunityId: created.data.id, stageEventId: event.id, lostAtStage: created.data.stage, lostReason: '预算冻结',
      status: 'pending', reviewNote: '', reviewedBy: null, reopenedAt: null,
    })
    expect(lost.data.lossReviews![0].history.map((row) => row.kind)).toEqual(['Created'])

    const reopened = await api.rollbackOpportunityStage(created.data.id, { targetStage: created.data.stage as never, reason: '客户重启预算' }, lost.data.modified)
    expect(reopened.data.lostReason).toBe('')
    expect(reopened.data.lossReviews![0].reopenedAt).toBeTruthy()
    expect(reopened.data.lossReviews![0].history.map((row) => row.kind)).toEqual(['Reopened', 'Created'])

    const again = await api.markOpportunityLost(created.data.id, { lostReason: '竞品低价' }, reopened.data.modified)
    expect(again.data.lossReviews!.map((row) => [row.lostReason, row.reopenedAt === null])).toEqual([['竞品低价', true], ['预算冻结', false]])
    expect((await api.getStrategyOpportunity(created.data.id)).data.lossReviews).toHaveLength(2)
  })

  it('lets only a Manager record, edit and revert the conclusion, with an audit row each time', async () => {
    const salesRepository = createMemorySalesRepository()
    const manager = createMockApi({ latency: 0, role: 'Manager', today: '2026-07-17', salesRepository })
    const sales = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01', today: '2026-07-17', salesRepository })
    const created = await manager.createStrategyOpportunity(deal)
    const lost = await manager.markOpportunityLost(created.data.id, { lostReason: '预算冻结' })
    const pending = lost.data.lossReviews![0]
    const review = (input: Parameters<typeof manager.reviewOpportunityLoss>[2], version: string, api = manager, id = created.data.id, reviewId = pending.id) =>
      api.reviewOpportunityLoss(id, reviewId, input, version)

    await expect(review({ status: 'Reviewed', reviewNote: '价格' }, pending.modified, sales)).rejects.toMatchObject({ code: 'PERMISSION_DENIED' })
    await expect(review({ status: 'Done' as never, reviewNote: '价格' }, pending.modified)).rejects.toMatchObject({ code: 'VALIDATION_ERROR', fieldErrors: { status: 'Invalid value' } })
    await expect(review({ status: 'Reviewed', reviewNote: '  ' }, pending.modified)).rejects.toMatchObject({ code: 'VALIDATION_ERROR', fieldErrors: { reviewNote: 'Enter 1-4000 characters' } })
    await expect(review({ status: 'Reviewed', reviewNote: 'x'.repeat(4001) }, pending.modified)).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    await expect(review({ status: 'Reviewed', reviewNote: '价格' }, '')).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    await expect(review({ status: 'Reviewed', reviewNote: '价格' }, '2026-07-17T10:30:00')).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    await expect(review({ status: 'Reviewed', reviewNote: '价格' }, '2020-01-01T00:00:00Z')).rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
    await expect(review({ status: 'Reviewed', reviewNote: '价格' }, pending.modified, manager, created.data.id, 'LR-missing')).rejects.toMatchObject({ code: 'NOT_FOUND' })
    await expect(review({ status: 'Pending', reviewNote: '', revertReason: '还要再看' }, pending.modified)).rejects.toMatchObject({ code: 'INVALID_TRANSITION' })

    const done = await review({ status: 'Reviewed', reviewNote: ' 价格高于竞品 15% ' }, pending.modified)
    expect(done.data).toMatchObject({ status: 'reviewed', reviewNote: '价格高于竞品 15%', reviewedBy: expect.any(String), reviewedAt: done.data.modified })
    expect(done.data.modified).not.toBe(pending.modified)
    expect(done.data.history.map((row) => row.kind)).toEqual(['Reviewed', 'Created'])
    // Saving the same conclusion again is a no-op: no new version, no audit row.
    const same = await review({ status: 'Reviewed', reviewNote: '价格高于竞品 15%' }, done.data.modified)
    expect(same.data.modified).toBe(done.data.modified)
    expect(same.data.history).toHaveLength(2)
    await expect(review({ status: 'Reviewed', reviewNote: '改结论' }, pending.modified)).rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
    const edited = await review({ status: 'Reviewed', reviewNote: '价格 + 交期' }, done.data.modified)
    expect(edited.data.history.map((row) => row.kind)).toEqual(['ReviewUpdated', 'Reviewed', 'Created'])

    await expect(review({ status: 'Pending', reviewNote: '' }, edited.data.modified)).rejects.toMatchObject({ code: 'VALIDATION_ERROR', fieldErrors: { revertReason: 'Enter 1-4000 characters' } })
    const reverted = await review({ status: 'Pending', reviewNote: '', revertReason: '销售补充了新信息' }, edited.data.modified)
    expect(reverted.data).toMatchObject({ status: 'pending', reviewNote: '价格 + 交期', reviewedBy: null, reviewedAt: null })
    expect(reverted.data.history[0]).toMatchObject({ kind: 'ReviewReverted', status: 'pending', note: '价格 + 交期', reason: '销售补充了新信息' })
    // Sales sees the same record on the deal, and the review never moved the Opportunity's own version.
    const seen = await sales.getStrategyOpportunity(created.data.id)
    expect(seen.data.lossReviews![0]).toMatchObject({ id: pending.id, status: 'pending', history: expect.any(Array) })
    expect(seen.data.modified).toBe(lost.data.modified)
  })

  it('backfills stored deals lost before reviews existed, once per loss, like the server patch', async () => {
    const salesRepository = createMemorySalesRepository()
    const first = createMockApi({ latency: 0, role: 'Manager', today: '2026-07-17', salesRepository })
    const created = await first.createStrategyOpportunity(deal)
    const lost = await first.markOpportunityLost(created.data.id, { lostReason: '预算冻结' })
    const reopened = await first.rollbackOpportunityStage(created.data.id, { targetStage: created.data.stage as never, reason: '重启' }, lost.data.modified)
    await first.markOpportunityLost(created.data.id, { lostReason: '竞品低价' }, reopened.data.modified)
    // Data saved by an older build: the losses are in the stage history, the reviews are not.
    const stored = salesRepository.snapshot.opportunities.find((item) => item.id === created.data.id)!
    const events = stored.stageHistory.filter((row) => row.event === 'marked_lost').map((row) => row.id)
    delete stored.lossReviews
    salesRepository.save()

    const later = createMockApi({ latency: 0, role: 'Manager', today: '2026-07-18', salesRepository })
    const backfilled = (await later.getStrategyOpportunity(created.data.id)).data.lossReviews!
    expect(backfilled).toHaveLength(2)
    expect(new Set(backfilled.map((row) => row.stageEventId))).toEqual(new Set(events))
    const [newest, oldest] = backfilled
    expect(newest).toMatchObject({ lostReason: '竞品低价', status: 'pending', reopenedAt: null })
    expect(newest.history.map((row) => row.kind)).toEqual(['Created'])
    expect(oldest).toMatchObject({ lostReason: '预算冻结', status: 'pending', reopenedAt: expect.any(String) })
    expect(oldest.history.map((row) => row.kind)).toEqual(['Reopened', 'Created'])
    // Nothing is invented: no conclusion, no reviewer, and a second load adds nothing.
    expect(backfilled.every((row) => row.reviewNote === '' && row.reviewedBy === null)).toBe(true)
    const again = createMockApi({ latency: 0, role: 'Manager', today: '2026-07-19', salesRepository })
    expect((await again.getStrategyOpportunity(created.data.id)).data.lossReviews!.map((row) => row.id)).toEqual(backfilled.map((row) => row.id))
    // Only the older loss missing (saved by an older build before the newer one was recorded): it goes after the newer one.
    stored.lossReviews = stored.lossReviews!.filter((row) => row.lostReason === '竞品低价')
    salesRepository.save()
    const partial = createMockApi({ latency: 0, role: 'Manager', today: '2026-07-20', salesRepository })
    expect((await partial.getStrategyOpportunity(created.data.id)).data.lossReviews!.map((row) => row.lostReason)).toEqual(['竞品低价', '预算冻结'])
  })

  it('refuses reviews from roles other than Manager and keeps the Warnings read model server-only', async () => {
    const salesRepository = createMemorySalesRepository()
    const manager = createMockApi({ latency: 0, role: 'Manager', today: '2026-07-17', salesRepository })
    const engineer = createMockApi({ latency: 0, role: 'Engineer', userName: '演示员工14', assignedAccountIds: ['ACC-001'], today: '2026-07-17', salesRepository })
    const created = await manager.createStrategyOpportunity(deal)
    const review = (await manager.markOpportunityLost(created.data.id, { lostReason: '预算冻结' })).data.lossReviews![0]
    await expect(engineer.reviewOpportunityLoss(created.data.id, review.id, { status: 'Reviewed', reviewNote: '价格' }, review.modified))
      .rejects.toMatchObject({ code: 'PERMISSION_DENIED' })
    // Like Review and Plan, the Warnings page needs the business API; the mock says so instead of inventing counts.
    await expect(manager.getWarnings({ period: 'week' } as never)).rejects.toMatchObject({ code: 'BACKEND_NOT_CONNECTED' })
  })
})
