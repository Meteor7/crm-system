import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { CrmApiError, type CrmApi } from '@/api'
import { useAppStore } from '@/stores/app'
import { createAppRouter } from '@/app/router'
import ContactsPage from './ContactsPage.vue'
import ContactDetailPage from './ContactDetailPage.vue'
import ContactModal from '@/features/contacts/ContactModal.vue'
import ContactPicker from '@/features/contacts/ContactPicker.vue'

async function pageContext(role: 'Manager' | 'Manager' = 'Manager') {
  const api = createMockApi({ latency: 0, role })
  const pinia = createPinia()
  useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
  const router = createAppRouter()
  return { api, pinia, router }
}

describe('Contacts pages', () => {
  it('opens an independent detail route instead of a drawer', async () => {
    const { api, pinia, router } = await pageContext()
    await router.push('/contacts')
    await router.isReady()
    const wrapper = mount(ContactsPage, {
      props: { apiClient: api },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    await wrapper.get('[data-contact-id="CON-001"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/contacts/CON-001')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('uses initial account and status query filters without a page search box', async () => {
    const { api, pinia, router } = await pageContext()
    await router.push('/contacts?accountId=ACC-001&contactStatus=Active')
    const wrapper = mount(ContactsPage, {
      props: { apiClient: api },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    expect(wrapper.find('[aria-label="搜索联系人"]').exists()).toBe(false)
    expect(wrapper.get('[aria-label="客户筛选"]').element).toHaveProperty('value', 'ACC-001')
    expect(wrapper.get('[aria-label="状态筛选"]').element).toHaveProperty('value', 'Active')
    expect(wrapper.findAll('[data-contact-id]').length).toBeGreaterThan(0)
  })

  it('defaults to active Contacts and exposes Archived through explicit filters', async () => {
    const { api, pinia, router } = await pageContext()
    const archivedId = 'CON-001'
    const archived = (await api.getContact(archivedId)).data.contact
    const { id, dataQuality: _dataQuality, updatedAt: _updatedAt, modified: _modified, ...input } = archived
    await api.updateContact(id, { ...input, status: 'Archived' })
    await router.push('/contacts')
    const activeWrapper = mount(ContactsPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(activeWrapper.find(`[data-contact-id="${archivedId}"]`).exists()).toBe(false)

    await router.push('/contacts?contactStatus=Archived')
    const archivedWrapper = mount(ContactsPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()
    expect(archivedWrapper.find(`[data-contact-id="${archivedId}"]`).exists()).toBe(true)

    await router.push('/contacts?contactStatus=All')
    const allWrapper = mount(ContactsPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()
    expect(allWrapper.get('[aria-label="状态筛选"]').element).toHaveProperty('value', 'All')
    expect(allWrapper.find(`[data-contact-id="${archivedId}"]`).exists()).toBe(true)
    expect(allWrapper.find('[data-contact-id="CON-002"]').exists()).toBe(true)
  })

  it('renders genuine related business links on the Contact detail subpage', async () => {
    const { api, pinia, router } = await pageContext()
    const sourceTimelineApi: CrmApi = {
      ...api,
      getContact: async (id) => {
        const result = await api.getContact(id)
        return { ...result, data: { ...result.data, timeline: [{ id: 'visit:V-001', at: '2026-07-28', type: 'Visit', title: 'Source visit', summary: 'Recorded', href: '/visits?source=V-001' }] } }
      },
    }
    await router.push('/contacts/CON-001')
    const wrapper = mount(ContactDetailPage, {
      props: { apiClient: sourceTimelineApi },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    expect(wrapper.get('[data-related="opportunities"]').attributes('href')).toContain('contactId=CON-001')
    expect(wrapper.get('[data-related="visits"]').attributes('href')).toContain('contactId=CON-001')
    expect(wrapper.get('[data-related="demo-requests"]').attributes('href')).toContain('contactId=CON-001')
    expect(wrapper.get('[data-related="bookings"]').attributes('href')).toContain('contactId=CON-001')
    expect(wrapper.get('[data-timeline-id="visit:V-001"]').attributes('href')).toBe('/visits?source=V-001')
    expect(wrapper.find('[data-testid="contact-drawer"]').exists()).toBe(false)
  })

  it('keeps write and merge actions role-aware', async () => {
    const management = await pageContext('Manager')
    await management.router.push('/contacts/CON-001')
    const managementView = mount(ContactDetailPage, {
      props: { apiClient: management.api },
      global: { plugins: [management.pinia, management.router] },
    })
    await flushPromises()
    expect(managementView.find('[data-testid="edit-contact"]').exists()).toBe(true)
    expect(managementView.find('[data-testid="merge-contact"]').exists()).toBe(true)
    expect(managementView.find('[data-testid="new-opportunity"]').exists()).toBe(true)
    expect(managementView.find('[data-testid="record-visit"]').exists()).toBe(true)

    const admin = await pageContext()
    await admin.router.push('/contacts/CON-001')
    const editable = mount(ContactDetailPage, {
      props: { apiClient: admin.api },
      global: { plugins: [admin.pinia, admin.router] },
    })
    await flushPromises()
    expect(editable.find('[data-testid="edit-contact"]').exists()).toBe(true)
    expect(editable.find('[data-testid="merge-contact"]').exists()).toBe(true)
    expect(editable.get('[data-testid="merge-contact"]').element.closest('.section-card')).toBeNull()
    expect(editable.get('[data-testid="delete-contact"]').classes()).toContain('delete-button')
    expect(editable.find('[data-testid="contact-file-dropzone"]').exists()).toBe(true)
    expect(editable.text()).toContain('文件 (0)')
    expect(editable.text()).not.toContain('合并会迁移业务关联并归档重复记录')
  })

  it('renders Contacts from another public Account as genuinely read-only', async () => {
    const source = createMockApi({ latency: 0, role: 'Manager' })
    const sales = createMockApi({ latency: 0, role: 'Sales', userId: 'readonly.sales@example.invalid' })
    const accountResponse = await source.listAccounts({ page: 1, pageSize: 100 })
    const sourceContactResponse = await source.getContact('CON-001')
    const account360Response = await source.getAccount360(sourceContactResponse.data.contact.accountId)
    const contactListResponse = await source.listContacts({ accountId: sourceContactResponse.data.contact.accountId, page: 1, pageSize: 100 })
    const fileListResponse = await source.listContactFiles('CON-001', { page: 1, pageSize: 200 })
    const account = {
      ...account360Response.data.account,
      owner: 'account.owner@example.invalid',
      visibility: 'Public' as const,
    }
    const { siteId: _siteId, siteName: _siteName, ...contactWithoutSite } = sourceContactResponse.data.contact
    const contact = {
      ...contactWithoutSite,
      accountId: account.id,
      accountName: account.name,
      accountShortName: account.shortName,
    }
    const readonlyApi: CrmApi = {
      ...sales,
      listAccounts: async () => ({
        ...accountResponse,
        data: { items: [account] },
        meta: { ...accountResponse.meta, requestId: accountResponse.meta?.requestId ?? 'req_readonly_accounts', total: 1 },
      }),
      listContacts: async () => ({
        ...contactListResponse,
        data: { items: [contact] },
        meta: { ...contactListResponse.meta, requestId: contactListResponse.meta?.requestId ?? 'req_readonly_contacts', total: 1 },
      }),
      getContact: async () => ({
        ...sourceContactResponse,
        data: { ...sourceContactResponse.data, contact },
      }),
      getAccount360: async () => ({
        ...account360Response,
        data: { ...account360Response.data, account, sites: [], contacts: [contact] },
      }),
      listContactFiles: async () => ({
        ...fileListResponse,
        data: { items: [] },
        meta: { ...fileListResponse.meta, requestId: fileListResponse.meta?.requestId ?? 'req_readonly_files', total: 0 },
      }),
    }
    const pinia = createPinia()
    useAppStore(pinia).bootstrap = (await sales.getBootstrap()).data
    const router = createAppRouter()
    await router.push('/contacts')
    const listView = mount(ContactsPage, {
      props: { apiClient: readonlyApi },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    expect(listView.text()).toContain('仅客户负责人可见')
    expect(listView.find('[data-testid="edit-contact"]').exists()).toBe(false)
    expect(listView.find('[data-testid="new-contact"]').exists()).toBe(false)
    listView.unmount()

    await router.push(`/contacts/${contact.id}`)
    const detailView = mount(ContactDetailPage, {
      props: { apiClient: readonlyApi },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    expect(detailView.text()).toContain('仅客户负责人可见')
    expect(detailView.find('[data-testid="edit-contact"]').exists()).toBe(false)
    expect(detailView.find('[data-testid="new-opportunity"]').exists()).toBe(false)
    expect(detailView.find('[data-testid="record-visit"]').exists()).toBe(false)
    expect(detailView.find('[data-testid="contact-file-dropzone"]').exists()).toBe(false)
  })

  it('uploads and removes a file from the Contact Files card', async () => {
    const { api, pinia, router } = await pageContext()
    await router.push('/contacts/CON-001')
    const wrapper = mount(ContactDetailPage, {
      props: { apiClient: api },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    const input = wrapper.get('input[type="file"]')
    const file = new File(['contact profile'], 'profile.pdf', { type: 'application/pdf' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await flushPromises()

    expect(wrapper.text()).toContain('文件 (1)')
    expect(wrapper.text()).toContain('profile.pdf')

    await wrapper.get('[aria-label="删除 profile.pdf"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('文件 (0)')
    expect(wrapper.text()).not.toContain('profile.pdf')
  })

  it('falls back safely when a hot-reloaded API object lacks Contact file methods', async () => {
    const { api, pinia, router } = await pageContext()
    const legacyApi = {
      ...api,
      listContactFiles: undefined,
      uploadContactFiles: undefined,
      getContactFile: undefined,
      deleteContactFile: undefined,
    } as unknown as CrmApi
    await router.push('/contacts/CON-001')
    const wrapper = mount(ContactDetailPage, {
      props: { apiClient: legacyApi },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="contact-file-dropzone"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('listContactFiles is not a function')
    expect(wrapper.text()).not.toContain('联系人文件接口尚未加载')
  })

  it('confirms administrator hard delete and returns to the list', async () => {
    const { api, pinia, router } = await pageContext()
    await router.push('/contacts/CON-001')
    const activeDetail = mount(ContactDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    await activeDetail.get('[data-testid="edit-contact"]').trigger('click')
    expect(activeDetail.find('[data-testid="delete-contact-from-edit"]').exists()).toBe(true)
    await activeDetail.get('[data-testid="delete-contact-from-edit"]').trigger('click')
    expect(activeDetail.find('[role="dialog"]').exists()).toBe(true)
    expect(activeDetail.get('[role="dialog"]').text()).toContain('不可恢复')
    await activeDetail.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/contacts')
    await expect(api.getContact('CON-001')).rejects.toMatchObject({ code: 'NOT_FOUND' })
  })

  it('removes the retired Needs Review migration records from local Contacts', async () => {
    const { api, pinia, router } = await pageContext()
    await router.push('/contacts?contactStatus=All')
    const wrapper = mount(ContactsPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    for (const name of ['王志远', '陈珂', '赵昕', '李敏', '周楠', '顾晓', '马会东', '孙强', '钱宇']) {
      expect(wrapper.text()).not.toContain(name)
    }
    expect(wrapper.find('[data-testid="needs-review"]').exists()).toBe(false)
  })

  it('offers hard delete from the list edit modal and refreshes the list', async () => {
    const { api, pinia, router } = await pageContext()
    await router.push('/contacts')
    const wrapper = mount(ContactsPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    const firstRow = wrapper.get('[data-contact-id="CON-001"]').element.closest('tr')!
    const editButton = wrapper.findAll('[data-testid="edit-contact"]').find((button) => button.element.closest('tr') === firstRow)
    expect(editButton).toBeDefined()
    await editButton!.trigger('click')
    expect(wrapper.find('[data-testid="delete-contact-from-edit"]').exists()).toBe(true)
    await wrapper.get('[data-testid="delete-contact-from-edit"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('不可恢复')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()

    expect(wrapper.find('[data-contact-id="CON-001"]').exists()).toBe(false)
    await expect(api.getContact('CON-001')).rejects.toMatchObject({ code: 'NOT_FOUND' })
  })

  it('keeps Contact detail content available when reference loading fails', async () => {
    const { api, pinia, router } = await pageContext()
    const failingReferences: CrmApi = {
      ...api,
      listAccounts: async () => { throw new Error('reference service unavailable') },
    }
    await router.push('/contacts/CON-001')
    const wrapper = mount(ContactDetailPage, {
      props: { apiClient: failingReferences },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain((await api.getContact('CON-001')).data.contact.name)
    expect(wrapper.find('[data-related="opportunities"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="edit-contact"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="contact-references-unavailable"]').exists()).toBe(true)
  })

  it('renders empty, error, and denied states for Contact lists', async () => {
    const empty = await pageContext()
    const emptyApi: CrmApi = { ...empty.api, listContacts: () => empty.api.listContacts({ search: '__none__' }) }
    await empty.router.push('/contacts')
    const emptyWrapper = mount(ContactsPage, { props: { apiClient: emptyApi }, global: { plugins: [empty.pinia, empty.router] } })
    await flushPromises()
    expect(emptyWrapper.find('.state-empty').exists()).toBe(true)

    const error = await pageContext()
    const errorApi: CrmApi = { ...error.api, listContacts: async () => { throw new CrmApiError('NETWORK_ERROR', 'contact list failed', 'req_contacts_error', true) } }
    await error.router.push('/contacts')
    const errorWrapper = mount(ContactsPage, { props: { apiClient: errorApi }, global: { plugins: [error.pinia, error.router] } })
    await flushPromises()
    expect(errorWrapper.find('.state-error').exists()).toBe(true)

    const denied = await pageContext()
    const deniedApi: CrmApi = { ...denied.api, listContacts: async () => { throw new CrmApiError('PERMISSION_DENIED', 'contact list denied', 'req_contacts_denied') } }
    await denied.router.push('/contacts')
    const deniedWrapper = mount(ContactsPage, { props: { apiClient: deniedApi }, global: { plugins: [denied.pinia, denied.router] } })
    await flushPromises()
    expect(deniedWrapper.find('.state-denied').exists()).toBe(true)
  })

  it('keeps complete reporting choices after saving while a list filter is active', async () => {
    const { api, pinia, router } = await pageContext()
    await router.push({ path: '/contacts', query: { accountId: 'ACC-001', search: (await api.getContact('CON-001')).data.contact.name } })
    const wrapper = mount(ContactsPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    await wrapper.get('[data-testid="edit-contact"]').trigger('click')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    await wrapper.get('[data-testid="new-contact"]').trigger('click')

    expect(wrapper.find('[data-reports-to-option="CON-002"]').exists()).toBe(true)
  })

  it('merges a selected duplicate and stays on the survivor Contact page', async () => {
    const { api, pinia, router } = await pageContext()
    await router.push('/contacts/CON-001')
    const wrapper = mount(ContactDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    await wrapper.get('[data-testid="merge-contact"]').trigger('click')
    await wrapper.get('select').setValue('CON-002')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/contacts/CON-001')
    expect((await api.getContact('CON-002')).data.contact.status).toBe('Archived')
  })

  it('keeps the current Contact visible when merge reports a conflict', async () => {
    const { api, pinia, router } = await pageContext()
    const conflictingApi: CrmApi = {
      ...api,
      mergeContacts: async () => { throw new CrmApiError('CONTACT_MERGE_CONFLICT', 'merge conflict', 'req_merge_conflict') },
    }
    await router.push('/contacts/CON-001')
    const wrapper = mount(ContactDetailPage, { props: { apiClient: conflictingApi }, global: { plugins: [pinia, router] } })
    await flushPromises()

    await wrapper.get('[data-testid="merge-contact"]').trigger('click')
    await wrapper.get('select').setValue('CON-002')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('merge conflict')
    expect(router.currentRoute.value.path).toBe('/contacts/CON-001')
    expect(wrapper.text()).toContain((await api.getContact('CON-001')).data.contact.name)
  })

  it('limits site and reporting choices to the selected account', async () => {
    const api = createMockApi({ latency: 0 })
    const accounts = (await api.listAccounts({ pageSize: 100 })).data.items
    const account = (await api.getAccount360('ACC-001')).data
    const otherAccount = (await api.getAccount360('ACC-002')).data
    const wrapper = mount(ContactModal, {
      props: {
        accounts,
        sites: [
          ...account.sites.map((site) => ({ ...site, accountId: 'ACC-001' })),
          ...otherAccount.sites.map((site) => ({ ...site, accountId: 'ACC-002' })),
        ],
        contacts: [...account.contacts, ...otherAccount.contacts],
        fixedAccountId: 'ACC-001',
      },
    })

    expect(wrapper.get('[aria-label="所属客户"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-site-option="SITE-001"]').exists()).toBe(true)
    expect(wrapper.find('[data-site-option="SITE-003"]').exists()).toBe(false)
    expect(wrapper.find('[data-reports-to-option="CON-004"]').exists()).toBe(false)
  })

  it('only offers active Contacts from the chosen account in the reusable picker', async () => {
    const api = createMockApi({ latency: 0 })
    const first = (await api.listContacts({ accountId: 'ACC-001', pageSize: 100 })).data.items
    const second = (await api.listContacts({ accountId: 'ACC-002', pageSize: 100 })).data.items
    const wrapper = mount(ContactPicker, {
      props: { contacts: [...first, ...second], accountId: 'ACC-001' },
    })

    expect(wrapper.find('[data-contact-option="CON-001"]').exists()).toBe(true)
    expect(wrapper.find('[data-contact-option="CON-004"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="create-contact"]').text()).toContain('快速新增联系人')
  })

  it('redirects the retired stakeholders route to Contacts', async () => {
    const router = createAppRouter()
    await router.push('/stakeholders')
    await router.isReady()
    expect(router.currentRoute.value.path).toBe('/contacts')
  })
})
