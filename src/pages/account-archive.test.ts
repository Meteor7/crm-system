import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createAppRouter } from '@/app/router'
import { CrmApiError } from '@/api'
import { createMockApi } from '@/api/mock-adapter'
import { useAppStore } from '@/stores/app'
import type { AccountSummaryDto, ContactListQuery, UserRole } from '@/types/crm'
import type { BookingDto } from '@/types/crm'
import ContactFilesCard from '@/features/contacts/ContactFilesCard.vue'
import ContactPicker from '@/features/contacts/ContactPicker.vue'
import BookingEditorModal from '@/features/opportunities/BookingEditorModal.vue'
import StakeholderEditorModal from '@/features/opportunities/StakeholderEditorModal.vue'
import OpportunityEditorModal from '@/features/opportunities/OpportunityEditorModal.vue'
import AccountsPage from './AccountsPage.vue'
import AccountDetailPage from './AccountDetailPage.vue'
import BookingDetailPage from './BookingDetailPage.vue'
import BookingPage from './BookingPage.vue'
import ContactDetailPage from './ContactDetailPage.vue'
import OpportunityDetailPage from './OpportunityDetailPage.vue'

type MockApi = ReturnType<typeof createMockApi>

async function context(role: UserRole, path: string) {
  const api = createMockApi({ latency: 0, role, userName: role === 'Sales' ? 'Demo Staff 01' : '演示员工24' })
  const pinia = createPinia()
  const bootstrap = (await api.getBootstrap()).data
  useAppStore(pinia).bootstrap = bootstrap
  const router = createAppRouter()
  await router.push(path)
  await router.isReady()
  return { api, pinia, router, user: bootstrap.user }
}

function archived(account: AccountSummaryDto, by: string): AccountSummaryDto {
  return { ...account, archived: true, archivedAt: '2026-10-07T05:00:00Z', archivedBy: by }
}

// The Account 360 as the server answers it: archived (by `state.by`) while `state.archived` is set (the page reads
// it again after an archive or a restore, as the profile's own controls follow the record).
function serve360(api: MockApi, state: { archived: boolean; by: string }) {
  const original = api.getAccount360.bind(api)
  vi.spyOn(api, 'getAccount360').mockImplementation(async (id) => {
    const result = await original(id)
    return state.archived ? { ...result, data: { ...result.data, account: archived(result.data.account, state.by) } } : result
  })
  return state
}

async function detail(role: UserRole, id: string, prepare?: (api: MockApi) => void) {
  const { api, pinia, router, user } = await context(role, `/accounts/${id}`)
  prepare?.(api)
  const wrapper = mount(AccountDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
  await flushPromises()
  return { api, router, user, wrapper }
}

// The pickers as the server answers them with Accounts archived: the Accounts out of the Account list, their Contacts
// out of the Contact list unless they are asked for by their Account's id.
function hideFromPickers(api: MockApi, ...accountIds: string[]) {
  const hidden = new Set(accountIds)
  const accounts = api.listAccounts.bind(api)
  const contacts = api.listContacts.bind(api)
  vi.spyOn(api, 'listAccounts').mockImplementation(async (query = {}) => {
    const result = await accounts({ ...query, pageSize: 200 })
    const items = result.data.items.filter((item) => !hidden.has(item.id))
    return { ...result, data: { ...result.data, items }, meta: { requestId: 'req-accounts', page: 1, pageSize: 200, total: items.length } }
  })
  return vi.spyOn(api, 'listContacts').mockImplementation(async (query: ContactListQuery = {}) => {
    const result = await contacts({ ...query, pageSize: 200 })
    const items = query.accountId ? result.data.items : result.data.items.filter((item) => !hidden.has(item.accountId))
    return { ...result, data: { ...result.data, items }, meta: { requestId: 'req-contacts', page: 1, pageSize: 200, total: items.length } }
  })
}

afterEach(() => vi.restoreAllMocks())

describe('Account archive', () => {
  it('lets a Manager archive an Account from its page, which then is read-only with the notice and the restore, and restore it', async () => {
    const state = { archived: false, by: '' }
    const { api, router, user, wrapper } = await detail('Manager', 'ACC-001', (prepared) => { serve360(prepared, state) })
    state.by = user.id
    const account = (await api.getAccount360('ACC-001')).data.account
    const archive = vi.spyOn(api, 'archiveAccount').mockImplementation(async () => { state.archived = true; return { data: archived(account, user.id), warnings: [] } })
    expect(wrapper.find('[data-testid="edit-account"]').exists()).toBe(true)
    expect(wrapper.find('[data-manage-sites]').exists()).toBe(true)
    expect(wrapper.find('[data-unarchive-account]').exists()).toBe(false)
    expect(wrapper.find('[data-archived-notice]').exists()).toBe(false)

    await wrapper.get('[data-archive-account]').trigger('click')
    await flushPromises()
    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.attributes('aria-label')).toBe('归档客户')
    expect(dialog.text()).toContain(account.name)
    expect(dialog.text()).toContain('全部保留')
    expect(dialog.text()).toContain('厂区和联系人')
    expect(dialog.text()).not.toContain('删除')
    expect(dialog.get('[data-modal-submit]').text()).toBe('归档')
    expect(dialog.get('[data-modal-submit]').classes()).toContain('danger-action')
    await dialog.get('form').trigger('submit')
    await flushPromises()

    expect(archive).toHaveBeenCalledWith('ACC-001')
    expect(router.currentRoute.value.path).toBe('/accounts/ACC-001')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    const notice = wrapper.get('[data-archived-notice]').text()
    expect(notice).toContain('已归档')
    expect(notice).toContain(user.name)
    expect(notice).toContain('取消归档后恢复')
    expect(wrapper.find('[data-archive-account]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="edit-account"]').exists()).toBe(false)
    // The profile read the Account again: its Sites take no change either; what is read stays.
    expect(wrapper.find('[data-manage-sites]').exists()).toBe(false)
    expect(wrapper.text()).toContain(account.name)
    expect(wrapper.find('[data-testid="export-customer-report"]').exists()).toBe(true)

    const restore = vi.spyOn(api, 'unarchiveAccount').mockImplementation(async () => { state.archived = false; return { data: { ...account, archived: false }, warnings: [] } })
    await wrapper.get('[data-unarchive-account]').trigger('click')
    await flushPromises()
    expect(restore).toHaveBeenCalledWith('ACC-001')
    expect(wrapper.find('[data-archived-notice]').exists()).toBe(false)
    expect(wrapper.find('[data-unarchive-account]').exists()).toBe(false)
    expect(wrapper.find('[data-archive-account]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="edit-account"]').exists()).toBe(true)
    expect(wrapper.find('[data-manage-sites]').exists()).toBe(true)
  })

  it('offers the archive to nobody but a Manager, and shows an archived Account to a Sales user read-only with a notice to ask a Manager', async () => {
    const { api } = await context('Manager', '/accounts/ACC-001')
    const account = (await api.getAccount360('ACC-001')).data.account

    const sales = await detail('Sales', 'ACC-001')
    expect(sales.wrapper.find('[data-archive-account]').exists()).toBe(false)
    expect(sales.wrapper.find('[data-unarchive-account]').exists()).toBe(false)

    const archivedForSales = await detail('Sales', 'ACC-001', (prepared) => { serve360(prepared, { archived: true, by: 'manager@example.invalid' }) })
    const notice = archivedForSales.wrapper.get('[data-archived-notice]').text()
    expect(notice).toContain('请联系经理')
    expect(notice).not.toContain('取消归档后')
    expect(archivedForSales.wrapper.find('[data-unarchive-account]').exists()).toBe(false)
    expect(archivedForSales.wrapper.find('[data-archive-account]').exists()).toBe(false)
    expect(archivedForSales.wrapper.find('[data-testid="edit-account"]').exists()).toBe(false)
    expect(archivedForSales.wrapper.find('[data-manage-sites]').exists()).toBe(false)
    expect(archivedForSales.wrapper.text()).toContain(account.name)
  })

  it('keeps the page and shows the refusal with its request id when the archive or the restore is refused, and clears it for another Account', async () => {
    const { api, router, wrapper } = await detail('Manager', 'ACC-001')
    vi.spyOn(api, 'archiveAccount').mockRejectedValue(new CrmApiError('INVALID_TRANSITION', 'An Account with an open Opportunity cannot be archived; close or archive the Opportunity first.', 'req-archive-account', false))
    await wrapper.get('[data-archive-account]').trigger('click')
    await flushPromises()
    await wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()

    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.get('[data-archive-error]').text()).toContain('客户还有进行中的商机，不能归档；请先关闭或归档该商机。')
    expect(dialog.get('[data-archive-error]').text()).toContain('请求编号 req-archive-account')
    expect(wrapper.findAll('[data-archive-error]')).toHaveLength(1)
    expect(dialog.get('[data-modal-submit]').attributes('disabled')).toBeUndefined()
    expect(router.currentRoute.value.path).toBe('/accounts/ACC-001')
    expect(wrapper.find('[data-archived-notice]').exists()).toBe(false)
    await dialog.get('header button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.find('[data-archive-error]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="edit-account"]').exists()).toBe(true)

    const state = { archived: true, by: 'manager@example.invalid' }
    const archivedPage = await detail('Manager', 'ACC-001', (prepared) => {
      serve360(prepared, state)
      vi.spyOn(prepared, 'unarchiveAccount').mockRejectedValue(new CrmApiError('SCOPE_DENIED', 'Customer is outside the current user scope.', 'req-restore-account', false))
    })
    await archivedPage.wrapper.get('[data-unarchive-account]').trigger('click')
    await flushPromises()
    expect(archivedPage.wrapper.get('[data-archive-error]').text()).toContain('req-restore-account')
    expect(archivedPage.wrapper.find('[data-archived-notice]').exists()).toBe(true)
    expect(archivedPage.wrapper.get('[data-unarchive-account]').attributes('disabled')).toBeUndefined()

    // The error belongs to that Account: another one (not archived) opened in the same page starts clean.
    const other = (await archivedPage.api.listAccounts({ pageSize: 3 })).data.items.find((item) => item.id !== 'ACC-001')!
    state.archived = false
    await archivedPage.router.push(`/accounts/${other.id}`)
    await flushPromises()
    expect(archivedPage.wrapper.find('[data-archive-error]').exists()).toBe(false)
    expect(archivedPage.wrapper.find('[data-archived-notice]').exists()).toBe(false)
    expect(archivedPage.wrapper.find('[data-archive-account]').exists()).toBe(true)
  })

  it('drops the answer of an archive that arrives after the page moved on to another Account', async () => {
    const { api, router, wrapper } = await detail('Manager', 'ACC-001')
    const other = (await api.listAccounts({ pageSize: 3 })).data.items.find((item) => item.id !== 'ACC-001')!
    const account = (await api.getAccount360('ACC-001')).data.account
    let settle: (value: { data: AccountSummaryDto; warnings: never[] }) => void = () => {}
    vi.spyOn(api, 'archiveAccount').mockImplementation(() => new Promise((resolve) => { settle = resolve }))
    await wrapper.get('[data-archive-account]').trigger('click')
    await flushPromises()
    await wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="dialog"] [data-modal-submit]').attributes('disabled')).toBeDefined()

    await router.push(`/accounts/${other.id}`)
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('[data-archive-account]').attributes('disabled')).toBeUndefined()
    // From here the page's reads of the Account hang: an answer written over the Account shown would stay seen.
    vi.spyOn(api, 'getAccount360').mockImplementation(() => new Promise(() => {}))
    settle({ data: archived(account, 'manager@example.invalid'), warnings: [] })
    await flushPromises()
    expect(wrapper.find('[data-archived-notice]').exists()).toBe(false)
    expect(wrapper.find('[data-unarchive-account]').exists()).toBe(false)
    expect(wrapper.find('[data-archive-account]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="edit-account"]').exists()).toBe(true)
  })

  it('acts on the Account it shows: none while another one loads, and the dialog names the Account it archives', async () => {
    const { api, router, wrapper } = await detail('Manager', 'ACC-001')
    const other = (await api.listAccounts({ pageSize: 3 })).data.items.find((item) => item.id !== 'ACC-001')!
    const read = api.getAccount360.bind(api)
    let release: () => void = () => {}
    vi.spyOn(api, 'getAccount360').mockImplementation(async (id) => {
      if (id === other.id) await new Promise<void>((resolve) => { release = resolve })
      return read(id)
    })
    const archive = vi.spyOn(api, 'archiveAccount')

    await router.push(`/accounts/${other.id}`)
    await flushPromises()
    // The record read before is still in the page while the other one loads: no archive and no edit for it.
    expect(wrapper.find('[data-archive-account]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="edit-account"]').exists()).toBe(false)
    release()
    await flushPromises()
    await wrapper.get('[data-archive-account]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="dialog"]').text()).toContain(other.name)
    expect(archive).not.toHaveBeenCalled()
  })

  it('lists active Accounts by default, the archived ones through the filter kept in the URL, marked', async () => {
    const { api, pinia, router } = await context('Manager', '/accounts')
    const [first, second] = (await api.listAccounts({ pageSize: 2 })).data.items
    const archivedSecond = archived(second!, 'manager@example.invalid')
    const list = vi.spyOn(api, 'listAccounts').mockImplementation(async (query = {}) => {
      const items = query.archiveState === 'archived' ? [archivedSecond] : query.archiveState === 'all' ? [first!, archivedSecond] : [first!]
      return { data: { items }, meta: { requestId: 'req-list', page: 1, pageSize: 10, total: items.length }, warnings: [] }
    })
    const wrapper = mount(AccountsPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ archiveState: 'active' }))
    expect(wrapper.findAll('[data-account-id]').map((row) => row.attributes('data-account-id'))).toEqual([first!.id])
    expect(wrapper.find('[data-account-archived]').exists()).toBe(false)
    expect(wrapper.find('[data-delete-account]').exists()).toBe(false)

    await wrapper.get('[aria-label="归档状态"]').setValue('archived')
    await flushPromises()
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ archiveState: 'archived', page: 1 }))
    expect(router.currentRoute.value.query.archive).toBe('archived')
    expect(wrapper.findAll('[data-account-id]').map((row) => row.attributes('data-account-id'))).toEqual([second!.id])
    expect(wrapper.get(`[data-account-archived="${second!.id}"]`).text()).toBe('已归档')

    await wrapper.get('[aria-label="归档状态"]').setValue('all')
    await flushPromises()
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ archiveState: 'all' }))
    expect(wrapper.findAll('[data-account-id]')).toHaveLength(2)
    expect(wrapper.findAll('[data-account-archived]')).toHaveLength(1)

    // The filter comes back from the URL, and the reset puts it back to the active ones.
    await router.push('/accounts?archive=archived')
    await flushPromises()
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ archiveState: 'archived' }))
    expect((wrapper.get('[aria-label="归档状态"]').element as HTMLSelectElement).value).toBe('archived')
    await wrapper.get('[aria-label="归档状态"]').setValue('all')
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '重置条件')!.trigger('click')
    await flushPromises()
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ archiveState: 'active' }))
    expect(router.currentRoute.value.query.archive).toBeUndefined()
  })

  it('keeps the archived Account of a closed deal and of a cancelled order as their editors\' choice, as it was', async () => {
    const { api, pinia } = await context('Manager', '/opportunities/OPP-001')
    // The pickers list the active Accounts only: the record's own Account, archived, is not among them.
    const deal = { ...(await api.getStrategyOpportunity('OPP-001')).data, account: 'Archived Fab Co.', site: 'Archived Fab Site' }
    const listed = (await api.listAccounts({ pageSize: 50 })).data.items.filter((item) => item.id !== deal.accountId)
    const dealEditor = mount(OpportunityEditorModal, {
      props: { opportunity: deal, accounts: listed, sitesByAccount: {}, defaultOwner: deal.owner, currentUserId: deal.owner },
      global: { plugins: [pinia] },
    })
    await flushPromises()
    const dealAccount = dealEditor.get('select[aria-label="客户"]').element as HTMLSelectElement
    const dealSite = dealEditor.get('select[aria-label="厂区"]').element as HTMLSelectElement
    expect(dealAccount.value).toBe(deal.accountId)
    expect(dealSite.value).toBe(deal.siteId)
    expect(dealEditor.get('[data-own-account]').text()).toBe('Archived Fab Co.')
    expect(dealEditor.get('[data-own-site]').text()).toBe('Archived Fab Site')

    const order: BookingDto = { ...(await api.listBookings({ pageSize: 50 })).data.items.find((item) => item.source === 'Upsell')!, status: 'Cancelled', accountName: 'Archived Fab Co.' }
    const orderEditor = mount(BookingEditorModal, {
      props: { booking: order, accounts: listed.filter((item) => item.id !== order.accountId), contacts: [], defaultOwner: order.owner },
      global: { plugins: [pinia] },
    })
    await flushPromises()
    expect((orderEditor.get('select[aria-label="客户"]').element as HTMLSelectElement).value).toBe(order.accountId)
    expect(orderEditor.get('[data-own-account]').text()).toBe('Archived Fab Co.')

    // An Account the pickers do list is not offered twice.
    const listedDeal = mount(OpportunityEditorModal, {
      props: { opportunity: deal, accounts: [...listed, { ...listed[0]!, id: deal.accountId }], sitesByAccount: { [deal.accountId]: [{ id: deal.siteId, name: 'Fab', city: '', type: '', process: '', status: '量产' }] }, defaultOwner: deal.owner, currentUserId: deal.owner },
      global: { plugins: [pinia] },
    })
    await flushPromises()
    expect(listedDeal.find('[data-own-account]').exists()).toBe(false)
    expect(listedDeal.find('[data-own-site]').exists()).toBe(false)
  })

  it('reads the Contacts of an archived Account by its id when the correction of its cancelled order opens, so the form keeps its Contact', async () => {
    const { api, pinia, router } = await context('Manager', '/booking')
    const base = (await api.listBookings({ pageSize: 50 })).data.items.find((item) => item.source === 'Upsell')!
    const own = (await api.listContacts({ accountId: base.accountId, contactStatus: 'Active', pageSize: 50 })).data.items[0]!
    const order: BookingDto = { ...base, status: 'Cancelled', installedToolId: undefined, primaryContactId: own.id }
    vi.spyOn(api, 'getBooking').mockResolvedValue({ data: order, warnings: [] })
    const contacts = hideFromPickers(api, order.accountId)
    await router.push(`/booking/${order.id}`)
    const wrapper = mount(BookingDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router, ElementPlus] } })
    await flushPromises()

    await wrapper.get('[data-testid="edit-booking"]').trigger('click')
    await flushPromises()
    expect(contacts).toHaveBeenCalledWith(expect.objectContaining({ accountId: order.accountId, contactStatus: 'Active' }))
    const dialog = wrapper.get('[role="dialog"]')
    expect((dialog.get('select[aria-label="选择联系人"]').element as HTMLSelectElement).value).toBe(own.id)
    expect((dialog.get('form').element as HTMLFormElement).checkValidity()).toBe(true)
  })

  it('reads the Contacts of an archived Account by its id when a stakeholder of its deal is edited, so the form keeps its Contact', async () => {
    const { api, pinia, router } = await context('Manager', '/opportunities/OPP-001')
    const deal = (await api.getStrategyOpportunity('OPP-001')).data
    const own = (await api.listContacts({ accountId: deal.accountId, contactStatus: 'Active', pageSize: 50 })).data.items[0]!
    const person = { id: 'STK-ARCHIVED', contactId: own.id, name: own.name, title: own.title, role: 'Decision Maker' as const, influence: 'High' as const, stance: 'Support' as const, coverage: 'Monthly' }
    vi.spyOn(api, 'getStrategyOpportunity').mockResolvedValue({ data: { ...deal, stage: 'lost', lostAtStage: 'quotation_sent', stakeholders: [person] }, warnings: [] })
    const contacts = hideFromPickers(api, deal.accountId)
    const wrapper = mount(OpportunityDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    await wrapper.get('button[aria-label="编辑关键人"]').trigger('click')
    await flushPromises()
    expect(contacts).toHaveBeenCalledWith(expect.objectContaining({ accountId: deal.accountId, contactStatus: 'Active' }))
    expect(wrapper.getComponent(ContactPicker).props('modelValue')).toBe(person.contactId)
    expect((wrapper.get('select[aria-label="选择联系人"]').element as HTMLSelectElement).value).toBe(person.contactId)
  })

  it('reads the Contacts of an archived Account by its id when the list opens the correction of its cancelled order', async () => {
    const { api, pinia, router } = await context('Manager', '/booking')
    const base = (await api.listBookings({ pageSize: 50 })).data.items.find((item) => item.source === 'Upsell')!
    const own = (await api.listContacts({ accountId: base.accountId, contactStatus: 'Active', pageSize: 50 })).data.items[0]!
    const order: BookingDto = { ...base, status: 'Cancelled', installedToolId: undefined, primaryContactId: own.id }
    const listBookings = api.listBookings.bind(api)
    vi.spyOn(api, 'listBookings').mockImplementation(async (query = {}) => {
      const result = await listBookings(query)
      return { ...result, data: { ...result.data, items: result.data.items.map((item) => item.id === order.id ? order : item) } }
    })
    const contacts = hideFromPickers(api, order.accountId)
    const wrapper = mount(BookingPage, { props: { apiClient: api }, global: { plugins: [pinia, router, ElementPlus] } })
    await flushPromises()

    await wrapper.get(`[data-booking-id="${order.id}"] .edit-button`).trigger('click')
    await flushPromises()
    expect(contacts).toHaveBeenCalledWith(expect.objectContaining({ accountId: order.accountId, contactStatus: 'Active' }))
    expect((wrapper.get('[role="dialog"] select[aria-label="选择联系人"]').element as HTMLSelectElement).value).toBe(own.id)
  })

  it('keeps the correction it opened last, with its Contacts, when the Contacts read for an earlier one arrive after it', async () => {
    const { api, pinia, router } = await context('Manager', '/booking')
    const items = (await api.listBookings({ pageSize: 50 })).data.items
    const cancelled = async (item: BookingDto): Promise<BookingDto> => {
      const own = (await api.listContacts({ accountId: item.accountId, contactStatus: 'Active', pageSize: 50 })).data.items[0]!
      return { ...item, status: 'Cancelled', installedToolId: undefined, primaryContactId: own.id }
    }
    const second = await cancelled(items.find((item) => item.source === 'Upsell')!)
    const first = await cancelled(items.find((item) => item.accountId !== second.accountId)!)
    const listBookings = api.listBookings.bind(api)
    vi.spyOn(api, 'listBookings').mockImplementation(async (query = {}) => {
      const result = await listBookings(query)
      return { ...result, data: { ...result.data, items: result.data.items.map((item) => item.id === first.id ? first : item.id === second.id ? second : item) } }
    })
    // Both under archived Accounts: each correction reads its Account's Contacts by its id.
    const contacts = hideFromPickers(api, first.accountId, second.accountId)
    const read = contacts.getMockImplementation()!
    let release: () => void = () => {}
    contacts.mockImplementation(async (query: ContactListQuery = {}) => {
      if (query.accountId === first.accountId) await new Promise<void>((resolve) => { release = resolve })
      return read(query)
    })
    const wrapper = mount(BookingPage, { props: { apiClient: api }, global: { plugins: [pinia, router, ElementPlus] } })
    await flushPromises()

    // The first correction waits for its Contacts; the second opens with its own.
    await wrapper.get(`[data-booking-id="${first.id}"] .edit-button`).trigger('click')
    await wrapper.get(`[data-booking-id="${second.id}"] .edit-button`).trigger('click')
    await flushPromises()
    const editor = () => wrapper.getComponent(BookingEditorModal)
    const contact = () => (wrapper.get('[role="dialog"] select[aria-label="选择联系人"]').element as HTMLSelectElement).value
    expect(editor().props('booking')?.id).toBe(second.id)
    expect(contact()).toBe(second.primaryContactId)
    release()
    await flushPromises()
    expect(editor().props('booking')?.id).toBe(second.id)
    expect(contact()).toBe(second.primaryContactId)
  })

  it('keeps the stakeholder it opened last when the Contacts read for an earlier opening arrive after it', async () => {
    const { api, pinia, router } = await context('Manager', '/opportunities/OPP-001')
    const deal = (await api.getStrategyOpportunity('OPP-001')).data
    const own = (await api.listContacts({ accountId: deal.accountId, contactStatus: 'Active', pageSize: 50 })).data.items[0]!
    const person = { id: 'STK-LATE', contactId: own.id, name: own.name, title: own.title, role: 'Decision Maker' as const, influence: 'High' as const, stance: 'Support' as const, coverage: 'Monthly' }
    vi.spyOn(api, 'getStrategyOpportunity').mockResolvedValue({ data: { ...deal, stage: 'lost', lostAtStage: 'quotation_sent', stakeholders: [person] }, warnings: [] })
    const contacts = hideFromPickers(api, deal.accountId)
    const read = contacts.getMockImplementation()!
    let calls = 0
    let release: () => void = () => {}
    contacts.mockImplementation(async (query: ContactListQuery = {}) => {
      if (query.accountId && ++calls === 1) await new Promise<void>((resolve) => { release = resolve })
      return read(query)
    })
    const wrapper = mount(OpportunityDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    // A new stakeholder first (its read waits), then the existing one (its read answers at once).
    await wrapper.get('[data-testid="new-opportunity-stakeholder"]').trigger('click')
    await wrapper.get('button[aria-label="编辑关键人"]').trigger('click')
    await flushPromises()
    expect(wrapper.getComponent(StakeholderEditorModal).props('stakeholder')?.id).toBe(person.id)
    release()
    await flushPromises()
    expect(wrapper.getComponent(StakeholderEditorModal).props('stakeholder')?.id).toBe(person.id)
  })

  it('says in the stakeholder editor when the archived Account\'s Contacts could not be read', async () => {
    const { api, pinia, router } = await context('Manager', '/opportunities/OPP-001')
    const deal = (await api.getStrategyOpportunity('OPP-001')).data
    vi.spyOn(api, 'getStrategyOpportunity').mockResolvedValue({ data: { ...deal, stage: 'lost', lostAtStage: 'quotation_sent' }, warnings: [] })
    const contacts = hideFromPickers(api, deal.accountId)
    const read = contacts.getMockImplementation()!
    contacts.mockImplementation(async (query: ContactListQuery = {}) => {
      if (query.accountId) throw new CrmApiError('NETWORK_ERROR', 'The Contacts could not be read.', 'req-own-contacts', true)
      return read(query)
    })
    const wrapper = mount(OpportunityDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    await wrapper.get('[data-testid="new-opportunity-stakeholder"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="dialog"]').text()).toContain('The Contacts could not be read.')
  })

  it('closes the profile editor when the page moves on to another Account, and reads an Account named in another case', async () => {
    const { api, router, wrapper } = await detail('Manager', 'ACC-001')
    await wrapper.get('[data-testid="edit-account"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    const other = (await api.listAccounts({ pageSize: 3 })).data.items.find((item) => item.id !== 'ACC-001')!
    await router.push(`/accounts/${other.id}`)
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)

    // The URL names the Account in another case (the server matches it so and answers the Account itself): it is
    // the Account shown.
    const read = api.getAccount360.bind(api)
    vi.spyOn(api, 'getAccount360').mockImplementation(async (id) => read(id.toUpperCase()))
    await router.push('/accounts/acc-001')
    await flushPromises()
    expect(wrapper.find('[data-archive-account]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="edit-account"]').exists()).toBe(true)
  })

  it('shows the refusal of an archive asked for an Account named in another case, and lets it be asked again', async () => {
    const { api, wrapper } = await detail('Manager', 'acc-001', (prepared) => {
      const read = prepared.getAccount360.bind(prepared)
      vi.spyOn(prepared, 'getAccount360').mockImplementation(async (id) => read(id.toUpperCase()))
    })
    const archive = vi.spyOn(api, 'archiveAccount').mockRejectedValue(new CrmApiError('INVALID_TRANSITION', 'An Account with an open Opportunity cannot be archived; close or archive the Opportunity first.', 'req-archive-case', false))
    await wrapper.get('[data-archive-account]').trigger('click')
    await flushPromises()
    await wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()

    expect(archive).toHaveBeenCalledWith('ACC-001')
    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.get('[data-archive-error]').text()).toContain('req-archive-case')
    expect(dialog.get('[data-modal-submit]').attributes('disabled')).toBeUndefined()
  })

  it('saves the profile to the Account it was opened for, and leaves another Account the page moved on to as it is', async () => {
    const { api, router, wrapper } = await detail('Manager', 'acc-001', (prepared) => {
      const read = prepared.getAccount360.bind(prepared)
      vi.spyOn(prepared, 'getAccount360').mockImplementation(async (id) => read(id.toUpperCase()))
    })
    const update = api.updateAccount.bind(api)
    let release: () => void = () => {}
    const updateAccount = vi.spyOn(api, 'updateAccount').mockImplementation(async (...args) => {
      await new Promise<void>((resolve) => { release = resolve })
      return update(...args)
    })
    // The Sites are written after the profile: held here, so the page is seen between the two.
    vi.spyOn(api, 'updateAccountSite').mockImplementation(() => new Promise(() => {}))
    vi.spyOn(api, 'createAccountSite').mockImplementation(() => new Promise(() => {}))
    await wrapper.get('[data-testid="edit-account"]').trigger('click')
    await flushPromises()
    await wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()
    expect(updateAccount.mock.calls[0]![0]).toBe('ACC-001')

    const other = (await api.listAccounts({ pageSize: 3 })).data.items.find((item) => item.id !== 'ACC-001')!
    await router.push(`/accounts/${other.id}`)
    await flushPromises()
    release()
    await flushPromises()
    // The answer is the first Account's: the page, on the other one, keeps it and its controls.
    expect(wrapper.find('[data-archive-account]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="edit-account"]').exists()).toBe(true)
  })

  it('writes the Sites of a save to the Account its editor was opened for, and opens no editor while it is in flight', async () => {
    const { api, router, wrapper } = await detail('Manager', 'acc-001', (prepared) => {
      const read = prepared.getAccount360.bind(prepared)
      vi.spyOn(prepared, 'getAccount360').mockImplementation(async (id) => read(id.toUpperCase()))
    })
    const update = api.updateAccount.bind(api)
    let release: () => void = () => {}
    vi.spyOn(api, 'updateAccount').mockImplementation(async (...args) => {
      await new Promise<void>((resolve) => { release = resolve })
      return update(...args)
    })
    const createSite = vi.spyOn(api, 'createAccountSite')
    const updateSite = vi.spyOn(api, 'updateAccountSite')
    const deleteSite = vi.spyOn(api, 'deleteAccountSite')
    await wrapper.get('[data-testid="edit-account"]').trigger('click')
    await flushPromises()
    // One of its Sites removed, one added, the others kept (and written again).
    const existing = wrapper.findAll('[data-remove-site]')
    expect(existing.length).toBeGreaterThan(1)
    const removedSite = existing[0]!.attributes('data-remove-site')
    await existing[0]!.trigger('click')
    await wrapper.get('[data-add-site]').trigger('click')
    const inputs = wrapper.get('.site-draft:last-of-type').findAll('input')
    await inputs[0]!.setValue('First Account Site')
    await inputs[2]!.setValue('Wafer Fab')
    await inputs[3]!.setValue('28nm')
    await wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()

    // The page moves on while the save is in flight: no editor opens for the other Account until it is done.
    const other = (await api.listAccounts({ pageSize: 3 })).data.items.find((item) => item.id !== 'ACC-001')!
    await router.push(`/accounts/${other.id}`)
    await flushPromises()
    expect(wrapper.get('[data-testid="edit-account"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-manage-sites]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)

    release()
    await flushPromises()
    // Its Sites went to the first Account, under the id it was read with.
    expect(createSite).toHaveBeenCalledWith('ACC-001', expect.objectContaining({ name: 'First Account Site' }))
    expect(deleteSite).toHaveBeenCalledWith('ACC-001', removedSite)
    expect(updateSite).toHaveBeenCalled()
    const accounts = [...createSite.mock.calls, ...updateSite.mock.calls, ...deleteSite.mock.calls].map((call) => call[0])
    expect(accounts).toEqual(accounts.map(() => 'ACC-001'))
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="edit-account"]').attributes('disabled')).toBeUndefined()
  })

  it('keeps the profile editor fields waiting while its save is in flight, and writes the Sites as they were submitted', async () => {
    const { api, wrapper } = await detail('Manager', 'ACC-001')
    const update = api.updateAccountSite.bind(api)
    let release: () => void = () => {}
    let held = false
    const updateSite = vi.spyOn(api, 'updateAccountSite').mockImplementation(async (...args) => {
      if (!held) {
        held = true
        await new Promise<void>((resolve) => { release = resolve })
      }
      return update(...args)
    })
    const deleteSite = vi.spyOn(api, 'deleteAccountSite')
    await wrapper.get('[data-testid="edit-account"]').trigger('click')
    await flushPromises()
    const sites = wrapper.findAll('.site-draft')
    expect(sites.length).toBeGreaterThan(1)
    const ids = wrapper.findAll('[data-remove-site]').map((button) => button.attributes('data-remove-site'))
    await sites[1]!.findAll('input')[0]!.setValue('Submitted Site Name')
    await wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()

    // While the first Site is written, the fields wait; a change made to them anyway is not sent, a removal not done.
    expect(wrapper.get('[data-account-editor-fields]').attributes('disabled')).toBeDefined()
    await wrapper.findAll('.site-draft')[1]!.findAll('input')[0]!.setValue('Typed During The Save')
    await wrapper.get(`[data-remove-site="${ids[0]}"]`).trigger('click')
    await wrapper.get('[data-add-site]').trigger('click')
    release()
    await flushPromises()

    expect(updateSite.mock.calls.map((call) => call[1])).toEqual(ids)
    expect(updateSite.mock.calls[1]![2]).toEqual(expect.objectContaining({ name: 'Submitted Site Name' }))
    expect(deleteSite).not.toHaveBeenCalled()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('removes again on a retry only the Sites its failed save did not remove', async () => {
    const { api, wrapper } = await detail('Manager', 'ACC-001')
    const remove = api.deleteAccountSite.bind(api)
    let failed = false
    const deleteSite = vi.spyOn(api, 'deleteAccountSite').mockImplementation(async (...args) => {
      // The second removal fails once.
      if (deleteSite.mock.calls.length === 2 && !failed) {
        failed = true
        throw new CrmApiError('NETWORK_ERROR', 'The Site could not be removed.', 'req-site-removal', true)
      }
      return remove(...args)
    })
    await wrapper.get('[data-testid="edit-account"]').trigger('click')
    await flushPromises()
    const ids = wrapper.findAll('[data-remove-site]').map((button) => button.attributes('data-remove-site'))
    expect(ids.length).toBeGreaterThan(1)
    await wrapper.get(`[data-remove-site="${ids[0]}"]`).trigger('click')
    await wrapper.get(`[data-remove-site="${ids[1]}"]`).trigger('click')
    await wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="dialog"]').text()).toContain('The Site could not be removed.')

    await wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()
    expect(deleteSite.mock.calls.map((call) => call[1])).toEqual([ids[0], ids[1], ids[1]])
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('shows on the Account the page moved on to no refusal of an earlier archive, and keeps its own archive in flight', async () => {
    const { api, router, wrapper } = await detail('Manager', 'ACC-001')
    const other = (await api.listAccounts({ pageSize: 3 })).data.items.find((item) => item.id !== 'ACC-001')!
    const refusals: Array<(reason: unknown) => void> = []
    vi.spyOn(api, 'archiveAccount').mockImplementation(() => new Promise((_resolve, reject) => { refusals.push(reject) }))
    const archiveShown = async () => {
      await wrapper.get('[data-archive-account]').trigger('click')
      await flushPromises()
      await wrapper.get('[role="dialog"] form').trigger('submit')
      await flushPromises()
    }
    await archiveShown()
    await router.push(`/accounts/${other.id}`)
    await flushPromises()
    // The other Account's own archive goes out; then the first one's refusal arrives.
    await archiveShown()
    expect(wrapper.get('[role="dialog"] [data-modal-submit]').attributes('disabled')).toBeDefined()
    refusals[0]!(new CrmApiError('INVALID_TRANSITION', 'An Account with an open Opportunity cannot be archived; close or archive the Opportunity first.', 'req-earlier-account', false))
    await flushPromises()
    expect(wrapper.text()).not.toContain('req-earlier-account')
    expect(wrapper.get('[role="dialog"] [data-modal-submit]').attributes('disabled')).toBeDefined()
  })

  it('drops an archive answered while the page reads its Account again after another', async () => {
    let holdAgain = false
    let releaseLoad: () => void = () => {}
    const { api, router, wrapper } = await detail('Manager', 'ACC-001', (prepared) => {
      const read = prepared.getAccount360.bind(prepared)
      vi.spyOn(prepared, 'getAccount360').mockImplementation(async (id) => {
        if (holdAgain && id === 'ACC-001') await new Promise<void>((resolve) => { releaseLoad = resolve })
        return read(id)
      })
    })
    const other = (await api.listAccounts({ pageSize: 3 })).data.items.find((item) => item.id !== 'ACC-001')!
    const account = (await api.getAccount360('ACC-001')).data.account
    let settle: (value: { data: AccountSummaryDto; warnings: never[] }) => void = () => {}
    vi.spyOn(api, 'archiveAccount').mockImplementation(() => new Promise((resolve) => { settle = resolve }))
    await wrapper.get('[data-archive-account]').trigger('click')
    await flushPromises()
    await wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()
    await router.push(`/accounts/${other.id}`)
    await flushPromises()
    // Back on the first Account, read again (held): the page still has the other one's record.
    holdAgain = true
    await router.push('/accounts/ACC-001')
    await flushPromises()
    settle({ data: archived(account, 'manager@example.invalid'), warnings: [] })
    await flushPromises()
    expect(wrapper.find('[data-archived-notice]').exists()).toBe(false)
    expect(wrapper.find('[data-unarchive-account]').exists()).toBe(false)
    releaseLoad()
    await flushPromises()
    expect(wrapper.find('[data-archive-account]').exists()).toBe(true)
  })

  it('keeps a new Booking form opened after a correction when that correction Contacts arrive after it', async () => {
    const { api, pinia, router } = await context('Manager', '/booking')
    const base = (await api.listBookings({ pageSize: 50 })).data.items.find((item) => item.source === 'Upsell')!
    const order: BookingDto = { ...base, status: 'Cancelled', installedToolId: undefined }
    const listBookings = api.listBookings.bind(api)
    vi.spyOn(api, 'listBookings').mockImplementation(async (query = {}) => {
      const result = await listBookings(query)
      return { ...result, data: { ...result.data, items: result.data.items.map((item) => item.id === order.id ? order : item) } }
    })
    const contacts = hideFromPickers(api, order.accountId)
    const read = contacts.getMockImplementation()!
    let release: () => void = () => {}
    contacts.mockImplementation(async (query: ContactListQuery = {}) => {
      if (query.accountId === order.accountId) await new Promise<void>((resolve) => { release = resolve })
      return read(query)
    })
    const wrapper = mount(BookingPage, { props: { apiClient: api }, global: { plugins: [pinia, router, ElementPlus] } })
    await flushPromises()

    await wrapper.get(`[data-booking-id="${order.id}"] .edit-button`).trigger('click')
    await wrapper.get('[data-testid="new-booking"]').trigger('click')
    await flushPromises()
    expect(wrapper.getComponent(BookingEditorModal).props('booking')).toBeFalsy()
    release()
    await flushPromises()
    expect(wrapper.getComponent(BookingEditorModal).props('booking')).toBeFalsy()
  })

  it('says in the correction editor of the list when the archived Account Contacts could not be read', async () => {
    const { api, pinia, router } = await context('Manager', '/booking')
    const base = (await api.listBookings({ pageSize: 50 })).data.items.find((item) => item.source === 'Upsell')!
    const order: BookingDto = { ...base, status: 'Cancelled', installedToolId: undefined }
    const listBookings = api.listBookings.bind(api)
    vi.spyOn(api, 'listBookings').mockImplementation(async (query = {}) => {
      const result = await listBookings(query)
      return { ...result, data: { ...result.data, items: result.data.items.map((item) => item.id === order.id ? order : item) } }
    })
    const contacts = hideFromPickers(api, order.accountId)
    const read = contacts.getMockImplementation()!
    contacts.mockImplementation(async (query: ContactListQuery = {}) => {
      if (query.accountId) throw new CrmApiError('NETWORK_ERROR', 'The Contacts could not be read.', 'req-list-contacts', true)
      return read(query)
    })
    const wrapper = mount(BookingPage, { props: { apiClient: api }, global: { plugins: [pinia, router, ElementPlus] } })
    await flushPromises()

    await wrapper.get(`[data-booking-id="${order.id}"] .edit-button`).trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="dialog"]').text()).toContain('The Contacts could not be read.')
  })

  it('offers the stakeholder editor once the page references have arrived', async () => {
    const { api, pinia, router } = await context('Manager', '/opportunities/OPP-001')
    const deal = (await api.getStrategyOpportunity('OPP-001')).data
    const own = (await api.listContacts({ accountId: deal.accountId, contactStatus: 'Active', pageSize: 50 })).data.items[0]!
    const person = { id: 'STK-WAIT', contactId: own.id, name: own.name, title: own.title, role: 'Decision Maker' as const, influence: 'High' as const, stance: 'Support' as const, coverage: 'Monthly' }
    vi.spyOn(api, 'getStrategyOpportunity').mockResolvedValue({ data: { ...deal, stakeholders: [person] }, warnings: [] })
    const accounts = api.listAccounts.bind(api)
    let release: () => void = () => {}
    vi.spyOn(api, 'listAccounts').mockImplementation(async (query = {}) => {
      await new Promise<void>((resolve) => { release = resolve })
      return accounts(query)
    })
    const wrapper = mount(OpportunityDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()
    expect(wrapper.get('[data-testid="new-opportunity-stakeholder"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[aria-label="编辑关键人"]').attributes('disabled')).toBeDefined()
    release()
    await flushPromises()
    expect(wrapper.get('[data-testid="new-opportunity-stakeholder"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('button[aria-label="编辑关键人"]').attributes('disabled')).toBeUndefined()
  })

  it('closes the stakeholder editor when the page moves to another Opportunity', async () => {
    const { pinia, router, api } = await context('Manager', '/opportunities/OPP-001')
    const wrapper = mount(OpportunityDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()
    await wrapper.get('[data-testid="new-opportunity-stakeholder"]').trigger('click')
    await flushPromises()
    expect(wrapper.findComponent(StakeholderEditorModal).exists()).toBe(true)
    await router.push('/opportunities/OPP-003')
    await flushPromises()
    expect(wrapper.findComponent(StakeholderEditorModal).exists()).toBe(false)
  })

  it('opens no stakeholder editor on another Opportunity for an opening answered after the page moved on', async () => {
    const { api, pinia, router } = await context('Manager', '/opportunities/OPP-001')
    const deal = (await api.getStrategyOpportunity('OPP-001')).data
    const getDeal = api.getStrategyOpportunity.bind(api)
    vi.spyOn(api, 'getStrategyOpportunity').mockImplementation(async (id) => id === 'OPP-001'
      ? { data: { ...deal, stage: 'lost', lostAtStage: 'quotation_sent' }, warnings: [] }
      : getDeal(id))
    const contacts = hideFromPickers(api, deal.accountId)
    const read = contacts.getMockImplementation()!
    let release: () => void = () => {}
    contacts.mockImplementation(async (query: ContactListQuery = {}) => {
      if (query.accountId === deal.accountId) await new Promise<void>((resolve) => { release = resolve })
      return read(query)
    })
    const wrapper = mount(OpportunityDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    await wrapper.get('[data-testid="new-opportunity-stakeholder"]').trigger('click')
    await router.push('/opportunities/OPP-003')
    await flushPromises()
    release()
    await flushPromises()
    expect(wrapper.findComponent(StakeholderEditorModal).exists()).toBe(false)
  })

  it('tells a Sales user who does not own an archived Account that its Contact\'s Site is the owner\'s to see', async () => {
    const { api, pinia, router } = await context('Sales', '/contacts/CON-001')
    const original = api.getContact.bind(api)
    vi.spyOn(api, 'getContact').mockImplementation(async (id) => {
      const result = await original(id)
      return { ...result, data: { ...result.data, accountArchived: true, accountOwner: 'owner@example.invalid', contact: { ...result.data.contact, siteId: '', siteName: '' } } }
    })
    hideFromPickers(api, (await original('CON-001')).data.contact.accountId)
    const wrapper = mount(ContactDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(wrapper.text()).toContain('仅客户负责人可见')
  })

  it('shows a Contact of an archived Account read-only, with the notice and without the writes', async () => {
    const { api, pinia, router } = await context('Manager', '/contacts/CON-001')
    // Before the archive, its files take a removal.
    const active = mount(ContactDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()
    expect(active.getComponent(ContactFilesCard).props('canDelete')).toBe(true)
    active.unmount()
    const original = api.getContact.bind(api)
    vi.spyOn(api, 'getContact').mockImplementation(async (id) => {
      const result = await original(id)
      return { ...result, data: { ...result.data, accountArchived: true } }
    })
    const wrapper = mount(ContactDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(wrapper.get('[data-account-archived-notice]').text()).toContain('所属客户已归档')
    for (const control of ['edit-contact', 'merge-contact', 'delete-contact', 'new-opportunity', 'record-visit', 'contact-file-dropzone']) {
      expect(wrapper.find(`[data-testid="${control}"]`).exists(), control).toBe(false)
    }
    expect(wrapper.find('[data-related="opportunities"]').exists()).toBe(true)
    expect(wrapper.getComponent(ContactFilesCard).props('canDelete')).toBe(false)
  })
})
