import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
import { CrmApiError, type CrmApi } from '@/api'
import { createMockApi } from '@/api/mock-adapter'
import { createDemoRepository, createMemoryDemoStorage, seedDemoSnapshot } from '@/demo/demo-repository'
import { createAppRouter } from '@/app/router'
import DemoRequestModal from '@/features/demo-requests/DemoRequestModal.vue'
import type { CreateDemoRequestInput } from '@/types/crm'
import DemoRequestsPage from './DemoRequestsPage.vue'

describe('a Demo Request save the server refuses', () => {
  it('is answered in the dialog, with the fields it names flagged, not on the page behind it', async () => {
    const api = createMockApi({ role: 'Sales', latency: 0 })
    vi.spyOn(api, 'createDemoRequest').mockRejectedValue(
      new CrmApiError('VALIDATION_ERROR', 'Demo Request form is incomplete.', 'req_demo_refused', false, { 'wafers.1.slotId': 'Required' }),
    )
    const router = createAppRouter()
    await router.push('/demo-requests'); await router.isReady()
    const wrapper = mount(DemoRequestsPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()

    await wrapper.get('[data-testid="new-demo-request"]').trigger('click')
    await wrapper.get('[data-add-wafer]').trigger('click')
    // What the dialog sends is its own business; here the server refuses whatever it gets.
    wrapper.findComponent(DemoRequestModal).vm.$emit('submit', {} as CreateDemoRequestInput)
    await flushPromises()

    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    const refusal = wrapper.get('[data-modal-error]')
    expect(refusal.get('span').text()).not.toBe('')
    expect(refusal.text()).toContain('Request ID · req_demo_refused')
    expect(wrapper.get('[data-field-error="wafers.1.slotId"]').text()).toBe('请填写此项')
    expect(wrapper.find('[data-api-error]').exists()).toBe(false)

    // Closed, the refusal goes with the dialog: the page does not show it afterwards.
    await wrapper.get('[role="dialog"] footer .secondary-button').trigger('click')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.find('[data-api-error]').exists()).toBe(false)
  })

  it('keeps the errors of the page\'s own actions out of the dialog, and a late refusal out of the next dialog', async () => {
    // The seeded DR-101, put back to Draft, is a record the Sales view offers to submit.
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      snapshot.demoRequests.find((item) => item.id === 'DR-101')!.status = 'Draft'
    })
    const api = createMockApi({ repository, latency: 0 })
    const refused = new CrmApiError('INTERNAL_ERROR', 'Demo Request could not be submitted.', 'req_submit_refused', true)
    vi.spyOn(api, 'transitionDemoRequest').mockRejectedValue(refused)
    const held = { reject: null as null | ((reason: unknown) => void) }
    vi.spyOn(api, 'createDemoRequest').mockImplementation(() => new Promise((_resolve, reject) => { held.reject = reject }))
    const router = createAppRouter()
    await router.push('/demo-requests'); await router.isReady()
    const wrapper = mount(DemoRequestsPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()

    // A page action refused: the banner, and a dialog opened after it shows nothing of it.
    await wrapper.get('[data-demo-view="sales"]').trigger('click')
    await wrapper.get('[data-demo-action="DR-101-submit"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-api-error]').text()).toContain('req_submit_refused')
    await wrapper.get('[data-testid="new-demo-request"]').trigger('click')
    expect(wrapper.find('[data-modal-error]').exists()).toBe(false)
    await wrapper.get('[role="dialog"] footer .secondary-button').trigger('click')

    // A save whose answer comes after the dialog was closed and another opened: the banner, not the new dialog.
    await wrapper.get('[data-testid="new-demo-request"]').trigger('click')
    wrapper.findComponent(DemoRequestModal).vm.$emit('submit', {} as CreateDemoRequestInput)
    await flushPromises()
    await wrapper.get('[role="dialog"] footer .secondary-button').trigger('click')
    await wrapper.get('[data-testid="new-demo-request"]').trigger('click')
    held.reject!(new CrmApiError('VALIDATION_ERROR', 'Demo Request form is incomplete.', 'req_late_refusal', false, { 'wafers.0.slotId': 'Required' }))
    await flushPromises()
    expect(wrapper.find('[data-modal-error]').exists()).toBe(false)
    expect(wrapper.find('[data-field-error="wafers.0.slotId"]').exists()).toBe(false)
    expect(wrapper.get('[data-api-error]').text()).toContain('req_late_refusal')
  })

  it('keeps the dialog\'s rows in their places while its own save is out, whatever the page\'s other actions do', async () => {
    // Two drafts: the dialog saves one while the other's submit, started after it, is refused first.
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      for (const id of ['DR-101', 'DR-102']) snapshot.demoRequests.find((item) => item.id === id)!.status = 'Draft'
    })
    const api = createMockApi({ repository, latency: 0 })
    vi.spyOn(api, 'transitionDemoRequest').mockRejectedValue(new CrmApiError('INTERNAL_ERROR', 'Demo Request could not be submitted.', 'req_submit_refused', true))
    type Saved = Awaited<ReturnType<CrmApi['updateDemoRequest']>>
    const held: { resolve: (value: Saved) => void } = { resolve: () => undefined }
    vi.spyOn(api, 'updateDemoRequest').mockImplementation(() => new Promise<Saved>((resolve) => { held.resolve = resolve }))
    const router = createAppRouter()
    await router.push('/demo-requests'); await router.isReady()
    const wrapper = mount(DemoRequestsPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()

    await wrapper.get('[data-demo-view="sales"]').trigger('click')
    await wrapper.get('[data-demo-action="DR-101-edit"]').trigger('click')
    expect(wrapper.get('[data-add-wafer]').attributes('disabled')).toBeUndefined()
    wrapper.findComponent(DemoRequestModal).vm.$emit('submit', {} as CreateDemoRequestInput)
    await flushPromises()
    expect(wrapper.get('[data-add-wafer]').attributes('disabled')).toBeDefined()

    // Another record's action, started after the dialog's save, ends first (refused): the rows stay in their places.
    await wrapper.get('[data-demo-request="DR-102"]').trigger('click')
    await wrapper.get('[data-demo-action="DR-102-submit"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-api-error]').text()).toContain('req_submit_refused')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    expect(wrapper.get('[data-add-wafer]').attributes('disabled')).toBeDefined()

    held.resolve({ data: { id: 'DR-101' } } as Saved)
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('keeps the dialog\'s draft when another action of the page succeeds meanwhile', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      for (const id of ['DR-101', 'DR-102']) snapshot.demoRequests.find((item) => item.id === id)!.status = 'Draft'
    })
    const api = createMockApi({ repository, latency: 0 })
    const listAccounts = vi.spyOn(api, 'listAccounts')
    vi.spyOn(api, 'transitionDemoRequest').mockResolvedValue({ data: {} } as Awaited<ReturnType<CrmApi['transitionDemoRequest']>>)
    const router = createAppRouter()
    await router.push('/demo-requests'); await router.isReady()
    const wrapper = mount(DemoRequestsPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()

    await wrapper.get('[data-demo-view="sales"]').trigger('click')
    await wrapper.get('[data-demo-action="DR-101-edit"]').trigger('click')
    await wrapper.get('[data-add-wafer]').trigger('click')
    await wrapper.get('[name="wafer-1-slotId"]').setValue('S-2')
    const rows = wrapper.findAll('[data-wafer-row]').length
    const readsBefore = listAccounts.mock.calls.length

    // The page's own action goes through and the page reads its references again: the form is not started over.
    await wrapper.get('[data-demo-request="DR-102"]').trigger('click')
    await wrapper.get('[data-demo-action="DR-102-submit"]').trigger('click')
    await flushPromises()
    expect(listAccounts.mock.calls.length).toBeGreaterThan(readsBefore)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-wafer-row]')).toHaveLength(rows)
    expect((wrapper.get('[name="wafer-1-slotId"]').element as HTMLInputElement).value).toBe('S-2')
  })

  it('leaves the dialog open now alone when the save of a dialog since closed succeeds late', async () => {
    const api = createMockApi({ role: 'Sales', latency: 0 })
    type Created = Awaited<ReturnType<CrmApi['createDemoRequest']>>
    const saves: Array<{ resolve: (value: Created) => void; reject: (reason: unknown) => void }> = []
    vi.spyOn(api, 'createDemoRequest').mockImplementation(() => new Promise<Created>((resolve, reject) => { saves.push({ resolve, reject }) }))
    const router = createAppRouter()
    await router.push('/demo-requests'); await router.isReady()
    const wrapper = mount(DemoRequestsPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()

    // A saved and closed while its answer is out; B opened and saved.
    await wrapper.get('[data-testid="new-demo-request"]').trigger('click')
    wrapper.findComponent(DemoRequestModal).vm.$emit('submit', {} as CreateDemoRequestInput)
    await flushPromises()
    await wrapper.get('[role="dialog"] footer .secondary-button').trigger('click')
    await wrapper.get('[data-testid="new-demo-request"]').trigger('click')
    wrapper.findComponent(DemoRequestModal).vm.$emit('submit', {} as CreateDemoRequestInput)
    await flushPromises()
    expect(saves).toHaveLength(2)

    // A's success: the list is read anew, B stays open and saving; B's refusal then lands in B.
    saves[0]!.resolve({ data: { id: 'DR-NEW' } } as Created)
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    expect(wrapper.get('[data-modal-submit]').attributes('disabled')).toBeDefined()
    saves[1]!.reject(new CrmApiError('VALIDATION_ERROR', 'Demo Request form is incomplete.', 'req_b_refused', false, { 'wafers.0.slotId': 'Required' }))
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    expect(wrapper.get('[data-modal-error]').text()).toContain('req_b_refused')
    expect(wrapper.find('[data-api-error]').exists()).toBe(false)
  })
})
