import { createPinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { CrmApiError, type CrmApi } from '@/api'
import { createMockApi } from '@/api/mock-adapter'
import { createDemoRepository, createMemoryDemoStorage, seedDemoSnapshot } from '@/demo/demo-repository'
import { createMemorySalesRepository } from '@/demo/sales-repository'
import { setLocale } from '@/i18n'
import { useAppStore } from '@/stores/app'
import type { EvaluationDto, EvaluationStatus, UserRole } from '@/types/crm'
import EvaluationsPage from './EvaluationsPage.vue'

const mounted: VueWrapper[] = []
afterEach(() => { mounted.splice(0).forEach(wrapper => wrapper.unmount()); vi.restoreAllMocks() })

async function context(options: { role?: UserRole; prepare?: (evaluation: EvaluationDto) => void; omitFocusedFromList?: boolean; unfocused?: boolean } = {}) {
  const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
  if (options.prepare) await repository.transact(snapshot => options.prepare!(snapshot.evaluations.find(row => row.id === 'EVAL-103')!))
  const api = createMockApi({ repository, salesRepository: createMemorySalesRepository(), latency: 0, role: options.role ?? 'Manager', today: '2026-07-17', ...(options.role === 'Sales' ? { userName: 'Demo Staff 02' } : {}) })
  if (options.omitFocusedFromList) {
    const list = api.listEvaluations.bind(api)
    vi.spyOn(api, 'listEvaluations').mockImplementation(async query => {
      const response = await list(query)
      return { ...response, data: { ...response.data, items: response.data.items.filter(row => row.id !== 'EVAL-103') } }
    })
    vi.spyOn(api, 'getEvaluation')
  }
  const pinia = createPinia()
  const app = useAppStore(pinia)
  app.bootstrap = (await api.getBootstrap()).data
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/evaluations', component: EvaluationsPage }, { path: '/demo/:demoId', name: 'demo-detail', component: { template: '<div />' } }] })
  await router.push(options.unfocused ? '/evaluations' : '/evaluations?focus=EVAL-103')
  await router.isReady()
  const wrapper = mount(EvaluationsPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
  mounted.push(wrapper)
  await flushPromises()
  return { wrapper, api, app, repository, current: async () => (await api.getEvaluation('EVAL-103')).data }
}

async function open(wrapper: VueWrapper, action: 'reschedule' | 'complete' | 'cancel') {
  await wrapper.get(`[data-test-run="CUSTOMER04-R02"] [data-run-action="${action}"]`).trigger('click')
}

async function submit(wrapper: VueWrapper) {
  await wrapper.get('.modal-card form').trigger('submit')
  await flushPromises()
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

type PageContext = Awaited<ReturnType<typeof context>>

async function preparedEvaluation(
  current: PageContext['current'],
  change: (evaluation: EvaluationDto) => void,
  modified = '2026-07-17T12:00:01.000000Z',
) {
  const evaluation = structuredClone(await current())
  change(evaluation)
  evaluation.modified = modified
  return evaluation
}

async function persistPreparedEvaluation(context: PageContext, evaluation: EvaluationDto) {
  await context.repository.transact(snapshot => {
    const index = snapshot.evaluations.findIndex(row => row.id === evaluation.id)
    snapshot.evaluations[index] = structuredClone(evaluation)
  })
  return { data: structuredClone(evaluation), warnings: [] }
}

function stubRunUpdate(context: PageContext, evaluation: EvaluationDto) {
  return vi.spyOn(context.api, 'updateEvaluationRun').mockImplementation(
    async () => persistPreparedEvaluation(context, evaluation),
  )
}

function stubRunCancellation(context: PageContext, evaluation: EvaluationDto) {
  return vi.spyOn(context.api, 'cancelEvaluationRun').mockImplementation(
    async () => persistPreparedEvaluation(context, evaluation),
  )
}

describe('Evaluation page planned test-run actions', () => {
  it('reschedules the existing run, keeps it Planned and refreshes the page without adding a record', async () => {
    const page = await context()
    const { wrapper, api, current } = page
    const original = await current()
    expect(original.modified).toEqual(expect.any(String))
    const returned = await preparedEvaluation(current, evaluation => {
      Object.assign(evaluation.runs.find(run => run.id === 'CUSTOMER04-R02')!, { date: '2026-08-05' })
    })
    const update = stubRunUpdate(page, returned)
    const add = vi.spyOn(api, 'addEvaluationRun')
    await open(wrapper, 'reschedule')
    await wrapper.get('[data-run-date]').setValue('2026-08-05')
    await submit(wrapper)

    expect(update).toHaveBeenCalledWith('EVAL-103', 'CUSTOMER04-R02', expect.objectContaining({ date: '2026-08-05', expectedModified: original.modified, capture: null, falsePositive: null, wph: null }))
    expect(add).not.toHaveBeenCalled()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    const changed = await current()
    expect(changed.runs).toHaveLength(original.runs.length)
    expect(changed.modified).not.toBe(original.modified)
    expect(changed.runs.find(run => run.id === 'CUSTOMER04-R02')).toMatchObject({ status: 'Planned', date: '2026-08-05', lot: 'JC-CHIPLET-072', wafers: 5 })
    expect(wrapper.get('[data-test-run="CUSTOMER04-R02"]').text()).toContain('2026-08-05')
  })

  it('requires all result fields and a nonblank summary, while accepting zero results', async () => {
    const page = await context()
    const { wrapper, current } = page
    const returned = await preparedEvaluation(current, evaluation => {
      Object.assign(evaluation.runs.find(run => run.id === 'CUSTOMER04-R02')!, {
        status: 'Completed', capture: 0, falsePositive: 0, wph: 0, summary: 'Zero is a measured result',
      })
    })
    const update = stubRunUpdate(page, returned)
    await open(wrapper, 'complete')
    await submit(wrapper)
    expect(update).not.toHaveBeenCalled()
    expect(wrapper.get('[role="dialog"]').text()).toContain('请填写三项结果和摘要')
    await wrapper.get('[data-run-capture]').setValue('0')
    await wrapper.get('[data-run-false-positive]').setValue('0')
    await wrapper.get('[data-run-summary]').setValue('Zero is a measured result')
    await submit(wrapper)
    expect(update).not.toHaveBeenCalled()
    await wrapper.get('[data-run-wph]').setValue('0')
    await wrapper.get('[data-run-summary]').setValue('  ')
    await submit(wrapper)
    expect(update).not.toHaveBeenCalled()
    await wrapper.get('[data-run-summary]').setValue('  Zero is a measured result  ')
    await submit(wrapper)

    expect(update).toHaveBeenCalledOnce()
    expect((await current()).runs.find(run => run.id === 'CUSTOMER04-R02')).toMatchObject({ status: 'Completed', capture: 0, falsePositive: 0, wph: 0, summary: 'Zero is a measured result' })
    expect(wrapper.get('[data-test-run="CUSTOMER04-R02"]').text()).toContain('已完成')
    expect(wrapper.find('[data-test-run="CUSTOMER04-R02"] [data-run-action]').exists()).toBe(false)
  })

  it('does not treat persisted Frappe zero defaults as explicitly entered completion results', async () => {
    const page = await context({ prepare: evaluation => {
      Object.assign(evaluation.runs.find(run => run.id === 'CUSTOMER04-R02')!, {
        capture: 0, falsePositive: 0, wph: 0, summary: 'Scheduled qualification test',
      })
    } })
    const { wrapper, current } = page
    const returned = await preparedEvaluation(current, evaluation => {
      Object.assign(evaluation.runs.find(run => run.id === 'CUSTOMER04-R02')!, {
        status: 'Completed', capture: 0, falsePositive: 0, wph: 0, summary: 'Measured zero results',
      })
    })
    const update = stubRunUpdate(page, returned)
    await open(wrapper, 'complete')
    for (const metric of ['capture', 'false-positive', 'wph']) {
      expect((wrapper.get(`[data-run-${metric}]`).element as HTMLInputElement).value).toBe('')
    }
    await submit(wrapper)
    expect(update).not.toHaveBeenCalled()
    expect((await current()).runs.find(run => run.id === 'CUSTOMER04-R02')?.status).toBe('Planned')
    for (const metric of ['capture', 'false-positive', 'wph']) await wrapper.get(`[data-run-${metric}]`).setValue('0')
    await wrapper.get('[data-run-summary]').setValue('Measured zero results')
    await submit(wrapper)
    expect(update).toHaveBeenCalledOnce()
    expect((await current()).runs.find(run => run.id === 'CUSTOMER04-R02')).toMatchObject({ status: 'Completed', capture: 0, falsePositive: 0, wph: 0 })
  })

  it.each([['capture', '101'], ['false-positive', '-1'], ['wph', '-1']])('rejects out-of-range %s before sending a completion', async (field, value) => {
    const { wrapper, api } = await context()
    const update = vi.spyOn(api, 'updateEvaluationRun')
    await open(wrapper, 'complete')
    for (const metric of ['capture', 'false-positive', 'wph']) await wrapper.get(`[data-run-${metric}]`).setValue('1')
    await wrapper.get('[data-run-summary]').setValue('Measured')
    await wrapper.get(`[data-run-${field}]`).setValue(value)
    await submit(wrapper)
    expect(update).not.toHaveBeenCalled()
    expect(wrapper.get('[role="alert"]').text()).toContain('WPH')
  })

  it('requires a cancellation reason, retains the cancelled run and refreshes its audit and totals', async () => {
    const page = await context()
    const { wrapper, current } = page
    const returned = await preparedEvaluation(current, evaluation => {
      Object.assign(evaluation.runs.find(run => run.id === 'CUSTOMER04-R02')!, {
        status: 'Cancelled', summary: 'Customer cancelled wafer delivery',
      })
      evaluation.wafers = 5
      evaluation.history = [{
        id: 'EVH-CANCELLED-R02', actor: 'Demo Staff 01', at: '2026-07-17T12:00:01.000000Z',
        eventType: 'Test Run', from: 'Planned', to: 'Cancelled',
        summary: 'Cancelled Test Run CUSTOMER04-R02: Customer cancelled wafer delivery',
      }, ...(evaluation.history ?? [])]
    })
    const cancel = stubRunCancellation(page, returned)
    await open(wrapper, 'cancel')
    await wrapper.get('[data-run-reason]').setValue('  ')
    await submit(wrapper)
    expect(cancel).not.toHaveBeenCalled()
    expect(wrapper.get('[role="alert"]').text()).toContain('取消原因')
    await wrapper.get('[data-run-reason]').setValue('  Customer cancelled wafer delivery  ')
    await submit(wrapper)

    expect(cancel).toHaveBeenCalledWith('EVAL-103', 'CUSTOMER04-R02', expect.objectContaining({ reason: 'Customer cancelled wafer delivery', expectedModified: expect.any(String) }))
    const cancelled = await current()
    expect(cancelled.wafers).toBe(5)
    expect(cancelled.history?.[0]).toMatchObject({ eventType: 'Test Run', summary: expect.stringContaining('Customer cancelled wafer delivery') })
    expect(wrapper.get('[data-test-run="CUSTOMER04-R02"]').text()).toContain('已取消')
    expect(wrapper.get('[data-test-run="CUSTOMER04-R02"]').text()).toContain('Customer cancelled wafer delivery')
    expect(wrapper.find('[data-test-run="CUSTOMER04-R02"] [data-run-action]').exists()).toBe(false)
    expect(wrapper.get('.evaluation-history').text()).toContain('Customer cancelled wafer delivery')
  })

  it('opens the focused Scheduled evaluation in preparation and exposes its Planned run actions', async () => {
    const page = await context({ prepare: evaluation => { evaluation.status = 'Scheduled' } })
    const { wrapper } = page
    expect(wrapper.get('[data-evaluation-workspace]').attributes('data-evaluation-workspace')).toBe('preparation')
    expect(wrapper.get('[data-evaluation-actions]').text()).toContain('EVAL-103')
    const returned = await preparedEvaluation(page.current, evaluation => {
      evaluation.runs.find(run => run.id === 'CUSTOMER04-R02')!.date = '2026-08-07'
    })
    const update = stubRunUpdate(page, returned)
    await open(wrapper, 'reschedule')
    await wrapper.get('[data-run-date]').setValue('2026-08-07')
    await submit(wrapper)
    expect(update).toHaveBeenCalledOnce()
    expect(wrapper.get('[data-test-run="CUSTOMER04-R02"]').text()).toContain('2026-08-07')
  })

  it('loads and manages the focus target even when it is absent from the current list page', async () => {
    const page = await context({ omitFocusedFromList: true })
    const { wrapper, api } = page
    expect(api.getEvaluation).toHaveBeenCalledWith('EVAL-103')
    expect((await api.listEvaluations({ page: 1, pageSize: 6 })).data.items.some(row => row.id === 'EVAL-103')).toBe(false)
    expect(wrapper.get('[data-evaluation-actions]').text()).toContain('EVAL-103')
    const returned = await preparedEvaluation(page.current, evaluation => {
      evaluation.runs.find(run => run.id === 'CUSTOMER04-R02')!.date = '2026-08-15'
    })
    const update = stubRunUpdate(page, returned)
    await open(wrapper, 'reschedule')
    await wrapper.get('[data-run-date]').setValue('2026-08-15')
    await submit(wrapper)
    expect(update).toHaveBeenCalledWith('EVAL-103', 'CUSTOMER04-R02', expect.objectContaining({ date: '2026-08-15' }))
    expect(wrapper.get('[data-test-run="CUSTOMER04-R02"]').text()).toContain('2026-08-15')
  })

  it.each(['Analysis', 'Internal Review', 'Customer Review'] as EvaluationStatus[])('shows run history without mutation actions in %s', async status => {
    const { wrapper } = await context({ prepare: evaluation => { evaluation.status = status } })
    expect(wrapper.find('[data-test-run="CUSTOMER04-R02"]').exists()).toBe(true)
    expect(wrapper.find('[data-run-action]').exists()).toBe(false)
  })

  it('leaves previous-round, Completed and Cancelled runs visible without mutation controls', async () => {
    const { wrapper } = await context({ prepare: evaluation => {
      evaluation.testRound = 2
      evaluation.runs.push({ ...evaluation.runs[1]!, id: 'CUSTOMER04-R03', round: 2, status: 'Cancelled', summary: 'Previous cancellation' })
    } })
    expect(wrapper.findAll('[data-test-run]')).toHaveLength(3)
    expect(wrapper.get('[data-test-run="CUSTOMER04-R01"]').text()).toContain('已完成')
    expect(wrapper.get('[data-test-run="CUSTOMER04-R02"]').text()).toContain('第 1 轮')
    expect(wrapper.get('[data-test-run="CUSTOMER04-R03"]').text()).toContain('已取消')
    expect(wrapper.find('[data-run-action]').exists()).toBe(false)
  })

  it('lets an in-scope Sales user read run history without write controls', async () => {
    const { wrapper } = await context({ role: 'Sales' })
    expect(wrapper.find('[data-test-run="CUSTOMER04-R02"]').exists()).toBe(true)
    expect(wrapper.find('[data-run-action]').exists()).toBe(false)
  })

  it('lets an in-scope Sales user close Customer Review with a comment and nothing more', async () => {
    const page = await context({
      role: 'Sales',
      prepare: evaluation => { evaluation.status = 'Customer Review'; evaluation.reportStatus = 'Ready' },
    })
    const { wrapper, api, current } = page
    expect(wrapper.find('[data-customer-report-action="EVAL-103"]').exists()).toBe(true)
    expect(wrapper.find('[data-retest-evaluation="EVAL-103"]').exists()).toBe(true)
    expect(wrapper.find('[data-add-run="EVAL-103"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="terminate-evaluation-EVAL-103"]').exists()).toBe(false)

    // The server decides whether Sales may close the review; the page only has to send the comment.
    const archived = await preparedEvaluation(current, evaluation => { evaluation.status = 'Accepted' })
    const spy = vi.spyOn(api, 'updateEvaluationStatus').mockImplementation(async () => persistPreparedEvaluation(page, archived))
    await wrapper.get('[data-advance-status="Accepted"]').trigger('click')
    await wrapper.get('[data-customer-comment-body]').setValue('客户确认检出率达标')
    await wrapper.get('[data-submit-customer-comment]').trigger('click')
    await flushPromises()
    expect(spy).toHaveBeenCalledWith('EVAL-103', { status: 'Accepted', customerComment: '客户确认检出率达标' }, expect.any(String))
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect((await current()).status).toBe('Accepted')
  })

  it.each(['PERMISSION_DENIED', 'SCOPE_DENIED'])('clears the dialog and all visible records on %s', async code => {
    const { wrapper, api } = await context()
    vi.spyOn(api, 'cancelEvaluationRun').mockRejectedValue(new CrmApiError(code, 'Access revoked', 'req-run-denied'))
    await open(wrapper, 'cancel')
    await wrapper.get('[data-run-reason]').setValue('No longer needed')
    await submit(wrapper)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.find('[data-test-runs]').exists()).toBe(false)
    expect(wrapper.find('[data-evaluation-table]').exists()).toBe(false)
    expect(wrapper.text()).toContain('req-run-denied')
  })

  it('preserves the draft after a network write failure and lets the user retry successfully', async () => {
    const page = await context()
    const { wrapper, current } = page
    const returned = await preparedEvaluation(current, evaluation => {
      evaluation.runs.find(run => run.id === 'CUSTOMER04-R02')!.date = '2026-08-16'
    })
    const update = stubRunUpdate(page, returned)
      .mockRejectedValueOnce(new CrmApiError('NETWORK_ERROR', 'Connection interrupted', 'req-write-network'))
    await open(wrapper, 'reschedule')
    await wrapper.get('[data-run-date]').setValue('2026-08-16')
    await submit(wrapper)
    expect(wrapper.get<HTMLInputElement>('[data-run-date]').element.value).toBe('2026-08-16')
    expect(wrapper.get('[role="dialog"]').text()).toContain('req-write-network')
    expect(wrapper.get('[data-modal-submit]').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[data-run-reload]').exists()).toBe(false)
    await submit(wrapper)
    expect(update).toHaveBeenCalledTimes(2)
    expect(update.mock.calls[1]).toEqual(update.mock.calls[0])
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect((await current()).runs.find(row => row.id === 'CUSTOMER04-R02')!.date).toBe('2026-08-16')
  })

  it('keeps a conflicting draft until explicit reload and then saves using the refreshed version', async () => {
    const page = await context()
    const { wrapper, current } = page
    const latest = await preparedEvaluation(current, evaluation => {
      evaluation.runs.find(run => run.id === 'CUSTOMER04-R02')!.date = '2026-08-09'
    }, '2026-07-17T12:00:02.000000Z')
    const saved = structuredClone(latest)
    saved.runs.find(run => run.id === 'CUSTOMER04-R02')!.date = '2026-08-12'
    saved.modified = '2026-07-17T12:00:03.000000Z'
    const update = stubRunUpdate(page, saved)
      .mockRejectedValueOnce(new CrmApiError('VERSION_CONFLICT', 'Changed elsewhere', 'req-conflict'))
    await open(wrapper, 'reschedule')
    await wrapper.get('[data-run-date]').setValue('2026-08-05')
    // A separate client response is now the latest server fixture while this dialog stays stale.
    await persistPreparedEvaluation(page, latest)
    const latestVersion = latest.modified
    await submit(wrapper)
    expect(wrapper.get<HTMLInputElement>('[data-run-date]').element.value).toBe('2026-08-05')
    expect(wrapper.get('[data-modal-submit]').attributes('disabled')).toBeDefined()
    await submit(wrapper)
    expect(update).toHaveBeenCalledTimes(1)
    await wrapper.get('[data-run-reload]').trigger('click')
    await flushPromises()
    expect(wrapper.get<HTMLInputElement>('[data-run-date]').element.value).toBe('2026-08-09')
    expect(wrapper.get('[data-modal-submit]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[data-run-date]').setValue('2026-08-12')
    await submit(wrapper)
    expect(update).toHaveBeenLastCalledWith('EVAL-103', 'CUSTOMER04-R02', expect.objectContaining({ date: '2026-08-12', expectedModified: latestVersion }))
    expect((await current()).runs.find(run => run.id === 'CUSTOMER04-R02')!.date).toBe('2026-08-12')
  })

  it('preserves the draft and prevents stale resubmission when conflict reload fails', async () => {
    const { wrapper, api } = await context()
    const update = vi.spyOn(api, 'updateEvaluationRun').mockRejectedValue(new CrmApiError('VERSION_CONFLICT', 'Changed elsewhere', 'req-conflict'))
    await open(wrapper, 'reschedule')
    await wrapper.get('[data-run-date]').setValue('2026-08-06')
    await submit(wrapper)
    vi.spyOn(api, 'getEvaluation').mockRejectedValueOnce(new CrmApiError('NETWORK_ERROR', 'Connection failed', 'req-reload'))
    await wrapper.get('[data-run-reload]').trigger('click')
    await flushPromises()
    expect(wrapper.get<HTMLInputElement>('[data-run-date]').element.value).toBe('2026-08-06')
    expect(wrapper.get('[role="dialog"]').text()).toContain('req-reload')
    expect(wrapper.get('[data-modal-submit]').attributes('disabled')).toBeDefined()
    await submit(wrapper)
    expect(update).toHaveBeenCalledTimes(1)
  })

  it('closes a conflict dialog when reloading reveals that another user cancelled the run', async () => {
    const { wrapper, api, repository } = await context()
    vi.spyOn(api, 'updateEvaluationRun').mockRejectedValue(new CrmApiError('VERSION_CONFLICT', 'Changed elsewhere', 'req-conflict'))
    await open(wrapper, 'reschedule')
    await submit(wrapper)
    await repository.transact(snapshot => { snapshot.evaluations.find(row => row.id === 'EVAL-103')!.runs.find(run => run.id === 'CUSTOMER04-R02')!.status = 'Cancelled' })
    await wrapper.get('[data-run-reload]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('[data-test-run="CUSTOMER04-R02"]').text()).toContain('已取消')
    expect(wrapper.get('[data-api-error]').text()).toContain('不能修改')
  })

  it('prevents duplicate requests and closing by either button or backdrop while saving', async () => {
    const { wrapper, api, current } = await context()
    const result = { data: await current(), warnings: [] }
    const pending = deferred<Awaited<ReturnType<CrmApi['updateEvaluationRun']>>>()
    const update = vi.spyOn(api, 'updateEvaluationRun').mockReturnValue(pending.promise)
    await open(wrapper, 'reschedule')
    await submit(wrapper)
    expect(wrapper.get('[data-modal-submit]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    await submit(wrapper)
    await wrapper.get('.modal-card header button').trigger('click')
    await wrapper.get('.modal-card footer .secondary-button').trigger('click')
    await wrapper.get('.modal-host').trigger('mousedown')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    expect(update).toHaveBeenCalledTimes(1)
    pending.resolve(result)
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it.each(['success', 'denied'] as const)('ignores a stale %s response after the active identity changes', async outcome => {
    const { wrapper, api, app, current } = await context()
    const staleData = structuredClone(await current())
    staleData.runs.find(run => run.id === 'CUSTOMER04-R02')!.date = '2099-12-31'
    const pending = deferred<Awaited<ReturnType<CrmApi['updateEvaluationRun']>>>()
    const update = vi.spyOn(api, 'updateEvaluationRun').mockReturnValue(pending.promise)
    const list = vi.spyOn(api, 'listEvaluations')
    await open(wrapper, 'reschedule')
    await submit(wrapper)
    expect(update).toHaveBeenCalledOnce()
    app.identityRevision++
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    if (outcome === 'success') pending.resolve({ data: staleData, warnings: [] })
    else pending.reject(new CrmApiError('PERMISSION_DENIED', 'Old user denied', 'req-old-user'))
    await flushPromises()
    expect(wrapper.text()).not.toContain('2099-12-31')
    expect(wrapper.text()).not.toContain('req-old-user')
    expect(list).not.toHaveBeenCalled()
  })

  it('updates the action labels, modal and local validation when switching between English and Chinese', async () => {
    const { wrapper } = await context()
    setLocale('en-US')
    await flushPromises()
    expect(wrapper.get('[data-run-action="cancel"]').text()).toBe('Cancel run')
    await open(wrapper, 'cancel')
    await submit(wrapper)
    expect(wrapper.get('[role="dialog"]').attributes('aria-label')).toBe('Cancel test run')
    expect(wrapper.get('[role="alert"]').text()).toContain('Enter a cancellation reason')
    setLocale('zh-CN')
    await flushPromises()
    expect(wrapper.get('[role="dialog"]').attributes('aria-label')).toBe('取消测试')
    expect(wrapper.get('[role="alert"]').text()).toContain('请填写取消原因')
  })
})

// The mock adapter only stubs terminateEvaluation; each test supplies the server's answer.
describe('Terminate Demo Test', () => {
  const inProgress = (wrapper: VueWrapper) => Number(/\d+/.exec(wrapper.get('.header-chip').text())![0])

  async function terminatedCopy(page: PageContext) {
    return preparedEvaluation(page.current, (evaluation) => {
      evaluation.status = 'Rejected'
      evaluation.terminationReason = 'Customer paused the project'
    })
  }

  it('opens a reason dialog on Terminate and calls terminateEvaluation with the reason and loaded version', async () => {
    const page = await context({ prepare: (evaluation) => { evaluation.status = 'Testing' } })
    const { wrapper, api, current } = page
    const original = await current()
    const before = inProgress(wrapper)
    const returned = await terminatedCopy(page)
    const spy = vi.spyOn(api, 'terminateEvaluation').mockImplementation(async () => persistPreparedEvaluation(page, returned))
    const list = vi.spyOn(api, 'listEvaluations')

    await wrapper.get('[data-testid="terminate-evaluation-EVAL-103"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').attributes('aria-label')).toBe('终止 Demo')
    await submit(wrapper)
    expect(spy).not.toHaveBeenCalled()
    expect(wrapper.get('[role="dialog"] [role="alert"]').text()).toBe('请填写终止原因')
    await wrapper.get('[aria-label="终止原因"]').setValue('  Customer paused the project  ')
    await submit(wrapper)

    expect(spy).toHaveBeenCalledOnce()
    expect(spy).toHaveBeenCalledWith('EVAL-103', 'Customer paused the project', original.modified)
    expect(list).toHaveBeenCalled()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    const evaluation = await current()
    expect(evaluation.status).toBe('Rejected')
    expect(evaluation.terminationReason).toBe('Customer paused the project')
    // The terminated Demo leaves the in-progress workspace and count after the reload.
    expect(wrapper.find('[data-evaluation="EVAL-103"]').exists()).toBe(false)
    expect(inProgress(wrapper)).toBe(before - 1)
  })

  it('keeps the dialog and the reason after a refused write and lets the user retry', async () => {
    const page = await context()
    const { wrapper, api } = page
    const returned = await terminatedCopy(page)
    const spy = vi.spyOn(api, 'terminateEvaluation')
      .mockRejectedValueOnce(new CrmApiError('NETWORK_ERROR', 'Connection interrupted', 'req-terminate-network'))
      .mockImplementation(async () => persistPreparedEvaluation(page, returned))

    await wrapper.get('[data-testid="terminate-evaluation-EVAL-103"]').trigger('click')
    await wrapper.get('[aria-label="终止原因"]').setValue('Customer paused the project')
    await submit(wrapper)

    // The dialog carries the refusal; the page banner does not repeat it behind the dialog.
    expect(wrapper.get('[role="dialog"]').text()).toContain('req-terminate-network')
    expect(wrapper.find('[data-api-error]').exists()).toBe(false)
    expect(wrapper.findAll('[role="alert"]').filter((alert) => alert.text().includes('req-terminate-network'))).toHaveLength(1)
    expect(wrapper.get<HTMLTextAreaElement>('[aria-label="终止原因"]').element.value).toBe('Customer paused the project')
    expect(wrapper.get('[data-modal-submit]').attributes('disabled')).toBeUndefined()
    await submit(wrapper)
    expect(spy).toHaveBeenCalledTimes(2)
    expect(spy.mock.calls[1]).toEqual(spy.mock.calls[0])
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.find('[data-api-error]').exists()).toBe(false)
  })

  it('reloads after a version conflict and resubmits the same reason with the latest version', async () => {
    const page = await context({ prepare: (evaluation) => { evaluation.status = 'Testing' } })
    const { wrapper, api, current } = page
    const original = await current()
    // Another user changes the Demo Test while this dialog is open.
    const latest = await preparedEvaluation(current, (evaluation) => { evaluation.testRunDeadline = '2026-08-20' }, '2026-07-17T12:00:02.000000Z')
    const returned = structuredClone(latest)
    returned.status = 'Rejected'
    returned.terminationReason = 'Customer paused the project'
    returned.modified = '2026-07-17T12:00:03.000000Z'
    const spy = vi.spyOn(api, 'terminateEvaluation')
      .mockRejectedValueOnce(new CrmApiError('VERSION_CONFLICT', 'Changed elsewhere', 'req-terminate-conflict'))
      .mockImplementation(async () => persistPreparedEvaluation(page, returned))
    const list = vi.spyOn(api, 'listEvaluations')

    await wrapper.get('[data-testid="terminate-evaluation-EVAL-103"]').trigger('click')
    await wrapper.get('[aria-label="终止原因"]').setValue('Customer paused the project')
    await persistPreparedEvaluation(page, latest)
    await submit(wrapper)

    expect(spy).toHaveBeenCalledOnce()
    expect(spy).toHaveBeenLastCalledWith('EVAL-103', 'Customer paused the project', original.modified)
    expect(original.modified).not.toBe(latest.modified)
    expect(list).toHaveBeenCalled()
    expect(wrapper.get('[role="dialog"]').text()).toContain('req-terminate-conflict')
    expect(wrapper.get<HTMLTextAreaElement>('[aria-label="终止原因"]').element.value).toBe('Customer paused the project')
    expect(wrapper.get('[data-modal-submit]').attributes('disabled')).toBeUndefined()

    await submit(wrapper)
    expect(spy).toHaveBeenCalledTimes(2)
    expect(spy).toHaveBeenLastCalledWith('EVAL-103', 'Customer paused the project', latest.modified)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.find('[data-api-error]').exists()).toBe(false)
    expect((await current()).terminationReason).toBe('Customer paused the project')
    expect(wrapper.find('[data-evaluation="EVAL-103"]').exists()).toBe(false)
  })

  it('closes the dialog when the reload shows the Demo Test was already ended elsewhere', async () => {
    const page = await context()
    const { wrapper, api } = page
    const endedElsewhere = await terminatedCopy(page)
    const spy = vi.spyOn(api, 'terminateEvaluation')
      .mockRejectedValue(new CrmApiError('INVALID_TRANSITION', 'Evaluation is already Rejected.', 'req-terminate-ended'))

    await wrapper.get('[data-testid="terminate-evaluation-EVAL-103"]').trigger('click')
    await wrapper.get('[aria-label="终止原因"]').setValue('Customer paused the project')
    await persistPreparedEvaluation(page, endedElsewhere)
    await submit(wrapper)

    expect(spy).toHaveBeenCalledOnce()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('[data-api-error]').text()).toContain('该 Demo Test 已不在进行中')
    expect(wrapper.find('[data-evaluation="EVAL-103"]').exists()).toBe(false)
  })

  it('keeps the dialog on a conflict when the changed Demo Test has moved off the loaded list page', async () => {
    const page = await context({ unfocused: true, prepare: (evaluation) => { evaluation.status = 'Testing' } })
    const { wrapper, api, current } = page
    const original = await current()
    // Another user's change moves the Demo Test to the top of the list, off this page.
    const latest = await preparedEvaluation(current, (evaluation) => { evaluation.testRunDeadline = '2026-08-20' }, '2026-07-17T12:00:02.000000Z')
    const returned = structuredClone(latest)
    returned.status = 'Rejected'
    returned.terminationReason = 'Customer paused the project'
    returned.modified = '2026-07-17T12:00:03.000000Z'
    const spy = vi.spyOn(api, 'terminateEvaluation')
      .mockRejectedValueOnce(new CrmApiError('VERSION_CONFLICT', 'Changed elsewhere', 'req-terminate-conflict'))
      .mockImplementation(async () => persistPreparedEvaluation(page, returned))
    const list = api.listEvaluations.bind(api)
    let movedOffPage = false
    vi.spyOn(api, 'listEvaluations').mockImplementation(async (query) => {
      const response = await list(query)
      if (!movedOffPage) return response
      return { ...response, data: { ...response.data, items: response.data.items.filter((row) => row.id !== 'EVAL-103') } }
    })
    const read = vi.spyOn(api, 'getEvaluation')

    await wrapper.get('[data-evaluation="EVAL-103"]').trigger('click')
    await wrapper.get('[data-testid="terminate-evaluation-EVAL-103"]').trigger('click')
    await wrapper.get('[aria-label="终止原因"]').setValue('Customer paused the project')
    await persistPreparedEvaluation(page, latest)
    movedOffPage = true
    await submit(wrapper)

    expect(spy).toHaveBeenLastCalledWith('EVAL-103', 'Customer paused the project', original.modified)
    expect(read).toHaveBeenCalledWith('EVAL-103')
    expect(wrapper.find('[data-evaluation="EVAL-103"]').exists()).toBe(false)
    expect(wrapper.get('[role="dialog"]').text()).toContain('req-terminate-conflict')
    expect(wrapper.text()).not.toContain('该 Demo Test 已不在进行中')
    expect(wrapper.get<HTMLTextAreaElement>('[aria-label="终止原因"]').element.value).toBe('Customer paused the project')

    await submit(wrapper)
    expect(spy).toHaveBeenCalledTimes(2)
    expect(spy).toHaveBeenLastCalledWith('EVAL-103', 'Customer paused the project', latest.modified)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.find('[data-api-error]').exists()).toBe(false)
    expect((await current()).terminationReason).toBe('Customer paused the project')
  })

  it('closes the dialog with the read error when the conflict reload cannot read the Demo Test', async () => {
    const { wrapper, api } = await context({ unfocused: true })
    vi.spyOn(api, 'terminateEvaluation')
      .mockRejectedValue(new CrmApiError('VERSION_CONFLICT', 'Changed elsewhere', 'req-terminate-conflict'))
    vi.spyOn(api, 'getEvaluation')
      .mockRejectedValueOnce(new CrmApiError('NETWORK_ERROR', 'Connection failed', 'req-terminate-reload'))

    await wrapper.get('[data-evaluation="EVAL-103"]').trigger('click')
    await wrapper.get('[data-testid="terminate-evaluation-EVAL-103"]').trigger('click')
    await wrapper.get('[aria-label="终止原因"]').setValue('Customer paused the project')
    await submit(wrapper)

    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('[data-api-error]').text()).toContain('req-terminate-reload')
  })

  it('stays open while its request runs, so the answer cannot reach another dialog', async () => {
    const page = await context()
    const { wrapper, api } = page
    const returned = await terminatedCopy(page)
    const pending = deferred<Awaited<ReturnType<CrmApi['terminateEvaluation']>>>()
    const spy = vi.spyOn(api, 'terminateEvaluation').mockReturnValue(pending.promise)

    await wrapper.get('[data-testid="terminate-evaluation-EVAL-103"]').trigger('click')
    await wrapper.get('[aria-label="终止原因"]').setValue('Customer paused the project')
    await submit(wrapper)
    expect(wrapper.get('[data-modal-submit]').attributes('disabled')).toBeDefined()
    await wrapper.get('.modal-card header button').trigger('click')
    await wrapper.get('.modal-card footer .secondary-button').trigger('click')
    await wrapper.get('.modal-host').trigger('mousedown')
    expect(wrapper.get('[role="dialog"]').text()).toContain('EVAL-103')
    expect(spy).toHaveBeenCalledOnce()

    pending.resolve(await persistPreparedEvaluation(page, returned))
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('leaves no refusal on the page once the dialog is dismissed', async () => {
    const { wrapper, api } = await context()
    vi.spyOn(api, 'terminateEvaluation')
      .mockRejectedValue(new CrmApiError('NETWORK_ERROR', 'Connection interrupted', 'req-terminate-network'))

    await wrapper.get('[data-testid="terminate-evaluation-EVAL-103"]').trigger('click')
    await wrapper.get('[aria-label="终止原因"]').setValue('Customer paused the project')
    await submit(wrapper)
    expect(wrapper.get('[role="dialog"]').text()).toContain('req-terminate-network')
    expect(wrapper.find('[data-api-error]').exists()).toBe(false)

    // Dismissing leaves no refusal behind for the page to show once the dialog is gone,
    // and a dialog opened again does not bring the old one back.
    await wrapper.get('.modal-card footer .secondary-button').trigger('click')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.find('[data-api-error]').exists()).toBe(false)
    await wrapper.get('[data-testid="terminate-evaluation-EVAL-103"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).not.toContain('req-terminate-network')
  })

  it('keeps the refusal of another write out of the open dialog and shows it on the page', async () => {
    const page = await context({ prepare: (evaluation) => {
      evaluation.status = 'Scope Confirmed'
      evaluation.waferPreparationStatus = 'Pending'
      evaluation.testPreparationStatus = 'Pending'
    } })
    const { wrapper, api } = page
    vi.spyOn(api, 'completeEvaluationPreparation')
      .mockRejectedValue(new CrmApiError('NETWORK_ERROR', 'Connection interrupted', 'req-prepare-failed'))

    await wrapper.get('[data-testid="terminate-evaluation-EVAL-103"]').trigger('click')
    // A write started behind the open dialog fails: the dialog is about the termination, not about that write.
    await wrapper.get('[data-complete-preparation="test"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="dialog"]').text()).not.toContain('req-prepare-failed')
    expect(wrapper.get('[data-api-error]').text()).toContain('req-prepare-failed')
  })

  it('keeps the page banner of another write when the dialog is closed', async () => {
    const page = await context({ prepare: (evaluation) => {
      evaluation.status = 'Scope Confirmed'
      evaluation.waferPreparationStatus = 'Pending'
      evaluation.testPreparationStatus = 'Pending'
    } })
    const { wrapper, api } = page
    vi.spyOn(api, 'completeEvaluationPreparation')
      .mockRejectedValue(new CrmApiError('NETWORK_ERROR', 'Connection interrupted', 'req-prepare-failed'))

    await wrapper.get('[data-testid="terminate-evaluation-EVAL-103"]').trigger('click')
    await wrapper.get('[data-complete-preparation="test"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-api-error]').text()).toContain('req-prepare-failed')
    // Closing the dialog only drops the dialog's own state, not that failure.
    await wrapper.get('.modal-card footer .secondary-button').trigger('click')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('[data-api-error]').text()).toContain('req-prepare-failed')
  })

  it('tells the user the termination did not go through when the list cannot be reloaded after a conflict', async () => {
    const page = await context({ unfocused: true, prepare: (evaluation) => { evaluation.status = 'Testing' } })
    const { wrapper, api } = page
    vi.spyOn(api, 'terminateEvaluation')
      .mockRejectedValue(new CrmApiError('VERSION_CONFLICT', 'Changed elsewhere', 'req-terminate-conflict'))
    vi.spyOn(api, 'listEvaluations')
      .mockRejectedValueOnce(new CrmApiError('NETWORK_ERROR', 'List failed', 'req-list-failed'))

    await wrapper.get('[data-evaluation="EVAL-103"]').trigger('click')
    await wrapper.get('[data-testid="terminate-evaluation-EVAL-103"]').trigger('click')
    await wrapper.get('[aria-label="终止原因"]').setValue('Customer paused the project')
    await submit(wrapper)

    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('[data-api-error]').text()).toContain('req-terminate-conflict')
  })

  it.each(['PERMISSION_DENIED', 'SCOPE_DENIED'])('clears the dialog and all visible records on %s', async (code) => {
    const { wrapper, api } = await context()
    vi.spyOn(api, 'terminateEvaluation').mockRejectedValue(new CrmApiError(code, 'Access revoked', 'req-terminate-denied'))
    await wrapper.get('[data-testid="terminate-evaluation-EVAL-103"]').trigger('click')
    await wrapper.get('[aria-label="终止原因"]').setValue('Customer paused the project')
    await submit(wrapper)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.find('[data-evaluation-table]').exists()).toBe(false)
    expect(wrapper.text()).toContain('req-terminate-denied')
  })

  it('does not offer termination to Sales, who cannot write Demo Tests', async () => {
    const { wrapper } = await context({ role: 'Sales' })
    expect(wrapper.find('[data-evaluation="EVAL-103"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid^="terminate-evaluation-"]').exists()).toBe(false)
  })
})
