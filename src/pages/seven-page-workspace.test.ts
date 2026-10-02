import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { navigation } from '@/app/navigation'
import { createMockApi } from '@/api/mock-adapter'
import { useAppStore } from '@/stores/app'
import { createAppRouter } from '@/app/router'
import type { UserRole } from '@/types/crm'
import DocumentCenterPage from './DocumentCenterPage.vue'
import DemoWorkflowPage from './DemoWorkflowPage.vue'
import DemoDetailPage from './DemoDetailPage.vue'
import EvaluationsPage from './EvaluationsPage.vue'
import InstalledToolsPage from './InstalledToolsPage.vue'
import OpportunityStrategyPage from './OpportunityStrategyPage.vue'
import ServiceCalendarPage from './ServiceCalendarPage.vue'

afterEach(() => vi.useRealTimers())

async function mountDemoForRole(role: UserRole) {
  const pinia = createPinia()
  const router = createAppRouter()
  await router.push('/demo-workflow')
  await router.isReady()
  const wrapper = mount(DemoWorkflowPage, {
    props: { apiClient: createMockApi({ latency: 0, role }) },
    global: { plugins: [pinia, router] },
  })
  await flushPromises()
  return wrapper
}

async function mountDemoDetailForRole(role: UserRole, demoId = 'DR-108') {
  const pinia = createPinia()
  const router = createAppRouter()
  await router.push({ name: 'demo-detail', params: { demoId }, query: { from: 'demo-workflow' } })
  await router.isReady()
  const wrapper = mount(DemoDetailPage, {
    props: { apiClient: createMockApi({ latency: 0, role }) },
    global: { plugins: [pinia, router] },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('P1 business workspace', () => {
  const pages = [
    [OpportunityStrategyPage, 'Opportunities', 'opportunity-strategy'],
    [DemoWorkflowPage, 'Demo 档案', 'demo-workflow'],
    [InstalledToolsPage, 'Installed Tools', 'installed-tools'],
    [DocumentCenterPage, 'Document Center', 'document-center'],
    [ServiceCalendarPage, '日历', 'calendar'],
  ] as const

  it.each(pages)('renders %s as a complete page', (component, title, pageId) => {
    const wrapper = mount(component, { props: { apiClient: createMockApi({ latency: 0 }) }, global: { plugins: [createPinia(), createAppRouter()] } })
    expect(wrapper.get(`[data-page="${pageId}"]`).text()).toContain(title)
    expect(wrapper.find('[data-testid="page-placeholder"]').exists()).toBe(false)
  })

  it('publishes P1 beside the retained CRM foundation in the primary navigation', () => {
    const keys = navigation.flatMap((group) => group.items.map((item) => item.key))
    expect(keys).toEqual(expect.arrayContaining([
      'dashboard',
      'leads',
      'opportunities',
      'booking',
      'demo-workflow',
      'installed-tools',
      'calendar',
      'document-center',
    ]))
  })

  it('publishes Demo, Demo Request and Demo Test as separate navigation modules', () => {
    const demoGroup = navigation.find((group) => group.label === 'Demo 中心')

    expect(demoGroup?.items.map(({ key, label, path }) => ({ key, label, path }))).toEqual([
      { key: 'demo-workflow', label: 'Demo 档案', path: '/demo-workflow' },
      { key: 'demo-requests', label: 'Demo Request', path: '/demo-requests' },
      { key: 'demo-test', label: 'Demo Test', path: '/evaluations' },
    ])
  })

  it('positions Demo Test as analysis based on Demo Request', async () => {
    const wrapper = mount(EvaluationsPage, {
      props: { apiClient: createMockApi({ latency: 0 }) },
      global: { plugins: [createPinia(), createAppRouter()] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Demo Test')
    expect(wrapper.text()).toContain('与 Demo Request 同步管理测试准备、执行和客户评审')
  })

  it('projects complete Demo detail by the active three-role identity', async () => {
    const { wrapper: management } = await mountDemoDetailForRole('Manager')
    expect(management.find('[data-demo-sensitive="contact"]').exists()).toBe(true)
    expect(management.find('[data-demo-sensitive="wafer-samples"]').exists()).toBe(true)
    expect(management.find('[data-demo-sensitive="test-runs"]').exists()).toBe(true)

    const { wrapper: sales } = await mountDemoDetailForRole('Sales')
    expect(sales.find('[data-demo-sensitive="contact"]').exists()).toBe(false)
    expect(sales.find('[data-demo-sensitive="wafer-samples"]').exists()).toBe(false)
    expect(sales.find('[data-demo-sensitive="test-runs"]').exists()).toBe(true)
    expect(sales.findAll('[data-demo-sensitive="test-runs"] tbody tr')).toHaveLength(0)
    expect(sales.get('[data-demo-sensitive="test-runs"]').text()).not.toContain('Test Run DDL')
    expect(sales.get('[data-testid="selected-demo"]').text()).toContain('主要设备')
    expect(sales.get('[data-testid="selected-demo"]').text()).toContain('客户评审')
  })

  it('hides percentage progress from Demo cards and shows Engineer Review', async () => {
    const management = await mountDemoForRole('Manager')
    expect(management.find('.workspace-progress').exists()).toBe(false)
    expect(management.get('[data-demo-board]').text()).not.toMatch(/\d+%/)
    expect(management.text()).toContain('工程评估')
    expect(management.text()).not.toContain('Scope Review')
  })

  it('shows only active Demo work on the lifecycle board', async () => {
    const administrator = await mountDemoForRole('Manager')
    expect(administrator.findAll('.pipeline-card').length).toBeGreaterThan(0)
    expect(administrator.text()).not.toContain('已完成历史归档')
  })

  it('switches the selected opportunity and its strategy evidence', async () => {
    const wrapper = mount(OpportunityStrategyPage, { props: { apiClient: createMockApi({ latency: 0 }) }, global: { plugins: [createPinia(), createAppRouter()] } })
    await new Promise((resolve) => setTimeout(resolve, 0))
    await wrapper.get('[data-opportunity-id="OPP-007"]').trigger('click')
    expect(wrapper.get('[data-testid="selected-opportunity"]').text()).toContain('先进封装外观检测')
    expect(wrapper.text()).toContain('价格竞争进入最终轮')
  })

  it('switches the selected demo and wafer evidence', async () => {
    const { wrapper, router } = await mountDemoDetailForRole('Manager', 'DR-107')
    await router.push({ name: 'demo-detail', params: { demoId: 'DR-108' }, query: { from: 'demo-workflow' } })
    await vi.waitFor(() => expect(wrapper.get('[data-demo-detail]').text()).toContain('Micro-bump 检测客户评审'))
    expect(router.currentRoute.value.params.demoId).toBe('DR-108')
    expect(wrapper.get('[data-testid="selected-demo"]').text()).toContain('CUSTOMER05-R01')
  })

  it('filters the approved technical document catalog without exposing file links', async () => {
    const wrapper = mount(DocumentCenterPage, { props: { apiClient: createMockApi({ latency: 0, role: 'Sales' }) } })
    await new Promise((resolve) => setTimeout(resolve, 0))
    await wrapper.get('[data-library-filter="Technical"]').trigger('click')
    expect(wrapper.findAll('[data-document-row]')).toHaveLength(2)
    expect(wrapper.html()).not.toContain('href="http')
  })

  it('shows the selected Installed Tool lifecycle and warranty state', async () => {
    const wrapper = mount(InstalledToolsPage, { props: { apiClient: createMockApi({ latency: 0 }) } })
    await new Promise((resolve) => setTimeout(resolve, 0))
    await wrapper.get('[data-installed-tool-surface="detail"]').trigger('click')
    await flushPromises()
    const toolCards = wrapper.findAll('.workspace-select-card')

    await toolCards[2].trigger('click')
    await flushPromises()

    expect(wrapper.get('.lifecycle-step.is-current').text()).toContain('安装')
    expect(wrapper.get('[data-testid=installed-tool-master-data]').text()).toContain('SO-260041')
    await wrapper.findAll('.detail-tabs button')[2].trigger('click')
    expect(wrapper.get('.warranty-body').text()).toContain('档案完整')
    expect(wrapper.text()).toContain('After SAT')
  })

  it('replaces Installed Tool metrics with filters and reset', async () => {
    const wrapper = mount(InstalledToolsPage, { props: { apiClient: createMockApi({ latency: 0 }) } })
    await flushPromises()
    await wrapper.get('[data-installed-tool-surface="detail"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('.tool-metrics').exists()).toBe(false)
    const accountFilter = wrapper.get('select[aria-label="客户筛选"]')
    await accountFilter.setValue(accountFilter.findAll('option')[1].attributes('value')!)
    await flushPromises()
    expect(wrapper.findAll('.workspace-select-card').length).toBeLessThan(3)
    await wrapper.get('[data-testid="reset-installed-tool-filters"]').trigger('click')
    expect(wrapper.findAll('.workspace-select-card')).toHaveLength(3)
  })

  it('shows a converted Booking in Installed Tools with FAT as the current stage', async () => {
    const apiClient = createMockApi({ latency: 0 })
    const converted = await apiClient.convertBookingToInstalledTool('BKG-001', {
      siteId: 'SITE-006',
      engineerOwner: 'person077@crm.example.invalid',
      serial: 'FS12-CN-PAGE-001',
      model: 'FastScan 1200',
    })
    const wrapper = mount(InstalledToolsPage, { props: { apiClient } })
    await flushPromises()
    await wrapper.get('[data-installed-tool-surface="detail"]').trigger('click')
    await flushPromises()

    await wrapper.get(`[data-installed-tool-archive-id="${converted.data.installedTool.id}"]`).trigger('click')
    await flushPromises()
    expect(wrapper.get('.lifecycle-step.is-current').text()).toContain('FAT')
    expect(wrapper.text()).toContain('演示员工14')
    expect(wrapper.text()).not.toContain('@crm.example.invalid')
  })

  it('lets Boss edit any Installed Tool and reassign its engineer', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Manager', userName: '演示经理01' })
    const version = (await apiClient.getInstalledTool('TOOL-001')).data.modified!
    const updateInstalledTool = vi.spyOn(apiClient, 'updateInstalledTool')
    const wrapper = mount(InstalledToolsPage, { props: { apiClient } })
    await flushPromises()
    await wrapper.get('[data-installed-tool-surface="detail"]').trigger('click')
    await flushPromises()

    await wrapper.get('[data-testid="edit-installed-tool"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').attributes('aria-label')).toBe('编辑 Installed Tool 主数据')
    expect(wrapper.get('select[aria-label="负责工程师"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('input[aria-label="现场位置"]').setValue('Boss Updated Bay')
    await wrapper.get('select[aria-label="负责工程师"]').setValue('person053@crm.example.invalid')
    await wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()

    expect(updateInstalledTool).toHaveBeenCalledWith('TOOL-001', expect.any(Object), version)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('.tool-header').text()).toContain('Boss Updated Bay')
    expect((await apiClient.listInstalledTools()).data.items.find((item) => item.id === 'TOOL-001'))
      .toMatchObject({ location: 'Boss Updated Bay', engineerOwner: 'person053@crm.example.invalid' })
  })

  it('shows engineers only their assigned Installed Tools and locks reassignment', async () => {
    const wrapper = mount(InstalledToolsPage, {
      props: {
        apiClient: createMockApi({
          latency: 0,
          role: 'Engineer',
          userName: '演示员工14',
          assignedAccountIds: [],
        }),
      },
    })
    await flushPromises()
    await wrapper.get('[data-installed-tool-surface="detail"]').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.workspace-select-card')).toHaveLength(1)
    expect(wrapper.get('.workspace-select-card').text()).toContain('TOOL-001')
    await wrapper.get('[data-testid="edit-installed-tool"]').trigger('click')
    expect(wrapper.get('select[aria-label="负责工程师"]').attributes('disabled')).toBeDefined()
  })

  it('keeps Installed Tools read-only for Sales', async () => {
    const wrapper = mount(InstalledToolsPage, {
      props: { apiClient: createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01' }) },
    })
    await flushPromises()
    await wrapper.get('[data-installed-tool-surface="detail"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="edit-installed-tool"]').exists()).toBe(false)
  })

  it('renders upstream schedules in month and week Calendar views for Boss', async () => {
    const pinia = createPinia()
    useAppStore(pinia).bootstrap = (await createMockApi({ latency: 0, role: 'Manager' }).getBootstrap()).data
    const router = createAppRouter()
    await router.push('/calendar')
    await router.isReady()
    const wrapper = mount(ServiceCalendarPage, {
      props: { apiClient: createMockApi({ latency: 0, role: 'Manager' }) },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('全员安排')
    expect(wrapper.text()).toContain('Demo Test DDL')
    const companySelect = wrapper.get('select[aria-label="公司"]')
    const company = (companySelect.findAll('option')[1].element as HTMLOptionElement).value
    await companySelect.setValue(company)
    expect(wrapper.get('.event-detail').text()).toContain(company)
    await wrapper.get('.calendar-filters > button').trigger('click')

    const ownerSelect = wrapper.get('select[aria-label="负责人"]')
    const ownerOption = ownerSelect.findAll('option')[1]
    const owner = (ownerOption.element as HTMLOptionElement).value
    const ownerLabel = ownerOption.text()
    await ownerSelect.setValue(owner)
    expect(wrapper.get('.event-detail').text()).toContain(ownerLabel)
    await wrapper.get('.view-switch button:first-child').trigger('click')
    expect(wrapper.find('.week-view').exists()).toBe(true)
  })

  it('opens the exact upstream record from the plain Calendar detail button', async () => {
    const pinia = createPinia()
    const routeComponent = { template: '<div />' }
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/calendar', name: 'calendar', component: routeComponent },
        { path: '/visits', name: 'visits', component: routeComponent },
        { path: '/demo-workflow/:demoId', name: 'demo-detail', component: routeComponent },
        { path: '/evaluations', name: 'evaluations', component: routeComponent },
        { path: '/booking/:bookingId', name: 'booking-detail', component: routeComponent },
      ],
    })
    const apiClient = createMockApi({ latency: 0, role: 'Manager' })
    useAppStore(pinia).bootstrap = (await apiClient.getBootstrap()).data
    await router.push('/calendar')
    await router.isReady()

    const date = new Date()
    const dateKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
    const visits = await apiClient.listVisits({ page: 1, pageSize: 200 })
    const requests = await apiClient.listDemoRequests({ page: 1, pageSize: 200 })
    const evaluations = await apiClient.listEvaluations({ page: 1, pageSize: 200 })
    const pipeline = await apiClient.listPipeline({})
    const visit = visits.data.items[0]!
    const request = requests.data.items[0]!
    const evaluation = evaluations.data.items[0]!
    const booking = pipeline.data.bookings[0]!

    vi.spyOn(apiClient, 'listVisits').mockResolvedValue({
      ...visits,
      data: { items: [{ ...visit, date: dateKey }] },
    })
    vi.spyOn(apiClient, 'listDemoRequests').mockResolvedValue({
      ...requests,
      data: { items: [{ ...request, customerExpectedDate: dateKey, targetDate: dateKey }] },
    })
    vi.spyOn(apiClient, 'listEvaluations').mockResolvedValue({
      ...evaluations,
      data: { items: [{ ...evaluation, testRunDeadline: dateKey }] },
    })
    vi.spyOn(apiClient, 'listPipeline').mockResolvedValue({
      ...pipeline,
      data: { ...pipeline.data, bookings: [{ ...booking, ddl: dateKey }] },
    })

    const wrapper = mount(ServiceCalendarPage, {
      props: { apiClient },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    const destinations = [
      ['visit', `/visits?focus=${visit.id}`],
      ['request', `/demo-workflow/${request.id}?from=demo-requests`],
      ['test', `/evaluations?focus=${evaluation.id}`],
      ['booking', `/booking/${booking.id}`],
    ] as const

    for (const [eventClass, expectedPath] of destinations) {
      const monthEvent = wrapper.find(`.calendar-event.${eventClass}`)
      if (monthEvent.exists()) {
        await monthEvent.trigger('click')
      } else {
        await wrapper.get('.more-events').trigger('click')
        const dayEvent = wrapper.findAll('.day-agenda-list > button').find((item) => item.find(`.${eventClass}`).exists())
        expect(dayEvent).toBeDefined()
        await dayEvent!.trigger('click')
      }
      expect(wrapper.get('[data-calendar-detail]').text()).toBe('查看详情')
      await wrapper.get('[data-calendar-detail]').trigger('click')
      await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe(expectedPath))
    }

    await wrapper.get('.more-events').trigger('click')
    expect(wrapper.get('.day-agenda-detail [data-calendar-detail]').text()).toBe('查看详情')
  })

  it('reloads Sales visits after bootstrap resolves on a direct Calendar refresh', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-08-12T12:00:00+08:00'))
    const pinia = createPinia()
    const app = useAppStore(pinia)
    const baseApi = createMockApi({
      latency: 0,
      role: 'Sales',
      userId: 'person002@crm.example.invalid',
      userName: 'Demo Staff 01',
      today: '2026-08-12',
    })
    const bootstrapResult = await baseApi.getBootstrap()
    const visitResult = await baseApi.listVisits({ page: 1, pageSize: 200 })
    const seededVisit = visitResult.data.items[0]
    expect(seededVisit).toBeDefined()

    let resolveBootstrap!: (value: typeof bootstrapResult) => void
    const apiClient = {
      ...baseApi,
      getBootstrap: vi.fn(() => new Promise<typeof bootstrapResult>((resolve) => { resolveBootstrap = resolve })),
      listVisits: vi.fn(async () => ({
        ...visitResult,
        data: { items: [{ ...seededVisit, date: '2026-08-12' }] },
        meta: { ...visitResult.meta!, total: 1 },
      })),
    }

    const router = createAppRouter()
    await router.push('/calendar')
    await router.isReady()
    const wrapper = mount(ServiceCalendarPage, {
      props: { apiClient },
      global: { plugins: [pinia, router] },
    })
    const bootstrapPromise = app.loadBootstrap(apiClient)
    await flushPromises()
    expect(apiClient.listVisits).not.toHaveBeenCalled()

    resolveBootstrap(bootstrapResult)
    await bootstrapPromise
    await flushPromises()

    expect(apiClient.listVisits).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('.calendar-event.visit')).toHaveLength(1)
  })
  it('keeps server-scoped Sales events when the user ID differs from the display name', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-08-12T12:00:00+08:00'))
    const pinia = createPinia()
    const apiClient = createMockApi({
      latency: 0,
      role: 'Sales',
      userId: 'person002@crm.example.invalid',
      userName: 'Demo Staff 01',
      today: '2026-08-12',
    })
    useAppStore(pinia).bootstrap = (await apiClient.getBootstrap()).data

    const router = createAppRouter()
    await router.push('/calendar')
    await router.isReady()
    const wrapper = mount(ServiceCalendarPage, {
      props: { apiClient },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    expect(wrapper.findAll('.calendar-event').length).toBeGreaterThan(0)
  })
  it('loads the Engineer Calendar without requesting Sales visits', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-08-12T12:00:00+08:00'))
    const pinia = createPinia()
    const apiClient = createMockApi({
      latency: 0,
      role: 'Engineer',
      userId: 'person077@crm.example.invalid',
      userName: '演示员工14',
      today: '2026-08-12',
    })
    useAppStore(pinia).bootstrap = (await apiClient.getBootstrap()).data
    const listVisits = vi.fn().mockRejectedValue(new Error('Visit access denied'))
    apiClient.listVisits = listVisits
    const listPipeline = apiClient.listPipeline.bind(apiClient)
    const managerPipeline = await createMockApi({ latency: 0, role: 'Manager', userId: 'person029@crm.example.invalid' }).listPipeline({})
    const assignedAccountBooking = managerPipeline.data.bookings[0]
    expect(assignedAccountBooking).toBeDefined()
    apiClient.listPipeline = async (query) => {
      const result = await listPipeline(query)
      return {
        ...result,
        data: {
          ...result.data,
          bookings: [{ ...assignedAccountBooking, ddl: '2026-08-12', owner: 'person002@crm.example.invalid' }],
        },
      }
    }

    const router = createAppRouter()
    await router.push('/calendar')
    await router.isReady()
    const wrapper = mount(ServiceCalendarPage, {
      props: { apiClient },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    expect(listVisits).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('日历')
    expect(wrapper.text()).toContain('Demo Test DDL')
    expect(wrapper.findAll('.calendar-event').length).toBeGreaterThan(0)
    expect(wrapper.findAll('.calendar-event.request').length).toBeGreaterThan(0)
    expect(wrapper.findAll('.calendar-event.booking')).toHaveLength(1)
    expect(wrapper.find('.calendar-state.error').exists()).toBe(false)
  })

  it('opens the complete day agenda when a month cell has more than three events', async () => {
    const pinia = createPinia()
    const apiClient = createMockApi({ latency: 0, role: 'Manager' })
    useAppStore(pinia).bootstrap = (await apiClient.getBootstrap()).data
    const listVisits = apiClient.listVisits.bind(apiClient)
    apiClient.listVisits = async (query) => {
      const result = await listVisits(query)
      const seed = result.data.items[0]
      const date = new Date().toISOString().slice(0, 10)
      return {
        ...result,
        data: {
          items: Array.from({ length: 5 }, (_, index) => ({
            ...seed,
            id: `VIS-CROWDED-${index + 1}`,
            subject: `集中安排 ${index + 1}`,
            date,
          })),
        },
      }
    }
    const router = createAppRouter()
    await router.push('/calendar')
    await router.isReady()
    const wrapper = mount(ServiceCalendarPage, {
      props: { apiClient },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    await wrapper.get('.more-events').trigger('click')
    expect(wrapper.get('.day-agenda-header').text()).toContain('DAY OVERVIEW')
    expect(wrapper.findAll('.day-agenda-list > button').length).toBeGreaterThanOrEqual(5)
    await wrapper.findAll('.day-agenda-list > button').find((item) => item.text().includes('集中安排 2'))!.trigger('click')
    expect(wrapper.get('.day-agenda-detail').text()).toContain('集中安排 2')
  })

  it('drops the Test DDL and customer expected events of terminated Demos only', async () => {
    const pinia = createPinia()
    const apiClient = createMockApi({ latency: 0, role: 'Manager' })
    useAppStore(pinia).bootstrap = (await apiClient.getBootstrap()).data
    const router = createAppRouter()
    await router.push('/calendar')
    await router.isReady()

    const date = new Date()
    const dateKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
    const visits = await apiClient.listVisits({ page: 1, pageSize: 200 })
    const requests = await apiClient.listDemoRequests({ page: 1, pageSize: 200 })
    const evaluations = await apiClient.listEvaluations({ page: 1, pageSize: 200 })
    const pipeline = await apiClient.listPipeline({})
    const request = requests.data.items[0]!
    const evaluation = evaluations.data.items[0]!
    const reason = 'Customer paused the project'
    const withDeadline = (id: string, demoRequestId: string, changes: Partial<typeof evaluation>) => ({
      ...evaluation, id, demoRequestId, testRunDeadline: dateKey, terminationReason: '', ...changes,
    })
    const linkedRequest = (id: string, evaluationId?: string) => ({
      ...request, id, status: evaluationId ? 'Converted' as const : 'Engineer Review' as const, evaluationId,
      customerExpectedDate: dateKey, targetDate: dateKey,
    })
    // Terminated before any Test DDL was set, so the ranged Evaluation list cannot return it.
    const early = { ...evaluation, id: 'EVAL-EARLY', demoRequestId: 'DR-EARLY', status: 'Rejected' as const, terminationReason: reason, testRunDeadline: '' }

    vi.spyOn(apiClient, 'listVisits').mockResolvedValue({ ...visits, data: { items: [] }, meta: { ...visits.meta!, total: 0 } })
    vi.spyOn(apiClient, 'listPipeline').mockResolvedValue({ ...pipeline, data: { ...pipeline.data, bookings: [] } })
    vi.spyOn(apiClient, 'listEvaluations').mockResolvedValue({
      ...evaluations,
      meta: { ...evaluations.meta!, total: 4 },
      data: { items: [
        withDeadline('EVAL-RUNNING', 'DR-RUNNING', { status: 'Testing' }),
        withDeadline('EVAL-TERMINATED', 'DR-TERMINATED', { status: 'Rejected', terminationReason: reason }),
        withDeadline('EVAL-HISTORICAL', 'DR-HISTORICAL', { status: 'Rejected' }),
        withDeadline('EVAL-ACCEPTED', 'DR-ACCEPTED', { status: 'Accepted' }),
      ] },
    })
    vi.spyOn(apiClient, 'listDemoRequests').mockResolvedValue({
      ...requests,
      meta: { ...requests.meta!, total: 6 },
      data: { items: [
        linkedRequest('DR-RUNNING', 'EVAL-RUNNING'),
        linkedRequest('DR-TERMINATED', 'EVAL-TERMINATED'),
        linkedRequest('DR-HISTORICAL', 'EVAL-HISTORICAL'),
        linkedRequest('DR-ACCEPTED', 'EVAL-ACCEPTED'),
        linkedRequest('DR-EARLY', 'EVAL-EARLY'),
        linkedRequest('DR-OPEN'),
      ] },
    })
    const getEvaluation = vi.spyOn(apiClient, 'getEvaluation').mockImplementation(async (id) => {
      if (id !== early.id) throw new Error(`Unexpected Evaluation read ${id}`)
      return { ...evaluations, data: early }
    })

    const wrapper = mount(ServiceCalendarPage, { props: { apiClient }, global: { plugins: [pinia, router] } })
    await flushPromises()
    await wrapper.get('.view-switch button:first-child').trigger('click')
    await flushPromises()

    const titles = wrapper.findAll('.week-event strong').map((item) => item.text())
    const shown = (id: string) => titles.some((title) => title.startsWith(`${id} `))
    expect(getEvaluation).toHaveBeenCalledWith('EVAL-EARLY')
    expect(getEvaluation.mock.calls.every(([id]) => id === 'EVAL-EARLY')).toBe(true)
    for (const id of ['EVAL-RUNNING', 'EVAL-HISTORICAL', 'EVAL-ACCEPTED', 'DR-RUNNING', 'DR-HISTORICAL', 'DR-ACCEPTED', 'DR-OPEN']) {
      expect(shown(id), id).toBe(true)
    }
    for (const id of ['EVAL-TERMINATED', 'DR-TERMINATED', 'DR-EARLY']) expect(shown(id), id).toBe(false)
  })
})
