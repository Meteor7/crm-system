import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { setLocale } from '@/i18n'
import DocumentCenterPage from './DocumentCenterPage.vue'

vi.mock('@/api', async (importOriginal) => ({ ...await importOriginal<typeof import('@/api')>(), usingMock: false }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }) }))
vi.mock('@/features/shared/download-blob', () => ({ downloadBlob: vi.fn() }))
enableAutoUnmount(afterEach)

describe('Document Center live translation boundaries', () => {
  it('translates a rejected controlled preview and download without fetching again', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Manager' })
    const invalid = { blob: new Blob(['invalid']), mimeType: 'text/plain', fileName: 'invalid.txt' }
    const preview = vi.spyOn(apiClient, 'previewControlledDocument').mockResolvedValue(invalid)
    const download = vi.spyOn(apiClient, 'downloadControlledDocument').mockResolvedValue(invalid)
    const wrapper = mount(DocumentCenterPage, { props: { apiClient } })
    await flushPromises()
    expect(wrapper.text()).toContain('服务端未返回有效的受控 PDF')
    await wrapper.get('[data-controlled-download]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('服务端返回的受控文件类型不正确')
    setLocale('en-US')
    await flushPromises()
    expect(wrapper.text()).toContain('The server did not return a valid controlled PDF.')
    expect(wrapper.text()).toContain('The server returned an invalid controlled file type.')
    expect(preview).toHaveBeenCalledTimes(1)
    expect(download).toHaveBeenCalledTimes(1)
  })

  it('keeps upload selections and business content stable when their labels change', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Sales' })
    const submit = vi.spyOn(apiClient, 'submitControlledDocumentUpload').mockRejectedValue(new Error('backend 原始错误'))
    const wrapper = mount(DocumentCenterPage, { props: { apiClient } })
    await flushPromises()
    await wrapper.get('[data-upload-document]').trigger('click')
    const form = wrapper.get('[data-upload-modal] form')
    const inputs = form.findAll('input')
    await inputs[0].setValue('中文客户文件')
    await inputs[1].setValue('客户手册')
    const selects = form.findAll('select')
    await selects[0].setValue('Commercial')
    await selects[1].setValue('Direct')
    await selects[2].setValue('Restricted')
    const file = form.get('input[type="file"]')
    Object.defineProperty(file.element, 'files', { value: [new File(['data'], '客户手册.pdf', { type: 'application/pdf' })] })
    await file.trigger('change')
    expect(selects[2].text()).toContain('受限')
    setLocale('en-US')
    await flushPromises()
    expect(selects[2].text()).toContain('Restricted')
    await form.trigger('submit')
    await flushPromises()
    expect(submit).toHaveBeenCalledWith(expect.objectContaining({ title: '中文客户文件', documentType: '客户手册', category: 'Commercial', accessMode: 'Direct', confidentiality: 'Restricted' }), expect.objectContaining({ fileName: '客户手册.pdf' }))
    expect(wrapper.text()).toContain('backend 原始错误')
  })
})
