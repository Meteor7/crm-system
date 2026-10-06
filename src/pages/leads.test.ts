import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { CrmApiError } from '@/api'
import { useAppStore } from '@/stores/app'
import LeadListView from '@/features/leads/LeadListView.vue'
import LeadDetailPage from './LeadDetailPage.vue'

async function pageContext(role: 'Manager' | 'Manager' | 'Engineer' = 'Manager') {
  const api = createMockApi({ latency: 0, role })
  const pinia = createPinia()
  useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/leads', name: 'leads', component: { template: '<div />' } },
      { path: '/leads/:leadId', name: 'lead-detail', component: { template: '<div />' } },
      { path: '/opportunities', name: 'opportunities', component: { template: '<div />' } },
      { path: '/leads-opportunities', name: 'leads-opportunities', component: { template: '<div />' } },
      { path: '/accounts', name: 'accounts', component: { template: '<div />' } },
      { path: '/accounts/:accountId', name: 'account-detail', component: { template: '<div />' } },
      { path: '/contacts/:contactId', name: 'contact-detail', component: { template: '<div />' } },
    ],
  })
  return { api, pinia, router }
}

describe('Leads pages', () => {
  it('loads, filters, and opens an independent Lead detail route', async () => {
    const { api, pinia, router } = await pageContext()
    await router.push('/leads')
    const wrapper = mount(LeadListView, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(wrapper.findAll('[data-lead-id]')).toHaveLength(6)
    expect(wrapper.find('[data-testid="lead-search"]').exists()).toBe(false)
    await wrapper.get('[aria-label="状态"]').setValue('Qualified')
    await flushPromises()
    expect(wrapper.findAll('[data-lead-id]')).toHaveLength(2)

    await wrapper.get('[data-lead-id="LEAD-001"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/leads/LEAD-001')
  })

  it('keeps every owner in the Lead owner filter after one is chosen', async () => {
    const { api, pinia, router } = await pageContext()
    const leads = (await api.listLeads({ page: 1, pageSize: 50 })).data.items
    const chosen = leads[0]!.owner
    await router.push('/leads')
    const wrapper = mount(LeadListView, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()
    const ownerValues = () => wrapper.get('[aria-label="负责人"]').findAll('option').map((option) => option.attributes('value'))
    const before = ownerValues()
    expect(before.length).toBeGreaterThan(2)
    expect(before).toContain(chosen)

    await wrapper.get('[aria-label="负责人"]').setValue(chosen)
    await flushPromises()

    expect(wrapper.findAll('[data-lead-id]')).toHaveLength(leads.filter((lead) => lead.owner === chosen).length)
    expect(ownerValues()).toEqual(before)
  })

  it('offers a Sales user only themselves as Lead owner, since they see no one else\'s Leads', async () => {
    const { pinia, router } = await pageContext()
    const api = createMockApi({ latency: 0, role: 'Sales' })
    const user = (await api.getBootstrap()).data.user
    useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
    await router.push('/leads')
    const wrapper = mount(LeadListView, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(wrapper.get('[aria-label="负责人"]').findAll('option').map((option) => option.attributes('value'))).toEqual(['All', user.id])
  })

  it('shows a newly created Lead even when the previous filters would hide it', async () => {
    const { api, pinia, router } = await pageContext()
    await router.push('/leads')
    const wrapper = mount(LeadListView, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    await wrapper.get('[aria-label="状态"]').setValue('Qualified')
    await flushPromises()
    await wrapper.get('[data-testid="new-lead"]').trigger('click')
    await wrapper.get('[aria-label="姓名"]').setValue('韩宁')
    await wrapper.get('[aria-label="公司"]').setValue('北京示例半导体有限公司')
    await wrapper.get('[aria-label="职位"]').setValue('工艺经理')
    await wrapper.get('[aria-label="电话"]').setValue('+86 10 5555 0101')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[aria-label="状态"]').element).toHaveProperty('value', 'All')
    expect(wrapper.text()).toContain('韩宁')
    expect(wrapper.text()).toContain('北京示例半导体有限公司')
  })

  it('keeps create, edit, and convert actions role-aware', async () => {
    const management = await pageContext('Engineer')
    await management.router.push('/leads')
    const readOnly = mount(LeadListView, {
      props: { apiClient: management.api },
      global: { plugins: [management.pinia, management.router] },
    })
    await flushPromises()
    expect(readOnly.find('[data-testid="new-lead"]').exists()).toBe(false)
    expect(readOnly.find('[data-testid="edit-lead"]').exists()).toBe(false)

    const admin = await pageContext()
    await admin.router.push('/leads/LEAD-002')
    const detail = mount(LeadDetailPage, {
      props: { apiClient: admin.api },
      global: { plugins: [admin.pinia, admin.router] },
    })
    await flushPromises()
    expect(detail.find('[data-testid="edit-lead"]').exists()).toBe(true)
    expect(detail.find('[data-testid="convert-lead"]').exists()).toBe(true)
  })

  it('loads account references beyond the first page for Lead conversion', async () => {
    const { api, pinia, router } = await pageContext()
    const firstPage = await api.listAccounts({ page: 1, pageSize: 1 })
    const listAccounts = vi.spyOn(api, 'listAccounts').mockImplementation(async (query = {}) => ({
      data: { items: query.page === 2 ? [] : firstPage.data.items },
      meta: { requestId: `req-lead-account-page-${query.page ?? 1}`, total: 201, page: query.page ?? 1, pageSize: query.pageSize ?? 20 },
      warnings: [],
    }))
    await router.push('/leads/LEAD-002')
    mount(LeadDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(listAccounts).toHaveBeenNthCalledWith(1, { page: 1, pageSize: 200 })
    expect(listAccounts).toHaveBeenNthCalledWith(2, { page: 2, pageSize: 200 })
  })

  it('edits first-contact qualification directly from its detail card', async () => {
    const { api, pinia, router } = await pageContext()
    await router.push('/leads/LEAD-002')
    const wrapper = mount(LeadDetailPage, {
      props: { apiClient: api },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    await wrapper.get('[data-testid="edit-qualification"]').trigger('click')
    await wrapper.get('[aria-label="首次联系与判断"]').setValue('已电话确认，客户将在本季度评估设备。')
    await wrapper.get('[aria-label="判断结果"]').setValue('Working')
    await wrapper.get('[data-testid="save-qualification"]').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('已电话确认，客户将在本季度评估设备。')
    expect(wrapper.text()).toContain('跟进中')
    await expect(api.getLead('LEAD-002')).resolves.toMatchObject({
      data: {
        firstContactNote: '已电话确认，客户将在本季度评估设备。',
        status: 'Working',
      },
    })
  })

  it('adds a follow-up arrangement directly from the activity timeline', async () => {
    const { api, pinia, router } = await pageContext()
    const previousArrangement = (await api.getLead('LEAD-003')).data.nextAction
    await router.push('/leads/LEAD-003')
    const wrapper = mount(LeadDetailPage, {
      props: { apiClient: api },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    await wrapper.get('[data-testid="add-arrangement"]').trigger('click')
    expect(wrapper.get('[aria-label="后续安排"]').element).toHaveProperty('value', '')
    expect(wrapper.get('[aria-label="安排日期"]').element).toHaveProperty('value', '')
    await wrapper.get('[aria-label="后续安排"]').setValue('安排 FAE 技术需求访谈')
    await wrapper.get('[aria-label="安排日期"]').setValue('2026-08-08')
    await wrapper.get('[data-testid="save-arrangement"]').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('安排 FAE 技术需求访谈')
    expect(wrapper.text()).toContain('2026-08-08')
    expect(wrapper.text()).toContain(previousArrangement)
    await expect(api.getLead('LEAD-003')).resolves.toMatchObject({
      data: {
        nextAction: '安排 FAE 技术需求访谈',
        nextActionDue: '2026-08-08',
        activities: [
          { action: previousArrangement, dueDate: '2026-08-04' },
          { action: '安排 FAE 技术需求访谈', dueDate: '2026-08-08' },
        ],
      },
    })
  })

  it('renders Lead-specific profile and completes conversion from the detail page', async () => {
    const { api, pinia, router } = await pageContext()
    const convertLead = vi.spyOn(api, 'convertLead')
    await router.push('/leads/LEAD-001')
    const wrapper = mount(LeadDetailPage, {
      props: { apiClient: api },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('周启明')
    expect(wrapper.text()).toContain('示例企业016有限公司')
    expect(wrapper.text()).toContain('展会')
    expect(wrapper.text()).toContain('SEMICON China')

    await wrapper.get('[data-testid="convert-lead"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[aria-label="Opportunity 名称"]').attributes('required')).toBeDefined()
    expect(wrapper.find('[aria-label="客户简称"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="厂区名称"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="新联系人部门"]').exists()).toBe(true)
    await wrapper.get('[aria-label="业务领域"]').setValue('__custom_account_segment__')
    await wrapper.get('[aria-label="业务领域自定义"]').setValue('Power Semiconductor')
    await wrapper.get('[aria-label="Opportunity 名称"]').setValue('示例企业016缺陷检测正式商机')
    await wrapper.get('[aria-label="金额"]').setValue(9800000)
    // The converted Opportunity is in CNY: its amount in CNY follows the amount instead of being typed again.
    const amountCny = wrapper.get<HTMLInputElement>('[aria-label="人民币金额"]')
    expect([amountCny.element.value, amountCny.attributes('readonly')]).toEqual(['9800000', ''])
    expect(wrapper.get('[data-testid="lead-amount-cny-follows"]').text()).toBe('随金额自动填写，无需另填。')
    const toolTypeSelect = wrapper.get<HTMLSelectElement>('select[aria-label="设备类型"]')
    expect(toolTypeSelect.element.value).toBe('')
    expect(wrapper.find('input[aria-label="设备类型"]').exists()).toBe(false)
    await toolTypeSelect.setValue('Aconca')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(convertLead).not.toHaveBeenCalled()
    expect(wrapper.get('[data-field-error="qualificationConfirmed"]').text()).toBe('请先确认客户需求与预算负责人')

    await wrapper.get('[data-testid="qualification-confirmed"]').setValue(true)
    expect(wrapper.find('[data-field-error="qualificationConfirmed"]').exists()).toBe(false)
    // Confirming the need is not enough: the conversion also sets the new Opportunity's first level.
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(convertLead).not.toHaveBeenCalled()
    expect(wrapper.get('[data-field-error="opportunityProbabilityLevel"]').text()).toBe('请选择成功概率')

    await wrapper.get('[data-testid="lead-convert-probability-level"]').setValue('upside')
    expect(wrapper.find('[data-field-error="opportunityProbabilityLevel"]').exists()).toBe(false)
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('转换已完成')
    expect(convertLead).toHaveBeenCalledWith('LEAD-001', expect.objectContaining({
      newAccount: expect.objectContaining({ segment: 'Power Semiconductor' }),
      toolType: 'Aconca',
      opportunityProbabilityLevel: 'upside',
      opportunityAmountCny: '9800000',
      qualificationConfirmed: true,
    }))
    expect(wrapper.text()).toContain('OPP-')
    expect(wrapper.find('[data-testid="convert-lead"]').exists()).toBe(false)
  })

  it('asks before converting into an Account named like one the user sees, and converts on "仍要新建"', async () => {
    const { api, pinia, router } = await pageContext()
    const lead = (await api.getLead('LEAD-001')).data
    const convertLead = vi.spyOn(api, 'convertLead').mockImplementation(async (id, input) => {
      if (!input.newAccount?.confirmDuplicate) throw new CrmApiError('CONFLICT', 'An Account with this name exists already.', 'req_twin', false, { name: 'ACC-003' })
      return {
        data: {
          lead: { ...lead, id, status: 'Converted', convertedAt: '2026-09-30', convertedAccountId: 'ACC-NEW', convertedContactId: 'CON-NEW', convertedOpportunityId: 'OPP-TWIN' },
          accountId: 'ACC-NEW', contactId: 'CON-NEW', opportunityId: 'OPP-TWIN', reusedAccount: false, reusedContact: false,
        },
        meta: { requestId: 'req_convert_twin' },
        warnings: [],
      }
    })
    await router.push('/leads/LEAD-001')
    const wrapper = mount(LeadDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    await wrapper.get('[data-testid="convert-lead"]').trigger('click')
    await flushPromises()
    await wrapper.get('[aria-label="Opportunity 名称"]').setValue('示例企业016缺陷检测正式商机')
    await wrapper.get('select[aria-label="设备类型"]').setValue('Aconca')
    await wrapper.get('[data-testid="qualification-confirmed"]').setValue(true)
    await wrapper.get('[data-testid="lead-convert-probability-level"]').setValue('upside')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()

    // The refusal names the Accounts the user may look at and offers to go on; the dialog stays.
    expect(convertLead).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[data-duplicate-accounts]').text()).toContain('ACC-003')
    expect(wrapper.text()).toContain('已有同名的客户。')
    // Another new-Account name takes the offer away; the name asked about brings it back.
    await wrapper.get('[aria-label="客户全称"]').setValue('另一家公司')
    expect(wrapper.find('[data-duplicate-accounts]').exists()).toBe(false)
    await wrapper.get('[aria-label="客户全称"]').setValue(lead.company)
    expect(wrapper.find('[data-duplicate-accounts]').exists()).toBe(true)
    // A submission the dialog's own checks stop asks about no name: the offer does not come back for a name the
    // server was never asked about, and that name goes without a confirmation when it is sent.
    await wrapper.get('[aria-label="客户全称"]').setValue('另一家公司')
    await wrapper.get('[data-testid="qualification-confirmed"]').setValue(false)
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(convertLead).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-duplicate-accounts]').exists()).toBe(false)
    await wrapper.get('[data-testid="qualification-confirmed"]').setValue(true)
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(convertLead).toHaveBeenCalledTimes(2)
    expect(convertLead.mock.calls[1]![1].newAccount).toMatchObject({ name: '另一家公司' })
    expect(convertLead.mock.calls[1]![1].newAccount?.confirmDuplicate).toBeFalsy()
    // Refused for that name as well, the offer is for it; "仍要新建" sends it with the confirmation.
    expect(wrapper.find('[data-duplicate-accounts]').exists()).toBe(true)
    await wrapper.get('[data-create-anyway]').trigger('click')
    await flushPromises()
    expect(convertLead).toHaveBeenCalledTimes(3)
    expect(convertLead.mock.calls[2]![1]).toMatchObject({ newAccount: expect.objectContaining({ name: '另一家公司', confirmDuplicate: true }) })
    expect(wrapper.text()).toContain('转换已完成')
  })

  it('converts a Lead with both amounts left blank, since the new Opportunity starts at stage 1', async () => {
    const { api, pinia, router } = await pageContext()
    const lead = (await api.getLead('LEAD-001')).data
    const convertLead = vi.spyOn(api, 'convertLead').mockImplementation(async (id) => ({
      data: {
        lead: { ...lead, id, status: 'Converted', convertedAt: '2026-09-30', convertedAccountId: 'ACC-NEW', convertedContactId: 'CON-NEW', convertedOpportunityId: 'OPP-BLANK' },
        accountId: 'ACC-NEW', contactId: 'CON-NEW', opportunityId: 'OPP-BLANK', reusedAccount: false, reusedContact: false,
      },
      meta: { requestId: 'req_convert_blank_amount' },
      warnings: [],
    }))
    await router.push('/leads/LEAD-001')
    const wrapper = mount(LeadDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    await wrapper.get('[data-testid="convert-lead"]').trigger('click')
    await flushPromises()
    for (const label of ['金额', '人民币金额']) {
      const input = wrapper.get<HTMLInputElement>(`[aria-label="${label}"]`)
      expect(input.attributes('required')).toBeUndefined()
      expect(input.element.closest('label')?.querySelector('[data-required-mark]')).toBeNull()
      expect([input.attributes('min'), input.attributes('step')]).toEqual(['0', '0.01'])
    }
    // Blank and an exact 0 both mean "not entered yet", so the browser lets a typed 0 through; a supplied
    // negative or over-precise value is still checked. The amount in CNY only mirrors what is typed here.
    const amount = wrapper.get<HTMLInputElement>('[aria-label="金额"]')
    const amountCny = wrapper.get<HTMLInputElement>('[aria-label="人民币金额"]')
    expect(amountCny.attributes('readonly')).toBe('')
    await amount.setValue('0')
    expect(amount.element.validity.valid).toBe(true)
    expect(amountCny.element.value).toBe('0')
    await amount.setValue('-1')
    expect(amount.element.validity.rangeUnderflow).toBe(true)
    await amount.setValue('')
    expect(amountCny.element.value).toBe('')
    await wrapper.get<HTMLSelectElement>('select[aria-label="设备类型"]').setValue('Aconca')
    await wrapper.get('[data-testid="qualification-confirmed"]').setValue(true)
    await wrapper.get('[data-testid="lead-convert-probability-level"]').setValue('pipeline')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()

    expect(convertLead).toHaveBeenCalledTimes(1)
    expect(convertLead).toHaveBeenCalledWith('LEAD-001', expect.objectContaining({ opportunityAmount: '', opportunityAmountCny: '', opportunityProbabilityLevel: 'pipeline', qualificationConfirmed: true }))
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="conversion-result"]').text()).toContain('Opportunity · OPP-BLANK')
    expect(wrapper.find('[data-testid="convert-lead"]').exists()).toBe(false)
  })
})
