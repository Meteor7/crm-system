import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { CrmApiError } from '@/api'
import { createMockApi } from '@/api/mock-adapter'
import { createDemoRepository, createMemoryDemoStorage, seedDemoSnapshot } from '@/demo/demo-repository'
import { createAppRouter } from '@/app/router'
import AccountsPage from './AccountsPage.vue'
import RequirementsPage from './RequirementsPage.vue'
import PipelinePage from './PipelinePage.vue'
import DemoRequestsPage from './DemoRequestsPage.vue'
import EvaluationsPage from './EvaluationsPage.vue'
import DemoDetailPage from './DemoDetailPage.vue'

async function globals(path: string) {
  const router = createAppRouter()
  await router.push(path)
  await router.isReady()
  return { plugins: [createPinia(), router, ElementPlus], stubs: { teleport: true } }
}

const denied = () => new CrmApiError('PERMISSION_DENIED', '权限已撤销', 'req_revoked')

describe('permission revocation', () => {
  it('projects Demo archive fields by role before data reaches the page', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      const request = snapshot.demoRequests.find((item) => item.id === 'DR-108')!
      request.formData = {
        contactPerson: 'Sensitive Customer Contact', industry: 'Frontend', salesContact: 'person002@crm.example.invalid', demoOwner: 'person053@crm.example.invalid',
        sizeShape: '300 mm', material: 'Silicon', specificRequest: 'Business Request', detectMeasure: 'Defect capture',
        expectedResults: 'Customer result', otherTools: 'Sensitive Competition', primaryTool: 'Macro Inspection X8',
        complementaryTool: 'SEM', timing: '2026-Q3', keySuccessFactors: 'Capture target',
        internalQuestions: 'Sensitive Internal Question', customerQuestions: 'Customer delivery date?', wafers: [],
      }
      request.resourceWindow = '2026-08-01 ~ 2026-08-12'
      request.estimatedCompletionDate = '2026-08-13'
      request.engineerComment = 'Engineering archive comment'
      request.managerDecision = 'Approved'
      request.managerComment = 'Boss archive comment'
      const evaluation = snapshot.evaluations.find((item) => item.demoRequestId === request.id)!
      evaluation.runs[0].summary = 'Sensitive Unreleased Analysis'
      evaluation.status = 'Customer Review'
      evaluation.testRunDeadline = '2026-08-13'
      snapshot.artifacts.push(
        { id: 'ART-INTERNAL', demoRequestId: request.id, type: 'Demo Request DOCX', fileName: 'internal-request.docx', mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', version: 1, createdBy: 'person002@crm.example.invalid', createdAt: '2026-07-17T10:30:00+08:00', visibility: 'Internal', blob: new Blob(['docx']) },
        { id: 'ART-RELEASED', demoRequestId: request.id, evaluationId: evaluation.id, type: 'Test Report', fileName: 'released-report.pdf', mimeType: 'application/pdf', version: 1, createdBy: 'person029@crm.example.invalid', createdAt: '2026-07-17T10:30:00+08:00', visibility: 'Internal', blob: new Blob(['pdf']) },
      )
      evaluation.reportStatus = 'Ready'
      evaluation.reportArtifactId = 'ART-RELEASED'
      evaluation.reportVersion = 1
    })

    const bossData = (await createMockApi({ repository, latency: 0, role: 'Manager' }).listDemoWorkflows()).data.items
    const salesApi = createMockApi({ repository, latency: 0, role: 'Sales', userName: 'Demo Staff 01' })
    const salesData = (await salesApi.listDemoWorkflows()).data.items
    const bossArchive = JSON.stringify(bossData.find((item) => item.id === 'DR-108'))
    const salesArchive = JSON.stringify(salesData.find((item) => item.id === 'DR-108'))

    expect(bossArchive).toContain('Sensitive Customer Contact')
    expect(bossArchive).toContain('Sensitive Competition')
    expect(bossArchive).toContain('Sensitive Internal Question')
    expect(bossArchive).toContain('Sensitive Unreleased Analysis')
    expect(salesArchive).toContain('Business Request')
    expect(salesArchive).toContain('released-report.pdf')
    expect(salesArchive).not.toContain('Sensitive Customer Contact')
    expect(salesArchive).not.toContain('Sensitive Competition')
    expect(salesArchive).not.toContain('Sensitive Internal Question')
    expect(salesArchive).not.toContain('Sensitive Unreleased Analysis')
    expect(salesArchive).not.toContain('internal-request.docx')
    expect(salesData.find((item) => item.id === 'DR-108')?.evaluation).toMatchObject({ id: 'EVAL-104', status: 'Customer Review', testRunDeadline: '2026-08-13', runs: [] })
    const wrapper = mount(DemoDetailPage, { props: { apiClient: salesApi }, global: await globals('/demo-workflow/DR-108?from=demo-workflow') })
    await flushPromises()
    expect(wrapper.text()).toContain('Business Request')
    expect(wrapper.text()).toContain('released-report.pdf')
    expect(wrapper.text()).not.toContain('Test Run DDL')
    expect(wrapper.text()).not.toContain('客户预期')
    expect(wrapper.text()).not.toContain('Sensitive Customer Contact')
    expect(wrapper.text()).not.toContain('Sensitive Competition')
    expect(wrapper.text()).not.toContain('Sensitive Internal Question')
    expect(wrapper.text()).not.toContain('Sensitive Unreleased Analysis')

    const bossWrapper = mount(DemoDetailPage, {
      props: { apiClient: createMockApi({ repository, latency: 0, role: 'Manager' }) },
      global: await globals('/demo-workflow/DR-108?from=demo-workflow'),
    })
    await flushPromises()
    const text = bossWrapper.get('[data-testid="selected-demo"]').text()
    for (const expected of [
      '紧急', 'Demo Staff 01', 'Defect capture', 'SEM', '2026-08-01 ~ 2026-08-12', 'Engineering archive comment',
      'Approved', 'Boss archive comment', '演示员工15',
      '8', '96.1', '2.8', '38', 'Sensitive Unreleased Analysis', '2026-07-17',
    ]) expect(text).toContain(expected)
  })

  it('clears accounts after a successful list becomes forbidden', async () => {
    const base = createMockApi({ latency: 0 })
    const apiClient = { ...base, listAccounts: vi.fn().mockImplementationOnce((query) => base.listAccounts(query)).mockRejectedValueOnce(denied()) }
    const wrapper = mount(AccountsPage, { props: { apiClient }, global: await globals('/accounts') })
    await flushPromises()
    expect(wrapper.text()).toContain('示例企业014')

    await wrapper.get('[aria-label="业务领域"]').setValue('Advanced Packaging')
    await flushPromises()
    expect(wrapper.find('.state-denied').exists()).toBe(true)
    expect(wrapper.find('.account-stats').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('示例企业014')
  })

  it('clears requirements after a successful list becomes forbidden', async () => {
    const base = createMockApi({ latency: 0 })
    const apiClient = { ...base, listRequirements: vi.fn().mockImplementationOnce((query) => base.listRequirements(query)).mockRejectedValueOnce(denied()) }
    const wrapper = mount(RequirementsPage, { props: { apiClient }, global: await globals('/requirements') })
    await flushPromises()
    expect(wrapper.text()).toContain('Macro Inspection X8')

    await wrapper.get('[aria-label="需求状态"]').setValue('Demo验证')
    await flushPromises()
    expect(wrapper.find('.state-denied').exists()).toBe(true)
    expect(wrapper.find('.requirement-summary').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Macro Inspection X8')
  })

  it('clears pipeline data after a successful list becomes forbidden', async () => {
    const base = createMockApi({ latency: 0 })
    const apiClient = { ...base, listPipeline: vi.fn().mockImplementationOnce((query) => base.listPipeline(query)).mockRejectedValueOnce(denied()) }
    const wrapper = mount(PipelinePage, { props: { apiClient }, global: await globals('/pipeline') })
    await flushPromises()
    expect(wrapper.text()).toContain('南京缺陷检测设备')

    await wrapper.get('[aria-label="商机阶段"]').setValue('qualified_opportunity')
    await flushPromises()
    expect(wrapper.find('.state-denied').exists()).toBe(true)
    expect(wrapper.find('.pipeline-summary').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('南京缺陷检测设备')
  })

  it('clears Demo Requests when permission is revoked during a transition', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      snapshot.demoRequests.find((item) => item.id === 'DR-101')!.status = 'Draft'
    })
    const base = createMockApi({ repository, latency: 0 })
    const apiClient = { ...base, transitionDemoRequest: vi.fn().mockRejectedValue(denied()) }
    const wrapper = mount(DemoRequestsPage, { props: { apiClient }, global: await globals('/demo-requests') })
    await flushPromises()
    expect(wrapper.find('[data-demo-request="DR-101"]').exists()).toBe(true)

    await wrapper.get('[data-demo-view="sales"]').trigger('click')
    await wrapper.get('[data-demo-action="DR-101-submit"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('.state-denied').exists()).toBe(true)
    expect(wrapper.find('.request-summary').exists()).toBe(false)
    expect(wrapper.find('[data-demo-request="DR-101"]').exists()).toBe(false)
  })

  it('clears Demo Requests when the request has left the user\'s scope during a transition', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      snapshot.demoRequests.find((item) => item.id === 'DR-101')!.status = 'Draft'
    })
    const base = createMockApi({ repository, latency: 0 })
    // What the server answers when the request was reassigned and the user may no longer read it.
    const outOfScope = new CrmApiError('SCOPE_DENIED', 'The Demo Request is outside the current user scope.', 'req_scope')
    const apiClient = { ...base, transitionDemoRequest: vi.fn().mockRejectedValue(outOfScope) }
    const wrapper = mount(DemoRequestsPage, { props: { apiClient }, global: await globals('/demo-requests') })
    await flushPromises()

    await wrapper.get('[data-demo-view="sales"]').trigger('click')
    await wrapper.get('[data-demo-action="DR-101-submit"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('.state-denied').exists()).toBe(true)
    expect(wrapper.find('[data-demo-request="DR-101"]').exists()).toBe(false)
  })

  it('keeps Demo Requests when a write is refused for what it asks, not for who asks', async () => {
    const base = createMockApi({ repository: createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot), latency: 0 })
    // What the server answers a Sales user who names another Sales user as the Sales contact of a new request.
    const refused = new CrmApiError('SCOPE_DENIED', 'Sales users can only assign records to themselves.', 'req_refused')
    const apiClient = { ...base, createDemoRequest: vi.fn().mockRejectedValue(refused) }
    const wrapper = mount(DemoRequestsPage, { props: { apiClient }, global: await globals('/demo-requests') })
    await flushPromises()

    await wrapper.get('.page-actions .primary-button').trigger('click')
    await wrapper.findComponent({ name: 'DemoRequestModal' }).vm.$emit('submit', {})
    await flushPromises()
    expect(apiClient.createDemoRequest).toHaveBeenCalledTimes(1)
    // The refusal is shown as the error of that write; the page is not taken for one the user may no longer see,
    // and the dialog stays open with what was typed.
    expect(wrapper.find('.state-denied').exists()).toBe(false)
    expect(wrapper.get('[data-modal-error]').text()).toContain('销售只能把记录分配给自己，请把负责人选为本人。')
    expect(wrapper.find('[data-api-error]').exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'DemoRequestModal' }).exists()).toBe(true)
    expect(wrapper.find('[data-demo-request="DR-101"]').exists()).toBe(true)
  })

  it('clears Evaluations when permission is revoked during a status change', async () => {
    const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
    await repository.transact((snapshot) => {
      const evaluation = snapshot.evaluations.find((item) => item.id === 'EVAL-103')!
      evaluation.reportArtifactId = 'ART-READY'
      evaluation.internalReportArtifactId = 'ART-INTERNAL'
      evaluation.externalReportArtifactId = 'ART-EXTERNAL'
    })
    const base = createMockApi({ repository, latency: 0 })
    const apiClient = { ...base, updateEvaluationStatus: vi.fn().mockRejectedValue(denied()) }
    const wrapper = mount(EvaluationsPage, { props: { apiClient }, global: await globals('/evaluations') })
    await flushPromises()
    expect(wrapper.find('[data-evaluation="EVAL-103"]').exists()).toBe(true)

    await wrapper.get('[data-evaluation-view="execution"]').trigger('click')
    await wrapper.get('[data-evaluation="EVAL-103"]').trigger('click')
    await wrapper.get('[data-advance-status="Internal Review"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('.state-denied').exists()).toBe(true)
    expect(wrapper.find('[data-evaluation="EVAL-103"]').exists()).toBe(false)
  })

  it('clears Evaluations when permission is revoked while saving a Test Run', async () => {
    const base = createMockApi({ latency: 0 })
    const apiClient = { ...base, addEvaluationRun: vi.fn().mockRejectedValue(denied()) }
    const wrapper = mount(EvaluationsPage, { props: { apiClient }, global: await globals('/evaluations') })
    await flushPromises()

    await wrapper.get('[data-evaluation-view="execution"]').trigger('click')
    await wrapper.get('[data-add-run="EVAL-103"]').trigger('click')
    await wrapper.get('[aria-label="晶圆批次"]').setValue('LOT-DENIED')
    await wrapper.get('.modal-card form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('.state-denied').exists()).toBe(true)
    expect(wrapper.find('[data-evaluation="EVAL-103"]').exists()).toBe(false)
    expect(wrapper.find('.modal-card').exists()).toBe(false)
  })

})
