import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
import { accounts } from '@/api/mock-data'
import { controlledDocuments, demoProjects, installedTools, opportunities, procedureRuns, serviceAppointments } from '@/demo/operations-data'
import DemoWorkflowPage from './DemoWorkflowPage.vue'
import DemoDetailPage from './DemoDetailPage.vue'
import DocumentCenterPage from './DocumentCenterPage.vue'
import InstalledToolsPage from './InstalledToolsPage.vue'
import OpportunityStrategyPage from './OpportunityStrategyPage.vue'
import ServiceCalendarPage from './ServiceCalendarPage.vue'
import { createMockApi } from '@/api/mock-adapter'
import { createAppRouter } from '@/app/router'

describe('first demo completion contract', () => {
  it('uses shared customer IDs across every operational module', () => {
    const accountIds = new Set(accounts.map((account) => account.id))
    const rows = [...opportunities, ...demoProjects, ...installedTools, ...serviceAppointments, ...procedureRuns]
    expect(rows.every((row) => accountIds.has(row.accountId))).toBe(true)
    expect(demoProjects.every((demo) => opportunities.some((opportunity) => opportunity.id === demo.opportunityId))).toBe(true)
    expect(serviceAppointments.every((service) => installedTools.some((tool) => tool.serial === service.tool))).toBe(true)
    expect(procedureRuns.every((run) => installedTools.some((tool) => tool.serial === run.tool))).toBe(true)
  })

  it('provides the required commercial, demo, installed-base and audit fields', () => {
    expect(opportunities[0]).toMatchObject({ toolType: expect.any(String), saleType: expect.any(String), currency: expect.any(String), shipmentDate: expect.any(String), fatDate: expect.any(String), competition: expect.any(String) })
    expect(opportunities[0].history.length).toBeGreaterThan(0)
    expect(demoProjects[0]).toMatchObject({ contact: expect.any(String), industry: expect.any(String), specificRequest: expect.any(String), conclusion: expect.any(Object) })
    expect(installedTools[0]).toMatchObject({ sourceOpportunityId: expect.any(String), serviceContract: expect.any(String), pmCycle: expect.any(String), ownershipType: expect.any(String) })
    expect(serviceAppointments[0]).toMatchObject({ issue: expect.any(String), priority: expect.any(String), rootCause: expect.any(String), actionsPerformed: expect.any(String), customerSignoff: expect.any(String) })
    expect(procedureRuns[0]).toMatchObject({ qualificationResult: expect.any(String), deviation: expect.any(String), rollbackResult: expect.any(String) })
    expect(controlledDocuments[0].versions.length).toBeGreaterThan(0)
  })

  it('renders each completion area in the business workspaces', async () => {
    const apiClient = createMockApi({ latency: 0 })
    const router = createAppRouter()
    await router.push('/leads-opportunities?view=opportunities')
    await router.isReady()
    const demoRouter = createAppRouter()
    await demoRouter.push('/demo-workflow')
    await demoRouter.isReady()
    const opportunity = mount(OpportunityStrategyPage, { props: { apiClient }, global: { plugins: [createPinia(), router] } })
    const demo = mount(DemoWorkflowPage, { props: { apiClient }, global: { plugins: [createPinia(), demoRouter] } })
    const installed = mount(InstalledToolsPage, { props: { apiClient } })
    const service = mount(ServiceCalendarPage, { props: { apiClient }, global: { plugins: [createPinia()] } })
    const documents = mount(DocumentCenterPage, {
      props: { apiClient: createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01' }) },
    })
    await flushPromises()
    await installed.get('[data-installed-tool-surface="detail"]').trigger('click')
    await flushPromises()

    expect(opportunity.text()).toContain('Commercial Forecast')
    expect(opportunity.text()).toContain('Change History')
    expect(demo.get('h1').text()).toBe('Demo 档案')
    expect(demo.findAll('[data-demo-stage]')).toHaveLength(6)
    expect(demo.text()).not.toContain('Customer Q&A')
    await demo.get('[data-demo-id="DR-108"]').trigger('click')
    await vi.waitFor(() => expect(demoRouter.currentRoute.value.name).toBe('demo-detail'))
    const detailRouter = createAppRouter()
    await detailRouter.push({ name: 'demo-detail', params: { demoId: 'DR-108' }, query: { from: 'demo-workflow' } })
    await detailRouter.isReady()
    const detail = mount(DemoDetailPage, { props: { apiClient }, global: { plugins: [createPinia(), detailRouter] } })
    await flushPromises()
    expect(detail.text()).not.toContain('Test Run DDL')
    expect(detail.text()).toContain('基本信息')
    expect(detail.text()).toContain('测试报告')
    expect(detail.text()).toContain('Demo 结论')
    expect(detail.find('[data-demo-progress]').exists()).toBe(false)
    expect(installed.text()).toContain('版本与配置')
    expect(installed.text()).toContain('质保与服务')
    expect(service.text()).toContain('Calendar')
    expect(documents.text()).toContain('版本历史')
    expect(documents.text()).toContain('下载审计')
  })
})
