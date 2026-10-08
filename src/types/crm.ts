export type Tone = 'neutral' | 'info' | 'positive' | 'warning' | 'danger'

export type PersonnelRole = 'Manager' | 'Sales' | 'Engineer'
export type UserRole = PersonnelRole
/** Frappe User.name. In this project it is an ASCII email and is never a display name. */
export type UserId = string

export type Capability =
  | 'cockpit:view'
  | 'dashboard:view'
  | 'account:view' | 'account:write'
  | 'stakeholder:view' | 'stakeholder:write'
  | 'contact:view' | 'contact:write' | 'contact:merge' | 'contact:delete'
  | 'requirement:view'
  | 'deal:view' | 'deal:write' | 'deal:rollback' | 'deal:internal_validation_approve'
  | 'visit:view' | 'visit:create' | 'visit:write' | 'visit:review'
  | 'event:view' | 'event:write'
  | 'demo_request:view' | 'demo_request:create' | 'demo_request:engineering_review' | 'demo_request:manager_approve'
  | 'evaluation:view' | 'evaluation:write'
  | 'installed_tool:write'
  | 'service:view'
  | 'contract:view'
  | 'quotation:view' | 'quotation:write' | 'quotation:submit' | 'quotation:approve' | 'quotation:publish'
  | 'rfq:view' | 'rfq:create' | 'rfq:engineer_comment' | 'rfq:manager_approve'

export interface ApiMeta {
  requestId: string
  page?: number
  pageSize?: number
  total?: number
  generatedAt?: string
  staleAt?: string
}

export interface ApiResponse<T> {
  data: T
  meta?: ApiMeta
  warnings: string[]
}

export interface PageData<T> {
  items: T[]
}

export interface BootstrapDto {
  user: {
    id: UserId
    name: string
    initials: string
    role: UserRole
    team: string
  }
  capabilities: Capability[]
  version: string
  csrfToken?: string
  personnel?: Array<{
    id: UserId
    availableForAssignment: boolean
    name: string
    initials: string
    role: PersonnelRole
    team: string
    teamOwners: UserId[]
    assignedAccountIds: string[]
  }>
}

export interface ListQuery {
  search?: string
  segment?: string
  city?: string
  region?: string
  status?: string
  accountId?: string
  owner?: string
  type?: string
  dateFrom?: string
  dateTo?: string
  contactId?: string
  opportunityId?: string
  source?: string
  /** '1' lists Confirmed and Completed Bookings whose actual PO date is missing. */
  actualPoDateMissing?: string
  /** '1' lists only what is still in progress: Demo Requests not Converted or Cancelled, Demo Tests not Accepted or Rejected. */
  inProgress?: string
  /** Bookings: also return the count and totals of everything the query matches, read in the same request as the page. */
  summary?: boolean
  page?: number
  pageSize?: number
}

/** Count and totals of every Booking a list query matches, whatever page is shown. */
export interface BookingSummaryDto {
  count: number
  pendingCount: number
  confirmed: {
    count: number
    totals: Array<{ currency: string; amount: DecimalAmount }>
  }
}

export interface BookingPageData extends PageData<BookingDto> {
  /** Present when the query asked for it. */
  summary?: BookingSummaryDto
}

export interface AccountSummaryDto {
  id: string
  name: string
  shortName: string
  segment: string
  tier: 'S' | 'A' | 'B'
  city: string
  region: string
  owner: string
  visibility?: 'Private' | 'Public'
  customerKind?: '' | 'Prospect' | 'Existing'
  /** A Sales user who does not own the Account gets its Sites, pipeline, intent, next step and risk zeroed: no numbers, not zeroes. */
  metricsRestricted?: boolean
  /** Known open Opportunity amounts only. */
  pipelineAmount: number
  /** Open Opportunities whose amount is not entered yet, left out of pipelineAmount. */
  pipelineMissingAmountCount?: number
  intentScore: number
  stakeholderCount: number
  siteCount: number
  requirementCount: number
  completeness: number
  risk: '稳健' | '关注' | '高风险'
  nextAction: string
  nextActionDue: string
  updatedAt: string
  modified?: string
}

export interface CreateAccountInput {
  name: string
  shortName: string
  segment: AccountSummaryDto['segment']
  tier: AccountSummaryDto['tier']
  city: string
  region: string
  owner: string
  visibility?: 'Private' | 'Public'
  /** The user looked at the Accounts named like this one and says this is another company. */
  confirmDuplicate?: boolean
  customerKind?: '' | 'Prospect' | 'Existing'
}

export interface SiteDto {
  id: string
  name: string
  city: string
  type: string
  process: string
  status: '量产' | '建设中' | '规划中'
}

/** A Site read across Accounts, with the Account it belongs to. */
export type AccountSiteDto = SiteDto & { accountId: string }

export type BuyingRole = 'Decision Maker' | 'Economic Buyer' | 'Champion' | 'Technical Champion' | 'Technical Evaluator' | 'Procurement' | 'Influencer' | 'Blocker' | 'User'

export type ContactStatus = 'Active' | 'Left Company' | 'Archived'
export type ContactDataQuality = 'Complete' | 'Needs Review'

export interface ContactDto {
  id: string
  accountId: string
  siteId?: string
  name: string
  title: string
  department: string
  phone?: string
  email?: string
  reportsToContactId?: string
  relationship: 'Strong' | 'Developing' | 'Weak'
  owner: string
  status: ContactStatus
  dataQuality: ContactDataQuality
  mergedIntoContactId?: string
  updatedAt: string
  modified?: string
  /** @deprecated Contact buying-role data belongs to an Opportunity relationship. */
  role?: BuyingRole
  /** @deprecated Contact buying influence belongs to an Opportunity relationship. */
  influence?: 'High' | 'Medium' | 'Low'
  /** @deprecated Use reportsToContactId. */
  reportsTo?: string
}

export interface ContactSummaryDto extends ContactDto {
  accountName: string
  accountShortName: string
  siteName?: string
  opportunityRoles: string[]
}

export type CreateContactInput = Omit<ContactDto, 'id' | 'dataQuality' | 'updatedAt' | 'modified'>
export type UpdateContactInput = CreateContactInput

export interface ContactFileMetaDto {
  id: string
  contactId: string
  fileName: string
  mimeType: string
  size: number
  uploadedAt: string
  uploadedBy: string
}

export interface ContactListQuery extends ListQuery {
  siteId?: string
  contactId?: string
  contactStatus?: ContactStatus | 'All'
}

export interface ContactTimelineItemDto {
  id: string
  at: string
  type: 'Opportunity' | 'Visit' | 'Demo Request' | 'Booking'
  title: string
  summary: string
  href: string
}

export interface ContactDetailDto {
  contact: ContactSummaryDto
  reportsTo?: ContactSummaryDto
  directReports: ContactSummaryDto[]
  opportunities: Array<{ id: string; title: string; stage: string; role: string; href: string }>
  visits: Array<{ id: string; subject: string; date: string; href: string }>
  demoRequests: Array<{ id: string; title: string; status: string; href: string }>
  bookings: Array<{ id: string; title: string; status: string; href: string }>
  timeline: ContactTimelineItemDto[]
}

export type LeadStatus = 'New' | 'Working' | 'Qualified' | 'Nurturing' | 'Disqualified' | 'Converted'
export type LeadSource = 'Website' | 'Trade Show' | 'Partner Referral' | 'Outbound' | 'Customer Referral' | 'Other'

export interface LeadActivityDto {
  id: string
  action: string
  dueDate: string
}

export interface LeadDto {
  id: string
  name: string
  company: string
  title: string
  phone?: string
  email?: string
  source: LeadSource
  status: LeadStatus
  owner: string
  interest: string
  firstContactNote: string
  nextAction: string
  nextActionDue: string
  activities?: LeadActivityDto[]
  createdAt: string
  updatedAt: string
  modified?: string
  convertedAt?: string
  convertedAccountId?: string
  convertedContactId?: string
  convertedOpportunityId?: string
  convertedReusedAccount?: boolean
  convertedReusedContact?: boolean
}

export type CreateLeadInput = Omit<LeadDto, 'id' | 'createdAt' | 'updatedAt' | 'modified' | 'convertedAt' | 'convertedAccountId' | 'convertedContactId' | 'convertedOpportunityId' | 'convertedReusedAccount' | 'convertedReusedContact'>
export type UpdateLeadInput = CreateLeadInput

export interface LeadListQuery extends ListQuery {
  source?: LeadSource | 'All'
}

export interface LeadConversionInput {
  accountId?: string
  contactId?: string
  siteId?: string
  newAccount?: CreateAccountInput
  newSite?: Omit<SiteDto, 'id'>
  newContact?: Omit<CreateContactInput, 'accountId' | 'siteId' | 'reportsToContactId'>
  opportunityTitle: string
  /** '' leaves the amount of the new qualified_opportunity not entered yet. */
  opportunityAmount: DecimalAmount | ''
  /** The new Opportunity's amount in CNY, entered by Sales; '' leaves it not entered yet. */
  opportunityAmountCny: DecimalAmount | ''
  opportunityCloseDate: string
  opportunityOwner: string
  toolType: string
  /** Whoever converts sets the new Opportunity's first level. */
  opportunityProbabilityLevel: OpportunityProbabilityLevel
  /** Sales confirms the customer need and the budget owner; conversion requires `true`. */
  qualificationConfirmed?: boolean
}

export interface LeadConversionResult {
  lead: LeadDto
  accountId: string
  contactId: string
  opportunityId: string
  reusedAccount: boolean
  reusedContact: boolean
}

/** @deprecated Compatibility input for the legacy Stakeholders page. */
export interface CreateStakeholderInput {
  accountId: string
  name: string
  title: string
  department: string
  role: BuyingRole
  influence: 'High' | 'Medium' | 'Low'
  relationship: ContactDto['relationship']
  reportsTo?: string
  email?: string
}

/** @deprecated Compatibility input for the legacy Stakeholders page. */
export type UpdateStakeholderInput = CreateStakeholderInput

export interface RequirementDto {
  id: string
  accountId: string
  accountName: string
  title: string
  category: string
  equipment: string
  application: string
  site: string
  quantity: number
  budgetAmount: number
  budgetStatus: 'Confirmed' | 'In Review' | 'Unknown'
  status: '需求识别' | '技术确认' | 'Demo验证' | '预算审批' | '采购计划' | '已确认'
  completeness: number
  owner: string
  nextAction: string
  due: string
  linkedDealId?: string
  linkedEvaluationId?: string
  modified?: string
}

export interface OpportunityDto {
  id: string
  accountId: string
  accountName: string
  title: string
  segment: AccountSummaryDto['segment']
  /** '' until someone enters it (allowed at qualified_opportunity), never a believable 0. */
  amount: DecimalAmount | ''
  currency: string
  stage: OpportunityStage
  probabilityLevel: OpportunityProbabilityLevelValue
  intentScore: number
  budgetStatus: RequirementDto['budgetStatus']
  owner: string
  nextAction: string
  due: string
  sourceRequirementId?: string
  saleType?: string
  modified?: string
}

export type BookingSource = 'Opportunity' | 'Upsell'
export type BookingType = 'Equipment' | 'Service'
/** Where a Booking's actual PO date came from. */
export type ActualPoDateSource = 'po_confirmation' | 'booking_entry' | 'backfill'

export interface BookingDto {
  id: string
  accountId: string
  accountName: string
  title: string
  primaryContactId: string
  customerContact: string
  equipment: string
  quantity: number
  ddl: string
  amount: DecimalAmount
  currency: string
  status: 'Confirmed' | 'Pending' | 'Completed' | 'Cancelled'
  bookingDate: string
  /** Date on the customer's PO (YYYY-MM-DD), empty until recorded. Not the Opportunity's expected poDate. */
  actualPoDate?: string
  actualPoDateSource?: ActualPoDateSource | ''
  /** Reason given with the latest Manager correction. */
  actualPoDateNote?: string
  /** The order's amount in CNY: the amount of a CNY Booking, '' until entered for another currency. */
  amountCny?: DecimalAmount | ''
  /** Reason given with the latest Manager correction of the CNY amount. */
  amountCnyNote?: string
  owner: string
  source: BookingSource
  bookingType?: BookingType
  sourceOpportunityId: string
  installedToolId?: string
  installedToolConvertedAt?: string
  note: string
  modified?: string
}

export interface UpsertBookingInput {
  accountId: string
  primaryContactId: string
  equipment: string
  quantity: number
  ddl: string
  amount: DecimalAmount
  currency: string
  status: BookingDto['status']
  owner: string
  source: BookingSource
  bookingType?: BookingType
  sourceOpportunityId: string
  note: string
  /** Optional on an Upsell Booking; once recorded, only a Manager's correction changes it. */
  actualPoDate?: string
  /** Required for a confirmed Booking in another currency; ignored for CNY. */
  amountCny?: DecimalAmount | ''
}

export interface SetBookingAmountCnyInput {
  amountCny: DecimalAmount
  /** Required when the Booking already has a CNY amount. */
  reason?: string
}

export interface SetActualPoDateInput {
  /** YYYY-MM-DD, not later than today. */
  actualPoDate: string
  /** Required when the Booking already has a date. */
  reason?: string
}

export type DemoRequestStatus = 'Draft' | 'Engineer Review' | 'Engineer Returned' | 'Manager Approval' | 'Manager Rejected' | 'Converted' | 'Cancelled'
export type DemoRequestPriority = 'Critical' | 'High' | 'Medium' | 'Low'
export type DemoLifecycleStage = 'Engineer Review' | 'Manager Approval' | 'Test Preparation' | 'Test Execution' | 'Internal Review' | 'Customer Review'
export type DemoHealthLevel = 'healthy' | 'stalled' | 'critical'

export interface DemoTrackingDto {
  lastProgressAt: string
  lastProgressSummary: string
  lastProgressActor: string
  nextAction: string
  nextActionOwner: string
  nextActionDue: string
}

export interface DemoHealthDto {
  level: DemoHealthLevel
  reason: string
  daysSinceProgress: number
  daysToCustomerExpected: number | null
}

export type DemoArtifactType = 'Demo Request DOCX' | 'Test Report' | 'Customer Report'

export interface DemoArtifactMetaDto {
  id: string
  demoRequestId: string
  evaluationId?: string
  type: DemoArtifactType
  fileName: string
  mimeType: string
  version: number
  round?: number
  createdBy: string
  createdAt: string
  visibility: 'Internal' | 'Customer Review'
}

export interface DemoWaferDetailDto {
  slotId: string
  wid: string
  waferSpecificity: string
  notchFlat: string
  doiMetrologyItems: string
  resultFileProvided: string
}

export interface DemoRequestFormData {
  contactPerson: string
  industry: string
  salesContact: string
  demoOwner: string
  sizeShape: string
  material: string
  specificRequest: string
  detectMeasure: string
  expectedResults: string
  otherTools: string
  primaryTool: string
  complementaryTool: string
  timing: string
  keySuccessFactors: string
  internalQuestions: string
  customerQuestions: string
  wafers: DemoWaferDetailDto[]
}

export interface DemoRequestImportResult {
  fileName: string
  companyName: string
  formData: DemoRequestFormData
  detectedFields: string[]
}

export interface DemoRequestHistoryDto {
  at: string
  actor: string
  from: DemoRequestStatus | ''
  to: DemoRequestStatus
  comment: string
}

export interface DemoRequestDto {
  id: string
  accountId: string
  accountName: string
  primaryContactId: string
  requirementId?: string
  opportunityId?: string
  requestMode: 'Opportunity' | 'Self Test'
  segment: AccountSummaryDto['segment']
  salesOwner: string
  createdBy: string
  title: string
  objective: string
  requestedEquipment: string
  sampleType: string
  sampleQuantity: number
  targetDate: string
  customerExpectedDate: string
  priority: DemoRequestPriority
  acceptanceCriteria: string
  status: DemoRequestStatus
  engineerOwner: string
  feasibility: '' | 'Pending' | 'Feasible' | 'Need More Info'
  testPlan: string
  assignedEquipment: string
  resourceWindow: string
  estimatedCompletionDate: string
  technicalRisk: string
  engineerComment: string
  managerDecision: '' | 'Pending' | 'Approved' | 'Rejected'
  managerComment: string
  tracking: DemoTrackingDto
  formData?: DemoRequestFormData
  preparedBy?: string
  preparedDate?: string
  approvedBy?: string
  approvedDate?: string
  evaluationId?: string
  createdAt: string
  updatedAt: string
  modified?: string
  history: DemoRequestHistoryDto[]
}

export interface CreateDemoRequestInput {
  accountId?: string
  primaryContactId?: string
  requirementId?: string
  opportunityId?: string
  requestMode: 'Opportunity' | 'Self Test'
  formData: DemoRequestFormData
  customerExpectedDate: string
  submit?: boolean
}

export type DemoRequestCommand =
  | { type: 'submit' }
  | { type: 'cancel'; comment?: string }
  | { type: 'engineer_return'; comment: string }
  | { type: 'engineer_approve'; engineerOwner: string; testPlan: string; assignedEquipment: string; resourceWindow: string; estimatedCompletionDate: string; technicalRisk: string; comment: string }
  | { type: 'manager_reject'; comment: string }
  | { type: 'manager_approve'; comment: string }

export type EvaluationStatus = 'Requested' | 'Scope Confirmed' | 'Sample Received' | 'Scheduled' | 'Testing' | 'Analysis' | 'Internal Review' | 'Customer Review' | 'Accepted' | 'Rejected'

export interface TestRunDto {
  id: string
  date: string
  lot: string
  /** Test round the run belongs to; a retest opens a new round and only that round's runs gate Internal Review. */
  round: number
  wafers: number
  /** Cancelled keeps the record with its reason in `summary`; it no longer counts as a plan or towards wafers. */
  status: 'Planned' | 'Completed' | 'Cancelled'
  capture: number | null
  falsePositive: number | null
  wph: number | null
  summary: string
}

export type CreateTestRunInput = Omit<TestRunDto, 'id' | 'status' | 'round'>
export type AddEvaluationRunInput = CreateTestRunInput & { expectedModified?: string }
/** Same fields as a new run: without results the Planned run is rescheduled or edited, with results it is completed. */
export type UpdateEvaluationRunInput = CreateTestRunInput & { expectedModified: string }
export type CancelEvaluationRunInput = { reason: string; expectedModified: string }
export type SetEvaluationTestRunDeadlineInput = { testRunDeadline: string; expectedModified?: string }

export type EvaluationPreparationBranch = 'wafer' | 'test'
export type EvaluationPreparationStatus = 'Pending' | 'Completed'

export interface EvaluationHistoryDto {
  id: string
  actor: string
  at: string
  eventType: 'Created' | 'Status' | 'Preparation' | 'Test Run' | 'Deadline' | 'Report'
  from: string
  to: string
  summary: string
}

export interface EvaluationCustomerReviewDto {
  id: string
  round: number
  comment: string
  author: string
  createdAt: string
}

export interface EvaluationDto {
  id: string
  accountId: string
  accountName: string
  requirementId?: string
  demoRequestId?: string
  segment: AccountSummaryDto['segment']
  title: string
  status: EvaluationStatus
  owner: string
  plannedEnd: string
  testRunDeadline: string
  wafers: number
  acceptance: 'Pending' | 'Accepted' | 'Rejected'
  reportStatus: 'Not Ready' | 'Ready'
  reportArtifactId?: string
  reportArtifact?: DemoArtifactMetaDto
  internalReportArtifactId?: string
  internalReportArtifact?: DemoArtifactMetaDto
  externalReportArtifactId?: string
  externalReportArtifact?: DemoArtifactMetaDto
  reportVersion: number
  customerReportArtifactId?: string
  customerReportArtifact?: DemoArtifactMetaDto
  testRound: number
  customerReviews?: EvaluationCustomerReviewDto[]
  criteria?: string
  /** Set only when a Demo was terminated mid-flight; historical Rejected records leave it blank. */
  terminationReason?: string
  runs: TestRunDto[]
  history?: EvaluationHistoryDto[]
  waferPreparationStatus?: EvaluationPreparationStatus
  waferPreparationCompletedBy?: string
  waferPreparationCompletedAt?: string
  testPreparationStatus?: EvaluationPreparationStatus
  testPreparationCompletedBy?: string
  testPreparationCompletedAt?: string
  modified?: string
}

export interface DemoTestReportUploadInput {
  internalFile: MultipartFilePart
  externalFile: MultipartFilePart
  // The round the uploader was looking at. A retest opens a new round, so a window left
  // open across one is refused instead of filing its report against the wrong round.
  expectedRound: number
}

export interface DemoTestReportUploadResult {
  internalReportArtifact: DemoArtifactMetaDto
  externalReportArtifact: DemoArtifactMetaDto
  version: number
}

export interface CustomerReportUploadInput {
  file: MultipartFilePart
  expectedRound: number
}

export interface CustomerReportUploadResult {
  artifact: DemoArtifactMetaDto
  round: number
  version: number
}

export interface EvaluationStatusCommand {
  status: EvaluationStatus
  customerComment?: string
}

export interface ContractDto {
  id: string
  accountId: string
  opportunityId?: string
  accountName: string
  segment: AccountSummaryDto['segment']
  type: 'NDA' | 'Evaluation Agreement' | 'Service Contract' | 'Sales Contract'
  status: 'Draft' | 'Unsigned' | 'Active' | 'Expired' | 'Terminated'
  signed: boolean
  amount: number
  start: string
  end: string
  owner: string
  modified?: string
}

export interface DemoRequestTransitionResult {
  request: DemoRequestDto
  evaluation?: EvaluationDto
}

export interface ActionDto {
  id: string
  accountId: string
  opportunityId?: string
  title: string
  owner: string
  due: string
  status: 'Open' | 'Completed'
  sourceType: 'Requirement' | 'Visit' | 'Deal' | 'Demo Request' | 'Evaluation' | 'Contract'
  modified?: string
}

export type VisitStatus = 'Planned' | 'Visited' | 'Minutes Submitted' | 'Manager Reviewed'

export interface VisitDto {
  id: string
  accountId: string
  primaryContactId?: string
  opportunityId?: string
  accountName: string
  segment: AccountSummaryDto['segment']
  subject: string
  date: string
  type: 'On-site' | 'Video' | 'Phone'
  status: VisitStatus
  owner: string
  objective: string
  outcome: string
  nextAction: string
  actionOwner: string
  due: string
  actionDone: boolean
  customerKind?: '' | 'Prospect' | 'Existing'
  customerKindCapturedAt?: string | null
  completedAt?: string | null
  modified?: string
}

export type MeetingRecordParseStatus = 'Parsed' | 'NeedsManualReview' | 'ArchiveOnly' | 'Failed'

export interface VisitMeetingRecordDto {
  id: string
  visitId: string
  meetingStart: string
  meetingEnd: string
  purpose: string
  attendees: string
  agenda: string
  summary: string
  conclusion: string
  followup: string
  parseStatus: MeetingRecordParseStatus
  parseMessage: string
  parsedAt: string
  manuallyCorrected: boolean
  modified?: string
}

export interface VisitAttachmentDto {
  id: string
  visitId: string
  fileName: string
  mimeType: string
  size: number
  uploadedAt: string
  uploadedBy: string
}

export interface VisitDetailDto extends VisitDto {
  primaryContact?: ContactSummaryDto
  meetingRecord: VisitMeetingRecordDto | null
  attachments: VisitAttachmentDto[]
}

export interface VisitMeetingRecordInput {
  meetingStart?: string
  meetingEnd?: string
  purpose: string
  attendees: string
  agenda: string
  summary: string
  conclusion: string
  followup: string
}

export interface VisitParticipantDto {
  contactId: string
  isPrimary: boolean
  meetingRole?: string
}

export interface CreateVisitInput {
  accountId: string
  primaryContactId?: string
  opportunityId?: string
  subject: string
  date: string
  type: VisitDto['type']
  owner: string
  objective: string
}


/** Fields a Sales/Manager user may change on an existing Visit; the backend `edit` command locks after Manager Reviewed. */
export type UpdateVisitInput = Pick<CreateVisitInput, 'subject' | 'date' | 'type' | 'owner' | 'objective'>

export interface DashboardDto {
  asOf: string
  kpis: {
    moneyByCurrency: Array<{
      currency: string
      openPipeline: DecimalAmount
      confirmedBooking: DecimalAmount
      cumulativeWon: DecimalAmount
    }>
    /** Open / won Opportunities whose amount is not entered yet; the money figures above leave them out. */
    openPipelineMissingAmountCount?: number
    cumulativeWonMissingAmountCount?: number
    overdueActions: number
    pendingDemoRequests: number
    activeEvaluations: number
  }
  funnel: Array<{
    stage: string
    currency: string
    amount: DecimalAmount
    count: number
    /** How many of `count` have no amount yet: `amount` adds the known ones only. */
    missingAmountCount?: number
  }>
  bookingByMonth: Array<{ label: string; currency: string; amount: DecimalAmount; count: number }>
  ownerPerformance: Array<{ owner: string; currency: string; pipeline: DecimalAmount; booking: DecimalAmount; pipelineMissingAmountCount?: number }>
  topAccounts: Array<{ accountId: string; accountName: string; currency: string; pipeline: DecimalAmount; booking: DecimalAmount; pipelineMissingAmountCount?: number }>
  segmentDistribution: Array<{ label: string; currency: string; pipeline: DecimalAmount; booking: DecimalAmount; pipelineMissingAmountCount?: number }>
  regionDistribution: Array<{ label: string; currency: string; pipeline: DecimalAmount; booking: DecimalAmount; pipelineMissingAmountCount?: number }>
  tierDistribution: Array<{ label: string; count: number }>
  riskDistribution: Array<{ label: string; count: number }>
  process: {
    requirementsByStatus: Array<{ label: string; count: number; amount: number }>
    budgetByStatus: Array<{ label: string; count: number; amount: number }>
    actionsBySource: Array<{ label: string; count: number }>
    actionsByTimeliness: Array<{ label: string; count: number }>
    demoByStatus: Array<{ label: string; count: number }>
    demoByPriority: Array<{ label: string; count: number }>
    evaluationByStatus: Array<{ label: string; count: number }>
    evaluationRunResults: Array<{ label: string; count: number }>
    visitsByStatus: Array<{ label: string; count: number }>
    visitsByOwner: Array<{ label: string; count: number }>
  }
  attentionAccounts: AccountSummaryDto[]
  weeklyActions: ActionDto[]
  deliveryAlerts: Array<{ id: string; type: 'Demo Request' | 'Evaluation'; title: string; detail: string; tone: Tone }>
  completeness: Array<{ label: string; value: number; total: number }>
}

export interface Account360Dto {
  account: AccountSummaryDto
  sites: SiteDto[]
  contacts: ContactSummaryDto[]
  requirements: RequirementDto[]
  opportunities: OpportunityDto[]
  bookings: BookingDto[]
  demoRequests: DemoRequestDto[]
  evaluations: EvaluationDto[]
  quotations: AccountQuotationDto[]
  contracts: ContractDto[]
  actions: ActionDto[]
  visits: VisitDto[]
  summary: {
    activeDemos: number
    contractsAtRisk: number
    lastVisit: string
  }
}

export interface AccountQuotationDto {
  id: string
  refNo: string
  quotationType: 'Device' | 'Service'
  opportunityId: string
  opportunityTitle: string
  accountId: string
  accountName: string
  owner: string
  status: 'Draft' | 'Published' | 'Accepted' | 'Rejected' | 'Expired'
  approvalStatus: 'Not Submitted' | 'Pending' | 'Approved' | 'Rejected' | 'Not Required'
  latestVersion: number
  currentVersionId: string
  currentPublishedVersionId: string
  modified: string
}

export interface PipelineDto {
  opportunities: OpportunityDto[]
  bookings: BookingDto[]
  totals: Array<{
    currency: string
    openPipeline: DecimalAmount
    confirmedBooking: DecimalAmount
  }>
  /** Open Opportunities whose amount is not entered yet; `totals` leave them out. */
  openPipelineMissingAmountCount?: number
}
import type { DecimalAmount } from '@/domain/money'
import type { MultipartFilePart } from '@/api/binary-transport'
import type { OpportunityProbabilityLevel, OpportunityProbabilityLevelValue } from './workspaces'
import type { OpportunityStage } from '@/domain/opportunity-stages'
