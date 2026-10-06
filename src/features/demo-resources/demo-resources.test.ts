import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createAppRouter } from '@/app/router'
import { createMockApi } from '@/api/mock-adapter'
import { CrmApiError } from '@/api/contracts'
import { createFrappeApi } from '@/api/frappe-adapter'
import { setLocale } from '@/i18n'
import { useAppStore } from '@/stores/app'
import DemoResourcesPage from '@/pages/DemoResourcesPage.vue'
import DemoResourceSchedulePanel from './DemoResourceSchedulePanel.vue'
import { resourceDateTime, shanghaiInput, shanghaiTimestamp, type DemoResourceSchedule } from './types'

const meta = { requestId: 'resource-test', generatedAt: '' }
const ok = <T,>(data: T) => ({ data, meta, warnings: [] })
const machine = { id: 'M-1', code: 'SERIAL-1', title: 'Machine one', platform: 'Inspection', maintainer: 'engineer', enabled: true, modified: 'v1', canMaintain: true }
const schedule = (): DemoResourceSchedule => ({ evaluationId: 'E-1', resourceId: 'M-1', start: '2030-10-01T02:00:00Z', end: '2030-10-01T04:00:00Z', modified: 'e1', canWrite: true, state: 'available', impacts: [], history: [] })
beforeEach(() => setLocale('zh-CN'))

async function setup(panel = false, role: 'Manager' | 'Sales' = 'Manager') {
  const api = createMockApi({ role, latency: 0 })
  api.getDemoResources = vi.fn(async () => ok({ resources: [{ ...machine, canMaintain: role === 'Manager' }], maintainers: [{ id: 'engineer', name: 'Engineer' }] }))
  api.getDemoUnavailability = vi.fn(async () => ok([{ id: 'U-1', resourceId: 'M-1', start: '2030-10-01T03:00:00Z', end: '2030-10-01T05:00:00Z', reason: 'Maintenance', status: 'Active' as const, modified: 'u1' }]))
  api.saveDemoUnavailability = vi.fn(async (id, input) => ok({ ...input, id: 'U-1', resourceId: id, modified: 'u2' }))
  api.getDemoResourceSchedule = vi.fn(async () => ok({ ...schedule(), canWrite: role === 'Manager' }))
  api.saveDemoResourceSchedule = vi.fn(async (_id, input) => ok({ ...schedule(), ...input, modified: 'e2' }))
  const pinia = createPinia(), router = createAppRouter()
  await router.push('/demo-resources'); await router.isReady()
  const wrapper = panel
    ? mount(DemoResourceSchedulePanel, { props: { evaluationId: 'E-1', apiClient: api, refreshToken: 'e1' }, global: { plugins: [pinia, router] } })
    : mount(DemoResourcesPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
  await flushPromises()
  return { wrapper, api, app: useAppStore(pinia) }
}

describe('Demo equipment and availability', () => {
  it('refreshes availability on reopen even when the Evaluation version is unchanged', async () => {
    const { wrapper, api } = await setup(true)
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.get('[data-resource-state]').text()).toContain('未与已记录')
    await wrapper.get('button').trigger('click')
    vi.mocked(api.getDemoResourceSchedule).mockResolvedValueOnce(ok({ ...schedule(), state: 'blocked' }))
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(api.getDemoResourceSchedule).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[data-resource-state]').text()).toContain('安排与设备不可用时间相交')
    wrapper.unmount()
  })
  it('keeps unsaved input on reopen and requires a fresh load before saving', async () => {
    const { wrapper, api } = await setup(true)
    await wrapper.get('button').trigger('click'); await flushPromises()
    await wrapper.findAll('input')[0].setValue('2030-10-01T09:00')
    await wrapper.get('button').trigger('click'); await wrapper.get('button').trigger('click')
    expect(api.getDemoResourceSchedule).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[role="alert"]').text()).toContain('输入已保留')
    expect(wrapper.find('[data-resource-state]').exists()).toBe(false)
    expect((wrapper.findAll('input')[0].element as HTMLInputElement).value).toBe('2030-10-01T09:00')
    await wrapper.get('form').trigger('submit')
    expect(api.saveDemoResourceSchedule).not.toHaveBeenCalled()
    await wrapper.get('[role="alert"] button').trigger('click'); await flushPromises()
    expect(api.getDemoResourceSchedule).toHaveBeenCalledTimes(2)
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })
  it('lets a validation error be corrected without discarding the schedule draft', async () => {
    const { wrapper, api } = await setup(true)
    await wrapper.get('button').trigger('click'); await flushPromises()
    vi.mocked(api.saveDemoResourceSchedule).mockRejectedValueOnce(new CrmApiError('VALIDATION_ERROR', 'End must be later than start.', 'bad-date'))
    await wrapper.findAll('input')[1].setValue('2030-10-01T09:00')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
    await wrapper.findAll('input')[1].setValue('2030-10-01T13:00')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.saveDemoResourceSchedule).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('uses explicit Shanghai time regardless of browser timezone', () => {
    expect(shanghaiInput('2030-10-01T02:00:00Z')).toBe('2030-10-01T10:00')
    expect(shanghaiTimestamp('2030-10-01T10:00')).toBe('2030-10-01T10:00:00+08:00')
    expect(resourceDateTime('2030-10-01T02:00:00Z')).toContain('2030-10-01 10:00')
  })
  it('loads schedules lazily and saves against the returned Evaluation version', async () => {
    const { wrapper, api } = await setup(true)
    expect(api.getDemoResourceSchedule).not.toHaveBeenCalled()
    await wrapper.get('button').trigger('click'); await flushPromises()
    const dates = wrapper.findAll('input[type="datetime-local"]')
    expect((dates[0].element as HTMLInputElement).value).toBe('2030-10-01T10:00')
    await dates[0].setValue('2030-10-01T09:30')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.saveDemoResourceSchedule).toHaveBeenCalledWith('E-1', { resourceId: 'M-1', start: '2030-10-01T09:30:00+08:00', end: '2030-10-01T12:00:00+08:00' }, 'e1')
    wrapper.unmount()
  })
  it('preserves dirty input and blocks saving when the Demo changes', async () => {
    const { wrapper, api } = await setup(true)
    await wrapper.get('button').trigger('click'); await flushPromises()
    await wrapper.findAll('input')[0].setValue('2030-10-01T09:00')
    await wrapper.setProps({ refreshToken: 'e3' })
    expect(wrapper.get('[role="alert"]').text()).toContain('输入已保留')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    await wrapper.get('form').trigger('submit')
    expect(api.saveDemoResourceSchedule).not.toHaveBeenCalled()
    expect((wrapper.findAll('input')[0].element as HTMLInputElement).value).toBe('2030-10-01T09:00')
    wrapper.unmount()
  })
  it('resolves an interval with its own CAS version and retains draft on conflict', async () => {
    const { wrapper, api } = await setup()
    await wrapper.get('[data-unavailable="U-1"] button').trigger('click')
    await wrapper.get('[data-interval-form] select').setValue('Resolved')
    api.saveDemoUnavailability = vi.fn().mockRejectedValue(new CrmApiError('VERSION_CONFLICT', 'Changed', 'test'))
    await wrapper.get('[data-interval-form]').trigger('submit'); await flushPromises()
    expect(api.saveDemoUnavailability).toHaveBeenCalledWith('M-1', { start: '2030-10-01T11:00:00+08:00', end: '2030-10-01T13:00:00+08:00', reason: 'Maintenance', status: 'Resolved' }, 'U-1', 'u1')
    expect((wrapper.get('[data-interval-form] select').element as HTMLSelectElement).value).toBe('Resolved')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
  it('keeps Sales read-only and clears maintenance editors after a role change', async () => {
    const { wrapper, app } = await setup()
    await wrapper.get('[data-edit-resource]').trigger('click')
    expect(wrapper.find('[data-resource-form]').exists()).toBe(true)
    app.bootstrap = { ...app.bootstrap!, user: { ...app.bootstrap!.user, role: 'Sales' } }
    await flushPromises()
    expect(wrapper.find('[data-resource-form]').exists()).toBe(false)
    expect(wrapper.find('[data-new-resource]').exists()).toBe(false)
    wrapper.unmount()
    const sales = await setup(true, 'Sales')
    await sales.wrapper.get('button').trigger('click'); await flushPromises()
    expect(sales.wrapper.find('form').exists()).toBe(false)
    expect(sales.wrapper.text()).toContain('10:00')
    sales.wrapper.unmount()
  })
  it('posts explicit resource identities and versions to the Frappe endpoints', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({ message: ok(schedule()) }), { headers: { 'Content-Type': 'application/json' } }))
    const api = createFrappeApi({ fetchImpl })
    const input = { resourceId: 'M-1', start: '2030-10-01T10:00:00+08:00', end: '2030-10-01T12:00:00+08:00' }
    await api.saveDemoResourceSchedule('E-1', input, 'version1')
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/method/rayher_crm.api.v1.demo_resources.save_demo_resource_schedule')
    expect(init.method).toBe('POST')
    expect(Object.fromEntries(new URLSearchParams(init.body as string))).toEqual({ evaluationId: 'E-1', input: JSON.stringify(input), expectedModified: 'version1' })
  })
})
