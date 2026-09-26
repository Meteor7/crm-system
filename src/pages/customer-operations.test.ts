import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { ROLE_PROFILES } from '@/domain/permissions'
import { useAppStore } from '@/stores/app'
import { createAppRouter } from '@/app/router'
import VisitsPage from './VisitsPage.vue'
import ContactsPage from './ContactsPage.vue'

function globals() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const app = useAppStore(pinia)
  app.bootstrap = {
    user: { id: 'admin', name: '管理员', initials: 'AD', role: 'Manager', team: 'CRM' },
    capabilities: ROLE_PROFILES['Manager'].capabilities,
    version: 'test',
  }
  return { plugins: [pinia, createAppRouter()] }
}

enableAutoUnmount(afterEach)

describe('customer operations pages', () => {
  it('opens a Contact-scoped Visit and persists the primary Contact link', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const router = createAppRouter()
    const api = createMockApi({ latency: 0 })
    await router.push('/visits?create=1&accountId=ACC-001&primaryContactId=CON-001')
    const wrapper = mount(VisitsPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect((wrapper.get('[aria-label="拜访客户"]').element as HTMLSelectElement).value).toBe('ACC-001')
    expect((wrapper.get('[aria-label="选择联系人"]').element as HTMLSelectElement).value).toBe('CON-001')
    await wrapper.get('[aria-label="拜访主题"]').setValue('联系人联通拜访')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()

    const linked = await api.listVisits({ contactId: 'CON-001' })
    expect(linked.data.items).toContainEqual(expect.objectContaining({ subject: '联系人联通拜访', primaryContactId: 'CON-001' }))
  })

  it('quick creates and selects a Contact inside the Visit form', async () => {
    const api = createMockApi({ latency: 0 })
    const wrapper = mount(VisitsPage, { props: { apiClient: api }, global: globals() })
    await flushPromises()

    await wrapper.get('[data-testid="new-visit"]').trigger('click')
    await wrapper.get('[data-testid="create-contact"]').trigger('click')
    await wrapper.get('[aria-label="联系人姓名"]').setValue('拜访快速联系人')
    await wrapper.get('[aria-label="联系人职位"]').setValue('Process Manager')
    await wrapper.get('[aria-label="联系人部门"]').setValue('Process')
    await wrapper.findAll('[data-modal-submit]').at(-1)!.trigger('submit')
    await flushPromises()

    const created = (await api.listContacts({ search: '拜访快速联系人', page: 1, pageSize: 10 })).data.items[0]
    expect((wrapper.get('[aria-label="选择联系人"]').element as HTMLSelectElement).value).toBe(created.id)
  })

  it('renders Visits as one row per record in the shared data-table style', async () => {
    const api = createMockApi({ latency: 0 })
    const listVisits = vi.spyOn(api, 'listVisits')
    const wrapper = mount(VisitsPage, { props: { apiClient: api }, global: globals() })
    await flushPromises()

    const initialQuery = listVisits.mock.calls[0]?.[0]
    expect(initialQuery).not.toHaveProperty('dateFrom')
    expect(initialQuery).not.toHaveProperty('dateTo')
    expect(wrapper.find('input[type="date"]').exists()).toBe(false)
    expect(wrapper.find('.status-rail').exists()).toBe(false)
    expect(wrapper.find('.visit-card').exists()).toBe(false)
    expect(wrapper.get('table.crm-table.visits-table').element.tagName).toBe('TABLE')
    expect(wrapper.findAll('table.visits-table tbody tr')).toHaveLength(2)
    expect(wrapper.get('[data-visit-id="V-001"]').text()).toContain('南京 Fab Demo 前现场确认')
    expect(wrapper.get('[data-visit-id="V-001"]').text()).toContain('现场拜访')
  })

  it('focuses the Visit selected from Calendar without hiding the Visit list', async () => {
    const pinia = createPinia()
    const router = createAppRouter()
    const api = createMockApi({ latency: 0, role: 'Manager' })
    useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
    await router.push('/visits?focus=V-001')
    await router.isReady()

    const wrapper = mount(VisitsPage, {
      props: { apiClient: api },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    expect(wrapper.get('[data-visit-id="V-001"]').classes()).toContain('focused')
    expect(wrapper.get('[data-visit-id="V-003"]').classes()).not.toContain('focused')

    await router.push('/visits?focus=V-UNKNOWN')
    await flushPromises()
    expect(wrapper.find('table.crm-table.visits-table').exists()).toBe(true)
    expect(wrapper.find('table.visits-table tbody tr.focused').exists()).toBe(false)
  })

  it('shows the four-step visit workflow and creates a planned visit', async () => {
    const wrapper = mount(VisitsPage, { props: { apiClient: createMockApi({ latency: 0 }) }, global: globals() })
    await flushPromises()

    expect(wrapper.text()).toContain('待拜访')
    expect(wrapper.text()).toContain('拜访完成')
    await wrapper.get('[data-testid="new-visit"]').trigger('click')
    await wrapper.get('[aria-label="拜访主题"]').setValue('新增客户拜访')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('新增客户拜访')
  })

  it('does not expose Visit edit or delete actions', async () => {
    const wrapper = mount(VisitsPage, { props: { apiClient: createMockApi({ latency: 0 }) }, global: globals() })
    await flushPromises()

    expect(wrapper.find('[data-delete-visit]').exists()).toBe(false)
    expect(wrapper.find('.visit-actions .text-button').exists()).toBe(false)
  })

  it('does not expose independent Action completion from the Visit list', async () => {
    const api = createMockApi({ latency: 0 })
    const version = '2026-08-06T01:00:00.000Z'
    const listVisits = api.listVisits.bind(api)
    api.listVisits = async (query) => {
      const result = await listVisits(query)
      result.data.items = result.data.items.map((visit) => ({ ...visit, modified: version }))
      return result
    }
    const wrapper = mount(VisitsPage, { props: { apiClient: api }, global: globals() })
    await flushPromises()

    expect(wrapper.text()).not.toContain('完成 Action')
  })

  it('renders the normalized Contact master list without Opportunity buying roles', async () => {
    const wrapper = mount(ContactsPage, { props: { apiClient: createMockApi({ latency: 0 }) }, global: globals() })
    await flushPromises()

    expect(wrapper.text()).toContain('联系人主档')
    expect(wrapper.text()).toContain('演示员工36')
    expect(wrapper.text()).not.toContain('Economic Buyer')
    expect(wrapper.find('[data-testid="new-contact"]').exists()).toBe(true)
  })

  it('lets management viewers create visits and maintain Contacts across customers', async () => {
    const management = createMockApi({ latency: 0, role: 'Manager' })
    const visits = mount(VisitsPage, { props: { apiClient: management }, global: { plugins: [createPinia(), createAppRouter()] } })
    await flushPromises()
    expect(visits.find('[data-testid="new-visit"]').exists()).toBe(true)
    expect(visits.find('[data-delete-visit]').exists()).toBe(false)
    expect(visits.find('.visit-actions .text-button').exists()).toBe(false)

    const contacts = mount(ContactsPage, { props: { apiClient: management }, global: { plugins: [createPinia(), createAppRouter()] } })
    await flushPromises()
    expect(contacts.find('[data-testid="new-contact"]').exists()).toBe(true)
    expect(contacts.find('[data-testid="edit-contact"]').exists()).toBe(true)
  })
})
