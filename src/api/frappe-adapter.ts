import type { ApiResponse } from '@/types/crm'
import type { CrmApi, CrmApiErrorCode } from './contracts'
import { CrmApiError, normalizeCrmApiErrorCode } from './contracts'
import { ClientRequestError } from './request-state'
import { localeMessage } from '@/i18n'
import { appendMultipartFile, type BinaryDownload } from './binary-transport'

const API_PREFIX = '/api/method/rayher_crm.api.v1.'
const DEFAULT_TIMEOUT_MS = 30_000
let redirectingToLogin = false

export const FRAPPE_METHODS = {
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
  listContracts: 'read_only_views.list_contracts',
  listQuotationCatalog: 'quotations.list_catalog',
  listQuotations: 'quotations.list_quotations',
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
  completeServiceBooking: 'bookings.complete_service_booking',
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
  if (status === 401 || status === 403) return localeMessage('Your session does not have permission to perform this action.', '当前会话无权执行此操作。')
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

function redirectUnauthenticated(error: CrmApiError) {
  if (error.code !== 'UNAUTHENTICATED' || typeof window === 'undefined') return
  if (redirectingToLogin) return
  if (window.location.pathname === '/login' || window.location.pathname.startsWith('/login/')) return
  redirectingToLogin = true
  const redirect = window.location.pathname + window.location.search + window.location.hash
  window.location.assign('/login?redirect-to=' + encodeURIComponent(redirect || '/crm'))
}

function throwRequestError(payload: unknown, response: Response, fallbackRequestId: string): never {
  const error = errorFromPayload(payload, response, fallbackRequestId)
  redirectUnauthenticated(error)
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

  async function send(method: string, init: RequestInit, fallbackRequestId: string) {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    try {
      return await fetchImpl(method, { ...init, signal: controller.signal })
    } catch (error) {
      throw normalizeFrappeError(error, fallbackRequestId)
    } finally {
      clearTimeout(timer)
    }
  }

  async function requestJson<T>(method: string, verb: 'GET' | 'POST', values?: RequestValues, multipart?: FormData): Promise<ApiResponse<T>> {
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
    const response = await send(url, { method: verb, credentials: 'same-origin', headers, body }, fallbackRequestId)
    const payload = await parseJson(response)
    const envelope = unwrapFrappeMessage(payload)
    if (isRecord(envelope) && isRecord(envelope.error)) throwRequestError(payload, response, fallbackRequestId)
    if (!response.ok) throwRequestError(payload, response, fallbackRequestId)
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
  }

  async function requestBinary(method: string, values: RequestValues, fallbackName: string): Promise<BinaryDownload> {
    const fallbackRequestId = requestId()
    const response = await send(methodUrl(method, values), {
      method: 'GET', credentials: 'same-origin', headers: { Accept: 'application/octet-stream' },
    }, fallbackRequestId)
    if (!response.ok) {
      const payload = await parseJson(response)
      throwRequestError(payload, response, fallbackRequestId)
    }
    return {
      blob: await response.blob(),
      fileName: parseFileName(response.headers.get('Content-Disposition'), fallbackName),
      mimeType: response.headers.get('Content-Type')?.split(';')[0]?.trim() || 'application/octet-stream',
    }
  }

  const get = <T>(key: keyof CrmApi, values?: RequestValues) => requestJson<T>(FRAPPE_METHODS[key], 'GET', values)
  const post = <T>(key: keyof CrmApi, values?: RequestValues) => requestJson<T>(FRAPPE_METHODS[key], 'POST', values)

  const api: CrmApi = {
    getBootstrap: () => get('getBootstrap'),
    changeCurrentUserPassword: (input) => post('changeCurrentUserPassword', input),
    async listNotifications(query) {
      const result = await get<Awaited<ReturnType<CrmApi['listNotifications']>>['data']['items']>('listNotifications', query as RequestValues)
      return { ...result, data: { items: result.data } }
    },
    markNotificationRead: (id) => post('markNotificationRead', { id }),
    markAllNotificationsRead: () => post('markAllNotificationsRead'),
    getDashboard: (query) => get('getDashboard', { ...query }),
    listAccounts: (query) => get('listAccounts', query as RequestValues),
    listAccountSegments: () => get('listAccountSegments'),
    listAccountCities: () => get('listAccountCities'),
    createAccount: (input) => post('createAccount', { input }),
    updateAccount: (id, input, expectedModified) => post('updateAccount', { id, input, expectedModified }),
    deleteAccount: (id) => post('deleteAccount', { id }),
    getAccount360: (id) => get('getAccount360', { id }),
    createAccountSite: (accountId, input) => post('createAccountSite', { accountId, input }),
    updateAccountSite: (accountId, siteId, input) => post('updateAccountSite', { accountId, siteId, input }),
    deleteAccountSite: (accountId, siteId) => post('deleteAccountSite', { accountId, siteId }),
    listVisits: (query) => get('listVisits', query as RequestValues),
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
    deleteLead: (id) => post('deleteLead', { id }),
    convertLead: (id, input) => post('convertLead', { id, input }),
    listStakeholders: (query) => get('listStakeholders', query as RequestValues),
    createStakeholder: (input) => post('createStakeholder', { input }),
    updateStakeholder: (id, input, expectedModified) => post('updateStakeholder', { id, input, expectedModified }),
    listRequirements: (query) => get('listRequirements', query as RequestValues),
    listPipeline: (query) => get('listPipeline', query as RequestValues),
    listBookings: (query) => get('listBookings', query as RequestValues),
    createBooking: (input) => post('createBooking', { input }),
    updateBooking: (id, input, expectedModified) => post('updateBooking', { id, input, expectedModified }),
    deleteBooking: (id) => post('deleteBooking', { id }),
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
    addEvaluationRun: (id, input) => post('addEvaluationRun', { id, input }),
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
      for (const [field, file] of [['internalFile', input.internalFile], ['externalFile', input.externalFile]] as const) {
        // Snapshot application-visible plaintext before multipart serialization.
        const content = await file.blob.arrayBuffer()
        const snapshot = new Blob([content], { type: file.mimeType })
        appendMultipartFile(form, field, { ...file, blob: snapshot, size: snapshot.size })
      }
      return requestJson(FRAPPE_METHODS.releaseDemoTestReport, 'POST', undefined, form)
    },
    listContracts: (query) => get('listContracts', query as RequestValues),
    listQuotationCatalog: () => get('listQuotationCatalog'),
    listQuotations: (query) => get('listQuotations', query as RequestValues),
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
    getStrategyOpportunity: (id) => get('getStrategyOpportunity', { id }),
    createStrategyOpportunity: (input) => post('createStrategyOpportunity', { input }),
    updateStrategyOpportunity: (id, input, expectedModified) => post('updateStrategyOpportunity', { id, input, expectedModified }),
    rollbackOpportunityStage: (id, input, expectedModified) => post('rollbackOpportunityStage', { id, input, expectedModified }),
    deleteStrategyOpportunity: (id) => post('deleteStrategyOpportunity', { id }),
    createOpportunityStakeholder: (opportunityId, input) => post('createOpportunityStakeholder', { opportunityId, input }),
    updateOpportunityStakeholder: (opportunityId, stakeholderId, input) => post('updateOpportunityStakeholder', { opportunityId, stakeholderId, input }),
    deleteOpportunityStakeholder: (opportunityId, stakeholderId) => post('deleteOpportunityStakeholder', { opportunityId, stakeholderId }),
    createOpportunityAction: (opportunityId, input) => post('createOpportunityAction', { opportunityId, input }),
    updateOpportunityAction: (opportunityId, actionId, input) => post('updateOpportunityAction', { opportunityId, actionId, input }),
    deleteOpportunityAction: (opportunityId, actionId) => post('deleteOpportunityAction', { opportunityId, actionId }),
    listDemoWorkflows: (query) => get('listDemoWorkflows', query as RequestValues),
    getDemoWorkflow: (id) => get('getDemoWorkflow', { id }),
    listDemoComments: (demoRequestId, query) => get('listDemoComments', { demoRequestId, ...query }),
    addDemoComment: (demoRequestId, input) => post('addDemoComment', { demoRequestId, input }),
    listInstalledTools: (query) => get('listInstalledTools', query as RequestValues),
    getInstalledTool: (id) => get('getInstalledTool', { id }),
    convertBookingToInstalledTool: (id, input, expectedModified) => post('convertBookingToInstalledTool', { id, input, expectedModified }),
    completeServiceBooking: (id, expectedModified) => post('completeServiceBooking', { id, expectedModified }),
    transitionInstalledTool: (id, input, expectedModified) => post('transitionInstalledTool', { id, input, expectedModified }),
    addInstalledToolVersionRecord: (id, input, expectedModified) => post('addInstalledToolVersionRecord', { id, input, expectedModified }),
    addInstalledToolServiceRecord: (id, input, expectedModified) => post('addInstalledToolServiceRecord', { id, input, expectedModified }),
    updateInstalledTool: (id, input, expectedModified) => post('updateInstalledTool', { id, input, expectedModified }),
    listControlledDocuments: (query) => get('listControlledDocuments', query as RequestValues),
    previewControlledDocument: (documentId) => requestBinary(FRAPPE_METHODS.previewControlledDocument, { documentId }, 'controlled-document-preview.pdf'),
    downloadControlledDocument: (documentId) => requestBinary(FRAPPE_METHODS.downloadControlledDocument, { documentId }, 'controlled-document.pdf'),
    requestControlledDocumentAccess: (versionId, reason) => post('requestControlledDocumentAccess', { versionId, reason }),
    listControlledDocumentRequests: (query) => get('listControlledDocumentRequests', query as RequestValues),
    decideControlledDocumentRequest: (requestId, decision) => post('decideControlledDocumentRequest', { requestId, decision }),
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
