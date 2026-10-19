import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { CrmApiError } from '@/api/contracts'
import { setLocale } from '@/i18n'
import { planFixture } from './plan.fixture'
import type { CommitmentMetric, PlanCommitment, PlanDto } from './plan-types'
import PlanCommitmentsPanel from './PlanCommitmentsPanel.vue'

const meta = { requestId: 'commitment-test', generatedAt: '' }
const record: PlanCommitment = { id: 'promise', sales: 'alice', metric: 'visits', period: 'week', anchor: '2026-09-21', value: '5', note: 'Visit two fabs', modified: 'v1', modifiedBy: 'manager' }
function plan(): PlanDto {
  const data = planFixture()
  const activities = (['visits', 'leads', 'tests', 'quotes', 'followups', 'actions', 'events'] as CommitmentMetric[]).map(key => ({ key,
    scheduled: { state: 'ready' as const, value: 2 }, commitment: { state: 'ready' as const, value: '5', record: { ...record, metric: key } },
    target: { state: 'not_set' as const, value: null, record: null } }))
  data.commitments = { people: [{ id: 'alice', name: 'Alice', canEdit: true, activities }], team: activities, history: {}, allocated: true }
  return data
}
beforeEach(() => setLocale('zh-CN'))
describe('Plan commitments', () => {
  it('separates scheduled records, missing target and a saved zero promise with the exact version', async () => {
    const api = createMockApi({ role: 'Manager', latency: 0 })
    api.savePlanCommitment = vi.fn(async input => ({ data: { ...record, ...input, modified: 'v2' }, warnings: [], meta }))
    const wrapper = mount(PlanCommitmentsPanel, { props: { data: plan(), apiClient: api } })
    expect(wrapper.get('[data-commitment-owner="alice"]').text()).toContain('未设置')
    const scheduled = wrapper.get('[data-commitment-owner="alice"] td')
    expect(scheduled.text()).toBe('2')
    expect(scheduled.find('button, a, input').exists()).toBe(false)
    await wrapper.get('[data-commitment-edit]').trigger('click')
    await wrapper.get('[data-commitment-value]').setValue('0')
    await wrapper.get('textarea').setValue('Travel cancelled')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.savePlanCommitment).toHaveBeenCalledWith({ sales: 'alice', metric: 'visits', period: 'week', anchor: '2026-09-21', value: '0', note: 'Travel cancelled' }, 'v1')
    expect(wrapper.emitted('saved')).toHaveLength(1)
    wrapper.unmount()
  })
  it('keeps a conflicting draft and requires reopening the editor before another save', async () => {
    const api = createMockApi({ role: 'Manager', latency: 0 })
    api.savePlanCommitment = vi.fn().mockRejectedValue(new CrmApiError('VERSION_CONFLICT', 'Changed; reload', 'stale'))
    const wrapper = mount(PlanCommitmentsPanel, { props: { data: plan(), apiClient: api } })
    await wrapper.get('[data-commitment-edit]').trigger('click')
    await wrapper.get('[data-commitment-value]').setValue('8')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('Changed')
    expect((wrapper.get('[data-commitment-value]').element as HTMLInputElement).value).toBe('8')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    await wrapper.get('form').trigger('submit')
    expect(api.savePlanCommitment).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
  it('explains differing units and keeps scope-filtered promises read-only', async () => {
    const api = createMockApi({ role: 'Manager', latency: 0 }), data = plan()
    const wrapper = mount(PlanCommitmentsPanel, { props: { data, apiClient: api } })
    await wrapper.get('select').setValue('tests')
    expect(wrapper.text()).toContain('单位不同')
    await wrapper.get('select').setValue('quotes')
    expect(wrapper.text()).toContain('可能属于换版')
    const changed = plan()
    changed.commitments!.allocated = false; changed.commitments!.people[0].canEdit = false
    await wrapper.setProps({ data: changed })
    expect(wrapper.text()).toContain('清除这些筛选')
    expect(wrapper.find('[data-commitment-edit]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('reloads the plan after a stale owner and allows correcting editable validation errors', async () => {
    const api = createMockApi({ role: 'Manager', latency: 0 })
    api.savePlanCommitment = vi.fn()
      .mockRejectedValueOnce(new CrmApiError('VALIDATION_ERROR', 'Check the note', 'invalid'))
      .mockRejectedValueOnce(new CrmApiError('VERSION_CONFLICT', 'Sales rep role changed; reload', 'stale-owner'))
    const wrapper = mount(PlanCommitmentsPanel, { props: { data: plan(), apiClient: api } })
    await wrapper.get('[data-commitment-edit]').trigger('click')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[role="alert"] button').exists()).toBe(false)
    await wrapper.get('textarea').setValue('Corrected note')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[role="alert"] button').trigger('click')
    expect(wrapper.emitted('reload')).toHaveLength(1)
    expect(wrapper.find('form').exists()).toBe(false)
    expect(api.savePlanCommitment).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
  it('shows both preserved duplicate records and their audits without offering an ambiguous edit', () => {
    const api = createMockApi({ role: 'Manager', latency: 0 }), data = plan()
    data.commitments!.people[0].activities[0].commitment = {
      state: 'insufficient', value: null, record: null, reason: 'duplicate_targets',
      conflicts: [{ ...record, note: 'First preserved note' }, { ...record, id: 'second', value: '8', note: 'Second preserved note' }],
    }
    data.commitments!.history = {
      promise: [{ id: 'audit-1', actor: 'manager', at: '2026-09-22T12:00:00Z', changes: [['note', 'Previous first note', 'First preserved note']] }],
      second: [{ id: 'audit-2', actor: 'manager', at: '2026-09-22T12:00:00Z', changes: [['commitment_value', '6', '8']] }],
    }
    const wrapper = mount(PlanCommitmentsPanel, { props: { data, apiClient: api } })
    const row = wrapper.get('[data-commitment-owner="alice"]')
    expect(row.get('[data-commitment-conflict]').text()).toContain('演示员工170核对')
    expect(row.find('[data-commitment-edit]').exists()).toBe(false)
    const first = row.get('[data-commitment-record="promise"]'), second = row.get('[data-commitment-record="second"]')
    expect(first.text()).toContain('promise · 数量: 5')
    expect(first.text()).toContain('First preserved note')
    expect(first.get('details').text()).toContain('Previous first note')
    expect(second.text()).toContain('second · 数量: 8')
    expect(second.text()).toContain('Second preserved note')
    expect(second.get('details').text()).toContain('6 → 8')
    wrapper.unmount()
  })
  it.each([
    new CrmApiError('NETWORK_ERROR', 'Connection lost', 'network', true),
    new CrmApiError('INTERNAL_ERROR', 'Try again', 'server', true),
    new Error('Transport interrupted'),
  ])('preserves a transiently failed draft and retries it successfully: %s', async reason => {
    const api = createMockApi({ role: 'Manager', latency: 0 })
    api.savePlanCommitment = vi.fn().mockRejectedValueOnce(reason)
      .mockResolvedValueOnce({ data: { ...record, value: '8', note: 'Retain this meeting note' }, warnings: [], meta })
    const wrapper = mount(PlanCommitmentsPanel, { props: { data: plan(), apiClient: api } })
    await wrapper.get('[data-commitment-edit]').trigger('click')
    await wrapper.get('[data-commitment-value]').setValue('8')
    await wrapper.get('textarea').setValue('Retain this meeting note')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect((wrapper.get('[data-commitment-value]').element as HTMLInputElement).value).toBe('8')
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('Retain this meeting note')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[role="alert"] button').exists()).toBe(false)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.savePlanCommitment).toHaveBeenCalledTimes(2)
    expect(vi.mocked(api.savePlanCommitment).mock.calls[1]).toEqual(vi.mocked(api.savePlanCommitment).mock.calls[0])
    expect(wrapper.emitted('saved')).toHaveLength(1)
    expect(wrapper.find('form').exists()).toBe(false)
    wrapper.unmount()
  })
  it('keeps a refreshed draft stale when its pending request then has a transient failure', async () => {
    const api = createMockApi({ role: 'Manager', latency: 0 })
    let rejectSave!: (reason: unknown) => void
    api.savePlanCommitment = vi.fn(() => new Promise<never>((_resolve, reject) => { rejectSave = reject }))
    const wrapper = mount(PlanCommitmentsPanel, { props: { data: plan(), apiClient: api } })
    await wrapper.get('[data-commitment-edit]').trigger('click')
    await wrapper.get('form').trigger('submit')
    await wrapper.setProps({ data: plan() })
    rejectSave(new CrmApiError('NETWORK_ERROR', 'Connection lost', 'network', true))
    await flushPromises()
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[role="alert"] button').exists()).toBe(true)
    await wrapper.get('form').trigger('submit')
    expect(api.savePlanCommitment).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
})
