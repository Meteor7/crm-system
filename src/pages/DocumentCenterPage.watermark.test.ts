import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { CrmApi } from '@/api'
import type { ControlledDocumentDto } from '@/types/workspaces'
import DocumentCenterPage from './DocumentCenterPage.vue'

vi.mock('@/api', () => ({ api: {}, usingMock: false }))

async function mountApproval(hasPreview: boolean, documentMissing = false, role: 'Manager' | 'Sales' = 'Manager', deliveryMode: 'Original' | 'Watermarked' = 'Original') {
  const document: ControlledDocumentDto = {
    id: 'DOC-EXCEL', versionId: 'DOC-EXCEL-1.0-R1', title: 'Controlled spreadsheet',
    category: 'Technical', type: 'Technical document', product: 'General',
    version: '1.0', revision: 'R1', status: 'Released', confidentiality: 'Restricted',
    access: 'Request', hasPreview, canPreview: false, canDownload: true, deliveryMode,
    reviewDate: '', owner: 'Manager', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    size: 100, fileName: 'controlled.xlsx', versions: [], audit: [], applicableTool: '',
  }
  const request = {
    id: 'REQ-EXCEL', documentId: document.id, documentTitle: document.title,
    versionId: document.versionId, requester: 'sales@example.invalid', requesterName: 'Sales',
    requesterRole: 'Sales', reason: 'Customer review', status: 'Pending', deliveryMode: '',
    submittedAt: '2026-10-09 10:00:00', decidedBy: '', decidedAt: '',
  }
  const page = (items: unknown[]) => ({ data: { items }, meta: { total: items.length, page: 1, pageSize: 200 }, warnings: [] })
  const decide = vi.fn().mockResolvedValue({ data: { ...request, status: 'Approved', deliveryMode: 'Original' } })
  const download = vi.fn()
  const requestAccess = vi.fn().mockResolvedValue({ data: request })
  const apiClient = {
    getBootstrap: vi.fn().mockResolvedValue({ data: { user: { role, name: role, team: 'Management' } } }),
    listControlledDocuments: vi.fn().mockResolvedValue(page(documentMissing
      ? [{ ...document, id: 'DOC-OTHER', hasPreview: true }]
      : [document])),
    listControlledDocumentRequests: vi.fn().mockResolvedValue(page([request])),
    listControlledDocumentUploadRequests: vi.fn().mockResolvedValue(page([])),
    decideControlledDocumentRequest: decide,
    downloadControlledDocument: download,
    requestControlledDocumentAccess: requestAccess,
  } as unknown as CrmApi
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/document-center', component: DocumentCenterPage }] })
  await router.push('/document-center?workspace=approvals')
  const wrapper = mount(DocumentCenterPage, { props: { apiClient }, global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, decide, download, requestAccess }
}

describe('Document Center watermarked approval availability', () => {
  it.each([false, true])('blocks watermarked approval when the PDF source is unavailable (document missing: %s)', async (documentMissing) => {
    const { wrapper, decide } = await mountApproval(false, documentMissing)
    const watermarked = wrapper.get('[data-approval-action="approve-watermarked"]')
    expect(watermarked.attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-watermark-approval-help]').text()).toContain('该文档没有 PDF 预览，无法批准水印 PDF，请选择批准原件。')
    await watermarked.trigger('click')
    expect(decide).not.toHaveBeenCalled()
    const original = wrapper.get('[data-approval-action="approve-original"]')
    expect(original.attributes('disabled')).toBeUndefined()
    await original.trigger('click')
    await flushPromises()
    expect(decide).toHaveBeenCalledWith('REQ-EXCEL', 'approve-original', undefined)
    wrapper.unmount()
  })

  it('requires a new request instead of downloading an approved watermarked file without a PDF source', async () => {
    const { wrapper, download, requestAccess } = await mountApproval(false, false, 'Sales', 'Watermarked')
    expect(wrapper.find('[data-controlled-download]').exists()).toBe(false)
    expect(wrapper.get('[data-original-approval-required]').text()).toContain('请重新提交申请，由经理批准原件下载。')
    expect(wrapper.find('[data-access-request-form]').exists()).toBe(true)
    await wrapper.get('[data-access-reason]').setValue('Please approve the original spreadsheet')
    await wrapper.get('[data-access-request-form]').trigger('submit')
    await flushPromises()
    expect(requestAccess).toHaveBeenCalledWith('DOC-EXCEL-1.0-R1', 'Please approve the original spreadsheet')
    expect(wrapper.find('[data-access-request-form]').exists()).toBe(false)
    expect(wrapper.find('[data-controlled-download]').exists()).toBe(false)
    expect(download).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps an approved original download available without a PDF source', async () => {
    const { wrapper } = await mountApproval(false, false, 'Sales', 'Original')
    expect(wrapper.find('[data-controlled-download]').exists()).toBe(true)
    expect(wrapper.find('[data-original-approval-required]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('allows watermarked approval when a document has a PDF preview regardless of its original format', async () => {
    const { wrapper, decide } = await mountApproval(true)
    const watermarked = wrapper.get('[data-approval-action="approve-watermarked"]')
    expect(watermarked.attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[data-watermark-approval-help]').exists()).toBe(false)
    await watermarked.trigger('click')
    await flushPromises()
    expect(decide).toHaveBeenCalledWith('REQ-EXCEL', 'approve-watermarked', undefined)
    wrapper.unmount()
  })
})
