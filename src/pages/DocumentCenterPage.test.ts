import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import type { UserRole } from '@/types/crm'
import { createAppRouter } from '@/app/router'
import DocumentCenterPage from './DocumentCenterPage.vue'

async function mountPage(role: UserRole, seedRequest = false) {
  const apiClient = createMockApi({
    latency: 0,
    role,
    userName: role === 'Manager' ? '演示员工24' : role === 'Engineer' ? '演示员工14' : 'Demo Staff 01',
  })
  if (seedRequest) {
    await apiClient.requestControlledDocumentAccess(
      'DOC-ACONCA-FSBS-EDGE-0610-V2',
      'Customer technical review',
    )
  }
  const wrapper = mount(DocumentCenterPage, { props: { apiClient } })
  await flushPromises()
  return { wrapper, apiClient }
}

describe('DocumentCenterPage', () => {
  it('uses the shared CRM workspace visual grammar', async () => {
    const { wrapper } = await mountPage('Sales')

    expect(wrapper.get('.workspace-page').attributes('data-page')).toBe('document-center')
    expect(wrapper.get('.page-title-row').text()).toContain('Document Center')
    expect(wrapper.findAll('.workspace-panel').length).toBeGreaterThanOrEqual(2)
    expect(wrapper.find('.document-center-header').exists()).toBe(false)
    expect(wrapper.find('.role-card').exists()).toBe(false)
  })

  it('opens Manager on the complete document library with an approval-queue switch', async () => {
    const { wrapper } = await mountPage('Manager')

    expect(wrapper.find('.document-metrics').exists()).toBe(false)
    expect(wrapper.findAll('[data-document-row]')).toHaveLength(2)
    expect(wrapper.get('[data-workspace-tab="library"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.find('[data-workspace-tab="approvals"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-approval-action]')).toHaveLength(0)
  })

  it('opens the approval workspace from the registered query route', async () => {
    const router = createAppRouter()
    await router.push('/document-center?workspace=approvals')
    await router.isReady()
    const apiClient = createMockApi({ latency: 0, role: 'Manager' })
    const wrapper = mount(DocumentCenterPage, { props: { apiClient }, global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.get('[data-workspace-tab="approvals"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.find('[data-approval-workspace], [data-approval-empty]').exists()).toBe(true)
  })

  it('places the orange upload archive action in the page header and opens the upload modal', async () => {
    const { wrapper } = await mountPage('Sales')
    const action = wrapper.get('.page-title-row [data-upload-document]')

    expect(action.classes()).toContain('primary-button')
    expect(action.text()).toContain('上传档案')
    await action.trigger('click')
    expect(wrapper.find('[data-upload-modal]').exists()).toBe(true)
  })

  it('shows Manager a clean document view without personal watermark language', async () => {
    const { wrapper } = await mountPage('Manager')

    expect(wrapper.find('.pdf-watermark').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('个人水印')
    expect(wrapper.text()).not.toContain('下载水印 PDF')
    expect(wrapper.text()).toContain('无水印')
  })

  it('shows Manager an available original instead of restricted content when a document has no preview', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Manager' })
    const response = await apiClient.listControlledDocuments()
    response.data.items[0] = {
      ...response.data.items[0],
      hasPreview: false,
      canPreview: false,
      canDownload: true,
      deliveryMode: 'Original',
    }
    vi.spyOn(apiClient, 'listControlledDocuments').mockResolvedValue(response)

    const wrapper = mount(DocumentCenterPage, { props: { apiClient } })
    await flushPromises()

    expect(wrapper.find('[data-document-preview="original-only"]').exists()).toBe(true)
    expect(wrapper.find('[data-document-preview="locked"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('内容受限')
    expect(wrapper.find('[data-controlled-download]').exists()).toBe(true)
  })
  it.each(['Sales', 'Engineer', 'Manager'] as const)('shows %s the document upload action', async (role) => {
    const { wrapper } = await mountPage(role)
    expect(wrapper.find('[data-upload-document]').exists()).toBe(true)
  })

  it('keeps the upload action available when the released document library is empty', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Manager' })
    const emptyLibrary = await apiClient.listControlledDocuments()
    emptyLibrary.data.items = []
    vi.spyOn(apiClient, 'listControlledDocuments').mockResolvedValue(emptyLibrary)

    const wrapper = mount(DocumentCenterPage, { props: { apiClient } })
    await flushPromises()

    expect(wrapper.find('[data-upload-document]').exists()).toBe(true)
  })

  it('shows Sales only the Aconca and Nansi controlled presentations', async () => {
    const { wrapper } = await mountPage('Sales')

    expect(wrapper.findAll('[data-document-row]')).toHaveLength(2)
    expect(wrapper.text()).toContain('Aconca FS/BS Edge Technical Presentation')
    expect(wrapper.text()).toContain('Nansi Technical Presentation')
    expect(wrapper.text()).not.toContain('Mushi')
    expect(wrapper.find('[data-document-preview="locked"]').exists()).toBe(true)
    expect(wrapper.find('[data-controlled-download]').exists()).toBe(false)
    expect(wrapper.find('[data-approval-workspace]').exists()).toBe(false)
  })

  it('submits the literal access reason for Nansi and keeps it locked pending approval', async () => {
    const { wrapper, apiClient } = await mountPage('Sales')
    const requestAccess = vi.spyOn(apiClient, 'requestControlledDocumentAccess')

    await wrapper.get('[data-document-id="DOC-NANSI-0610"]').trigger('click')
    const reason = 'Customer Nansi technical presentation review'
    await wrapper.get('[data-access-reason]').setValue(reason)
    await wrapper.get('[data-access-request-form]').trigger('submit')
    await flushPromises()

    expect(requestAccess).toHaveBeenCalledWith('DOC-NANSI-0610-0610-V1', reason)
    expect(wrapper.get('[data-access-request-status]').text()).toContain('Manager Review')
    expect(wrapper.find('[data-document-preview="locked"]').exists()).toBe(true)
  })

  it('gives Manager both watermarked PDF and original PPTX approval choices', async () => {
    const { wrapper } = await mountPage('Manager', true)

    await wrapper.get('[data-workspace-tab="approvals"]').trigger('click')

    expect(wrapper.findAll('.request-card')).toHaveLength(1)
    expect(wrapper.text()).toContain('Aconca FS/BS Edge Technical Presentation')
    const actions = wrapper.findAll('[data-approval-action]')
    expect(actions).toHaveLength(4)
    expect(actions.every((action) => action.attributes('disabled') === undefined)).toBe(true)

    await wrapper.get('[data-approval-action="approve-original"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.request-card')).toHaveLength(0)
    expect(wrapper.get('[data-workspace-tab="approvals"] b').text()).toBe('0')
    expect(wrapper.text()).toContain('已批准')
  })

  it('keeps the released library visible when one approval queue fails to load', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Manager' })
    vi.spyOn(apiClient, 'listControlledDocumentRequests').mockRejectedValue(new Error('REQ-ACCESS-LOAD: access queue unavailable'))

    const wrapper = mount(DocumentCenterPage, { props: { apiClient } })
    await flushPromises()

    expect(wrapper.findAll('[data-document-row]')).toHaveLength(2)
    expect(wrapper.find('.document-state.is-error').exists()).toBe(false)
    await wrapper.get('[data-workspace-tab="approvals"]').trigger('click')
    expect(wrapper.get('[data-approval-load-error="access"]').text()).toContain('REQ-ACCESS-LOAD')
  })

  it('loads every document page instead of silently truncating the library at 200 rows', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Sales' })
    const seed = (await apiClient.listControlledDocuments()).data.items[0]!
    const documents = Array.from({ length: 201 }, (_, index) => ({
      ...seed,
      id: `DOC-PAGED-${String(index + 1).padStart(3, '0')}`,
      versionId: `DOC-PAGED-${String(index + 1).padStart(3, '0')}-V1`,
      title: `Paged controlled document ${index + 1}`,
    }))
    const listControlledDocuments = vi.spyOn(apiClient, 'listControlledDocuments').mockImplementation(async (query = {}) => {
      const page = query.page ?? 1
      const pageSize = query.pageSize ?? 20
      const start = (page - 1) * pageSize
      return {
        data: { items: documents.slice(start, start + pageSize) },
        meta: { requestId: `req-document-page-${page}`, total: documents.length, page, pageSize },
        warnings: [],
      }
    })

    const wrapper = mount(DocumentCenterPage, { props: { apiClient } })
    await flushPromises()

    expect(listControlledDocuments).toHaveBeenNthCalledWith(1, { page: 1, pageSize: 200 })
    expect(listControlledDocuments).toHaveBeenNthCalledWith(2, { page: 2, pageSize: 200 })
    expect(wrapper.findAll('[data-document-row]')).toHaveLength(201)
    expect(wrapper.text()).toContain('Paged controlled document 201')
  })
})
