import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { createAppRouter } from '@/app/router'
import PageHeader from '@/design-system/PageHeader.vue'
import DataNotice from '@/design-system/DataNotice.vue'
import PipelineStageColumn from '@/design-system/PipelineStageColumn.vue'
import TestDeadlineModal from '@/features/evaluations/TestDeadlineModal.vue'
import { formatDisplayDate } from '@/domain/time'
import { setLocale } from '@/i18n'
import { useAppStore } from '@/stores/app'
import ServiceCalendarPage from './ServiceCalendarPage.vue'
import RequirementsPage from './RequirementsPage.vue'
import BookingDetailPage from './BookingDetailPage.vue'
import RfqDetailPage from './RfqDetailPage.vue'
import AppShell from '@/app/AppShell.vue'
import { createMemorySalesRepository } from '@/demo/sales-repository'

describe('PR4 review regressions', () => {
  it('keeps requirement filter values stable while translating their displayed labels', async () => {
    const api = createMockApi({ latency: 0 })
    const read = vi.spyOn(api, 'listRequirements')
    const wrapper = mount(RequirementsPage, { props: { apiClient: api } })
    await flushPromises()
    const select = wrapper.get('select.filter-control')
    setLocale('en-US')
    await flushPromises()
    expect(select.findAll('option').map((option) => option.text())).toEqual([
      'All statuses', 'Need identified', 'Technical confirmation', 'Demo validation', 'Budget approval', 'Procurement planning', 'Confirmed',
    ])
    expect(read).toHaveBeenCalledTimes(1)
    expect(wrapper.get('.requirement-summary').text()).not.toContain('万')
    expect(wrapper.get('.requirement-table').text()).toContain('units')
    await select.setValue('预算审批')
    await flushPromises()
    expect(read).toHaveBeenLastCalledWith(expect.objectContaining({ status: '预算审批' }))
    setLocale('zh-CN')
    await flushPromises()
    expect((select.element as HTMLSelectElement).value).toBe('预算审批')
    expect(wrapper.get('.requirement-table').text()).toContain('台')
    expect(read).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('switches the language through the shell menu and persists the selected option', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const pinia = createPinia()
    useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
    })
    await router.push('/dashboard')
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { RouterView: true } } })
    await flushPromises()
    await wrapper.get('[data-testid="locale-toggle"]').trigger('click')
    expect(wrapper.findAll('[role="menuitemradio"]')[0].attributes('aria-checked')).toBe('true')
    await wrapper.findAll('[role="menuitemradio"]')[1].trigger('click')
    expect(wrapper.find('.locale-menu').exists()).toBe(false)
    expect(document.documentElement.lang).toBe('en-US')
    expect(wrapper.get('nav.primary-nav').attributes('aria-label')).toBe('Main navigation')
    expect(localStorage.getItem('semicrm.locale')).toBe('en-US')
    expect(router.currentRoute.value.path).toBe('/dashboard')
    await wrapper.get('[data-testid="locale-toggle"]').trigger('click')
    expect(wrapper.findAll('[role="menuitemradio"]')[1].attributes('aria-checked')).toBe('true')
    await wrapper.findAll('[role="menuitemradio"]')[0].trigger('click')
    expect(document.documentElement.lang).toBe('zh-CN')
    expect(wrapper.get('nav.primary-nav').attributes('aria-label')).toBe('主导航')
    expect(localStorage.getItem('semicrm.locale')).toBe('zh-CN')
    wrapper.unmount()
  })

  it('translates an existing missing-Booking error without requesting data again', async () => {
    const api = createMockApi({ latency: 0 })
    const read = vi.spyOn(api, 'listPipeline')
    const router = createAppRouter()
    await router.push('/booking/MISSING-BOOKING')
    const wrapper = mount(BookingDetailPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('未找到 Booking MISSING-BOOKING')
    setLocale('en-US')
    await flushPromises()
    expect(wrapper.text()).toContain('Booking not found MISSING-BOOKING')
    expect(read).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('uses the selected language before confirming a protected RFQ revision', async () => {
    const repository = createMemorySalesRepository()
    const opportunity = repository.snapshot.opportunities.find((item) => item.owner === 'person002@crm.example.invalid')!
    opportunity.stage = 'customer_budget_approved'
    repository.save()
    const api = createMockApi({ latency: 0, role: 'Sales', userId: opportunity.owner, salesRepository: repository })
    const blob = new Blob(['%PDF mock'], { type: 'application/pdf' })
    const created = await api.createRfq({ opportunityId: opportunity.id, engineerId: 'person077@crm.example.invalid' }, { blob, fileName: 'rfq.pdf', mimeType: blob.type, size: blob.size })
    const response = await api.getRfq(created.data.id)
    vi.spyOn(api, 'getRfq').mockResolvedValue({ ...response, data: { ...response.data, status: 'Sales Revision' } })
    const revise = vi.spyOn(api, 'reviseRfq')
    const pinia = createPinia()
    useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
    const router = createAppRouter()
    await router.push(`/rfqs/${created.data.id}`)
    const wrapper = mount(RfqDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()
    const file = new File(['%TSD-Header-###%encrypted'], 'protected.pdf', { type: 'application/pdf' })
    const input = wrapper.get('.action-panel input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    setLocale('en-US')
    await flushPromises()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    try {
      await wrapper.get('.action-panel .primary-button').trigger('click')
      await flushPromises()
      expect(confirm).toHaveBeenCalledWith('TipRay-protected files cannot be previewed online, but downloads remain readable. Upload anyway?')
      expect(revise).not.toHaveBeenCalled()
    } finally {
      confirm.mockRestore()
      wrapper.unmount()
    }
  })

  it('translates loaded calendar events offline without refetching or losing the selected event', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const pinia = createPinia()
    useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
    const router = createAppRouter()
    await router.push('/calendar')
    const now = new Date()
    const date = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
    const [visits, requests, evaluations, pipeline] = await Promise.all([
      api.listVisits({ pageSize: 200 }), api.listDemoRequests({ pageSize: 200 }),
      api.listEvaluations({ pageSize: 200 }), api.listPipeline({}),
    ])
    const booking = { ...pipeline.data.bookings.find((item) => item.status !== 'Cancelled')!, ddl: date }
    const reads = [
      vi.spyOn(api, 'listVisits').mockResolvedValue({ ...visits, meta: { ...visits.meta, requestId: 'calendar-visits', total: 1 }, data: { items: [{ ...visits.data.items[0]!, date }] } }),
      vi.spyOn(api, 'listDemoRequests').mockResolvedValue({ ...requests, meta: { ...requests.meta, requestId: 'calendar-requests', total: 1 }, data: { items: [{ ...requests.data.items.find((item) => item.status !== 'Cancelled')!, customerExpectedDate: date }] } }),
      vi.spyOn(api, 'listEvaluations').mockResolvedValue({ ...evaluations, meta: { ...evaluations.meta, requestId: 'calendar-evaluations', total: 1 }, data: { items: [{ ...evaluations.data.items[0]!, testRunDeadline: date }] } }),
      vi.spyOn(api, 'listPipeline').mockResolvedValue({ ...pipeline, data: { ...pipeline.data, bookings: [booking] } }),
    ]
    const wrapper = mount(ServiceCalendarPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()
    await wrapper.get('.more-events').trigger('click')
    await wrapper.findAll('.day-agenda-list > button').find((button) => button.find('.booking').exists())!.trigger('click')
    expect(wrapper.get('.day-agenda-detail').text()).toContain(`${booking.quantity} 台`)
    for (const read of reads) read.mockRejectedValue(new Error('Offline'))

    setLocale('en-US')
    await flushPromises()
    expect(wrapper.find('.calendar-state.error').exists()).toBe(false)
    expect(wrapper.findAll('.day-agenda-list > button')).toHaveLength(4)
    expect(wrapper.get('.day-agenda-list').text()).toContain('Customer expected')
    expect(wrapper.get('.day-agenda-detail').text()).toContain(`${booking.quantity} units`)
    expect(wrapper.get('.day-agenda-list > button.active').text()).toContain(booking.id)

    setLocale('zh-CN')
    await flushPromises()
    expect(wrapper.get('.day-agenda-detail').text()).toContain(`${booking.quantity} 台`)
    expect(wrapper.get('.day-agenda-list > button.active').text()).toContain(booking.id)
    for (const read of reads) expect(read).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('translates the shared data timestamp when the dashboard language changes', async () => {
    const updatedAt = '2026-09-07T08:00:00Z'
    const wrapper = mount(PageHeader, { props: { title: 'Dashboard', description: '', updatedAt } })
    expect(wrapper.get('small').text()).toBe(`数据截至 ${formatDisplayDate(updatedAt)}`)
    setLocale('en-US')
    await flushPromises()
    expect(wrapper.get('small').text()).toBe(`Data as of ${formatDisplayDate(updatedAt)}`)
    wrapper.unmount()
  })

  it('updates an existing validation error without changing the deadline draft', async () => {
    const api = createMockApi({ latency: 0 })
    const evaluation = (await api.listEvaluations({ pageSize: 1 })).data.items[0]!
    const wrapper = mount(TestDeadlineModal, { props: { evaluation } })
    await wrapper.get('input').setValue('')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.get('[role="alert"]').text()).toBe('请输入有效日期')
    setLocale('en-US')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('Enter a valid date')
    expect((wrapper.get('input').element as HTMLInputElement).value).toBe('')
    await wrapper.get('input').setValue('2026-10-12')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.emitted('submit')?.[0]).toEqual([{ testRunDeadline: '2026-10-12' }])
    wrapper.unmount()
  })

  it('translates shared refresh actions and empty pipeline columns', async () => {
    const notice = mount(DataNotice, { props: { message: 'API warning' } })
    const column = mount(PipelineStageColumn, { props: { label: 'Pipeline', count: 0 } })
    setLocale('en-US')
    await flushPromises()
    expect(notice.get('button').text()).toBe('Refresh now')
    expect(column.get('p').text()).toBe('No records in this stage')
    await notice.get('button').trigger('click')
    expect(notice.emitted('refresh')).toHaveLength(1)
    await column.setProps({ emptyCopy: 'Custom empty message' })
    expect(column.get('p').text()).toBe('Custom empty message')
    notice.unmount()
    column.unmount()
  })
})
