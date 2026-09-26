import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createAppRouter } from '@/app/router'
import { CrmApiError } from '@/api'
import { createMockApi } from '@/api/mock-adapter'
import { createDemoRepository, createMemoryDemoStorage, seedDemoSnapshot } from '@/demo/demo-repository'
import { createMemorySalesRepository } from '@/demo/sales-repository'
import { getDemoRequestFormData } from '@/domain/demo-request-form'
import DemoRequestsPage from './DemoRequestsPage.vue'
import EvaluationsPage from './EvaluationsPage.vue'
import ContractsPage from './ContractsPage.vue'
import DemoDetailPage from './DemoDetailPage.vue'

const docxMocks = vi.hoisted(() => ({ generateDemoRequestDocxArtifact: vi.fn() }))
const downloadMocks = vi.hoisted(() => ({ downloadBlob: vi.fn() }))
vi.mock('@/features/demo-requests/demo-request-docx', () => docxMocks)
vi.mock('@/features/shared/download-blob', () => downloadMocks)

beforeEach(() => {
  docxMocks.generateDemoRequestDocxArtifact.mockReset()
  docxMocks.generateDemoRequestDocxArtifact.mockResolvedValue({
    fileName: 'Demo_Request_DR-101.docx',
    blob: new Blob(['docx'], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }),
  })
  downloadMocks.downloadBlob.mockReset()
})

async function globals(path: string) {
  const router = createAppRouter()
  await router.push(path)
  await router.isReady()
  return { plugins: [createPinia(), router] }
}

describe('delivery workflow pages', () => {
  it('prefills a new Demo Request with the current Sales user id', async () => {
    const api = createMockApi({ latency: 0, role: 'Sales', userId: 'person002@crm.example.invalid', userName: 'Demo Staff 01' })
    const wrapper = mount(DemoRequestsPage, {
      props: { apiClient: api },
      global: await globals('/demo-requests'),
    })
    await flushPromises()

    const createButton = wrapper.findAll('button').find((button) => button.text().includes('新建 Demo Request'))!
    await createButton.trigger('click')

    expect((wrapper.get('select[name="salesContact"]').element as HTMLSelectElement).value).toBe('person002@crm.example.invalid')
  })

  it('does not render a standalone contact-link list below Demo Request', async () => {
    const wrapper = mount(DemoRequestsPage, {
      props: { apiClient: createMockApi({ latency: 0 }) },
      global: await globals('/demo-requests'),
    })
    await flushPromises()

    expect(wrapper.findAll('a[href^="/contacts/"]')).toHaveLength(0)
  })

  it('keeps Demo Request separate from the arrow-linked processing views', async () => {
    const wrapper = mount(DemoRequestsPage, {
      props: { apiClient: createMockApi({ latency: 0 }) },
      global: await globals('/demo-requests'),
    })
    await flushPromises()

    expect(wrapper.findAll('[data-demo-view]')).toHaveLength(4)
    expect(wrapper.findAll('[data-demo-flow-arrow]')).toHaveLength(2)
    expect(wrapper.get('[data-demo-view="overview"]').attributes('aria-current')).toBe('page')

    await wrapper.get('[data-demo-view="engineer"]').trigger('click')

    expect(wrapper.get('[data-demo-view="engineer"]').attributes('aria-current')).toBe('page')
    expect(wrapper.find('[data-demo-workspace="engineer"]').exists()).toBe(true)
  })

  it('shows Sales DRF engineering inputs on the unified Demo detail page', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      const request = snapshot.demoRequests.find((item) => item.id === 'DR-101')!
      request.formData = {
        ...getDemoRequestFormData(request),
        detectMeasure: 'TSV void detection and overlay measurement',
        expectedResults: 'Capture at least 95% of known defects',
        keySuccessFactors: 'Stable recipe and repeatable coordinates',
        internalQuestions: 'Can the current probe fixture support this wafer?',
      }
    })
    const router = createAppRouter()
    await router.push({ name: 'demo-detail', params: { demoId: 'DR-101' }, query: { from: 'demo-requests' } })
    await router.isReady()
    const wrapper = mount(DemoDetailPage, {
      props: { apiClient: createMockApi({ repository, latency: 0, role: 'Engineer', userName: '演示员工14' }) },
      global: { plugins: [createPinia(), router] },
    })
    await flushPromises()

    const detail = wrapper.get('[data-demo-detail-information]')
    expect(detail.text()).toContain('TSV void detection and overlay measurement')
    expect(detail.text()).toContain('Capture at least 95% of known defects')
    expect(detail.text()).toContain('Stable recipe and repeatable coordinates')
    expect(detail.text()).toContain('Can the current probe fixture support this wafer?')
  })

  it('moves Demo Requests through submission and Boss approval', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    const salesRepository = createMemorySalesRepository()
    const templateOpportunity = salesRepository.snapshot.opportunities[0]!
    salesRepository.snapshot.opportunities.push({
      ...structuredClone(templateOpportunity),
      id: 'OPP-004', accountId: 'ACC-003', siteId: salesRepository.snapshot.sites['ACC-003']![0]!.id,
      account: '示例企业003有限公司', site: salesRepository.snapshot.sites['ACC-003']![0]!.name,
      title: '关键尺寸量测替换', stage: 'Wafer Demo确认', probability: 47,
      stakeholders: [], actions: [], history: [],
    })
    await repository.transact((snapshot) => {
      const request = snapshot.demoRequests.find((item) => item.id === 'DR-101')!
      request.status = 'Draft'
      request.history = []
    })
    const sales = createMockApi({ repository, salesRepository, latency: 0, role: 'Sales', userName: 'Demo Staff 01' })
    let wrapper = mount(DemoRequestsPage, { props: { apiClient: sales }, global: await globals('/demo-requests') })
    await flushPromises()

    await wrapper.get('[data-demo-view="sales"]').trigger('click')
    await wrapper.get('[data-demo-action="DR-101-submit"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-demo-view="overview"]').trigger('click')
    expect(wrapper.get('[data-demo-request="DR-101"]').text()).toContain('待工程评估')

    wrapper.unmount()
    const boss = createMockApi({ repository, salesRepository, latency: 0, role: 'Manager', userName: 'Demo Staff 03' })
    wrapper = mount(DemoRequestsPage, { props: { apiClient: boss }, global: await globals('/demo-requests') })
    await flushPromises()
    await wrapper.get('[data-demo-view="manager"]').trigger('click')
    await wrapper.get('[data-demo-action="DR-103-review"]').trigger('click')
    await wrapper.get('[aria-label="Boss 审批意见"]').setValue('批准进入 Demo')
    await wrapper.get('.modal-card form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[data-demo-request="DR-103"]').exists()).toBe(false)
    expect(wrapper.get('[data-demo-test-handoff]').text()).toContain('DR-103')
    expect(wrapper.get('[data-demo-test-handoff]').text()).toContain('EVAL-107')
    expect(wrapper.get('[data-demo-test-handoff] a').attributes('href')).toBe('/evaluations?focus=EVAL-107')

    wrapper.unmount()
    wrapper = mount(EvaluationsPage, { props: { apiClient: boss }, global: await globals('/evaluations?focus=EVAL-107') })
    await flushPromises()
    expect(wrapper.find('[data-evaluation="EVAL-107"]').exists()).toBe(true)
    expect(wrapper.get('[data-evaluation="EVAL-107"]').classes()).toContain('selected')
    expect(wrapper.get('[data-demo-test-focus]').text()).toContain('来源 Demo Request DR-103')
  })

  it('sends the current Demo Request version for a Sales transition', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      const request = snapshot.demoRequests.find((item) => item.id === 'DR-101')!
      request.status = 'Draft'
      request.modified = '2026-08-06T03:30:00.000000Z'
    })
    const api = createMockApi({ repository, latency: 0, role: 'Sales' })
    const transition = vi.spyOn(api, 'transitionDemoRequest')
    const wrapper = mount(DemoRequestsPage, { props: { apiClient: api }, global: await globals('/demo-requests') })
    await flushPromises()

    await wrapper.get('[data-demo-view="sales"]').trigger('click')
    await wrapper.get('[data-demo-action="DR-101-submit"]').trigger('click')
    await flushPromises()

    expect(transition).toHaveBeenCalledWith('DR-101', { type: 'submit' }, '2026-08-06T03:30:00.000000Z')
  })

  it('reloads concurrent Demo Request changes without replacing the loaded page', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      snapshot.demoRequests.find((item) => item.id === 'DR-101')!.status = 'Draft'
    })
    const base = createMockApi({ repository, latency: 0, role: 'Sales' })
    const apiClient = {
      ...base,
      transitionDemoRequest: vi.fn().mockRejectedValue(
        new CrmApiError('VERSION_CONFLICT', '记录已被其他用户更新，请重新确认。', 'req_demo_conflict'),
      ),
    }
    const wrapper = mount(DemoRequestsPage, { props: { apiClient }, global: await globals('/demo-requests') })
    await flushPromises()

    await wrapper.get('[data-demo-view="sales"]').trigger('click')
    await wrapper.get('[data-demo-action="DR-101-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-demo-request="DR-101"]').exists()).toBe(true)
    expect(wrapper.find('.state-error').exists()).toBe(false)
    expect(wrapper.get('[data-api-error]').text()).toContain('记录已被其他用户更新')
    expect(wrapper.get('[data-api-error]').text()).toContain('req_demo_conflict')
  })

  it('records a wafer Test Run and exposes its measured result', async () => {
    const api = createMockApi({ latency: 0 })
    const wrapper = mount(EvaluationsPage, { props: { apiClient: api }, global: await globals('/evaluations') })
    await flushPromises()

    expect(wrapper.findAll('[data-evaluation-view]')).toHaveLength(6)
    await wrapper.get('[data-evaluation-view="execution"]').trigger('click')
    await wrapper.get('[data-add-run="EVAL-103"]').trigger('click')
    await wrapper.get('[aria-label="晶圆批次"]').setValue('LOT-NEW')
    await wrapper.get('[aria-label="Wafer 数量"]').setValue('4')
    await wrapper.get('[aria-label="缺陷捕获率"]').setValue('97')
    await wrapper.get('[aria-label="误报率"]').setValue('2.1')
    await wrapper.get('[aria-label="吞吐量 WPH"]').setValue('35')
    await wrapper.get('[aria-label="结果摘要"]').setValue('指标达到验收标准')
    await wrapper.get('.modal-card form').trigger('submit')
    await flushPromises()

    expect((await api.listEvaluations({})).data.items.find((item) => item.id === 'EVAL-103')?.runs.at(-1)).toMatchObject({
      lot: 'LOT-NEW',
      capture: 97,
      falsePositive: 2.1,
      wph: 35,
      summary: '指标达到验收标准',
    })
  })

  it('keeps Customer Review active but moves Accepted and Rejected tests out of Demo Test', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    const wrapper = mount(EvaluationsPage, {
      props: { apiClient: createMockApi({ repository, latency: 0 }) },
      global: await globals('/evaluations'),
    })
    await flushPromises()

    expect(wrapper.text()).not.toContain('On Hold')
    expect(wrapper.find('[data-evaluation="EVAL-105"]').exists()).toBe(false)
    expect(wrapper.find('[data-evaluation="EVAL-106"]').exists()).toBe(false)
    expect(wrapper.find('[data-evaluation="EVAL-104"]').exists()).toBe(true)
  })

  it('sends the current Evaluation version when advancing Demo Test status', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      const evaluation = snapshot.evaluations.find((item) => item.id === 'EVAL-103')!
      evaluation.modified = '2026-08-06 10:00:00.000000'
      evaluation.reportArtifactId = 'ART-READY'
      evaluation.internalReportArtifactId = 'ART-INTERNAL'
      evaluation.externalReportArtifactId = 'ART-EXTERNAL'
    })
    const api = createMockApi({ repository, latency: 0, role: 'Manager' })
    const updateStatus = vi.spyOn(api, 'updateEvaluationStatus')
    const wrapper = mount(EvaluationsPage, { props: { apiClient: api }, global: await globals('/evaluations') })
    await flushPromises()

    await wrapper.get('[data-evaluation-view="execution"]').trigger('click')
    await wrapper.get('[data-evaluation="EVAL-103"]').trigger('click')
    await wrapper.get('[data-advance-status="Internal Review"]').trigger('click')
    await flushPromises()

    expect(updateStatus).toHaveBeenCalledWith(
      'EVAL-103',
      { status: 'Internal Review' },
      '2026-08-06 10:00:00.000000',
    )
  })

  it('requires a customer comment before archiving or retesting a Demo Test', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      const evaluation = snapshot.evaluations.find((item) => item.id === 'EVAL-103')!
      evaluation.status = 'Customer Review'
      evaluation.reportStatus = 'Ready'
      evaluation.modified = '2026-08-25T10:00:00.000000Z'
    })
    const api = createMockApi({ repository, latency: 0, role: 'Manager' })
    const updateStatus = vi.spyOn(api, 'updateEvaluationStatus')
    const wrapper = mount(EvaluationsPage, { props: { apiClient: api }, global: await globals('/evaluations') })
    await flushPromises()

    await wrapper.get('[data-evaluation="EVAL-103"]').trigger('click')
    // Rejection is gone: Customer Review only records a comment.
    expect(wrapper.find('[data-reject-evaluation]').exists()).toBe(false)

    await wrapper.get('[data-advance-status="Accepted"]').trigger('click')
    expect(updateStatus).not.toHaveBeenCalled()
    expect(wrapper.get('[aria-label="记录 Customer Comment"]').attributes('aria-modal')).toBe('true')
    expect(wrapper.get('[data-submit-customer-comment]').attributes('disabled')).toBeDefined()

    await wrapper.get('[data-customer-comment-body]').setValue('客户认为误报率仍偏高，要求再测一轮')
    await wrapper.get('[data-outcome-retest]').setValue()
    await wrapper.get('[data-submit-customer-comment]').trigger('click')
    await flushPromises()

    expect(updateStatus).toHaveBeenCalledWith(
      'EVAL-103',
      { status: 'Testing', customerComment: '客户认为误报率仍偏高，要求再测一轮' },
      '2026-08-25T10:00:00.000000Z',
    )
  })

  it('uploads a Customer Report from the Customer Review panel', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      const evaluation = snapshot.evaluations.find((item) => item.id === 'EVAL-103')!
      evaluation.status = 'Customer Review'
      evaluation.reportStatus = 'Ready'
    })
    const api = createMockApi({ repository, latency: 0, role: 'Manager' })
    const wrapper = mount(EvaluationsPage, { props: { apiClient: api }, global: await globals('/evaluations') })
    await flushPromises()

    await wrapper.get('[data-evaluation="EVAL-103"]').trigger('click')
    await wrapper.get('[data-customer-report-action="EVAL-103"]').trigger('click')
    expect(wrapper.get('[aria-label="上传 Customer 报告"]').attributes('aria-modal')).toBe('true')

    const input = wrapper.get('[data-customer-report]')
    const file = new File(['customer feedback'], 'customer-feedback.pptx', {
      type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    })
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await wrapper.get('[data-upload-customer-report]').trigger('click')
    await flushPromises()

    const snapshot = await repository.read()
    expect(snapshot.artifacts.filter((item) => item.type === 'Customer Report')).toEqual([
      expect.objectContaining({ fileName: '[Customer] customer-feedback.pptx', round: 1, version: 1 }),
    ])
  })

  it('completes each preparation branch with the current Evaluation version', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      snapshot.evaluations.find((item) => item.id === 'EVAL-101')!.modified = '2026-08-06T04:00:00.000000Z'
    })
    const api = createMockApi({ repository, latency: 0, role: 'Manager' })
    const complete = vi.spyOn(api, 'completeEvaluationPreparation')
    const wrapper = mount(EvaluationsPage, { props: { apiClient: api }, global: await globals('/evaluations') })
    await flushPromises()

    await wrapper.get('[data-evaluation-view="preparation"]').trigger('click')
    await wrapper.get('[data-complete-preparation="test"]').trigger('click')
    await flushPromises()

    expect(complete).toHaveBeenCalledWith('EVAL-101', 'test', '2026-08-06T04:00:00.000000Z')
    expect(wrapper.get('[data-evaluation="EVAL-101"]').text()).toContain('测试准备 · 已完成')
  })

  it('keeps loaded Demo Test data visible when a non-permission status write fails', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      const evaluation = snapshot.evaluations.find((item) => item.id === 'EVAL-103')!
      evaluation.reportArtifactId = 'ART-READY'
      evaluation.internalReportArtifactId = 'ART-INTERNAL'
      evaluation.externalReportArtifactId = 'ART-EXTERNAL'
    })
    const apiClient = createMockApi({ repository, latency: 0, role: 'Manager' })
    vi.spyOn(apiClient, 'updateEvaluationStatus').mockRejectedValue(
      new CrmApiError('VALIDATION_ERROR', 'expectedModified is required.', 'req_eval_version'),
    )
    const wrapper = mount(EvaluationsPage, { props: { apiClient }, global: await globals('/evaluations') })
    await flushPromises()

    await wrapper.get('[data-evaluation-view="execution"]').trigger('click')
    await wrapper.get('[data-evaluation="EVAL-103"]').trigger('click')
    await wrapper.get('[data-advance-status="Internal Review"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-evaluation="EVAL-103"]').exists()).toBe(true)
    expect(wrapper.find('.state-error').exists()).toBe(false)
    expect(wrapper.get('[data-api-error]').text()).toContain('expectedModified is required.')
    expect(wrapper.get('[data-api-error]').text()).toContain('req_eval_version')
  })

  it('requires a summary for completed runs before submitting', async () => {
    const api = createMockApi({ latency: 0 })
    const addRun = vi.spyOn(api, 'addEvaluationRun')
    const wrapper = mount(EvaluationsPage, { props: { apiClient: api }, global: await globals('/evaluations') })
    await flushPromises()

    await wrapper.get('[data-evaluation-view="execution"]').trigger('click')
    await wrapper.get('[data-add-run="EVAL-103"]').trigger('click')
    await wrapper.get('[aria-label="晶圆批次"]').setValue('LOT-NO-SUMMARY')
    await wrapper.get('[aria-label="缺陷捕获率"]').setValue('97')
    await wrapper.get('[aria-label="误报率"]').setValue('2.1')
    await wrapper.get('[aria-label="吞吐量 WPH"]').setValue('35')
    await wrapper.get('.modal-card form').trigger('submit')

    expect(wrapper.get('[role="alert"]').text()).toContain('结果摘要')
    expect(addRun).not.toHaveBeenCalled()
  })

  it('uses three active groups without On Hold and saves a Preparation DDL warning', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    const api = createMockApi({ repository, latency: 0 })
    const setDeadline = vi.spyOn(api, 'setEvaluationTestRunDeadline')
    const wrapper = mount(EvaluationsPage, { props: { apiClient: api }, global: await globals('/evaluations') })
    await flushPromises()

    expect(wrapper.findAll('[data-evaluation-view]').map((item) => item.attributes('data-evaluation-view'))).toEqual([
      'overview', 'wafer', 'preparation', 'execution', 'internal', 'customer',
    ])
    expect(wrapper.text()).not.toContain('On Hold')
    await wrapper.get('[data-evaluation-view="preparation"]').trigger('click')
    await wrapper.get('[data-set-ddl="EVAL-101"]').trigger('click')
    await wrapper.get('[aria-label="Test Run DDL"]').setValue('2026-09-30')
    await wrapper.get('.modal-card form').trigger('submit')
    await flushPromises()

    expect(setDeadline).toHaveBeenCalledWith('EVAL-101', { testRunDeadline: '2026-09-30' })
    expect(wrapper.get('[data-api-warning]').text()).toContain('Test Run DDL 晚于客户预期时间')
    expect((await repository.read()).evaluations.find((item) => item.id === 'EVAL-101')?.testRunDeadline).toBe('2026-09-30')

    await wrapper.get('[aria-label="Evaluation 客户"]').setValue('ACC-006')
    await flushPromises()
    expect(wrapper.find('[data-api-warning]').exists()).toBe(false)
  })

  it('lets Sales correct returned requests and cancel editable drafts', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      snapshot.demoRequests.find((item) => item.id === 'DR-101')!.status = 'Engineer Returned'
      snapshot.demoRequests.find((item) => item.id === 'DR-102')!.status = 'Draft'
    })
    const wrapper = mount(DemoRequestsPage, { props: { apiClient: createMockApi({ repository, latency: 0 }) }, global: await globals('/demo-requests') })
    await flushPromises()

    await wrapper.get('[data-demo-view="sales"]').trigger('click')
    await wrapper.get('[data-demo-request="DR-101"]').trigger('click')
    await wrapper.get('[data-demo-action="DR-101-edit"]').trigger('click')
    await wrapper.get('[name="primaryTool"]').setValue('Macro Inspection X9')
    await wrapper.get('.modal-card form').trigger('submit')
    await flushPromises()
    const updated = (await repository.read()).demoRequests.find((item) => item.id === 'DR-101')!
    expect(getDemoRequestFormData(updated).primaryTool).toBe('Macro Inspection X9')
    expect(updated.status).toBe('Engineer Review')

    await wrapper.get('[data-demo-view="sales"]').trigger('click')
    await wrapper.get('[data-demo-request="DR-102"]').trigger('click')
    await wrapper.get('[data-demo-action="DR-102-cancel"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-demo-request="DR-102"]').exists()).toBe(false)
  })

  it('shows signed status, amount and 30/60/90-day contract risk', async () => {
    const wrapper = mount(ContractsPage, { props: { apiClient: createMockApi({ latency: 0 }) }, global: await globals('/contracts') })
    await flushPromises()

    expect(wrapper.text()).toContain('评估协议')
    expect(wrapper.text()).toMatch(/\d+ 天内/)
    expect(wrapper.text()).toContain('未签署')
    expect(wrapper.text()).toContain('¥68万')
  })
  it('downloads a saved Demo Request and keeps cards visible after a generation error', async () => {
    const api = createMockApi({ latency: 0 })
    const save = vi.spyOn(api, 'saveDemoArtifact')
    const wrapper = mount(DemoRequestsPage, { props: { apiClient: api }, global: await globals('/demo-requests') })
    await flushPromises()

    await wrapper.get('[data-demo-download="DR-101"]').trigger('click')
    await flushPromises()
    expect(docxMocks.generateDemoRequestDocxArtifact).toHaveBeenCalledWith(expect.objectContaining({ id: 'DR-101' }))
    expect(save).toHaveBeenCalledWith(expect.objectContaining({
      demoRequestId: 'DR-101', type: 'Demo Request DOCX', visibility: 'Internal',
    }))
    expect(wrapper.get('[data-demo-save="DR-101"]').attributes()).toMatchObject({
      download: 'Demo_Request_DR-101.docx',
    })
    expect(wrapper.text()).toContain('Word 已生成，请点击“保存 Word 文件”完成下载。')

    docxMocks.generateDemoRequestDocxArtifact.mockRejectedValueOnce(new Error('generation failed'))
    await wrapper.get('[data-demo-download="DR-101"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('generation failed')
    expect(wrapper.find('[data-demo-request="DR-101"]').exists()).toBe(true)
  })
  it('downloads Word for management and engineering roles even when Artifact saving is denied', async () => {
    for (const role of ['Manager', 'Engineer'] as const) {
      const api = createMockApi({
        latency: 0,
        role,
        ...(role === 'Engineer'
          ? { userName: '演示员工14' }
          : { userName: '演示经理01' }),
      })
      const save = vi.spyOn(api, 'saveDemoArtifact')
        .mockRejectedValue(new CrmApiError('PERMISSION_DENIED', '当前角色没有 Artifact 写入权限', 'req_artifact_denied'))
      const wrapper = mount(DemoRequestsPage, { props: { apiClient: api }, global: await globals('/demo-requests') })
      await flushPromises()
      await wrapper.get('[data-demo-download]').trigger('click')
      await flushPromises()

      expect(save).toHaveBeenCalled()
      expect(wrapper.get('[data-demo-save]').attributes('download')).toMatch(/^Demo_Request_.*\.docx$/)
      expect(wrapper.text()).toContain('当前角色没有 Artifact 写入权限，本次文件不会保存到归档。')
      expect(wrapper.text()).not.toContain('Word 文档生成失败')
      wrapper.unmount()
    }
  })
  it('lets management update workflow status but keeps Test Run entry owner-gated', async () => {
    const management = createMockApi({ latency: 0, role: 'Manager' })
    const requests = mount(DemoRequestsPage, { props: { apiClient: management }, global: await globals('/demo-requests') })
    await flushPromises()
    expect(requests.find('.page-actions .primary-button').exists()).toBe(true)
    await requests.get('[data-demo-view="manager"]').trigger('click')
    expect(requests.find('[data-demo-action]').exists()).toBe(true)

    const evaluations = mount(EvaluationsPage, { props: { apiClient: management }, global: await globals('/evaluations') })
    await flushPromises()
    expect(evaluations.find('[data-add-run]').exists()).toBe(false)
    expect(evaluations.find('[data-complete-preparation]').exists()).toBe(true)
  })

  it('reloads after report upload and exposes the same Artifact metadata in Demo Test and Demo archive', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      const evaluation = snapshot.evaluations.find((item) => item.id === 'EVAL-103')!
      evaluation.status = 'Testing'
      evaluation.reportStatus = 'Not Ready'
    })
    const boss = createMockApi({ repository, latency: 0, role: 'Manager', userName: 'Demo Staff 03' })
    const wrapper = mount(EvaluationsPage, { props: { apiClient: boss }, global: await globals('/evaluations') })
    await flushPromises()

    await wrapper.get('[data-evaluation-view="execution"]').trigger('click')
    await wrapper.get('[data-report-action="EVAL-103"]').trigger('click')
    await flushPromises()
    const internalInput = wrapper.get('[data-internal-report]')
    const externalInput = wrapper.get('[data-external-report]')
    Object.defineProperty(internalInput.element, 'files', { value: [new File(['capture=98.5'], 'results.txt', { type: 'text/plain' })], configurable: true })
    Object.defineProperty(externalInput.element, 'files', { value: [new File(['customer result'], 'customer-results.txt', { type: 'text/plain' })], configurable: true })
    await internalInput.trigger('change')
    await externalInput.trigger('change')
    await wrapper.get('[data-upload-test-report]').trigger('click')
    await flushPromises()
    await flushPromises()

    const snapshot = await repository.read()
    const evaluation = snapshot.evaluations.find((item) => item.id === 'EVAL-103')!
    const archive = (await boss.listDemoWorkflows()).data.items.find((item) => item.id === 'DR-107')!
    const reportArtifacts = archive.artifacts?.filter((item) => item.type === 'Test Report') ?? []
    expect(reportArtifacts).toHaveLength(2)
    expect(evaluation).toMatchObject({
      reportStatus: 'Ready',
      reportArtifactId: evaluation.internalReportArtifactId,
      reportVersion: reportArtifacts[0].version,
    })
    expect(new Set(reportArtifacts.map((item) => item.id))).toEqual(new Set([
      evaluation.internalReportArtifactId, evaluation.externalReportArtifactId,
    ]))
  })
})
