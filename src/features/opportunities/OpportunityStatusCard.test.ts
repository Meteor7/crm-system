import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { CrmApiError } from '@/api'
import { createMockApi } from '@/api/mock-adapter'
import { setLocale, useI18n } from '@/i18n'
import OpportunityStatusCard from './OpportunityStatusCard.vue'

beforeEach(() => setLocale('zh-CN'))
afterEach(() => { vi.restoreAllMocks(); document.body.innerHTML = '' })
function mountCard(api = createMockApi({ latency: 0 }), canWrite = true) {
  return mount(OpportunityStatusCard, { props: { opportunityId: 'OPP-001', apiClient: api, canWrite }, global: { stubs: { Teleport: true } } })
}
describe('Opportunity Status', () => {
  it('saves text and multiple files together and retains attachments when editing', async () => {
    const api = createMockApi({ latency: 0 })
    const save = vi.spyOn(api, 'saveOpportunityStatus')
    const wrapper = mountCard(api)
    await flushPromises()
    await wrapper.get('[data-testid="new-status"]').trigger('click')
    await wrapper.get('textarea').setValue('客户需求已确认\n等待样品')
    const files = [new File(['scope'], '规格.txt', { type: 'text/plain' }), new File(['notes'], '会议.txt', { type: 'text/plain' })]
    Object.defineProperty(wrapper.get('input[type="file"]').element, 'files', { value: files, configurable: true })
    await wrapper.get('input[type="file"]').trigger('change')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(save).toHaveBeenCalledWith('OPP-001', { text: '客户需求已确认\n等待样品', retainedFileIds: [] }, expect.arrayContaining([expect.objectContaining({ fileName: '规格.txt', blob: files[0] })]))
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('.status-information').text()).toContain('客户需求已确认')
    expect(wrapper.findAll('.status-file')).toHaveLength(2)
    await wrapper.get('[aria-label="编辑 Status 记录"]').trigger('click')
    await wrapper.get('textarea').setValue('已收到样品')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.findAll('.status-record')).toHaveLength(1)
    expect(wrapper.findAll('.status-file')).toHaveLength(2)
    expect(save.mock.calls[1][1].retainedFileIds).toHaveLength(2)
    const refreshed = mountCard(api)
    await flushPromises()
    expect(refreshed.text()).toContain('已收到样品')
    wrapper.unmount(); refreshed.unmount()
  })
  it('keeps the draft and files on failure, and cancel never saves', async () => {
    const api = createMockApi({ latency: 0 })
    const save = vi.spyOn(api, 'saveOpportunityStatus').mockRejectedValueOnce(new Error('unavailable'))
    const wrapper = mountCard(api)
    await flushPromises()
    await wrapper.get('[data-testid="new-status"]').trigger('click')
    await wrapper.get('textarea').setValue('保留草稿')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('textarea').element.value).toBe('保留草稿')
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    await wrapper.get('.secondary-button').trigger('click')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(save).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
  it('keeps Status named identically in both languages and hides editing for readers', async () => {
    const wrapper = mountCard(undefined, false)
    await flushPromises()
    expect(wrapper.get('h2').text()).toBe('Status')
    expect(wrapper.find('[data-testid="new-status"]').exists()).toBe(false)
    setLocale('en-US'); await flushPromises()
    expect(wrapper.get('h2').text()).toBe('Status')
    wrapper.unmount()
  })
  it('rejects empty information and too many attachments without saving', async () => {
    const api = createMockApi({ latency: 0 })
    const save = vi.spyOn(api, 'saveOpportunityStatus')
    const wrapper = mountCard(api)
    await flushPromises(); await wrapper.get('[data-testid="new-status"]').trigger('click')
    await wrapper.get('textarea').setValue('   ')
    await wrapper.get('form').trigger('submit')
    expect(save).not.toHaveBeenCalled()
    Object.defineProperty(wrapper.get('input[type="file"]').element, 'files', { value: Array.from({ length: 11 }, (_, i) => new File(['x'], `${i}.txt`)) })
    await wrapper.get('input[type="file"]').trigger('change')
    expect(wrapper.get('[role="alert"]').text()).toContain('10')
    expect(wrapper.findAll('.draft-file')).toHaveLength(0)
    wrapper.unmount()
  })
})
describe('Status upload format compatibility', () => {
  it.each(['a'.repeat(136) + '.txt', '文'.repeat(136) + '.txt', '📄' + 'a'.repeat(135) + '.txt'])('accepts a 140-character filename: %s', async (name) => {
    const wrapper = mountCard()
    await flushPromises()
    await wrapper.get('[data-testid="new-status"]').trigger('click')
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [new File(['text'], name, { type: 'text/plain' })] })
    await input.trigger('change')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.get('.draft-file').text()).toContain(name)
    wrapper.unmount()
  })
  it.each([141, 180])('rejects a %i-character filename and keeps the draft and selected files', async (length) => {
    const api = createMockApi({ latency: 0 })
    const save = vi.spyOn(api, 'saveOpportunityStatus')
    const wrapper = mountCard(api)
    await flushPromises()
    await wrapper.get('[data-testid="new-status"]').trigger('click')
    await wrapper.get('textarea').setValue('保留草稿')
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [new File(['text'], 'keep.txt')], configurable: true })
    await input.trigger('change')
    Object.defineProperty(input.element, 'files', { value: [new File(['text'], 'a'.repeat(length - 4) + '.txt')] })
    await input.trigger('change')
    expect(wrapper.get('[role="alert"]').text()).toContain('文件名（含扩展名）最多 140 个字符')
    expect(wrapper.get('textarea').element.value).toBe('保留草稿')
    expect(wrapper.findAll('.draft-file')).toHaveLength(1)
    expect(wrapper.get('.draft-file').text()).toContain('keep.txt')
    expect(save).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it.each(['doc', 'xls', 'ppt'])('rejects legacy .%s files before upload and explains conversion', async (extension) => {
    const api = createMockApi({ latency: 0 })
    const wrapper = mountCard(api)
    await flushPromises()
    await wrapper.get('[data-testid="new-status"]').trigger('click')
    const input = wrapper.get('input[type="file"]')
    expect(input.attributes('accept')!.split(',')).not.toContain('.' + extension)
    Object.defineProperty(input.element, 'files', { value: [new File(['legacy'], 'report.' + extension)] })
    await input.trigger('change')
    expect(wrapper.get('[role="alert"]').text()).toContain('DOCX、XLSX 或 PPTX')
    expect(wrapper.findAll('.draft-file')).toHaveLength(0)
    wrapper.unmount()
  })
  it('sends a CSV selected with an Excel MIME type as text/csv', async () => {
    const api = createMockApi({ latency: 0 })
    const save = vi.spyOn(api, 'saveOpportunityStatus')
    const wrapper = mountCard(api)
    await flushPromises()
    await wrapper.get('[data-testid="new-status"]').trigger('click')
    await wrapper.get('textarea').setValue('Measurement results')
    const file = new File(['wafer,value\n1,2'], 'measurements.csv', { type: 'application/vnd.ms-excel' })
    Object.defineProperty(wrapper.get('input[type="file"]').element, 'files', { value: [file] })
    await wrapper.get('input[type="file"]').trigger('change')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(save.mock.calls[0][2][0]).toMatchObject({ fileName: file.name, mimeType: 'text/csv' })
    expect(wrapper.findAll('.status-file')).toHaveLength(1)
    wrapper.unmount()
  })
})

describe('Status attachment download', () => {
  it('downloads through the scoped endpoint and surfaces a refusal instead of a file', async () => {
    const api = createMockApi({ latency: 0 })
    const record = {
      id: 'STATUS-1', text: '已确认', files: [{ id: 'SA-1', fileName: 'meeting.txt', mimeType: 'text/plain', size: 12 }],
      updatedAt: '2026-09-21T10:00:00+08:00', updatedBy: 'sales-lin', modified: '2026-09-21 10:00:00',
    }
    vi.spyOn(api, 'listOpportunityStatuses').mockResolvedValue({ data: [record] } as never)
    const fetched = vi.spyOn(api, 'getOpportunityStatusFile').mockResolvedValue(
      { blob: new Blob(['hello']), fileName: 'meeting.txt' } as never,
    )
    const saved = vi.spyOn(await import('@/features/shared/download-blob'), 'downloadBlob').mockImplementation(() => {})

    const wrapper = mountCard(api)
    await flushPromises()
    await wrapper.get('.status-file').trigger('click')
    await flushPromises()

    // The card must go through the audited endpoint, never at a file URL itself.
    expect(fetched).toHaveBeenCalledWith('OPP-001', 'STATUS-1', 'SA-1')
    expect(saved).toHaveBeenCalledTimes(1)
    expect(saved.mock.calls[0][1]).toBe('meeting.txt')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)

    // A removed attachment: the server refuses, and the card says so rather than
    // saving an error page as if it were the file.
    saved.mockClear()
    fetched.mockRejectedValueOnce(new CrmApiError('NOT_FOUND', '附件不存在', 'req-1', false))
    await wrapper.get('.status-file').trigger('click')
    await flushPromises()
    expect(saved).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('附件不存在')
    wrapper.unmount()
  })
})
