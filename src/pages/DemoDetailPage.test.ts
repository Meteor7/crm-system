import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { CrmApiError } from '@/api'
import { createAppRouter } from '@/app/router'
import { createDemoRepository, createMemoryDemoStorage, seedDemoSnapshot } from '@/demo/demo-repository'
import DemoDetailPage from './DemoDetailPage.vue'

async function mountPage(
  tab: 'information' | 'comment' = 'information',
  from: 'demo-workflow' | 'demo-requests' | 'evaluations' = 'demo-workflow',
) {
  const router = createAppRouter()
  await router.push({
    name: 'demo-detail',
    params: { demoId: 'DR-105' },
    query: { tab, from },
  })
  await router.isReady()
  const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
  const apiClient = createMockApi({
    repository,
    latency: 0,
    role: 'Manager',
    userName: '演示员工24',
    today: '2026-07-31',
  })
  const wrapper = mount(DemoDetailPage, {
    props: { apiClient },
    global: { plugins: [createPinia(), router] },
  })
  await flushPromises()
  return { wrapper, router, apiClient }
}

describe('Demo detail page', () => {
  it('loads the routed project by exact id instead of searching a capped list', async () => {
    const router = createAppRouter()
    await router.push('/demo-workflow/DR-201')
    await router.isReady()
    const seedApi = createMockApi({ latency: 0, role: 'Manager' })
    const project = (await seedApi.listDemoWorkflows({ page: 1, pageSize: 1 })).data.items[0]
    const exact = vi.fn().mockResolvedValue({ data: { ...project, id: 'DR-201', title: '第 201 条真实 Demo 项目' }, warnings: [] })
    const apiClient = Object.assign(createMockApi({ latency: 0, role: 'Manager' }), { getDemoWorkflow: exact })
    const list = vi.spyOn(apiClient, 'listDemoWorkflows')

    const wrapper = mount(DemoDetailPage, {
      props: { apiClient },
      global: { plugins: [createPinia(), router] },
    })
    await flushPromises()

    expect(exact).toHaveBeenCalledWith('DR-201')
    expect(list).not.toHaveBeenCalled()
    expect(wrapper.get('[data-demo-detail]').text()).toContain('第 201 条真实 Demo 项目')
  })

  it.each([
    ['a terminated Demo', 'Rejected', 'Customer paused the project', 'Pending', '已终止'],
    ['a historical rejection', 'Rejected', '', 'Rejected', '已拒绝'],
    ['an accepted Demo', 'Accepted', '', 'Accepted', '已接受'],
  ])('shows %s from the reopened archive projection', async (_label, status, terminationReason, acceptance, chip) => {
    const seedApi = createMockApi({ latency: 0, role: 'Manager' })
    const project = (await seedApi.listDemoWorkflows({ page: 1, pageSize: 1 })).data.items[0]
    const ended = {
      ...project, id: 'DR-110', status, terminationReason, archiveCategory: 'Completed' as const,
      evaluation: project.evaluation && { ...project.evaluation, status },
      conclusion: { ...project.conclusion, status: acceptance as 'Pending' | 'Accepted' | 'Rejected' },
    }
    const apiClient = Object.assign(createMockApi({ latency: 0, role: 'Manager' }), {
      getDemoWorkflow: vi.fn().mockResolvedValue({ data: ended, warnings: [] }),
    })
    // Every open reads the persisted projection again; nothing is carried over from the session.
    for (let open = 0; open < 2; open++) {
      const router = createAppRouter()
      await router.push('/demo-workflow/DR-110')
      await router.isReady()
      const wrapper = mount(DemoDetailPage, { props: { apiClient }, global: { plugins: [createPinia(), router] } })
      await flushPromises()
      expect(wrapper.get('.status-chip').text()).toBe(chip)
      const conclusion = wrapper.get('.conclusion-panel')
      if (terminationReason) {
        expect(conclusion.get('[data-termination-reason]').text()).toContain(terminationReason)
        expect(conclusion.get('[data-customer-review-status]').text()).toContain('未评审')
      } else {
        expect(conclusion.find('[data-termination-reason]').exists()).toBe(false)
        expect(wrapper.text()).not.toContain('已终止')
      }
      wrapper.unmount()
    }
  })

  it('keeps the Demo detail visible and shows Request ID when an artifact download fails', async () => {
    const router = createAppRouter()
    await router.push('/demo-workflow/DR-FAIL')
    await router.isReady()
    const seedApi = createMockApi({ latency: 0, role: 'Manager' })
    const project = (await seedApi.listDemoWorkflows({ page: 1, pageSize: 1 })).data.items[0]
    const apiClient = Object.assign(createMockApi({ latency: 0, role: 'Manager' }), {
      getDemoWorkflow: vi.fn().mockResolvedValue({ data: {
        ...project, id: 'DR-FAIL', artifacts: [{ id: 'ART-FAIL', type: 'Test Report', fileName: 'failed.pdf', version: 1, createdAt: '2026-08-14' }],
      }, warnings: [] }),
      getDemoArtifact: vi.fn().mockRejectedValue(new CrmApiError('FILE_UNAVAILABLE', 'Artifact is unavailable', 'req-artifact-fail')),
    })
    const wrapper = mount(DemoDetailPage, {
      props: { apiClient }, global: { plugins: [createPinia(), router] },
    })
    await flushPromises()

    await wrapper.get('[data-download-artifact="ART-FAIL"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-demo-detail]').text()).toContain(project.title)
    expect(wrapper.get('[data-artifact-error]').text()).toContain('Artifact is unavailable')
    expect(wrapper.get('[data-artifact-error]').text()).toContain('req-artifact-fail')
  })

  it.each([
    ['demo-requests', '/demo-requests'],
    ['evaluations', '/evaluations'],
  ] as const)('shows a prominent back button for %s details', async (from, expectedPath) => {
    const { wrapper } = await mountPage('information', from)
    const backButton = wrapper.get('.back-link')

    expect(backButton.classes()).toContain('detail-back-button')
    expect(backButton.attributes('href')).toBe(expectedPath)
  })

  it('renders the shared project information and complete timeline', async () => {
    const { wrapper, router } = await mountPage()

    expect(router.currentRoute.value.path).toBe('/demo-workflow/DR-105')
    expect(wrapper.get('[data-demo-detail]').text()).toContain('先进制程缺陷复检准备')
    expect(wrapper.get('[data-demo-detail-tab="information"]').attributes('aria-current')).toBe('page')
    expect(wrapper.get('[data-demo-detail-information]').text()).toContain('Demo Request')
    expect(wrapper.get('[data-demo-detail-information]').text()).toContain('Demo Test')
    expect(wrapper.get('[data-project-timeline-dashboard]').text()).toContain('内部评审')
    expect(wrapper.findAll('[data-parallel-lane]')).toHaveLength(2)
  })

  it('publishes a persistent Comment from the current user', async () => {
    const { wrapper, router, apiClient } = await mountPage('comment')

    expect(wrapper.get('[data-demo-detail-tab="comment"]').attributes('aria-current')).toBe('page')
    expect(wrapper.findAll('[data-demo-comment]').length).toBeGreaterThanOrEqual(3)
    expect(wrapper.get('.mention-picker').text()).toContain('\u6f14\u793a\u7ecf\u740601')
    await wrapper.get('.mention-picker input[value="person073@crm.example.invalid"]').setValue(true)
    await wrapper.get('.mention-picker input[value="person077@crm.example.invalid"]').setValue(true)
    await wrapper.get('[data-demo-comment-input]').setValue('内部评审结论已补充，请演示员工14复核。')
    await wrapper.get('[data-publish-demo-comment]').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[data-demo-comments]').text()).toContain('内部评审结论已补充，请演示员工14复核。')
    expect(wrapper.get('[data-demo-comments]').text()).toContain('演示员工24')
    expect((await apiClient.listDemoComments('DR-105')).data.items[0].body).toBe('内部评审结论已补充，请演示员工14复核。')
    expect((await apiClient.listDemoComments('DR-105')).data.items[0].mentionedPeople).toEqual([
      { id: 'person073@crm.example.invalid', name: '\u6f14\u793a\u7ecf\u740601' },
      { id: 'person077@crm.example.invalid', name: '\u6f14\u793a\u5458\u5de514' },
    ])
    expect(wrapper.get('[data-demo-comments]').text()).toContain('@\u6f14\u793a\u7ecf\u740601')
    expect(wrapper.get('[data-demo-comments]').text()).toContain('@\u6f14\u793a\u5458\u5de514')
    expect(router.currentRoute.value.query.tab).toBe('comment')
  })

  it('loads all comment pages so older project discussion does not disappear after 200 rows', async () => {
    const router = createAppRouter()
    await router.push('/demo-workflow/DR-105?tab=comment')
    await router.isReady()
    const apiClient = createMockApi({ latency: 0, role: 'Manager' })
    const seed = (await apiClient.listDemoComments('DR-105', { page: 1, pageSize: 1 })).data.items[0]!
    const comments = Array.from({ length: 201 }, (_, index) => ({
      ...seed,
      id: `CMT-PAGED-${String(index + 1).padStart(3, '0')}`,
      body: `Project discussion ${index + 1}`,
    }))
    const listDemoComments = vi.spyOn(apiClient, 'listDemoComments').mockImplementation(async (_id, query = {}) => {
      const page = query.page ?? 1
      const pageSize = query.pageSize ?? 20
      const start = (page - 1) * pageSize
      return {
        data: { items: comments.slice(start, start + pageSize) },
        meta: { requestId: `req-comment-page-${page}`, total: comments.length, page, pageSize },
        warnings: [],
      }
    })
    const wrapper = mount(DemoDetailPage, {
      props: { apiClient }, global: { plugins: [createPinia(), router] },
    })
    await flushPromises()

    expect(listDemoComments).toHaveBeenNthCalledWith(1, 'DR-105', { page: 1, pageSize: 200 })
    expect(listDemoComments).toHaveBeenNthCalledWith(2, 'DR-105', { page: 2, pageSize: 200 })
    expect(wrapper.findAll('[data-demo-comment]')).toHaveLength(201)
    expect(wrapper.text()).toContain('Project discussion 201')
  })
})
