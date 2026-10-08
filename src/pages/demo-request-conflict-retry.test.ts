import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { expect, it, vi } from 'vitest'
import { CrmApiError, type CrmApi } from '@/api'
import { createMockApi } from '@/api/mock-adapter'
import { createDemoRepository, createMemoryDemoStorage, seedDemoSnapshot } from '@/demo/demo-repository'
import { createAppRouter } from '@/app/router'
import ModalShell from '@/design-system/ModalShell.vue'
import DemoRequestModal from '@/features/demo-requests/DemoRequestModal.vue'
import { getDemoRequestFormData } from '@/domain/demo-request-form'
import type { DemoRequestCommand, DemoRequestDto } from '@/types/crm'
import DemoRequestsPage from './DemoRequestsPage.vue'

const FIRST = '2026-10-01 09:00:00.000000'
const LATER = '2026-10-07 09:00:00.000000'
const conflict = () => new CrmApiError('VERSION_CONFLICT', 'Record changed; reload before saving.', 'req_conflict', false)

// DR-101 as the page lists it: at FIRST when the dialog opens; at LATER, with another person's text (and the state
// they moved it to), once someone else has saved it; gone once it has left the in-progress ones; or the list cannot
// be read at all.
// `holding` keeps every list read out until the test lets it go, in the order it was asked (`release`).
interface ListState { later: boolean; gone: boolean; fail: boolean; denied: boolean; holding: boolean; release: Array<() => void>; text?: string; modified?: string; status?: DemoRequestDto['status'] }
function listDr101(api: CrmApi, state: ListState) {
  const listNow = api.listDemoRequests.bind(api)
  vi.spyOn(api, 'listDemoRequests').mockImplementation(async (query) => {
    if (state.holding) await new Promise<void>((resolve) => { state.release.push(resolve) })
    if (state.fail) throw new CrmApiError('INTERNAL_ERROR', 'The list could not be read.', 'req_read', true)
    if (state.denied) throw new CrmApiError('PERMISSION_DENIED', '', 'req_denied', false)
    const result = await listNow(query)
    result.data.items = result.data.items.flatMap((item): DemoRequestDto[] => item.id !== 'DR-101'
      ? [item]
      : state.gone ? [] : [{
        ...item,
        modified: state.later ? state.modified ?? LATER : FIRST,
        status: state.status ?? item.status,
        formData: state.later ? { ...getDemoRequestFormData(item), specificRequest: state.text ?? 'Changed by someone else' } : item.formData,
      }])
    return result
  })
}

async function mountPage(role: 'Sales' | 'Engineer', status: DemoRequestDto['status']) {
  const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
  await repository.transact((snapshot) => {
    snapshot.demoRequests.find((item) => item.id === 'DR-101')!.status = status
  })
  const api = createMockApi({ repository, role, latency: 0 })
  const state: ListState = { later: false, gone: false, fail: false, denied: false, holding: false, release: [] }
  listDr101(api, state)
  const router = createAppRouter()
  await router.push('/demo-requests'); await router.isReady()
  const wrapper = mount(DemoRequestsPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
  await flushPromises()
  return { api, state, wrapper }
}

it('keeps the draft after a version conflict, refuses a plain retry, and saves once the latest version is loaded', async () => {
  const { api, state, wrapper } = await mountPage('Sales', 'Draft')
  const sent: Array<[string | undefined, string]> = []
  const submitted: boolean[] = []
  vi.spyOn(api, 'updateDemoRequest').mockImplementation(async (id, input, expectedModified) => {
    sent.push([expectedModified, input.formData.specificRequest])
    submitted.push(Boolean(input.submit))
    if (expectedModified !== LATER) throw conflict()
    return { data: { id } } as Awaited<ReturnType<CrmApi['updateDemoRequest']>>
  })
  await wrapper.get('[data-demo-view="sales"]').trigger('click')
  await wrapper.get('[data-demo-action="DR-101-edit"]').trigger('click')
  const original = (wrapper.get('textarea[name="specificRequest"]').element as HTMLTextAreaElement).value
  const waferRows = wrapper.findAll('[data-wafer-row]').length
  await wrapper.get('[data-add-wafer]').trigger('click')
  expect(wrapper.findAll('[data-wafer-row]')).toHaveLength(waferRows + 1)
  // The user's choice for this save: no resubmission.
  await wrapper.get('.submit-choice input').setValue(false)

  // Someone else saves meanwhile; the dialog's save, through its own form, names the version it opened with.
  state.later = true
  wrapper.getComponent(ModalShell).vm.$emit('submit')
  await flushPromises()
  expect(sent).toEqual([[FIRST, original]])
  expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
  expect(wrapper.find('[data-reload-demo-request]').exists()).toBe(true)
  expect(wrapper.find('.modal-feedback [data-reload-demo-request]').exists()).toBe(true)
  expect(wrapper.find('.modal-body [data-modal-error]').exists()).toBe(false)
  expect(wrapper.get('[data-modal-error]').text()).toContain('再载入最新版本后重新保存')
  expect(wrapper.get('[data-modal-error]').text()).toContain('req_conflict')
  expect(wrapper.findAll('[data-wafer-row]')).toHaveLength(waferRows + 1)
  expect(wrapper.find('[data-api-error]').exists()).toBe(false)

  // A save without the latest version is refused again: nothing of the other person's is overwritten unseen.
  wrapper.getComponent(ModalShell).vm.$emit('submit')
  await flushPromises()
  expect(sent).toEqual([[FIRST, original], [FIRST, original]])
  expect(wrapper.find('[role="dialog"]').exists()).toBe(true)

  // The latest version, asked for: the dialog shows what the other person saved, the draft is gone, and what the
  // user chose to do with the save (no resubmission) is kept.
  await wrapper.get('[data-reload-demo-request]').trigger('click')
  await flushPromises()
  expect(wrapper.find('[data-modal-error]').exists()).toBe(false)
  expect((wrapper.get('textarea[name="specificRequest"]').element as HTMLTextAreaElement).value).toBe('Changed by someone else')
  expect(wrapper.findAll('[data-wafer-row]')).toHaveLength(waferRows)
  expect((wrapper.get('.submit-choice input').element as HTMLInputElement).checked).toBe(false)
  wrapper.getComponent(ModalShell).vm.$emit('submit')
  await flushPromises()
  expect(sent[2]).toEqual([LATER, 'Changed by someone else'])
  expect(submitted).toEqual([false, false, false])
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
})

it('closes the dialog and says so when the latest version is asked for and the request has left the list', async () => {
  const { api, state, wrapper } = await mountPage('Sales', 'Draft')
  vi.spyOn(api, 'updateDemoRequest').mockRejectedValue(conflict())
  await wrapper.get('[data-demo-view="sales"]').trigger('click')
  await wrapper.get('[data-demo-action="DR-101-edit"]').trigger('click')
  state.gone = true
  wrapper.getComponent(ModalShell).vm.$emit('submit')
  await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
  await wrapper.get('[data-reload-demo-request]').trigger('click')
  await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  expect(wrapper.get('[data-api-error]').text()).toContain('不在这个列表里')
  expect(wrapper.find('[data-demo-request="DR-101"]').exists()).toBe(false)
})

it('tells the dialog when the latest version cannot be read, and keeps its draft and the way out', async () => {
  const { api, state, wrapper } = await mountPage('Sales', 'Draft')
  vi.spyOn(api, 'updateDemoRequest').mockRejectedValue(conflict())
  await wrapper.get('[data-demo-view="sales"]').trigger('click')
  await wrapper.get('[data-demo-action="DR-101-edit"]').trigger('click')
  const waferRows = wrapper.findAll('[data-wafer-row]').length
  await wrapper.get('[data-add-wafer]').trigger('click')
  state.later = true
  wrapper.getComponent(ModalShell).vm.$emit('submit')
  await flushPromises()
  expect(wrapper.get('[data-modal-error]').text()).toContain('req_conflict')

  // The read fails: the dialog says so, with the draft and the button still there; the page's error state is behind it.
  state.fail = true
  await wrapper.get('[data-reload-demo-request]').trigger('click')
  await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
  expect(wrapper.get('[data-modal-error]').text()).toContain('req_read')
  expect(wrapper.find('[data-reload-demo-request]').exists()).toBe(true)
  expect(wrapper.findAll('[data-wafer-row]')).toHaveLength(waferRows + 1)

  // Tried again once the list can be read: the latest version is loaded.
  state.fail = false
  await wrapper.get('[data-reload-demo-request]').trigger('click')
  await flushPromises()
  expect(wrapper.find('[data-modal-error]').exists()).toBe(false)
  expect((wrapper.get('textarea[name="specificRequest"]').element as HTMLTextAreaElement).value).toBe('Changed by someone else')
})

it('holds the dialog while the latest version is being read, and closes it when the read is refused for the user', async () => {
  const { api, state, wrapper } = await mountPage('Sales', 'Draft')
  vi.spyOn(api, 'updateDemoRequest').mockRejectedValue(conflict())
  await wrapper.get('[data-demo-view="sales"]').trigger('click')
  await wrapper.get('[data-demo-action="DR-101-edit"]').trigger('click')
  state.later = true
  wrapper.getComponent(ModalShell).vm.$emit('submit')
  await flushPromises()

  const held = () => ({
    submit: wrapper.get('[data-modal-submit]').attributes('disabled') !== undefined,
    reload: wrapper.get('[data-reload-demo-request]').attributes('disabled') !== undefined,
    fields: wrapper.get('fieldset.dialog-fields').attributes('disabled') !== undefined,
    field: wrapper.get('textarea[name="specificRequest"]').element.matches(':disabled'),
  })
  // The read is out: nothing in the dialog can be saved, reloaded, imported or typed meanwhile (every field waits in
  // the disabled fieldset: anything typed now would be lost when the form starts over).
  state.holding = true
  await wrapper.get('[data-reload-demo-request]').trigger('click')
  await flushPromises()
  expect(held()).toEqual({ submit: true, reload: true, fields: true, field: true })
  expect(wrapper.get('[data-add-wafer]').attributes('disabled')).toBeDefined()
  expect(state.release).toHaveLength(1)

  // The read is answered in the open dialog: the form starts over on the latest version, and everything is free again.
  state.release.shift()!()
  await flushPromises()
  expect(wrapper.find('[data-modal-error]').exists()).toBe(false)
  expect(wrapper.get('fieldset.dialog-fields').attributes('disabled')).toBeUndefined()
  expect(wrapper.get('[data-modal-submit]').attributes('disabled')).toBeUndefined()
  expect((wrapper.get('textarea[name="specificRequest"]').element as HTMLTextAreaElement).value).toBe('Changed by someone else')

  // Closed while a read is out, then opened again: the new dialog starts free, and the abandoned read, answered
  // while the new dialog has its own read out, ends with its own session and frees nothing of the new one.
  wrapper.getComponent(ModalShell).vm.$emit('submit')
  await flushPromises()
  state.release.shift()!()  // the list read that follows the conflict
  await flushPromises()
  await wrapper.get('[data-reload-demo-request]').trigger('click')
  await flushPromises()
  expect(state.release).toHaveLength(1)
  await wrapper.get('[role="dialog"] footer .secondary-button').trigger('click')
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  await wrapper.get('[data-demo-action="DR-101-edit"]').trigger('click')
  expect(wrapper.get('fieldset.dialog-fields').attributes('disabled')).toBeUndefined()
  expect(wrapper.get('[data-modal-submit]').attributes('disabled')).toBeUndefined()
  wrapper.getComponent(ModalShell).vm.$emit('submit')
  await flushPromises()
  state.release.splice(1, 1)[0]!()  // the new dialog's list read after its conflict
  await flushPromises()
  await wrapper.get('[data-reload-demo-request]').trigger('click')
  await flushPromises()
  expect(held()).toEqual({ submit: true, reload: true, fields: true, field: true })
  expect(state.release).toHaveLength(2)
  state.release.shift()!()  // the abandoned dialog's read, answered late
  await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
  expect(held()).toEqual({ submit: true, reload: true, fields: true, field: true })
  // A third version, saved by someone else meanwhile.
  state.text = 'Changed again'; state.modified = '2026-10-07 10:00:00.000000'
  state.release.shift()!()  // the new dialog's own read
  await flushPromises()
  expect(wrapper.find('[data-modal-error]').exists()).toBe(false)
  expect(wrapper.get('fieldset.dialog-fields').attributes('disabled')).toBeUndefined()
  expect(wrapper.get('[data-modal-submit]').attributes('disabled')).toBeUndefined()
  expect((wrapper.get('textarea[name="specificRequest"]').element as HTMLTextAreaElement).value).toBe('Changed again')
  state.holding = false

  // Refused for the user on a later read: the page shows it, the dialog has nothing to show.
  wrapper.getComponent(ModalShell).vm.$emit('submit')
  await flushPromises()
  state.denied = true
  await wrapper.get('[data-reload-demo-request]').trigger('click')
  await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  expect(wrapper.find('[data-demo-request="DR-101"]').exists()).toBe(false)
})

it('lets an abandoned read arrive without touching the dialog opened since', async () => {
  const { api, state, wrapper } = await mountPage('Sales', 'Draft')
  vi.spyOn(api, 'updateDemoRequest').mockRejectedValue(conflict())
  await wrapper.get('[data-demo-view="sales"]').trigger('click')
  await wrapper.get('[data-demo-action="DR-101-edit"]').trigger('click')
  state.later = true
  wrapper.getComponent(ModalShell).vm.$emit('submit')
  await flushPromises()
  state.holding = true
  await wrapper.get('[data-reload-demo-request]').trigger('click')
  await flushPromises()
  await wrapper.get('[role="dialog"] footer .secondary-button').trigger('click')
  await wrapper.get('[data-demo-action="DR-101-edit"]').trigger('click')
  const waferRows = wrapper.findAll('[data-wafer-row]').length
  await wrapper.get('[data-add-wafer]').trigger('click')

  // The read the closed dialog asked for is answered while the new one has nothing out: it refreshes the list and
  // leaves the dialog, its draft and its fields alone.
  state.release.shift()!()
  await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
  expect(wrapper.findAll('[data-wafer-row]')).toHaveLength(waferRows + 1)
  expect(wrapper.get('fieldset.dialog-fields').attributes('disabled')).toBeUndefined()
  expect(wrapper.get('[data-modal-submit]').attributes('disabled')).toBeUndefined()
  expect(wrapper.find('[data-modal-error]').exists()).toBe(false)
})

it('keeps the way to the latest version when a retry is refused for another reason', async () => {
  const { api, state, wrapper } = await mountPage('Sales', 'Draft')
  let saves = 0
  vi.spyOn(api, 'updateDemoRequest').mockImplementation(async () => {
    saves += 1
    throw saves === 1 ? conflict() : new CrmApiError('VALIDATION_ERROR', 'Demo Request form is incomplete.', 'req_incomplete', false, { 'wafers.0.slotId': 'Required' })
  })
  await wrapper.get('[data-demo-view="sales"]').trigger('click')
  await wrapper.get('[data-demo-action="DR-101-edit"]').trigger('click')
  state.later = true
  wrapper.getComponent(ModalShell).vm.$emit('submit')
  await flushPromises()
  expect(wrapper.find('[data-reload-demo-request]').exists()).toBe(true)

  // The retry is refused for its content: the refusal is shown, and the version is still the one refused before.
  wrapper.getComponent(ModalShell).vm.$emit('submit')
  await flushPromises()
  expect(wrapper.get('[data-modal-error]').text()).toContain('req_incomplete')
  expect(wrapper.find('[data-reload-demo-request]').exists()).toBe(true)
  await wrapper.get('[data-reload-demo-request]').trigger('click')
  await flushPromises()
  expect(wrapper.find('[data-modal-error]').exists()).toBe(false)
  expect((wrapper.get('textarea[name="specificRequest"]').element as HTMLTextAreaElement).value).toBe('Changed by someone else')
})

it('waits for a form import in flight before the latest version can be loaded', async () => {
  const { api, state, wrapper } = await mountPage('Sales', 'Draft')
  vi.spyOn(api, 'updateDemoRequest').mockRejectedValue(conflict())
  let finish = (value: Awaited<ReturnType<CrmApi['importDemoRequestForm']>>) => { void value }
  vi.spyOn(api, 'importDemoRequestForm').mockImplementation(() => new Promise((resolve) => { finish = resolve }))
  await wrapper.get('[data-demo-view="sales"]').trigger('click')
  await wrapper.get('[data-demo-action="DR-101-edit"]').trigger('click')
  state.later = true
  wrapper.getComponent(ModalShell).vm.$emit('submit')
  await flushPromises()
  expect(wrapper.get('[data-reload-demo-request]').attributes('disabled')).toBeUndefined()

  // A DRF being recognised: the latest version cannot be loaded under it.
  const input = wrapper.get('[data-demo-request-import] input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: [new File(['%PDF-1.4'], 'drf.pdf', { type: 'application/pdf' })] })
  await input.trigger('change')
  await flushPromises()
  expect(wrapper.get('[data-reload-demo-request]').attributes('disabled')).toBeDefined()
  finish({ data: { fileName: 'drf.pdf', companyName: '', formData: getDemoRequestFormData(null), detectedFields: [] }, meta: { requestId: 'req_import' }, warnings: [] } as unknown as Awaited<ReturnType<CrmApi['importDemoRequestForm']>>)
  await flushPromises()
  expect(wrapper.get('[data-reload-demo-request]').attributes('disabled')).toBeUndefined()
})

it('shows no reload button for a conflict answered to the new-request dialog', async () => {
  const { api, wrapper } = await mountPage('Sales', 'Draft')
  vi.spyOn(api, 'createDemoRequest').mockRejectedValue(conflict())
  await wrapper.get('[data-testid="new-demo-request"]').trigger('click')
  wrapper.findComponent(DemoRequestModal).vm.$emit('submit', {} as DemoRequestCommand)
  await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
  expect(wrapper.get('[data-modal-error]').text()).toContain('req_conflict')
  expect(wrapper.find('[data-reload-demo-request]').exists()).toBe(false)
})

it('closes a review dialog whose request has moved on to another step, and says so', async () => {
  const { api, state, wrapper } = await mountPage('Engineer', 'Engineer Review')
  vi.spyOn(api, 'transitionDemoRequest').mockRejectedValue(conflict())
  await wrapper.get('[data-demo-request="DR-101"]').trigger('click')
  await wrapper.get('[data-demo-action="DR-101-review"]').trigger('click')
  // Another Engineer approved it meanwhile: it is still in progress, but no longer awaiting this review.
  state.later = true; state.status = 'Manager Approval'
  wrapper.findComponent(DemoRequestModal).vm.$emit('submit', {} as DemoRequestCommand)
  await flushPromises()
  await wrapper.get('[data-reload-demo-request]').trigger('click')
  await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  expect(wrapper.get('[data-api-error]').text()).toContain('已不在这一步')
})

it('treats the Engineer review dialog the same way: a conflict keeps it open, the latest version is loaded on request', async () => {
  const { api, state, wrapper } = await mountPage('Engineer', 'Engineer Review')
  const versions: Array<string | undefined> = []
  vi.spyOn(api, 'transitionDemoRequest').mockImplementation(async (id, _command, expectedModified) => {
    versions.push(expectedModified)
    if (expectedModified !== LATER) throw conflict()
    return { data: { request: { id } } } as Awaited<ReturnType<CrmApi['transitionDemoRequest']>>
  })
  await wrapper.get('[data-demo-request="DR-101"]').trigger('click')
  await wrapper.get('[data-demo-action="DR-101-review"]').trigger('click')
  state.later = true
  wrapper.findComponent(DemoRequestModal).vm.$emit('submit', {} as DemoRequestCommand)
  await flushPromises()
  expect(versions).toEqual([FIRST])
  expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
  await wrapper.get('[data-reload-demo-request]').trigger('click')
  await flushPromises()
  expect(wrapper.find('[data-modal-error]').exists()).toBe(false)
  wrapper.findComponent(DemoRequestModal).vm.$emit('submit', {} as DemoRequestCommand)
  await flushPromises()
  expect(versions).toEqual([FIRST, LATER])
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
})
