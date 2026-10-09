import type { Territory, TerritoryInput, TerritoryAssignment, TerritoryAssignmentInput, TerritoryCatalogue } from '@/features/territories/types'
import type { BoardFilters, BoardQuery, BoardResult, SavedBoardQuery, SaveBoardQueryInput } from '@/features/opportunity-board/types'
import type { DemoResource, DemoResourceInput, DemoResourceCatalogue, DemoUnavailability, DemoUnavailabilityInput, DemoResourceSchedule, DemoResourceScheduleInput } from '@/features/demo-resources/types'
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
import type { PlanDto, PlanQuery, PlanDetails, PlanDetailQuery, PlanCommitment, PlanCommitmentInput } from '@/features/cockpit/plan-types'
import type { EventDto, EventInput } from '@/features/events/types'
import type { CockpitSettings, CockpitSettingsInput, ReviewDto, ReviewQuery, ReviewDetails, Target, TargetInput, WarningActionInput, WarningHandling, WarningPlanInput, WarningsDto } from '@/features/cockpit/types'
import type {
  Account360Dto,
  AccountSiteDto,
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
  UpdateEvaluationRunInput,
  CancelEvaluationRunInput,
  SetEvaluationTestRunDeadlineInput,
  SetActualPoDateInput,
  SetBookingAmountCnyInput,
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
  BookingPageData,
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
  ConfirmBudgetApprovedInput,
  RequestInternalValidationInput,
  ReviewInternalValidationInput,
  ConfirmPoInput,
  MarkOpportunityLostInput,
  CreateOpportunityStakeholderInput,
  UpdateOpportunityStakeholderInput,
  StrategyOpportunityDto,
  StrategyOpportunityListQuery,
  StrategyOpportunityPageData,
  TransitionInstalledToolInput,
  UpdateInstalledToolInput,
  UpdateStrategyOpportunityInput,
} from '@/types/workspaces'
import type { BinaryDownload, DemoArtifactUploadInput, MultipartFilePart } from './binary-transport'
import type { NotificationDto, NotificationListQuery } from '@/types/notifications'
import type { QuotationFollowUpInput, QuotationPlanning, CreateQuotationInput, QuotationApprovalDecisionInput, QuotationDecisionInput, QuotationCatalogItemDto, QuotationDetailDto, QuotationDraftInput, QuotationListQuery, QuotationSummaryDto } from '@/features/quotations/types'
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
  queryOpportunities(input: BoardQuery): Promise<ApiResponse<BoardResult>>
  exportOpportunities(input: BoardQuery): Promise<ApiResponse<BoardResult>>
  getQueryRecipients(): Promise<ApiResponse<{ items: Array<{ value: string; label: string }> }>>
  shareOpportunityQuery(id: string, recipients: string[], expectedModified: string): Promise<ApiResponse<SavedBoardQuery>>
  getOpportunityFilters(): Promise<ApiResponse<BoardFilters>>
  listOpportunityQueries(): Promise<ApiResponse<{ items: SavedBoardQuery[] }>>
  saveOpportunityQuery(input: SaveBoardQueryInput, id?: string, expectedModified?: string): Promise<ApiResponse<SavedBoardQuery>>
  deleteOpportunityQuery(id: string, expectedModified: string): Promise<ApiResponse<{ id: string; status: 'Deleted' }>>
  getPlan(query: PlanQuery): Promise<ApiResponse<PlanDto>>
  savePlanCommitment(input: PlanCommitmentInput, expectedModified?: string): Promise<ApiResponse<PlanCommitment>>
  getPlanDetails(query: PlanDetailQuery): Promise<ApiResponse<PlanDetails>>
  getReview(query: ReviewQuery): Promise<ApiResponse<ReviewDto>>
  getReviewDetails(query: ReviewQuery & { metric: string; page?: number; pageSize?: number }): Promise<ApiResponse<ReviewDetails>>
  getWarnings(query: ReviewQuery): Promise<ApiResponse<WarningsDto>>
  saveReviewTarget(input: TargetInput, expectedModified?: string): Promise<ApiResponse<Target>>
  getReviewTarget(query: Omit<TargetInput, 'value'>): Promise<ApiResponse<Target | null>>
  // Warnings handling (Manager): thresholds, a warning's next step, and the action taken on a stage 6 row.
  // expectedModified is null until the record exists.
  getTerritoryCatalogue(): Promise<ApiResponse<TerritoryCatalogue>>
  saveTerritory(input: TerritoryInput, name?: string, expectedModified?: string): Promise<ApiResponse<Territory>>
  saveTerritoryAssignment(input: TerritoryAssignmentInput, name?: string, expectedModified?: string): Promise<ApiResponse<TerritoryAssignment>>
  getCockpitSettings(): Promise<ApiResponse<CockpitSettings>>
  saveCockpitSettings(input: CockpitSettingsInput, expectedModified: string | null): Promise<ApiResponse<CockpitSettings>>
  saveWarningPlan(input: WarningPlanInput, expectedModified: string | null): Promise<ApiResponse<WarningHandling>>
  recordWarningAction(input: WarningActionInput, expectedModified: string | null): Promise<ApiResponse<WarningHandling>>
  getBootstrap(): Promise<ApiResponse<BootstrapDto>>
  changeCurrentUserPassword(input: { currentPassword: string; newPassword: string }): Promise<ApiResponse<{ updated: true }>>
  /** Ends the signed-in session on the server (Frappe's own `logout`); the page then goes to the login page. */
  signOut(): Promise<void>
  listNotifications(query?: NotificationListQuery): Promise<ApiResponse<PageData<NotificationDto>>>
  markNotificationRead(id: string): Promise<ApiResponse<{ id: string; read: true; readAt: string }>>
  markAllNotificationsRead(): Promise<ApiResponse<{ updated: number; readAt: string }>>
  getDashboard(query: DashboardQuery): Promise<ApiResponse<DashboardDto>>
  listAccounts(query: ListQuery): Promise<ApiResponse<PageData<AccountSummaryDto>>>
  listAccountSegments(): Promise<ApiResponse<string[]>>
  listAccountRegions(): Promise<ApiResponse<string[]>>
  listAccountCities(): Promise<ApiResponse<string[]>>
  createAccount(input: CreateAccountInput): Promise<ApiResponse<AccountSummaryDto>>
  updateAccount(id: string, input: CreateAccountInput, expectedModified?: string): Promise<ApiResponse<AccountSummaryDto>>
  /** A Manager archives an Account in place of deleting it: out of the list, the pickers and the figures with its Sites and Contacts, read-only, restorable. */
  archiveAccount(id: string): Promise<ApiResponse<AccountSummaryDto>>
  /** Brings an archived Account back as it was (Manager). */
  unarchiveAccount(id: string): Promise<ApiResponse<AccountSummaryDto>>
  getAccount360(id: string): Promise<ApiResponse<Account360Dto>>
  /** Every Site the user may read, across Accounts, in one request. */
  listAccountSites(): Promise<ApiResponse<AccountSiteDto[]>>
  createAccountSite(accountId: string, input: Omit<SiteDto, 'id'>): Promise<ApiResponse<SiteDto>>
  updateAccountSite(accountId: string, siteId: string, input: Omit<SiteDto, 'id'>): Promise<ApiResponse<SiteDto>>
  deleteAccountSite(accountId: string, siteId: string): Promise<ApiResponse<{ id: string }>>
  listEvents(query: ListQuery): Promise<ApiResponse<PageData<EventDto>>>
  getEvent(id: string): Promise<ApiResponse<EventDto>>
  saveEvent(input: EventInput, id?: string, expectedModified?: string): Promise<ApiResponse<EventDto>>
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
  /** Manager only. The Lead leaves the list and the figures and keeps all it holds; a converted Lead is refused. */
  archiveLead(id: string): Promise<ApiResponse<LeadDto>>
  /** Manager only. The Lead is back as it was. */
  unarchiveLead(id: string): Promise<ApiResponse<LeadDto>>
  convertLead(id: string, input: LeadConversionInput): Promise<ApiResponse<LeadConversionResult>>
  listStakeholders(query: ListQuery): Promise<ApiResponse<PageData<ContactDto>>>
  createStakeholder(input: CreateStakeholderInput): Promise<ApiResponse<ContactDto>>
  updateStakeholder(id: string, input: UpdateStakeholderInput, expectedModified?: string): Promise<ApiResponse<ContactDto>>
  /** 只读：Requirement 在迁移期为只读视图（契约 A5）；后端需裁决“锁写的 DocType + ingest 通道”或“外部视图”。 */
  listRequirements(query: ListQuery): Promise<ApiResponse<PageData<RequirementDto>>>
  listPipeline(query: ListQuery): Promise<ApiResponse<PipelineDto>>
  listBookings(query: ListQuery): Promise<ApiResponse<BookingPageData>>
  createBooking(input: UpsertBookingInput): Promise<ApiResponse<BookingDto>>
  updateBooking(id: string, input: UpsertBookingInput, expectedModified?: string): Promise<ApiResponse<BookingDto>>
  getBooking(id: string): Promise<ApiResponse<BookingDto>>
  /** Manager only. An Upsell Booking leaves the list, the pipeline, the figures and the reminders and keeps all it holds; an Opportunity Booking (cancel it instead) and a completed one (a delivered order) are refused. */
  archiveBooking(id: string): Promise<ApiResponse<BookingDto>>
  /** Manager only. The Booking is back as it was. */
  unarchiveBooking(id: string): Promise<ApiResponse<BookingDto>>
  listDemoRequests(query: ListQuery): Promise<ApiResponse<PageData<DemoRequestDto>>>
  importDemoRequestForm(file: MultipartFilePart): Promise<ApiResponse<DemoRequestImportResult>>
  createDemoRequest(input: CreateDemoRequestInput): Promise<ApiResponse<DemoRequestDto>>
  updateDemoRequest(id: string, input: CreateDemoRequestInput, expectedModified?: string): Promise<ApiResponse<DemoRequestDto>>
  transitionDemoRequest(id: string, command: DemoRequestCommand, expectedModified?: string): Promise<ApiResponse<DemoRequestTransitionResult>>
  listEvaluations(query: ListQuery): Promise<ApiResponse<PageData<EvaluationDto>>>
  getEvaluation(id: string): Promise<ApiResponse<EvaluationDto>>
  completeEvaluationPreparation(id: string, branch: EvaluationPreparationBranch, expectedModified: string): Promise<ApiResponse<EvaluationDto>>
  updateEvaluationStatus(id: string, command: EvaluationStatusCommand, expectedModified?: string): Promise<ApiResponse<EvaluationDto>>
  terminateEvaluation(id: string, reason: string, expectedModified: string): Promise<ApiResponse<EvaluationDto>>
  addEvaluationRun(id: string, input: AddEvaluationRunInput): Promise<ApiResponse<EvaluationDto>>
  updateEvaluationRun(id: string, runId: string, input: UpdateEvaluationRunInput): Promise<ApiResponse<EvaluationDto>>
  cancelEvaluationRun(id: string, runId: string, input: CancelEvaluationRunInput): Promise<ApiResponse<EvaluationDto>>
  setEvaluationTestRunDeadline(id: string, input: SetEvaluationTestRunDeadlineInput): Promise<ApiResponse<EvaluationDto>>
  saveDemoArtifact(input: DemoArtifactUploadInput): Promise<ApiResponse<DemoArtifactMetaDto>>
  getDemoArtifact(id: string): Promise<BinaryDownload>
  releaseDemoTestReport(id: string, input: DemoTestReportUploadInput): Promise<ApiResponse<DemoTestReportUploadResult>>
  uploadCustomerReport(id: string, input: CustomerReportUploadInput): Promise<ApiResponse<CustomerReportUploadResult>>
  /** 只读：Contract 同上，迁移期只读。 */
  listContracts(query: ListQuery): Promise<ApiResponse<PageData<ContractDto>>>
  listQuotationCatalog(): Promise<ApiResponse<QuotationCatalogItemDto[]>>
  listQuotations(query?: QuotationListQuery): Promise<ApiResponse<PageData<QuotationSummaryDto>>>
  getQuotationPlanning(quotationId: string): Promise<ApiResponse<QuotationPlanning>>
  saveQuotationSchedule(quotationId: string, input: { plannedSendDate: string | null }, expectedModified: string): Promise<ApiResponse<QuotationPlanning>>
  saveQuotationFollowUp(quotationId: string, input: QuotationFollowUpInput, id: string | undefined, expectedModified: string): Promise<ApiResponse<QuotationPlanning>>
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
  listStrategyOpportunities(query?: StrategyOpportunityListQuery): Promise<ApiResponse<StrategyOpportunityPageData>>
  /** Equipment type options: the five presets, then custom types in the order they were added. */
  listEquipmentTypes(): Promise<ApiResponse<string[]>>
  getStrategyOpportunity(id: string): Promise<ApiResponse<StrategyOpportunityDto>>
  saveBlueSheetFlags(id: string, input: { items: import('@/types/workspaces').BlueSheetRedFlagInput[] }, expectedModified: string): Promise<ApiResponse<StrategyOpportunityDto>>
  getBlueSheetAssessment(id: string): Promise<ApiResponse<import('@/types/workspaces').BlueSheetAssessment>>
  applyBlueSheetSuggestion(id: string, input: import('@/types/workspaces').BlueSheetConfirmation, expectedModified: string): Promise<ApiResponse<StrategyOpportunityDto>>
  createStrategyOpportunity(input: CreateStrategyOpportunityInput): Promise<ApiResponse<StrategyOpportunityDto>>
  updateStrategyOpportunity(id: string, input: UpdateStrategyOpportunityInput, expectedModified?: string): Promise<ApiResponse<StrategyOpportunityDto>>
  saveProbabilityRecovery(id: string, eventId: string, input: import('@/types/workspaces').SaveProbabilityRecoveryInput, expectedModified: string): Promise<ApiResponse<import('@/types/workspaces').ProbabilityRecoveryDto>>
  recordProbabilityRecoveryAction(id: string, eventId: string, input: import('@/types/workspaces').RecordProbabilityRecoveryActionInput, expectedModified: string): Promise<ApiResponse<import('@/types/workspaces').ProbabilityRecoveryDto>>
  /** Manager only (deal:rollback). A lost Opportunity reopens at or below the stage it was lost at. */
  rollbackOpportunityStage(id: string, input: RollbackOpportunityStageInput, expectedModified?: string): Promise<ApiResponse<StrategyOpportunityDto>>
  /** demo_done -> customer_budget_approved with the declared approval date. */
  confirmBudgetApproved(id: string, input: ConfirmBudgetApprovedInput, expectedModified?: string): Promise<ApiResponse<StrategyOpportunityDto>>
  /** At quotation_sent; the stage does not change until another Manager approves. */
  requestInternalValidation(id: string, input: RequestInternalValidationInput, expectedModified?: string): Promise<ApiResponse<StrategyOpportunityDto>>
  /** deal:internal_validation_approve. Approval creates a Pending Booking and moves to internal_validation. */
  reviewInternalValidation(id: string, input: ReviewInternalValidationInput, expectedModified?: string): Promise<ApiResponse<StrategyOpportunityDto>>
  /** Confirms the PO from quotation_sent or internal_validation, or replaces a cancelled Booking at po_received. */
  confirmPo(id: string, input: ConfirmPoInput, expectedModified?: string): Promise<ApiResponse<StrategyOpportunityDto>>
  /** Only at the open stages and without a live Booking. */
  markOpportunityLost(id: string, input: MarkOpportunityLostInput, expectedModified?: string): Promise<ApiResponse<StrategyOpportunityDto>>
  reviewOpportunityLoss(id: string, reviewId: string, input: import('@/types/workspaces').LossReviewInput, expectedModified: string): Promise<ApiResponse<import('@/types/workspaces').LossReviewDto>>
  /** Manager only. The Opportunity leaves every list, the board, the cockpit and the warnings, keeps all it holds and is read-only, its Quotations frozen with it; refused while a Booking of its own is not cancelled or a Demo Request or demo test of its own has not ended. */
  archiveStrategyOpportunity(id: string): Promise<ApiResponse<StrategyOpportunityDto>>
  /** Manager only. The Opportunity is back as it was. */
  unarchiveStrategyOpportunity(id: string): Promise<ApiResponse<StrategyOpportunityDto>>
  createOpportunityStakeholder(opportunityId: string, input: CreateOpportunityStakeholderInput): Promise<ApiResponse<OpportunityStakeholderDto>>
  updateOpportunityStakeholder(opportunityId: string, stakeholderId: string, input: UpdateOpportunityStakeholderInput): Promise<ApiResponse<OpportunityStakeholderDto>>
  deleteOpportunityStakeholder(opportunityId: string, stakeholderId: string): Promise<ApiResponse<{ id: string }>>
  listOpportunityStatuses(opportunityId: string): Promise<ApiResponse<import('@/features/opportunities/status-types').OpportunityStatusRecord[]>>
  getOpportunityDocuments(opportunityId: string): Promise<ApiResponse<import('@/features/opportunities/document-types').OpportunityDocuments>>
  saveOpportunityDocumentLinks(opportunityId: string, input: Partial<Record<import('@/features/opportunities/document-types').ScorecardKey, string>>, expectedModified: string): Promise<ApiResponse<import('@/features/opportunities/document-types').OpportunityDocumentLinks>>
  saveOpportunityStatus(opportunityId: string, input: import('@/features/opportunities/status-types').SaveOpportunityStatusInput, files: MultipartFilePart[]): Promise<ApiResponse<import('@/features/opportunities/status-types').OpportunityStatusRecord>>
  getOpportunityStatusFile(opportunityId: string, recordId: string, fileId: string): Promise<BinaryDownload>
  createOpportunityAction(opportunityId: string, input: CreateOpportunityActionInput): Promise<ApiResponse<OpportunityActionDto>>
  updateOpportunityAction(opportunityId: string, actionId: string, input: UpdateOpportunityActionInput): Promise<ApiResponse<OpportunityActionDto>>
  deleteOpportunityAction(opportunityId: string, actionId: string): Promise<ApiResponse<{ id: string }>>
  listDemoWorkflows(query?: ListQuery): Promise<ApiResponse<PageData<DemoWorkflowDto>>>
  getDemoWorkflow(id: string): Promise<ApiResponse<DemoWorkflowDto>>
  getDemoResources(): Promise<ApiResponse<DemoResourceCatalogue>>
  saveDemoResource(input: DemoResourceInput, id?: string, expectedModified?: string): Promise<ApiResponse<DemoResource>>
  getDemoUnavailability(resourceId: string): Promise<ApiResponse<DemoUnavailability[]>>
  saveDemoUnavailability(resourceId: string, input: DemoUnavailabilityInput, id?: string, expectedModified?: string): Promise<ApiResponse<DemoUnavailability>>
  getDemoResourceSchedule(evaluationId: string): Promise<ApiResponse<DemoResourceSchedule>>
  saveDemoResourceSchedule(evaluationId: string, input: DemoResourceScheduleInput, expectedModified: string): Promise<ApiResponse<DemoResourceSchedule>>
  listDemoComments(demoRequestId: string, query?: ListQuery): Promise<ApiResponse<PageData<DemoCommentDto>>>
  addDemoComment(demoRequestId: string, input: { body: string; mentionedPersonIds?: string[] }): Promise<ApiResponse<DemoCommentDto>>
  listInstalledTools(query?: ListQuery): Promise<ApiResponse<PageData<InstalledToolDto>>>
  getInstalledTool(id: string): Promise<ApiResponse<InstalledToolDetailDto>>
  convertBookingToInstalledTool(id: string, input: ConvertBookingToInstalledToolInput, expectedModified?: string): Promise<ApiResponse<{ booking: BookingDto; installedTool: InstalledToolDto }>>
  completeServiceBooking(id: string, expectedModified?: string): Promise<ApiResponse<BookingDto>>
  /** Manager only: fill in or correct the actual PO date of a Confirmed or Completed Booking. */
  setBookingActualPoDate(id: string, input: SetActualPoDateInput, expectedModified?: string): Promise<ApiResponse<BookingDto>>
  setBookingAmountCny(id: string, input: SetBookingAmountCnyInput, expectedModified?: string): Promise<ApiResponse<BookingDto>>
  transitionInstalledTool(id: string, input: TransitionInstalledToolInput, expectedModified?: string): Promise<ApiResponse<InstalledToolDetailDto>>
  addInstalledToolVersionRecord(id: string, input: AddInstalledToolVersionRecordInput, expectedModified?: string): Promise<ApiResponse<InstalledToolDetailDto>>
  addInstalledToolServiceRecord(id: string, input: AddInstalledToolServiceRecordInput, expectedModified?: string): Promise<ApiResponse<InstalledToolDetailDto>>
  updateInstalledTool(id: string, input: UpdateInstalledToolInput, expectedModified?: string): Promise<ApiResponse<InstalledToolDto>>
  listControlledDocuments(query?: ListQuery): Promise<ApiResponse<PageData<ControlledDocumentDto>>>
  previewControlledDocument(documentId: string): Promise<BinaryDownload>
  downloadControlledDocument(documentId: string): Promise<BinaryDownload>
  requestControlledDocumentAccess(versionId: string, reason: string): Promise<ApiResponse<ControlledDocumentAccessRequestDto>>
  listControlledDocumentRequests(query?: ListQuery): Promise<ApiResponse<PageData<ControlledDocumentAccessRequestDto>>>
  decideControlledDocumentRequest(requestId: string, decision: 'approve-watermarked' | 'approve-original' | 'reject' | 'more-info', note?: string): Promise<ApiResponse<ControlledDocumentAccessRequestDto>>
  submitControlledDocumentUpload(input: DocumentUploadInput, file: MultipartFilePart): Promise<ApiResponse<DocumentUploadRequestDto>>
  listControlledDocumentUploadRequests(query?: ListQuery): Promise<ApiResponse<PageData<DocumentUploadRequestDto>>>
  decideControlledDocumentUploadRequest(requestId: string, input: DocumentUploadDecisionInput): Promise<ApiResponse<DocumentUploadRequestDto>>
}
