import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CrmApi } from '@/api'
import { setLocale } from '@/i18n'
import QuotationPlanningPanel from './QuotationPlanningPanel.vue'
import type { QuotationPlanning } from './types'

beforeEach(() => setLocale('zh-CN'))
const initial = (): QuotationPlanning => ({ quotationId: 'q', modified: 'v1', plannedSendDate: null, followUps: [] })
function context() {
  const data = initial()
  const api = {
    getQuotationPlanning: vi.fn(async () => ({ data: structuredClone(data), warnings: [], meta: { requestId: 'read' } })),
    saveQuotationSchedule: vi.fn(async (_id, input) => ({ data: { ...data, ...input, modified: 'v2' }, warnings: [], meta: { requestId: 'schedule' } })),
    saveQuotationFollowUp: vi.fn(async (_id, input) => ({ data: { ...data, modified: 'v3', followUps: [{ ...input, id: 'f', completedAt: null, completedVersion: null }] }, warnings: [], meta: { requestId: 'followup' } })),
  }
  const wrapper = mount(QuotationPlanningPanel, { props: { quotationId: 'q', apiClient: api as unknown as CrmApi, canWrite: true } })
  return { api, wrapper }
}

describe('Quotation plans', () => {
  it('shows distinct Shanghai completion times for follow-ups completed on the same business day', async () => {
    const { api, wrapper } = context()
    api.getQuotationPlanning.mockResolvedValue({ data: { ...initial(), followUps: [
      { id: 'first', title: 'First', due: '2026-10-06', status: 'Done', note: '', completedAt: '2026-10-05T23:15:00Z', completedVersion: 'v1' },
      { id: 'second', title: 'Second', due: '2026-10-06', status: 'Done', note: '', completedAt: '2026-10-06T01:45:00Z', completedVersion: 'v1' },
    ] }, warnings: [], meta: { requestId: 'completion-times' } })
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.findAll('li small').map(row => row.text())).toEqual(['完成于 2026-10-06 07:15', '完成于 2026-10-06 09:45'])
    wrapper.unmount()
  })

  it('refreshes an open clean panel after the quotation changes and saves with the refreshed version', async () => {
    const { api, wrapper } = context()
    await wrapper.get('button').trigger('click'); await flushPromises()
    api.getQuotationPlanning.mockResolvedValue({ data: { ...initial(), modified: 'published' }, warnings: [], meta: { requestId: 'refresh' } })
    await wrapper.setProps({ quotationModified: 'published' }); await flushPromises()
    expect(api.getQuotationPlanning).toHaveBeenCalledTimes(2)
    await wrapper.get('header button').trigger('click')
    await wrapper.get('[data-followup-title]').setValue('After publishing')
    await wrapper.get('[data-followup-due]').setValue('2026-10-13')
    await wrapper.get('.followup-form').trigger('submit'); await flushPromises()
    expect(api.saveQuotationFollowUp).toHaveBeenCalledWith('q', expect.objectContaining({ title: 'After publishing' }), undefined, 'published')
    wrapper.unmount()
  })

  it('retains unsaved input on a parent change and requires an explicit reload', async () => {
    const { api, wrapper } = context()
    await wrapper.get('button').trigger('click'); await flushPromises()
    await wrapper.get('.send-plan input').setValue('2026-10-12')
    await wrapper.setProps({ quotationModified: 'external-save' }); await flushPromises()
    expect(api.getQuotationPlanning).toHaveBeenCalledTimes(1)
    expect((wrapper.get('.send-plan input').element as HTMLInputElement).value).toBe('2026-10-12')
    expect(wrapper.get('.send-plan button').attributes('disabled')).toBeDefined()
    await wrapper.get('.send-plan').trigger('submit'); await flushPromises()
    expect(api.saveQuotationSchedule).not.toHaveBeenCalled()
    await wrapper.get('[role=alert] button').trigger('click'); await flushPromises()
    expect(api.getQuotationPlanning).toHaveBeenCalledTimes(2)
    expect(wrapper.get('.send-plan button').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('loads on demand and uses the new quotation version when saving a follow-up after the send date', async () => {
    const { api, wrapper } = context()
    expect(api.getQuotationPlanning).not.toHaveBeenCalled()
    await wrapper.get('button').trigger('click'); await flushPromises()
    await wrapper.get('.send-plan input').setValue('2026-10-12')
    expect(wrapper.get('header button').attributes('disabled')).toBeDefined()
    await wrapper.get('.send-plan').trigger('submit'); await flushPromises()
    expect(api.saveQuotationSchedule).toHaveBeenCalledWith('q', { plannedSendDate: '2026-10-12' }, 'v1')
    await wrapper.get('header button').trigger('click')
    await wrapper.get('[data-followup-title]').setValue('Confirm scope')
    await wrapper.get('[data-followup-due]').setValue('2026-10-13')
    await wrapper.get('.followup-form').trigger('submit'); await flushPromises()
    expect(api.saveQuotationFollowUp).toHaveBeenCalledWith('q', { title: 'Confirm scope', due: '2026-10-13', status: 'Open', note: '' }, undefined, 'v2')
    expect(wrapper.find('.followup-form').exists()).toBe(false)
    expect(wrapper.get('li').text()).toContain('Confirm scope')
    wrapper.unmount()
  })

  it('keeps a failed follow-up draft until the user explicitly reloads', async () => {
    const { api, wrapper } = context()
    api.saveQuotationFollowUp.mockRejectedValue(new Error('Quotation changed'))
    await wrapper.get('button').trigger('click'); await flushPromises()
    await wrapper.get('header button').trigger('click')
    await wrapper.get('[data-followup-title]').setValue('Retain this note')
    await wrapper.get('[data-followup-due]').setValue('2026-10-13')
    await wrapper.get('[data-followup-status]').setValue('Done')
    await wrapper.get('.followup-form').trigger('submit'); await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain('Quotation changed')
    expect((wrapper.get('[data-followup-title]').element as HTMLInputElement).value).toBe('Retain this note')
    expect(api.getQuotationPlanning).toHaveBeenCalledTimes(1)
    await wrapper.get('[role=alert] button').trigger('click'); await flushPromises()
    expect(wrapper.find('.followup-form').exists()).toBe(false)
    expect(api.getQuotationPlanning).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('does not expose write controls to a reader', async () => {
    const { wrapper } = context()
    await wrapper.setProps({ canWrite: false })
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.find('header button').exists()).toBe(false)
    wrapper.unmount()
  })
})
