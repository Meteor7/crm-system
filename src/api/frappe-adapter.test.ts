import { afterEach, describe, expect, it, vi } from 'vitest'
import { CrmApiError } from './contracts'
import { createFrappeApi, FRAPPE_METHODS } from './frappe-adapter'

function jsonResponse(payload: unknown, status = 200, headers: HeadersInit = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

function success<T>(data: T, meta = { requestId: 'req_test' }) {
  return jsonResponse({ message: { data, meta, warnings: [] } })
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  delete (window as Window & { frappe?: unknown }).frappe
})

describe('Frappe method contract', () => {
  it('freezes every CrmApi method to a rayher_crm v1 whitelist endpoint', () => {
    expect(FRAPPE_METHODS).toEqual({
      getBootstrap: 'bootstrap.get_bootstrap',
      changeCurrentUserPassword: 'account.change_password',
      listNotifications: 'notifications.list_notifications',
      markNotificationRead: 'notifications.mark_notification_read',
      markAllNotificationsRead: 'notifications.mark_all_notifications_read',
      getDashboard: 'dashboard.get_dashboard',
      listAccounts: 'accounts.list_accounts',
      listAccountSegments: 'accounts.list_account_segments',
      listAccountCities: 'accounts.list_account_cities',
      createAccount: 'accounts.create_account',
      updateAccount: 'accounts.update_account',
      deleteAccount: 'accounts.delete_account',
      getAccount360: 'accounts.get_account_360',
      createAccountSite: 'accounts.create_account_site',
      updateAccountSite: 'accounts.update_account_site',
      deleteAccountSite: 'accounts.delete_account_site',
      listVisits: 'visits.list_visits',
      getVisit: 'visits.get_visit',
      getVisitDetail: 'visits.get_visit_detail',
      createVisit: 'visits.create_visit',
      submitVisitRecord: 'visits.submit_visit_record',
      reviewVisit: 'visits.review_visit',
      updateVisit: 'visits.update_visit',
      updateVisitMeetingRecord: 'visits.update_meeting_record',
      getVisitAttachment: 'visits.download_attachment',
      listContacts: 'contacts.list_contacts',
      getContact: 'contacts.get_contact',
      createContact: 'contacts.create_contact',
      updateContact: 'contacts.update_contact',
      mergeContacts: 'contacts.merge_contacts',
      deleteContact: 'contacts.delete_contact',
      listContactFiles: 'contact_files.list_files',
      uploadContactFiles: 'contact_files.upload_files',
      getContactFile: 'contact_files.download_file',
      deleteContactFile: 'contact_files.delete_file',
      listLeads: 'leads.list_leads',
      getLead: 'leads.get_lead',
      createLead: 'leads.create_lead',
      updateLead: 'leads.update_lead',
      deleteLead: 'leads.delete_lead',
      convertLead: 'leads.convert_lead',
      listStakeholders: 'stakeholders.list_stakeholders',
      createStakeholder: 'stakeholders.create_stakeholder',
      updateStakeholder: 'stakeholders.update_stakeholder',
      listRequirements: 'read_only_views.list_requirements',
      listPipeline: 'pipeline.list_pipeline',
      listBookings: 'bookings.list_bookings',
      createBooking: 'bookings.create_booking',
      updateBooking: 'bookings.update_booking',
      deleteBooking: 'bookings.delete_booking',
      completeServiceBooking: 'bookings.complete_service_booking',
      listDemoRequests: 'demo_requests.list_demo_requests',
      importDemoRequestForm: 'demo_requests.import_form',
      createDemoRequest: 'demo_requests.create_demo_request',
      updateDemoRequest: 'demo_requests.update_demo_request',
      transitionDemoRequest: 'demo_requests.transition_demo_request',
      listEvaluations: 'evaluations.list_evaluations',
      getEvaluation: 'evaluations.get_evaluation',
      completeEvaluationPreparation: 'evaluations.complete_evaluation_preparation',
      updateEvaluationStatus: 'evaluations.update_evaluation_status',
      addEvaluationRun: 'evaluations.add_evaluation_run',
      setEvaluationTestRunDeadline: 'evaluations.set_evaluation_test_run_deadline',
      saveDemoArtifact: 'demo_artifacts.save_artifact',
      getDemoArtifact: 'demo_artifacts.download_artifact',
      releaseDemoTestReport: 'evaluations.release_demo_test_report',
      uploadCustomerReport: 'evaluations.upload_customer_report',
      listContracts: 'read_only_views.list_contracts',
      listQuotations: 'quotations.list_quotations',
      listQuotationCatalog: 'quotations.list_catalog',
  getQuotation: 'quotations.get_quotation',
  createQuotation: 'quotations.create_quotation',
  linkQuotationOpportunity: 'quotations.link_opportunity',
  saveQuotationDraft: 'quotations.save_draft',
  createQuotationVersion: 'quotations.create_version',
  discardQuotationDraft: 'quotations.discard_draft',
  publishQuotation: 'quotations.publish_version',
  submitQuotationForApproval: 'quotations.submit_for_approval',
  reviewQuotationApproval: 'quotations.review_approval',
  recordQuotationDecision: 'quotations.record_decision',
  getQuotationPreviewPdf: 'quotations.preview_pdf',
  getQuotationPdf: 'quotations.download_pdf',
      listRfqs: 'rfqs.list_rfqs',
      getRfq: 'rfqs.get_rfq',
      createRfq: 'rfqs.create_rfq',
      reviseRfq: 'rfqs.revise_rfq',
      submitRfqEngineerComment: 'rfqs.submit_engineer_comment',
      reviewRfq: 'rfqs.review_rfq',
      previewRfqFile: 'rfqs.preview_rfq_file',
      downloadRfqFile: 'rfqs.download_rfq_file',
      listStrategyOpportunities: 'opportunities.list_strategy_opportunities',
      getStrategyOpportunity: 'opportunities.get_strategy_opportunity',
      createStrategyOpportunity: 'opportunities.create_strategy_opportunity',
      updateStrategyOpportunity: 'opportunities.update_strategy_opportunity',
      rollbackOpportunityStage: 'opportunities.rollback_opportunity_stage',
      deleteStrategyOpportunity: 'opportunities.delete_strategy_opportunity',
      createOpportunityStakeholder: 'opportunities.create_opportunity_stakeholder',
      updateOpportunityStakeholder: 'opportunities.update_opportunity_stakeholder',
      deleteOpportunityStakeholder: 'opportunities.delete_opportunity_stakeholder',
      createOpportunityAction: 'opportunities.create_opportunity_action',
      updateOpportunityAction: 'opportunities.update_opportunity_action',
      deleteOpportunityAction: 'opportunities.delete_opportunity_action',
      listDemoWorkflows: 'evaluations.list_demo_workflows',
      getDemoWorkflow: 'evaluations.get_demo_workflow',
      listDemoComments: 'demo_requests.list_demo_comments',
      addDemoComment: 'demo_requests.add_demo_comment',
      listInstalledTools: 'installed_tools.list_installed_tools',
      getInstalledTool: 'installed_tools.get_installed_tool',
      convertBookingToInstalledTool: 'installed_tools.convert_booking_to_installed_tool',
      updateInstalledTool: 'installed_tools.update_installed_tool',
      transitionInstalledTool: 'installed_tools.transition_installed_tool',
      addInstalledToolVersionRecord: 'installed_tools.add_installed_tool_version_record',
      addInstalledToolServiceRecord: 'installed_tools.add_installed_tool_service_record',
      listControlledDocuments: 'read_only_views.list_controlled_documents',
      previewControlledDocument: 'controlled_documents.preview_document',
      downloadControlledDocument: 'controlled_documents.download_document',
      requestControlledDocumentAccess: 'read_only_views.request_controlled_document_access',
      listControlledDocumentRequests: 'read_only_views.list_controlled_document_requests',
      decideControlledDocumentRequest: 'read_only_views.decide_controlled_document_request',
      submitControlledDocumentUpload: 'document_uploads.submit_upload',
      listControlledDocumentUploadRequests: 'document_uploads.list_upload_requests',
      decideControlledDocumentUploadRequest: 'document_uploads.decide_upload_request',
    })
  })
})

describe('Frappe JSON transport', () => {
  it('posts stable ids to every Manager-only Sales delete endpoint', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(success({ id: 'deleted', status: 'Deleted' })))
    const api = createFrappeApi({ fetchImpl: fetchMock })

    await api.deleteAccount('ACC-DEL')
    await api.deleteLead('LEAD-DEL')
    await api.deleteStrategyOpportunity('OPP-DEL')
    await api.deleteBooking('BOOK-DEL')

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/method/rayher_crm.api.v1.accounts.delete_account',
      '/api/method/rayher_crm.api.v1.leads.delete_lead',
      '/api/method/rayher_crm.api.v1.opportunities.delete_strategy_opportunity',
      '/api/method/rayher_crm.api.v1.bookings.delete_booking',
    ])
    expect(fetchMock.mock.calls.map(([, init]) => new URLSearchParams(String(init.body)).get('id'))).toEqual([
      'ACC-DEL', 'LEAD-DEL', 'OPP-DEL', 'BOOK-DEL',
    ])
  })

  it('unwraps the Frappe message envelope and encodes defined GET query fields', async () => {
    const fetchMock = vi.fn().mockResolvedValue(success({ items: [{ id: 'ACC-1' }] }))
    const api = createFrappeApi({ fetchImpl: fetchMock })

    const result = await api.listAccounts({ search: '晶 圆', page: 2, pageSize: 20 })

    expect(result.data.items).toEqual([{ id: 'ACC-1' }])
    expect(fetchMock).toHaveBeenCalledOnce()
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/method/rayher_crm.api.v1.accounts.list_accounts?search=%E6%99%B6+%E5%9C%86&page=2&pageSize=20')
    expect(init).toMatchObject({ method: 'GET', credentials: 'same-origin' })
    expect(init.body).toBeUndefined()
  })

  it('loads the canonical account segments through the Frappe GET endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(success(['Frontend', 'Advanced Packaging']))
    const api = createFrappeApi({ fetchImpl: fetchMock })

    const result = await api.listAccountSegments()

    expect(result.data).toEqual(['Frontend', 'Advanced Packaging'])
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/method/rayher_crm.api.v1.accounts.list_account_segments')
    expect(init).toMatchObject({ method: 'GET', credentials: 'same-origin' })
  })

  it('loads account cities through the Frappe GET endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(success(['上海', '苏州']))
    const api = createFrappeApi({ fetchImpl: fetchMock })

    const result = await api.listAccountCities()

    expect(result.data).toEqual(['上海', '苏州'])
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/method/rayher_crm.api.v1.accounts.list_account_cities')
    expect(init).toMatchObject({ method: 'GET', credentials: 'same-origin' })
  })

  it('sends a Visit edit as the backend edit command with the visit type renamed to visitType', async () => {
    const fetchMock = vi.fn().mockResolvedValue(success({ id: 'CRM-VIS-00001' }))
    const api = createFrappeApi({ fetchImpl: fetchMock })

    await api.updateVisit('CRM-VIS-00001', { subject: '改期后拜访', date: '2026-07-28', type: 'On-site', owner: 'sales@example.com', objective: '确认样片' }, '2026-08-04 12:00:00.000000')

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const body = new URLSearchParams(String(init.body))
    expect(url).toContain('rayher_crm.api.v1.visits.update_visit')
    expect(body.get('id')).toBe('CRM-VIS-00001')
    // `command.type` is the command discriminator; the visit type must not overwrite it.
    expect(JSON.parse(body.get('command')!)).toEqual({ type: 'edit', subject: '改期后拜访', date: '2026-07-28', visitType: 'On-site', owner: 'sales@example.com', objective: '确认样片' })
    expect(body.get('expectedModified')).toBe('2026-08-04 12:00:00.000000')
  })

  it('JSON-serializes complex POST fields and sends the Frappe CSRF token', async () => {
    ;(window as Window & { frappe?: { csrf_token?: string } }).frappe = { csrf_token: 'csrf-test-only' }
    const fetchMock = vi.fn().mockResolvedValue(success({ id: 'ACC-1' }))
    const api = createFrappeApi({ fetchImpl: fetchMock })
    const input = { name: 'Test Account', tier: 'A' } as never

    await api.updateAccount('ACC-1', input, '2026-08-04 12:00:00.000000')

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const headers = new Headers(init.headers)
    const body = new URLSearchParams(String(init.body))
    expect(init.method).toBe('POST')
    expect(init.credentials).toBe('same-origin')
    expect(headers.get('Content-Type')).toBe('application/x-www-form-urlencoded;charset=UTF-8')
    expect(headers.get('X-Frappe-CSRF-Token')).toBe('csrf-test-only')
    expect(body.get('id')).toBe('ACC-1')
    expect(JSON.parse(body.get('input')!)).toEqual(input)
    expect(body.get('expectedModified')).toBe('2026-08-04 12:00:00.000000')
  })

  it('sends current versions for Demo Request transitions and preparation commands', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(success({ id: 'ok' })))
    const api = createFrappeApi({ fetchImpl: fetchMock })
    const version = '2026-08-06T03:00:00.000000Z'

    await api.transitionDemoRequest('DR-1', { type: 'submit' }, version)
    await api.completeEvaluationPreparation('EVAL-1', 'wafer', version)

    const transitionBody = new URLSearchParams(String(fetchMock.mock.calls[0][1].body))
    expect(transitionBody.get('expectedModified')).toBe(version)
    const preparationBody = new URLSearchParams(String(fetchMock.mock.calls[1][1].body))
    expect(preparationBody.get('branch')).toBe('wafer')
    expect(preparationBody.get('expectedModified')).toBe(version)
  })

  it('wraps the notification endpoint flat data as PageData without losing metadata', async () => {
    const envelope = {
      data: [{ id: 'CRM-NOT-1' }],
      meta: { requestId: 'req_notifications', page: 1, pageSize: 20, total: 1 },
      warnings: [],
    }
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ message: envelope }))
    const result = await createFrappeApi({ fetchImpl: fetchMock }).listNotifications({ unreadOnly: true })

    expect(result).toEqual({ ...envelope, data: { items: envelope.data } })
  })

  it('converts a CRM business error envelope to CrmApiError even on non-2xx', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ message: {
      data: null,
      meta: { requestId: 'req_conflict' },
      warnings: [],
      error: {
        code: 'VERSION_CONFLICT',
        message: 'The record changed.',
        retryable: false,
        fieldErrors: { expectedModified: 'stale' },
      },
    } }, 409))

    const promise = createFrappeApi({ fetchImpl: fetchMock }).markNotificationRead('CRM-NOT-1')

    await expect(promise).rejects.toEqual(expect.objectContaining({
      name: 'CrmApiError',
      code: 'VERSION_CONFLICT',
      requestId: 'req_conflict',
      retryable: false,
      fieldErrors: { expectedModified: 'stale' },
    }))
  })

  it.each([
    [401, 'UNAUTHENTICATED'],
    [403, 'PERMISSION_DENIED'],
    [404, 'NOT_FOUND'],
    [409, 'VERSION_CONFLICT'],
    [422, 'VALIDATION_ERROR'],
    [503, 'INTERNAL_ERROR'],
  ] as const)('normalizes bare HTTP %s failures to %s', async (status, code) => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ exception: 'redacted upstream failure' }, status, {
      'X-Request-ID': 'req_http',
    }))
    const promise = createFrappeApi({ fetchImpl: fetchMock }).getBootstrap()
    await expect(promise).rejects.toEqual(expect.objectContaining({ code, requestId: 'req_http' }))
  })

  it('normalizes fetch failures without exposing implementation errors', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    const promise = createFrappeApi({ fetchImpl: fetchMock }).getBootstrap()
    await expect(promise).rejects.toEqual(expect.objectContaining({
      code: 'NETWORK_ERROR',
      retryable: true,
    }))
  })

  it('normalizes an aborted request as a retryable network error', async () => {
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    }))
    const promise = createFrappeApi({ fetchImpl: fetchMock as typeof fetch, timeoutMs: 1 }).getBootstrap()
    await expect(promise).rejects.toEqual(expect.objectContaining({
      code: 'NETWORK_ERROR',
      retryable: true,
    }))
  })
})

describe('Frappe multipart and binary transport', () => {
  it('uploads one completed DRF for server-side PDF or DOCX extraction', async () => {
    const fetchMock = vi.fn().mockResolvedValue(success({
      fileName: 'completed-drf.pdf', companyName: 'Example Semiconductor Co.',
      formData: { primaryTool: 'Aconca FS Edge', wafers: [] }, detectedFields: ['companyName', 'primaryTool'],
    }))
    const api = createFrappeApi({ fetchImpl: fetchMock })

    await api.importDemoRequestForm({
      blob: new Blob(['pdf'], { type: 'application/pdf' }),
      fileName: 'completed-drf.pdf', mimeType: 'application/pdf', size: 3,
    })

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/method/rayher_crm.api.v1.demo_requests.import_form')
    expect(init.body).toBeInstanceOf(FormData)
    expect(((init.body as FormData).get('file') as File).name).toBe('completed-drf.pdf')
  })

  it('uploads Contact files as repeated multipart files without forcing Content-Type', async () => {
    const fetchMock = vi.fn().mockResolvedValue(success([]))
    const api = createFrappeApi({ fetchImpl: fetchMock })

    await api.uploadContactFiles('CON-1', [
      { blob: new Blob(['a'], { type: 'text/plain' }), fileName: 'a.txt', mimeType: 'text/plain', size: 1 },
      { blob: new Blob(['b'], { type: 'text/plain' }), fileName: 'b.txt', mimeType: 'text/plain', size: 1 },
    ])

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const headers = new Headers(init.headers)
    expect(init.body).toBeInstanceOf(FormData)
    expect(headers.has('Content-Type')).toBe(false)
    expect((init.body as FormData).get('contactId')).toBe('CON-1')
    expect((init.body as FormData).getAll('files')).toHaveLength(2)
  })

  it('uploads one Demo artifact with separate metadata fields', async () => {
    const fetchMock = vi.fn().mockResolvedValue(success({ id: 'ART-1' }))
    const api = createFrappeApi({ fetchImpl: fetchMock })
    await api.saveDemoArtifact({
      demoRequestId: 'DEMO-1', evaluationId: 'EVAL-1', type: 'Demo Request DOCX', visibility: 'Internal',
      file: { blob: new Blob(['x']), fileName: 'result.bin', mimeType: 'application/octet-stream', size: 1 },
    })
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const body = init.body as FormData
    expect(body.get('demoRequestId')).toBe('DEMO-1')
    expect(body.get('evaluationId')).toBe('EVAL-1')
    expect(body.get('type')).toBe('Demo Request DOCX')
    expect(body.get('visibility')).toBe('Internal')
    expect(body.getAll('file')).toHaveLength(1)
  })

  it('uploads one controlled document with metadata and a separate multipart file', async () => {
    const fetchMock = vi.fn().mockResolvedValue(success({ id: 'DOCUP-00001', status: 'Pending' }))
    const api = createFrappeApi({ fetchImpl: fetchMock })
    await api.submitControlledDocumentUpload({
      title: 'Engineer equipment manual', category: 'Technical', documentType: 'Equipment Manual',
      accessMode: 'Request', confidentiality: 'Confidential', product: 'ETCH-01',
      version: '1.0', revision: 'R1', reviewDate: '2027-08-12',
    }, { blob: new Blob(['manual']), fileName: 'manual.pdf', mimeType: 'application/pdf', size: 6 })

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/method/rayher_crm.api.v1.document_uploads.submit_upload')
    expect(init.body).toBeInstanceOf(FormData)
    const form = init.body as FormData
    expect(form.get('title')).toBe('Engineer equipment manual')
    expect(form.get('category')).toBe('Technical')
    expect(form.get('accessMode')).toBe('Request')
    expect((form.get('file') as File).name).toBe('manual.pdf')
  })

  it('returns raw binary and decodes an RFC 5987 filename', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('pdf', {
      status: 200,
      headers: {
        'Content-Type': 'application/pdf',
        'Content-Disposition': "attachment; filename*=UTF-8''%E6%B5%8B%E8%AF%95.pdf",
      },
    }))
    const download = await createFrappeApi({ fetchImpl: fetchMock }).getDemoArtifact('ART-1')
    expect(download.fileName).toBe('测试.pdf')
    expect(download.mimeType).toBe('application/pdf')
    expect(await download.blob.text()).toBe('pdf')
  })

  it('uploads the selected Test Report as multipart data', async () => {
    const fetchMock = vi.fn().mockResolvedValue(success({ id: 'ART-REPORT-1' }))
    const internalBlob = new Blob(['internal'], { type: 'application/pdf' })
    const externalBlob = new Blob(['external'], { type: 'application/pdf' })
    const internalReadSpy = vi.spyOn(internalBlob, 'arrayBuffer')
    const externalReadSpy = vi.spyOn(externalBlob, 'arrayBuffer')
    await createFrappeApi({ fetchImpl: fetchMock }).releaseDemoTestReport('EVAL-1', {
      internalFile: { blob: internalBlob, fileName: 'internal.pdf', mimeType: 'application/pdf', size: internalBlob.size },
      externalFile: { blob: externalBlob, fileName: 'external.pdf', mimeType: 'application/pdf', size: externalBlob.size },
      expectedRound: 2,
    })
    expect(internalReadSpy).toHaveBeenCalledOnce()
    expect(externalReadSpy).toHaveBeenCalledOnce()
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(init.body).toBeInstanceOf(FormData)
    const form = init.body as FormData
    expect(form.get('id')).toBe('EVAL-1')
    expect(form.get('expectedRound')).toBe('2')
    expect((form.get('internalFile') as File).name).toBe('internal.pdf')
    expect((form.get('externalFile') as File).name).toBe('external.pdf')
  })

  it('preserves TipRay-encrypted bytes in the multipart request', async () => {
    const fetchMock = vi.fn().mockResolvedValue(success({ id: 'ART-REPORT-1' }))
    const encrypted = '%TSD-Header-###%encrypted'
    const blob = new Blob([encrypted], { type: 'application/pdf' })

    await createFrappeApi({ fetchImpl: fetchMock }).releaseDemoTestReport('EVAL-1', {
      internalFile: { blob, fileName: 'report.pdf', mimeType: 'application/pdf', size: blob.size },
      externalFile: { blob, fileName: 'customer-report.pdf', mimeType: 'application/pdf', size: blob.size },
      expectedRound: 1,
    })

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const uploaded = (init.body as FormData).get('internalFile') as File
    expect(uploaded.name).toBe('report.pdf')
    expect(uploaded.type).toBe('application/pdf')
    expect(await uploaded.text()).toBe(encrypted)
  })
})

describe('normalizeFrappeError compatibility', () => {
  it('keeps an existing CrmApiError unchanged', () => {
    const error = new CrmApiError('VALIDATION_ERROR', 'invalid', 'req_existing')
    expect(error).toBe(error)
  })
})

describe('Installed Tool audit transport', () => {
  it('maps detail and all audit commands to the exact real Frappe endpoints', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(success({ id: 'CRM-TOOL-00001' })))
    const api = createFrappeApi({ fetchImpl: fetchMock })
    const transition = { completedAt: '2026-08-12', result: 'Passed', openIssues: 'None', customerSignoff: 'Signed', comment: 'Done', evidence: ['report.pdf'] }
    const version = { changeDate: '2026-08-12', changeType: 'Software' as const, toValue: '1.2', reason: 'Release', comment: '' }
    const service = { serviceDate: '2026-08-12', serviceType: 'Remote Support' as const, result: 'Resolved', openIssues: 'None', comment: '' }

    await api.getInstalledTool('CRM-TOOL-00001')
    await api.transitionInstalledTool('CRM-TOOL-00001', transition, 'v1')
    await api.addInstalledToolVersionRecord('CRM-TOOL-00001', version, 'v2')
    await api.addInstalledToolServiceRecord('CRM-TOOL-00001', service, 'v3')

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/method/rayher_crm.api.v1.installed_tools.get_installed_tool?id=CRM-TOOL-00001',
      '/api/method/rayher_crm.api.v1.installed_tools.transition_installed_tool',
      '/api/method/rayher_crm.api.v1.installed_tools.add_installed_tool_version_record',
      '/api/method/rayher_crm.api.v1.installed_tools.add_installed_tool_service_record',
    ])
    expect(fetchMock.mock.calls.map(([, init]) => init.method)).toEqual(['GET', 'POST', 'POST', 'POST'])
    const bodies = fetchMock.mock.calls.slice(1).map(([, init]) => new URLSearchParams(String(init.body)))
    expect(bodies.map((body) => body.get('expectedModified'))).toEqual(['v1', 'v2', 'v3'])
    expect(bodies.map((body) => body.get('id'))).toEqual(['CRM-TOOL-00001', 'CRM-TOOL-00001', 'CRM-TOOL-00001'])
    expect(JSON.parse(bodies[0].get('input') ?? '{}')).toEqual(transition)
    expect(JSON.parse(bodies[1].get('input') ?? '{}')).toEqual(version)
    expect(JSON.parse(bodies[2].get('input') ?? '{}')).toEqual(service)
  })
})
