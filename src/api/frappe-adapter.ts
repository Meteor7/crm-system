import type { ApiResponse } from '@/types/crm'
import type { CrmApi, CrmApiErrorCode } from './contracts'
import { CrmApiError, normalizeCrmApiErrorCode } from './contracts'
import { ClientRequestError } from './request-state'
import { localeMessage } from '@/i18n'
import { appendMultipartFile, type BinaryDownload } from './binary-transport'
import { SESSION_EXPIRED_EVENT, loginUrl } from './session'

const API_PREFIX = '/api/method/rayher_crm.api.v1.'
const DEFAULT_TIMEOUT_MS = 30_000
// Full-set exports share one server snapshot and may take longer than page reads.
// Match the 120-second Gunicorn/proxy budget in backend/compose.yaml.
const EXPORT_TIMEOUT_MS = 120_000
let redirectingToLogin = false

export const FRAPPE_METHODS = {
  queryOpportunities: 'cockpit.query_opportunities',
      exportOpportunities: 'cockpit.export_opportunities',
      getQueryRecipients: 'cockpit.get_query_recipients',
      shareOpportunityQuery: 'cockpit.share_opportunity_query',
  getOpportunityFilters: 'cockpit.get_opportunity_filters',
  listOpportunityQueries: 'cockpit.list_opportunity_queries',
  saveOpportunityQuery: 'cockpit.save_opportunity_query',
  deleteOpportunityQuery: 'cockpit.delete_opportunity_query',
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
  // Frappe's own endpoint, outside the rayher_crm whitelist: `signOut` below does not go through `methodUrl`.
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
  archiveAccount: 'accounts.archive_account',
  unarchiveAccount: 'accounts.unarchive_account',
  getAccount360: 'accounts.get_account_360',
  listAccountSites: 'accounts.list_account_sites',
  createAccountSite: 'accounts.create_account_site',
  updateAccountSite: 'accounts.update_account_site',
  deleteAccountSite: 'accounts.delete_account_site',
  listVisits: 'visits.list_visits',
  listEvents: 'events.list_events',
  getEvent: 'events.get_event',
  saveEvent: 'events.save_event',
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
  listQuotationCatalog: 'quotations.list_catalog',
  listQuotations: 'quotations.list_quotations',
  getQuotationPlanning: 'quotation_planning.get_planning',
  saveQuotationSchedule: 'quotation_planning.save_schedule',
  saveQuotationFollowUp: 'quotation_planning.save_follow_up',
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
  listStrategyOpportunities: 'opportunities.list_strategy_opportunities',
  listEquipmentTypes: 'opportunities.list_equipment_types',
  getStrategyOpportunity: 'opportunities.get_strategy_opportunity',
  saveBlueSheetFlags: 'opportunities.save_blue_sheet_flags',
  getBlueSheetAssessment: 'opportunities.get_blue_sheet_assessment',
  applyBlueSheetSuggestion: 'opportunities.apply_blue_sheet_suggestion',
  createStrategyOpportunity: 'opportunities.create_strategy_opportunity',
  updateStrategyOpportunity: 'opportunities.update_strategy_opportunity',
  saveProbabilityRecovery: 'opportunities.save_probability_recovery',
  recordProbabilityRecoveryAction: 'opportunities.record_probability_recovery_action',
  rollbackOpportunityStage: 'opportunities.rollback_opportunity_stage',
  confirmBudgetApproved: 'opportunities.confirm_budget_approved',
  requestInternalValidation: 'opportunities.request_internal_validation',
  reviewInternalValidation: 'opportunities.review_internal_validation',
  confirmPo: 'opportunities.confirm_po',
  markOpportunityLost: 'opportunities.mark_opportunity_lost',
  reviewOpportunityLoss: 'opportunities.review_opportunity_loss',
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
  completeServiceBooking: 'bookings.complete_service_booking',
  setBookingActualPoDate: 'bookings.set_actual_po_date',
  setBookingAmountCny: 'bookings.set_amount_cny',
  transitionInstalledTool: 'installed_tools.transition_installed_tool',
  addInstalledToolVersionRecord: 'installed_tools.add_installed_tool_version_record',
  addInstalledToolServiceRecord: 'installed_tools.add_installed_tool_service_record',
  updateInstalledTool: 'installed_tools.update_installed_tool',
  listControlledDocuments: 'read_only_views.list_controlled_documents',
  previewControlledDocument: 'controlled_documents.preview_document',
  downloadControlledDocument: 'controlled_documents.download_document',
  listRfqs: 'rfqs.list_rfqs',
  getRfq: 'rfqs.get_rfq',
  createRfq: 'rfqs.create_rfq',
  reviseRfq: 'rfqs.revise_rfq',
  submitRfqEngineerComment: 'rfqs.submit_engineer_comment',
  reviewRfq: 'rfqs.review_rfq',
  previewRfqFile: 'rfqs.preview_rfq_file',
  downloadRfqFile: 'rfqs.download_rfq_file',
  requestControlledDocumentAccess: 'read_only_views.request_controlled_document_access',
  listControlledDocumentRequests: 'read_only_views.list_controlled_document_requests',
  decideControlledDocumentRequest: 'read_only_views.decide_controlled_document_request',
  submitControlledDocumentUpload: 'document_uploads.submit_upload',
  listControlledDocumentUploadRequests: 'document_uploads.list_upload_requests',
  decideControlledDocumentUploadRequest: 'document_uploads.decide_upload_request',
} as const satisfies Record<keyof CrmApi, string>

type RequestValues = Record<string, unknown>
type JsonRecord = Record<string, unknown>

export interface FrappeApiOptions {
  fetchImpl?: typeof fetch
  timeoutMs?: number
  /** Export response wait; defaults to timeoutMs when supplied, otherwise 120s. */
  exportTimeoutMs?: number
  csrfToken?: () => string | undefined
}
function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function requestId() {
  return `frontend_req_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
}

function defaultCsrfToken() {
  if (typeof window === 'undefined') return undefined
  const frappe = (window as Window & { frappe?: { csrf_token?: unknown } }).frappe
  return typeof frappe?.csrf_token === 'string' && frappe.csrf_token ? frappe.csrf_token : undefined
}

function appendValue(target: URLSearchParams | FormData, key: string, value: unknown) {
  if (value === undefined || value === null) return
  const serialized = typeof value === 'object' ? JSON.stringify(value) : String(value)
  target.append(key, serialized)
}

function methodUrl(method: string, query?: RequestValues) {
  const url = `${API_PREFIX}${method}`
  if (!query) return url
  const params = new URLSearchParams()
  Object.entries(query).forEach(([key, value]) => appendValue(params, key, value))
  const encoded = params.toString()
  return encoded ? `${url}?${encoded}` : url
}

function unwrapFrappeMessage(payload: unknown) {
  let value = isRecord(payload) && 'message' in payload ? payload.message : payload
  if (typeof value === 'string') {
    try {
      value = JSON.parse(value)
    } catch {
      return value
    }
  }
  return value
}

function safeCode(value: unknown, fallback: CrmApiErrorCode): CrmApiErrorCode {
  return normalizeCrmApiErrorCode(value, fallback)
}

function statusCode(status: number): CrmApiErrorCode {
  if (status === 401) return 'UNAUTHENTICATED'
  if (status === 403) return 'PERMISSION_DENIED'
  if (status === 404) return 'NOT_FOUND'
  if (status === 409) return 'VERSION_CONFLICT'
  if (status === 422) return 'VALIDATION_ERROR'
  return 'INTERNAL_ERROR'
}

function statusMessage(status: number) {
  if (status === 401) return localeMessage('Your session has ended. Please sign in again.', '登录已失效，请重新登录。')
  if (status === 403) return localeMessage('Your session does not have permission to perform this action.', '当前会话无权执行此操作。')
  if (status === 409) return localeMessage('This record was changed by another user. Refresh and try again.', '记录已被其他用户修改，请刷新后重试。')
  if (status === 422) return localeMessage('The request data failed validation.', '请求数据未通过校验。')
  return status >= 500 ? localeMessage('The backend service is temporarily unavailable. Please try again later.', '后端服务暂时不可用，请稍后重试。') : localeMessage('Data request failed.', '数据请求失败。')
}

function errorFromPayload(payload: unknown, response: Response, fallbackRequestId: string) {
  const envelope = unwrapFrappeMessage(payload)
  const meta = isRecord(envelope) && isRecord(envelope.meta) ? envelope.meta : undefined
  const error = isRecord(envelope) && isRecord(envelope.error) ? envelope.error : undefined
  const resolvedRequestId = typeof meta?.requestId === 'string'
    ? meta.requestId
    : response.headers.get('X-Request-ID') || fallbackRequestId
  if (error) {
    const fallback = response.ok ? 'INTERNAL_ERROR' : statusCode(response.status)
    const fieldErrors = isRecord(error.fieldErrors)
      ? Object.fromEntries(Object.entries(error.fieldErrors).filter((entry): entry is [string, string] => typeof entry[1] === 'string'))
      : {}
    if (typeof error.message === 'string') return new CrmApiError(safeCode(error.code, fallback), error.message, resolvedRequestId, error.retryable === true, fieldErrors)
    return new ClientRequestError(
      safeCode(error.code, fallback),
      statusMessage(response.status),
      resolvedRequestId,
      error.retryable === true,
      fieldErrors,
    )
  }
  return new ClientRequestError(
    statusCode(response.status),
    statusMessage(response.status),
    resolvedRequestId,
    response.status >= 500,
  )
}

async function parseJson(response: Response) {
  const text = await response.text()
  if (!text) return undefined
  try {
    return JSON.parse(text) as unknown
  } catch {
    return undefined
  }
}

/** Frappe transport failures are normalized without exposing server exception text. */
export function normalizeFrappeError(error: unknown, fallbackRequestId: string): CrmApiError {
  if (error instanceof CrmApiError) return error
  if (error instanceof DOMException && error.name === 'AbortError') {
    return new ClientRequestError('NETWORK_ERROR', localeMessage('The backend request timed out. Please try again later.', '后端请求超时，请稍后重试。'), fallbackRequestId, true)
  }
  if (error instanceof TypeError) {
    return new ClientRequestError('NETWORK_ERROR', localeMessage('Unable to connect to the backend. Check your network and try again.', '无法连接后端服务，请检查网络后重试。'), fallbackRequestId, true)
  }
  return new ClientRequestError('INTERNAL_ERROR', localeMessage('Data request failed. Please try again later.', '数据请求失败，请稍后重试。'), fallbackRequestId, true)
}

function handleUnauthenticated(error: CrmApiError, method: string) {
  if (error.code !== 'UNAUTHENTICATED' || typeof window === 'undefined') return
  if (window.location.pathname === '/login' || window.location.pathname.startsWith('/login/')) return
  if (method !== FRAPPE_METHODS.getBootstrap) {
    // The session ended while the page was in use. Leaving on our own would discard whatever is
    // being typed, so the shell says so and offers the way to the login page instead.
    window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT))
    return
  }
  // The bootstrap runs when the page loads: nobody is signed in and nothing can be lost.
  if (redirectingToLogin) return
  redirectingToLogin = true
  window.location.assign(loginUrl())
}

function throwRequestError(payload: unknown, response: Response, fallbackRequestId: string, method: string): never {
  const error = errorFromPayload(payload, response, fallbackRequestId)
  handleUnauthenticated(error, method)
  throw error
}

function parseFileName(disposition: string | null, fallback: string) {
  if (!disposition) return fallback
  const extended = disposition.match(/filename\*\s*=\s*UTF-8''([^;]+)/i)?.[1]
  let candidate: string | undefined
  if (extended) {
    try {
      candidate = decodeURIComponent(extended.trim().replace(/^"|"$/g, ''))
    } catch {
      candidate = undefined
    }
  }
  candidate ??= disposition.match(/filename\s*=\s*(?:"([^"]+)"|([^;]+))/i)?.slice(1).find(Boolean)?.trim()
  const safe = candidate?.split(/[\\/]/).pop()?.replace(/[\u0000-\u001f]/g, '').trim()
  return safe || fallback
}

export function createFrappeApi(options: FrappeApiOptions = {}): CrmApi {
  const fetchImpl = options.fetchImpl ?? globalThis.fetch
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS
  const csrfToken = options.csrfToken ?? defaultCsrfToken

  // The requests out at the moment, so that the sign-out can wait for them: Frappe writes a session back to its
  // cache at the end of a request it authenticated, so one answered after the session was ended would revive it.
  const inFlight = new Set<Promise<unknown>>()
  // Once the sign-out is under way nothing else leaves this client (a request answered after the session was ended
  // would write it back), until the sign-out fails and the session is there to use.
  let signingOut = false

  async function send<T>(method: string, init: RequestInit, fallbackRequestId: string, consume: (response: Response, refreshDeadline: () => void) => Promise<T>, requestTimeoutMs = timeoutMs, forSignOut = false) {
    if (signingOut && !forSignOut) {
      throw new ClientRequestError('INTERNAL_ERROR', localeMessage('Signing out; the request was not sent.', '正在退出登录，请求未发送。'), fallbackRequestId)
    }
    const controller = new AbortController()
    let timer = setTimeout(() => controller.abort(), requestTimeoutMs)
    const refreshDeadline = () => {
      if (controller.signal.aborted) return
      clearTimeout(timer)
      timer = setTimeout(() => controller.abort(), requestTimeoutMs)
    }
    // Both the deadline and sign-out tracking include body consumption.
    const request = (async () => consume(await fetchImpl(method, { ...init, signal: controller.signal }), refreshDeadline))()
    inFlight.add(request)
    try {
      return await request
    } catch (error) {
      throw normalizeFrappeError(error, fallbackRequestId)
    } finally {
      clearTimeout(timer)
      inFlight.delete(request)
    }
  }

  async function requestJson<T>(method: string, verb: 'GET' | 'POST', values?: RequestValues, multipart?: FormData, requestTimeoutMs?: number): Promise<ApiResponse<T>> {
    const fallbackRequestId = requestId()
    const headers = new Headers({ Accept: 'application/json' })
    let url = methodUrl(method)
    let body: BodyInit | undefined
    if (verb === 'GET') {
      url = methodUrl(method, values)
    } else if (multipart) {
      body = multipart
    } else {
      const params = new URLSearchParams()
      Object.entries(values ?? {}).forEach(([key, value]) => appendValue(params, key, value))
      body = params
      headers.set('Content-Type', 'application/x-www-form-urlencoded;charset=UTF-8')
    }
    if (verb !== 'GET') {
      const token = csrfToken()
      if (token) headers.set('X-Frappe-CSRF-Token', token)
    }
    return send(url, { method: verb, credentials: 'same-origin', headers, body }, fallbackRequestId, async response => {
      const payload = await parseJson(response)
      const envelope = unwrapFrappeMessage(payload)
      if (isRecord(envelope) && isRecord(envelope.error)) throwRequestError(payload, response, fallbackRequestId, method)
      if (!response.ok) throwRequestError(payload, response, fallbackRequestId, method)
      if (!isRecord(envelope) || !('data' in envelope)) {
        throw new ClientRequestError('INTERNAL_ERROR', localeMessage('The backend returned an unrecognized data format.', '后端返回了无法识别的数据格式。'), fallbackRequestId, true)
      }
      return {
        data: envelope.data as T,
        meta: isRecord(envelope.meta) && typeof envelope.meta.requestId === 'string'
          ? envelope.meta as unknown as ApiResponse<T>['meta']
          : undefined,
        warnings: Array.isArray(envelope.warnings) ? envelope.warnings.filter((item): item is string => typeof item === 'string') : [],
      }
    }, requestTimeoutMs)
  }

  async function requestBinary(method: string, values: RequestValues, fallbackName: string): Promise<BinaryDownload> {
    const fallbackRequestId = requestId()
    return send(methodUrl(method, values), {
      method: 'GET', credentials: 'same-origin', headers: { Accept: 'application/octet-stream' },
    }, fallbackRequestId, async (response, refreshDeadline) => {
      if (!response.ok) {
        const payload = await parseJson(response)
        throwRequestError(payload, response, fallbackRequestId, method)
      }
      // Downloads can be large. Bound header wait and body inactivity, while allowing
      // an actively transferring file to take longer than the ordinary JSON deadline.
      refreshDeadline()
      const blob = response.body
        ? await new Response(response.body.pipeThrough(new TransformStream<Uint8Array, Uint8Array>({
          transform(chunk, stream) {
            if (chunk.byteLength) refreshDeadline()
            stream.enqueue(chunk)
          },
        })), { headers: response.headers }).blob()
        : await response.blob()
      return {
        blob,
        fileName: parseFileName(response.headers.get('Content-Disposition'), fallbackName),
        mimeType: response.headers.get('Content-Type')?.split(';')[0]?.trim() || 'application/octet-stream',
      }
    })
  }

  const get = <T>(key: keyof CrmApi, values?: RequestValues) => requestJson<T>(FRAPPE_METHODS[key], 'GET', values)
  const post = <T>(key: keyof CrmApi, values?: RequestValues, requestTimeoutMs?: number) => requestJson<T>(FRAPPE_METHODS[key], 'POST', values, undefined, requestTimeoutMs)

  const api: CrmApi = {
    getBootstrap: () => get('getBootstrap'),
    changeCurrentUserPassword: (input) => post('changeCurrentUserPassword', input),
    async signOut() {
      signingOut = true
      try {
        // The session is ended once the requests out under it are answered (none of them writes it back then), and
        // none follows them. One that timed out here may still be running on the server: not waited for.
        while (inFlight.size) await Promise.allSettled([...inFlight])
        // Frappe's own `logout`, as a GET: Frappe asks no CSRF token of a GET, and the CRM's token comes with its
        // bootstrap, which may have failed (no CRM role, a server fault) while the session is there to end.
        const fallbackRequestId = requestId()
        await send('/api/method/logout', { method: 'GET', credentials: 'same-origin', headers: { Accept: 'application/json' } }, fallbackRequestId, async response => {
          const payload = await parseJson(response)
          if (!response.ok) throwRequestError(payload, response, fallbackRequestId, FRAPPE_METHODS.signOut)
        }, timeoutMs, true)
      } catch (error) {
        // Still signed in: the page goes on using the session.
        signingOut = false
        throw error
      }
    },
    async listNotifications(query) {
      const result = await get<Awaited<ReturnType<CrmApi['listNotifications']>>['data']['items']>('listNotifications', query as RequestValues)
      return { ...result, data: { items: result.data } }
    },
    markNotificationRead: (id) => post('markNotificationRead', { id }),
    markAllNotificationsRead: () => post('markAllNotificationsRead'),
    queryOpportunities: (input) => post('queryOpportunities', { input }),
    exportOpportunities: (input) => post('exportOpportunities', { input }, options.exportTimeoutMs ?? options.timeoutMs ?? EXPORT_TIMEOUT_MS),
    getQueryRecipients: () => get('getQueryRecipients'),
    shareOpportunityQuery: (id, recipients, expectedModified) => post('shareOpportunityQuery', { id, recipients, expectedModified }),
    getOpportunityFilters: () => get('getOpportunityFilters'),
    listOpportunityQueries: () => get('listOpportunityQueries'),
    saveOpportunityQuery: (input, id, expectedModified) => post('saveOpportunityQuery', { input, id, expectedModified }),
    deleteOpportunityQuery: (id, expectedModified) => post('deleteOpportunityQuery', { id, expectedModified }),
    getPlan: (query) => get('getPlan', { ...query }),
    savePlanCommitment: (input, expectedModified) => post('savePlanCommitment', { input, expectedModified }),
    getPlanDetails: (query) => get('getPlanDetails', { ...query }),
    getReview: (query) => get('getReview', { ...query }),
    getReviewDetails: (query) => get('getReviewDetails', { ...query }),
    getWarnings: (query) => get('getWarnings', { ...query }),
    saveReviewTarget: (input, expectedModified) => post('saveReviewTarget', { input, expectedModified }),
    getReviewTarget: (query) => get('getReviewTarget', { ...query }),
    getTerritoryCatalogue: () => get('getTerritoryCatalogue'),
    saveTerritory: (input, name, expectedModified) => post('saveTerritory', { input, name, expectedModified }),
    saveTerritoryAssignment: (input, name, expectedModified) => post('saveTerritoryAssignment', { input, name, expectedModified }),
    getCockpitSettings: () => get('getCockpitSettings'),
    saveCockpitSettings: (input, expectedModified) => post('saveCockpitSettings', { input, expectedModified }),
    saveWarningPlan: (input, expectedModified) => post('saveWarningPlan', { input, expectedModified }),
    recordWarningAction: (input, expectedModified) => post('recordWarningAction', { input, expectedModified }),
    getDashboard: (query) => get('getDashboard', { ...query }),
    listAccounts: (query) => get('listAccounts', query as RequestValues),
    listAccountSegments: () => get('listAccountSegments'),
    listAccountRegions: () => get('listAccountRegions'),
    listAccountCities: () => get('listAccountCities'),
    createAccount: (input) => post('createAccount', { input }),
    updateAccount: (id, input, expectedModified) => post('updateAccount', { id, input, expectedModified }),
    archiveAccount: (id) => post('archiveAccount', { id }),
    unarchiveAccount: (id) => post('unarchiveAccount', { id }),
    getAccount360: (id) => get('getAccount360', { id }),
    listAccountSites: () => get('listAccountSites'),
    createAccountSite: (accountId, input) => post('createAccountSite', { accountId, input }),
    updateAccountSite: (accountId, siteId, input) => post('updateAccountSite', { accountId, siteId, input }),
    deleteAccountSite: (accountId, siteId) => post('deleteAccountSite', { accountId, siteId }),
    listVisits: (query) => get('listVisits', query as RequestValues),
    listEvents: query => get('listEvents', query as RequestValues),
    getEvent: id => get('getEvent', { id }),
    saveEvent: (input, id, expectedModified) => post('saveEvent', { input, id, expectedModified }),
    getVisit: (id) => get('getVisit', { id }),
    getVisitDetail: (id) => get('getVisitDetail', { id }),
    createVisit: (input) => post('createVisit', { input }),
    async submitVisitRecord(id, file) {
      const form = new FormData()
      form.append('visitId', id)
      appendMultipartFile(form, 'file', file)
      return requestJson(FRAPPE_METHODS.submitVisitRecord, 'POST', undefined, form)
    },
    reviewVisit: (id, expectedModified) => post('reviewVisit', { id, expectedModified }),
    // `command.type` is the backend command discriminator, so the visit type travels as `visitType`.
    updateVisit: (id, { type, ...rest }, expectedModified) => post('updateVisit', { id, command: { type: 'edit', ...rest, visitType: type }, expectedModified }),
    updateVisitMeetingRecord: (id, input, expectedModified) => post('updateVisitMeetingRecord', { id, input, expectedModified }),
    getVisitAttachment: (fileId) => requestBinary(FRAPPE_METHODS.getVisitAttachment, { fileId }, 'meeting-record-file'),
    listContacts: (query) => get('listContacts', query as RequestValues),
    getContact: (id) => get('getContact', { id }),
    createContact: (input) => post('createContact', { input }),
    updateContact: (id, input, expectedModified) => post('updateContact', { id, input, expectedModified }),
    mergeContacts: (input) => post('mergeContacts', { input }),
    deleteContact: (id) => post('deleteContact', { id }),
    listContactFiles: (contactId, query) => get('listContactFiles', { contactId, ...query }),
    uploadContactFiles(contactId, files) {
      const form = new FormData()
      form.append('contactId', contactId)
      files.forEach((file) => appendMultipartFile(form, 'files', file))
      return requestJson(FRAPPE_METHODS.uploadContactFiles, 'POST', undefined, form)
    },
    getContactFile: (fileId) => requestBinary(FRAPPE_METHODS.getContactFile, { fileId }, 'contact-file.bin'),
    deleteContactFile: (fileId) => post('deleteContactFile', { fileId }),
    listLeads: (query) => get('listLeads', query as RequestValues),
    getLead: (id) => get('getLead', { id }),
    createLead: (input) => post('createLead', { input }),
    updateLead: (id, input, expectedModified) => post('updateLead', { id, input, expectedModified }),
    archiveLead: (id) => post('archiveLead', { id }),
    unarchiveLead: (id) => post('unarchiveLead', { id }),
    convertLead: (id, input) => post('convertLead', { id, input }),
    listStakeholders: (query) => get('listStakeholders', query as RequestValues),
    createStakeholder: (input) => post('createStakeholder', { input }),
    updateStakeholder: (id, input, expectedModified) => post('updateStakeholder', { id, input, expectedModified }),
    listRequirements: (query) => get('listRequirements', query as RequestValues),
    listPipeline: (query) => get('listPipeline', query as RequestValues),
    listBookings: (query) => get('listBookings', query as RequestValues),
    createBooking: (input) => post('createBooking', { input }),
    updateBooking: (id, input, expectedModified) => post('updateBooking', { id, input, expectedModified }),
    getBooking: (id) => get('getBooking', { id }),
    archiveBooking: (id) => post('archiveBooking', { id }),
    unarchiveBooking: (id) => post('unarchiveBooking', { id }),
    listDemoRequests: (query) => get('listDemoRequests', query as RequestValues),
    async importDemoRequestForm(file) {
      const content = await file.blob.arrayBuffer()
      const snapshot = new Blob([content], { type: file.mimeType })
      const form = new FormData()
      appendMultipartFile(form, 'file', { ...file, blob: snapshot, size: snapshot.size })
      return requestJson(FRAPPE_METHODS.importDemoRequestForm, 'POST', undefined, form)
    },
    createDemoRequest: (input) => post('createDemoRequest', { input }),
    updateDemoRequest: (id, input, expectedModified) => post('updateDemoRequest', { id, input, expectedModified }),
    transitionDemoRequest: (id, command, expectedModified) => post('transitionDemoRequest', { id, command, expectedModified }),
    listEvaluations: (query) => get('listEvaluations', query as RequestValues),
    getEvaluation: (id) => get('getEvaluation', { id }),
    completeEvaluationPreparation: (id, branch, expectedModified) => post('completeEvaluationPreparation', { id, branch, expectedModified }),
    updateEvaluationStatus: (id, command, expectedModified) => post('updateEvaluationStatus', { id, command, expectedModified }),
    terminateEvaluation: (id, reason, expectedModified) => post('terminateEvaluation', { id, reason, expectedModified }),
    addEvaluationRun: (id, input) => post('addEvaluationRun', { id, input }),
    updateEvaluationRun: (id, runId, input) => post('updateEvaluationRun', { id, runId, input }),
    cancelEvaluationRun: (id, runId, input) => post('cancelEvaluationRun', { id, runId, input }),
    setEvaluationTestRunDeadline: (id, input) => post('setEvaluationTestRunDeadline', { id, input }),
    saveDemoArtifact(input) {
      const form = new FormData()
      appendValue(form, 'demoRequestId', input.demoRequestId)
      appendValue(form, 'evaluationId', input.evaluationId)
      appendValue(form, 'type', input.type)
      appendValue(form, 'visibility', input.visibility)
      appendMultipartFile(form, 'file', input.file)
      return requestJson(FRAPPE_METHODS.saveDemoArtifact, 'POST', undefined, form)
    },
    getDemoArtifact: (id) => requestBinary(FRAPPE_METHODS.getDemoArtifact, { artifactId: id }, 'demo-artifact.bin'),
    async releaseDemoTestReport(id, input) {
      const form = new FormData()
      appendValue(form, 'id', id)
      appendValue(form, 'expectedRound', input.expectedRound)
      for (const [field, file] of [['internalFile', input.internalFile], ['externalFile', input.externalFile]] as const) {
        // Snapshot application-visible plaintext before multipart serialization.
        const content = await file.blob.arrayBuffer()
        const snapshot = new Blob([content], { type: file.mimeType })
        appendMultipartFile(form, field, { ...file, blob: snapshot, size: snapshot.size })
      }
      return requestJson(FRAPPE_METHODS.releaseDemoTestReport, 'POST', undefined, form)
    },
    async uploadCustomerReport(id, input) {
      const form = new FormData()
      appendValue(form, 'id', id)
      appendValue(form, 'expectedRound', input.expectedRound)
      // Snapshot application-visible plaintext before multipart serialization.
      const content = await input.file.blob.arrayBuffer()
      const snapshot = new Blob([content], { type: input.file.mimeType })
      appendMultipartFile(form, 'file', { ...input.file, blob: snapshot, size: snapshot.size })
      return requestJson(FRAPPE_METHODS.uploadCustomerReport, 'POST', undefined, form)
    },
    listContracts: (query) => get('listContracts', query as RequestValues),
    listQuotationCatalog: () => get('listQuotationCatalog'),
    listQuotations: (query) => get('listQuotations', query as RequestValues),
    getQuotationPlanning: quotationId => get('getQuotationPlanning', { quotationId }),
    saveQuotationSchedule: (quotationId, input, expectedModified) => post('saveQuotationSchedule', { quotationId, input, expectedModified }),
    saveQuotationFollowUp: (quotationId, input, id, expectedModified) => post('saveQuotationFollowUp', { quotationId, input, id, expectedModified }),
    getQuotation: (id, versionId) => get('getQuotation', { id, versionId }),
    createQuotation: (input) => post('createQuotation', { input }),
    linkQuotationOpportunity: (id, opportunityId, expectedModified) => post('linkQuotationOpportunity', { id, opportunityId, expectedModified }),
    saveQuotationDraft: (id, input, expectedModified) => post('saveQuotationDraft', { id, input, expectedModified }),
    createQuotationVersion: (id) => post('createQuotationVersion', { id }),
    discardQuotationDraft: (id, expectedModified) => post('discardQuotationDraft', { id, expectedModified }),
    publishQuotation: (id, expectedModified) => post('publishQuotation', { id, expectedModified }),
    submitQuotationForApproval: (id, expectedModified) => post('submitQuotationForApproval', { id, expectedModified }),
    reviewQuotationApproval: (id, input) => post('reviewQuotationApproval', { id, ...input }),
    recordQuotationDecision: (id, input) => post('recordQuotationDecision', { id, ...input }),
    getQuotationPreviewPdf: (id, versionId) => requestBinary(FRAPPE_METHODS.getQuotationPreviewPdf, { id, versionId }, 'quotation-preview.pdf'),
    getQuotationPdf: (id, versionId) => requestBinary(FRAPPE_METHODS.getQuotationPdf, { id, versionId }, 'quotation.pdf'),
    listStrategyOpportunities: (query) => get('listStrategyOpportunities', query as RequestValues),
    listEquipmentTypes: () => get('listEquipmentTypes'),
    getStrategyOpportunity: (id) => get('getStrategyOpportunity', { id }),
    saveBlueSheetFlags: (id, input, expectedModified) => post('saveBlueSheetFlags', { id, input, expectedModified }),
    getBlueSheetAssessment: (id) => get('getBlueSheetAssessment', { id }),
    applyBlueSheetSuggestion: (id, input, expectedModified) => post('applyBlueSheetSuggestion', { id, input, expectedModified }),
    createStrategyOpportunity: (input) => post('createStrategyOpportunity', { input }),
    updateStrategyOpportunity: (id, input, expectedModified) => post('updateStrategyOpportunity', { id, input, expectedModified }),
    saveProbabilityRecovery: (id, eventId, input, expectedModified) => post('saveProbabilityRecovery', { id, eventId, input, expectedModified }),
    recordProbabilityRecoveryAction: (id, eventId, input, expectedModified) => post('recordProbabilityRecoveryAction', { id, eventId, input, expectedModified }),
    rollbackOpportunityStage: (id, input, expectedModified) => post('rollbackOpportunityStage', { id, input, expectedModified }),
    confirmBudgetApproved: (id, input, expectedModified) => post('confirmBudgetApproved', { id, input, expectedModified }),
    requestInternalValidation: (id, input, expectedModified) => post('requestInternalValidation', { id, input, expectedModified }),
    reviewInternalValidation: (id, input, expectedModified) => post('reviewInternalValidation', { id, input, expectedModified }),
    confirmPo: (id, input, expectedModified) => post('confirmPo', { id, input, expectedModified }),
    markOpportunityLost: (id, input, expectedModified) => post('markOpportunityLost', { id, input, expectedModified }),
    reviewOpportunityLoss: (id, reviewId, input, expectedModified) => post('reviewOpportunityLoss', { id, reviewId, input, expectedModified }),
    archiveStrategyOpportunity: (id) => post('archiveStrategyOpportunity', { id }),
    unarchiveStrategyOpportunity: (id) => post('unarchiveStrategyOpportunity', { id }),
    createOpportunityStakeholder: (opportunityId, input) => post('createOpportunityStakeholder', { opportunityId, input }),
    updateOpportunityStakeholder: (opportunityId, stakeholderId, input) => post('updateOpportunityStakeholder', { opportunityId, stakeholderId, input }),
    deleteOpportunityStakeholder: (opportunityId, stakeholderId) => post('deleteOpportunityStakeholder', { opportunityId, stakeholderId }),
    listOpportunityStatuses: (opportunityId) => get('listOpportunityStatuses', { opportunityId }),
    getOpportunityDocuments: (opportunityId) => get('getOpportunityDocuments', { opportunityId }),
    saveOpportunityDocumentLinks: (opportunityId, input, expectedModified) => post('saveOpportunityDocumentLinks', { opportunityId, input, expectedModified }),
    saveOpportunityStatus(opportunityId, input, files) {
      const form = new FormData()
      form.append('opportunityId', opportunityId)
      form.append('input', JSON.stringify(input))
      files.forEach((file) => appendMultipartFile(form, 'files', file))
      return requestJson(FRAPPE_METHODS.saveOpportunityStatus, 'POST', undefined, form)
    },
    getOpportunityStatusFile: (opportunityId, recordId, fileId) => requestBinary(FRAPPE_METHODS.getOpportunityStatusFile, { opportunityId, recordId, fileId }, 'status-file'),
    createOpportunityAction: (opportunityId, input) => post('createOpportunityAction', { opportunityId, input }),
    updateOpportunityAction: (opportunityId, actionId, input) => post('updateOpportunityAction', { opportunityId, actionId, input }),
    deleteOpportunityAction: (opportunityId, actionId) => post('deleteOpportunityAction', { opportunityId, actionId }),
    listDemoWorkflows: (query) => get('listDemoWorkflows', query as RequestValues),
    getDemoWorkflow: (id) => get('getDemoWorkflow', { id }),
    getDemoResources: () => get('getDemoResources'),
    saveDemoResource: (input, id, expectedModified) => post('saveDemoResource', { input, id, expectedModified }),
    getDemoUnavailability: (resourceId) => get('getDemoUnavailability', { resourceId }),
    saveDemoUnavailability: (resourceId, input, id, expectedModified) => post('saveDemoUnavailability', { resourceId, input, id, expectedModified }),
    getDemoResourceSchedule: (evaluationId) => get('getDemoResourceSchedule', { evaluationId }),
    saveDemoResourceSchedule: (evaluationId, input, expectedModified) => post('saveDemoResourceSchedule', { evaluationId, input, expectedModified }),
    listDemoComments: (demoRequestId, query) => get('listDemoComments', { demoRequestId, ...query }),
    addDemoComment: (demoRequestId, input) => post('addDemoComment', { demoRequestId, input }),
    listInstalledTools: (query) => get('listInstalledTools', query as RequestValues),
    getInstalledTool: (id) => get('getInstalledTool', { id }),
    convertBookingToInstalledTool: (id, input, expectedModified) => post('convertBookingToInstalledTool', { id, input, expectedModified }),
    completeServiceBooking: (id, expectedModified) => post('completeServiceBooking', { id, expectedModified }),
    setBookingActualPoDate: (id, input, expectedModified) => post('setBookingActualPoDate', { id, input, expectedModified }),
    setBookingAmountCny: (id, input, expectedModified) => post('setBookingAmountCny', { id, input, expectedModified }),
    transitionInstalledTool: (id, input, expectedModified) => post('transitionInstalledTool', { id, input, expectedModified }),
    addInstalledToolVersionRecord: (id, input, expectedModified) => post('addInstalledToolVersionRecord', { id, input, expectedModified }),
    addInstalledToolServiceRecord: (id, input, expectedModified) => post('addInstalledToolServiceRecord', { id, input, expectedModified }),
    updateInstalledTool: (id, input, expectedModified) => post('updateInstalledTool', { id, input, expectedModified }),
    listControlledDocuments: (query) => get('listControlledDocuments', query as RequestValues),
    previewControlledDocument: (documentId) => requestBinary(FRAPPE_METHODS.previewControlledDocument, { documentId }, 'controlled-document-preview.pdf'),
    downloadControlledDocument: (documentId) => requestBinary(FRAPPE_METHODS.downloadControlledDocument, { documentId }, 'controlled-document.pdf'),
    requestControlledDocumentAccess: (versionId, reason) => post('requestControlledDocumentAccess', { versionId, reason }),
    listControlledDocumentRequests: (query) => get('listControlledDocumentRequests', query as RequestValues),
    decideControlledDocumentRequest: (requestId, decision, note) => post('decideControlledDocumentRequest', { requestId, decision, ...(note ? { note } : {}) }),
    submitControlledDocumentUpload(input, file) {
      const form = new FormData()
      Object.entries(input).forEach(([key, value]) => appendValue(form, key, value))
      appendMultipartFile(form, 'file', file)
      return requestJson(FRAPPE_METHODS.submitControlledDocumentUpload, 'POST', undefined, form)
    },
    listControlledDocumentUploadRequests: (query) => get('listControlledDocumentUploadRequests', query as RequestValues),
    decideControlledDocumentUploadRequest: (requestId, input) => post('decideControlledDocumentUploadRequest', { requestId, input }),
    listRfqs: (query) => get('listRfqs', query as RequestValues),
    getRfq: (id) => get('getRfq', { id }),
    createRfq(input, file) {
      const form = new FormData()
      Object.entries(input).forEach(([key, value]) => appendValue(form, key, value))
      appendMultipartFile(form, 'file', file)
      return requestJson(FRAPPE_METHODS.createRfq, 'POST', undefined, form)
    },
    reviseRfq(id, file, expectedModified) {
      const form = new FormData()
      appendValue(form, 'id', id)
      appendValue(form, 'expectedModified', expectedModified)
      appendMultipartFile(form, 'file', file)
      return requestJson(FRAPPE_METHODS.reviseRfq, 'POST', undefined, form)
    },
    submitRfqEngineerComment: (id, comment, expectedModified) => post('submitRfqEngineerComment', { id, input: { comment }, expectedModified }),
    reviewRfq: (id, input, expectedModified) => post('reviewRfq', { id, input, expectedModified }),
    previewRfqFile: (id, versionId) => requestBinary(FRAPPE_METHODS.previewRfqFile, { id, versionId }, 'rfq-preview.pdf'),
    downloadRfqFile: (id, versionId) => requestBinary(FRAPPE_METHODS.downloadRfqFile, { id, versionId }, 'rfq-file'),
  }
  return api
}
