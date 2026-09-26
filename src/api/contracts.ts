/**
 * ============================================================================
 *  CRM 后端数据库对接契约(BINDING)— Frappe / MariaDB
 * ============================================================================
 *  本文件(`CrmApi` + `CrmApiError`)是前端与后端之间的强制接口契约。
 *  后端(Frappe adapter / DocType / whitelisted method)实现 **必须**严格遵守:
 *      docs/CRM-后端数据库对接契约-2026-08-04.md
 *
 *  Frappe 是开发、staging 与 production 的唯一正式运行时;Mock adapter 仅供测试注入。
 *  下列「契约层 Gate」必须持续满足(详见契约文档 A 层,每条均带【验收标准】):
 *    A1  跨 HTTP 的 DTO 不得含 `Blob`;下载改二进制流端点、上传改 multipart
 *    A2  所有业务记录 DTO 须有 `modified`;`update*` 须带 `expectedModified`(乐观锁)
 *    A3  `owner`/`*By` 须为稳定 ID(Link→User),不得是显示名;服务端忽略客户端值
 *    A4  错误码须用冻结枚举;adapter 须实现 Frappe 异常 → CrmApiError 归一层
 *    A5  只读实体(Requirement/Contract/Action)须登记写入策略;无未实现 capability
 *    A6  create 入参不得带 `id`;命名空间不得撞车(CON- 前缀)
 *
 *  后端实现 MUST(B1–B14,含事务/权限/文件/通知/日期/分页)同样见该契约文档。
 *  合规门(Go/No-Go Checklist)必须全绿后才可作为 Stage/Production 后端验收依据。
 * ============================================================================
 */
import type {
  Account360Dto,
  AccountSummaryDto,
  ApiResponse,
  BootstrapDto,
  ContractDto,
  CreateAccountInput,
  CreateDemoRequestInput,
  CreateVisitInput,
  UpdateVisitInput,
  DashboardDto,
  DemoArtifactMetaDto,
  DemoRequestCommand,
  DemoRequestDto,
  DemoRequestImportResult,
  DemoRequestTransitionResult,
  DemoTestReportUploadInput,
  DemoTestReportUploadResult,
  CustomerReportUploadInput,
  CustomerReportUploadResult,
  EvaluationDto,
  EvaluationPreparationBranch,
  EvaluationStatusCommand,
  ListQuery,
  PageData,
  PipelineDto,
  RequirementDto,
  CreateStakeholderInput,
  UpdateStakeholderInput,
  CreateTestRunInput,
  AddEvaluationRunInput,
  SetEvaluationTestRunDeadlineInput,
  UpsertBookingInput,
  VisitDto,
  VisitDetailDto,
  VisitMeetingRecordInput,
  VisitMeetingRecordDto,
  ContactDto,
  ContactDetailDto,
  ContactFileMetaDto,
  CreateContactInput,
  UpdateContactInput,
  ContactListQuery,
  ContactSummaryDto,
  BookingDto,
  LeadConversionInput,
  LeadConversionResult,
  LeadDto,
  CreateLeadInput,
  UpdateLeadInput,
  LeadListQuery,
  SiteDto,
} from '@/types/crm'
import type {
  ControlledDocumentDto,
  ControlledDocumentAccessRequestDto,
  DocumentUploadDecisionInput,
  DocumentUploadInput,
  DocumentUploadRequestDto,
  AddInstalledToolServiceRecordInput,
  AddInstalledToolVersionRecordInput,
  ConvertBookingToInstalledToolInput,
  CreateStrategyOpportunityInput,
  DemoCommentDto,
  DemoWorkflowDto,
  InstalledToolDetailDto,
  InstalledToolDto,
  OpportunityActionDto,
  CreateOpportunityActionInput,
  UpdateOpportunityActionInput,
  OpportunityStakeholderDto,
  RollbackOpportunityStageInput,
  CreateOpportunityStakeholderInput,
  UpdateOpportunityStakeholderInput,
  StrategyOpportunityDto,
  TransitionInstalledToolInput,
  UpdateInstalledToolInput,
  UpdateStrategyOpportunityInput,
} from '@/types/workspaces'
import type { BinaryDownload, DemoArtifactUploadInput, MultipartFilePart } from './binary-transport'
import type { NotificationDto, NotificationListQuery } from '@/types/notifications'
import type { CreateQuotationInput, QuotationApprovalDecisionInput, QuotationDecisionInput, QuotationCatalogItemDto, QuotationDetailDto, QuotationDraftInput, QuotationListQuery, QuotationSummaryDto } from '@/features/quotations/types'
import type { CreateRfqInput, ReviewRfqInput, RfqDetailDto, RfqListQuery, RfqSummaryDto } from '@/features/rfqs/types'

export type CrmApiErrorCode =
  | 'UNAUTHENTICATED'
  | 'PERMISSION_DENIED'
  | 'SCOPE_DENIED'
  | 'NOT_FOUND'
  | 'VALIDATION_ERROR'
  | 'CONFLICT'
  | 'INVALID_TRANSITION'
  | 'VERSION_CONFLICT'
  | 'REPORT_NOT_READY'
  | 'RFQ_APPROVAL_REQUIRED'
  | 'BACKEND_NOT_CONNECTED'
  | 'NETWORK_ERROR'
  | 'INTERNAL_ERROR'

const CRM_API_ERROR_CODES: ReadonlySet<string> = new Set<CrmApiErrorCode>([
  'UNAUTHENTICATED', 'PERMISSION_DENIED', 'SCOPE_DENIED', 'NOT_FOUND',
  'VALIDATION_ERROR', 'CONFLICT', 'INVALID_TRANSITION', 'VERSION_CONFLICT',
  'REPORT_NOT_READY', 'RFQ_APPROVAL_REQUIRED', 'BACKEND_NOT_CONNECTED', 'NETWORK_ERROR', 'INTERNAL_ERROR',
])

const VALIDATION_CODES = new Set([
  'INVALID_OWNER', 'BOOKING_SOURCE_REQUIRED', 'CONTACT_INACTIVE', 'LINK_MISMATCH',
  'INVALID_REPORTING_LINE', 'LEAD_CONVERSION_INCOMPLETE',
])

export function normalizeCrmApiErrorCode(code: unknown, fallback: CrmApiErrorCode = 'INTERNAL_ERROR'): CrmApiErrorCode {
  if (typeof code !== 'string') return fallback
  if (CRM_API_ERROR_CODES.has(code)) return code as CrmApiErrorCode
  if (['INSTALLED_TOOL_SCOPE_DENIED', 'INSTALLED_TOOL_REASSIGN_DENIED'].includes(code)) return 'SCOPE_DENIED'
  if (code.endsWith('_NOT_FOUND')) return 'NOT_FOUND'
  if (VALIDATION_CODES.has(code)) return 'VALIDATION_ERROR'
  if (['INVALID_REPORT_STAGE', 'INVALID_RUN_STAGE', 'BOOKING_NOT_CONFIRMED', 'BOOKING_SOURCE_INVALID', 'BOOKING_STATUS_INVALID'].includes(code)) return 'INVALID_TRANSITION'
  if (code === 'EVALUATION_EXISTS') return 'REPORT_NOT_READY'
  if (['CONTACT_ACCOUNT_MISMATCH', 'SITE_ACCOUNT_MISMATCH', 'CONTACT_MERGE_CONFLICT', 'RUN_EXISTS'].includes(code)
    || code.startsWith('DUPLICATE_') || code.endsWith('_EXISTS') || code.includes('_ALREADY_') || code.endsWith('_LOCKED')) return 'CONFLICT'
  if (code === 'UPSTREAM_TIMEOUT') return 'NETWORK_ERROR'
  return fallback
}
export class CrmApiError extends Error {
  public readonly code: CrmApiErrorCode

  constructor(
    code: string,
    message: string,
    public readonly requestId: string,
    public readonly retryable = false,
    public readonly fieldErrors: Record<string, string> = {},
  ) {
    super(message)
    this.code = normalizeCrmApiErrorCode(code)
    this.name = 'CrmApiError'
  }
}

export interface DashboardQuery {
  range: 'month' | 'quarter' | 'year'
  segment?: string
}

export interface CrmApi {
  getBootstrap(): Promise<ApiResponse<BootstrapDto>>
  changeCurrentUserPassword(input: { currentPassword: string; newPassword: string }): Promise<ApiResponse<{ updated: true }>>
  listNotifications(query?: NotificationListQuery): Promise<ApiResponse<PageData<NotificationDto>>>
  markNotificationRead(id: string): Promise<ApiResponse<{ id: string; read: true; readAt: string }>>
  markAllNotificationsRead(): Promise<ApiResponse<{ updated: number; readAt: string }>>
  getDashboard(query: DashboardQuery): Promise<ApiResponse<DashboardDto>>
  listAccounts(query: ListQuery): Promise<ApiResponse<PageData<AccountSummaryDto>>>
  listAccountSegments(): Promise<ApiResponse<string[]>>
  listAccountCities(): Promise<ApiResponse<string[]>>
  createAccount(input: CreateAccountInput): Promise<ApiResponse<AccountSummaryDto>>
  updateAccount(id: string, input: CreateAccountInput, expectedModified?: string): Promise<ApiResponse<AccountSummaryDto>>
  deleteAccount(id: string): Promise<ApiResponse<{ id: string; status: 'Deleted' }>>
  getAccount360(id: string): Promise<ApiResponse<Account360Dto>>
  createAccountSite(accountId: string, input: Omit<SiteDto, 'id'>): Promise<ApiResponse<SiteDto>>
  updateAccountSite(accountId: string, siteId: string, input: Omit<SiteDto, 'id'>): Promise<ApiResponse<SiteDto>>
  deleteAccountSite(accountId: string, siteId: string): Promise<ApiResponse<{ id: string }>>
  listVisits(query: ListQuery): Promise<ApiResponse<PageData<VisitDto>>>
  getVisit(id: string): Promise<ApiResponse<VisitDto>>
  getVisitDetail(id: string): Promise<ApiResponse<VisitDetailDto>>
  createVisit(input: CreateVisitInput): Promise<ApiResponse<VisitDto>>
  submitVisitRecord(id: string, file: MultipartFilePart): Promise<ApiResponse<VisitDetailDto>>
  reviewVisit(id: string, expectedModified?: string): Promise<ApiResponse<VisitDto>>
  updateVisit(id: string, input: UpdateVisitInput, expectedModified?: string): Promise<ApiResponse<VisitDto>>
  updateVisitMeetingRecord(id: string, input: VisitMeetingRecordInput, expectedModified?: string): Promise<ApiResponse<VisitMeetingRecordDto>>
  getVisitAttachment(fileId: string): Promise<BinaryDownload>
  listContacts(query: ContactListQuery): Promise<ApiResponse<PageData<ContactSummaryDto>>>
  getContact(id: string): Promise<ApiResponse<ContactDetailDto>>
  createContact(input: CreateContactInput): Promise<ApiResponse<ContactSummaryDto>>
  updateContact(id: string, input: UpdateContactInput, expectedModified?: string): Promise<ApiResponse<ContactSummaryDto>>
  mergeContacts(input: { survivorId: string; duplicateId: string }): Promise<ApiResponse<ContactSummaryDto>>
  deleteContact(id: string): Promise<ApiResponse<{ id: string; status: 'Deleted' }>>
  listContactFiles(contactId: string, query?: ListQuery): Promise<ApiResponse<PageData<ContactFileMetaDto>>>
  uploadContactFiles(contactId: string, files: MultipartFilePart[]): Promise<ApiResponse<ContactFileMetaDto[]>>
  getContactFile(fileId: string): Promise<BinaryDownload>
  deleteContactFile(fileId: string): Promise<ApiResponse<{ id: string }>>
  listLeads(query: LeadListQuery): Promise<ApiResponse<PageData<LeadDto>>>
  getLead(id: string): Promise<ApiResponse<LeadDto>>
  createLead(input: CreateLeadInput): Promise<ApiResponse<LeadDto>>
  updateLead(id: string, input: UpdateLeadInput, expectedModified?: string): Promise<ApiResponse<LeadDto>>
  deleteLead(id: string): Promise<ApiResponse<{ id: string; status: 'Deleted' }>>
  convertLead(id: string, input: LeadConversionInput): Promise<ApiResponse<LeadConversionResult>>
  listStakeholders(query: ListQuery): Promise<ApiResponse<PageData<ContactDto>>>
  createStakeholder(input: CreateStakeholderInput): Promise<ApiResponse<ContactDto>>
  updateStakeholder(id: string, input: UpdateStakeholderInput, expectedModified?: string): Promise<ApiResponse<ContactDto>>
  /** 只读：Requirement 在迁移期为只读视图（契约 A5）；后端需裁决“锁写的 DocType + ingest 通道”或“外部视图”。 */
  listRequirements(query: ListQuery): Promise<ApiResponse<PageData<RequirementDto>>>
  listPipeline(query: ListQuery): Promise<ApiResponse<PipelineDto>>
  listBookings(query: ListQuery): Promise<ApiResponse<PageData<BookingDto>>>
  createBooking(input: UpsertBookingInput): Promise<ApiResponse<BookingDto>>
  updateBooking(id: string, input: UpsertBookingInput, expectedModified?: string): Promise<ApiResponse<BookingDto>>
  deleteBooking(id: string): Promise<ApiResponse<{ id: string; status: 'Deleted' }>>
  listDemoRequests(query: ListQuery): Promise<ApiResponse<PageData<DemoRequestDto>>>
  importDemoRequestForm(file: MultipartFilePart): Promise<ApiResponse<DemoRequestImportResult>>
  createDemoRequest(input: CreateDemoRequestInput): Promise<ApiResponse<DemoRequestDto>>
  updateDemoRequest(id: string, input: CreateDemoRequestInput, expectedModified?: string): Promise<ApiResponse<DemoRequestDto>>
  transitionDemoRequest(id: string, command: DemoRequestCommand, expectedModified?: string): Promise<ApiResponse<DemoRequestTransitionResult>>
  listEvaluations(query: ListQuery): Promise<ApiResponse<PageData<EvaluationDto>>>
  getEvaluation(id: string): Promise<ApiResponse<EvaluationDto>>
  completeEvaluationPreparation(id: string, branch: EvaluationPreparationBranch, expectedModified: string): Promise<ApiResponse<EvaluationDto>>
  updateEvaluationStatus(id: string, command: EvaluationStatusCommand, expectedModified?: string): Promise<ApiResponse<EvaluationDto>>
  addEvaluationRun(id: string, input: AddEvaluationRunInput): Promise<ApiResponse<EvaluationDto>>
  setEvaluationTestRunDeadline(id: string, input: SetEvaluationTestRunDeadlineInput): Promise<ApiResponse<EvaluationDto>>
  saveDemoArtifact(input: DemoArtifactUploadInput): Promise<ApiResponse<DemoArtifactMetaDto>>
  getDemoArtifact(id: string): Promise<BinaryDownload>
  releaseDemoTestReport(id: string, input: DemoTestReportUploadInput): Promise<ApiResponse<DemoTestReportUploadResult>>
  uploadCustomerReport(id: string, input: CustomerReportUploadInput): Promise<ApiResponse<CustomerReportUploadResult>>
  /** 只读：Contract 同上，迁移期只读。 */
  listContracts(query: ListQuery): Promise<ApiResponse<PageData<ContractDto>>>
  listQuotationCatalog(): Promise<ApiResponse<QuotationCatalogItemDto[]>>
  listQuotations(query?: QuotationListQuery): Promise<ApiResponse<PageData<QuotationSummaryDto>>>
  getQuotation(id: string, versionId?: string): Promise<ApiResponse<QuotationDetailDto>>
  createQuotation(input: CreateQuotationInput): Promise<ApiResponse<QuotationDetailDto>>
  linkQuotationOpportunity(id: string, opportunityId: string, expectedModified: string): Promise<ApiResponse<QuotationDetailDto>>
  saveQuotationDraft(id: string, input: QuotationDraftInput, expectedModified?: string): Promise<ApiResponse<QuotationDetailDto>>
  createQuotationVersion(id: string): Promise<ApiResponse<QuotationDetailDto>>
  discardQuotationDraft(id: string, expectedModified?: string): Promise<ApiResponse<QuotationDetailDto>>
  publishQuotation(id: string, expectedModified?: string): Promise<ApiResponse<QuotationDetailDto>>
  submitQuotationForApproval(id: string, expectedModified?: string): Promise<ApiResponse<QuotationDetailDto>>
  reviewQuotationApproval(id: string, input: QuotationApprovalDecisionInput): Promise<ApiResponse<QuotationDetailDto>>
  recordQuotationDecision(id: string, input: QuotationDecisionInput): Promise<ApiResponse<QuotationDetailDto>>
  getQuotationPreviewPdf(id: string, versionId?: string): Promise<BinaryDownload>
  getQuotationPdf(id: string, versionId?: string): Promise<BinaryDownload>
  listRfqs(query?: RfqListQuery): Promise<ApiResponse<PageData<RfqSummaryDto>>>
  getRfq(id: string): Promise<ApiResponse<RfqDetailDto>>
  createRfq(input: CreateRfqInput, file: MultipartFilePart): Promise<ApiResponse<RfqDetailDto>>
  reviseRfq(id: string, file: MultipartFilePart, expectedModified: string): Promise<ApiResponse<RfqDetailDto>>
  submitRfqEngineerComment(id: string, comment: string, expectedModified: string): Promise<ApiResponse<RfqDetailDto>>
  reviewRfq(id: string, input: ReviewRfqInput, expectedModified: string): Promise<ApiResponse<RfqDetailDto>>
  previewRfqFile(id: string, versionId?: string): Promise<BinaryDownload>
  downloadRfqFile(id: string, versionId?: string): Promise<BinaryDownload>
  listStrategyOpportunities(query?: ListQuery): Promise<ApiResponse<PageData<StrategyOpportunityDto>>>
  getStrategyOpportunity(id: string): Promise<ApiResponse<StrategyOpportunityDto>>
  createStrategyOpportunity(input: CreateStrategyOpportunityInput): Promise<ApiResponse<StrategyOpportunityDto>>
  updateStrategyOpportunity(id: string, input: UpdateStrategyOpportunityInput, expectedModified?: string): Promise<ApiResponse<StrategyOpportunityDto>>
  rollbackOpportunityStage(id: string, input: RollbackOpportunityStageInput, expectedModified?: string): Promise<ApiResponse<StrategyOpportunityDto>>
  deleteStrategyOpportunity(id: string): Promise<ApiResponse<{ id: string; status: 'Deleted' }>>
  createOpportunityStakeholder(opportunityId: string, input: CreateOpportunityStakeholderInput): Promise<ApiResponse<OpportunityStakeholderDto>>
  updateOpportunityStakeholder(opportunityId: string, stakeholderId: string, input: UpdateOpportunityStakeholderInput): Promise<ApiResponse<OpportunityStakeholderDto>>
  deleteOpportunityStakeholder(opportunityId: string, stakeholderId: string): Promise<ApiResponse<{ id: string }>>
  createOpportunityAction(opportunityId: string, input: CreateOpportunityActionInput): Promise<ApiResponse<OpportunityActionDto>>
  updateOpportunityAction(opportunityId: string, actionId: string, input: UpdateOpportunityActionInput): Promise<ApiResponse<OpportunityActionDto>>
  deleteOpportunityAction(opportunityId: string, actionId: string): Promise<ApiResponse<{ id: string }>>
  listDemoWorkflows(query?: ListQuery): Promise<ApiResponse<PageData<DemoWorkflowDto>>>
  getDemoWorkflow(id: string): Promise<ApiResponse<DemoWorkflowDto>>
  listDemoComments(demoRequestId: string, query?: ListQuery): Promise<ApiResponse<PageData<DemoCommentDto>>>
  addDemoComment(demoRequestId: string, input: { body: string; mentionedPersonIds?: string[] }): Promise<ApiResponse<DemoCommentDto>>
  listInstalledTools(query?: ListQuery): Promise<ApiResponse<PageData<InstalledToolDto>>>
  getInstalledTool(id: string): Promise<ApiResponse<InstalledToolDetailDto>>
  convertBookingToInstalledTool(id: string, input: ConvertBookingToInstalledToolInput, expectedModified?: string): Promise<ApiResponse<{ booking: BookingDto; installedTool: InstalledToolDto }>>
  completeServiceBooking(id: string, expectedModified?: string): Promise<ApiResponse<BookingDto>>
  transitionInstalledTool(id: string, input: TransitionInstalledToolInput, expectedModified?: string): Promise<ApiResponse<InstalledToolDetailDto>>
  addInstalledToolVersionRecord(id: string, input: AddInstalledToolVersionRecordInput, expectedModified?: string): Promise<ApiResponse<InstalledToolDetailDto>>
  addInstalledToolServiceRecord(id: string, input: AddInstalledToolServiceRecordInput, expectedModified?: string): Promise<ApiResponse<InstalledToolDetailDto>>
  updateInstalledTool(id: string, input: UpdateInstalledToolInput, expectedModified?: string): Promise<ApiResponse<InstalledToolDto>>
  listControlledDocuments(query?: ListQuery): Promise<ApiResponse<PageData<ControlledDocumentDto>>>
  previewControlledDocument(documentId: string): Promise<BinaryDownload>
  downloadControlledDocument(documentId: string): Promise<BinaryDownload>
  requestControlledDocumentAccess(versionId: string, reason: string): Promise<ApiResponse<ControlledDocumentAccessRequestDto>>
  listControlledDocumentRequests(query?: ListQuery): Promise<ApiResponse<PageData<ControlledDocumentAccessRequestDto>>>
  decideControlledDocumentRequest(requestId: string, decision: 'approve-watermarked' | 'approve-original' | 'reject' | 'more-info'): Promise<ApiResponse<ControlledDocumentAccessRequestDto>>
  submitControlledDocumentUpload(input: DocumentUploadInput, file: MultipartFilePart): Promise<ApiResponse<DocumentUploadRequestDto>>
  listControlledDocumentUploadRequests(query?: ListQuery): Promise<ApiResponse<PageData<DocumentUploadRequestDto>>>
  decideControlledDocumentUploadRequest(requestId: string, input: DocumentUploadDecisionInput): Promise<ApiResponse<DocumentUploadRequestDto>>
}
