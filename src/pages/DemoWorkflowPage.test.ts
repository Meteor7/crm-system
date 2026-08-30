import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
import { createAppRouter } from '@/app/router'
import { createMockApi } from '@/api/mock-adapter'
import type { CrmApi } from '@/api'
import { createDemoRepository, createMemoryDemoStorage, seedDemoSnapshot } from '@/demo/demo-repository'
import DemoWorkflowPage from './DemoWorkflowPage.vue'

async function mountPage(apiOverride?: CrmApi) {
  const router = createAppRouter()
  await router.push('/demo-workflow')
  await router.isReady()
  const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
  const apiClient = apiOverride ?? createMockApi({
        repository,
        latency: 0,
        role: 'Manager',
        today: '2026-07-28',
      })
  const wrapper = mount(DemoWorkflowPage, {
    props: { apiClient },
    global: { plugins: [createPinia(), router] },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('Demo lifecycle archive board', () => {
  it('loads Demo workflows beyond the first 200 records', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Manager' })
    const seed = (await apiClient.listDemoWorkflows({ page: 1, pageSize: 1 })).data.items[0]
    const rows = Array.from({ length: 201 }, (_, index) => ({ ...seed, id: `DR-PAGED-${index + 1}` }))
    const list = vi.spyOn(apiClient, 'listDemoWorkflows').mockImplementation(async (query = {}) => {
      const page = query.page ?? 1
      const pageSize = query.pageSize ?? 20
      return {
        data: { items: rows.slice((page - 1) * pageSize, page * pageSize) },
        meta: { requestId: `req-demo-${page}`, page, pageSize, total: rows.length }, warnings: [],
      }
    })

    const { wrapper } = await mountPage(apiClient)

    expect(list).toHaveBeenNthCalledWith(1, { page: 1, pageSize: 200 })
    expect(list).toHaveBeenNthCalledWith(2, { page: 2, pageSize: 200 })
    expect(wrapper.findAll('.pipeline-card')).toHaveLength(201)
  })

  it('renders the project-cycle board from the existing Demo workflow records', async () => {
    const { wrapper, router } = await mountPage()

    expect(wrapper.findAll('[data-demo-surface]').map((button) => button.text())).toEqual([
      '项目周期看板',
      '生命周期看板',
      'Demo 档案',
    ])

    await wrapper.get('[data-demo-surface="project"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query.surface).toBe('project')
    expect(wrapper.find('[data-demo-project-placeholder]').exists()).toBe(false)
    expect(wrapper.find('[data-project-cycle-board]').exists()).toBe(true)
    expect(wrapper.findAll('[data-project-cycle-table]')).toHaveLength(1)
    expect(wrapper.findAll('[data-project-cycle-section]')).toHaveLength(0)
    const rows = wrapper.findAll('[data-project-cycle-row]')
    expect(rows).toHaveLength(10)
    expect(wrapper.findAll('[data-project-cycle-row] [data-project-timeline]')).toHaveLength(10)
    expect(rows.slice(0, 2).map((row) => row.attributes('data-project-id'))).toEqual(['DR-107', 'DR-108'])
    expect(rows.slice(0, 2).every((row) => row.attributes('data-customer-risk') === 'true')).toBe(true)
    expect(rows.slice(-2).every((row) => row.classes().includes('is-completed-project'))).toBe(true)
    expect(wrapper.get('[data-project-id="DR-101"] [data-customer-expected-ddl]').text()).toBe('DDL：2026-08-20')
    expect(wrapper.get('[data-project-id="DR-101"] [data-current-stage-owner]').text()).not.toBe('')
    expect(wrapper.get('[data-project-cycle-table]').text()).toContain('项目名称')
    expect(wrapper.get('[data-project-cycle-table]').text()).toContain('当前阶段负责人')
    expect(wrapper.get('[data-project-cycle-table]').text()).toContain('项目周期节点')
    expect(wrapper.get('[data-project-cycle-table]').text()).toContain('Wafer & Test Preparation')
    expect(wrapper.findAll('[data-parallel-preparation]')).toHaveLength(10)
    const parallelPreparation = wrapper.get('[data-project-id="DR-101"] [data-parallel-preparation]')
    expect(parallelPreparation.findAll('[data-parallel-lane]')).toHaveLength(2)
    expect(parallelPreparation.find('[data-parallel-stage="wafer-preparation"]').attributes('data-tooltip')).toBe('Wafer Preparation')
    expect(parallelPreparation.find('[data-parallel-stage="test-preparation"]').attributes('data-tooltip')).toBe('Test Preparation')
    const partialPreparation = wrapper.get('[data-project-id="DR-105"] [data-parallel-preparation]')
    expect(partialPreparation.classes()).toContain('current')
    expect(partialPreparation.get('[data-parallel-stage="wafer-preparation"]').classes()).toContain('done')
    expect(partialPreparation.get('[data-parallel-stage="test-preparation"]').classes()).toContain('current')
    expect(wrapper.get('[data-project-cycle-board]').text()).toContain('过去100天已完成')
    expect(wrapper.findAll('[data-customer-risk="true"]')).toHaveLength(2)
    expect(wrapper.get('[data-project-id="DR-107"]').attributes('data-customer-risk')).toBe('true')
    expect(wrapper.get('[data-project-id="DR-107"]').classes()).toContain('is-customer-risk')
    expect(wrapper.get('[data-project-id="DR-110"]').attributes('data-customer-risk')).toBe('false')
    expect(wrapper.get('[data-project-id="DR-110"]').classes()).not.toContain('is-customer-risk')
    expect(wrapper.get('[data-project-id="DR-110"]').classes()).toContain('is-completed-project')
    const projectTimeline = wrapper.get('[data-project-id="DR-101"] [data-project-timeline]').text()
    expect(projectTimeline).toContain('Sales Preparation')
    expect(projectTimeline).toContain('Engineer Review')
    expect(projectTimeline).toContain('Manager Approval')
    expect(projectTimeline).toContain('Wafer & Test Preparation')
    expect(projectTimeline).toContain('Test Execution')
    expect(projectTimeline).toContain('Customer Review')
    expect(wrapper.find('[data-demo-board]').exists()).toBe(false)
    expect(wrapper.find('[data-demo-archive]').exists()).toBe(false)
  })

  it('uses green for normal Request, orange for normal Test and red for urgent projects', async () => {
    const { wrapper } = await mountPage()
    await wrapper.get('[data-demo-surface="project"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-project-id="DR-101"]').classes()).toContain('is-request-project')
    expect(wrapper.get('[data-project-id="DR-105"]').classes()).toContain('is-test-project')
    expect(wrapper.get('[data-project-id="DR-101"] [data-project-timeline]').classes()).toContain('tone-request')
    expect(wrapper.get('[data-project-id="DR-105"] [data-project-timeline]').classes()).toContain('tone-test')
    expect(wrapper.get('[data-project-id="DR-107"]').classes()).toContain('is-customer-risk')
    expect(wrapper.get('[data-project-id="DR-107"]').text()).toContain('加急')
    expect(wrapper.get('[data-project-id="DR-107"] [data-project-timeline]').classes()).toContain('tone-critical')
    expect(wrapper.get('[data-project-id="DR-110"] [data-project-timeline]').classes()).toContain('tone-complete')
  })

  it('filters the project-cycle rows by customer and keeps the route query', async () => {
    const { wrapper, router } = await mountPage()
    await wrapper.get('[data-demo-surface="project"]').trigger('click')
    await flushPromises()

    const customer = wrapper.get('select[aria-label="项目客户"]')
    expect(customer.findAll('option').map((option) => option.text())).toContain('示例企业014有限公司')

    await customer.setValue('示例企业014有限公司')
    await flushPromises()

    expect(router.currentRoute.value.query.customer).toBe('示例企业014有限公司')
    const visibleProjects = wrapper.findAll('[data-project-id]')
    expect(visibleProjects).toHaveLength(2)

    await customer.setValue('all')
    await flushPromises()

    expect(router.currentRoute.value.query.customer).toBeUndefined()
    expect(wrapper.findAll('[data-project-id]')).toHaveLength(10)
  })

  it('opens the shared archive detail route from a project row', async () => {
    const { wrapper, router } = await mountPage()
    await wrapper.get('[data-demo-surface="project"]').trigger('click')
    await flushPromises()

    await wrapper.get('[data-project-id="DR-104"]').trigger('click')
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('demo-detail'))

    expect(router.currentRoute.value).toMatchObject({
      name: 'demo-detail',
      params: { demoId: 'DR-104' },
      query: { surface: 'project', from: 'demo-workflow' },
    })
  })

  it('opens a completed project from its row at the bottom of the board', async () => {
    const { wrapper, router } = await mountPage()
    await wrapper.get('[data-demo-surface="project"]').trigger('click')
    await flushPromises()

    await wrapper.get('[data-project-id="DR-110"]').trigger('click')
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('demo-detail'))

    expect(router.currentRoute.value).toMatchObject({
      name: 'demo-detail',
      params: { demoId: 'DR-110' },
      query: { surface: 'project', from: 'demo-workflow' },
    })
  })

  it('renders the six ordered lifecycle stages and active cards only', async () => {
    const { wrapper } = await mountPage()
    const stages = wrapper.findAll('[data-demo-stage]')

    expect(stages.map((stage) => stage.attributes('data-demo-stage'))).toEqual([
      'Engineer Review',
      'Manager Approval',
      'Test Preparation',
      'Test Execution',
      'Internal Review',
      'Customer Review',
    ])
    expect(wrapper.findAll('.pipeline-card').length).toBeGreaterThan(0)
    expect(wrapper.text()).not.toContain('创建 Demo Request 草稿')
  })

  it('keeps cards compact without dates or person avatars', async () => {
    const { wrapper } = await mountPage()
    const cards = wrapper.get('[data-demo-board]')

    expect(cards.get('[data-demo-id="DR-102"]').text()).toContain('Sales Demo Staff 02 · Engineer 演示员工15')
    expect(cards.text()).not.toContain('@crm.example.invalid')
    expect(cards.text()).not.toContain('Test Run DDL')
    wrapper.findAll('.pipeline-card').forEach((card) => {
      expect(card.text()).not.toMatch(/\d{4}-\d{2}-\d{2}/)
    })
    expect(cards.find('img').exists()).toBe(false)
    expect(cards.find('.avatar').exists()).toBe(false)
    expect(cards.findAll('[data-demo-stage-scroll]')).toHaveLength(6)
  })

  it('filters cards by health, Sales owner and Engineer owner', async () => {
    const { wrapper } = await mountPage()
    const originalCount = wrapper.findAll('.pipeline-card').length

    expect(wrapper.find('input[aria-label="搜索 Demo 档案"]').exists()).toBe(false)
    await wrapper.get('select[aria-label="健康状态"]').setValue('critical')
    expect(wrapper.findAll('.pipeline-card').length).toBeLessThan(originalCount)

    await wrapper.get('select[aria-label="健康状态"]').setValue('all')
    await wrapper.get('select[aria-label="Sales Owner"]').setValue('person002@crm.example.invalid')
    expect(wrapper.findAll('.pipeline-card').length).toBeGreaterThan(0)
    expect(wrapper.findAll('.pipeline-card').every((card) => card.text().includes('Sales Demo Staff 01'))).toBe(true)

    await wrapper.get('select[aria-label="Sales Owner"]').setValue('all')
    await wrapper.get('select[aria-label="Engineer Owner"]').setValue('person077@crm.example.invalid')
    expect(wrapper.findAll('.pipeline-card').length).toBeGreaterThan(0)
    expect(wrapper.findAll('.pipeline-card').every((card) => card.text().includes('Engineer 演示员工14'))).toBe(true)
    expect(wrapper.find('[data-stage-change]').exists()).toBe(false)
    expect(wrapper.find('[draggable="true"]').exists()).toBe(false)
  })

  it('opens the unified detail route from the lifecycle board', async () => {
    const { wrapper, router } = await mountPage()
    const first = wrapper.get('.pipeline-card')
    const id = first.attributes('data-demo-id')

    await first.trigger('click')
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('demo-detail'))

    expect(router.currentRoute.value).toMatchObject({
      name: 'demo-detail',
      params: { demoId: id },
      query: { from: 'demo-workflow' },
    })
  })

  it('switches to Demo archives and groups completed records by customer or equipment', async () => {
    const { wrapper, router } = await mountPage()

    await wrapper.get('[data-demo-surface="archive"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query.surface).toBe('archive')
    expect(wrapper.find('[data-demo-board]').exists()).toBe(false)
    expect(wrapper.findAll('[data-demo-archive-group]').length).toBeGreaterThan(0)
    expect(wrapper.findAll('[data-demo-id]')).toHaveLength(2)
    expect(wrapper.text()).toContain('示例企业003有限公司')
    expect(wrapper.text()).toContain('示例企业018有限公司')
    expect(wrapper.text()).toContain('Accepted')
    expect(wrapper.text()).toContain('Rejected')
    expect(wrapper.text()).toContain('DR-109')
    expect(wrapper.text()).toContain('DR-110')

    await wrapper.get('[data-archive-group-mode="equipment"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query.groupBy).toBe('equipment')
    expect(wrapper.text()).toContain('Macro Inspection X8')
    expect(wrapper.text()).toContain('PackageVision P7')
    expect(wrapper.text()).not.toContain('Customer Q&A')
    expect(wrapper.text()).not.toContain('On Hold')
  })

  it('opens an archived Demo detail and returns with archive classification preserved', async () => {
    const { wrapper, router } = await mountPage()
    await wrapper.get('[data-demo-surface="archive"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-archive-group-mode="equipment"]').trigger('click')
    await flushPromises()

    await wrapper.get('[data-demo-id="DR-110"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value).toMatchObject({
      name: 'demo-detail',
      params: { demoId: 'DR-110' },
      query: {
        surface: 'archive',
        groupBy: 'equipment',
        from: 'demo-workflow',
      },
    })
  })
})
