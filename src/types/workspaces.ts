import type { DecimalAmount } from '@/domain/money'
import type {
  InternalValidationStatus,
  OpenOpportunityStage,
  OpportunityMilestoneStage,
  OpportunityReachedAtBasis,
  OpportunityStage,
  OpportunityStageHistoryEvent,
  OpportunityStageHistorySource,
} from '@/domain/opportunity-stages'
import type { BookingDto, DemoHealthDto, DemoLifecycleStage, DemoTrackingDto, ListQuery, SiteDto } from './crm'

/** Success probability levels from lowest to highest. Only the Opportunity owner sets one; a level carries no percentage. */
export const OPPORTUNITY_PROBABILITY_LEVELS = ['low_probability', 'pipeline', 'upside', 'committed'] as const
export type OpportunityProbabilityLevel = typeof OPPORTUNITY_PROBABILITY_LEVELS[number]
/** An empty value means the owner has not set a level yet (pending sales confirmation). */
export type OpportunityProbabilityLevelValue = OpportunityProbabilityLevel | ''
/** List filter: one level, `pending` for an empty level, or `All`. */
export type OpportunityProbabilityLevelFilter = OpportunityProbabilityLevel | 'pending' | 'All'

export const OPPORTUNITY_STAKEHOLDER_ROLES = [
  'Decision Maker', 'Economic Buyer', 'Technical Buyer', 'User Buyer', 'Coach',
  'Procurement', 'Influencer', 'Champion', 'Technical Champion', 'Primary Contact',
] as const
export type OpportunityStakeholderRole = typeof OPPORTUNITY_STAKEHOLDER_ROLES[number]
export const OPPORTUNITY_STAKEHOLDER_INFLUENCES = ['High', 'Medium', 'Low'] as const
export type OpportunityStakeholderInfluence = typeof OPPORTUNITY_STAKEHOLDER_INFLUENCES[number]
export const OPPORTUNITY_STAKEHOLDER_STANCES = ['Support', 'Neutral', 'Against'] as const
export type OpportunityStakeholderStance = typeof OPPORTUNITY_STAKEHOLDER_STANCES[number]
export const OPPORTUNITY_STAKEHOLDER_RESPONSE_MODES = ['Growth', 'Trouble', 'Even Keel', 'Overconfident'] as const
export type OpportunityStakeholderResponseMode = typeof OPPORTUNITY_STAKEHOLDER_RESPONSE_MODES[number]
/** Blue Sheet competition: one row per competitor. */
export interface OpportunityCompetitor {
  name: string
  /** What the competitor is strong at in this deal. */
  strengths: string
  /** How we answer it. */
  response: string
}
export const MAX_OPPORTUNITY_COMPETITORS = 10
export const OPPORTUNITY_ACTION_STATUSES = ['Open', 'In Progress', 'Blocked', 'Rescheduled', 'Done'] as const
export type OpportunityActionStatus = typeof OPPORTUNITY_ACTION_STATUSES[number]

export interface OpportunityStakeholderDto {
  id: string
  contactId: string
  name: string
  title: string
  role: OpportunityStakeholderRole
  influence: OpportunityStakeholderInfluence
  stance: OpportunityStakeholderStance
  /** Blue Sheet buying-influence response mode; blank when not recorded. */
  responseMode?: OpportunityStakeholderResponseMode | ''
  coverage: string
  isCoach?: boolean
  winResult?: string
  opportunityNotes?: string
}

export interface OpportunityActionDto {
  id: string
  title: string
  owner: string
  due: string
  status: OpportunityActionStatus
  remark?: string
  completedAt?: string | null
}

export type CreateOpportunityStakeholderInput = Omit<OpportunityStakeholderDto, 'id' | 'name' | 'title'>
export type UpdateOpportunityStakeholderInput = CreateOpportunityStakeholderInput
export type CreateOpportunityActionInput = Omit<OpportunityActionDto, 'id' | 'completedAt'>
export type UpdateOpportunityActionInput = CreateOpportunityActionInput

export interface OpportunityProbabilityHistoryDto {
  id: string
  from: OpportunityProbabilityLevelValue
  to: OpportunityProbabilityLevelValue
  /** Why the owner lowered the level. Required on a downgrade, empty otherwise. */
  reason: string
  actor: string
  /** UTC ISO timestamp ending in Z. */
  at: string
  /** Legacy events can have no recorded plan; never infer one from other actions. */
  recovery?: ProbabilityRecoveryDto | null
}

export interface LossReviewInput {
  status: 'Reviewed' | 'Pending'
  /** The conclusion; required to mark the loss reviewed, kept unchanged by a revert. */
  reviewNote: string
  /** Required to revert a reviewed loss to pending; recorded in the audit trail. */
  revertReason?: string
}

/** One post-mortem per marked_lost event; it survives reopening the Opportunity. */
export interface LossReviewDto {
  id: string
  opportunityId: string
  stageEventId: string
  lostAt: string
  lostAtStage: string
  lostBy: string
  lostReason: string
  status: 'pending' | 'reviewed'
  reviewNote: string
  reviewedBy: string | null
  reviewedAt: string | null
  reopenedAt: string | null
  modified: string
  history: { id: string; kind: string; status: 'pending' | 'reviewed'; note: string; reason: string; actor: string; at: string }[]
}

export interface ProbabilityRecoveryDto {
  id: string
  plan: string
  modified: string
  state?: 'pending' | 'handled'
  actionTaken?: string | null
  actedBy?: string | null
  actedAt?: string | null
  history: Array<{ id: string; kind: 'Created' | 'PlanUpdated' | 'ActionRecorded'; plan: string; actor: string; at: string; actionTaken?: string | null }>
}

export interface RecordProbabilityRecoveryActionInput {
  actionTaken: string
  recoveryModified: string
}

export interface SaveProbabilityRecoveryInput {
  plan: string
  /** null explicitly creates a missing legacy plan; edits require its loaded version. */
  recoveryModified: string | null
}

export interface StrategyOpportunityListQuery extends ListQuery {
  probabilityLevel?: OpportunityProbabilityLevelFilter
  /** Also return count and totals per stage of everything the query matches, read in the same request as the page. */
  stageSummary?: boolean
}

/** Count and totals of one stage over every Opportunity a list query matches, whatever page is shown. */
export interface OpportunityStageSummaryDto {
  stage: string
  count: number
  /** How many of them have no amount entered yet; the totals leave these out. */
  unknownAmountCount: number
  totals: Array<{ currency: string; amount: DecimalAmount }>
}

export interface StrategyOpportunityPageData {
  items: StrategyOpportunityDto[]
  /** Present when the query asked for it. */
  stageSummary?: OpportunityStageSummaryDto[]
}

export interface CreateStrategyOpportunityInput {
  accountId: string
  siteId: string
  title: string
  owner: string
  /**
   * May be '' (not entered yet) while the Opportunity is at qualified_opportunity, where every new Opportunity
   * starts, together with originalAmount and amountCny. Every edit after it has left that stage requires all three.
   */
  amount: DecimalAmount | ''
  intentScore?: number
  /**
   * Required when creating: whoever opens the Opportunity sets its first level, including a Manager
   * opening one for Sales. Afterwards only the owner may change it, and a set level is never cleared.
   */
  probabilityLevel?: OpportunityProbabilityLevelValue
  /** Required when the owner lowers the level. */
  probabilityReason?: string
  /** Required in the same save as a probability downgrade. */
  probabilityActionPlan?: string
  poDate: string
  toolType: string
  saleType: string
  subRegion: string
  currency: string
  originalAmount?: DecimalAmount | ''
  /**
   * Entered by Sales in CNY on every Opportunity, whatever its currency. Optional like the amount at
   * qualified_opportunity; any edit of an Opportunity past that stage that has none must fill it in.
   */
  amountCny: DecimalAmount | ''
  shipmentDate?: string
  fatDate?: string
  paymentMilestones?: string[]
  competition?: string
  /** Left out, the stored list is kept; an empty list clears it. */
  competitors?: OpportunityCompetitor[]
  singleSalesObjective?: string
  winReason?: string
  lostReason?: string
  strengths?: string[]
  redFlags?: string[]
  informationNeeded?: string[]
  /**
   * Sales confirms the customer need and the budget owner. Creating an Opportunity requires `true`;
   * every new Opportunity starts at qualified_opportunity.
   */
  qualificationConfirmed?: boolean
}

/** Stages change only through their workflow actions, so an update never carries a stage. */
export type UpdateStrategyOpportunityInput = Partial<Omit<CreateStrategyOpportunityInput, 'qualificationConfirmed'>>

export interface RollbackOpportunityStageInput {
  targetStage: OpportunityMilestoneStage
  reason: string
}

/** Booking fields Sales enters for an Opportunity; account, source, Opportunity and type always follow the Opportunity. */
export interface BookingDraft {
  primaryContactId: string
  equipment: string
  quantity: number
  ddl: string
  amount: DecimalAmount
  currency: string
  /** The order's amount in CNY when its currency is not CNY; required when the PO is confirmed. Ignored for CNY. */
  amountCny?: DecimalAmount | ''
  owner: string
  note: string
}

export interface ConfirmBudgetApprovedInput {
  /** YYYY-MM-DD, not later than today. */
  approvedOn: string
}

export interface RequestInternalValidationInput {
  reason: string
  expectedPoDate: string
  booking: BookingDraft
}

export interface ReviewInternalValidationInput {
  validationId: string
  decision: 'approved' | 'rejected'
  /** Optional to approve, required to reject. */
  comment: string
}

export interface ConfirmPoInput {
  booking: BookingDraft
  /** `liveBooking.modified` the form was prefilled from; the server requires it while a Pending Booking exists. */
  expectedBookingModified?: string
  /** Date on the customer's PO, not later than today; not the Opportunity's expected poDate. */
  actualPoDate: string
}

export interface MarkOpportunityLostInput {
  lostReason: string
}

export interface OpportunityStageHistoryDto {
  id: string
  /** Empty for creation and migration rows. */
  from: OpportunityStage | ''
  to: OpportunityStage
  source: OpportunityStageHistorySource
  event: OpportunityStageHistoryEvent
  referenceDoctype: string
  referenceName: string
  reason: string
  actor: string
  /** UTC ISO timestamp of when the row was written. */
  recordedAt: string
  /** UTC ISO timestamp of the business arrival, such as a declared budget date; only migration rows may leave it empty. */
  reachedAt: string
  reachedAtBasis: OpportunityReachedAtBasis
}

/** The latest internal validation request of an Opportunity. */
export interface OpportunityInternalValidationDto {
  id: string
  attemptNo: number
  status: InternalValidationStatus
  reason: string
  expectedPoDate: string
  booking: BookingDraft
  requestedBy: string
  requestedAt: string
  decidedBy: string
  decidedAt: string
  decisionComment: string
  /** The Pending Booking created when the request was approved. */
  bookingId: string
  cancelledBy: string
  cancelledAt: string
  cancelReason: string
}

/** The Opportunity's Booking that is not Cancelled. Details are omitted when the viewer cannot read that Booking. */
export interface OpportunityLiveBookingDto {
  id: string
  status: Exclude<BookingDto['status'], 'Cancelled'>
  primaryContactId?: string
  equipment?: string
  quantity?: number
  ddl?: string
  amount?: DecimalAmount
  currency?: string
  owner?: string
  note?: string
  /** Version to send back as `expectedBookingModified` when the PO confirms this Pending Booking. */
  modified?: string
  /** The order's amount in CNY: the amount of a CNY Booking, '' until entered for another currency. */
  amountCny?: DecimalAmount | ''
  actualPoDate?: string
}

export interface StrategyOpportunityDto {
  id: string
  sourceLeadId?: string
  accountId: string
  siteId: string
  siteRestricted?: boolean
  title: string
  account: string
  site: string
  owner: string
  stage: OpportunityStage
  /** UTC ISO timestamp of the latest arrival at the current stage, or ''. */
  stageChangedAt: string
  /** A Demo reached customer review before the amount was entered; saving the amount applies the move. */
  pendingStageAdvance?: 'demo_done' | ''
  /** YYYY-MM-DD on which Sales declared the customer approved the budget, or ''. */
  budgetApprovedOn: string
  /** The open stage the Opportunity was lost at. Empty unless lost, and possibly empty for a migrated loss. */
  lostAtStage: OpenOpportunityStage | ''
  /** UTC ISO timestamp, or ''. */
  lostAt: string
  lostBy: string
  /** '' until someone enters it (allowed at qualified_opportunity), never a believable 0. */
  amount: DecimalAmount | ''
  probabilityLevel: OpportunityProbabilityLevelValue
  /** Level changes, newest first. */
  probabilityHistory: OpportunityProbabilityHistoryDto[]
  /** Stage changes, newest first. Stage moves are no longer written to the generic history. */
  stageHistory: OpportunityStageHistoryDto[]
  /** The latest internal validation request, or null. */
  internalValidation: OpportunityInternalValidationDto | null
  /** The non-cancelled Booking (Pending, Confirmed or Completed), or null. */
  liveBooking: OpportunityLiveBookingDto | null
  poDate: string
  updated: string
  modified?: string
  score: number
  toolType: string
  saleType: string
  subRegion: string
  currency: string
  /** '' while the amount is not entered yet. */
  originalAmount: DecimalAmount | ''
  /** The amount in CNY entered by Sales; '' until someone enters it, never a CNY 0. */
  amountCny: DecimalAmount | ''
  shipmentDate: string
  fatDate: string
  paymentMilestones: string[]
  competition: string
  /** Blue Sheet competitors; adapters that predate the field omit it. */
  competitors?: OpportunityCompetitor[]
  /** Blue Sheet objective; adapters and records that predate the field may omit it. */
  singleSalesObjective?: string
  winReason: string
  lostReason: string
  /** Post-mortems, newest first. Absent from adapters that predate loss reviews. */
  lossReviews?: LossReviewDto[]
  history: Array<{ at: string; actor: string; field: string; from: string; to: string }>
  strengths: string[]
  redFlags: string[]
  informationNeeded: string[]
  stakeholders: OpportunityStakeholderDto[]
  actions: OpportunityActionDto[]
}

export interface LegacyOpportunityStakeholderDto extends Omit<OpportunityStakeholderDto, 'contactId'> {
  contactId?: string
  email?: string
}

export interface LegacyStrategyOpportunityDto extends Omit<StrategyOpportunityDto, 'stakeholders'> {
  stakeholders: LegacyOpportunityStakeholderDto[]
}

export type DemoProjectTimelineState = 'Done' | 'Current' | 'Waiting'

export interface DemoProjectTimelineStepDto {
  key: string
  label: string
  state: DemoProjectTimelineState
  date?: string
  actor?: string
}

export interface DemoCommentDto {
  id: string
  demoRequestId: string
  author: string
  role: string
  body: string
  mentionedPersonId?: string
  mentionedPerson?: string
  mentionedPeople?: Array<{ id: string; name: string }>
  createdAt: string
}

export interface DemoWorkflowDto {
  id: string
  accountId: string
  siteId: string
  opportunityId: string
  title: string
  account: string
  opportunity: string
  salesOwner: string
  engineerOwner: string
  equipment: string
  /** @deprecated Use engineerOwner for Demo responsibility. */
  owner: string
  status: string
  /** Why the Demo Test was terminated mid-flight; blank for every other Demo, including historical rejections. */
  terminationReason?: string
  archiveCategory: 'In Progress' | 'Completed'
  stage?: DemoLifecycleStage
  health?: DemoHealthDto
  tracking?: DemoTrackingDto
  /** @deprecated Demo 档案不展示推算进度，仅为旧后端适配保留。 */
  progress?: number
  customerExpectedDate?: string
  projectTimeline?: DemoProjectTimelineStepDto[]
  request?: {
    objective: string
    requestedEquipment: string
    sampleType: string
    sampleQuantity: number
    priority: string
    acceptanceCriteria: string
    salesOwner: string
    specificRequest: string
    detectMeasure: string
    expectedResults: string
    complementaryTool: string
    contactPerson?: string
    industry?: string
    competition?: string
    internalQuestions?: string[]
    testPlan?: string
    assignedEquipment?: string
    resourceWindow?: string
    estimatedCompletionDate?: string
    technicalRisk?: string
    engineerComment?: string
    managerDecision?: string
    managerComment?: string
    wafers?: Array<{ id: string; specificity: string; detail: string }>
  }
  evaluation?: {
    modified?: string
    id: string
    status: string
    owner: string
    testRunDeadline: string
    waferPreparationStatus?: 'Pending' | 'Completed'
    waferPreparationCompletedBy?: string
    waferPreparationCompletedAt?: string
    testPreparationStatus?: 'Pending' | 'Completed'
    testPreparationCompletedBy?: string
    testPreparationCompletedAt?: string
    runs: Array<{
      id: string
      date: string
      lot: string
      /** Retest round the run belongs to; earlier rounds stay in the archive next to the current one. */
      round: number
      wafers: number
      status: 'Planned' | 'Completed' | 'Cancelled'
      summary: string
      capture: number | null
      falsePositive: number | null
      wph: number | null
    }>
  }
  artifacts?: Array<{
    id: string
    type: 'Demo Request DOCX' | 'Test Report' | 'Customer Report'
    fileName: string
    mimeType?: string
    version: number
    round?: number
    createdBy?: string
    createdAt: string
    visibility?: 'Internal' | 'Customer Review'
  }>
  tool?: string
  objective?: string
  target?: string
  successFactors?: string[]
  contact?: string
  industry?: string
  salesContact?: string
  waferCount?: number
  specificRequest?: string
  detectMeasure?: string
  expectedResults?: string
  otherTools?: string
  complementaryTool?: string
  internalQuestions?: string[]
  customerQuestions?: string[]
  preparedBy?: string
  approvedBy?: string
  conclusion: { status: 'Pending' | 'Accepted' | 'Rejected'; summary?: string; customerFeedback?: string; confirmedBy?: string; confirmedAt?: string; followUpAction?: string }
  customerReviews?: Array<{ id: string; round: number; comment: string; author: string; createdAt: string }>
  testRound?: number
  approvals: Array<{ label: string; actor: string; status: 'Done' | 'Current' | 'Waiting' }>
  executions: Array<{ id: string; tool: string; window: string; engineer: string; status: string }>
  wafers: Array<{ id: string; lot: string; material: string; diameter: string; thickness: string; status: string }>
  testRuns: Array<{ id: string; date: string; recipe: string; capture: number | null; falsePositive: number | null; wph: number | null; result: string }>
}

export interface InstalledToolDto {
  id: string
  accountId: string
  siteId: string
  serial: string
  model: string
  account: string
  site: string
  location: string
  status: string
  lifecycleStage?: 'FAT' | 'Shipment' | 'Installation' | 'SAT' | 'Warranty'
  software: string
  firmware: string
  warrantyEnd: string
  completeness: number
  sourceBookingId: string
  sourceOpportunityId: string
  salesOwner: string
  engineerOwner: string
  salesOrder: string
  contract: string
  warrantyStart: string
  serviceContract: string
  pmCycle: string
  lastService: string
  operatingSystem: string
  configuration: string
  ownershipType: string
  milestones: Array<{ label: string; date: string; state: 'Done' | 'Current' | 'Waiting' }>
  documents: string[]
  modified?: string
}

export interface InstalledToolLifecycleHistoryDto {
  id: string
  at: string
  actor: string
  fromStage: string
  toStage: string
  completedAt: string
  result: string
  openIssues: string
  customerSignoff: string
  comment: string
  evidence: string[]
}

export interface InstalledToolVersionHistoryDto {
  id: string
  at: string
  actor: string
  changeDate: string
  changeType: InstalledToolVersionChangeType
  fromValue: string
  toValue: string
  reason: string
  comment: string
}

export interface InstalledToolServiceHistoryDto {
  id: string
  at: string
  actor: string
  serviceDate: string
  serviceType: InstalledToolServiceType
  result: string
  openIssues: string
  nextAction: string
  actionOwner: string
  due: string
  comment: string
  warrantyStart: string
  warrantyEnd: string
  serviceContract: string
  pmCycle: string
}

export interface InstalledToolDetailDto extends InstalledToolDto {
  lifecycleHistory: InstalledToolLifecycleHistoryDto[]
  versionHistory: InstalledToolVersionHistoryDto[]
  serviceHistory: InstalledToolServiceHistoryDto[]
  lifecycleCompleted: boolean
  canOperate: boolean
  canReassign: boolean
  /** The Sites of the Account, for the editor, as the choice is made: id, name and city. Empty for a reader who may not see the Tool's Site. */
  sites: Array<Pick<SiteDto, 'id' | 'name' | 'city'>>
}

export type InstalledToolVersionChangeType = 'Software' | 'Firmware' | 'Operating System' | 'Configuration'
export type InstalledToolServiceType = 'Warranty Activation' | 'Preventive Maintenance' | 'Corrective Service' | 'Remote Support' | 'Installation Support' | 'Contract Change'

export interface TransitionInstalledToolInput {
  completedAt: string
  result: string
  openIssues: string
  customerSignoff: string
  comment: string
  evidence: string[]
}

export interface AddInstalledToolVersionRecordInput {
  changeDate: string
  changeType: InstalledToolVersionChangeType
  toValue: string
  reason: string
  comment?: string
}

export interface AddInstalledToolServiceRecordInput {
  serviceDate: string
  serviceType: InstalledToolServiceType
  result: string
  openIssues: string
  nextAction?: string
  actionOwner?: string
  due?: string
  comment?: string
  warrantyStart?: string
  warrantyEnd?: string
  serviceContract?: string
  pmCycle?: string
}
export interface ConvertBookingToInstalledToolInput {
  siteId: string
  engineerOwner: string
  /** Legacy clients may send this value; the server ignores it and generates the serial. */
  serial?: string
  model: string
  location?: string
  salesOrder?: string
  contract?: string
  software?: string
  firmware?: string
  configuration?: string
}

export interface UpdateInstalledToolInput {
  siteId: string
  /** Legacy clients may send this value; the server keeps the existing serial. */
  serial?: string
  model: string
  location: string
  engineerOwner: string
  /** Legacy compatibility fields are ignored by the audited master-data endpoint. */
  status?: string
  software?: string
  firmware?: string
  configuration?: string
  operatingSystem?: string
  warrantyStart?: string
  warrantyEnd: string
  serviceContract?: string
  pmCycle?: string
  ownershipType: string
  salesOrder: string
  contract: string
}

export interface ControlledDocumentDto {
  id: string
  versionId: string
  title: string
  category: 'Technical' | 'Commercial'
  type: string
  product: string
  version: string
  revision: string
  status: string
  confidentiality: string
  access: 'Direct' | 'Request'
  canPreview?: boolean
  canDownload?: boolean
  deliveryMode?: 'Watermarked' | 'Original' | ''
  accessRequest?: ControlledDocumentAccessRequestDto | null
  reviewDate: string
  owner: string
  mimeType: string
  size: number
  hasPreview: boolean
  fileUrl?: string
  fileName?: string
  versions: Array<{ version: string; revision: string; status: 'Released' | 'Superseded' | 'Obsolete'; releasedAt: string; checksum: string }>
  audit: Array<{ id: string; employee: string; at: string; reason: string; version: string }>
  applicableTool: string
}

export interface DocumentUploadInput {
  title: string
  category: 'Technical' | 'Commercial'
  documentType: string
  accessMode: 'Direct' | 'Request'
  confidentiality: 'Internal' | 'Confidential' | 'Restricted'
  product?: string
  version?: string
  revision?: string
  reviewDate?: string
  applicableTool?: string
}

export interface DocumentUploadRequestDto extends DocumentUploadInput {
  id: string
  fileName: string
  mimeType: string
  size: number
  status: 'Pending' | 'Published' | 'Rejected'
  submittedBy: string
  submittedByName: string
  submittedByRole: string
  submittedAt: string
  decidedBy: string
  decidedAt: string
  decisionReason: string
  publishedDocumentId: string
}

export type DocumentUploadDecisionInput =
  | { decision: 'approve'; category: 'Technical' | 'Commercial'; confidentiality: 'Internal' | 'Confidential' | 'Restricted'; accessMode: 'Direct' | 'Request' }
  | { decision: 'reject'; reason: string }

export type DocumentApprovalQueueItem =
  | { kind: 'access'; submittedAt: string; request: ControlledDocumentAccessRequestDto }
  | { kind: 'upload'; submittedAt: string; request: DocumentUploadRequestDto }

export interface ControlledDocumentAccessRequestDto {
  id: string
  requester: string
  requesterName: string
  requesterRole: string
  documentId: string
  documentTitle: string
  versionId: string
  /** The version and revision the request names, as the document had them when it was made (empty on a request older than the fields, whose document moved on). */
  version?: string
  revision?: string
  /** The document's own confidentiality, status and download audit, with the Manager's queue: the approval detail of a document the Released library no longer lists reads them here. */
  documentConfidentiality?: string
  documentStatus?: string
  documentAudit?: Array<{ id: string; employee: string; at: string; reason: string; version: string }>
  reason: string
  status: 'Pending' | 'Approved' | 'Rejected' | 'More Info Required'
  deliveryMode: 'Watermarked' | 'Original' | ''
  submittedAt: string
  decidedBy: string
  decidedAt: string
  /** What the Manager told the applicant with a rejection or a request for more information. */
  decisionNote: string
}
