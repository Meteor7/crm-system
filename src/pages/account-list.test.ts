import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import type { Component } from 'vue'
import { createMockApi } from '@/api/mock-adapter'
import type { CrmApi } from '@/api'
import type { AccountSummaryDto, ContactSummaryDto } from '@/types/crm'
import { useAppStore } from '@/stores/app'
import { createAppRouter } from '@/app/router'
import { readAllPages } from '@/features/shared/read-all-pages'
import AccountsPage from './AccountsPage.vue'
import ContactsPage from './ContactsPage.vue'
import AccountDetailPage from './AccountDetailPage.vue'
import ContactDetailPage from './ContactDetailPage.vue'
import AccountProfile from '@/features/accounts/AccountProfile.vue'
import { buildCustomerReportModel } from '@/features/accounts/customer-report-model'
import ContactModal from '@/features/contacts/ContactModal.vue'

async function open(page: Component, path: string, api: CrmApi) {
  const pinia = createPinia()
  useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
  const router = createAppRouter()
  await router.push(path)
  await router.isReady()
  const wrapper = mount(page, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
  await flushPromises()
  return { wrapper, router }
}

describe('the Account list (F1-08, F1-09, F1-11)', () => {
  it('marks every Account Public or Private', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const original = api.listAccounts.bind(api)
    // The double leaves visibility unset: the first row is made Public, the second Private.
    vi.spyOn(api, 'listAccounts').mockImplementation(async (query) => {
      const result = await original(query)
      const items = result.data.items.map((item, index) => ({ ...item, visibility: index === 0 ? 'Public' as const : 'Private' as const }))
      return { ...result, data: { ...result.data, items } }
    })
    const accounts = (await api.listAccounts({ page: 1, pageSize: 50 })).data.items
    const { wrapper } = await open(AccountsPage, '/accounts', api)

    const badges = wrapper.findAll('[data-account-visibility]')
    expect(badges.length).toBe(accounts.length)
    for (const account of accounts) {
      const row = wrapper.get(`[data-account-id="${account.id}"]`)
      expect(row.get('[data-account-visibility]').text()).toBe(account.visibility === 'Public' ? '公开' : '私有')
    }
  })

  it('searches the list on Enter and in the URL, and the reset clears it', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const reads = vi.spyOn(api, 'listAccounts')
    const { wrapper, router } = await open(AccountsPage, '/accounts?page=2', api)
    expect(reads).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, search: undefined }))

    const input = wrapper.get('[data-account-search]')
    await input.setValue('示例企业015')
    await input.trigger('keydown.enter')
    await flushPromises()
    expect(reads).toHaveBeenLastCalledWith(expect.objectContaining({ search: '示例企业015', page: 1 }))
    expect(router.currentRoute.value.query.search).toBe('示例企业015')
    expect(wrapper.findAll('[data-account-id]').length).toBeGreaterThan(0)

    await wrapper.get('.reset-button').trigger('click')
    await flushPromises()
    expect((wrapper.get('[data-account-search]').element as HTMLInputElement).value).toBe('')
    expect(reads).toHaveBeenLastCalledWith(expect.objectContaining({ search: undefined }))
    expect(router.currentRoute.value.query.search).toBeUndefined()
  })

  it('reloads once on a reset, keeps the page a route restore asked for, and reloads nothing while the user types', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const reads = vi.spyOn(api, 'listAccounts')
    const { wrapper, router } = await open(AccountsPage, '/accounts?search=a', api)
    const calls = () => reads.mock.calls.length
    const before = calls()
    await wrapper.get('.reset-button').trigger('click')
    await flushPromises()
    expect(calls()).toBe(before + 1)
    // A route restore (back/forward) with a search and a page keeps that page.
    await router.push('/accounts?search=b&page=2')
    await flushPromises()
    expect(reads).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'b', page: 2 }))
    expect(router.currentRoute.value.query.page).toBe('2')
    // Typing reloads nothing and writes no URL: the list is what the URL says until Enter, which writes both.
    const typed = calls()
    await wrapper.get('[data-account-search]').setValue('typed')
    await flushPromises()
    expect(calls()).toBe(typed)
    expect(router.currentRoute.value.query.search).toBe('b')
    await wrapper.get('[data-account-search]').trigger('keydown.enter')
    await flushPromises()
    expect(reads).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'typed', page: 1 }))
    expect(router.currentRoute.value.query).toMatchObject({ search: 'typed', page: '1' })
    // Text left in the box when leaving the page touches nothing.
    await wrapper.get('[data-account-search]').setValue('c')
    const beforeLeave = calls()
    wrapper.unmount()
    await router.push('/contacts')
    await flushPromises()
    expect(calls()).toBe(beforeLeave)
    expect(router.currentRoute.value.query.search).toBeUndefined()
  })

  it('opens with the search of the URL', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const reads = vi.spyOn(api, 'listAccounts')
    const { wrapper } = await open(AccountsPage, '/accounts?search=示例企业044', api)
    expect(reads).toHaveBeenLastCalledWith(expect.objectContaining({ search: '示例企业044' }))
    expect((wrapper.get('[data-account-search]').element as HTMLInputElement).value).toBe('示例企业044')
  })

  it('turns the page with the search in force, not with text typed but not entered', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const original = api.listAccounts.bind(api)
    // More Accounts than a page, so that the pager shows.
    const reads = vi.spyOn(api, 'listAccounts').mockImplementation(async (query) => {
      const result = await original(query)
      return { ...result, meta: { ...result.meta, requestId: result.meta?.requestId ?? 'req_accounts', total: 30 } }
    })
    const { wrapper, router } = await open(AccountsPage, '/accounts', api)
    await wrapper.get('[data-account-search]').setValue('typed')
    await wrapper.get('[data-page-next]').trigger('click')
    await flushPromises()
    expect(reads).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, search: undefined }))
    expect(router.currentRoute.value.query.page).toBe('2')
    expect(router.currentRoute.value.query.search).toBeUndefined()
    expect((wrapper.get('[data-account-search]').element as HTMLInputElement).value).toBe('typed')
  })

  it('leaves the Enter that ends an IME composition to the composition', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const reads = vi.spyOn(api, 'listAccounts')
    const { wrapper, router } = await open(AccountsPage, '/accounts', api)
    const before = reads.mock.calls.length
    // The characters are still being composed: the model has none of them yet, and the Enter commits them.
    // Chrome and Firefox say so with `isComposing`; WebKit sends the Enter after the composition, with keyCode 229.
    for (const init of [{ isComposing: true }, { isComposing: false, keyCode: 229 }]) {
      const composing = new KeyboardEvent('keydown', { key: 'Enter', cancelable: true, bubbles: true, ...init })
      wrapper.get('[data-account-search]').element.dispatchEvent(composing)
      await flushPromises()
      expect(composing.defaultPrevented).toBe(false)
    }
    expect(reads.mock.calls.length).toBe(before)
    expect(router.currentRoute.value.query.search).toBeUndefined()
  })

  it('says "owner only" where the server zeroed the numbers for a Sales user', async () => {
    const api = createMockApi({ latency: 0, role: 'Sales' })
    const original = api.listAccounts.bind(api)
    vi.spyOn(api, 'listAccounts').mockImplementation(async (query) => {
      const result = await original(query)
      const [first, ...rest] = result.data.items
      const restricted: AccountSummaryDto = { ...first!, visibility: 'Public', metricsRestricted: true, siteCount: 0, pipelineAmount: 0, pipelineMissingAmountCount: 0, intentScore: 0, risk: '稳健', nextAction: '', nextActionDue: '' }
      return { ...result, data: { ...result.data, items: [restricted, ...rest] } }
    })
    const { wrapper } = await open(AccountsPage, '/accounts', api)
    const rows = wrapper.findAll('[data-account-id]')
    const first = rows[0]!
    expect(first.get('[data-account-owner-only]').text()).toBe('仅客户负责人可见')
    expect(first.text()).not.toContain('¥0')
    expect(first.text()).not.toContain('意愿评分')
    expect(first.text()).not.toContain('0 个厂区')
    expect(first.text()).not.toContain('稳健')
    expect(first.text().match(/仅客户负责人可见/g)?.length).toBe(4)
    // The other rows keep their numbers.
    expect(rows[1]!.find('[data-account-owner-only]').exists()).toBe(false)
    expect(rows[1]!.find('[data-account-pipeline]').exists()).toBe(true)
  })
})

describe('the Contact list search (F1-09)', () => {
  it('searches on Enter, keeps the search in the URL, and the reset clears it', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const reads = vi.spyOn(api, 'listContacts')
    const { wrapper, router } = await open(ContactsPage, '/contacts', api)

    const input = wrapper.get('[data-contact-search]')
    await input.setValue('chen')
    await input.trigger('keydown.enter')
    await flushPromises()
    expect(reads).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'chen', page: 1 }))
    expect(router.currentRoute.value.query.search).toBe('chen')

    await wrapper.get('.reset-button').trigger('click')
    await flushPromises()
    expect(reads).toHaveBeenLastCalledWith(expect.objectContaining({ search: undefined }))
    expect(router.currentRoute.value.query.search).toBeUndefined()
  })

  it('leaves the Enter that ends an IME composition to the composition', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const reads = vi.spyOn(api, 'listContacts')
    const { wrapper, router } = await open(ContactsPage, '/contacts', api)
    const before = reads.mock.calls.length
    for (const init of [{ isComposing: true }, { isComposing: false, keyCode: 229 }]) {
      const composing = new KeyboardEvent('keydown', { key: 'Enter', cancelable: true, bubbles: true, ...init })
      wrapper.get('[data-contact-search]').element.dispatchEvent(composing)
      await flushPromises()
      expect(composing.defaultPrevented).toBe(false)
    }
    expect(reads.mock.calls.length).toBe(before)
    expect(router.currentRoute.value.query.search).toBeUndefined()
  })

  it('reloads nothing while the user types, and keeps the page a route restore asked for', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const reads = vi.spyOn(api, 'listContacts')
    const { wrapper, router } = await open(ContactsPage, '/contacts', api)
    const before = reads.mock.calls.length
    await wrapper.get('[data-contact-search]').setValue('typed')
    await flushPromises()
    expect(reads.mock.calls.length).toBe(before)
    expect(router.currentRoute.value.query.search).toBeUndefined()
    await router.push('/contacts?search=b&page=2')
    await flushPromises()
    expect(reads).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'b', page: 2 }))
    expect(router.currentRoute.value.query.page).toBe('2')
    expect((wrapper.get('[data-contact-search]').element as HTMLInputElement).value).toBe('b')
  })

  it('refreshes after a delete with the search in force, and keeps every Contact when reading them again fails', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const original = api.listContacts.bind(api)
    const everyone = await readAllPages((page, pageSize) => original({ contactStatus: 'Active', page, pageSize }))
    const { wrapper, router } = await open(ContactsPage, '/contacts', api)
    // From here on, reading every Contact fails; the list's own reloads go on.
    const reads = vi.spyOn(api, 'listContacts').mockImplementation(async (query) => {
      if (query?.pageSize === 200) throw new Error('all contacts offline')
      return original(query)
    })
    await wrapper.get('[data-contact-search]').setValue('typed')
    const firstRow = wrapper.get('[data-contact-id="CON-001"]').element.closest('tr')!
    const editButton = wrapper.findAll('[data-testid="edit-contact"]').find((button) => button.element.closest('tr') === firstRow)
    await editButton!.trigger('click')
    await wrapper.get('[data-testid="delete-contact-from-edit"]').trigger('click')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[data-contact-id="CON-001"]').exists()).toBe(false)
    // The refresh ran without the draft, the URL says no search, and the draft is still in the box.
    expect(reads.mock.calls.filter(([query]) => query?.pageSize !== 200).every(([query]) => query?.search === undefined)).toBe(true)
    expect(router.currentRoute.value.query.search).toBeUndefined()
    expect((wrapper.get('[data-contact-search]').element as HTMLInputElement).value).toBe('typed')
    // Reading them again failed: the cache is the page, which is the whole set, and the deleted Contact is out of it.
    await wrapper.get('[data-testid="new-contact"]').trigger('click')
    const candidates = wrapper.findComponent(ContactModal).props('contacts') as ContactSummaryDto[]
    expect(candidates.map((item) => item.id)).not.toContain('CON-001')
    expect(candidates.length).toBe(everyone.length - 1)
  })

  it.each([
    ['is the whole set', 0],
    ['is one page of more', 5],
  ])('after a delete whose reloads fail, offers the Contacts it had less the deleted one, when the page %s', async (_case, more) => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const original = api.listContacts.bind(api)
    const everyone = await readAllPages((page, pageSize) => original({ contactStatus: 'Active', page, pageSize }))
    const reads = vi.spyOn(api, 'listContacts').mockImplementation(async (query) => {
      const result = await original(query)
      if (query?.pageSize === 200) return result
      return { ...result, meta: { ...result.meta, requestId: result.meta?.requestId ?? 'req_contacts', total: (result.meta?.total ?? result.data.items.length) + more } }
    })
    const { wrapper } = await open(ContactsPage, '/contacts', api)
    // From the delete on, nothing can be read: the list's reload and the read of every Contact both fail.
    const deleteContact = api.deleteContact.bind(api)
    vi.spyOn(api, 'deleteContact').mockImplementation(async (id) => {
      const result = await deleteContact(id)
      reads.mockRejectedValue(new Error('contacts offline'))
      return result
    })
    const firstRow = wrapper.get('[data-contact-id="CON-001"]').element.closest('tr')!
    const editButton = wrapper.findAll('[data-testid="edit-contact"]').find((button) => button.element.closest('tr') === firstRow)
    await editButton!.trigger('click')
    await wrapper.get('[data-testid="delete-contact-from-edit"]').trigger('click')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('contacts offline')
    await wrapper.get('[data-testid="new-contact"]').trigger('click')
    const candidates = wrapper.findComponent(ContactModal).props('contacts') as ContactSummaryDto[]
    expect(candidates.map((item) => item.id)).not.toContain('CON-001')
    expect(candidates.length).toBe(everyone.length - 1)
  })

  it('after a save whose reloads fail, offers the Contact as saved: not when it has left the company', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const original = api.listContacts.bind(api)
    const everyone = await readAllPages((page, pageSize) => original({ contactStatus: 'Active', page, pageSize }))
    const reads = vi.spyOn(api, 'listContacts').mockImplementation(original)
    const { wrapper } = await open(ContactsPage, '/contacts', api)
    // From the save on, nothing can be read.
    const updateContact = api.updateContact.bind(api)
    vi.spyOn(api, 'updateContact').mockImplementation(async (id, input, modified) => {
      const result = await updateContact(id, input, modified)
      reads.mockRejectedValue(new Error('contacts offline'))
      return result
    })
    const firstRow = wrapper.get('[data-contact-id="CON-001"]').element.closest('tr')!
    const editButton = wrapper.findAll('[data-testid="edit-contact"]').find((button) => button.element.closest('tr') === firstRow)
    await editButton!.trigger('click')
    await wrapper.get('[aria-label="联系人状态"]').setValue('Left Company')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('contacts offline')
    await wrapper.get('[data-testid="new-contact"]').trigger('click')
    const candidates = wrapper.findComponent(ContactModal).props('contacts') as ContactSummaryDto[]
    expect(candidates.map((item) => item.id)).not.toContain('CON-001')
    expect(candidates.length).toBe(everyone.length - 1)
  })

  it('reads every Contact at its start even after a save that put one in the cache meanwhile', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const original = api.listContacts.bind(api)
    const everyone = await readAllPages((page, pageSize) => original({ contactStatus: 'Active', page, pageSize }))
    const held = { release: null as null | (() => void) }
    let wholeSetReads = 0
    vi.spyOn(api, 'listContacts').mockImplementation(async (query) => {
      // The page's first request (the Archived list) is slow; the save's reload of it is not.
      if (query?.contactStatus === 'Archived' && !held.release) await new Promise<void>((resolve) => { held.release = resolve })
      // The read of every Contact after the save fails; the page's own, at its start, does not.
      if (query?.pageSize === 200 && ++wholeSetReads === 1) throw new Error('contacts offline')
      return original(query)
    })
    const { wrapper } = await open(ContactsPage, '/contacts?contactStatus=Archived', api)
    await wrapper.get('[data-testid="new-contact"]').trigger('click')
    await wrapper.get('[aria-label="联系人姓名"]').setValue('新来的人')
    await wrapper.get('[aria-label="联系人职位"]').setValue('工程师')
    await wrapper.get('[aria-label="联系人部门"]').setValue('研发')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    // The first request returns, late and superseded; the cache holds the saved Contact alone, which is no whole set:
    // the page reads them all, as it would have with nothing in the cache.
    held.release!()
    await flushPromises()
    await wrapper.get('[data-testid="new-contact"]').trigger('click')
    const candidates = wrapper.findComponent(ContactModal).props('contacts') as ContactSummaryDto[]
    expect(candidates.length).toBe(everyone.length + 1)
    expect(candidates.map((item) => item.name)).toContain('新来的人')
  })

  it('does not let a read of every Contact that returns after a delete bring the deleted one back', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const original = api.listContacts.bind(api)
    const everyone = await readAllPages((page, pageSize) => original({ contactStatus: 'Active', page, pageSize }))
    const held = { release: null as null | (() => void) }
    vi.spyOn(api, 'listContacts').mockImplementation(async (query) => {
      const result = await original(query)
      // The page is one of more, so the page's start reads every Contact: that first read is slow, and answers
      // what it read before the delete.
      if (query?.pageSize !== 200) return { ...result, meta: { ...result.meta, requestId: result.meta?.requestId ?? 'req_contacts', total: (result.meta?.total ?? result.data.items.length) + 5 } }
      if (!held.release) await new Promise<void>((resolve) => { held.release = resolve })
      return result
    })
    const { wrapper } = await open(ContactsPage, '/contacts', api)
    const firstRow = wrapper.get('[data-contact-id="CON-001"]').element.closest('tr')!
    const editButton = wrapper.findAll('[data-testid="edit-contact"]').find((button) => button.element.closest('tr') === firstRow)
    await editButton!.trigger('click')
    await wrapper.get('[data-testid="delete-contact-from-edit"]').trigger('click')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[data-contact-id="CON-001"]').exists()).toBe(false)
    // The delete's reload and its read of every Contact are done; the start's read returns now, CON-001 in it.
    held.release!()
    await flushPromises()
    await wrapper.get('[data-testid="new-contact"]').trigger('click')
    const candidates = wrapper.findComponent(ContactModal).props('contacts') as ContactSummaryDto[]
    expect(candidates.map((item) => item.id)).not.toContain('CON-001')
    expect(candidates.length).toBe(everyone.length - 1)
  })

  it('does not take a searched page for the whole set, however late its response', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const original = api.listContacts.bind(api)
    const everyone = await readAllPages((page, pageSize) => original({ contactStatus: 'Active', page, pageSize }))
    let release!: () => void
    const gate = new Promise<void>((resolve) => { release = resolve })
    // The search's response (one Contact) waits until the box has been cleared (which applies no search).
    vi.spyOn(api, 'listContacts').mockImplementation(async (query) => {
      const result = await original(query)
      if (!query?.search) return result
      await gate
      return { ...result, data: { ...result.data, items: everyone.slice(0, 1) }, meta: { ...result.meta, requestId: result.meta?.requestId ?? 'req_search', total: 1 } }
    })
    const { wrapper } = await open(ContactsPage, '/contacts?search=chen', api)
    await wrapper.get('[data-contact-search]').setValue('')
    release()
    await flushPromises()
    await wrapper.get('[data-testid="new-contact"]').trigger('click')
    const candidates = wrapper.findComponent(ContactModal).props('contacts') as ContactSummaryDto[]
    expect(everyone.length).toBeGreaterThan(1)
    expect(candidates.length).toBe(everyone.length)
  })
})

describe('the customer report of someone else\'s Public Account (F1-11)', () => {
  it('carries the owner-only row in place of the risks the server zeroed', async () => {
    const api = createMockApi({ latency: 0, role: 'Sales' })
    const detail = (await api.getAccount360('ACC-001')).data
    const restricted = { ...detail, account: { ...detail.account, visibility: 'Public' as const, metricsRestricted: true, risk: '稳健' as const } }
    expect(JSON.stringify(buildCustomerReportModel(restricted, '2026-10-04', 'zh-CN'))).toContain('仅客户负责人可见')
    expect(JSON.stringify(buildCustomerReportModel(restricted, '2026-10-04', 'en-US'))).toContain('Visible to the account owner only')
    expect(JSON.stringify(buildCustomerReportModel(detail, '2026-10-04', 'zh-CN'))).not.toContain('仅客户负责人可见')
  })
})

describe('the Account profile of someone else\'s Public Account (F1-08, F1-11)', () => {
  it('shows the visibility and says the Sites are the owner\'s to see', async () => {
    const api = createMockApi({ latency: 0, role: 'Sales' })
    const snapshot = await api.getAccount360('ACC-001')
    snapshot.data.account = { ...snapshot.data.account, visibility: 'Public', metricsRestricted: true, siteCount: 0 }
    snapshot.data.sites = []
    vi.spyOn(api, 'getAccount360').mockResolvedValue(snapshot)
    const wrapper = mount(AccountProfile, { props: { accountId: 'ACC-001', apiClient: api }, global: { plugins: [createPinia()] } })
    await flushPromises()

    expect(wrapper.get('[data-account-visibility]').text()).toBe('公开')
    expect(wrapper.get('[data-sites-owner-only]').text()).toBe('仅客户负责人可见')
    expect(wrapper.text()).not.toContain('暂无厂区记录')
    wrapper.unmount()
  })
})

describe('the "Back to" control of a record opened from its list', () => {
  async function context() {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const pinia = createPinia()
    useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
    const router = createAppRouter()
    const mountAt = async (page: Component, path: string) => {
      await router.push(path)
      await router.isReady()
      const wrapper = mount(page, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
      await flushPromises()
      return wrapper
    }
    return { api, router, mountAt }
  }

  it.each([
    ['Account', AccountsPage, AccountDetailPage, '/accounts?search=%E5%8F%B0&pageSize=25', '[data-open-account-detail]', 'listAccounts', '/accounts'],
    ['Contact', ContactsPage, ContactDetailPage, '/contacts?search=Chen&contactStatus=All', '[data-contact-id]', 'listContacts', '/contacts'],
  ] as const)('returns to the %s list as it was: its search, filters and page', async (_label, listPage, detailPage, listPath, rowSelector, listMethod, plainList) => {
    const { api, router, mountAt } = await context()
    // The rows are the double's whatever the search says; the search itself is the server's to match.
    const original = api[listMethod].bind(api) as (query: Record<string, unknown>) => Promise<unknown>
    vi.spyOn(api, listMethod).mockImplementation(((query: Record<string, unknown>) => original({ ...query, search: undefined })) as never)
    const list = await mountAt(listPage, listPath)
    const listUrl = router.currentRoute.value.fullPath
    expect(listUrl).toBe(listPath)

    await list.get(rowSelector).trigger('click')
    await flushPromises()
    const record = router.currentRoute.value
    expect(record.name).toBe(plainList === '/accounts' ? 'account-detail' : 'contact-detail')
    // The record's URL carries the list's, so that a reload of the record keeps its way back.
    expect(record.query.from).toBe(listUrl)
    // Unmounting the list, the router's last app, resets the router; the record is opened by its URL.
    list.unmount()

    const detail = await mountAt(detailPage, record.fullPath)
    expect(detail.get('.detail-back-button').attributes('href')).toBe(listUrl)
    detail.unmount()
  })

  it.each([
    ['Account', AccountDetailPage, '/accounts/ACC-001', '/accounts'],
    ['Contact', ContactDetailPage, '/contacts/CON-001', '/contacts'],
  ] as const)('returns to the plain %s list when opened elsewhere, or with a way back that is not the list', async (_label, detailPage, detailPath, plainList) => {
    const { mountAt } = await context()
    for (const from of [undefined, '/dashboard', '/visits?search=x', 'https://example.invalid/accounts', plainList === '/accounts' ? '/contacts?search=x' : '/accounts?search=x', 'not a path']) {
      const detail = await mountAt(detailPage, from === undefined ? detailPath : `${detailPath}?from=${encodeURIComponent(from)}`)
      expect(detail.get('.detail-back-button').attributes('href'), `from=${from}`).toBe(plainList)
      detail.unmount()
    }
  })
})
