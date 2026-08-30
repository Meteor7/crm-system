import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CrmApiError } from '@/api'
import { createMockApi } from '@/api/mock-adapter'
import { DASHBOARD_CHART_IDS } from '@/features/dashboard/dashboard-subscriptions'
import DashboardPage from './DashboardPage.vue'
import { createAppRouter } from '@/app/router'
import { useAppStore } from '@/stores/app'

async function globals() {
  const router = createAppRouter()
  await router.push('/dashboard')
  await router.isReady()
  return { plugins: [createPinia(), router], stubs: { CrmChart: { template: '<div data-testid="chart" />' } } }
}

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-07-17T10:30:00+08:00'))
    localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders KPI data from the API instead of static markup', async () => {
    const wrapper = mount(DashboardPage, {
      props: { apiClient: createMockApi({ latency: 0, role: 'Manager', userName: '演示经理01' }) },
      global: await globals(),
    })
    await flushPromises()

    expect(wrapper.text()).toContain('信息中心')
    expect(wrapper.text()).toContain('Open Pipeline')
    expect(wrapper.text()).toContain('Confirmed Booking')
    expect(wrapper.text()).toContain('累计 Closed Won')
    expect(wrapper.text()).toContain('CNY 56,900,000.00')
    expect(wrapper.text()).toContain('CNY 41,768,000.00')
    expect(wrapper.text()).toContain('CNY 22,400,000.00')
    expect(wrapper.text()).toContain('实际 Booking 月度分布')
    expect(wrapper.text()).toContain('重点事项与执行提醒')
    expect(wrapper.text()).toContain('相关事项速览')
    expect(wrapper.text()).not.toContain('管理者待干预')
    expect(wrapper.text()).not.toContain('Calendar Overview')
    expect(wrapper.text()).toContain('Test DDL')
    expect(wrapper.text()).not.toContain('Document Compliance')
    expect(wrapper.text()).toContain('查看更多分析')
    expect(wrapper.get('[data-dashboard-subscriptions]').text()).toContain('我的订阅看板')
    expect(wrapper.findAll('[data-subscribed-dashboard]')).toHaveLength(3)
    expect(wrapper.find('[data-testid="manage-dashboard-subscriptions"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('验证与合同提醒')
    expect(wrapper.text()).not.toContain('数据完整度')
    expect(wrapper.text()).not.toContain('看板时间范围')
    expect(wrapper.text()).not.toContain('客户情报')
    expect(wrapper.find('[data-testid="trend-chart-grid"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="chart"]')).toHaveLength(3)
    expect(wrapper.find('.kpi-value-pipeline').exists()).toBe(true)
    expect(wrapper.find('.kpi-value-weighted').exists()).toBe(true)
    expect(wrapper.find('.kpi-value-booking').exists()).toBe(true)
    expect(wrapper.find('.kpi-value-won').exists()).toBe(true)
    const primaryCards = wrapper.findAll('.decision-grid > .section-card')
    expect(primaryCards).toHaveLength(3)
    expect(primaryCards[0].text()).toContain('Demo / Wafer Test 状态')
    expect(primaryCards[0].text()).toContain('EVALUATION')
    expect(wrapper.text()).not.toContain('团队业绩与管线')
    const scheduleItems = wrapper.findAll('.team-schedule-list > button')
    expect(scheduleItems).toHaveLength(5)
    await scheduleItems.find((item) => item.text().includes('DR-110'))!.trigger('click')
    expect(wrapper.get('.snapshot-body').text()).toContain('DR-110')
    expect(wrapper.get('.snapshot-body').text()).toContain('EVAL-106')
    expect(wrapper.get('.snapshot-body').text()).toContain('提前客户预期 1 天')

    await wrapper.get('[data-testid="toggle-more-analysis"]').trigger('click')

    expect(wrapper.findAll('.section-card').filter((card) => card.text().includes('Demo / Wafer Test 状态'))).toHaveLength(1)
    expect(wrapper.findAll('[data-testid="chart"]')).toHaveLength(15)
    expect(DASHBOARD_CHART_IDS).not.toEqual(expect.arrayContaining(['contracts', 'contract-type', 'contract-risk']))
    const renderedDashboardIds = [
      ...wrapper.findAll('[data-subscribed-dashboard]'),
      ...wrapper.findAll('[data-expanded-dashboard]'),
    ].map((card) => card.attributes('data-dashboard-id'))
    expect(renderedDashboardIds).toEqual([...DASHBOARD_CHART_IDS])
    expect(new Set(renderedDashboardIds).size).toBe(DASHBOARD_CHART_IDS.length)
    const datasetCards = wrapper.findAll('.dashboard-dataset-card')
    expect(datasetCards).toHaveLength(DASHBOARD_CHART_IDS.length)
    expect(datasetCards.every((card) => card.find('[data-dashboard-source]').exists())).toBe(false)
    expect(wrapper.text()).toContain('收起更多分析')
  })

  it('lets Boss replace one of exactly three subscribed charts without duplicating it below', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Manager', userName: '演示经理01' })
    const wrapper = mount(DashboardPage, {
      props: { apiClient },
      global: await globals(),
    })
    await flushPromises()

    expect(wrapper.findAll('[data-subscribed-dashboard]').map((card) => card.attributes('data-dashboard-id')))
      .toEqual(['evaluation-status', 'booking-month', 'top-accounts'])

    await wrapper.get('[data-testid="manage-dashboard-subscriptions"]').trigger('click')
    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.text()).toContain('管理订阅看板')
    expect(dialog.findAll('[data-subscription-option][aria-pressed="true"]')).toHaveLength(3)
    expect(dialog.get('[data-subscription-id="region"]').attributes('disabled')).toBeDefined()

    await dialog.get('[data-subscription-id="evaluation-status"]').trigger('click')
    expect(dialog.get('[data-modal-submit]').attributes('disabled')).toBeDefined()
    expect(dialog.get('[data-subscription-id="region"]').attributes('disabled')).toBeUndefined()

    await dialog.get('[data-subscription-id="region"]').trigger('click')
    expect(dialog.get('[data-modal-submit]').attributes('disabled')).toBeUndefined()
    await dialog.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.findAll('[data-subscribed-dashboard]').map((card) => card.attributes('data-dashboard-id')))
      .toEqual(['booking-month', 'top-accounts', 'region'])

    await wrapper.get('[data-testid="toggle-more-analysis"]').trigger('click')
    expect(wrapper.findAll('[data-expanded-dashboard][data-dashboard-id="evaluation-status"]')).toHaveLength(1)
    expect(wrapper.findAll('[data-expanded-dashboard][data-dashboard-id="region"]')).toHaveLength(0)

    wrapper.unmount()
    const restored = mount(DashboardPage, {
      props: { apiClient },
      global: await globals(),
    })
    await flushPromises()

    expect(restored.findAll('[data-subscribed-dashboard]').map((card) => card.attributes('data-dashboard-id')))
      .toEqual(['booking-month', 'top-accounts', 'region'])
  })

  it('lets Boss add a second complete subscription row and restores both rows', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Manager', userName: '演示经理01' })
    const wrapper = mount(DashboardPage, {
      props: { apiClient },
      global: await globals(),
    })
    await flushPromises()

    expect(wrapper.findAll('[data-subscription-dashboard-row]')).toHaveLength(1)
    await wrapper.get('[data-testid="manage-dashboard-subscriptions"]').trigger('click')
    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.findAll('[data-subscription-row-tab]')).toHaveLength(1)
    expect(dialog.find('[data-testid="delete-subscription-row"]').exists()).toBe(false)

    await dialog.get('[data-testid="add-subscription-row"]').trigger('click')

    expect(dialog.findAll('[data-subscription-row-tab]')).toHaveLength(2)
    expect(dialog.get('[data-subscription-row-index="1"]').attributes('aria-pressed')).toBe('true')
    expect(dialog.get('[data-modal-submit]').attributes('disabled')).toBeDefined()
    expect(dialog.get('[data-subscription-id="evaluation-status"]').attributes('disabled')).toBeDefined()
    expect(dialog.get('[data-subscription-id="evaluation-status"]').text()).toContain('第 1 排已订阅')

    await dialog.get('[data-subscription-id="region"]').trigger('click')
    await dialog.get('[data-subscription-id="tier"]').trigger('click')
    await dialog.get('[data-subscription-id="risk"]').trigger('click')

    expect(dialog.get('[data-modal-submit]').attributes('disabled')).toBeUndefined()
    await dialog.get('form').trigger('submit')
    await flushPromises()

    const rows = wrapper.findAll('[data-subscription-dashboard-row]')
    expect(rows).toHaveLength(2)
    expect(rows[0].findAll('[data-subscribed-dashboard]')).toHaveLength(3)
    expect(rows[1].findAll('[data-subscribed-dashboard]')).toHaveLength(3)
    expect(wrapper.findAll('[data-subscribed-dashboard]').map((card) => card.attributes('data-dashboard-id')))
      .toEqual(['evaluation-status', 'booking-month', 'top-accounts', 'region', 'tier', 'risk'])

    await wrapper.get('[data-testid="toggle-more-analysis"]').trigger('click')
    const allDashboardIds = [
      ...wrapper.findAll('[data-subscribed-dashboard]'),
      ...wrapper.findAll('[data-expanded-dashboard]'),
    ].map((card) => card.attributes('data-dashboard-id'))
    expect(allDashboardIds).toEqual([...DASHBOARD_CHART_IDS])
    expect(new Set(allDashboardIds).size).toBe(DASHBOARD_CHART_IDS.length)

    wrapper.unmount()
    const restored = mount(DashboardPage, {
      props: { apiClient },
      global: await globals(),
    })
    await flushPromises()

    expect(restored.findAll('[data-subscription-dashboard-row]')).toHaveLength(2)
    expect(restored.findAll('[data-subscribed-dashboard]').map((card) => card.attributes('data-dashboard-id')))
      .toEqual(['evaluation-status', 'booking-month', 'top-accounts', 'region', 'tier', 'risk'])
  })

  it('keeps the first row, discards cancelled deletion, and can delete a later row', async () => {
    localStorage.setItem(
      'semiconductor-crm:boss-dashboard-subscriptions:v2:zhao.jing%40crm.example.invalid',
      JSON.stringify([
        ['evaluation-status', 'booking-month', 'top-accounts'],
        ['region', 'tier', 'risk'],
      ]),
    )
    const wrapper = mount(DashboardPage, {
      props: { apiClient: createMockApi({ latency: 0, role: 'Manager', userName: '演示经理01' }) },
      global: await globals(),
    })
    await flushPromises()

    await wrapper.get('[data-testid="manage-dashboard-subscriptions"]').trigger('click')
    let dialog = wrapper.get('[role="dialog"]')
    expect(dialog.find('[data-testid="delete-subscription-row"]').exists()).toBe(false)
    await dialog.get('[data-subscription-row-index="1"]').trigger('click')
    await dialog.get('[data-testid="delete-subscription-row"]').trigger('click')
    await dialog.get('.secondary-button').trigger('click')

    expect(wrapper.findAll('[data-subscription-dashboard-row]')).toHaveLength(2)

    await wrapper.get('[data-testid="manage-dashboard-subscriptions"]').trigger('click')
    dialog = wrapper.get('[role="dialog"]')
    await dialog.get('[data-subscription-row-index="1"]').trigger('click')
    await dialog.get('[data-testid="delete-subscription-row"]').trigger('click')
    await dialog.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.findAll('[data-subscription-dashboard-row]')).toHaveLength(1)
    expect(wrapper.findAll('[data-subscribed-dashboard]').map((card) => card.attributes('data-dashboard-id')))
      .toEqual(['evaluation-status', 'booking-month', 'top-accounts'])

    await wrapper.get('[data-testid="toggle-more-analysis"]').trigger('click')
    expect(wrapper.findAll('[data-expanded-dashboard][data-dashboard-id="region"]')).toHaveLength(1)
    expect(wrapper.findAll('[data-expanded-dashboard][data-dashboard-id="tier"]')).toHaveLength(1)
    expect(wrapper.findAll('[data-expanded-dashboard][data-dashboard-id="risk"]')).toHaveLength(1)
  })

  it('falls back to the default subscriptions when browser data is invalid', async () => {
    localStorage.setItem(
      'semiconductor-crm:boss-dashboard-subscriptions:v1:%E8%B5%B5%E6%80%BB%40crm.example.invalid',
      JSON.stringify(['region', 'risk']),
    )
    const wrapper = mount(DashboardPage, {
      props: { apiClient: createMockApi({ latency: 0, role: 'Manager', userName: '演示经理01' }) },
      global: await globals(),
    })
    await flushPromises()

    expect(wrapper.findAll('[data-subscribed-dashboard]').map((card) => card.attributes('data-dashboard-id')))
      .toEqual(['evaluation-status', 'booking-month', 'top-accounts'])
  })

  it('shows non-management users only the next 15 days reminder center', async () => {
    const wrapper = mount(DashboardPage, {
      props: { apiClient: createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01' }) },
      global: await globals(),
    })
    await flushPromises()

    expect(wrapper.text()).toContain('信息中心')
    expect(wrapper.text()).toContain('未来 15 天提醒')
    expect(wrapper.findAll('[data-reminder-id]').length).toBeGreaterThan(0)
    expect(wrapper.text()).not.toContain('Open Pipeline')
    expect(wrapper.text()).not.toContain('管理者待干预')
    expect(wrapper.text()).not.toContain('数据完整度')
    expect(wrapper.find('[data-testid="trend-chart-grid"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="manage-dashboard-subscriptions"]').exists()).toBe(false)
  })

  it('loads the Engineer reminder center without requesting Sales visits', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Engineer', userName: '演示员工14' })
    const listVisits = vi.fn().mockRejectedValue(
      new CrmApiError('PERMISSION_DENIED', 'Visit access denied', 'req_visit_denied', false),
    )
    apiClient.listVisits = listVisits
    const pinia = createPinia()
    useAppStore(pinia).bootstrap = (await apiClient.getBootstrap()).data
    const router = createAppRouter()
    await router.push('/dashboard')
    await router.isReady()

    const wrapper = mount(DashboardPage, {
      props: { apiClient },
      global: { plugins: [pinia, router], stubs: { CrmChart: { template: '<div data-testid="chart" />' } } },
    })
    await flushPromises()

    expect(listVisits).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('信息中心')
    expect(wrapper.text()).toContain('未来 15 天提醒')
    expect(wrapper.text()).toContain('Demo Test DDL')
    expect(wrapper.text()).not.toContain('Visit access denied')
  })

  it('reads every reminder page instead of truncating visits and Demo work at 200 rows', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Manager', userName: 'Demo Staff 01' })
    const visitSeed = (await apiClient.listVisits({ page: 1, pageSize: 1 })).data.items
    const requestSeed = (await apiClient.listDemoRequests({ page: 1, pageSize: 1 })).data.items
    const evaluationSeed = (await apiClient.listEvaluations({ page: 1, pageSize: 1 })).data.items
    const paged = <T,>(items: T[], requestPrefix: string) => vi.fn(async (query: { page?: number; pageSize?: number } = {}) => {
      const page = query.page ?? 1
      const pageSize = query.pageSize ?? 20
      return {
        data: { items: page === 1 ? items : [] },
        meta: { requestId: `${requestPrefix}-${page}`, total: 201, page, pageSize },
        warnings: [],
      }
    })
    const listVisits = paged(visitSeed, 'req-visit-page')
    const listDemoRequests = paged(requestSeed, 'req-request-page')
    const listEvaluations = paged(evaluationSeed, 'req-evaluation-page')
    apiClient.listVisits = listVisits
    apiClient.listDemoRequests = listDemoRequests
    apiClient.listEvaluations = listEvaluations

    mount(DashboardPage, { props: { apiClient }, global: await globals() })
    await flushPromises()

    expect(listVisits).toHaveBeenNthCalledWith(2, { page: 2, pageSize: 200 })
    expect(listDemoRequests).toHaveBeenNthCalledWith(2, { page: 2, pageSize: 200 })
    expect(listEvaluations).toHaveBeenNthCalledWith(2, { page: 2, pageSize: 200 })
  })

  it('shows a request ID and retries after a dashboard failure', async () => {
    const base = createMockApi({ latency: 0, role: 'Manager', userName: '演示经理01' })
    const apiClient = {
      ...base,
      getDashboard: vi.fn()
        .mockRejectedValueOnce(new CrmApiError('UPSTREAM_TIMEOUT', '经营数据请求超时', 'req_test_42', true))
        .mockImplementation((query) => base.getDashboard(query)),
    }
    const wrapper = mount(DashboardPage, { props: { apiClient }, global: await globals() })
    await flushPromises()

    expect(wrapper.text()).toContain('req_test_42')
    await wrapper.get('[data-testid="retry-dashboard"]').find('button').trigger('click')
    await flushPromises()

    expect(apiClient.getDashboard).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('Open Pipeline')
  })
})
