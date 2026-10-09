import { afterEach, describe, expect, it, vi } from 'vitest'
import { CrmApiError } from './contracts'
import { createFrappeApi, FRAPPE_METHODS } from './frappe-adapter'
import { SESSION_EXPIRED_EVENT } from './session'

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
  it('posts a period commitment and the previously saved version', async () => {
    const fetchMock = vi.fn().mockResolvedValue(success({ id: 'promise' }))
    const api = createFrappeApi({ fetchImpl: fetchMock })
    const input = { sales: 'sales', period: 'week' as const, anchor: '2030-09-02', metric: 'visits' as const, value: '0', note: 'Updated promise' }
    await api.savePlanCommitment(input, 'previous')
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/method/rayher_crm.api.v1.cockpit.save_plan_commitment')
    expect(Object.fromEntries(new URLSearchParams(init.body as string))).toEqual({ input: JSON.stringify(input), expectedModified: 'previous' })
  })

  it('carries the Blue Sheet version, stable flags and suggestion fingerprint to the backend', async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => success({ id: 'OPP-1' }))
    const api = createFrappeApi({ fetchImpl: fetchMock })
    const input = { items: [{ id: 'flag-1', text: 'Risk', severity: 'High' as const, status: 'Resolved' as const }] }
    await api.saveBlueSheetFlags('OPP-1', input, 'version-1')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/method/rayher_crm.api.v1.opportunities.save_blue_sheet_flags')
    expect(Object.fromEntries(new URLSearchParams(fetchMock.mock.calls[0][1]!.body as string))).toEqual({ id: 'OPP-1', input: JSON.stringify(input), expectedModified: 'version-1' })
    const confirmation = { fingerprint: 'facts-v1', probabilityReason: 'Budget', probabilityActionPlan: 'Meet buyer' }
    await api.applyBlueSheetSuggestion('OPP-1', confirmation, 'version-2')
    expect(Object.fromEntries(new URLSearchParams(fetchMock.mock.calls[1][1]!.body as string))).toEqual({ id: 'OPP-1', input: JSON.stringify(confirmation), expectedModified: 'version-2' })
  })

  it('reads an exact target key without writing or sending a target value', async () => {
    const fetchMock = vi.fn().mockResolvedValue(success(null))
    const api = createFrappeApi({ fetchImpl: fetchMock })
    const key = { scope: 'sales' as const, sales: 'rep@example.invalid', territory: '', metric: 'visits' as const,
      period: 'weekly_default' as const, anchor: '2030-09-02' }
    expect((await api.getReviewTarget(key)).data).toBeNull()
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const parsed = new URL(url, 'http://localhost')
    expect(parsed.pathname).toBe('/api/method/rayher_crm.api.v1.cockpit.get_target')
    expect(Object.fromEntries(parsed.searchParams)).toEqual(key)
    expect(init.method).toBe('GET')
  })
  it('keeps effective dates and the saved version on territory assignment edits', async () => {
    const fetchMock = vi.fn().mockResolvedValue(success({ id: 'A-1' }))
    const api = createFrappeApi({ fetchImpl: fetchMock })
    const input = { territory: 'East China', salesOwner: 'sales@example.invalid', validFrom: '2026-10-01', validUntil: null, cancelled: false, note: 'New responsibility' }
    await api.saveTerritoryAssignment(input, 'A-1', '2026-09-30T00:00:00Z')
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/method/rayher_crm.api.v1.territories.save_assignment')
    expect(Object.fromEntries(new URLSearchParams(init.body as string))).toEqual({ name: 'A-1', input: JSON.stringify(input), expectedModified: '2026-09-30T00:00:00Z' })
  })

  it('reads the opportunity library and saves links with the exact parent version', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => success({}))
    const api = createFrappeApi({ fetchImpl: fetchMock })
    await api.getOpportunityDocuments('OPP-1')
    const input = { productScorecard: 'https://example.com/card', dealScorecard: '' }
    await api.saveOpportunityDocumentLinks('OPP-1', input, '2026-10-01T00:00:00Z')
    const readUrl = new URL(fetchMock.mock.calls[0][0], 'http://localhost')
    expect(readUrl.pathname).toBe('/api/method/rayher_crm.api.v1.opportunity_documents.get_documents')
    expect(readUrl.searchParams.get('opportunityId')).toBe('OPP-1')
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(url).toBe('/api/method/rayher_crm.api.v1.opportunity_documents.save_links')
    expect(init.method).toBe('POST')
    expect(Object.fromEntries(new URLSearchParams(init.body as string))).toEqual({ opportunityId: 'OPP-1', input: JSON.stringify(input), expectedModified: '2026-10-01T00:00:00Z' })
  })

  it('posts recovery edits with both parent and recovery versions', async () => {
    const fetchMock = vi.fn().mockResolvedValue(success({ id: 'REC-1', plan: 'Meet buyer' }))
    const api = createFrappeApi({ fetchImpl: fetchMock })
    const input = { plan: 'Meet buyer', recoveryModified: '2026-09-22T00:00:00.000000Z' }
    await api.saveProbabilityRecovery('OPP-1', 'EVENT-1', input, '2026-09-21T00:00:00.000000Z')
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/method/rayher_crm.api.v1.opportunities.save_probability_recovery')
    expect(init.method).toBe('POST')
    const body = new URLSearchParams(init.body as string)
    expect(Object.fromEntries(body)).toEqual({ id: 'OPP-1', eventId: 'EVENT-1', input: JSON.stringify(input), expectedModified: '2026-09-21T00:00:00.000000Z' })
  })

  it('freezes every CrmApi method to a rayher_crm v1 whitelist endpoint', () => {
    expect(FRAPPE_METHODS).toEqual({
      queryOpportunities: 'cockpit.query_opportunities',
      exportOpportunities: 'cockpit.export_opportunities',
      getQueryRecipients: 'cockpit.get_query_recipients',
      shareOpportunityQuery: 'cockpit.share_opportunity_query',
      getOpportunityFilters: 'cockpit.get_opportunity_filters',
      listOpportunityQueries: 'cockpit.list_opportunity_queries',
      saveOpportunityQuery: 'cockpit.save_opportunity_query',
      deleteOpportunityQuery: 'cockpit.delete_opportunity_query',
      getQuotationPlanning: 'quotation_planning.get_planning',
      saveQuotationSchedule: 'quotation_planning.save_schedule',
      saveQuotationFollowUp: 'quotation_planning.save_follow_up',
      listEvents: 'events.list_events',
      getEvent: 'events.get_event',
      saveEvent: 'events.save_event',
      getPlan: 'cockpit.get_plan',
      savePlanCommitment: 'cockpit.save_plan_commitment',
      getPlanDetails: 'cockpit.get_plan_details',
      getReview: 'cockpit.get_review',
      getReviewDetails: 'cockpit.get_details',
      getWarnings: 'cockpit.get_warnings',
      saveReviewTarget: 'cockpit.save_target',
      getReviewTarget: 'cockpit.get_target',
      getTerritoryCatalogue: 'territories.get_catalogue',
      saveTerritory: 'territories.save_territory',
      saveTerritoryAssignment: 'territories.save_assignment',
      getCockpitSettings: 'cockpit.get_cockpit_settings',
      saveCockpitSettings: 'cockpit.save_cockpit_settings',
      saveWarningPlan: 'cockpit.save_warning_plan',
      recordWarningAction: 'cockpit.record_warning_action',
      getBootstrap: 'bootstrap.get_bootstrap',
      changeCurrentUserPassword: 'account.change_password',
      signOut: 'logout',
      listNotifications: 'notifications.list_notifications',
      markNotificationRead: 'notifications.mark_notification_read',
      markAllNotificationsRead: 'notifications.mark_all_notifications_read',
      getDashboard: 'dashboard.get_dashboard',
      listAccounts: 'accounts.list_accounts',
      listAccountSegments: 'accounts.list_account_segments',
      listAccountRegions: 'accounts.list_account_regions',
      listAccountCities: 'accounts.list_account_cities',
      createAccount: 'accounts.create_account',
      updateAccount: 'accounts.update_account',
      deleteAccount: 'accounts.delete_account',
      getAccount360: 'accounts.get_account_360',
      listAccountSites: 'accounts.list_account_sites',
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
      archiveLead: 'leads.archive_lead',
      unarchiveLead: 'leads.unarchive_lead',
      convertLead: 'leads.convert_lead',
      listStakeholders: 'stakeholders.list_stakeholders',
      createStakeholder: 'stakeholders.create_stakeholder',
      updateStakeholder: 'stakeholders.update_stakeholder',
      listRequirements: 'read_only_views.list_requirements',
      listPipeline: 'pipeline.list_pipeline',
      listBookings: 'bookings.list_bookings',
      createBooking: 'bookings.create_booking',
      updateBooking: 'bookings.update_booking',
      getBooking: 'bookings.get_booking',
      archiveBooking: 'bookings.archive_booking',
      unarchiveBooking: 'bookings.unarchive_booking',
      completeServiceBooking: 'bookings.complete_service_booking',
      setBookingActualPoDate: 'bookings.set_actual_po_date',
      setBookingAmountCny: 'bookings.set_amount_cny',
      listDemoRequests: 'demo_requests.list_demo_requests',
      importDemoRequestForm: 'demo_requests.import_form',
      createDemoRequest: 'demo_requests.create_demo_request',
      updateDemoRequest: 'demo_requests.update_demo_request',
      transitionDemoRequest: 'demo_requests.transition_demo_request',
      listEvaluations: 'evaluations.list_evaluations',
      getEvaluation: 'evaluations.get_evaluation',
      completeEvaluationPreparation: 'evaluations.complete_evaluation_preparation',
      updateEvaluationStatus: 'evaluations.update_evaluation_status',
      terminateEvaluation: 'evaluations.terminate_evaluation',
      addEvaluationRun: 'evaluations.add_evaluation_run',
      updateEvaluationRun: 'evaluations.update_evaluation_run',
      cancelEvaluationRun: 'evaluations.cancel_evaluation_run',
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
      listEquipmentTypes: 'opportunities.list_equipment_types',
      getStrategyOpportunity: 'opportunities.get_strategy_opportunity',
      saveBlueSheetFlags: 'opportunities.save_blue_sheet_flags',
      getBlueSheetAssessment: 'opportunities.get_blue_sheet_assessment',
      applyBlueSheetSuggestion: 'opportunities.apply_blue_sheet_suggestion',
      createStrategyOpportunity: 'opportunities.create_strategy_opportunity',
      updateStrategyOpportunity: 'opportunities.update_strategy_opportunity',
      reviewOpportunityLoss: 'opportunities.review_opportunity_loss',
      saveProbabilityRecovery: 'opportunities.save_probability_recovery',
      recordProbabilityRecoveryAction: 'opportunities.record_probability_recovery_action',
      rollbackOpportunityStage: 'opportunities.rollback_opportunity_stage',
      confirmBudgetApproved: 'opportunities.confirm_budget_approved',
      requestInternalValidation: 'opportunities.request_internal_validation',
      reviewInternalValidation: 'opportunities.review_internal_validation',
      confirmPo: 'opportunities.confirm_po',
      markOpportunityLost: 'opportunities.mark_opportunity_lost',
      archiveStrategyOpportunity: 'opportunities.archive_strategy_opportunity',
      unarchiveStrategyOpportunity: 'opportunities.unarchive_strategy_opportunity',
      createOpportunityStakeholder: 'opportunities.create_opportunity_stakeholder',
      updateOpportunityStakeholder: 'opportunities.update_opportunity_stakeholder',
      deleteOpportunityStakeholder: 'opportunities.delete_opportunity_stakeholder',
      listOpportunityStatuses: 'opportunity_status.list_records',
      getOpportunityDocuments: 'opportunity_documents.get_documents',
      saveOpportunityDocumentLinks: 'opportunity_documents.save_links',
      saveOpportunityStatus: 'opportunity_status.save_record',
      getOpportunityStatusFile: 'opportunity_status.download_file',
      createOpportunityAction: 'opportunities.create_opportunity_action',
      updateOpportunityAction: 'opportunities.update_opportunity_action',
      deleteOpportunityAction: 'opportunities.delete_opportunity_action',
      listDemoWorkflows: 'evaluations.list_demo_workflows',
      getDemoWorkflow: 'evaluations.get_demo_workflow',
      getDemoResources: 'demo_resources.get_demo_resources',
      saveDemoResource: 'demo_resources.save_demo_resource',
      getDemoUnavailability: 'demo_resources.get_demo_unavailability',
      saveDemoUnavailability: 'demo_resources.save_demo_unavailability',
      getDemoResourceSchedule: 'demo_resources.get_demo_resource_schedule',
      saveDemoResourceSchedule: 'demo_resources.save_demo_resource_schedule',
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
  it('posts stable ids to the Manager-only Account delete endpoint', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(success({ id: 'deleted', status: 'Deleted' })))
    const api = createFrappeApi({ fetchImpl: fetchMock })

    await api.deleteAccount('ACC-DEL')

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(['/api/method/rayher_crm.api.v1.accounts.delete_account'])
    expect(fetchMock.mock.calls.map(([, init]) => new URLSearchParams(String(init.body)).get('id'))).toEqual(['ACC-DEL'])
  })

  it('posts the Opportunity id to the archive and restore endpoints', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(success({ id: 'OPP-ARC', archived: true })))
    const api = createFrappeApi({ fetchImpl: fetchMock })

    await api.archiveStrategyOpportunity('OPP-ARC')
    await api.unarchiveStrategyOpportunity('OPP-ARC')

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/method/rayher_crm.api.v1.opportunities.archive_strategy_opportunity',
      '/api/method/rayher_crm.api.v1.opportunities.unarchive_strategy_opportunity',
    ])
    expect(fetchMock.mock.calls.map(([, init]) => new URLSearchParams(String(init.body)).get('id'))).toEqual(['OPP-ARC', 'OPP-ARC'])
  })

  it('reads a Booking by id and posts the id to its archive and restore endpoints', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(success({ id: 'BKG-ARC', archived: true })))
    const api = createFrappeApi({ fetchImpl: fetchMock })

    await api.getBooking('BKG-ARC')
    await api.archiveBooking('BKG-ARC')
    await api.unarchiveBooking('BKG-ARC')

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/method/rayher_crm.api.v1.bookings.get_booking?id=BKG-ARC',
      '/api/method/rayher_crm.api.v1.bookings.archive_booking',
      '/api/method/rayher_crm.api.v1.bookings.unarchive_booking',
    ])
    expect(fetchMock.mock.calls.slice(1).map(([, init]) => new URLSearchParams(String(init.body)).get('id'))).toEqual(['BKG-ARC', 'BKG-ARC'])
  })

  it('posts the Lead id to the archive and restore endpoints', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(success({ id: 'LEAD-ARC', archived: true })))
    const api = createFrappeApi({ fetchImpl: fetchMock })

    await api.archiveLead('LEAD-ARC')
    await api.unarchiveLead('LEAD-ARC')

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/method/rayher_crm.api.v1.leads.archive_lead',
      '/api/method/rayher_crm.api.v1.leads.unarchive_lead',
    ])
    expect(fetchMock.mock.calls.map(([, init]) => new URLSearchParams(String(init.body)).get('id'))).toEqual(['LEAD-ARC', 'LEAD-ARC'])
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

  it('loads the shared account regions through the Frappe GET endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(success(['East China', 'South China', 'Southeast Asia']))
    const api = createFrappeApi({ fetchImpl: fetchMock })

    const result = await api.listAccountRegions()

    expect(result.data).toEqual(['East China', 'South China', 'Southeast Asia'])
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/method/rayher_crm.api.v1.accounts.list_account_regions')
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

  it('signs out through Frappe\'s own logout endpoint, as a GET that needs no CSRF token', async () => {
    // No token: the CRM's bootstrap, which brings it, may have failed while the session is there to end.
    ;(window as Window & { frappe?: { csrf_token?: string } }).frappe = {}
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ message: 'Logged Out' }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    const api = createFrappeApi({ fetchImpl: fetchMock })

    await api.signOut()

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/method/logout')
    expect(init.method).toBe('GET')
    expect(init.credentials).toBe('same-origin')
    expect(init.body).toBeUndefined()

    // A refusal is an error the page can show; the session is then still there.
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ exc_type: 'ValidationError' }), { status: 400, headers: { 'Content-Type': 'application/json' } }))
    await expect(api.signOut()).rejects.toBeInstanceOf(CrmApiError)
  })

  it('ends the session only once the requests out under it are answered', async () => {
    // A request answered after the logout would write the session back (Frappe renews the session cache at the end
    // of every request it authenticated): the logout waits for what is out.
    ;(window as Window & { frappe?: { csrf_token?: string } }).frappe = {}
    let answer: (response: Response) => void = () => undefined
    const fetchMock = vi.fn()
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { answer = resolve }))
      .mockResolvedValue(new Response(JSON.stringify({ message: 'Logged Out' }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    const api = createFrappeApi({ fetchImpl: fetchMock })

    const reading = api.listNotifications({ page: 1, pageSize: 1 }).catch(() => undefined)
    const signingOut = api.signOut()
    await Promise.resolve(); await Promise.resolve()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect((fetchMock.mock.calls[0] as [string])[0]).not.toBe('/api/method/logout')

    answer(new Response(JSON.stringify({ message: { data: [], meta: { requestId: 'req_n', page: 1, pageSize: 1, total: 0 }, warnings: [] } }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    await reading
    await signingOut
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect((fetchMock.mock.calls[1] as [string])[0]).toBe('/api/method/logout')
  })

  it('sends nothing else once the sign-out is under way, until the sign-out fails', async () => {
    ;(window as Window & { frappe?: { csrf_token?: string } }).frappe = {}
    const ok = () => new Response(JSON.stringify({ message: { data: {}, meta: { requestId: 'req' }, warnings: [] } }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    let answerBootstrap: (response: Response) => void = () => undefined
    let answerLogout: (response: Response) => void = () => undefined
    const fetchMock = vi.fn()
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { answerBootstrap = resolve }))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { answerLogout = resolve }))
      .mockImplementation(async () => ok())
    const api = createFrappeApi({ fetchImpl: fetchMock })

    // The bootstrap is out when the sign-out starts: the logout waits for it, and what the bootstrap's answer sets
    // off (the notification reads) is not sent.
    const booting = api.getBootstrap().catch(() => undefined)
    const signingOut = api.signOut()
    await Promise.resolve(); await Promise.resolve()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    answerBootstrap(ok())
    await booting
    await Promise.resolve(); await Promise.resolve()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect((fetchMock.mock.calls[1] as [string])[0]).toBe('/api/method/logout')
    await expect(api.listNotifications({ page: 1, pageSize: 1 })).rejects.toMatchObject({ message: '正在退出登录，请求未发送。' })
    expect(fetchMock).toHaveBeenCalledTimes(2)

    // The sign-out refused: the session is there to use, and the requests go out again.
    answerLogout(new Response(JSON.stringify({ exc_type: 'ValidationError' }), { status: 400, headers: { 'Content-Type': 'application/json' } }))
    await expect(signingOut).rejects.toBeInstanceOf(CrmApiError)
    await api.listNotifications({ page: 1, pageSize: 1 }).catch(() => undefined)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('waits for an in-flight body deadline before sending logout', async () => {
    vi.useFakeTimers()
    try {
      const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
        if (url.endsWith('/logout')) return jsonResponse({ message: 'Logged Out' })
        return new Response(new ReadableStream({ start(controller) {
          init?.signal?.addEventListener('abort', () => controller.error(new DOMException('Aborted', 'AbortError')))
        } }))
      })
      const api = createFrappeApi({ fetchImpl: fetchMock as typeof fetch, timeoutMs: 100 })
      const reading = api.getBootstrap().then(() => null, error => error as CrmApiError)
      await vi.advanceTimersByTimeAsync(1)
      const signingOut = api.signOut()
      await vi.advanceTimersByTimeAsync(98)
      expect(fetchMock).toHaveBeenCalledTimes(1)
      await vi.advanceTimersByTimeAsync(1)
      await expect(reading).resolves.toMatchObject({ code: 'NETWORK_ERROR', retryable: true })
      await signingOut
      expect(fetchMock.mock.calls.map(call => call[0])).toEqual([
        '/api/method/rayher_crm.api.v1.bootstrap.get_bootstrap', '/api/method/logout',
      ])
      expect(vi.getTimerCount()).toBe(0)
    } finally { vi.useRealTimers() }
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

  describe('a session that is no longer signed in', () => {
    // The adapter redirects once per page load, so each test loads it afresh.
    async function freshAdapter() {
      vi.resetModules()
      return import('./frappe-adapter')
    }

    function stubLocation() {
      const assign = vi.fn()
      vi.stubGlobal('location', { pathname: '/assets/rayher_crm/crm/index.html', search: '?v=819a78af9dc5', hash: '#/warnings', assign })
      return assign
    }

    function expiredSessionListener() {
      const listener = vi.fn()
      window.addEventListener(SESSION_EXPIRED_EVENT, listener)
      return { listener, stop: () => window.removeEventListener(SESSION_EXPIRED_EVENT, listener) }
    }

    it('returns to the login page and keeps the current address when the bootstrap finds nobody signed in', async () => {
      const assign = stubLocation()
      const expired = expiredSessionListener()
      const { createFrappeApi: create } = await freshAdapter()
      const fetchMock = vi.fn().mockImplementation(async () => jsonResponse({ exc_type: 'AuthenticationError' }, 401))
      const api = create({ fetchImpl: fetchMock })

      await expect(api.getBootstrap()).rejects.toEqual(expect.objectContaining({ code: 'UNAUTHENTICATED', message: '登录已失效，请重新登录。' }))
      await expect(api.getBootstrap()).rejects.toEqual(expect.objectContaining({ code: 'UNAUTHENTICATED' }))
      expired.stop()

      expect(assign).toHaveBeenCalledTimes(1)
      expect(assign).toHaveBeenCalledWith(
        `/login?redirect-to=${encodeURIComponent('/assets/rayher_crm/crm/index.html?v=819a78af9dc5#/warnings')}`,
      )
      expect(expired.listener).not.toHaveBeenCalled()
    })

    it('stays on the page and announces the expired session when any other call finds nobody signed in', async () => {
      const assign = stubLocation()
      const expired = expiredSessionListener()
      const { createFrappeApi: create } = await freshAdapter()
      const fetchMock = vi.fn().mockImplementation(async () => jsonResponse({ exc_type: 'AuthenticationError' }, 401))
      const api = create({ fetchImpl: fetchMock })

      // A background poll, a write, and a download: none of them may take the page away from what is being typed.
      await expect(api.listNotifications({ page: 1, pageSize: 1 })).rejects.toEqual(expect.objectContaining({ code: 'UNAUTHENTICATED' }))
      await expect(api.markAllNotificationsRead()).rejects.toEqual(expect.objectContaining({ code: 'UNAUTHENTICATED' }))
      await expect(api.getContactFile('CRM-CF-1')).rejects.toEqual(expect.objectContaining({ code: 'UNAUTHENTICATED' }))
      expired.stop()

      expect(assign).not.toHaveBeenCalled()
      expect(expired.listener).toHaveBeenCalledTimes(3)
    })

    it.each([
      [403, { message: { data: null, error: { code: 'PERMISSION_DENIED', message: 'The current user is not permitted to perform this operation.' } } }, 'PERMISSION_DENIED'],
      [403, { message: { data: null, error: { code: 'SCOPE_DENIED', message: 'The Account is outside the current user scope.' } } }, 'SCOPE_DENIED'],
      [500, { message: { data: null, error: { code: 'INTERNAL_ERROR', message: 'The request could not be completed.' } } }, 'INTERNAL_ERROR'],
    ] as const)('stays on the page, with the session still good, on HTTP %s %j', async (status, payload, code) => {
      const assign = stubLocation()
      const expired = expiredSessionListener()
      const { createFrappeApi: create } = await freshAdapter()
      const api = create({ fetchImpl: vi.fn().mockImplementation(async () => jsonResponse(payload, status)) })

      await expect(api.getBootstrap()).rejects.toEqual(expect.objectContaining({ code }))
      await expect(api.markAllNotificationsRead()).rejects.toEqual(expect.objectContaining({ code }))
      expired.stop()

      expect(assign).not.toHaveBeenCalled()
      expect(expired.listener).not.toHaveBeenCalled()
    })
  })

  it('asks the Opportunity list for its stage summary in the same request and returns it with the page', async () => {
    const stageSummary = [{ stage: 'demo_done', count: 25, unknownAmountCount: 0, totals: [{ currency: 'CNY', amount: '25000.00' }] }]
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ message: {
      data: { items: [], stageSummary }, meta: { requestId: 'req_board', page: 1, pageSize: 200, total: 25 }, warnings: [],
    } }))

    const result = await createFrappeApi({ fetchImpl: fetchMock }).listStrategyOpportunities({ page: 1, pageSize: 200, status: 'All', stageSummary: true })

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url.startsWith('/api/method/rayher_crm.api.v1.opportunities.list_strategy_opportunities?')).toBe(true)
    expect(Object.fromEntries(new URLSearchParams(url.split('?')[1]))).toEqual({ page: '1', pageSize: '200', status: 'All', stageSummary: 'true' })
    expect(result.data.stageSummary).toEqual(stageSummary)
    expect(result.meta?.total).toBe(25)
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

describe('Warnings business reads and loss reviews', () => {
  it('reads the Warnings page with the Review scope and posts a Manager post-mortem with the review version', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(success({})))
    const api = createFrappeApi({ fetchImpl: fetchMock })
    const query = { period: 'month' as const, anchor: '2026-09-01', sales: 'sales@example.com', region: 'East China', market: 'Frontend' }
    await api.getWarnings(query)
    await api.reviewOpportunityLoss('OPP-1', 'LOSS-1', { status: 'Reviewed', reviewNote: 'Report shared' }, '2026-09-22T00:00:00.000000Z')
    const [[readUrl, readInit], [writeUrl, writeInit]] = fetchMock.mock.calls
    const url = new URL(readUrl, 'http://localhost')
    expect(url.pathname).toBe('/api/method/rayher_crm.api.v1.cockpit.get_warnings')
    for (const [key, value] of Object.entries(query)) expect(url.searchParams.get(key)).toBe(value)
    expect(readInit.method).toBe('GET')
    expect(new URL(writeUrl, 'http://localhost').pathname).toBe('/api/method/rayher_crm.api.v1.opportunities.review_opportunity_loss')
    expect(writeInit.method).toBe('POST')
    const body = new URLSearchParams(writeInit.body)
    expect(body.get('id')).toBe('OPP-1')
    expect(body.get('reviewId')).toBe('LOSS-1')
    expect(body.get('expectedModified')).toBe('2026-09-22T00:00:00.000000Z')
    expect(JSON.parse(body.get('input') ?? '{}')).toEqual({ status: 'Reviewed', reviewNote: 'Report shared' })
  })

  it('reads and saves the thresholds and posts next steps and stage 6 actions with the handling version', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(success({})))
    const api = createFrappeApi({ fetchImpl: fetchMock })
    const settings = { quoteExpiryDays: 21, stage6NoPoDays: 45 }
    const plan = { warningType: 'quotation_expiry' as const, sourceId: 'Q-1', sourceEvent: 'V-2', nextStep: 'Re-price before Friday' }
    const action = { warningType: 'stage6_no_po' as const, sourceId: 'OPP-6', sourceEvent: 'EVT-6', actionTaken: 'GM call with the buyer', followUpOn: '2026-10-08' }
    await api.getCockpitSettings()
    await api.saveCockpitSettings(settings, '2026-09-20T00:00:00.000000Z')
    await api.saveWarningPlan(plan, null)
    await api.recordWarningAction(action, '2026-09-22T00:00:00.000000Z')
    const urls = fetchMock.mock.calls.map(([url]) => new URL(url, 'http://localhost').pathname)
    expect(urls).toEqual(['get_cockpit_settings', 'save_cockpit_settings', 'save_warning_plan', 'record_warning_action'].map(name => `/api/method/rayher_crm.api.v1.cockpit.${name}`))
    expect(fetchMock.mock.calls.map(([, init]) => init.method)).toEqual(['GET', 'POST', 'POST', 'POST'])
    const bodies = fetchMock.mock.calls.slice(1).map(([, init]) => Object.fromEntries(new URLSearchParams(String(init.body))))
    expect(bodies[0]).toEqual({ input: JSON.stringify(settings), expectedModified: '2026-09-20T00:00:00.000000Z' })
    // A first next step has no record yet: no expectedModified is sent.
    expect(bodies[1]).toEqual({ input: JSON.stringify(plan) })
    expect(bodies[2]).toEqual({ input: JSON.stringify(action), expectedModified: '2026-09-22T00:00:00.000000Z' })
  })
})

describe('Plan business reads', () => {
  const exportQuery = { scope: { sales: [], regions: [], markets: [], equipment: [] }, match: 'all' as const, conditions: [], sort: { field: 'stageChangedAt' as const, direction: 'asc' as const }, groupBy: null, page: 1, pageSize: 200 }
  it.each(['complete', 'stall'] as const)('times binary download inactivity instead of total transfer time: %s', async (ending) => {
    vi.useFakeTimers()
    try {
      let signal: AbortSignal | undefined
      let stream!: ReadableStreamDefaultController<Uint8Array>
      const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
        signal = init?.signal ?? undefined
        return new Response(new ReadableStream<Uint8Array>({ start(controller) {
          stream = controller
          signal?.addEventListener('abort', () => controller.error(new DOMException('Aborted', 'AbortError')))
        } }), { headers: { 'Content-Type': 'application/pdf', 'Content-Disposition': 'attachment; filename="large.pdf"' } })
      })
      const outcome = createFrappeApi({ fetchImpl: fetchMock as typeof fetch }).getContactFile('large-file')
        .then(value => ({ value }), error => ({ error: error as CrmApiError }))
      await vi.advanceTimersByTimeAsync(20_000)
      stream.enqueue(new TextEncoder().encode('first'))
      await vi.advanceTimersByTimeAsync(20_000)
      expect(signal?.aborted).toBe(false)
      if (ending === 'complete') {
        stream.enqueue(new TextEncoder().encode('second'))
        await vi.advanceTimersByTimeAsync(20_000)
        expect(signal?.aborted).toBe(false)
        stream.close()
        const result = await outcome
        expect(result).toMatchObject({ value: { fileName: 'large.pdf', mimeType: 'application/pdf' } })
        if ('value' in result) {
          expect(await result.value.blob.text()).toBe('firstsecond')
          expect(result.value.blob.type).toBe('application/pdf')
        }
      } else {
        // An empty chunk does not count as progress or extend a stalled download.
        stream.enqueue(new Uint8Array())
        await vi.advanceTimersByTimeAsync(9_999)
        expect(signal?.aborted).toBe(false)
        await vi.advanceTimersByTimeAsync(1)
        expect(signal?.aborted).toBe(true)
        await expect(outcome).resolves.toMatchObject({ error: { code: 'NETWORK_ERROR', retryable: true } })
      }
      expect(vi.getTimerCount()).toBe(0)
    } finally { vi.useRealTimers() }
  })
  it.each(['export', 'binary'] as const)('keeps the deadline active through a stalled %s response body', async (kind) => {
    vi.useFakeTimers()
    try {
      let signal: AbortSignal | undefined
      const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
        signal = init?.signal ?? undefined
        return new Response(new ReadableStream({ start(controller) {
          signal?.addEventListener('abort', () => controller.error(new DOMException('Aborted', 'AbortError')))
        } }))
      })
      const api = createFrappeApi({ fetchImpl: fetchMock as typeof fetch, timeoutMs: 100, exportTimeoutMs: 200 })
      const outcome = (kind === 'export' ? api.exportOpportunities(exportQuery) : api.getContactFile('file-1'))
        .then(() => null, error => error as CrmApiError)
      const deadline = kind === 'export' ? 200 : 100
      await vi.advanceTimersByTimeAsync(deadline - 1)
      expect(signal?.aborted).toBe(false)
      await vi.advanceTimersByTimeAsync(1)
      expect(signal?.aborted).toBe(true)
      await expect(outcome).resolves.toMatchObject({ code: 'NETWORK_ERROR', retryable: true })
      expect(vi.getTimerCount()).toBe(0)
    } finally { vi.useRealTimers() }
  })
  it('clears the deadline only after a delayed export body completes', async () => {
    vi.useFakeTimers()
    try {
      let signal: AbortSignal | undefined
      let stream!: ReadableStreamDefaultController<Uint8Array>
      const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
        signal = init?.signal ?? undefined
        return new Response(new ReadableStream<Uint8Array>({ start(controller) { stream = controller } }))
      })
      const exported = createFrappeApi({ fetchImpl: fetchMock as typeof fetch, exportTimeoutMs: 200 }).exportOpportunities(exportQuery)
      await vi.advanceTimersByTimeAsync(100)
      expect(vi.getTimerCount()).toBe(1)
      stream.enqueue(new TextEncoder().encode(JSON.stringify({ message: { data: { items: [] } } })))
      stream.close()
      await expect(exported).resolves.toMatchObject({ data: { items: [] } })
      expect(vi.getTimerCount()).toBe(0)
      await vi.advanceTimersByTimeAsync(200)
      expect(signal?.aborted).toBe(false)
    } finally { vi.useRealTimers() }
  })
  it('allows a full export past 30 seconds while ordinary reads still time out', async () => {
    vi.useFakeTimers()
    try {
      let finishExport!: (value: Response) => void
      let exportSignal: AbortSignal | undefined
      const fetchMock = vi.fn((url: string, init?: RequestInit) => new Promise<Response>((resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
        if (url.endsWith('export_opportunities')) { finishExport = resolve; exportSignal = init?.signal ?? undefined }
      }))
      const api = createFrappeApi({ fetchImpl: fetchMock as typeof fetch })
      const ordinary = expect(api.getBootstrap()).rejects.toMatchObject({ code: 'NETWORK_ERROR', retryable: true })
      const exported = api.exportOpportunities(exportQuery)
      await vi.advanceTimersByTimeAsync(45_000)
      await ordinary
      expect(exportSignal?.aborted).toBe(false)
      finishExport(success({ items: ['complete export'] }))
      await expect(exported).resolves.toMatchObject({ data: { items: ['complete export'] } })
      expect(vi.getTimerCount()).toBe(0)
    } finally { vi.useRealTimers() }
  })
  it.each([
    [{}, 120_000],
    [{ timeoutMs: 500 }, 500],
    [{ timeoutMs: 500, exportTimeoutMs: 2_000 }, 2_000],
  ])('keeps export timeout bounded and respects explicit overrides %j', async (options, timeout) => {
    vi.useFakeTimers()
    try {
      let signal: AbortSignal | undefined
      const fetchMock = vi.fn((_url: string, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
        signal = init?.signal ?? undefined
        signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
      }))
      const api = createFrappeApi({ ...options, fetchImpl: fetchMock as typeof fetch })
      const rejected = expect(api.exportOpportunities(exportQuery)).rejects.toMatchObject({ code: 'NETWORK_ERROR', retryable: true })
      await vi.advanceTimersByTimeAsync(timeout - 1)
      expect(signal?.aborted).toBe(false)
      await vi.advanceTimersByTimeAsync(1)
      await rejected
      expect(signal?.aborted).toBe(true)
      expect(vi.getTimerCount()).toBe(0)
    } finally { vi.useRealTimers() }
  })
  it('serializes query export, recipient lookup and sharing with the expected version', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(success({})))
    const api = createFrappeApi({ fetchImpl: fetchMock })
    const input = { scope: { sales: [], regions: [], markets: [], equipment: [] }, match: 'all' as const, conditions: [], sort: { field: 'stageChangedAt' as const, direction: 'asc' as const }, groupBy: null, page: 2, pageSize: 1, savedQuery: { id: 'shared', modified: 'v1' } }
    await api.exportOpportunities(input)
    await api.getQueryRecipients()
    await api.shareOpportunityQuery('shared', ['reader@example.invalid'], 'v2')
    expect(fetchMock.mock.calls.map(([url]) => new URL(url, 'http://localhost').pathname)).toEqual(['export_opportunities', 'get_query_recipients', 'share_opportunity_query'].map(method => '/api/method/rayher_crm.api.v1.cockpit.' + method))
    expect(fetchMock.mock.calls.map(([, init]) => init.method)).toEqual(['POST', 'GET', 'POST'])
    expect(JSON.parse(new URLSearchParams(fetchMock.mock.calls[0][1].body).get('input')!)).toEqual(input)
    const shared = new URLSearchParams(fetchMock.mock.calls[2][1].body)
    expect(shared.get('expectedModified')).toBe('v2')
    expect(JSON.parse(shared.get('recipients')!)).toEqual(['reader@example.invalid'])
  })
  it('sends future periods and identical filters to the dedicated summary and detail endpoints', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(success({})))
    const api = createFrappeApi({ fetchImpl: fetchMock })
    const query = { period: 'week' as const, anchor: '2026-09-21', sales: 'sales@example.com', region: 'East China', market: 'Advanced Packaging' }
    await api.getPlan(query)
    await api.getPlanDetails({ ...query, metric: 'po', page: 2, pageSize: 50, includeOverdue: false })
    const urls = fetchMock.mock.calls.map(([url]) => new URL(url, 'http://localhost'))
    expect(urls[1].searchParams.get('includeOverdue')).toBe('false')
    expect(urls.map(url => url.pathname)).toEqual(['/api/method/rayher_crm.api.v1.cockpit.get_plan', '/api/method/rayher_crm.api.v1.cockpit.get_plan_details'])
    for (const url of urls) for (const [key, value] of Object.entries(query)) expect(url.searchParams.get(key)).toBe(value)
    expect(urls[1].searchParams.get('metric')).toBe('po')
    expect(urls[1].searchParams.get('page')).toBe('2')
    expect(urls[1].searchParams.get('pageSize')).toBe('50')
    expect(fetchMock.mock.calls.every(([, init]) => init.method === 'GET')).toBe(true)
  })
})
