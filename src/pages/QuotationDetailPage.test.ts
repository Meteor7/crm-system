import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CrmApi } from '@/api'
import { createAppRouter } from '@/app/router'
import { useAppStore } from '@/stores/app'
import type { QuotationDetailDto, QuotationDraftInput } from '@/features/quotations/types'
import QuotationDetailPage from './QuotationDetailPage.vue'
import QuotationEditor from '@/features/quotations/QuotationEditor.vue'

const downloadMocks = vi.hoisted(() => ({ downloadBlob: vi.fn() }))
vi.mock('@/features/shared/download-blob', () => downloadMocks)

const detail: QuotationDetailDto = {
  quotation: { id: 'CRM-QTN-00001', refNo: 'PK20260810-A1', quotationType: 'Device', opportunityId: 'OPP-001', opportunityTitle: 'AOI Project', accountId: 'ACC-001', accountName: 'Planck Fab', owner: 'sales@example.com', status: 'Draft', approvalStatus: 'Not Submitted', latestVersion: 1, currentVersionId: 'CRM-QTV-00001', currentPublishedVersionId: '', modified: '2026-08-10T10:00:00+08:00' },
  version: { id: 'CRM-QTV-00001', version: 1, quotationType: 'Device', status: 'Draft', approvalStatus: 'Not Submitted', currentApprovalId: '', modified: '2026-08-10T10:00:00+08:00', refNo: 'PK20260810-A1', opportunityId: 'OPP-001', accountId: 'ACC-001', owner: 'sales@example.com', primaryContactId: '', addressId: '', customerName: 'Planck Fab', attentionName: '', attentionTitle: '', attentionPhone: '', addressText: '', quoteDate: '2026-08-10', validityMonths: 1, validUntil: '2026-09-10', currency: 'CNY', items: [{ lineKey: 'device-1', lineType: 'Device', parentDeviceKey: '', name: 'AOI 9000', model: 'A9', description: 'Inspection system', pricingMode: 'Charged', quantity: 1, unitPrice: '100.00', lineAmount: '100.00' }], subtotal: '100.00', discountType: 'None', discountValue: '0.00', discountAmount: '0.00', total: '100.00', paymentTerms: [{ percentage: '30.00', triggerCondition: 'PO', description: '' }, { percentage: '30.00', triggerCondition: 'Shipment', description: '' }, { percentage: '30.00', triggerCondition: 'Installation', description: '' }, { percentage: '10.00', triggerCondition: 'Acceptance', description: '' }], incoterm: 'FOB Shanghai', deliveryMonths: 3, deliveryStart: 'PO', warrantyMonths: 12, warrantyStart: 'Acceptance', installation: '', training: '', documentation: '', packing: '', feedbackDate: '', feedbackNote: '', pdfAvailable: false, publishedAt: '' },
  versions: [],
  approvals: [],
}
detail.versions = [detail.version]

const catalog = [
  { id: 'CAT-DRAKENS', level: 'Device' as const, name: 'Drakens 4482', parentId: '' },
  { id: 'CAT-PROCESS', level: 'System' as const, name: '检测腔体 Process module', parentId: 'CAT-DRAKENS' },
  { id: 'CAT-EFEM', level: 'System' as const, name: '晶圆传输系统 EFEM', parentId: 'CAT-DRAKENS' },
  { id: 'CAT-LIGHT', level: 'Accessory' as const, name: '四通道时域照明系统', parentId: 'CAT-PROCESS' },
  { id: 'CAT-RFID', level: 'Accessory' as const, name: 'RFID reader', parentId: 'CAT-EFEM' },
]
function api() {
  const calls: string[] = []
  const save = vi.fn(async (_name: string, input: QuotationDraftInput, _expectedModified?: string) => {
    calls.push('save')
    const saved = structuredClone(detail)
    saved.version = { ...saved.version, ...structuredClone(input), modified: '2026-08-10T10:00:01+08:00' }
    saved.versions = [saved.version]
    return { data: saved, warnings: [] }
  })
  const publish = vi.fn(async (_name: string, expectedModified?: string) => {
    calls.push('publish')
    const published = structuredClone(detail)
    published.version.status = 'Published'
    published.version.modified = expectedModified ?? published.version.modified
    published.versions = [published.version]
    return { data: published, warnings: [] }
  })
  const submit = vi.fn(async (_name: string, expectedModified?: string) => {
    calls.push('submit')
    const submitted = structuredClone(detail)
    submitted.version.approvalStatus = 'Pending'
    submitted.version.modified = expectedModified ?? submitted.version.modified
    submitted.quotation.approvalStatus = 'Pending'
    submitted.versions = [submitted.version]
    return { data: submitted, warnings: [] }
  })
  return { client: {
    getBootstrap: vi.fn(async () => ({ data: { user: { id: 'sales@example.com', name: 'Sales', initials: 'S', role: 'Sales', team: 'Sales' }, capabilities: ['quotation:view', 'quotation:write', 'quotation:submit'], today: '2026-08-10', environment: 'Frappe' }, warnings: [] })),
    getQuotation: vi.fn(async () => ({ data: structuredClone(detail), warnings: [] })),
    listQuotationCatalog: vi.fn(async () => ({ data: structuredClone(catalog), warnings: [] })),
    getQuotationPreviewPdf: vi.fn(async () => ({ blob: new Blob(['%PDF-preview'], { type: 'application/pdf' }), fileName: 'preview.pdf' })),
    saveQuotationDraft: save, publishQuotation: publish, submitQuotationForApproval: submit,
    listContacts: vi.fn(async () => ({ data: { items: [] }, warnings: [] })), getAccount360: vi.fn(async () => ({ data: { sites: [] }, warnings: [] })),
  } as unknown as CrmApi, save, publish, submit, calls }
}

async function mountPage(client: CrmApi) {
  const pinia = createPinia(); useAppStore(pinia).bootstrap = (await client.getBootstrap()).data
  const router = createAppRouter(); await router.push('/quotations/CRM-QTN-00001'); await router.isReady()
  const wrapper = mount(QuotationDetailPage, { props: { apiClient: client }, global: { plugins: [pinia, router] } })
  await flushPromises()
  return wrapper
}

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

beforeEach(() => {
  downloadMocks.downloadBlob.mockReset()
  vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:quotation-preview'), revokeObjectURL: vi.fn() })
})

describe('QuotationDetailPage', () => {
  it('downloads a published quotation through the shared blob helper', async () => {
    const { client } = api()
    const published = structuredClone(detail)
    published.version.status = 'Published'
    published.version.pdfAvailable = true
    published.versions = [published.version]
    vi.mocked(client.getQuotation).mockResolvedValue({ data: published, warnings: [] })
    client.getQuotationPdf = vi.fn(async () => ({ blob: new Blob(['pdf'], { type: 'application/pdf' }), fileName: 'PK20260810-A1.pdf', mimeType: 'application/pdf' }))
    const wrapper = await mountPage(client)

    await wrapper.get('[data-testid="download-quotation-pdf"]').trigger('click')
    await flushPromises()

    expect(downloadMocks.downloadBlob).toHaveBeenCalledWith(expect.objectContaining({ type: 'application/pdf' }), 'PK20260810-A1.pdf')
  })

  it('shows structured editor, synchronized preview, history, and autosaves after one second', async () => {
    const { client, save } = api(); const wrapper = await mountPage(client)
    expect(wrapper.text()).toContain('设备、系统与选装配件')
    expect(wrapper.text()).toContain('报价单预览')
    expect(wrapper.text()).toContain('历史版本')
    expect(wrapper.attributes('data-editable')).toBe('true')
    expect(wrapper.find('[data-testid="download-quotation-pdf"]').exists()).toBe(false)
    expect(wrapper.get('[aria-label="设备名称"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[aria-label="设备名称"]').setValue('AOI 9100')
    await flushPromises()
    expect(wrapper.findComponent(QuotationEditor).emitted('changed')).toBeTruthy()
    expect(save).not.toHaveBeenCalled()
    await new Promise((resolve) => setTimeout(resolve, 1050)); await flushPromises()
    expect(save).toHaveBeenCalledOnce()
    expect(save.mock.calls[0]![1].items[0].name).toBe('AOI 9100')
  })

  it('persists device price and percentage discount and refreshes normalized totals', async () => {
    const { client, save } = api()
    save.mockImplementationOnce(async (_name: string, input: QuotationDraftInput) => {
      const saved = structuredClone(detail)
      saved.version = {
        ...saved.version,
        ...structuredClone(input),
        subtotal: '123.45',
        discountValue: '10.00',
        discountAmount: '12.35',
        total: '111.10',
        modified: '2026-08-10T10:00:01+08:00',
      }
      saved.version.items[0]!.lineAmount = '123.45'
      saved.versions = [saved.version]
      return { data: saved, warnings: [] }
    })
    const wrapper = await mountPage(client)

    await wrapper.get('[aria-label="设备含税单价"]').setValue('123.45')
    await wrapper.get('[data-discount-type="Percentage"]').trigger('click')
    await wrapper.get('[aria-label="整单折扣值"]').setValue('10')
    await new Promise((resolve) => setTimeout(resolve, 1050))
    await flushPromises()

    expect(save).toHaveBeenCalledOnce()
    expect(save.mock.calls[0]![1].items[0]!.unitPrice).toBe('123.45')
    expect(save.mock.calls[0]![1].discountType).toBe('Percentage')
    expect(save.mock.calls[0]![1].discountValue).toBe('10')
    expect(wrapper.get('[data-testid="quotation-preview"]').attributes('src')).toBe('blob:quotation-preview')
    expect(wrapper.get('[data-testid="quotation-preview"]').attributes('src')).toBe('blob:quotation-preview')
  })

  it('shows only three editable commercial month fields and server template preview', async () => {
    const { client } = api()
    const wrapper = await mountPage(client)

    expect(wrapper.get('[aria-label="交期月数"]').attributes('min')).toBe('1')
    expect(wrapper.get('[aria-label="维保月数"]').attributes('min')).toBe('1')
    expect(wrapper.get('[aria-label="报价有效期月数"]').attributes('min')).toBe('1')
    expect(wrapper.findAll('[data-payment-percentage]')).toHaveLength(4)
    expect(wrapper.text()).toContain('FOB上海')
    expect(wrapper.text()).toContain('Installation, 5 days')
    expect(wrapper.get('[data-testid="quotation-preview"]').attributes('src')).toBe('blob:quotation-preview')
    expect(wrapper.get('[data-testid="quotation-preview"]').attributes('srcdoc')).toBeUndefined()
    expect(wrapper.get('[data-testid="quotation-preview"]').attributes('src')).toBe('blob:quotation-preview')
  })

  it('autosaves editable payment percentages', async () => {
    const { client, save } = api(); const wrapper = await mountPage(client)
    await wrapper.get('[data-payment-percentage="0"]').setValue('20')
    await new Promise((resolve) => setTimeout(resolve, 1050)); await flushPromises()
    expect(save).toHaveBeenCalledOnce()
    expect(save.mock.calls[0]![1].paymentTerms.map((term) => term.percentage)).toEqual(['20', '30.00', '30.00', '10.00'])
  })

  it('renders Service quotations with a simplified line editor', async () => {
    const { client } = api(); const service = structuredClone(detail)
    service.quotation.quotationType = 'Service'; service.version.quotationType = 'Service'; service.versions = [service.version]
    vi.mocked(client.getQuotation).mockResolvedValue({ data: service, warnings: [] })
    const wrapper = await mountPage(client)
    expect(wrapper.text()).toContain('SERVICE ITEMS')
    expect(wrapper.find('[data-add-accessory]').exists()).toBe(false)
  })

  it('links an Others quotation to an unquoted Opportunity from the same Account', async () => {
    const { client } = api(); const others = structuredClone(detail)
    others.quotation.opportunityId = ''; others.quotation.opportunityTitle = 'Others'
    others.version.opportunityId = ''; others.versions = [others.version]
    vi.mocked(client.getQuotation).mockResolvedValue({ data: others, warnings: [] })
    client.listStrategyOpportunities = vi.fn(async () => ({ data: { items: [
      { id: 'OPP-AVAILABLE', title: 'Service expansion', accountId: 'ACC-001', account: 'Planck Fab' },
      { id: 'OPP-FOREIGN', title: 'Foreign project', accountId: 'ACC-002', account: 'Other Fab' },
    ] }, meta: { requestId: 'o', total: 2 }, warnings: [] })) as unknown as CrmApi['listStrategyOpportunities']
    client.listQuotations = vi.fn(async () => ({ data: { items: [] }, meta: { requestId: 'q', total: 0 }, warnings: [] }))
    client.linkQuotationOpportunity = vi.fn(async () => {
      const linked = structuredClone(others)
      linked.quotation.opportunityId = 'OPP-AVAILABLE'; linked.quotation.opportunityTitle = 'Service expansion'
      return { data: linked, warnings: [] }
    })
    const wrapper = await mountPage(client)

    await wrapper.get('[data-testid="link-quotation-opportunity"]').trigger('click'); await flushPromises()
    const options = wrapper.findAll('[data-testid="link-opportunity-select"] option').map((node) => node.attributes('value'))
    expect(options).toEqual(['', 'OPP-AVAILABLE'])
    await wrapper.get('[data-testid="link-opportunity-select"]').setValue('OPP-AVAILABLE')
    await wrapper.get('[data-modal-submit]').trigger('submit'); await flushPromises()
    expect(client.linkQuotationOpportunity).toHaveBeenCalledWith(others.quotation.id, 'OPP-AVAILABLE', others.version.modified)
    expect(wrapper.text()).toContain('Service expansion')
  })

  it('uses positive whole-number constraints for device and accessory quantities', async () => {
    const { client } = api(); const wrapper = await mountPage(client)
    await wrapper.get('[data-testid="add-system-device-1"] [role="combobox"]').trigger('click')
    await wrapper.get('[aria-label="系统自定义名称"]').setValue('Custom System')
    await wrapper.get('[aria-label="新增自定义系统"]').trigger('click')
    await wrapper.get('[data-testid^="add-accessory-"] [role="combobox"]').trigger('click')
    await wrapper.get('[aria-label="配件自定义名称"]').setValue('Custom Accessory')
    await wrapper.get('[aria-label="新增自定义配件"]').trigger('click')
    const deviceQuantity = wrapper.get('[aria-label="设备数量"]')
    const accessoryQuantity = wrapper.get('[aria-label="配件数量"]')
    expect(deviceQuantity.attributes('min')).toBe('1')
    expect(deviceQuantity.attributes('step')).toBe('1')
    expect(accessoryQuantity.attributes('min')).toBe('1')
    expect(accessoryQuantity.attributes('step')).toBe('1')
    expect(wrapper.get('[aria-label="删除配件"]').classes()).toContain('remove-line-button')
  })
  it('uses click-safe non-native selectors for contact and site', async () => {
    const { client } = api(); const wrapper = await mountPage(client)
    expect(wrapper.find('[data-testid="quotation-contact-select"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="quotation-site-select"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="quotation-contact-select"] select').exists()).toBe(false)
    expect(wrapper.find('[data-testid="quotation-site-select"] select').exists()).toBe(false)
  })
  it('uses a click-safe picker for accessory pricing mode and autosaves the selection', async () => {
    const { client, save } = api(); const wrapper = await mountPage(client)
    await wrapper.get('[data-testid="add-system-device-1"] [role="combobox"]').trigger('click')
    await wrapper.get('[aria-label="系统自定义名称"]').setValue('Custom System')
    await wrapper.get('[aria-label="新增自定义系统"]').trigger('click')
    await wrapper.get('[data-testid^="add-accessory-"] [role="combobox"]').trigger('click')
    await wrapper.get('[aria-label="配件自定义名称"]').setValue('Custom Accessory')
    await wrapper.get('[aria-label="新增自定义配件"]').trigger('click')
    const picker = wrapper.get('[data-testid="accessory-pricing-mode-select"]')
    expect(picker.find('select').exists()).toBe(false)
    await picker.get('[role="combobox"]').trigger('click')
    const charged = picker.findAll('[role="option"]').find((option) => option.text() === 'Charged')
    expect(charged).toBeDefined()
    await charged!.trigger('click')
    expect(wrapper.get('[aria-label="配件含税单价"]').attributes('disabled')).toBeUndefined()
    await new Promise((resolve) => setTimeout(resolve, 1050)); await flushPromises()
    expect(save).toHaveBeenCalledOnce()
    expect(save.mock.calls[0]![1].items.find((item) => item.lineType === 'Accessory')?.pricingMode).toBe('Charged')
  })
  it('filters the three-level catalog and autosaves selected hierarchy', async () => {
    const { client, save } = api(); const wrapper = await mountPage(client)
    await wrapper.get('[data-testid="add-device"] [role="combobox"]').trigger('click')
    await wrapper.findAll('[data-testid="add-device"] [role="option"]').find((node) => node.text() === 'Drakens 4482')!.trigger('click')
    const systemFilter = wrapper.findAll('[data-testid^="add-system-"]').at(-1)!
    await systemFilter.get('[role="combobox"]').trigger('click')
    await systemFilter.findAll('[role="option"]').find((node) => node.text() === '检测腔体 Process module')!.trigger('click')
    const accessoryFilter = wrapper.findAll('[data-testid^="add-accessory-"]').at(-1)!
    await accessoryFilter.get('[role="combobox"]').trigger('click')
    await accessoryFilter.findAll('[role="option"]').find((node) => node.text() === '四通道时域照明系统')!.trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 1050)); await flushPromises()
    expect(save).toHaveBeenCalledOnce()
    const selected = save.mock.calls[0]![1].items.slice(-3)
    expect(selected.map((item) => item.lineType)).toEqual(['Device', 'System', 'Accessory'])
    expect(selected[1]!.parentDeviceKey).toBe(selected[0]!.lineKey)
    expect(selected[2]!.parentSystemKey).toBe(selected[1]!.lineKey)
    expect(selected.map((item) => item.catalogItemId)).toEqual(['CAT-DRAKENS', 'CAT-PROCESS', 'CAT-LIGHT'])
  })

  it('flushes the latest draft before submitting approval and uses the saved version token', async () => {
    const { client, save, submit, calls } = api(); const wrapper = await mountPage(client)
    await wrapper.get('[aria-label="设备名称"]').setValue('AOI 9200')
    await wrapper.get('[data-testid="submit-quotation-approval"]').trigger('click')
    await flushPromises()
    expect(save).toHaveBeenCalledOnce()
    expect(save.mock.calls[0]![1].items[0].name).toBe('AOI 9200')
    expect(submit).toHaveBeenCalledWith('CRM-QTN-00001', '2026-08-10T10:00:01+08:00')
    expect(calls).toEqual(['save', 'submit'])
  })

  it('locks a pending Sales quotation until a Manager decides it', async () => {
    const { client } = api()
    const pending = structuredClone(detail)
    pending.version.approvalStatus = 'Pending'
    pending.version.currentApprovalId = 'CRM-QTA-00001'
    pending.quotation.approvalStatus = 'Pending'
    pending.approvals = [{ id:'CRM-QTA-00001',quotationId:pending.quotation.id,versionId:pending.version.id,attempt:1,status:'Pending',submittedBy:'sales@example.com',submittedAt:'2026-08-10T10:05:00+08:00',decidedBy:'',decidedAt:'',comment:'' }]
    vi.mocked(client.getQuotation).mockResolvedValue({ data: pending, warnings: [] })
    const wrapper = await mountPage(client)
    expect(wrapper.attributes('data-editable')).toBe('false')
    expect(wrapper.text()).toContain('等待 Manager 审批')
    expect(wrapper.find('[data-testid="submit-quotation-approval"]').exists()).toBe(false)
    expect(wrapper.get('[aria-label="设备名称"]').attributes('disabled')).toBeDefined()
  })

  it('renders an address-restricted quotation as read-only', async () => {
    const { client, save } = api()
    const restricted = structuredClone(detail)
    restricted.quotation.opportunityId = ''
    restricted.version.addressRestricted = true
    restricted.versions = [restricted.version]
    vi.mocked(client.getQuotation).mockResolvedValue({ data: restricted, warnings: [] })

    const wrapper = await mountPage(client)

    expect(wrapper.attributes('data-editable')).toBe('false')
    expect(wrapper.get('[data-testid="quotation-address-restricted"]').text()).toContain('当前报价为只读')
    expect(wrapper.get('[aria-label="设备名称"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="submit-quotation-approval"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="link-quotation-opportunity"]').exists()).toBe(false)
    expect(save).not.toHaveBeenCalled()
  })

  it('shows Manager approval actions and requires a rejection reason', async () => {
    const { client } = api()
    const pending = structuredClone(detail)
    pending.version.approvalStatus = 'Pending'
    pending.version.currentApprovalId = 'CRM-QTA-00001'
    pending.quotation.approvalStatus = 'Pending'
    pending.approvals = [{ id:'CRM-QTA-00001',quotationId:pending.quotation.id,versionId:pending.version.id,attempt:1,status:'Pending',submittedBy:'sales@example.com',submittedAt:'2026-08-10T10:05:00+08:00',decidedBy:'',decidedAt:'',comment:'' }]
    client.getBootstrap = vi.fn(async () => ({ data: { user:{id:'manager@example.com',name:'Manager',initials:'M',role:'Manager',team:'Management'},capabilities:['quotation:view','quotation:write','quotation:approve','quotation:publish'],version:'test' }, warnings:[] } as never))
    vi.mocked(client.getQuotation).mockResolvedValue({ data: pending, warnings: [] })
    client.reviewQuotationApproval = vi.fn(async () => ({ data: pending, warnings: [] }))
    const wrapper = await mountPage(client)
    expect(wrapper.find('[data-testid="approve-quotation"]').exists()).toBe(true)
    await wrapper.get('[data-testid="reject-quotation"]').trigger('click')
    expect(wrapper.get('[data-modal-submit]').attributes('disabled')).toBeDefined()
    await wrapper.get('textarea[maxlength="1000"]').setValue('Revise price')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(client.reviewQuotationApproval).toHaveBeenCalledWith(pending.quotation.id, expect.objectContaining({ decision:'Rejected',comment:'Revise price',expectedModified:pending.version.modified }))
  })
})


describe('QuotationDetailPage optimistic save recovery', () => {
  it('surfaces a version conflict without retrying and overwriting another user', async () => {
    const { CrmApiError } = await import('@/api')
    const { client, save } = api()
    const wrapper = await mountPage(client)

    await wrapper.get('[aria-label="设备名称"]').setValue('First local edit')
    await new Promise((resolve) => setTimeout(resolve, 1050))
    await flushPromises()
    expect(save).toHaveBeenCalledOnce()

    save.mockRejectedValueOnce(new CrmApiError(
      'VERSION_CONFLICT',
      '报价单已被其他用户更新，请刷新后重新应用本地修改。',
      'req_quotation_conflict',
    ))

    await wrapper.get('[aria-label="设备名称"]').setValue('Second local edit')
    await new Promise((resolve) => setTimeout(resolve, 1050))
    await flushPromises()

    expect(save).toHaveBeenCalledTimes(2)
    expect(client.getQuotation).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('报价单已被其他用户更新，请刷新后重新应用本地修改。')
    wrapper.unmount()
  })

  it('does not replace local edits when a focus refresh returns late', async () => {
    const { client } = api()
    const wrapper = await mountPage(client)
    let resolveRefresh!: (value: Awaited<ReturnType<CrmApi['getQuotation']>>) => void
    vi.mocked(client.getQuotation).mockImplementationOnce(() => new Promise((resolve) => { resolveRefresh = resolve }))

    window.dispatchEvent(new Event('focus'))
    await wrapper.get('[aria-label="设备名称"]').setValue('本地尚未保存的设备名')

    const remote = structuredClone(detail)
    remote.version.items[0].name = '另一位用户保存的设备名'
    remote.version.modified = '2026-08-10T10:00:02+08:00'
    remote.versions = [remote.version]
    resolveRefresh({ data: remote, warnings: [] })
    await flushPromises()

    expect((wrapper.get('[aria-label="设备名称"]').element as HTMLInputElement).value).toBe('本地尚未保存的设备名')
    wrapper.unmount()
  })
})
describe('QuotationDetailPage adversarial loading', () => {
  it('keeps an owned quotation visible when its account is outside the Sales account scope', async () => {
    const { CrmApiError } = await import('@/api')
    const { client } = api()
    vi.mocked(client.getAccount360).mockRejectedValueOnce(new CrmApiError(
      'SCOPE_DENIED',
      'The account is outside the current user scope.',
      'req_account_scope',
    ))

    const wrapper = await mountPage(client)

    expect(wrapper.find('.summary-strip').exists()).toBe(true)
    expect(wrapper.text()).toContain('PK20260810-A1')
    expect(wrapper.text()).toContain('req_account_scope')
    expect(wrapper.find('[data-state="denied"]').exists()).toBe(false)
  })

  it('loads every active contact page instead of truncating at the backend cap', async () => {
    const { client } = api()
    vi.mocked(client.listContacts).mockImplementation(async (query) => ({
      data: { items: query.page === 2 ? [{ id: 'C-3', name: 'Third' }] : [{ id: 'C-1', name: 'First' }, { id: 'C-2', name: 'Second' }] } as never,
      meta: { requestId: 'contacts', total: 3 }, warnings: [],
    }))
    const wrapper = await mountPage(client)
    expect(client.listContacts).toHaveBeenNthCalledWith(1, { accountId: 'ACC-001', contactStatus: 'Active', page: 1, pageSize: 200 })
    expect(client.listContacts).toHaveBeenNthCalledWith(2, { accountId: 'ACC-001', contactStatus: 'Active', page: 2, pageSize: 200 })
    expect(wrapper.text()).toContain('客户与报价信息')
  })

  it('keeps the newest preview when an older PDF request finishes last', async () => {
    const { client } = api()
    let resolveFirst!: (value: { blob: Blob; fileName: string; mimeType: string }) => void
    let resolveSecond!: (value: { blob: Blob; fileName: string; mimeType: string }) => void
    vi.mocked(client.getQuotationPreviewPdf)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveSecond = resolve }))
    vi.mocked(URL.createObjectURL).mockReturnValueOnce('blob:latest').mockReturnValueOnce('blob:stale')
    const wrapper = await mountPage(client)
    await wrapper.get('[aria-label="设备名称"]').setValue('Newest device')
    await new Promise((resolve) => setTimeout(resolve, 1050)); await flushPromises()
    resolveSecond({ blob: new Blob(['new']), fileName: 'new.pdf', mimeType: 'application/pdf' }); await flushPromises()
    expect(wrapper.get('[data-testid="quotation-preview"]').attributes('src')).toBe('blob:latest')
    resolveFirst({ blob: new Blob(['old']), fileName: 'old.pdf', mimeType: 'application/pdf' }); await flushPromises()
    expect(wrapper.get('[data-testid="quotation-preview"]').attributes('src')).toBe('blob:latest')
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:stale')
  })
})
