import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import type { CrmApi } from '@/api/contracts'
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

  it('sends the note with a request for more information', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Manager' })
    await apiClient.requestControlledDocumentAccess('DOC-ACONCA-FSBS-EDGE-0610-V2', 'Customer technical review')
    const decide = vi.spyOn(apiClient, 'decideControlledDocumentRequest')
    const wrapper = mount(DocumentCenterPage, { props: { apiClient } })
    await flushPromises()
    await wrapper.get('[data-workspace-tab="approvals"]').trigger('click')
    await wrapper.get('[data-decision-note]').setValue('  Name the customer and the meeting  ')
    await wrapper.get('[data-approval-action="more-info"]').trigger('click')
    await flushPromises()
    expect(decide).toHaveBeenCalledWith(expect.any(String), 'more-info', 'Name the customer and the meeting')
    expect(wrapper.findAll('.request-card')).toHaveLength(0)
  })

  it('reads the library again after a download, so that the audit shows it', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Manager' })
    const listNow = apiClient.listControlledDocuments.bind(apiClient)
    let downloaded = false
    vi.spyOn(apiClient, 'listControlledDocuments').mockImplementation(async (query) => {
      const result = await listNow(query)
      // Read anew after the download, the document is at a later version and has the download in its audit.
      if (downloaded) result.data.items = result.data.items.map((item, index) => index === 0 ? { ...item, version: '9.9', audit: [{ id: 'AUDIT-NEW', employee: 'Controlled Manager', at: '2026-10-05T12:00:00', reason: 'Download without a request', version: `${item.id}-x` }] } : item)
      return result
    })
    const first = (await listNow({ page: 1, pageSize: 50 })).data.items[0]!
    const mimeType = first.deliveryMode === 'Original' ? first.mimeType : 'application/pdf'
    vi.spyOn(apiClient, 'downloadControlledDocument').mockImplementation(async () => { downloaded = true; return { blob: new Blob(['x'], { type: mimeType }), mimeType, fileName: 'x.bin' } })
    const preview = vi.spyOn(apiClient, 'previewControlledDocument').mockResolvedValue({ blob: new Blob(['%PDF-1.4'], { type: 'application/pdf' }), mimeType: 'application/pdf', fileName: 'p.pdf' })
    const createObjectURL = URL.createObjectURL
    URL.createObjectURL = vi.fn(() => 'blob:preview')
    const wrapper = mount(DocumentCenterPage, { props: { apiClient } })
    await flushPromises()
    expect(preview).toHaveBeenCalledTimes(1)
    const reads = (apiClient.listControlledDocuments as ReturnType<typeof vi.fn>).mock.calls.length
    expect(wrapper.text()).not.toContain('Controlled Manager')

    // The download's own row is in the audit once the download went through: the library was read again.
    await wrapper.get('[data-controlled-download]').trigger('click')
    await flushPromises()
    expect((apiClient.listControlledDocuments as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(reads)
    await wrapper.findAll('button').find((button) => button.text() === '下载审计')!.trigger('click')
    expect(wrapper.get('[data-download-audit]').text()).toContain('Controlled Manager')
    // The document at a later version now: its preview is loaded anew, not the old version's kept under the new title.
    expect(wrapper.text()).toContain('9.9')
    expect(preview).toHaveBeenCalledTimes(2)
    URL.createObjectURL = createObjectURL
  })

  it('shows a request submitted here whichever of its answer and a library read comes first', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Sales' })
    const listNow = apiClient.listControlledDocuments.bind(apiClient)
    const [a, b] = (await listNow({ page: 1, pageSize: 50 })).data.items
    const pending = { id: 'ACCESS-B', requester: 'person002@crm.example.invalid', requesterName: 'Demo Staff 01', requesterRole: 'Sales', documentId: b!.id, documentTitle: b!.title, versionId: b!.versionId, version: b!.version, revision: b!.revision, reason: 'Review', status: 'Pending' as const, deliveryMode: '' as const, submittedAt: '2026-10-05T10:00:00', decidedBy: '', decidedAt: '', decisionNote: '' }
    type Listed = Awaited<ReturnType<CrmApi['listControlledDocuments']>>
    // Every read of the library is answered by hand, with or without the request on B.
    const reads: Array<(withRequest: boolean) => void> = []
    vi.spyOn(apiClient, 'listControlledDocuments').mockImplementation((query) => new Promise<Listed>((resolve) => {
      reads.push(async (withRequest) => {
        const result = await listNow(query)
        result.data.items = result.data.items.map((item) => item.id === a!.id
          ? { ...item, canDownload: true, canPreview: false, deliveryMode: 'Original' as const }
          : item.id === b!.id ? { ...item, access: 'Request' as const, canDownload: false, canPreview: false, accessRequest: withRequest ? pending : null } : item)
        resolve(result)
      })
    }))
    type Requested = Awaited<ReturnType<CrmApi['requestControlledDocumentAccess']>>
    const submitSpy = vi.spyOn(apiClient, 'requestControlledDocumentAccess').mockResolvedValue({ data: pending, meta: { requestId: 'req-request' }, warnings: [] } as unknown as Requested)
    vi.spyOn(apiClient, 'downloadControlledDocument').mockResolvedValue({ blob: new Blob(['x'], { type: a!.mimeType }), mimeType: a!.mimeType, fileName: 'a.bin' })
    // The read out at the moment, answered (the page asks for the library after its microtasks).
    const answer = async (withRequest: boolean) => {
      await flushPromises()
      const read = reads.shift()
      if (!read) throw new Error('no read of the library is out')
      read(withRequest)
      await flushPromises()
    }
    const wrapper = mount(DocumentCenterPage, { props: { apiClient } })
    await answer(false)

    // A read begun by a download before the submit, still out when the submit is answered and the read the answer
    // starts lands: the old read, answered without the request after that, is stale and dropped.
    await wrapper.get('[data-controlled-download]').trigger('click')
    await flushPromises()
    expect(reads).toHaveLength(1)
    const stale = reads.shift()!
    await wrapper.get(`[data-document-id="${b!.id}"]`).trigger('click')
    await wrapper.get('[data-access-reason]').setValue('Customer technical review')
    await wrapper.get('[data-access-request-form]').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[data-access-request-status]').exists()).toBe(true)
    expect(reads).toHaveLength(1)
    await answer(true)
    expect(wrapper.find('[data-access-request-status]').exists()).toBe(true)
    stale(false)
    await flushPromises()
    expect(wrapper.find('[data-access-request-status]').exists()).toBe(true)

    // The other order: the submit's answer held; a download's read, begun after the submit and answered without
    // the request before the answer, then the answer: the request is shown, and the read the answer starts says so.
    await wrapper.get(`[data-document-id="${a!.id}"]`).trigger('click')
    await wrapper.get('[data-controlled-download]').trigger('click')
    await answer(false)
    await wrapper.get(`[data-document-id="${b!.id}"]`).trigger('click')
    expect(wrapper.find('[data-access-request-status]').exists()).toBe(false)
    let answerSubmit: (value: Requested) => void = () => undefined
    submitSpy.mockImplementation(() => new Promise<Requested>((resolve) => { answerSubmit = resolve }))
    await wrapper.get('[data-access-reason]').setValue('Customer technical review, again')
    await wrapper.get('[data-access-request-form]').trigger('submit')
    await wrapper.get(`[data-document-id="${a!.id}"]`).trigger('click')
    await wrapper.get('[data-controlled-download]').trigger('click')
    await answer(false)
    answerSubmit({ data: { ...pending, id: 'ACCESS-B-2', submittedAt: '2026-10-05T11:00:00' }, meta: { requestId: 'req-request-2' }, warnings: [] } as unknown as Requested)
    await flushPromises()
    await wrapper.get(`[data-document-id="${b!.id}"]`).trigger('click')
    expect(wrapper.find('[data-access-request-status]').exists()).toBe(true)
    expect(reads).toHaveLength(1)
    await answer(true)
    expect(wrapper.find('[data-access-request-status]').exists()).toBe(true)
  })

  it('keeps the preview when the library read anew changes only the audit', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Manager' })
    const listNow = apiClient.listControlledDocuments.bind(apiClient)
    let downloaded = false
    vi.spyOn(apiClient, 'listControlledDocuments').mockImplementation(async (query) => {
      const result = await listNow(query)
      if (downloaded) result.data.items = result.data.items.map((item, index) => index === 0 ? { ...item, audit: [{ id: 'AUDIT-NEW', employee: 'Controlled Manager', at: '2026-10-05T12:00:00', reason: 'Download without a request', version: `${item.id}-x` }] } : item)
      return result
    })
    const first = (await listNow({ page: 1, pageSize: 50 })).data.items[0]!
    const mimeType = first.deliveryMode === 'Original' ? first.mimeType : 'application/pdf'
    vi.spyOn(apiClient, 'downloadControlledDocument').mockImplementation(async () => { downloaded = true; return { blob: new Blob(['x'], { type: mimeType }), mimeType, fileName: 'x.bin' } })
    const preview = vi.spyOn(apiClient, 'previewControlledDocument').mockResolvedValue({ blob: new Blob(['%PDF-1.4'], { type: 'application/pdf' }), mimeType: 'application/pdf', fileName: 'p.pdf' })
    const createObjectURL = URL.createObjectURL
    URL.createObjectURL = vi.fn(() => 'blob:preview')
    const wrapper = mount(DocumentCenterPage, { props: { apiClient } })
    await flushPromises()
    expect(preview).toHaveBeenCalledTimes(1)

    // The same document at the same version, previewable as before, with a row more in its audit: the preview stays.
    await wrapper.get('[data-controlled-download]').trigger('click')
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '下载审计')!.trigger('click')
    expect(wrapper.get('[data-download-audit]').text()).toContain('Controlled Manager')
    expect(preview).toHaveBeenCalledTimes(1)
    URL.createObjectURL = createObjectURL
  })

  it('keeps a new download audit when a read the upload started is answered after it', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Manager' })
    const listNow = apiClient.listControlledDocuments.bind(apiClient)
    const first = (await listNow({ page: 1, pageSize: 50 })).data.items[0]!
    type Listed = Awaited<ReturnType<CrmApi['listControlledDocuments']>>
    const reads: Array<(withAudit: boolean) => void> = []
    vi.spyOn(apiClient, 'listControlledDocuments').mockImplementation((query) => new Promise<Listed>((resolve) => {
      reads.push(async (withAudit) => {
        const result = await listNow(query)
        if (withAudit) result.data.items = result.data.items.map((item, index) => index === 0 ? { ...item, audit: [{ id: 'AUDIT-NEW', employee: 'Controlled Manager', at: '2026-10-05T12:00:00', reason: 'Download without a request', version: `${item.id}-x` }] } : item)
        resolve(result)
      })
    }))
    const answer = async (withAudit: boolean) => {
      await flushPromises()
      const read = reads.shift()
      if (!read) throw new Error('no read of the library is out')
      read(withAudit)
      await flushPromises()
    }
    vi.spyOn(apiClient, 'submitControlledDocumentUpload').mockResolvedValue({ data: { id: 'UPL-1', status: 'Published' }, meta: { requestId: 'req-upload' }, warnings: [] } as unknown as Awaited<ReturnType<CrmApi['submitControlledDocumentUpload']>>)
    const mimeType = first.deliveryMode === 'Original' ? first.mimeType : 'application/pdf'
    vi.spyOn(apiClient, 'downloadControlledDocument').mockResolvedValue({ blob: new Blob(['x'], { type: mimeType }), mimeType, fileName: 'x.bin' })
    const wrapper = mount(DocumentCenterPage, { props: { apiClient } })
    await answer(false)

    // An upload published starts a read of the library; a download before that read is answered starts another,
    // answered first with the download in the audit; the upload's read, answered after, is dropped.
    await wrapper.get('[data-upload-document]').trigger('click')
    const form = wrapper.get('[data-upload-modal] form')
    const inputs = form.findAll('input')
    await inputs[0]!.setValue('Sequenced upload')
    await inputs[1]!.setValue('Manual')
    const file = form.get('input[type="file"]')
    Object.defineProperty(file.element, 'files', { value: [new File(['data'], 'manual.pdf', { type: 'application/pdf' })] })
    await file.trigger('change')
    await form.trigger('submit')
    await flushPromises()
    expect(reads).toHaveLength(1)
    const uploadRead = reads.shift()!
    await wrapper.get('[data-controlled-download]').trigger('click')
    await answer(true)
    await wrapper.findAll('button').find((button) => button.text() === '下载审计')!.trigger('click')
    expect(wrapper.get('[data-download-audit]').text()).toContain('Controlled Manager')
    uploadRead(false)
    await flushPromises()
    expect(wrapper.get('[data-download-audit]').text()).toContain('Controlled Manager')
  })

  it('reads the document of a request off the request when the Released library no longer lists it', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Manager' })
    const meta = { requestId: 'req-list', page: 1, pageSize: 50, total: 1 }
    vi.spyOn(apiClient, 'listControlledDocumentRequests').mockResolvedValue({ data: { items: [{
      id: 'ACCESS-SUPERSEDED', requester: 'person002@crm.example.invalid', requesterName: 'Demo Staff 01', requesterRole: 'Sales', documentId: 'DOC-SUPERSEDED', documentTitle: 'Superseded', versionId: 'DOC-SUPERSEDED-1.0-R1', version: '1.0', revision: 'R1', reason: 'Review', status: 'Pending', deliveryMode: '', submittedAt: '2026-10-05T10:00:00', decidedBy: '', decidedAt: '', decisionNote: '',
      documentConfidentiality: 'Internal', documentStatus: 'Superseded', documentAudit: [{ id: 'AUDIT-S', employee: 'Controlled Engineer', at: '2026-10-04T12:00:00', reason: 'Customer technical review', version: 'DOC-SUPERSEDED-1.0-R1' }],
    }] }, meta, warnings: [] })
    const wrapper = mount(DocumentCenterPage, { props: { apiClient } })
    await flushPromises()
    await wrapper.get('[data-workspace-tab="approvals"]').trigger('click')
    expect(wrapper.get('[data-approval-confidentiality]').text()).toBe('内部')
    expect(wrapper.text()).toContain('Controlled Engineer')
    // The version history is the version the request names, not empty and not that of another document.
    const history = wrapper.get('[data-version-history]')
    expect(history.text()).toContain('1 条')
    expect(history.text()).toContain('1.0 / R1')
  })

  it('leaves the library\'s word on a request submitted here when the submit is answered late', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Sales' })
    const listNow = apiClient.listControlledDocuments.bind(apiClient)
    const [a, b] = (await listNow({ page: 1, pageSize: 50 })).data.items
    let decided = false
    const pending = { id: 'ACCESS-B', requester: 'person002@crm.example.invalid', requesterName: 'Demo Staff 01', requesterRole: 'Sales', documentId: b!.id, documentTitle: b!.title, versionId: b!.versionId, version: b!.version, revision: b!.revision, reason: 'Review', status: 'Pending' as const, deliveryMode: '' as const, submittedAt: '2026-10-05T10:00:00', decidedBy: '', decidedAt: '', decisionNote: '' }
    // Decided meanwhile, and asked for again elsewhere and decided again: a newer request than the one answered late.
    const moreInfo = { ...pending, id: 'ACCESS-B-AGAIN', submittedAt: '2026-10-05T11:00:00', status: 'More Info Required' as const, decisionNote: 'Name the customer and the meeting' }
    vi.spyOn(apiClient, 'listControlledDocuments').mockImplementation(async (query) => {
      const result = await listNow(query)
      result.data.items = result.data.items.map((item) => item.id === a!.id
        ? { ...item, canDownload: true, canPreview: false, deliveryMode: 'Original' as const }
        : item.id === b!.id ? { ...item, access: 'Request' as const, canDownload: false, canPreview: false, accessRequest: decided ? moreInfo : null } : item)
      return result
    })
    type Requested = Awaited<ReturnType<CrmApi['requestControlledDocumentAccess']>>
    let answerSubmit: (value: Requested) => void = () => undefined
    vi.spyOn(apiClient, 'requestControlledDocumentAccess').mockImplementation(() => new Promise<Requested>((resolve) => { answerSubmit = resolve }))
    vi.spyOn(apiClient, 'downloadControlledDocument').mockImplementation(async () => { decided = true; return { blob: new Blob(['x'], { type: a!.mimeType }), mimeType: a!.mimeType, fileName: 'a.bin' } })
    const wrapper = mount(DocumentCenterPage, { props: { apiClient } })
    await flushPromises()

    // Submitted, the answer still out; the Manager decides meanwhile and another download reads the library anew.
    await wrapper.get(`[data-document-id="${b!.id}"]`).trigger('click')
    await wrapper.get('[data-access-reason]').setValue('Customer technical review')
    await wrapper.get('[data-access-request-form]').trigger('submit')
    await wrapper.get(`[data-document-id="${a!.id}"]`).trigger('click')
    await wrapper.get('[data-controlled-download]').trigger('click')
    await flushPromises()
    await wrapper.get(`[data-document-id="${b!.id}"]`).trigger('click')
    expect(wrapper.get('[data-access-request-decision]').text()).toContain('Name the customer and the meeting')

    // The submit's answer, late, and the read it starts failing: the library's word stands.
    vi.spyOn(apiClient, 'listControlledDocuments').mockImplementationOnce(() => Promise.reject(new Error('offline')))
    answerSubmit({ data: pending, meta: { requestId: 'req-request' }, warnings: [] } as unknown as Requested)
    await flushPromises()
    expect(wrapper.find('[data-access-request-status]').exists()).toBe(false)
    expect(wrapper.get('[data-access-request-decision]').text()).toContain('Name the customer and the meeting')
  })

  it('previews a document the library read anew lets the user preview', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Sales' })
    const listNow = apiClient.listControlledDocuments.bind(apiClient)
    const [a, b] = (await listNow({ page: 1, pageSize: 50 })).data.items
    let approved = false
    vi.spyOn(apiClient, 'listControlledDocuments').mockImplementation(async (query) => {
      const result = await listNow(query)
      result.data.items = result.data.items.map((item) => item.id === a!.id
        ? { ...item, canDownload: true, canPreview: false, deliveryMode: 'Original' as const }
        : item.id === b!.id ? { ...item, access: 'Request' as const, canDownload: approved, canPreview: approved, deliveryMode: approved ? 'Watermarked' as const : '' as const } : item)
      return result
    })
    let answerDownload: (value: { blob: Blob; mimeType: string; fileName: string }) => void = () => undefined
    vi.spyOn(apiClient, 'downloadControlledDocument').mockImplementation(() => new Promise((resolve) => { answerDownload = resolve }))
    const preview = vi.spyOn(apiClient, 'previewControlledDocument').mockResolvedValue({ blob: new Blob(['%PDF-1.4'], { type: 'application/pdf' }), mimeType: 'application/pdf', fileName: 'p.pdf' })
    const createObjectURL = URL.createObjectURL
    URL.createObjectURL = vi.fn(() => 'blob:preview')
    const wrapper = mount(DocumentCenterPage, { props: { apiClient } })
    await flushPromises()

    // The download of one document out, the other selected (no preview for it yet); approved meanwhile, the
    // library read anew after the download lets the user preview it: the preview is loaded, same version and all.
    await wrapper.get('[data-controlled-download]').trigger('click')
    await wrapper.get(`[data-document-id="${b!.id}"]`).trigger('click')
    await flushPromises()
    expect(preview).not.toHaveBeenCalled()
    approved = true
    answerDownload({ blob: new Blob(['x'], { type: a!.mimeType }), mimeType: a!.mimeType, fileName: 'a.bin' })
    await flushPromises()
    expect(preview).toHaveBeenCalledTimes(1)
    URL.createObjectURL = createObjectURL
  })

  it('shows the decision on a request submitted here once the library brings it back', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Sales' })
    const listNow = apiClient.listControlledDocuments.bind(apiClient)
    const [a, b] = (await listNow({ page: 1, pageSize: 50 })).data.items
    let phase: 'none' | 'pending' | 'more-info' = 'none'
    const pending = { id: 'ACCESS-B', requester: 'person002@crm.example.invalid', requesterName: 'Demo Staff 01', requesterRole: 'Sales', documentId: b!.id, documentTitle: b!.title, versionId: b!.versionId, version: b!.version, revision: b!.revision, reason: 'Review', status: 'Pending' as const, deliveryMode: '' as const, submittedAt: '2026-10-05T10:00:00', decidedBy: '', decidedAt: '', decisionNote: '' }
    const moreInfo = { ...pending, status: 'More Info Required' as const, decisionNote: 'Name the customer and the meeting' }
    vi.spyOn(apiClient, 'listControlledDocuments').mockImplementation(async (query) => {
      const result = await listNow(query)
      result.data.items = result.data.items.map((item) => item.id === a!.id
        ? { ...item, canDownload: true, canPreview: false, deliveryMode: 'Original' as const }
        : item.id === b!.id ? { ...item, access: 'Request' as const, canDownload: false, canPreview: false, accessRequest: phase === 'none' ? null : phase === 'pending' ? pending : moreInfo } : item)
      return result
    })
    vi.spyOn(apiClient, 'requestControlledDocumentAccess').mockImplementation(async () => { phase = 'pending'; return { data: pending, meta: { requestId: 'req-request' }, warnings: [] } as unknown as Awaited<ReturnType<CrmApi['requestControlledDocumentAccess']>> })
    vi.spyOn(apiClient, 'downloadControlledDocument').mockImplementation(async () => { phase = 'more-info'; return { blob: new Blob(['x'], { type: a!.mimeType }), mimeType: a!.mimeType, fileName: 'a.bin' } })
    const wrapper = mount(DocumentCenterPage, { props: { apiClient } })
    await flushPromises()

    // Submitted here: shown as under review.
    await wrapper.get(`[data-document-id="${b!.id}"]`).trigger('click')
    await wrapper.get('[data-access-reason]').setValue('Customer technical review')
    await wrapper.get('[data-access-request-form]').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[data-access-request-status]').exists()).toBe(true)

    // Another document downloaded, the library read anew: the Manager's answer is what the page shows.
    await wrapper.get(`[data-document-id="${a!.id}"]`).trigger('click')
    await wrapper.get('[data-controlled-download]').trigger('click')
    await flushPromises()
    await wrapper.get(`[data-document-id="${b!.id}"]`).trigger('click')
    expect(wrapper.find('[data-access-request-status]').exists()).toBe(false)
    expect(wrapper.get('[data-access-request-decision]').text()).toContain('Name the customer and the meeting')
  })

  it('shows the version and revision a request names, as the server gives them', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Manager' })
    const meta = { requestId: 'req-list', page: 1, pageSize: 50, total: 2 }
    const base = { requester: 'person002@crm.example.invalid', requesterName: 'Demo Staff 01', requesterRole: 'Sales', reason: 'Review', status: 'Pending' as const, deliveryMode: '' as const, submittedAt: '2026-10-05T10:00:00', decidedBy: '', decidedAt: '', decisionNote: '' }
    vi.spyOn(apiClient, 'listControlledDocumentRequests').mockResolvedValue({ data: { items: [
      // Named by the request itself, whatever the library says of the document now.
      { ...base, id: 'ACCESS-DASHED', documentId: 'DOC-ACONCA-FSBS-EDGE', documentTitle: 'Aconca', versionId: 'DOC-ACONCA-FSBS-EDGE-2026-Q4-R1', version: '2026-Q4', revision: 'R1' },
      // Older than the fields, its document gone from the library: read off the version id at its last dash.
      { ...base, id: 'ACCESS-OLD', documentId: 'DOC-GONE', documentTitle: 'Gone', versionId: 'DOC-GONE-2026-Q4-R1', submittedAt: '2026-10-04T10:00:00' },
      // Older than the fields, for a version its document has moved on from: its own, not the document's current one.
      { ...base, id: 'ACCESS-OLDER', documentId: 'DOC-ACONCA-FSBS-EDGE', documentTitle: 'Aconca', versionId: 'DOC-ACONCA-FSBS-EDGE-2025-Q1-R0', submittedAt: '2026-10-03T10:00:00' },
    ] }, meta, warnings: [] })
    const wrapper = mount(DocumentCenterPage, { props: { apiClient } })
    await flushPromises()
    await wrapper.get('[data-workspace-tab="approvals"]').trigger('click')
    const cards = wrapper.findAll('.request-card')
    expect(cards).toHaveLength(3)
    expect(wrapper.text()).toContain('DOC-ACONCA-FSBS-EDGE · 2026-Q4 / R1')
    await cards[1]!.trigger('click')
    // No revision is read off a version id (a revision may hold a dash of its own): the tail stands whole.
    expect(wrapper.text()).toContain('DOC-GONE · 2026-Q4-R1')
    expect(wrapper.text()).not.toContain('DOC-GONE · 2026-Q4 /')
    await cards[2]!.trigger('click')
    expect(wrapper.text()).toContain('DOC-ACONCA-FSBS-EDGE · 2025-Q1-R0')
  })

  it('lands a decision on the request it was made for while another is selected', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Manager' })
    await apiClient.requestControlledDocumentAccess('DOC-ACONCA-FSBS-EDGE-0610-V2', 'Customer technical review')
    await apiClient.requestControlledDocumentAccess('DOC-NANSI-0610-0610-V1', 'Internal training')
    const decideNow = apiClient.decideControlledDocumentRequest.bind(apiClient)
    type Decided = Awaited<ReturnType<typeof decideNow>>
    const held: { answer: (value: Decided) => void; args: Parameters<typeof decideNow> | null } = { answer: () => undefined, args: null }
    vi.spyOn(apiClient, 'decideControlledDocumentRequest').mockImplementation((...args) => new Promise<Decided>((resolve) => { held.answer = resolve; held.args = args }))
    const wrapper = mount(DocumentCenterPage, { props: { apiClient } })
    await flushPromises()
    await wrapper.get('[data-workspace-tab="approvals"]').trigger('click')
    const first = wrapper.findAll('.request-card')[0]!.text()

    // Asked for more on the first request; the second selected and a note typed for it while the answer is out.
    await wrapper.get('[data-decision-note]').setValue('Name the customer')
    await wrapper.get('[data-approval-action="more-info"]').trigger('click')
    await wrapper.findAll('.request-card')[1]!.trigger('click')
    await wrapper.get('[data-decision-note]').setValue('Note for the second')
    held.answer(await decideNow(...held.args!))
    await flushPromises()

    // The first request is decided and gone from the list; the second stays selected, undecided, with its note.
    expect(wrapper.findAll('.request-card')).toHaveLength(1)
    expect(wrapper.get('.request-card.active').text()).not.toBe(first)
    expect((wrapper.get('[data-decision-note]').element as HTMLTextAreaElement).value).toBe('Note for the second')
    expect(wrapper.get('[data-approval-action="more-info"]').attributes('disabled')).toBeUndefined()
  })

  it('starts the note afresh for another request', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Manager' })
    await apiClient.requestControlledDocumentAccess('DOC-ACONCA-FSBS-EDGE-0610-V2', 'Customer technical review')
    await apiClient.requestControlledDocumentAccess('DOC-NANSI-0610-0610-V1', 'Internal training')
    const decide = vi.spyOn(apiClient, 'decideControlledDocumentRequest')
    const wrapper = mount(DocumentCenterPage, { props: { apiClient } })
    await flushPromises()
    await wrapper.get('[data-workspace-tab="approvals"]').trigger('click')
    expect(wrapper.findAll('.request-card')).toHaveLength(2)
    await wrapper.get('[data-decision-note]').setValue('Only the first applicant should name its customer')
    await wrapper.findAll('.request-card')[1]!.trigger('click')
    // Typed for the first request, not sent for the second: the note is empty, and so the request for more information waits.
    expect((wrapper.get('[data-decision-note]').element as HTMLTextAreaElement).value).toBe('')
    await wrapper.get('[data-approval-action="more-info"]').trigger('click')
    await flushPromises()
    expect(decide).not.toHaveBeenCalled()
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
