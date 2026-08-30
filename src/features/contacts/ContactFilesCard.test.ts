import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import ContactFilesCard from './ContactFilesCard.vue'

describe('ContactFilesCard', () => {
  it('loads every attachment page instead of hiding files after row 200', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Sales' })
    const files = Array.from({ length: 201 }, (_, index) => ({
      id: `FILE-PAGED-${String(index + 1).padStart(3, '0')}`,
      contactId: 'CON-001',
      fileName: `contact-attachment-${index + 1}.pdf`,
      mimeType: 'application/pdf',
      size: 1024,
      uploadedAt: '2026-08-14T08:00:00+08:00',
      uploadedBy: 'person002@crm.example.invalid',
    }))
    const listContactFiles = vi.spyOn(apiClient, 'listContactFiles').mockImplementation(async (_id, query = {}) => {
      const page = query.page ?? 1
      const pageSize = query.pageSize ?? 20
      const start = (page - 1) * pageSize
      return {
        data: { items: files.slice(start, start + pageSize) },
        meta: { requestId: `req-contact-file-page-${page}`, total: files.length, page, pageSize },
        warnings: [],
      }
    })

    const wrapper = mount(ContactFilesCard, { props: { contactId: 'CON-001', apiClient } })
    await flushPromises()

    expect(listContactFiles).toHaveBeenNthCalledWith(1, 'CON-001', { page: 1, pageSize: 200 })
    expect(listContactFiles).toHaveBeenNthCalledWith(2, 'CON-001', { page: 2, pageSize: 200 })
    expect(wrapper.findAll('[data-file-id]')).toHaveLength(201)
    expect(wrapper.text()).toContain('contact-attachment-201.pdf')
  })
})
