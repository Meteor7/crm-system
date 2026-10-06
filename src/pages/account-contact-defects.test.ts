import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import type { Component } from 'vue'
import { createMockApi } from '@/api/mock-adapter'
import { CrmApiError, type CrmApi } from '@/api'
import { useAppStore } from '@/stores/app'
import { createAppRouter } from '@/app/router'
import AccountsPage from './AccountsPage.vue'
import AccountDetailPage from './AccountDetailPage.vue'
import ContactsPage from './ContactsPage.vue'

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

const TAKEN = 'An Account with this name exists already.'

describe('the reset of the list filters (F1-03)', () => {
  it('brings the Account list back to the first page when the filters already stand at their defaults', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    // Three pages of Accounts: every page answers with the first page's rows and a total of 25.
    const original = api.listAccounts.bind(api)
    const reads = vi.spyOn(api, 'listAccounts').mockImplementation(async (query) => {
      const result = await original({ ...query, page: 1 })
      return { ...result, meta: { ...result.meta, requestId: result.meta?.requestId ?? 'req_pages', total: 25 } }
    })
    const { wrapper, router } = await open(AccountsPage, '/accounts?page=3', api)
    expect(reads).toHaveBeenLastCalledWith(expect.objectContaining({ page: 3 }))
    expect(wrapper.get('.pagination-controls span').text()).toBe('第 3 / 3 页')

    await wrapper.get('.reset-button').trigger('click')
    await flushPromises()

    expect(reads).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, segment: 'All', city: 'All' }))
    expect(router.currentRoute.value.query.page).toBe('1')
    expect(wrapper.get('.pagination-controls span').text()).toBe('第 1 / 3 页')
    expect(wrapper.get('[data-page-previous]').attributes('disabled')).toBeDefined()
  })

  it('brings the Contact list back to the first page when the filters already stand at their defaults', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const original = api.listContacts.bind(api)
    const reads = vi.spyOn(api, 'listContacts').mockImplementation(async (query) => {
      const result = await original({ ...query, page: 1 })
      return { ...result, meta: { ...result.meta, requestId: result.meta?.requestId ?? 'req_pages', total: 25 } }
    })
    const { wrapper, router } = await open(ContactsPage, '/contacts?page=2', api)
    expect(wrapper.get('.pagination-controls span').text()).toBe('第 2 / 3 页')

    await wrapper.get('.reset-button').trigger('click')
    await flushPromises()

    expect(reads).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, contactStatus: 'Active' }))
    expect(router.currentRoute.value.query.page).toBe('1')
    expect(wrapper.get('.pagination-controls span').text()).toBe('第 1 / 3 页')
  })
})

describe('an Account named like one the user sees (F1-04)', () => {
  it('is created only once the user says it is another company', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const original = api.createAccount.bind(api)
    const create = vi.spyOn(api, 'createAccount').mockImplementation(async (input) => {
      if (!input.confirmDuplicate) throw new CrmApiError('CONFLICT', TAKEN, 'req_taken', false, { name: 'ACC-001, ACC-002' })
      return original(input)
    })
    const { wrapper, router } = await open(AccountsPage, '/accounts', api)
    await wrapper.get('[data-testid="new-account"], .page-actions .primary-button').trigger('click')
    await flushPromises()
    const modal = wrapper.get('[role="dialog"]')
    await modal.get('input[aria-label="客户全称"]').setValue('示例企业014有限公司')
    await modal.get('input[aria-label="客户简称"]').setValue('示例企业015')
    await modal.get('[data-modal-submit]').trigger('submit')
    await flushPromises()

    // The refusal names the Accounts the user may look at, and offers to go on.
    expect(create).toHaveBeenCalledTimes(1)
    expect(create.mock.calls[0]![0].confirmDuplicate).toBe(false)
    expect(modal.get('.form-error').text()).toContain('已有同名的客户。')
    expect(modal.get('[data-duplicate-accounts]').text()).toContain('ACC-001, ACC-002')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)

    // Another name is another question: the offer goes, and the new name is asked about anew.
    await modal.get('input[aria-label="客户全称"]').setValue('示例企业015有限公司')
    expect(modal.find('[data-duplicate-accounts]').exists()).toBe(false)
    await modal.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(create).toHaveBeenCalledTimes(2)
    expect(create.mock.calls[1]![0]).toMatchObject({ name: '示例企业015有限公司', confirmDuplicate: false })
    expect(modal.get('[data-duplicate-accounts]').text()).toContain('ACC-001, ACC-002')

    await modal.get('[data-create-anyway]').trigger('click')
    await flushPromises()
    expect(create).toHaveBeenCalledTimes(3)
    expect(create.mock.calls[2]![0]).toMatchObject({ name: '示例企业015有限公司', confirmDuplicate: true })
    expect(router.currentRoute.value.name).toBe('account-detail')
  })

  it('does not offer the Accounts named like an earlier name to a name typed while that answer was on its way', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    let refuse: (() => void) | undefined
    const create = vi.spyOn(api, 'createAccount').mockImplementation(() => new Promise((_, reject) => {
      refuse = () => reject(new CrmApiError('CONFLICT', TAKEN, 'req_late', false, { name: 'ACC-001' }))
    }))
    const { wrapper } = await open(AccountsPage, '/accounts', api)
    await wrapper.get('[data-testid="new-account"]').trigger('click')
    await flushPromises()
    const modal = wrapper.get('[role="dialog"]')
    await modal.get('input[aria-label="客户全称"]').setValue('示例企业014有限公司')
    await modal.get('input[aria-label="客户简称"]').setValue('示例企业015')
    await modal.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(create).toHaveBeenCalledTimes(1)

    // The name changes while the answer is on its way; the refusal that arrives is for the earlier name.
    await modal.get('input[aria-label="客户全称"]').setValue('示例企业015有限公司')
    refuse!()
    await flushPromises()
    expect(modal.get('.form-error').text()).toContain('已有同名的客户。')
    expect(modal.find('[data-duplicate-accounts]').exists()).toBe(false)
    expect(modal.find('[data-create-anyway]').exists()).toBe(false)
  })

  it('is renamed only once the user says it is another company', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const original = api.updateAccount.bind(api)
    const update = vi.spyOn(api, 'updateAccount').mockImplementation(async (id, input, expectedModified) => {
      if (!input.confirmDuplicate) throw new CrmApiError('CONFLICT', TAKEN, 'req_taken', false, { name: 'ACC-002' })
      return original(id, input, expectedModified)
    })
    const { wrapper } = await open(AccountDetailPage, '/accounts/ACC-001', api)
    await wrapper.get('[data-testid="edit-account"]').trigger('click')
    await flushPromises()
    const modal = wrapper.get('[role="dialog"]')
    await modal.get('input[aria-label="客户全称"]').setValue('示例企业044有限公司')
    await modal.get('[data-modal-submit]').trigger('submit')
    await flushPromises()

    expect(update).toHaveBeenCalledTimes(1)
    expect(modal.get('[data-duplicate-accounts]').text()).toContain('ACC-002')
    // Another name takes the offer away; the name asked about brings it back.
    await modal.get('input[aria-label="客户全称"]').setValue('示例企业044（武汉）')
    expect(modal.find('[data-duplicate-accounts]').exists()).toBe(false)
    await modal.get('input[aria-label="客户全称"]').setValue('示例企业044有限公司')
    expect(modal.find('[data-duplicate-accounts]').exists()).toBe(true)
    await modal.get('[data-save-anyway]').trigger('click')
    await flushPromises()
    expect(update).toHaveBeenCalledTimes(2)
    expect(update.mock.calls[1]![1]).toMatchObject({ name: '示例企业044有限公司', confirmDuplicate: true })
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })
})
