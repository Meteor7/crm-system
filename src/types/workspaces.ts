import type { DecimalAmount } from '@/domain/money'
import type { DemoHealthDto, DemoLifecycleStage, DemoTrackingDto } from './crm'

export const STRATEGY_OPPORTUNITY_STAGES = ['需求发现', 'Wafer Demo确认', '预算审批', '设备规格确认', '报价', '采购流程', 'Won', 'Lost'] as const
export type StrategyOpportunityStage = typeof STRATEGY_OPPORTUNITY_STAGES[number]

export const OPPORTUNITY_STAKEHOLDER_ROLES = [
  'Decision Maker', 'Economic Buyer', 'Technical Buyer', 'User Buyer', 'Coach',
  'Procurement', 'Influencer', 'Champion', 'Technical Champion', 'Primary Contact',
] as const
export type OpportunityStakeholderRole = typeof OPPORTUNITY_STAKEHOLDER_ROLES[number]
export const OPPORTUNITY_STAKEHOLDER_INFLUENCES = ['High', 'Medium', 'Low'] as const
export type OpportunityStakeholderInfluence = typeof OPPORTUNITY_STAKEHOLDER_INFLUENCES[number]
export const OPPORTUNITY_STAKEHOLDER_STANCES = ['Support', 'Neutral', 'Against'] as const
export type OpportunityStakeholderStance = typeof OPPORTUNITY_STAKEHOLDER_STANCES[number]
export const OPPORTUNITY_ACTION_STATUSES = ['Open', 'Done'] as const
export type OpportunityActionStatus = typeof OPPORTUNITY_ACTION_STATUSES[number]

export interface OpportunityStakeholderDto {
  id: string
  contactId: string
  name: string
  title: string
  role: OpportunityStakeholderRole
  influence: OpportunityStakeholderInfluence
  stance: OpportunityStakeholderStance
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
}

export type CreateOpportunityStakeholderInput = Omit<OpportunityStakeholderDto, 'id' | 'name' | 'title'>
export type UpdateOpportunityStakeholderInput = CreateOpportunityStakeholderInput
export type CreateOpportunityActionInput = Omit<OpportunityActionDto, 'id'>
export type UpdateOpportunityActionInput = CreateOpportunityActionInput

export interface CreateStrategyOpportunityInput {
  accountId: string
  siteId: string
  title: string
  owner: string
  stage: StrategyOpportunityStage
  forecast: string
  amount: DecimalAmount
  intentScore?: number
  probability?: number
  poDate: string
  toolType: string
  saleType: string
  subRegion: string
  currency: string
  originalAmount?: DecimalAmount
  shipmentDate?: string
  fatDate?: string
  paymentMilestones?: string[]
  competition?: string
  winReason?: string
  lostReason?: string
  strengths?: string[]
  redFlags?: string[]
  informationNeeded?: string[]
}

export type UpdateStrategyOpportunityInput = Partial<CreateStrategyOpportunityInput>

export interface RollbackOpportunityStageInput {
  targetStage: StrategyOpportunityStage
  reason: string
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
  stage: StrategyOpportunityStage
  forecast: string
  amount: DecimalAmount
  probability: number
  poDate: string
  updated: string
  modified?: string
  score: number
  toolType: string
  saleType: string
  subRegion: string
  currency: string
  originalAmount: DecimalAmount
  shipmentDate: string
  fatDate: string
  paymentMilestones: string[]
  competition: string
  winReason: string
  lostReason: string
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
      wafers: number
      status: 'Planned' | 'Completed'
      summary: string
      capture: number | null
      falsePositive: number | null
      wph: number | null
    }>
  }
  artifacts?: Array<{
    id: string
    type: 'Demo Request DOCX' | 'Test Report'
    fileName: string
    mimeType?: string
    version: number
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
  reason: string
  status: 'Pending' | 'Approved' | 'Rejected' | 'More Info Required'
  deliveryMode: 'Watermarked' | 'Original' | ''
  submittedAt: string
  decidedBy: string
  decidedAt: string
}
