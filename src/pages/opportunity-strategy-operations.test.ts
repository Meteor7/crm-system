import { flushPromises, mount } from '@vue/test-utils'
import { RouterLink } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { createAppRouter } from '@/app/router'
import { ROLE_PROFILES } from '@/domain/permissions'
import { useAppStore } from '@/stores/app'
import type { UserRole } from '@/types/crm'
import AccountsPage from './AccountsPage.vue'
import OpportunityStrategyPage from './OpportunityStrategyPage.vue'

async function linkFirstAvailableContact(api: ReturnType<typeof createMockApi>) {
  const opportunity = (await api.listStrategyOpportunities()).data.items[0]
  const contact = (await api.listContacts({ accountId: opportunity.accountId, pageSize: 100 })).data.items[0]
  await api.createOpportunityStakeholder(opportunity.id, {
    contactId: contact.id,
    role: 'Technical Champion',
    influence: 'High',
    stance: 'Support',
    coverage: 'Weekly technical sync',
  })
  return { opportunity: (await api.listStrategyOpportunities()).data.items[0], contact }
}

function setRole(role: UserRole) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAppStore(pinia).bootstrap = {
    user: { id: role, name: role === 'Engineer' ? '演示员工15' : '演示员工24', initials: 'LM', role, team: 'Test' },
    capabilities: ROLE_PROFILES[role].capabilities,
    version: 'test',
  }
  return pinia
}

describe('Mock customer and opportunity operations', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('uses backend customer cities and hides customer grades on the portfolio page', async () => {
    const router = createAppRouter()
    await router.push('/accounts')
    await router.isReady()
    const apiClient = createMockApi({ latency: 0 })
    apiClient.listAccountCities = vi.fn().mockResolvedValue({ data: ['苏州', '昆山'] })
    const wrapper = mount(AccountsPage, {
      props: { apiClient },
      global: { plugins: [setRole('Manager'), router] },
    })
    await flushPromises()

    const cityOptions = wrapper.get('[aria-label="城市"]').findAll('option').map((option) => option.text())
    expect(cityOptions).toContain('苏州')
    expect(cityOptions).toContain('昆山')
    expect(wrapper.text()).not.toContain('S / A 级客户')
    expect(wrapper.find('.account-link .status-badge').exists()).toBe(false)
  })

  it('creates a customer from the customer portfolio for CRM writers', async () => {
    const router = createAppRouter()
    await router.push('/accounts')
    await router.isReady()
    const apiClient = createMockApi({ latency: 0 })
    const createAccount = vi.spyOn(apiClient, 'createAccount')
    const createAccountSite = vi.spyOn(apiClient, 'createAccountSite')
    const wrapper = mount(AccountsPage, {
      props: { apiClient },
      global: { plugins: [setRole('Manager'), router] },
    })
    await flushPromises()

    await wrapper.get('[data-testid="new-account"]').trigger('click')
    await wrapper.get('[aria-label="客户全称"]').setValue('示例企业037有限公司')
    await wrapper.get('[aria-label="客户简称"]').setValue('Demo Fab')
    await wrapper.get('[aria-label="客户业务领域"]').setValue('__custom_account_segment__')
    await wrapper.get('[aria-label="客户业务领域自定义"]').setValue('Power Semiconductor')
    await wrapper.findAll('[data-modal-submit]').at(-1)!.trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('Demo Fab')
    expect(createAccount).toHaveBeenCalledWith(expect.objectContaining({ segment: 'Power Semiconductor' }))
    expect(wrapper.get('[aria-label="业务领域"]').findAll('option').map((option) => option.text())).toContain('Power Semiconductor')
    expect(createAccountSite).not.toHaveBeenCalled()
  })

  it('creates optional sites after creating a customer', async () => {
    const router = createAppRouter()
    await router.push('/accounts')
    await router.isReady()
    const apiClient = createMockApi({ latency: 0 })
    const createAccount = vi.spyOn(apiClient, 'createAccount')
    const createAccountSite = vi.spyOn(apiClient, 'createAccountSite')
    const wrapper = mount(AccountsPage, {
      props: { apiClient },
      global: { plugins: [setRole('Manager'), router] },
    })
    await flushPromises()

    await wrapper.get('[data-testid="new-account"]').trigger('click')
    await wrapper.get('[aria-label="客户全称"]').setValue('示例企业005有限公司')
    await wrapper.get('[aria-label="客户简称"]').setValue('Shanghai Test Fab')
    await wrapper.get('[data-add-site]').trigger('click')
    await wrapper.get('[aria-label="新厂区 1 名称"]').setValue('上海一厂')
    await wrapper.get('[aria-label="新厂区 1 类型"]').setValue('晶圆制造')
    await wrapper.get('[aria-label="新厂区 1 制程或用途"]').setValue('28nm')
    await wrapper.get('[aria-label="新厂区 1 状态"]').setValue('量产')
    await wrapper.findAll('[data-modal-submit]').at(-1)!.trigger('submit')
    await flushPromises()

    const createdAccount = await createAccount.mock.results[0]!.value
    expect(createAccountSite).toHaveBeenCalledWith(createdAccount.data.id, {
      name: '上海一厂',
      city: '上海',
      type: '晶圆制造',
      process: '28nm',
      status: '量产',
    })
    await vi.waitFor(() => expect(router.currentRoute.value.params.accountId).toBe(createdAccount.data.id))
  })

  it('retries only unfinished sites without creating the customer twice', async () => {
    const router = createAppRouter()
    await router.push('/accounts')
    await router.isReady()
    const apiClient = createMockApi({ latency: 0 })
    const createAccount = vi.spyOn(apiClient, 'createAccount')
    const originalCreateAccountSite = apiClient.createAccountSite.bind(apiClient)
    const createAccountSite = vi.spyOn(apiClient, 'createAccountSite')
      .mockImplementationOnce(originalCreateAccountSite)
      .mockRejectedValueOnce(new Error('厂区接口暂时不可用'))
      .mockImplementation(originalCreateAccountSite)
    const wrapper = mount(AccountsPage, {
      props: { apiClient },
      global: { plugins: [setRole('Manager'), router] },
    })
    await flushPromises()

    await wrapper.get('[data-testid="new-account"]').trigger('click')
    await wrapper.get('[aria-label="客户全称"]').setValue('示例企业041有限公司')
    await wrapper.get('[aria-label="客户简称"]').setValue('Retry Fab')
    await wrapper.get('[data-add-site]').trigger('click')
    await wrapper.get('[data-add-site]').trigger('click')
    await wrapper.get('[aria-label="新厂区 1 名称"]').setValue('一厂')
    await wrapper.get('[aria-label="新厂区 1 类型"]').setValue('晶圆制造')
    await wrapper.get('[aria-label="新厂区 1 制程或用途"]').setValue('28nm')
    await wrapper.get('[aria-label="新厂区 2 名称"]').setValue('二厂')
    await wrapper.get('[aria-label="新厂区 2 类型"]').setValue('先进封装')
    await wrapper.get('[aria-label="新厂区 2 制程或用途"]').setValue('CoWoS')
    await wrapper.findAll('[data-modal-submit]').at(-1)!.trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('客户已创建，但厂区保存失败')
    expect(createAccount).toHaveBeenCalledTimes(1)
    expect(createAccountSite).toHaveBeenCalledTimes(2)

    await wrapper.findAll('[data-modal-submit]').at(-1)!.trigger('submit')
    await flushPromises()

    expect(createAccount).toHaveBeenCalledTimes(1)
    expect(createAccountSite).toHaveBeenCalledTimes(3)
    expect(createAccountSite.mock.calls[2]?.[1].name).toBe('二厂')
  })

  it('hides customer and opportunity write controls from equipment engineers', async () => {
    const router = createAppRouter()
    await router.push('/accounts')
    await router.isReady()
    const accounts = mount(AccountsPage, {
      props: { apiClient: createMockApi({ latency: 0, role: 'Engineer', assignedAccountIds: ['ACC-001'] }) },
      global: { plugins: [setRole('Engineer'), router] },
    })
    await flushPromises()
    expect(accounts.find('[data-testid="new-account"]').exists()).toBe(false)

    const opportunities = mount(OpportunityStrategyPage, {
      props: { apiClient: createMockApi({ latency: 0, role: 'Engineer', assignedAccountIds: ['ACC-001'] }) },
      global: { plugins: [setRole('Engineer'), router] },
    })
    await flushPromises()
    expect(opportunities.find('[data-testid="new-opportunity"]').exists()).toBe(false)
    expect(opportunities.find('[data-testid="edit-opportunity"]').exists()).toBe(false)
  })

  it('creates and edits an opportunity in the current Mock session', async () => {
    const router = createAppRouter()
    await router.push('/leads-opportunities?view=opportunities')
    await router.isReady()
    const apiClient = createMockApi({ latency: 0 })
    const version = '2026-08-06T04:00:00.000Z'
    const listStrategyOpportunities = apiClient.listStrategyOpportunities.bind(apiClient)
    apiClient.listStrategyOpportunities = async (query) => {
      const result = await listStrategyOpportunities(query)
      result.data.items = result.data.items.map((opportunity) => ({ ...opportunity, modified: version }))
      return result
    }
    const updateStrategyOpportunity = vi.spyOn(apiClient, 'updateStrategyOpportunity')
    const wrapper = mount(OpportunityStrategyPage, {
      props: { apiClient },
      global: { plugins: [setRole('Manager'), router] },
    })
    await flushPromises()

    await wrapper.get('[data-testid="new-opportunity"]').trigger('click')
    await flushPromises()
    await wrapper.get('[aria-label="Opportunity 名称"]').setValue('Demo 新机会')
    await wrapper.get('[aria-label="Opportunity 金额"]').setValue('100000.00')
    await wrapper.findAll('[data-modal-submit]').at(-1)!.trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('Demo 新机会')

    await wrapper.get('[data-testid="edit-opportunity"]').trigger('click')
    await wrapper.get('[aria-label="Opportunity 名称"]').setValue('Demo 新机会（已更新）')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(updateStrategyOpportunity).toHaveBeenCalledWith(expect.any(String), expect.any(Object), version)
    expect(wrapper.text()).toContain('Demo 新机会（已更新）')
  })

  it('opens the Contact detail when an Opportunity Contact name is clicked', async () => {
    const api = createMockApi({ latency: 0 })
    const { contact } = await linkFirstAvailableContact(api)
    const linkedContactId = contact.id
    const router = createAppRouter()
    await router.push(`/leads-opportunities?view=opportunities&contactId=${linkedContactId}`)
    await router.isReady()
    const wrapper = mount(OpportunityStrategyPage, {
      props: { apiClient: api },
      global: { plugins: [setRole('Manager'), router] },
    })
    await flushPromises()

    const to = { name: 'contact-detail', params: { contactId: linkedContactId } }
    expect(wrapper.get(`a[href="/contacts/${linkedContactId}"]`).attributes('href')).toBe(`/contacts/${linkedContactId}`)
    const contactLink = wrapper.findAllComponents(RouterLink)
      .find((component) => {
        const target = component.props('to') as { name?: string; params?: { contactId?: string } }
        return target.name === to.name && target.params?.contactId === linkedContactId
      })!
    const push = vi.spyOn(router, 'push')
    await contactLink.trigger('click')
    await flushPromises()
    if (router.currentRoute.value.fullPath !== `/contacts/${linkedContactId}`) {
      expect(push).toHaveBeenCalledWith(to)
    } else {
      expect(router.currentRoute.value.fullPath).toBe(`/contacts/${linkedContactId}`)
    }
    wrapper.unmount()
  })

  it('quick creates a Contact for the Opportunity account and selects it', async () => {
    const api = createMockApi({ latency: 0 })
    const router = createAppRouter()
    await router.push('/leads-opportunities?view=opportunities')
    await router.isReady()
    const wrapper = mount(OpportunityStrategyPage, {
      props: { apiClient: api },
      global: { plugins: [setRole('Manager'), router] },
    })
    await flushPromises()

    await wrapper.get('[data-testid="new-opportunity-stakeholder"]').trigger('click')
    await wrapper.get('[data-testid="create-contact"]').trigger('click')
    await wrapper.get('[aria-label="联系人姓名"]').setValue('Quick-created contact')
    await wrapper.get('[aria-label="联系人职位"]').setValue('Process Manager')
    await wrapper.get('[aria-label="联系人部门"]').setValue('Process')
    await wrapper.findAll('[data-modal-submit]').at(-1)!.trigger('submit')
    await flushPromises()

    const created = (await api.listContacts({ search: 'Quick-created contact', page: 1, pageSize: 10 })).data.items[0]
    expect((wrapper.get('[data-testid="opportunity-contact-picker"] select').element as HTMLSelectElement).value).toBe(created.id)
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(wrapper.findAll('[aria-label="选择联系人"]')).toHaveLength(0)
    expect(wrapper.get(`[data-stakeholder-name="${created.name}"]`).attributes('data-stakeholder-name')).toBe(created.name)
    expect((await api.listStrategyOpportunities()).data.items[0].stakeholders).toContainEqual(expect.objectContaining({ contactId: created.id }))
  })

  it('reacts to Opportunity route queries for filter, view, account prefill, and one-shot create', async () => {
    const api = createMockApi({ latency: 0 })
    const { opportunity } = await linkFirstAvailableContact(api)
    const router = createAppRouter()
    await router.push('/leads-opportunities?view=opportunities')
    await router.isReady()
    const wrapper = mount(OpportunityStrategyPage, {
      props: { apiClient: api },
      global: { plugins: [setRole('Manager'), router] },
    })
    await flushPromises()

    await router.push({ query: { contactId: opportunity.stakeholders[0].contactId } })
    await flushPromises()
    expect(wrapper.findAll('[data-opportunity-id]')).toHaveLength(1)

    await router.push({ query: { accountId: 'ACC-005', create: '1', view: 'opportunities' } })
    await flushPromises()
    expect(wrapper.get('[aria-label="Opportunity 客户"]').element).toHaveProperty('value', 'ACC-005')
    expect(router.currentRoute.value.query.create).toBeUndefined()

    await wrapper.get('[aria-label="关闭"]').trigger('click')
    await router.push({ query: { accountId: 'ACC-005', view: 'opportunities' } })
    await flushPromises()
    expect(wrapper.find('[aria-label="Opportunity 客户"]').exists()).toBe(false)
  })

  it('adds and deletes opportunity actions', async () => {
    const router = createAppRouter()
    await router.push('/leads-opportunities?view=opportunities')
    await router.isReady()
    const wrapper = mount(OpportunityStrategyPage, {
      props: { apiClient: createMockApi({ latency: 0 }) },
      global: { plugins: [setRole('Manager'), router] },
    })
    await flushPromises()

    await wrapper.get('[data-testid="new-opportunity-action"]').trigger('click')
    await wrapper.get('[aria-label="Action 标题"]').setValue('确认验收窗口')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('确认验收窗口')

    const actionRow = wrapper.get('[data-action-title="确认验收窗口"]')
    await actionRow.get('[data-action="delete"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-action-title="确认验收窗口"]').exists()).toBe(false)
  })
})
