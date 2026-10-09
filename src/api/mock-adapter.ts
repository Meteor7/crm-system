import { createMockStatusApi } from '@/features/opportunities/mock-status-api'
import type { CrmApi, DashboardQuery } from './contracts'
import type { LossReviewDto, LossReviewInput, ProbabilityRecoveryDto } from '@/types/workspaces'
import { CrmApiError } from './contracts'
import type { DemoArtifactUploadInput, MultipartFilePart } from './binary-transport'
import { actions, contracts, requirements } from './mock-data'
import type { ApiResponse, AccountSummaryDto, ContactDetailDto, ContactDto, ContactFileMetaDto, ContactListQuery, ContactSummaryDto, CreateAccountInput, CreateContactInput, CreateDemoRequestInput, CreateLeadInput, CreateStakeholderInput, CreateTestRunInput, CreateVisitInput, DemoRequestCommand, DemoRequestDto, EvaluationDto, EvaluationPreparationBranch, EvaluationStatusCommand, LeadConversionInput, LeadConversionResult, LeadDto, LeadListQuery, ListQuery, OpportunityDto, PersonnelRole, SetActualPoDateInput, SetBookingAmountCnyInput, SiteDto, UpdateContactInput, UpdateLeadInput, UpdateStakeholderInput, UpdateVisitInput, UpsertBookingInput, UserRole, VisitDetailDto, VisitMeetingRecordDto, VisitMeetingRecordInput } from '@/types/crm'
import type { AddInstalledToolServiceRecordInput, AddInstalledToolVersionRecordInput, ControlledDocumentAccessRequestDto, ControlledDocumentDto, DocumentUploadRequestDto, ConvertBookingToInstalledToolInput, CreateOpportunityActionInput, CreateOpportunityStakeholderInput, CreateStrategyOpportunityInput, DemoCommentDto, DemoWorkflowDto, InstalledToolDetailDto, InstalledToolDto, InstalledToolLifecycleHistoryDto, InstalledToolServiceHistoryDto, InstalledToolVersionHistoryDto, RollbackOpportunityStageInput, StrategyOpportunityDto, StrategyOpportunityListQuery, TransitionInstalledToolInput, UpdateInstalledToolInput, UpdateOpportunityActionInput, UpdateOpportunityStakeholderInput, UpdateStrategyOpportunityInput } from '@/types/workspaces'
import type { BookingDto } from '@/types/crm'
import type { BookingDraft, ConfirmBudgetApprovedInput, ConfirmPoInput, MarkOpportunityLostInput, OpportunityInternalValidationDto, OpportunityLiveBookingDto, OpportunityStageHistoryDto, RequestInternalValidationInput, ReviewInternalValidationInput } from '@/types/workspaces'
import {
  OPEN_OPPORTUNITY_STAGES,
  PO_CONFIRMABLE_STAGES,
  canCreateDemoRequestAt,
  canCreateRfqAt,
  isClosedOpportunityStage,
  isOpenOpportunityStage,
  isOpportunityMilestoneStage,
  opportunityStageIndex,
  type OpenOpportunityStage,
  type OpportunityMilestoneStage,
  type OpportunityReachedAtBasis,
  type OpportunityStage,
  type OpportunityStageHistoryEvent,
  type OpportunityStageHistorySource,
} from '@/domain/opportunity-stages'
import type { StoredOpportunityInternalValidation } from '@/demo/sales-repository'
import { getContractRisk } from '@/domain/contracts'
import { shanghaiDate, shanghaiTimestamp } from '@/domain/time'
import { buildManagementDashboard } from '@/domain/dashboard'
import { canTransitionEvaluation, evaluationPreparationStatus, hasCompletedTestRun, isEvaluationPreparationComplete, isIsoDate } from '@/domain/evaluations'
import { ROLE_PROFILES, assertAnyCapability, assertCapability } from '@/domain/permissions'
import { isVisitEditable, validateCreateVisit } from '@/domain/visits'
import { validateReportingLine } from '@/domain/stakeholders'
import { deriveDemoRequestSummary, getDemoRequestFormData, validateDemoRequestFormData } from '@/domain/demo-request-form'
import { deriveDemoHealth, mapDemoLifecycleStage } from '@/domain/demo-lifecycle'
import { controlledDocuments } from '@/demo/operations-data'
import { createDemoRepository, createMemoryDemoStorage, seedDemoSnapshot, type DemoRepository, type DemoSnapshot } from '@/demo/demo-repository'
import { createMemorySalesRepository, isRetiredLocalContact, type SalesRepository } from '@/demo/sales-repository'
import { createMemoryContactFileRepository, type ContactFileRepository } from '@/demo/contact-file-repository'
import type { StoredContactFile, StoredDemoArtifact } from '@/demo/binary-storage'
import { expandOpportunityContact, formatContactDisplayLine, migrateLegacyPrimaryContacts } from '@/domain/contacts'
import { isOpportunityProbabilityLevelValue, matchesOpportunityProbabilityLevelFilter, opportunityProbabilityLevelRank } from '@/domain/opportunity-probability'
import { collapseRegion, isEnglishRegion, matchingRegion, regionOptions } from '@/domain/regions'
import { equipmentOptions, equipmentText, matchingEquipment } from '@/domain/equipment'
import { PERSONNEL, assertPersonnelRole } from '@/demo/personnel'
import { migrateLegacyUserId } from '@/demo/identity-migration'
import { addMoney, normalizeMoney } from '@/domain/money'
import type { RfqDetailDto, RfqVersionDto } from '@/features/rfqs/types'

const CONTACT_FILE_MAX_SIZE = 100 * 1024 * 1024
const CONTACT_FILE_NAME_PATTERN = /\.(pdf|doc|docx|xls|xlsx|ppt|pptx|txt|csv|png|jpe?g)$/i
const mockRfqsByRepository = new WeakMap<SalesRepository, RfqDetailDto[]>()
const mockRfqFilesByRepository = new WeakMap<SalesRepository, Map<string, { blob: Blob; fileName: string; mimeType: string }>>()
function clone<T>(value: T): T {
  return structuredClone(value)
}

function requestId() {
  return `req_mock_${Math.random().toString(36).slice(2, 10)}`
}

function wasDemoRequestSubmitted(request: Pick<DemoRequestDto, 'history'>) {
  return request.history.some((item) => item.to === 'Engineer Review')
}

function includes(value: string, search = '') {
  return value.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())
}

function contactFileMeta(file: StoredContactFile): ContactFileMetaDto {
  const { blob: _blob, ...meta } = file
  return meta
}

function validateContactFileUpload(file: MultipartFilePart) {
  const fileName = file.fileName.trim()
  if (!fileName || file.size <= 0 || file.blob.size <= 0) {
    throw new CrmApiError('VALIDATION_ERROR', '文件不能为空', requestId(), false)
  }
  if (file.size !== file.blob.size) {
    throw new CrmApiError('VALIDATION_ERROR', '文件大小信息不一致', requestId(), false)
  }
  if (file.size > CONTACT_FILE_MAX_SIZE) {
    throw new CrmApiError('VALIDATION_ERROR', '单个文件不能超过 100 MiB', requestId(), false)
  }
  if (!CONTACT_FILE_NAME_PATTERN.test(fileName)) {
    throw new CrmApiError('VALIDATION_ERROR', '仅支持 PDF、Office 文档、TXT、CSV、PNG 和 JPG 文件', requestId(), false)
  }
}

// A retest opens a new round, so a report chosen in a window opened before the retest
// belongs to the round the uploader saw, not to the round the Evaluation is on now.
function assertExpectedRound(evaluation: EvaluationDto, expectedRound: number) {
  if (expectedRound !== evaluation.testRound) {
    throw new CrmApiError('CONFLICT', `该 Demo Test 已进入第 ${evaluation.testRound} 轮，请刷新后重新上传报告`, requestId(), false)
  }
}

export function createMockApi(options: {
  repository?: DemoRepository
  latency?: number
  role?: UserRole
  userId?: string
  userName?: string
  teamOwners?: string[]
  assignedAccountIds?: string[]
  salesRepository?: SalesRepository
  contactFileRepository?: ContactFileRepository
  today?: string
} = {}): CrmApi {
  const latency = options.latency ?? 180
  const role = options.role ?? 'Manager'
  const profile = ROLE_PROFILES[role]
  const capabilities = profile.capabilities
  const requestedUserName = options.userName ?? (
    role === 'Sales'
      ? 'Demo Staff 01'
      : role === 'Engineer'
        ? '演示员工14'
        : '演示员工24'
  )
  const userId = options.userId ?? migrateLegacyUserId(requestedUserName, 'session.user')
  const activePerson = PERSONNEL.find((person) => person.id === userId)
  const userName = activePerson?.name ?? requestedUserName
  const assignedAccountIds = new Set(options.assignedAccountIds ?? ['ACC-001'])
  const today = options.today ?? shanghaiDate()
  const now = options.today ? `${today}T10:30:00+08:00` : shanghaiTimestamp()
  const historyAt = now.slice(0, 16).replace('T', ' ')
  const healthToday = today

  function validateOwner(value: string, allowedRoles: readonly PersonnelRole[], sharedSales = false) {
    const owner = value.trim()
    assertPersonnelRole(owner, allowedRoles)
    const ownerRole = PERSONNEL.find((person) => person.id === owner)!.role
    if (role === 'Sales' && ownerRole === 'Sales' && owner !== userId && !sharedSales) {
      throw new CrmApiError('SCOPE_DENIED', 'Sales 只能指定本人为负责人', requestId(), false)
    }
    if (role === 'Engineer' && ownerRole === 'Engineer' && owner !== userId) {
      throw new CrmApiError('SCOPE_DENIED', 'Engineer 只能指定本人为工程负责人', requestId(), false)
    }
    return owner
  }
  const response = <T>(data: T, warnings: string[] = []): ApiResponse<T> => ({
    data: clone(data),
    meta: { requestId: requestId(), generatedAt: now },
    warnings,
  })
  const pageResponse = <T>(items: T[], query: ListQuery = {}) => {
    const page = Number.isInteger(query.page) && Number(query.page) > 0 ? Number(query.page) : 1
    const pageSize = Number.isInteger(query.pageSize) && Number(query.pageSize) > 0
      ? Math.min(Number(query.pageSize), 200)
      : 20
    const start = (page - 1) * pageSize
    const result = response({ items: items.slice(start, start + pageSize) })
    result.meta = { ...result.meta!, page, pageSize, total: items.length }
    return result
  }
  const repository = options.repository ?? createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
  const salesRepository = options.salesRepository ?? createMemorySalesRepository()
  const contactFileRepository = options.contactFileRepository ?? createMemoryContactFileRepository()
  const localActions = clone(actions)
  const localContracts = clone(contracts)
  const localVisits = salesRepository.snapshot.visits
  const meetingRecords = new Map<string, VisitMeetingRecordDto>()
  const meetingFiles = new Map<string, { blob: Blob; fileName: string; mimeType: string; uploadedAt: string; uploadedBy: string; visitId: string }>()
  const localBookings = salesRepository.snapshot.bookings
  const localInstalledTools = salesRepository.snapshot.installedTools
  const installedToolLifecycleHistory = new Map<string, InstalledToolLifecycleHistoryDto[]>()
  const installedToolVersionHistory = new Map<string, InstalledToolVersionHistoryDto[]>()
  const installedToolServiceHistory = new Map<string, InstalledToolServiceHistoryDto[]>()
  const installedToolStages = ['FAT', 'Shipment', 'Installation', 'SAT', 'Warranty'] as const
  let installedToolMutationSequence = 0
  let accountMutationSequence = 0

  function nextAccountModified(accountId: string) {
    accountMutationSequence += 1
    return `${now}#account-${accountId}-${accountMutationSequence}`
  }

  function ensureAccountModified(account: AccountSummaryDto) {
    account.modified ??= `seed-account-${account.id}`
    return account.modified
  }

  function inferredInstalledToolStage(tool: InstalledToolDto) {
    return tool.lifecycleStage
      ?? tool.milestones.find((row) => row.state === 'Current')?.label as InstalledToolDto['lifecycleStage']
      ?? 'FAT'
  }

  function nextInstalledToolModified() {
    installedToolMutationSequence += 1
    return `${now}#${installedToolMutationSequence}`
  }

  function assertInstalledToolRead(tool: InstalledToolDto) {
    if (role === 'Engineer' && tool.engineerOwner !== userId) {
      throw new CrmApiError('SCOPE_DENIED', 'The Installed Tool is outside the current user scope.', requestId(), false)
    }
    if (role === 'Sales' && !canAccessInstalledTool(tool)) {
      throw new CrmApiError('SCOPE_DENIED', 'The Installed Tool is outside the current user scope.', requestId(), false)
    }
  }

  function assertInstalledToolOperator(tool: InstalledToolDto) {
    assertInstalledToolRead(tool)
    if (role !== 'Manager' && !(role === 'Engineer' && tool.engineerOwner === userId)) {
      throw new CrmApiError('PERMISSION_DENIED', 'Only Manager or the assigned Engineer may operate this Installed Tool.', requestId(), false)
    }
  }

  function assertInstalledToolVersion(tool: InstalledToolDto, expectedModified?: string) {
    if (expectedModified !== undefined && expectedModified !== tool.modified) {
      throw new CrmApiError('VERSION_CONFLICT', 'Installed Tool was modified by another request.', requestId(), false)
    }
  }

  function installedToolDetail(tool: InstalledToolDto): InstalledToolDetailDto {
    tool.modified ??= nextInstalledToolModified()
    const lifecycleHistory = installedToolLifecycleHistory.get(tool.id) ?? []
    return {
      ...clone(tool),
      lifecycleStage: inferredInstalledToolStage(tool),
      lifecycleHistory: clone(lifecycleHistory),
      versionHistory: clone(installedToolVersionHistory.get(tool.id) ?? []),
      serviceHistory: clone(installedToolServiceHistory.get(tool.id) ?? []),
      // A type stub only: a test that needs the Sites of the Tool's Account provides them itself.
      sites: [],
      lifecycleCompleted: lifecycleHistory.some((row) => row.toStage === 'Completed')
        || Boolean(tool.milestones.length && tool.milestones.every((row) => row.state === 'Done')),
      canOperate: role === 'Manager' || (role === 'Engineer' && tool.engineerOwner === userId),
      canReassign: role === 'Manager',
    }
  }
  const localContacts = salesRepository.snapshot.contacts
  const localLeads = salesRepository.snapshot.leads
  const localAccounts = salesRepository.snapshot.accounts
  const localAccountSegments = new Set([
    'Frontend',
    'Advanced Packaging',
    ...localAccounts.map((account) => account.segment.trim()).filter(Boolean),
  ])
  const localAccountRegions = new Set(regionOptions(localAccounts.map((account) => account.region)))
  const localSites = salesRepository.snapshot.sites
  const localDocumentRequests: ControlledDocumentAccessRequestDto[] = []
  const localDocumentUploadRequests: DocumentUploadRequestDto[] = []
  const localControlledDocuments = clone(controlledDocuments) as unknown as ControlledDocumentDto[]
  const localStrategyOpportunities: StrategyOpportunityDto[] = salesRepository.snapshot.opportunities
  const localEquipmentTypes = new Set(equipmentOptions(localStrategyOpportunities.map((opportunity) => opportunity.toolType ?? '')))
  // Mirrors services.equipment: a preset in another spelling is stored as the preset; anything else becomes a
  // custom type, added to the options only once the save succeeds.
  function equipmentTypeFor(value: unknown) {
    const text = typeof value === 'string' ? equipmentText(value) : ''
    if (!text) throw new CrmApiError('VALIDATION_ERROR', 'toolType is invalid.', requestId(), false, { toolType: 'Invalid value' })
    return matchingEquipment(text, [...localEquipmentTypes]) || text
  }
  const rfqFiles = mockRfqFilesByRepository.get(salesRepository) ?? new Map<string, { blob: Blob; fileName: string; mimeType: string }>()
  const localRfqs = mockRfqsByRepository.get(salesRepository) ?? []
  mockRfqsByRepository.set(salesRepository, localRfqs)
  mockRfqFilesByRepository.set(salesRepository, rfqFiles)
  let demoPrimaryContactsPromise: Promise<void> | undefined
  localStrategyOpportunities.forEach((opportunity) => {
    opportunity.stakeholders = opportunity.stakeholders.map((stakeholder, index) => ({ ...stakeholder, id: stakeholder.id ?? `STK-${opportunity.id}-${index + 1}` }))
    opportunity.actions = opportunity.actions.map((action, index) => ({ ...action, id: action.id ?? `ACT-${opportunity.id}-${index + 1}` }))
    backfillLossReviews(opportunity)
  })

  function nextRfqModified() {
    return `${now}#${requestId()}`
  }

  function rfqOpportunity(opportunity: StrategyOpportunityDto) {
    return {
      id: opportunity.id, title: opportunity.title, accountId: opportunity.accountId,
      account: opportunity.account, siteId: opportunity.siteId, site: opportunity.site,
      stage: opportunity.stage, owner: opportunity.owner, toolType: opportunity.toolType,
      poDate: opportunity.poDate,
    }
  }

  function assertRfqVisible(rfq: RfqDetailDto) {
    if (role === 'Sales' && rfq.salesOwner !== userId) throw new CrmApiError('SCOPE_DENIED', 'RFQ is outside the current user scope.', requestId(), false)
    if (role === 'Engineer' && rfq.engineerOwner !== userId) throw new CrmApiError('SCOPE_DENIED', 'RFQ is outside the current user scope.', requestId(), false)
  }

  function assertRfqVersion(rfq: RfqDetailDto, expectedModified: string) {
    if (!expectedModified?.trim()) throw new CrmApiError('VALIDATION_ERROR', 'expectedModified is required.', requestId(), false)
    if (rfq.modified !== expectedModified) throw new CrmApiError('VERSION_CONFLICT', 'RFQ was modified by another request.', requestId(), false)
  }

  function restoreSalesSnapshot(snapshot: SalesRepository['snapshot']) {
    localAccounts.splice(0, localAccounts.length, ...structuredClone(snapshot.accounts))
    for (const accountId of Object.keys(localSites)) delete localSites[accountId]
    Object.assign(localSites, structuredClone(snapshot.sites))
    localLeads.splice(0, localLeads.length, ...structuredClone(snapshot.leads))
    localContacts.splice(0, localContacts.length, ...structuredClone(snapshot.contacts))
    localBookings.splice(0, localBookings.length, ...structuredClone(snapshot.bookings))
    localInstalledTools.splice(0, localInstalledTools.length, ...structuredClone(snapshot.installedTools))
    localVisits.splice(0, localVisits.length, ...structuredClone(snapshot.visits))
    localStrategyOpportunities.splice(0, localStrategyOpportunities.length, ...structuredClone(snapshot.opportunities))
    localInternalValidations.splice(0, localInternalValidations.length, ...structuredClone(snapshot.internalValidations))
  }

  function restoreDemoSnapshot(draft: DemoSnapshot, snapshot: DemoSnapshot) {
    draft.version = snapshot.version
    draft.demoRequests = structuredClone(snapshot.demoRequests)
    draft.evaluations = structuredClone(snapshot.evaluations)
    draft.artifacts = structuredClone(snapshot.artifacts)
    if (snapshot.comments) draft.comments = structuredClone(snapshot.comments)
    else delete draft.comments
  }

  async function rollbackContactMutation(
    salesSnapshot: SalesRepository['snapshot'],
    demoSnapshot: DemoSnapshot,
    contactFiles: StoredContactFile[],
  ) {
    restoreSalesSnapshot(salesSnapshot)
    await Promise.allSettled([
      repository.transact((draft) => restoreDemoSnapshot(draft, demoSnapshot)),
      ...contactFiles.map((file) => contactFileRepository.save(file)),
    ])
  }

  function currentAccounts() {
    return localAccounts.map((account) => {
      const modified = ensureAccountModified(account)
      const accountOpportunities = localStrategyOpportunities.filter((opportunity) => opportunity.accountId === account.id)
      const openOpportunities = accountOpportunities.filter((opportunity) => isOpenOpportunityStage(opportunity.stage))
      const currencies = new Set(openOpportunities.map((opportunity) => opportunity.currency))
      const openActions = openOpportunities.flatMap((opportunity) => opportunity.actions)
        .filter((action) => action.status === 'Open')
        .sort((left, right) => left.due.localeCompare(right.due) || left.id.localeCompare(right.id))
      const nextAction = openActions[0]
      return {
        ...account,
        modified,
        pipelineAmount: currencies.size <= 1 ? Number(addMoney(openOpportunities.map((opportunity) => opportunity.amount))) : 0,
        intentScore: accountOpportunities.length
          ? Math.max(...accountOpportunities.map((opportunity) => opportunity.score))
          : 0,
        stakeholderCount: localContacts.filter((contact) => contact.accountId === account.id && contact.status === 'Active').length,
        siteCount: (localSites[account.id] ?? []).length,
        requirementCount: 0,
        risk: nextAction?.due && nextAction.due < today ? '高风险' as const : openOpportunities.length && !nextAction ? '关注' as const : '稳健' as const,
        nextAction: nextAction?.title ?? '',
        nextActionDue: nextAction?.due ?? '',
      }
    })
  }

  function currentPipelineOpportunities(): OpportunityDto[] {
    return localStrategyOpportunities.map((opportunity) => {
      const account = localAccounts.find((item) => item.id === opportunity.accountId)
      const requirement = requirements.find((item) => item.linkedDealId === opportunity.id)
      const nextAction = opportunity.actions
        .filter((action) => action.status === 'Open')
        .sort((a, b) => a.due.localeCompare(b.due))[0]
      return {
        id: opportunity.id,
        accountId: opportunity.accountId,
        accountName: account?.name ?? opportunity.account,
        title: opportunity.title,
        segment: account?.segment ?? 'Frontend',
        amount: opportunity.amount,
        currency: opportunity.currency,
        stage: opportunity.stage as OpportunityDto['stage'],
        probabilityLevel: opportunity.probabilityLevel,
        intentScore: opportunity.score,
        budgetStatus: requirement?.budgetStatus ?? 'Unknown',
        owner: opportunity.owner,
        nextAction: nextAction?.title ?? '',
        due: nextAction?.due ?? opportunity.poDate,
        sourceRequirementId: requirement?.id,
      }
    })
  }

  function canAccessAccount(accountId: string) {
    if (profile.scope === 'all') return true
    const account = localAccounts.find((item) => item.id === accountId)
    if (!account) return false
    if (role === 'Sales') return account.owner === userId || account.visibility === 'Public'
    if (profile.scope === 'own') return account.owner === userId
    return assignedAccountIds.has(accountId)
  }

  function canWriteAccount(accountId: string) {
    if (profile.scope === 'all') return true
    const account = localAccounts.find((item) => item.id === accountId)
    return role === 'Sales' && account?.owner === userId
  }

  function canAccessBusinessAccount(accountId: string) {
    if (profile.scope === 'all') return true
    const account = localAccounts.find((item) => item.id === accountId)
    if (!account) return false
    if (role === 'Sales') return account.owner === userId
    if (profile.scope === 'own') return account.owner === userId
    return assignedAccountIds.has(accountId)
  }

  function canAccessOpportunity(item: { accountId: string; owner: string }) {
    if (profile.scope === 'all') return true
    if (role === 'Sales') return item.owner === userId
    return assignedAccountIds.has(item.accountId)
  }

  function canAccessBooking(item: { accountId: string; owner: string }) {
    if (profile.scope === 'all') return true
    if (role === 'Sales') return item.owner === userId
    return assignedAccountIds.has(item.accountId)
  }

  function canAccessInstalledTool(item: { accountId: string; salesOwner: string; engineerOwner: string }) {
    if (profile.scope === 'all') return true
    if (role === 'Sales') return item.salesOwner === userId
    return item.engineerOwner === userId
  }

  function canAccessVisit(item: { owner: string; actionOwner: string }) {
    if (profile.scope === 'all') return true
    if (role === 'Sales') return item.owner === userId || item.actionOwner === userId
    return false
  }

  // Mirrors the backend `assert_can_change_visit`: an action owner reaches a colleague's
  // visit only to complete that action, so editing it or writing its record is refused.
  function assertCanChangeVisit(visit: { owner: string }) {
    if (role === 'Sales' && visit.owner !== userId) throw new CrmApiError('SCOPE_DENIED', '只有拜访负责人或经理可以修改该拜访', requestId(), false)
  }

  function canAccessRequirement(item: { accountId: string; owner: string }) {
    if (profile.scope === 'all') return true
    if (role === 'Sales') {
      try {
        return migrateLegacyUserId(item.owner, 'requirement.owner') === userId
      } catch {
        return false
      }
    }
    return assignedAccountIds.has(item.accountId)
  }

  function canAccessAction(item: { accountId: string; owner: string }) {
    if (profile.scope === 'all') return true
    if (role === 'Sales') return item.owner === userId
    return assignedAccountIds.has(item.accountId)
  }

  function assertAccountScope(accountId: string) {
    if (!canAccessAccount(accountId)) {
      throw new CrmApiError('SCOPE_DENIED', '当前角色无权访问该客户范围', requestId(), false)
    }
  }

  function assertBusinessAccountScope(accountId: string) {
    if (!canAccessBusinessAccount(accountId)) {
      throw new CrmApiError('SCOPE_DENIED', '当前角色无权访问该客户的业务数据', requestId(), false)
    }
  }

  function canAccessLead(lead: LeadDto) {
    if (profile.scope === 'all') return true
    return lead.owner === userId
  }

  function assertLead(id: string) {
    const lead = localLeads.find((item) => item.id === id)
    if (!lead) throw new CrmApiError('LEAD_NOT_FOUND', '未找到该 Lead', requestId(), false)
    if (!canAccessLead(lead)) throw new CrmApiError('SCOPE_DENIED', '当前角色无权访问该 Lead', requestId(), false)
    return lead
  }

  function scoped<T extends { accountId: string }>(rows: T[], predicate: (item: T) => boolean = (item) => canAccessBusinessAccount(item.accountId)) {
    return rows.filter(predicate)
  }

  function canAccessDemo(request: DemoRequestDto) {
    if (profile.scope === 'all') return true
    if (role === 'Sales') return request.salesOwner === userId
    if (role === 'Engineer') {
      return request.engineerOwner === userId
    }
    return canAccessAccount(request.accountId)
  }

  function assertDemoScope(request: DemoRequestDto) {
    if (!canAccessDemo(request)) {
      throw new CrmApiError('SCOPE_DENIED', '当前角色无权访问该 Demo 负责人范围', requestId(), false)
    }
  }

  function canAccessEvaluation(requests: DemoRequestDto[], evaluation: EvaluationDto) {
    const request = requests.find((item) =>
      item.id === evaluation.demoRequestId || item.evaluationId === evaluation.id,
    )
    if (request) return canAccessDemo(request)
    if (profile.scope === 'all') return true
    if (role === 'Sales') return evaluation.owner === userId
    return evaluation.owner === userId
  }

  function assertEvaluationScope(requests: DemoRequestDto[], evaluation: EvaluationDto) {
    if (!canAccessEvaluation(requests, evaluation)) {
      throw new CrmApiError('SCOPE_DENIED', '当前角色无权访问该 Demo 负责人范围', requestId(), false)
    }
  }

  function canReadDemoArtifact(
    request: DemoRequestDto,
    evaluation: EvaluationDto | undefined,
    artifact: StoredDemoArtifact,
    allowOwnedRequestDocx = false,
  ) {
    const ownedRequestDocx = artifact.type === 'Demo Request DOCX'
      && (artifact.createdBy === userId || request.salesOwner === userId)
    if (allowOwnedRequestDocx && ownedRequestDocx && role === 'Sales') return true
    if (!wasDemoRequestSubmitted(request)) return false
    if (artifact.type === 'Test Report' || artifact.type === 'Customer Report') return Boolean(evaluation)
    if (role === 'Manager') return true
    if (capabilities.includes('demo_request:engineering_review')) return true
    return false
  }

  function assertReportWritable(evaluation: EvaluationDto | undefined) {
    if (!evaluation) return
    if (evaluation.status === 'Accepted' || evaluation.status === 'Rejected') {
      throw new CrmApiError('INVALID_REPORT_STAGE', '终态 Evaluation 不允许修改 Test Run', requestId(), false)
    }
  }

  function validateTestRun(input: CreateTestRunInput) {
    const validWafers = Number.isFinite(input.wafers) && Number.isInteger(input.wafers) && input.wafers > 0
    if (!isIsoDate(input.date) || !input.lot.trim() || !validWafers) throw new CrmApiError('VALIDATION_ERROR', '有效日期、Lot 和正整数 Wafer 数量不能为空', requestId(), false)
    const metrics = [input.capture, input.falsePositive, input.wph]
    const hasMetrics = metrics.some((value) => value != null)
    const completeMetrics = metrics.every((value) => value != null && Number.isFinite(value))
    if (hasMetrics && !completeMetrics) throw new CrmApiError('VALIDATION_ERROR', '完成测试时 Capture、False Positive 和 WPH 必须同时填写', requestId(), false)
    if (completeMetrics && (input.capture! < 0 || input.capture! > 100 || input.falsePositive! < 0 || input.falsePositive! > 100 || input.wph! < 0)) throw new CrmApiError('VALIDATION_ERROR', 'Capture/False Positive 必须在 0–100，WPH 不能为负数', requestId(), false)
    if (completeMetrics && !input.summary.trim()) throw new CrmApiError('VALIDATION_ERROR', '完成 Test Run 时结果摘要不能为空', requestId(), false)
    return completeMetrics
  }

  function activeRunWafers(evaluation: EvaluationDto) {
    return evaluation.runs.filter((run) => run.status !== 'Cancelled').reduce((sum, run) => sum + run.wafers, 0)
  }

  function touchEvaluation(evaluation: EvaluationDto) {
    // The previous token is persisted, so same-tick writes and new API instances
    // cannot reuse a version as an instance-local counter or timestamp alone can.
    const previous = Date.parse(evaluation.modified ?? '')
    evaluation.modified = new Date(Math.max(Date.now(), Number.isFinite(previous) ? previous + 1 : 0)).toISOString()
  }

  function appendTestRunHistory(evaluation: EvaluationDto, summary: string, from: string, to: string) {
    evaluation.history = [{
      id: `${evaluation.id}-H-${(evaluation.history?.length ?? 0) + 1}`,
      actor: userId, at: shanghaiTimestamp(), eventType: 'Test Run', from, to, summary,
    }, ...(evaluation.history ?? [])]
  }

  function accountForViewer(account: AccountSummaryDto) {
    if (canAccessBusinessAccount(account.id)) return account
    return {
      ...account,
      pipelineAmount: 0,
      intentScore: 0,
      siteCount: 0,
      requirementCount: 0,
      risk: '稳健' as const,
      nextAction: '',
      nextActionDue: '',
    }
  }

  function visibleAccounts() {
    return currentAccounts().filter((account) => canAccessAccount(account.id)).map(accountForViewer)
  }

  async function wait() {
    if (latency > 0) await new Promise((resolve) => setTimeout(resolve, latency))
  }

  function openOpportunities() {
    return currentPipelineOpportunities().filter((item) => isOpenOpportunityStage(item.stage))
  }

  function validateDemoRequest(request: DemoRequestDto) {
    const errors = validateDemoRequestFormData(
      getDemoRequestFormData(request),
      { requireCustomerInformation: request.requestMode !== 'Self Test' },
    )
    const firstError = Object.values(errors)[0]
    if (firstError) throw new CrmApiError('VALIDATION_ERROR', firstError, requestId(), false)
  }

  function nextId(prefix: string, rows: Array<{ id: string }>) {
    const next = Math.max(0, ...rows.map((item) => Number(item.id.match(/(\d+)$/)?.[1] ?? 0))) + 1
    return `${prefix}-${String(next).padStart(3, '0')}`
  }

  function assertOpportunity(id: string) {
    const opportunity = localStrategyOpportunities.find((item) => item.id === id)
    if (!opportunity) throw new CrmApiError('OPPORTUNITY_NOT_FOUND', '未找到该 Opportunity', requestId(), false)
    assertAccountScope(opportunity.accountId)
    return opportunity
  }

  // Mirrors rayher_crm.services.regions: any spelling of a known region is stored as that region,
  // and a new custom region must be written in English.
  function accountRegion(value: string) {
    const text = collapseRegion(value)
    const region = matchingRegion(text, [...localAccountRegions]) || text
    if (!region) throw new CrmApiError('VALIDATION_ERROR', 'region is required.', requestId(), false, { region: 'Required' })
    if (!localAccountRegions.has(region) && !isEnglishRegion(region)) {
      throw new CrmApiError('VALIDATION_ERROR', 'region must be an English region name.', requestId(), false, { region: 'Use an English region name' })
    }
    return region
  }

  function opportunityRegion(value: string) {
    const text = collapseRegion(value)
    if (!text) throw new CrmApiError('VALIDATION_ERROR', 'subRegion is required.', requestId(), false, { subRegion: 'Required' })
    const region = matchingRegion(text, [...localAccountRegions])
    if (!region) throw new CrmApiError('VALIDATION_ERROR', 'subRegion is not a known region.', requestId(), false, { subRegion: 'Unknown region' })
    return region
  }

  // Mirrors opportunities.required_positive_money: an amount Sales must enter, above 0 with at most two decimals.
  function requiredPositiveMoney(value: unknown, field: string): string {
    const text = String(value ?? '').trim()
    if (!text) throw new CrmApiError('VALIDATION_ERROR', `${field} is required.`, requestId(), false, { [field]: 'Required' })
    let normalized = ''
    try { normalized = normalizeMoney(text) } catch { normalized = '' }
    if (!normalized || Number(normalized) <= 0) {
      throw new CrmApiError('VALIDATION_ERROR', `${field} must be positive with at most two decimal places.`, requestId(), false, { [field]: 'Invalid amount' })
    }
    return normalized
  }

  function validateOpportunity(input: Pick<CreateStrategyOpportunityInput, 'accountId' | 'siteId' | 'title' | 'owner' | 'amount' | 'poDate'> & { amountCny?: unknown; score: number; probabilityLevel: unknown }) {
    if ([input.accountId, input.siteId, input.title, input.owner, input.poDate].some((value) => !String(value ?? '').trim())) {
      throw new CrmApiError('VALIDATION_ERROR', '请完整填写 Opportunity 必填信息', requestId(), false)
    }
    let normalizedAmount: string
    try { normalizedAmount = normalizeMoney(input.amount) }
    catch { throw new CrmApiError('VALIDATION_ERROR', '金额必须为 DECIMAL(20,2) 字符串', requestId(), false) }
    if (Number(normalizedAmount) <= 0) throw new CrmApiError('VALIDATION_ERROR', '金额必须大于 0', requestId(), false)
    requiredPositiveMoney(input.amountCny, 'amountCny')
    if (!Number.isFinite(input.score) || input.score < 0 || input.score > 100) {
      throw new CrmApiError('VALIDATION_ERROR', '金额必须为非负数，购买意愿必须在 0 到 100 之间', requestId(), false)
    }
    if (!isOpportunityProbabilityLevelValue(input.probabilityLevel)) {
      throw new CrmApiError('VALIDATION_ERROR', '成功概率档位不符合后端契约', requestId(), false, { probabilityLevel: 'Invalid' })
    }
    validateOwner(input.owner, role === 'Manager' ? ['Sales', 'Manager'] : ['Sales'])
  }

  // Whoever opens an Opportunity sets its first level; every change after that is the owner's.
  function assertProbabilityLevelOwner(owner: string) {
    if (owner !== userId) throw new CrmApiError('PERMISSION_DENIED', 'Only the Opportunity owner can set the probability level.', requestId(), false)
  }

  function probabilityHistoryEntry(from: StrategyOpportunityDto['probabilityLevel'], to: StrategyOpportunityDto['probabilityLevel'], reason = '') {
    return {
      id: nextId('PLH', localStrategyOpportunities.flatMap((item) => item.probabilityHistory)),
      from,
      to,
      reason,
      actor: userId,
      at: new Date(now).toISOString(),
    }
  }

  const localInternalValidations: StoredOpportunityInternalValidation[] = salesRepository.snapshot.internalValidations
  // Every Opportunity write moves `modified`, so a workflow action sent with a stale version is refused as on the server.
  function touchOpportunity(opportunity: StrategyOpportunityDto) {
    opportunity.updated = '刚刚'
    opportunity.modified = nextRecoveryVersion(opportunity.modified)
  }

  function nextRecoveryVersion(previous?: string) {
    const previousTime = Date.parse(previous ?? '')
    return new Date(Math.max(Date.parse(now), Number.isFinite(previousTime) ? previousTime + 1 : 0)).toISOString()
  }

  function recoveryPlan(value: unknown, field = 'plan') {
    if (typeof value !== 'string' || !value.trim() || value.trim().length > 4000) {
      throw new CrmApiError('VALIDATION_ERROR', 'A recovery plan of 1–4000 characters is required.', requestId(), false, { [field]: 'Enter 1–4000 characters' })
    }
    return value.trim()
  }

  function newRecovery(eventId: string, plan: string): ProbabilityRecoveryDto {
    const modified = nextRecoveryVersion()
    return { id: `REC-${eventId}`, plan, modified, state: 'pending', history: [{ id: `REC-${eventId}-1`, kind: 'Created', plan, actor: userId, at: modified }] }
  }

  function requireOpportunityVersion(opportunity: StrategyOpportunityDto, expectedModified?: string) {
    if (!expectedModified?.trim()) throw new CrmApiError('VALIDATION_ERROR', 'expectedModified is required.', requestId(), false)
    if (expectedModified !== opportunity.modified) throw new CrmApiError('VERSION_CONFLICT', 'The record was changed by another request.', requestId(), false)
  }

  function lockOpportunityForAction(id: string, expectedModified?: string) {
    const opportunity = assertOpportunity(id)
    if (expectedModified && opportunity.modified && expectedModified !== opportunity.modified) {
      throw new CrmApiError('VERSION_CONFLICT', 'The record was changed by another request.', requestId(), false)
    }
    return opportunity
  }

  function requireOpportunityStage(opportunity: StrategyOpportunityDto, stages: readonly OpportunityStage[], action: string) {
    if (!stages.includes(opportunity.stage)) {
      throw new CrmApiError('INVALID_TRANSITION', `${action} is not available at ${opportunity.stage}.`, requestId(), false)
    }
  }

  function requireProbabilityLevel(opportunity: StrategyOpportunityDto) {
    if (!opportunity.probabilityLevel) {
      throw new CrmApiError('VALIDATION_ERROR', 'Set the probability level before this step.', requestId(), false, { probabilityLevel: 'Required' })
    }
  }

  function requiredActionText(value: unknown, field: string) {
    const text = typeof value === 'string' ? value.trim() : ''
    if (!text) throw new CrmApiError('VALIDATION_ERROR', `${field} is required.`, requestId(), false, { [field]: 'Required' })
    return text
  }

  function requiredActionDate(value: unknown, field: string) {
    const text = requiredActionText(value, field)
    if (!isIsoDate(text)) throw new CrmApiError('VALIDATION_ERROR', `${field} must be a real YYYY-MM-DD date.`, requestId(), false)
    return text
  }

  interface StageMoveDetails {
    source: OpportunityStageHistorySource
    event: OpportunityStageHistoryEvent
    referenceDoctype?: string
    referenceName?: string
    reason?: string
    reachedAt?: string
    reachedAtBasis?: OpportunityReachedAtBasis
  }

  function stageHistoryRow(from: OpportunityStage | '', to: OpportunityStage, details: StageMoveDetails): OpportunityStageHistoryDto {
    const recordedAt = new Date(now).toISOString()
    return {
      id: nextId('OSH', localStrategyOpportunities.flatMap((item) => item.stageHistory ?? [])),
      from,
      to,
      source: details.source,
      event: details.event,
      referenceDoctype: details.referenceDoctype ?? '',
      referenceName: details.referenceName ?? '',
      reason: details.reason ?? '',
      actor: userId,
      recordedAt,
      reachedAt: details.reachedAt ?? recordedAt,
      reachedAtBasis: details.reachedAtBasis ?? 'recorded',
    }
  }

  // The stage and its history row change together, as _move_stage does on the server.
  function moveOpportunityStage(opportunity: StrategyOpportunityDto, to: OpportunityStage, details: StageMoveDetails) {
    const row = stageHistoryRow(opportunity.stage, to, details)
    opportunity.stageHistory.unshift(row)
    opportunity.stage = to
    opportunity.stageChangedAt = row.reachedAt || row.recordedAt
    touchOpportunity(opportunity)
    return row
  }

  // Mirrors services.loss_review: one post-mortem per marked_lost event, kept when the deal reopens,
  // newest first; a review is its own record, so it never moves the Opportunity's `modified`.
  function appendLossReviewRevision(review: LossReviewDto, kind: string, options: { actor?: string; at?: string; reason?: string } = {}) {
    review.history.unshift({
      id: `${review.id}-${review.history.length + 1}`, kind, status: review.status, note: review.reviewNote,
      reason: options.reason ?? '', actor: options.actor ?? userId, at: options.at ?? review.modified,
    })
  }

  function createLossReview(opportunity: StrategyOpportunityDto, event: OpportunityStageHistoryDto, reopening?: OpportunityStageHistoryDto) {
    const review: LossReviewDto = {
      id: `LR-${event.id}`, opportunityId: opportunity.id, stageEventId: event.id,
      lostAt: event.reachedAt || event.recordedAt, lostAtStage: event.from, lostBy: event.actor, lostReason: event.reason,
      status: 'pending', reviewNote: '', reviewedBy: null, reviewedAt: null, reopenedAt: reopening?.recordedAt ?? null,
      modified: nextRecoveryVersion(), history: [],
    }
    appendLossReviewRevision(review, 'Created', { actor: event.actor, at: event.recordedAt })
    if (reopening) appendLossReviewRevision(review, 'Reopened', { actor: reopening.actor, at: reopening.recordedAt })
    opportunity.lossReviews = [review, ...(opportunity.lossReviews ?? [])]
    return review
  }

  // Like backfill_loss_reviews: stored deals lost before reviews existed get a pending one per loss; safe to repeat.
  // The stage history is kept newest first, and the mock clock can stamp several rows alike, so order is by position.
  function backfillLossReviews(opportunity: StrategyOpportunityDto) {
    const events = [...(opportunity.stageHistory ?? [])].reverse()
    const known = new Set((opportunity.lossReviews ?? []).map((review) => review.stageEventId))
    const missing = events.filter((event) => event.event === 'marked_lost' && !known.has(event.id))
    if (!missing.length) return
    for (const event of missing) createLossReview(opportunity, event, events.slice(events.indexOf(event) + 1).find((row) => row.event === 'reopened'))
    // Keep the list newest first even when only older losses were missing.
    const position = new Map(opportunity.stageHistory.map((row, index) => [row.id, index]))
    opportunity.lossReviews!.sort((a, b) => (position.get(a.stageEventId) ?? -1) - (position.get(b.stageEventId) ?? -1))
  }

  function markLossReviewsReopened(opportunity: StrategyOpportunityDto, event: OpportunityStageHistoryDto) {
    for (const review of opportunity.lossReviews ?? []) {
      if (review.reopenedAt) continue
      review.reopenedAt = event.recordedAt
      review.modified = nextRecoveryVersion(review.modified)
      appendLossReviewRevision(review, 'Reopened', { at: event.recordedAt })
    }
  }

  function lossReviewText(value: unknown, field: 'reviewNote' | 'revertReason', message: string) {
    const text = typeof value === 'string' ? value.trim() : ''
    if (!text || text.length > 4000) throw new CrmApiError('VALIDATION_ERROR', message, requestId(), false, { [field]: 'Enter 1-4000 characters' })
    return text
  }

  function expectedTimestamp(value: unknown) {
    if (typeof value !== 'string' || !value.trim()) throw new CrmApiError('VALIDATION_ERROR', 'expectedModified is required.', requestId(), false)
    const text = value.trim()
    const parsed = Date.parse(text)
    if (!Number.isFinite(parsed)) throw new CrmApiError('VALIDATION_ERROR', 'expectedModified must be an ISO timestamp.', requestId(), false)
    if (!/(Z|[+-]\d{2}:?\d{2})$/i.test(text)) throw new CrmApiError('VALIDATION_ERROR', 'expectedModified must include a timezone.', requestId(), false)
    return parsed
  }

  function appendOpportunityHistory(opportunity: StrategyOpportunityDto, field: string, from: string, to: string) {
    opportunity.history.unshift({ at: historyAt, actor: userId, field, from, to })
  }

  const AUTOMATIC_STAGE_EVENTS = {
    demo_customer_review: ['qualified_opportunity', 'demo_done'],
    rfq_approved: ['customer_budget_approved', 'rfq_validated'],
    quotation_published: ['rfq_validated', 'quotation_sent'],
  } as const satisfies Record<string, readonly [OpportunityMilestoneStage, OpportunityMilestoneStage]>

  // A server workflow moves its Opportunity to the milestone it reached. Already past it is a no-op; behind it is a conflict.
  function advanceOpportunityForEvent(
    opportunityId: string,
    event: keyof typeof AUTOMATIC_STAGE_EVENTS,
    reference: { referenceDoctype: string; referenceName: string },
  ) {
    const opportunity = localStrategyOpportunities.find((item) => item.id === opportunityId)
    if (!opportunity) throw new CrmApiError('OPPORTUNITY_NOT_FOUND', 'Opportunity was not found.', requestId(), false)
    const [requiredStage, targetStage] = AUTOMATIC_STAGE_EVENTS[event]
    if (opportunity.stage === 'lost') {
      // Customer feedback on a lost deal is still recorded; it does not reopen the deal.
      if (event === 'demo_customer_review') return
      throw new CrmApiError('INVALID_TRANSITION', 'A lost Opportunity cannot be advanced by workflow completion.', requestId(), false)
    }
    if (opportunityStageIndex(opportunity.stage) >= opportunityStageIndex(targetStage)) return
    if (opportunity.stage !== requiredStage) {
      throw new CrmApiError('CONFLICT', `Opportunity must be at ${requiredStage} before workflow completion can move it to ${targetStage}.`, requestId(), false)
    }
    moveOpportunityStage(opportunity, targetStage, { source: 'event', event, ...reference })
    salesRepository.save()
  }

  function latestInternalValidation(opportunityId: string): OpportunityInternalValidationDto | null {
    const latest = localInternalValidations
      .filter((item) => item.opportunityId === opportunityId)
      .sort((left, right) => right.attemptNo - left.attemptNo)[0]
    if (!latest) return null
    const { opportunityId: _opportunityId, ...validation } = clone(latest)
    return validation
  }

  function liveOpportunityBooking(opportunityId: string) {
    return localBookings.find((item) => item.source === 'Opportunity' && item.sourceOpportunityId === opportunityId && item.status !== 'Cancelled')
  }

  // The summary names the Booking, but its details stay inside the Booking scope, as on the server.
  function liveBookingSummary(opportunityId: string): OpportunityLiveBookingDto | null {
    const booking = liveOpportunityBooking(opportunityId)
    if (!booking) return null
    const summary: OpportunityLiveBookingDto = { id: booking.id, status: booking.status as OpportunityLiveBookingDto['status'] }
    if (!canAccessBooking(booking)) return summary
    return {
      ...summary,
      primaryContactId: booking.primaryContactId,
      equipment: booking.equipment,
      quantity: booking.quantity,
      ddl: booking.ddl,
      amount: booking.amount,
      currency: booking.currency,
      owner: booking.owner,
      note: booking.note,
      /** Version used by PO confirmation to reject a stale Pending Booking form. */
      modified: booking.modified,
      actualPoDate: booking.actualPoDate ?? '',
      amountCny: booking.amountCny ?? '',
    }
  }

  // Derived on every read: the latest request and the live Booking summary follow the stored rows and the viewer's scope.
  function withDerivedOpportunityState(opportunity: StrategyOpportunityDto): StrategyOpportunityDto {
    return {
      ...opportunity,
      internalValidation: latestInternalValidation(opportunity.id),
      liveBooking: liveBookingSummary(opportunity.id),
    }
  }

  function opportunityResponse(opportunity: StrategyOpportunityDto) {
    return response(withDerivedOpportunityState(opportunity))
  }

  function cancelPendingInternalValidation(opportunity: StrategyOpportunityDto, reason: string) {
    const pending = localInternalValidations.find((item) => item.opportunityId === opportunity.id && item.status === 'pending')
    if (!pending) return
    Object.assign(pending, { status: 'cancelled', cancelledBy: userId, cancelledAt: new Date(now).toISOString(), cancelReason: reason })
    appendOpportunityHistory(opportunity, 'internalValidationCancelled', pending.id, reason)
  }

  function nextInternalValidationId() {
    const next = Math.max(0, ...localInternalValidations.map((item) => Number(item.id.match(/(\d+)$/)?.[1] ?? 0))) + 1
    return `CRM-VAL-${String(next).padStart(5, '0')}`
  }

  // Mirrors bookings.validate_booking_amount_cny and cny_amount_text: a CNY order's amount already is its CNY amount,
  // another currency needs one once the order is confirmed.
  function bookingAmountCny(currency: string, amount: string, value: unknown, required: boolean): string {
    if (currency === 'CNY') return amount
    if (!String(value ?? '').trim()) {
      if (required) throw new CrmApiError('VALIDATION_ERROR', 'amountCny is required.', requestId(), false, { amountCny: 'Required' })
      return ''
    }
    return requiredPositiveMoney(value, 'amountCny')
  }

  // Mirrors validate_booking_draft: account, source and type follow the Opportunity, and Sales fills in the rest.
  function validateOpportunityBookingDraft(opportunity: StrategyOpportunityDto, draft: unknown, requireAmountCny = false): BookingDraft {
    if (!draft || typeof draft !== 'object' || Array.isArray(draft)) {
      throw new CrmApiError('VALIDATION_ERROR', 'booking is required.', requestId(), false, { booking: 'Required' })
    }
    const value = draft as Partial<Record<keyof BookingDraft, unknown>>
    const primaryContactId = requiredActionText(value.primaryContactId, 'primaryContactId')
    const contact = localContacts.find((item) => item.id === primaryContactId)
    if (!contact) throw new CrmApiError('CONTACT_NOT_FOUND', 'Contact was not found.', requestId(), false)
    if (contact.accountId !== opportunity.accountId) throw new CrmApiError('CONTACT_ACCOUNT_MISMATCH', 'The contact belongs to another account.', requestId(), false)
    if (contact.status !== 'Active') throw new CrmApiError('CONTACT_INACTIVE', 'The contact must be active.', requestId(), false)
    const ddl = requiredActionDate(value.ddl, 'ddl')
    const currency = requiredActionText(value.currency, 'currency').toUpperCase()
    const equipment = requiredActionText(value.equipment, 'equipment')
    const quantity = typeof value.quantity === 'number' || typeof value.quantity === 'string' ? Number(value.quantity) : Number.NaN
    if (!Number.isInteger(quantity) || quantity < 1) throw new CrmApiError('VALIDATION_ERROR', 'quantity must be a positive integer.', requestId(), false)
    let amount: string
    try { amount = normalizeMoney(String(value.amount ?? '')) }
    catch { throw new CrmApiError('VALIDATION_ERROR', 'amount must be non-negative with at most two decimal places.', requestId(), false) }
    const owner = validateOwner(typeof value.owner === 'string' ? value.owner : '', ['Sales'])
    const amountCny = currency === 'CNY' ? '' : bookingAmountCny(currency, amount, value.amountCny, requireAmountCny)
    return { primaryContactId, equipment, quantity, ddl, amount, currency, amountCny, owner, note: typeof value.note === 'string' ? value.note.trim() : '' }
  }

  function applyOpportunityBookingDraft(booking: BookingDto, draft: BookingDraft) {
    const contact = localContacts.find((item) => item.id === draft.primaryContactId)
    const amountCny = draft.currency === 'CNY' ? draft.amount : draft.amountCny ?? ''
    // A correction's reason describes the amount it came with, so it goes when that amount does.
    if (amountCny !== (booking.currency === 'CNY' ? booking.amount : booking.amountCny ?? '')) booking.amountCnyNote = ''
    Object.assign(booking, {
      title: `${draft.equipment} · ${draft.quantity} 台`,
      primaryContactId: draft.primaryContactId,
      customerContact: contact?.name ?? booking.customerContact,
      equipment: draft.equipment,
      quantity: draft.quantity,
      ddl: draft.ddl,
      amount: draft.amount,
      currency: draft.currency,
      amountCny,
      owner: draft.owner,
      note: draft.note,
      modified: `${now}#${requestId()}`,
    })
    return booking
  }

  // Mirrors bookings.validate_actual_po_date: the date on the customer's PO, never in the future.
  function validateActualPoDate(value: unknown, required: boolean) {
    const date = String(value ?? '').trim()
    if (!date) {
      if (required) throw new CrmApiError('VALIDATION_ERROR', 'actualPoDate is required.', requestId(), false, { actualPoDate: 'Required' })
      return ''
    }
    if (!isIsoDate(date)) throw new CrmApiError('VALIDATION_ERROR', 'actualPoDate must be a real YYYY-MM-DD date.', requestId(), false)
    if (date > today) throw new CrmApiError('VALIDATION_ERROR', 'actualPoDate cannot be in the future.', requestId(), false, { actualPoDate: 'Cannot be in the future' })
    return date
  }

  // Only PO confirmation and an approved internal validation create Opportunity Bookings.
  function createOpportunityBooking(opportunity: StrategyOpportunityDto, draft: BookingDraft, status: 'Pending' | 'Confirmed', actualPoDate = '') {
    const booking: BookingDto = {
      id: nextId('BKG', localBookings),
      accountId: opportunity.accountId,
      accountName: localAccounts.find((item) => item.id === opportunity.accountId)?.name ?? opportunity.account,
      title: '',
      primaryContactId: '',
      customerContact: '',
      equipment: '',
      quantity: 1,
      ddl: '',
      amount: '0.00',
      currency: 'CNY',
      status,
      bookingDate: today,
      owner: '',
      source: 'Opportunity',
      bookingType: opportunity.saleType === 'Service' ? 'Service' : 'Equipment',
      sourceOpportunityId: opportunity.id,
      note: '',
      // An approved internal validation creates a Pending Booking before any PO exists.
      actualPoDate,
      actualPoDateSource: actualPoDate ? 'po_confirmation' : '',
      actualPoDateNote: '',
    }
    localBookings.unshift(applyOpportunityBookingDraft(booking, draft))
    return booking
  }

  async function saveOpportunityStakeholderInternal(
    opportunityId: string,
    input: CreateOpportunityStakeholderInput | UpdateOpportunityStakeholderInput,
    stakeholderId?: string,
  ) {
    await wait()
    assertCapability(capabilities, 'deal:write')
    const opportunity = assertOpportunity(opportunityId)
    const contact = localContacts.find((item) => item.id === input.contactId)
    if (!contact) throw new CrmApiError('CONTACT_NOT_FOUND', '未找到联系人', requestId(), false)
    if (contact.accountId !== opportunity.accountId) throw new CrmApiError('CONTACT_ACCOUNT_MISMATCH', '联系人不属于该商机客户', requestId(), false)
    if (contact.status !== 'Active') throw new CrmApiError('CONTACT_INACTIVE', '只能关联在职联系人', requestId(), false)
    if ([input.role, input.influence, input.stance, input.coverage].some((value) => !value.trim())) {
      throw new CrmApiError('VALIDATION_ERROR', '请完整填写关键人信息', requestId(), false)
    }
    const index = stakeholderId ? opportunity.stakeholders.findIndex((item) => item.id === stakeholderId) : -1
    if (stakeholderId && index < 0) throw new CrmApiError('STAKEHOLDER_NOT_FOUND', '未找到该关键人', requestId(), false)
    const id = stakeholderId ?? nextId('STK', localStrategyOpportunities.flatMap((item) => item.stakeholders))
    if (opportunity.stakeholders.some((item) => item.contactId === input.contactId && item.id !== id)) {
      throw new CrmApiError('DUPLICATE_OPPORTUNITY_CONTACT', '同一联系人不能重复关联到该商机', requestId(), false)
    }
    const stakeholder = { ...input, id, name: contact.name, title: contact.title }
    if (index >= 0) opportunity.stakeholders[index] = stakeholder
    else opportunity.stakeholders.push(stakeholder)
    opportunity.history.unshift({ at: historyAt, actor: userId, field: 'Stakeholder', from: index >= 0 ? 'Updated' : '', to: stakeholder.name })
    salesRepository.save()
    return response(stakeholder)
  }

  async function saveOpportunityActionInternal(
    opportunityId: string,
    input: CreateOpportunityActionInput | UpdateOpportunityActionInput,
    actionId?: string,
  ) {
    await wait()
    assertCapability(capabilities, 'deal:write')
    const opportunity = assertOpportunity(opportunityId)
    if ([input.title, input.owner, input.due, input.status].some((value) => !value.trim())) {
      throw new CrmApiError('VALIDATION_ERROR', '请完整填写 Action 信息', requestId(), false)
    }
    const owner = validateOwner(input.owner, ['Sales', 'Engineer'])
    const index = actionId ? opportunity.actions.findIndex((item) => item.id === actionId) : -1
    if (actionId && index < 0) throw new CrmApiError('ACTION_NOT_FOUND', '未找到该 Action', requestId(), false)
    const id = actionId ?? nextId('ACT', localStrategyOpportunities.flatMap((item) => item.actions))
    if (input.remark !== undefined && (typeof input.remark !== 'string' || input.remark.length > 10000)) {
      throw new CrmApiError('VALIDATION_ERROR', 'Remark must be text of at most 10000 characters.', requestId(), false)
    }
    const action = { ...input, id, owner, remark: input.remark?.trim() ?? (index >= 0 ? opportunity.actions[index].remark ?? '' : '') }
    if (index >= 0) opportunity.actions[index] = action
    else opportunity.actions.push(action)
    opportunity.history.unshift({ at: historyAt, actor: userId, field: 'Action', from: index >= 0 ? 'Updated' : '', to: action.title })
    salesRepository.save()
    return response(action)
  }

  function addRequestHistory(request: DemoRequestDto, from: DemoRequestDto['status'] | '', to: DemoRequestDto['status'], actor: string, comment: string) {
    request.history.unshift({ at: now, actor, from, to, comment })
    request.updatedAt = now
    markProgress(request, comment, actor)
  }

  function markProgress(request: DemoRequestDto | undefined, summary: string, actor = userId) {
    if (!request) return
    request.tracking.lastProgressAt = now
    request.tracking.lastProgressSummary = summary
    request.tracking.lastProgressActor = actor
  }

  function contactsForAccount(accountId: string) {
    return localContacts.filter((contact) => contact.accountId === accountId)
  }

  function assertActiveContactForAccount(contactId: string, accountId: string) {
    const contact = localContacts.find((item) => item.id === contactId)
    if (!contact) throw new CrmApiError('CONTACT_NOT_FOUND', '未找到联系人', requestId(), false)
    if (contact.accountId !== accountId) {
      throw new CrmApiError('CONTACT_ACCOUNT_MISMATCH', '联系人不属于当前客户', requestId(), false)
    }
    if (contact.status !== 'Active') {
      throw new CrmApiError('CONTACT_INACTIVE', '离职或归档联系人不能新增业务关联', requestId(), false)
    }
    return contact
  }

  function expandBookingContact<T extends { primaryContactId: string; customerContact: string }>(booking: T): T {
    const contact = localContacts.find((item) => item.id === booking.primaryContactId)
    return { ...booking, customerContact: contact?.name ?? '联系人已缺失' }
  }

  // Mirrors _validate_source: an Upsell names no Opportunity, and an Opportunity keeps at most one live Booking.
  function validateBookingSource(input: UpsertBookingInput, bookingId?: string) {
    const sourceOpportunityId = String(input.sourceOpportunityId ?? '').trim()
    if (input.source !== 'Opportunity') {
      if (sourceOpportunityId) throw new CrmApiError('BOOKING_SOURCE_INVALID', 'Upsell Booking must not reference an Opportunity.', requestId(), false)
      return
    }
    if (!sourceOpportunityId) throw new CrmApiError('BOOKING_SOURCE_REQUIRED', 'Opportunity Booking requires a source Opportunity.', requestId(), false)
    const source = localStrategyOpportunities.find((item) => item.id === sourceOpportunityId)
    if (source?.accountId !== input.accountId) {
      throw new CrmApiError('BOOKING_SOURCE_INVALID', 'Source Opportunity must belong to the Account.', requestId(), false)
    }
    if (localBookings.some((item) => item.sourceOpportunityId === sourceOpportunityId && item.status !== 'Cancelled' && item.id !== bookingId)) {
      throw new CrmApiError('BOOKING_ALREADY_EXISTS', 'The Opportunity already has a live Booking.', requestId(), false)
    }
  }

  // Mirrors _assert_opportunity_booking_edit: an Opportunity Booking follows its Opportunity, so only its details and a manual cancel change.
  function assertOpportunityBookingEdit(current: BookingDto, input: UpsertBookingInput) {
    if (current.source !== 'Opportunity') return
    const fixed: Array<[unknown, string]> = [
      [input.accountId, current.accountId],
      [input.source, current.source],
      [input.sourceOpportunityId ?? current.sourceOpportunityId, current.sourceOpportunityId ?? ''],
      [input.bookingType ?? current.bookingType, current.bookingType ?? 'Equipment'],
    ]
    if (fixed.some(([value, expected]) => String(value ?? '') !== expected)) {
      throw new CrmApiError('BOOKING_SOURCE_INVALID', 'Account, source, Opportunity and type of an Opportunity Booking cannot change.', requestId(), false)
    }
    if (input.status !== current.status && (input.status !== 'Cancelled' || current.status === 'Cancelled')) {
      throw new CrmApiError('BOOKING_STATUS_INVALID', 'An Opportunity Booking can only be changed to Cancelled.', requestId(), false)
    }
  }

  function expandDemoContact(request: DemoRequestDto): DemoRequestDto {
    const contact = localContacts.find((item) => item.id === request.primaryContactId)
    if (!contact) return clone(request)
    return {
      ...clone(request),
      formData: { ...getDemoRequestFormData(request), contactPerson: formatContactDisplayLine(contact) },
    }
  }

  function ensureDemoPrimaryContacts() {
    demoPrimaryContactsPromise ??= repository.transact((snapshot) => {
      const retainedContacts = localContacts.filter((contact) => !isRetiredLocalContact(contact))
      const preparedRequests = snapshot.demoRequests.map((request) => {
        const linked = retainedContacts.some((contact) =>
          contact.id === request.primaryContactId && contact.accountId === request.accountId,
        )
        if (linked) return request
        const replacement = retainedContacts.find((contact) =>
          contact.accountId === request.accountId && contact.status === 'Active',
        )
        return replacement ? { ...request, primaryContactId: replacement.id } : request
      })
      const migrated = migrateLegacyPrimaryContacts(retainedContacts, [], preparedRequests)
      localContacts.splice(0, localContacts.length, ...migrated.contacts.filter((contact) => !isRetiredLocalContact(contact)))
      snapshot.demoRequests.splice(0, snapshot.demoRequests.length, ...migrated.demoRequests)
      salesRepository.save()
    }).catch((error) => {
      demoPrimaryContactsPromise = undefined
      throw error
    })
    return demoPrimaryContactsPromise
  }

  function contactSummary(contact: ContactDto): ContactSummaryDto {
    const account = currentAccounts().find((item) => item.id === contact.accountId)
    const site = (localSites[contact.accountId] ?? []).find((item) => item.id === contact.siteId)
    const opportunityRoles = localStrategyOpportunities.flatMap((opportunity) =>
      opportunity.stakeholders
        .filter((link) => link.contactId === contact.id)
        .map((link) => link.role),
    )
    return {
      ...contact,
      accountName: account?.name ?? '客户已缺失',
      accountShortName: account?.shortName ?? '-',
      ...(site ? { siteName: site.name } : {}),
      opportunityRoles: [...new Set(opportunityRoles)],
    }
  }

  function mapLegacyStakeholderInput(input: CreateStakeholderInput | UpdateStakeholderInput): CreateContactInput {
    const account = currentAccounts().find((item) => item.id === input.accountId)
    return {
      accountId: input.accountId,
      name: input.name,
      title: input.title,
      department: input.department,
      relationship: input.relationship,
      owner: account?.owner ?? userId,
      status: 'Active',
      reportsToContactId: input.reportsTo,
      reportsTo: input.reportsTo,
      email: input.email,
      role: input.role,
      influence: input.influence,
    }
  }

  const listContactsInternal = async (query: ContactListQuery) => {
    await ensureDemoPrimaryContacts()
    await wait()
    assertCapability(capabilities, 'contact:view')
    if (query.accountId && query.accountId !== 'All') assertAccountScope(query.accountId)
    const page = query.page ?? 1
    const pageSize = query.pageSize ?? 20
    const filtered = localContacts
      .filter((contact) => canAccessAccount(contact.accountId))
      .filter((contact) =>
        (!query.accountId || query.accountId === 'All' || contact.accountId === query.accountId) &&
        (!query.siteId || query.siteId === 'All' || contact.siteId === query.siteId) &&
        (!query.contactId || contact.id === query.contactId) &&
        (!query.contactStatus || query.contactStatus === 'All' || contact.status === query.contactStatus) &&
        (!query.owner || query.owner === 'All' || contact.owner === query.owner) &&
        (!query.search || includes(`${contact.name} ${contact.title} ${contact.department} ${contact.phone ?? ''} ${contact.email ?? ''}`, query.search)),
      )
      .map(contactSummary)
    const result = response({ items: filtered.slice((page - 1) * pageSize, page * pageSize) })
    result.meta = { ...result.meta!, page, pageSize, total: filtered.length }
    return result
  }

  const saveContactInternal = async (input: CreateContactInput | UpdateContactInput, id?: string) => {
    await wait()
    assertCapability(capabilities, 'contact:write')
    assertAccountScope(input.accountId)
    if (!canWriteAccount(input.accountId)) throw new CrmApiError('SCOPE_DENIED', '只有客户负责人可以编辑联系人', requestId(), false)
    const account = currentAccounts().find((item) => item.id === input.accountId)
    if (!account) throw new CrmApiError('ACCOUNT_NOT_FOUND', '未找到该客户', requestId(), false)
    if ([input.name, input.title, input.department, input.owner].some((value) => !String(value ?? '').trim())) {
      throw new CrmApiError('VALIDATION_ERROR', '请完整填写联系人必填信息', requestId(), false)
    }
    const owner = validateOwner(input.owner, ['Sales'])
    if (!['Active', 'Left Company', 'Archived'].includes(input.status)) {
      throw new CrmApiError('VALIDATION_ERROR', '联系人状态无效', requestId(), false)
    }
    const existing = id ? localContacts.find((contact) => contact.id === id) : undefined
    if (id && !existing) throw new CrmApiError('CONTACT_NOT_FOUND', '未找到该联系人', requestId(), false)
    if (existing && existing.accountId !== input.accountId) {
      throw new CrmApiError('CONTACT_ACCOUNT_MISMATCH', '联系人不能跨客户移动', requestId(), false)
    }
    if (input.siteId && !(localSites[input.accountId] ?? []).some((site) => site.id === input.siteId)) {
      throw new CrmApiError('CONTACT_ACCOUNT_MISMATCH', '所选厂区不属于该客户', requestId(), false)
    }
    const reportsToContactId = input.reportsToContactId ?? input.reportsTo
    const parent = reportsToContactId ? localContacts.find((contact) => contact.id === reportsToContactId) : undefined
    if (reportsToContactId && !parent) throw new CrmApiError('CONTACT_NOT_FOUND', '未找到直属上司', requestId(), false)
    if (parent && parent.accountId !== input.accountId) {
      throw new CrmApiError('CONTACT_ACCOUNT_MISMATCH', '直属上司必须属于同一客户', requestId(), false)
    }
    if (parent && parent.status !== 'Active') {
      throw new CrmApiError('VALIDATION_ERROR', '直属上司必须为在职联系人', requestId(), false)
    }
    const contactId = id ?? nextId('CON', localContacts)
    try {
      validateReportingLine(localContacts, contactId, reportsToContactId)
    } catch (error) {
      throw new CrmApiError('INVALID_REPORTING_LINE', error instanceof Error ? error.message : '汇报关系无效', requestId(), false)
    }
    const contact: ContactDto = {
      ...(existing ?? {}),
      ...clone(input),
      id: contactId,
      accountId: input.accountId,
      name: input.name.trim(),
      title: input.title.trim(),
      department: input.department.trim(),
      owner,
      ...(input.phone?.trim() ? { phone: input.phone.trim() } : {}),
      ...(input.email?.trim() ? { email: input.email.trim() } : {}),
      ...(reportsToContactId ? { reportsToContactId } : {}),
      dataQuality: 'Complete',
      updatedAt: today,
    }
    if (!reportsToContactId) {
      delete contact.reportsToContactId
      delete contact.reportsTo
    }
    const index = localContacts.findIndex((item) => item.id === contactId)
    if (index >= 0) localContacts[index] = contact
    else localContacts.push(contact)
    salesRepository.save()
    return response(contactSummary(contact))
  }

  const saveLeadInternal = async (input: CreateLeadInput | UpdateLeadInput, id?: string) => {
    await wait()
    assertCapability(capabilities, 'deal:write')
    if ([input.name, input.company, input.title, input.source, input.status, input.owner].some((value) => !String(value ?? '').trim())) {
      throw new CrmApiError('VALIDATION_ERROR', '请完整填写 Lead 姓名、公司、职位、来源、状态与负责人', requestId(), false)
    }
    if (!input.phone?.trim() && !input.email?.trim()) {
      throw new CrmApiError('VALIDATION_ERROR', '电话和邮箱至少填写一项', requestId(), false)
    }
    const allowedStatuses: LeadDto['status'][] = ['New', 'Working', 'Qualified', 'Nurturing', 'Disqualified', 'Converted']
    const allowedSources: LeadDto['source'][] = ['Website', 'Trade Show', 'Partner Referral', 'Outbound', 'Customer Referral', 'Other']
    if (!allowedStatuses.includes(input.status) || !allowedSources.includes(input.source)) {
      throw new CrmApiError('VALIDATION_ERROR', 'Lead 状态或来源无效', requestId(), false)
    }
    const existing = id ? assertLead(id) : undefined
    if (existing?.status === 'Converted') {
      throw new CrmApiError('LEAD_ALREADY_CONVERTED', '已转换的 Lead 不能再编辑', requestId(), false)
    }
    const owner = validateOwner(input.owner, ['Sales'])
    const lead: LeadDto = {
      ...clone(input),
      id: existing?.id ?? nextId('LEAD', localLeads),
      name: input.name.trim(),
      company: input.company.trim(),
      title: input.title.trim(),
      phone: input.phone?.trim(),
      email: input.email?.trim(),
      owner,
      interest: input.interest.trim(),
      firstContactNote: input.firstContactNote.trim(),
      nextAction: input.nextAction.trim(),
      activities: clone(input.activities ?? existing?.activities ?? []),
      createdAt: existing?.createdAt ?? today,
      updatedAt: today,
    }
    if (existing) Object.assign(existing, lead)
    else localLeads.unshift(lead)
    salesRepository.save()
    return response(lead)
  }

  const getContactInternal = async (id: string) => {
    await ensureDemoPrimaryContacts()
    await wait()
    assertCapability(capabilities, 'contact:view')
    const contact = localContacts.find((item) => item.id === id)
    if (!contact) throw new CrmApiError('CONTACT_NOT_FOUND', '未找到该联系人', requestId(), false)
    assertAccountScope(contact.accountId)
    const demoSnapshot = await repository.read()
    const opportunitiesForContact = scoped(localStrategyOpportunities, canAccessOpportunity)
      .filter((opportunity) => opportunity.accountId === contact.accountId)
      .flatMap((opportunity) => opportunity.stakeholders
        .filter((link) => link.contactId === id)
        .map((link) => ({
          id: opportunity.id,
          title: opportunity.title,
          stage: opportunity.stage,
          role: link.role,
          href: `/opportunities?contactId=${id}`,
          updated: opportunity.updated,
        })))
    const bookingsForContact = scoped(localBookings, canAccessBooking).filter((item) => item.primaryContactId === id).map((item) => ({
      id: item.id, title: item.title, status: item.status,
      href: `/booking?contactId=${id}`,
    }))
    const demosForContact = demoSnapshot.demoRequests.filter((item) => canAccessDemo(item) && item.primaryContactId === id).map((item) => ({
      id: item.id, title: item.title, status: item.status, href: `/demo-requests?contactId=${id}`,
    }))
    const visitsForContact = scoped(localVisits, canAccessVisit).filter((item) => item.primaryContactId === id).map((item) => ({
      id: item.id, subject: item.subject, date: item.date, href: `/visits?contactId=${id}`,
    }))
    const timeline = [
      ...opportunitiesForContact.map(({ updated, ...opportunity }) => ({
        id: `opportunity:${opportunity.id}`,
        at: updated,
        type: 'Opportunity' as const,
        title: opportunity.title,
        summary: opportunity.role,
        href: opportunity.href,
      })),
      ...visitsForContact.map((visit) => ({
        id: `visit:${visit.id}`,
        at: visit.date,
        type: 'Visit' as const,
        title: visit.subject,
        summary: 'Customer visit',
        href: visit.href,
      })),
      ...demosForContact.map((request) => ({
        id: `demo-request:${request.id}`,
        at: demoSnapshot.demoRequests.find((item) => item.id === request.id)?.updatedAt ?? '',
        type: 'Demo Request' as const,
        title: request.title,
        summary: request.status,
        href: request.href,
      })),
      ...bookingsForContact.map((booking) => ({
        id: `booking:${booking.id}`,
        at: localBookings.find((item) => item.id === booking.id)?.modified
          ?? localBookings.find((item) => item.id === booking.id)?.bookingDate ?? '',
        type: 'Booking' as const,
        title: booking.title,
        summary: booking.status,
        href: booking.href,
      })),
    ].sort((left, right) => right.at.localeCompare(left.at))
    const reportsTo = contact.reportsToContactId
      ? localContacts.find((item) => item.id === contact.reportsToContactId)
      : undefined
    const detail: ContactDetailDto = {
      contact: contactSummary(contact),
      ...(reportsTo ? { reportsTo: contactSummary(reportsTo) } : {}),
      directReports: localContacts.filter((item) => item.reportsToContactId === id).map(contactSummary),
      opportunities: opportunitiesForContact.map(({ updated: _updated, ...opportunity }) => opportunity),
      visits: visitsForContact,
      demoRequests: demosForContact,
      bookings: bookingsForContact,
      timeline,
    }
    return response(detail)
  }

  const listContactFilesInternal = async (contactId: string, query: ListQuery = {}) => {
    await wait()
    assertCapability(capabilities, 'contact:view')
    const contact = localContacts.find((item) => item.id === contactId)
    if (!contact) throw new CrmApiError('CONTACT_NOT_FOUND', '未找到该联系人', requestId(), false)
    assertBusinessAccountScope(contact.accountId)
    const files = await contactFileRepository.list(contactId)
    return pageResponse(files
      .map(contactFileMeta)
      .sort((left, right) => right.uploadedAt.localeCompare(left.uploadedAt)), query)
  }

  const uploadContactFilesInternal = async (contactId: string, files: MultipartFilePart[]) => {
    await wait()
    assertCapability(capabilities, 'contact:write')
    const contact = localContacts.find((item) => item.id === contactId)
    if (!contact) throw new CrmApiError('CONTACT_NOT_FOUND', '未找到该联系人', requestId(), false)
    assertBusinessAccountScope(contact.accountId)
    if (!canWriteAccount(contact.accountId)) throw new CrmApiError('SCOPE_DENIED', '只有客户负责人可以上传文件', requestId(), false)
    if (!files.length) throw new CrmApiError('VALIDATION_ERROR', '请选择要上传的文件', requestId(), false)
    files.forEach(validateContactFileUpload)
    const uploaded: ContactFileMetaDto[] = []
    for (const [index, input] of files.entries()) {
      const file: StoredContactFile = {
        id: `CF-${Date.now().toString(36)}-${index}-${Math.random().toString(36).slice(2, 8)}`,
        contactId,
        fileName: input.fileName.trim(),
        mimeType: input.mimeType || 'application/octet-stream',
        size: input.size,
        uploadedAt: new Date().toISOString(),
        uploadedBy: userId,
        blob: input.blob,
      }
      await contactFileRepository.save(file)
      uploaded.push(contactFileMeta(file))
    }
    return response(uploaded)
  }

  const getContactFileInternal = async (fileId: string) => {
    await wait()
    assertCapability(capabilities, 'contact:view')
    const file = await contactFileRepository.get(fileId)
    if (!file) throw new CrmApiError('CONTACT_FILE_NOT_FOUND', '未找到该文件', requestId(), false)
    const contact = localContacts.find((item) => item.id === file.contactId)
    if (!contact) throw new CrmApiError('CONTACT_NOT_FOUND', '未找到文件关联的联系人', requestId(), false)
    assertBusinessAccountScope(contact.accountId)
    return { blob: file.blob, fileName: file.fileName, mimeType: file.mimeType }
  }

  const deleteContactFileInternal = async (fileId: string) => {
    await wait()
    assertCapability(capabilities, 'contact:write')
    const file = await contactFileRepository.get(fileId)
    if (!file) throw new CrmApiError('CONTACT_FILE_NOT_FOUND', '未找到该文件', requestId(), false)
    const contact = localContacts.find((item) => item.id === file.contactId)
    if (!contact) throw new CrmApiError('CONTACT_NOT_FOUND', '未找到文件关联的联系人', requestId(), false)
    assertBusinessAccountScope(contact.accountId)
    if (!canWriteAccount(contact.accountId)) throw new CrmApiError('SCOPE_DENIED', '只有客户负责人可以删除文件', requestId(), false)
    await contactFileRepository.remove(fileId)
    return response({ id: fileId })
  }

  const mergeContactsInternal = async ({ survivorId, duplicateId }: { survivorId: string; duplicateId: string }) => {
    await ensureDemoPrimaryContacts()
    await wait()
    assertCapability(capabilities, 'contact:merge')
    if (survivorId === duplicateId) throw new CrmApiError('VALIDATION_ERROR', '不能合并同一联系人', requestId(), false)
    const survivor = localContacts.find((contact) => contact.id === survivorId)
    const duplicate = localContacts.find((contact) => contact.id === duplicateId)
    if (!survivor || !duplicate) throw new CrmApiError('CONTACT_NOT_FOUND', '未找到待合并联系人', requestId(), false)
    assertAccountScope(survivor.accountId)
    assertAccountScope(duplicate.accountId)
    if (survivor.accountId !== duplicate.accountId) {
      throw new CrmApiError('CONTACT_ACCOUNT_MISMATCH', '仅可合并同一客户的联系人', requestId(), false)
    }
    if (localStrategyOpportunities.some((opportunity) => {
      const ids = new Set(opportunity.stakeholders.map((link) => link.contactId))
      return ids.has(survivorId) && ids.has(duplicateId)
    })) {
      throw new CrmApiError('CONTACT_MERGE_CONFLICT', '同一商机已关联两个待合并联系人', requestId(), false)
    }
    const prospectiveContacts = localContacts.map((contact) => ({
      ...contact,
      ...(contact.reportsToContactId === duplicateId ? { reportsToContactId: survivorId } : {}),
      ...(contact.reportsTo === duplicateId ? { reportsTo: survivorId } : {}),
    }))
    try {
      for (const contact of prospectiveContacts) {
        validateReportingLine(prospectiveContacts, contact.id, contact.reportsToContactId)
      }
    } catch (error) {
      throw new CrmApiError(
        'INVALID_REPORTING_LINE',
        error instanceof Error ? `合并会使汇报关系无效：${error.message}` : '合并会使汇报关系无效',
        requestId(),
        false,
      )
    }
    const salesBefore = structuredClone(salesRepository.snapshot)
    const demoBefore = await repository.read()
    const filesBefore = await contactFileRepository.list(duplicateId)
    try {
      await contactFileRepository.reassignContact(duplicateId, survivorId)
      for (const opportunity of localStrategyOpportunities) {
        opportunity.stakeholders = opportunity.stakeholders.map((link) => link.contactId === duplicateId
          ? { ...link, contactId: survivorId, name: survivor.name, title: survivor.title }
          : link)
      }
      for (const contact of localContacts) {
        if (contact.reportsToContactId === duplicateId) contact.reportsToContactId = survivorId
        if (contact.reportsTo === duplicateId) contact.reportsTo = survivorId
      }
      for (let index = 0; index < localBookings.length; index += 1) {
        if (localBookings[index].primaryContactId === duplicateId) {
          localBookings[index] = expandBookingContact({ ...localBookings[index], primaryContactId: survivorId })
        }
      }
      for (const visit of localVisits) {
        if (visit.primaryContactId === duplicateId) visit.primaryContactId = survivorId
      }
      await repository.transact((snapshot) => {
        snapshot.demoRequests = snapshot.demoRequests.map((request) => request.primaryContactId === duplicateId
          ? expandDemoContact({ ...request, primaryContactId: survivorId })
          : request)
      })
      duplicate.status = 'Archived'
      duplicate.mergedIntoContactId = survivorId
      duplicate.updatedAt = today
      salesRepository.save()
      return response(contactSummary(survivor))
    } catch (error) {
      await rollbackContactMutation(salesBefore, demoBefore, filesBefore)
      throw error
    }
  }

  const deleteContactInternal = async (id: string) => {
    await wait()
    assertCapability(capabilities, 'contact:delete')
    const visibleContact = localContacts.find((item) => item.id === id)
    if (!visibleContact) throw new CrmApiError('CONTACT_NOT_FOUND', '未找到联系人', requestId(), false)
    assertAccountScope(visibleContact.accountId)
    await ensureDemoPrimaryContacts()
    const contactIndex = localContacts.findIndex((item) => item.id === id)
    const contact = localContacts[contactIndex]
    if (!contact) throw new CrmApiError('CONTACT_NOT_FOUND', '未找到联系人', requestId(), false)
    const replacement = localContacts.find((item) =>
      item.id !== id &&
      item.accountId === contact.accountId &&
      item.status === 'Active' &&
      item.name.trim().toLocaleLowerCase() === contact.name.trim().toLocaleLowerCase(),
    ) ?? localContacts.find((item) =>
      item.id !== id && item.accountId === contact.accountId && item.status === 'Active',
    )
    const salesBefore = structuredClone(salesRepository.snapshot)
    const demoBefore = await repository.read()
    const filesBefore = await contactFileRepository.list(id)
    try {
      for (const opportunity of localStrategyOpportunities) {
        opportunity.stakeholders = opportunity.stakeholders.filter((stakeholder) => stakeholder.contactId !== id)
      }
      for (let index = 0; index < localBookings.length; index += 1) {
        if (localBookings[index].primaryContactId !== id) continue
        localBookings[index] = {
          ...localBookings[index],
          primaryContactId: replacement?.id ?? '',
          customerContact: replacement?.name ?? localBookings[index].customerContact,
        }
      }
      for (const visit of localVisits) {
        if (visit.primaryContactId !== id) continue
        if (replacement) visit.primaryContactId = replacement.id
        else delete visit.primaryContactId
      }
      for (const item of localContacts) {
        if (item.reportsToContactId === id) delete item.reportsToContactId
        if (item.reportsTo === id) delete item.reportsTo
      }
      await repository.transact((snapshot) => {
        for (const request of snapshot.demoRequests) {
          if (request.primaryContactId !== id) continue
          const fallback = replacement ?? localContacts.find((item) =>
            item.id !== id && item.accountId === request.accountId && item.status === 'Active',
          )
          request.primaryContactId = fallback?.id ?? ''
        }
      })
      await contactFileRepository.removeForContact(id)
      localContacts.splice(contactIndex, 1)
      salesRepository.save()
      return response({ id, status: 'Deleted' as const })
    } catch (error) {
      await rollbackContactMutation(salesBefore, demoBefore, filesBefore)
      throw error
    }
  }

  const reviewUnavailable = async (): Promise<never> => {
    assertCapability(capabilities, 'cockpit:view')
    throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Review requires the business API.', 'review_unavailable', false)
  }
  // Contract-only placeholders for the document library: no capability of their own is asserted, so a Sales or
  // Engineer test client is refused for this reason and not for cockpit:view, and a Manager is not told that
  // Review is unavailable.
  const documentsUnavailable = async (): Promise<never> => {
    throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Opportunity documents require the business API.', 'documents_unavailable', false)
  }
  const boardUnavailable = async (): Promise<never> => {
    assertCapability(capabilities, "deal:view")
    throw new CrmApiError("BACKEND_NOT_CONNECTED", "Opportunities board requires the business API.", "board_unavailable", false)
  }
  const mockApi: CrmApi = {
    queryOpportunities: boardUnavailable,
    exportOpportunities: boardUnavailable,
    getQueryRecipients: boardUnavailable,
    shareOpportunityQuery: boardUnavailable,
    getOpportunityFilters: boardUnavailable,
    listOpportunityQueries: boardUnavailable,
    saveOpportunityQuery: boardUnavailable,
    deleteOpportunityQuery: boardUnavailable,
    getPlan: async () => {
      assertCapability(capabilities, 'cockpit:view')
      throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Plan requires the business API.', 'plan_unavailable', false)
    },
    getPlanDetails: async () => {
      assertCapability(capabilities, 'cockpit:view')
      throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Plan requires the business API.', 'plan_unavailable', false)
    },
    getReview: reviewUnavailable,
    getOpportunityDocuments: documentsUnavailable,
    saveOpportunityDocumentLinks: documentsUnavailable,
    getReviewDetails: reviewUnavailable,
    saveReviewTarget: reviewUnavailable,
    async savePlanCommitment() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Plan commitments require Frappe', requestId(), false) },
    getReviewTarget: reviewUnavailable,
    getWarnings: reviewUnavailable,
    getTerritoryCatalogue: reviewUnavailable,
    saveTerritory: reviewUnavailable,
    saveTerritoryAssignment: reviewUnavailable,
    getCockpitSettings: reviewUnavailable,
    saveCockpitSettings: reviewUnavailable,
    saveWarningPlan: reviewUnavailable,
    recordWarningAction: reviewUnavailable,
    // Same rules and order of checks as services.loss_review.review_loss.
    async reviewOpportunityLoss(id: string, reviewId: string, input: LossReviewInput, expectedModified: string) {
      await wait()
      assertCapability(capabilities, 'deal:write')
      if (role !== 'Manager') throw new CrmApiError('PERMISSION_DENIED', 'Only a Manager can confirm a lost-deal post-mortem.', requestId(), false)
      const opportunity = assertOpportunity(id)
      const status = input?.status
      if (status !== 'Reviewed' && status !== 'Pending') throw new CrmApiError('VALIDATION_ERROR', 'status is invalid.', requestId(), false, { status: 'Invalid value' })
      // Marking done needs the conclusion; reverting needs its own reason and keeps the conclusion.
      const note = status === 'Reviewed' ? lossReviewText(input.reviewNote, 'reviewNote', 'A post-mortem conclusion of 1-4000 characters is required.') : ''
      const reason = status === 'Pending' ? lossReviewText(input.revertReason, 'revertReason', 'A reason of 1-4000 characters is required to revert a post-mortem.') : ''
      const expected = expectedTimestamp(expectedModified)
      const review = localStrategyOpportunities.flatMap((item) => item.lossReviews ?? []).find((item) => item.id === reviewId)
      if (!review) throw new CrmApiError('NOT_FOUND', 'CRM Opportunity Loss Review was not found.', requestId(), false)
      if (expected !== Date.parse(review.modified)) throw new CrmApiError('VERSION_CONFLICT', 'The record was changed by another request.', requestId(), false)
      if (review.opportunityId !== opportunity.id) throw new CrmApiError('NOT_FOUND', 'The loss review was not found.', requestId(), false)
      if (status === 'Pending' && review.status !== 'reviewed') {
        throw new CrmApiError('INVALID_TRANSITION', 'Only a reviewed loss can be reverted to pending.', requestId(), false)
      }
      if (status === 'Reviewed' && review.status === 'reviewed' && review.reviewNote === note) return response(review)
      const kind = status === 'Pending' ? 'ReviewReverted' : review.status === 'reviewed' ? 'ReviewUpdated' : 'Reviewed'
      review.modified = nextRecoveryVersion(review.modified)
      if (status === 'Reviewed') Object.assign(review, { status: 'reviewed', reviewNote: note, reviewedBy: userId, reviewedAt: review.modified })
      else Object.assign(review, { status: 'pending', reviewedBy: null, reviewedAt: null })
      appendLossReviewRevision(review, kind, { reason })
      salesRepository.save()
      return response(review)
    },
    async getBootstrap() {
      await wait()
      return response({
        user: { id: userId, name: userName, initials: activePerson?.initials ?? userName.split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase(), role, team: activePerson?.team ?? role },
        capabilities,
        personnel: PERSONNEL,
        version: 'MVP Mock 0.1',
      })
    },

    async getDashboard(_query: DashboardQuery) {
      await wait()
      assertCapability(capabilities, 'dashboard:view')
      const snapshot = await repository.read()
      return response(buildManagementDashboard({
        asOf: historyAt,
        accounts: visibleAccounts(),
        actions: scoped(localActions, canAccessAction),
        bookings: scoped(localBookings, canAccessBooking),
        demoRequests: snapshot.demoRequests.filter(canAccessDemo),
        evaluations: snapshot.evaluations.filter((item) => canAccessEvaluation(snapshot.demoRequests, item)),
        opportunities: scoped(localStrategyOpportunities, canAccessOpportunity),
        requirements: scoped(requirements, canAccessRequirement),
        visits: scoped(localVisits, canAccessVisit),
      }))
    },

    async listAccounts(query: ListQuery) {
      await wait()
      assertCapability(capabilities, 'account:view')
      const page = query.page ?? 1
      const pageSize = query.pageSize ?? 20
      const filtered = visibleAccounts().filter((item) =>
        (!query.search || includes(`${item.name} ${item.shortName} ${item.owner}`, query.search)) &&
        (!query.accountId || item.id === query.accountId) &&
        (!query.segment || query.segment === 'All' || item.segment === query.segment) &&
        (!query.city || query.city === 'All' || item.city === query.city) &&
        (!query.region || query.region === 'All' || item.region === (matchingRegion(query.region, [...localAccountRegions]) || collapseRegion(query.region))),
      )
      const start = (page - 1) * pageSize
      const result = response({ items: filtered.slice(start, start + pageSize) })
      result.meta = { ...result.meta!, page, pageSize, total: filtered.length }
      return result
    },

    async listAccountSegments() {
      await wait()
      assertCapability(capabilities, 'account:view')
      return response([...localAccountSegments])
    },

    async listEquipmentTypes() {
      await wait()
      assertCapability(capabilities, 'deal:view')
      return response(equipmentOptions([...localEquipmentTypes]))
    },

    async listAccountRegions() {
      await wait()
      assertCapability(capabilities, 'account:view')
      return response(regionOptions([...localAccountRegions]))
    },

    async listAccountCities() {
      await wait()
      assertCapability(capabilities, 'account:view')
      const cities = visibleAccounts()
        .map((account) => account.city.trim())
        .filter(Boolean)
      return response([...new Set(cities)].sort((left, right) => left.localeCompare(right, 'zh-CN')))
    },

    async createAccount(input: CreateAccountInput) {
      await wait()
      assertCapability(capabilities, 'account:write')
      if ([input.name, input.shortName, input.segment, input.city, input.region, input.owner].some((value) => !value.trim())) {
        throw new CrmApiError('VALIDATION_ERROR', '请完整填写客户必填信息', requestId(), false)
      }
      const owner = validateOwner(input.owner, ['Sales'])
      const segment = input.segment.trim()
      const region = accountRegion(input.region)
      const account: AccountSummaryDto = {
        id: nextId('ACC', localAccounts), name: input.name.trim(), shortName: input.shortName.trim(), segment,
        tier: input.tier, city: input.city.trim(), region, owner, pipelineAmount: 0, intentScore: 0,
        stakeholderCount: 0, siteCount: 0, requirementCount: 0, completeness: 45, risk: '关注' as const,
        nextAction: '补齐客户档案与关键人', nextActionDue: today, updatedAt: '刚刚', visibility: input.visibility ?? 'Private',
      }
      account.modified = nextAccountModified(account.id)
      localAccounts.unshift(account)
      localAccountSegments.add(segment)
      localAccountRegions.add(region)
      localSites[account.id] = []
      salesRepository.save()
      return response(account)
    },

    async updateAccount(id: string, input: CreateAccountInput, expectedModified?: string) {
      await wait()
      assertCapability(capabilities, 'account:write')
      assertAccountScope(id)
      if ([input.name, input.shortName, input.segment, input.city, input.region, input.owner].some((value) => !value.trim())) {
        throw new CrmApiError('VALIDATION_ERROR', '请完整填写客户必填信息', requestId(), false)
      }
      const index = localAccounts.findIndex((item) => item.id === id)
      if (index < 0) throw new CrmApiError('ACCOUNT_NOT_FOUND', '未找到该客户', requestId(), false)
      const currentModified = ensureAccountModified(localAccounts[index])
      if (!expectedModified?.trim()) throw new CrmApiError("VALIDATION_ERROR", "expectedModified is required.", requestId(), false)
      if (expectedModified !== currentModified) throw new CrmApiError("VERSION_CONFLICT", "Account was modified by another request.", requestId(), false)
      if (role === 'Sales' && localAccounts[index].owner !== userId) {
        throw new CrmApiError('SCOPE_DENIED', '只有客户负责人可以编辑该客户', requestId(), false)
      }
      const owner = validateOwner(input.owner, ['Sales'])
      const name = input.name.trim()
      const segment = input.segment.trim()
      const region = accountRegion(input.region)
      localAccounts[index] = {
        ...localAccounts[index],
        name,
        shortName: input.shortName.trim(),
        segment,
        tier: input.tier,
        city: input.city.trim(),
        region,
        owner,
         modified: nextAccountModified(id),
        visibility: input.visibility ?? localAccounts[index].visibility ?? 'Private',
        updatedAt: '刚刚',
      }
      localAccountSegments.add(segment)
      localAccountRegions.add(region)
      localBookings.forEach((item) => { if (item.accountId === id) item.accountName = name })
      localVisits.forEach((item) => { if (item.accountId === id) item.accountName = name })
      localContracts.forEach((item) => { if (item.accountId === id) item.accountName = name })
      localStrategyOpportunities.forEach((item) => { if (item.accountId === id) item.account = name })
      localInstalledTools.forEach((item) => { if (item.accountId === id) item.account = name })
      await repository.transact((draft) => {
        draft.demoRequests.forEach((item) => { if (item.accountId === id) item.accountName = name })
        draft.evaluations.forEach((item) => { if (item.accountId === id) item.accountName = name })
      })
      salesRepository.save()
      return response(currentAccounts().find((item) => item.id === id)!)
    },

    // The archive is a server rule with no behaviour here; tests stub these (AGENTS.md).
    async archiveAccount(id: string) {
      await wait()
      throw new CrmApiError('INVALID_TRANSITION', `The mock API does not archive Accounts (${id}).`, requestId(), false)
    },
    async unarchiveAccount(id: string) {
      await wait()
      throw new CrmApiError('INVALID_TRANSITION', `The mock API does not archive Accounts (${id}).`, requestId(), false)
    },

    async listAccountSites() {
      throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Account sites require the business API.', 'account_sites_unavailable', false)
    },

    async getAccount360(id: string) {
      await ensureDemoPrimaryContacts()
      await wait()
      assertCapability(capabilities, 'account:view')
      const ownsInstalledToolAtAccount = role === 'Engineer'
        && localInstalledTools.some((tool) => tool.accountId === id && tool.engineerOwner === userId)
      if (!ownsInstalledToolAtAccount) assertAccountScope(id)
      const account = currentAccounts().find((item) => item.id === id)
      const snapshot = await repository.read()
      if (!account) throw new CrmApiError('ACCOUNT_NOT_FOUND', '未找到该客户', requestId(), false)
      const accountSites = canAccessBusinessAccount(id) ? localSites[id] ?? [] : []
      const accountContacts = contactsForAccount(id).map(contactSummary)
      const accountRequirements = scoped(requirements, canAccessRequirement).filter((item) => item.accountId === id)
      const accountOpportunities = scoped(currentPipelineOpportunities(), canAccessOpportunity).filter((item) => item.accountId === id)
      const accountBookings = scoped(localBookings, canAccessBooking).filter((item) => item.accountId === id).map(expandBookingContact)
      const accountDemos = snapshot.demoRequests.filter(canAccessDemo).filter((item) => item.accountId === id).map(expandDemoContact)
      const accountEvaluations = snapshot.evaluations.filter((item) => canAccessEvaluation(snapshot.demoRequests, item)).filter((item) => item.accountId === id)
      const accountContracts = scoped(localContracts).filter((item) => item.accountId === id)
      const accountActions = scoped(localActions, canAccessAction).filter((item) => item.accountId === id)
      const accountVisits = scoped(localVisits, canAccessVisit).filter((item) => item.accountId === id)
      return response({
        account: accountForViewer(account),
        sites: accountSites,
        contacts: accountContacts,
        requirements: accountRequirements,
        opportunities: accountOpportunities,
        bookings: accountBookings,
        demoRequests: accountDemos,
        evaluations: accountEvaluations,
        quotations: [],
        contracts: accountContracts,
        actions: accountActions,
        visits: accountVisits,
        summary: {
          activeDemos: accountEvaluations.filter((item) => !['Accepted','Rejected'].includes(item.status)).length,
          contractsAtRisk: accountContracts.filter((item) => (getContractRisk(item.end).band !== 'normal' || !item.signed)).length,
          lastVisit: accountVisits.filter((item) => item.status !== 'Planned').map((item) => item.date).sort().at(-1) ?? '—',
        },
      })
    },

    async createAccountSite(accountId: string, input: Omit<SiteDto, 'id'>) {
      await wait()
      assertCapability(capabilities, 'account:write')
      assertAccountScope(accountId)
      if (!canWriteAccount(accountId)) throw new CrmApiError('SCOPE_DENIED', '只有客户负责人可以编辑厂区', requestId(), false)
      if ([input.name, input.city, input.type, input.process, input.status].some((value) => !value.trim())) {
        throw new CrmApiError('VALIDATION_ERROR', 'Please complete all Site fields.', requestId(), false)
      }
      const site: SiteDto = { ...clone(input), id: nextId('SITE', Object.values(localSites).flat()) }
      ;(localSites[accountId] ??= []).unshift(site)
      salesRepository.save()
      return response(site)
    },

    async updateAccountSite(accountId: string, siteId: string, input: Omit<SiteDto, 'id'>) {
      await wait()
      assertCapability(capabilities, 'account:write')
      assertAccountScope(accountId)
      if (!canWriteAccount(accountId)) throw new CrmApiError('SCOPE_DENIED', '只有客户负责人可以编辑厂区', requestId(), false)
      const siteIndex = (localSites[accountId] ?? []).findIndex((item) => item.id === siteId)
      if (siteIndex < 0) throw new CrmApiError('NOT_FOUND', 'Site was not found.', requestId(), false)
      if ([input.name, input.city, input.type, input.process, input.status].some((value) => !value.trim())) {
        throw new CrmApiError('VALIDATION_ERROR', 'Please complete all Site fields.', requestId(), false)
      }
      localSites[accountId][siteIndex] = { ...clone(input), id: siteId }
      salesRepository.save()
      return response(localSites[accountId][siteIndex])
    },

    async deleteAccountSite(accountId: string, siteId: string) {
      await wait()
      assertCapability(capabilities, 'account:write')
      assertAccountScope(accountId)
      if (!canWriteAccount(accountId)) throw new CrmApiError('SCOPE_DENIED', '只有客户负责人可以编辑厂区', requestId(), false)
      const sites = localSites[accountId] ?? []
      const siteIndex = sites.findIndex((item) => item.id === siteId)
      if (siteIndex < 0) throw new CrmApiError('NOT_FOUND', 'Site was not found.', requestId(), false)
      sites.splice(siteIndex, 1)
      salesRepository.save()
      return response({ id: siteId })
    },

    async listVisits(query: ListQuery) {
      await wait()
      assertCapability(capabilities, 'visit:view')
      const filtered = scoped(localVisits, canAccessVisit).filter((item) =>
        (!query.search || includes(`${item.accountName} ${item.subject} ${item.objective}`, query.search)) &&
        (!query.accountId || query.accountId === 'All' || item.accountId === query.accountId) &&
        (!query.contactId || item.primaryContactId === query.contactId) &&
        (!query.status || query.status === 'All' || item.status === query.status) &&
        (!query.owner || query.owner === 'All' || item.owner === query.owner) &&
        (!query.dateFrom || item.date >= query.dateFrom) &&
        (!query.dateTo || item.date <= query.dateTo),
      )
      return pageResponse(filtered.sort((a, b) => b.date.localeCompare(a.date)), query)
    },

    async getVisit(id: string) {
      await wait()
      assertCapability(capabilities, 'visit:view')
      const visit = scoped(localVisits, canAccessVisit).find((item) => item.id === id)
      if (!visit) throw new CrmApiError('VISIT_NOT_FOUND', '未找到拜访', requestId(), false)
      return response(visit)
    },

    async getVisitDetail(id: string) {
      await wait()
      assertCapability(capabilities, 'visit:view')
      const visit = scoped(localVisits, canAccessVisit).find((item) => item.id === id)
      if (!visit) throw new CrmApiError('VISIT_NOT_FOUND', '未找到该拜访记录', requestId(), false)
      const primaryContact = visit.primaryContactId
        ? contactsForAccount(visit.accountId).find((item) => item.id === visit.primaryContactId)
        : undefined
      const attachments = [...meetingFiles.entries()].filter(([, item]) => item.visitId === id).map(([fileId, item]) => ({
        id: fileId, visitId: id, fileName: item.fileName, mimeType: item.mimeType, size: item.blob.size,
        uploadedAt: item.uploadedAt, uploadedBy: item.uploadedBy,
      }))
      return response({ ...visit, primaryContact: primaryContact ? contactSummary(primaryContact) : undefined, meetingRecord: meetingRecords.get(id) ?? null, attachments } as VisitDetailDto)
    },

    async createVisit(input: CreateVisitInput) {
      await wait()
      assertCapability(capabilities, 'visit:create')
      assertAccountScope(input.accountId)
      try { validateCreateVisit(input) } catch (error) {
        throw new CrmApiError('VALIDATION_ERROR', error instanceof Error ? error.message : '拜访信息不完整', requestId(), false)
      }
      const owner = validateOwner(input.owner, ['Sales'])
      const account = currentAccounts().find((item) => item.id === input.accountId)
      if (!account) throw new CrmApiError('ACCOUNT_NOT_FOUND', '未找到该客户', requestId(), false)
      if (input.primaryContactId) assertActiveContactForAccount(input.primaryContactId, input.accountId)
      const visit = {
        id: nextId('V', localVisits), accountId: account.id, accountName: account.name, segment: account.segment,
        ...(input.primaryContactId ? { primaryContactId: input.primaryContactId } : {}),
        subject: input.subject.trim(), date: input.date, type: input.type, status: 'Planned' as const, owner,
        objective: input.objective.trim(), outcome: '', nextAction: '', actionOwner: '', due: '', actionDone: false,
      }
      localVisits.unshift(visit)
      salesRepository.save()
      return response(visit)
    },

    async reviewVisit(id: string, expectedModified?: string) {
      await wait()
      assertCapability(capabilities, 'visit:review')
      const index = localVisits.findIndex((item) => item.id === id)
      if (index < 0) throw new CrmApiError('VISIT_NOT_FOUND', '\u672a\u627e\u5230\u8be5\u62dc\u8bbf\u8bb0\u5f55', requestId(), false)
      const visit = localVisits[index]
      assertAccountScope(visit.accountId)
      if (expectedModified && visit.modified && expectedModified !== visit.modified) {
        throw new CrmApiError('VERSION_CONFLICT', '\u62dc\u8bbf\u8bb0\u5f55\u5df2\u88ab\u5176\u4ed6\u7528\u6237\u4fee\u6539', requestId(), false)
      }
      const record = meetingRecords.get(id)
      const complete = record && [record.purpose, record.attendees, record.agenda, record.summary, record.conclusion, record.followup].every((value) => value.trim())
      if (visit.status !== 'Minutes Submitted' || !complete) {
        throw new CrmApiError('INVALID_TRANSITION', '\u8bf7\u5148\u63d0\u4ea4\u5b8c\u6574\u7684\u62dc\u8bbf\u8bb0\u5f55', requestId(), false)
      }
      localVisits[index] = { ...visit, status: 'Manager Reviewed', modified: shanghaiTimestamp() }
      salesRepository.save()
      return response(localVisits[index])
    },

    async updateVisit(id: string, input: UpdateVisitInput, expectedModified?: string) {
      await wait()
      assertCapability(capabilities, 'visit:write')
      const index = localVisits.findIndex((item) => item.id === id)
      if (index < 0) throw new CrmApiError('VISIT_NOT_FOUND', '未找到该拜访记录', requestId(), false)
      const visit = localVisits[index]
      if (!canAccessVisit(visit)) throw new CrmApiError('SCOPE_DENIED', '该拜访不在当前用户范围内', requestId(), false)
      assertAccountScope(visit.accountId)
      assertCanChangeVisit(visit)
      if (!isVisitEditable(visit)) throw new CrmApiError('INVALID_TRANSITION', '经理已审核的拜访不能再编辑', requestId(), false)
      if (expectedModified && visit.modified && expectedModified !== visit.modified) {
        throw new CrmApiError('VERSION_CONFLICT', '拜访记录已被其他用户修改', requestId(), false)
      }
      try { validateCreateVisit({ ...input, accountId: visit.accountId }) } catch (error) {
        throw new CrmApiError('VALIDATION_ERROR', error instanceof Error ? error.message : '拜访信息不完整', requestId(), false)
      }
      // Only a changed owner is re-validated: the backend lets any active Sales user stay owner.
      const owner = input.owner === visit.owner ? visit.owner : validateOwner(input.owner, ['Sales'])
      localVisits[index] = {
        ...visit, subject: input.subject.trim(), date: input.date, type: input.type, owner,
        objective: input.objective.trim(), modified: shanghaiTimestamp(),
      }
      salesRepository.save()
      return response(localVisits[index])
    },

    async submitVisitRecord(id: string, file: MultipartFilePart) {
      await wait()
      assertCapability(capabilities, 'visit:write')
      const visit = scoped(localVisits, canAccessVisit).find((item) => item.id === id)
      if (visit && !isVisitEditable(visit)) throw new CrmApiError('INVALID_TRANSITION', '\u5df2\u5ba1\u6838\u7684\u62dc\u8bbf\u8bb0\u5f55\u4e0d\u80fd\u518d\u4fee\u6539', requestId(), false)
      if (!visit) throw new CrmApiError('VISIT_NOT_FOUND', '未找到该拜访记录', requestId(), false)
      assertCanChangeVisit(visit)
      if (!file.fileName.trim() || !file.blob.size || file.blob.size > CONTACT_FILE_MAX_SIZE || /\.(exe|dll|bat|cmd|ps1|js|msi)$/i.test(file.fileName)) {
        throw new CrmApiError('VALIDATION_ERROR', '文件为空、过大或属于禁止上传的可执行文件', requestId(), false)
      }
      const fileId = `VIS-FILE-${Date.now().toString(36)}`
      meetingFiles.set(fileId, { blob: file.blob, fileName: file.fileName, mimeType: file.mimeType, uploadedAt: shanghaiTimestamp(), uploadedBy: userId, visitId: id })
      const parseable = /\.(txt|csv)$/i.test(file.fileName)
      let parsed: Record<string, string> = {}
      if (parseable) {
        const text = await file.blob.text()
        const aliases: Record<string, string> = { 'meeting time': 'meetingTime', 'meeting purpose': 'purpose', attendees: 'attendees', agenda: 'agenda', summary: 'summary', summay: 'summary', conclusion: 'conclusion', followup: 'followup', 'follow-up': 'followup' }
        let active = ''
        for (const raw of text.split(/\r?\n/)) {
          const line = raw.trim()
          const match = line.match(/^([^:,\t]+)[:,\t]\s*(.*)$/)
          const key = match ? aliases[match[1].trim().toLowerCase()] : ''
          if (key) { active = key; parsed[key] = match?.[2].trim() ?? '' }
          else if (active && line) parsed[active] = [parsed[active], line].filter(Boolean).join('\n')
        }
      }
      const complete = ['purpose', 'attendees', 'agenda', 'summary', 'conclusion', 'followup'].every((key) => parsed[key]?.trim())
      const meetingTime = parsed.meetingTime ?? ''
      meetingRecords.set(id, {
        id: `VIS-MTG-${id}`, visitId: id, meetingStart: meetingTime, meetingEnd: '', purpose: parsed.purpose ?? '', attendees: parsed.attendees ?? '',
        agenda: parsed.agenda ?? '', summary: parsed.summary ?? '', conclusion: parsed.conclusion ?? '', followup: parsed.followup ?? '',
        parseStatus: complete ? 'Parsed' : parseable ? 'NeedsManualReview' : 'ArchiveOnly',
        parseMessage: complete ? '会议记录解析成功' : parseable ? '部分字段未识别，请检查并补录' : '文件已归档，此格式需手动补录',
        parsedAt: shanghaiTimestamp(), manuallyCorrected: false, modified: shanghaiTimestamp(),
      })
      // Mirrors the backend: a complete record submits the visit for Manager review.
      if (complete && (visit.status === 'Planned' || visit.status === 'Visited')) visit.status = 'Minutes Submitted'
      visit.modified = shanghaiTimestamp()
      salesRepository.save()
      return this.getVisitDetail(id)
    },

    async updateVisitMeetingRecord(id: string, input: VisitMeetingRecordInput) {
      await wait()
      assertCapability(capabilities, 'visit:write')
      const visit = scoped(localVisits, canAccessVisit).find((item) => item.id === id)
      if (visit && !isVisitEditable(visit)) throw new CrmApiError('INVALID_TRANSITION', '\u5df2\u5ba1\u6838\u7684\u62dc\u8bbf\u8bb0\u5f55\u4e0d\u80fd\u518d\u4fee\u6539', requestId(), false)
      if (!visit) throw new CrmApiError('VISIT_NOT_FOUND', '未找到该拜访记录', requestId(), false)
      assertCanChangeVisit(visit)
      const now = shanghaiTimestamp()
      const record: VisitMeetingRecordDto = {
        id: meetingRecords.get(id)?.id ?? `VIS-MTG-${id}`, visitId: id,
        meetingStart: input.meetingStart ?? '', meetingEnd: input.meetingEnd ?? '', purpose: input.purpose.trim(), attendees: input.attendees.trim(),
        agenda: input.agenda.trim(), summary: input.summary.trim(), conclusion: input.conclusion.trim(), followup: input.followup.trim(),
        parseStatus: 'Parsed', parseMessage: '会议记录已人工确认', parsedAt: meetingRecords.get(id)?.parsedAt ?? now,
        manuallyCorrected: true, modified: now,
      }
      meetingRecords.set(id, record)
      const complete = [record.purpose, record.attendees, record.agenda, record.summary, record.conclusion, record.followup]
        .every((value) => value.trim())
      if (complete && (visit.status === 'Planned' || visit.status === 'Visited')) visit.status = 'Minutes Submitted'
      visit.modified = now
      salesRepository.save()
      return response(record)
    },

    async getVisitAttachment(fileId: string) {
      await wait()
      assertCapability(capabilities, 'visit:view')
      const file = meetingFiles.get(fileId)
      if (!file || !scoped(localVisits, canAccessVisit).some((item) => item.id === file.visitId)) throw new CrmApiError('NOT_FOUND', '未找到附件', requestId(), false)
      return { blob: file.blob, fileName: file.fileName, mimeType: file.mimeType }
    },


    listContacts: listContactsInternal,
    getContact: getContactInternal,
    createContact: saveContactInternal,
    updateContact: (id: string, input: UpdateContactInput) => saveContactInternal(input, id),
    mergeContacts: mergeContactsInternal,
    deleteContact: deleteContactInternal,
    listContactFiles: listContactFilesInternal,
    uploadContactFiles: uploadContactFilesInternal,
    getContactFile: getContactFileInternal,
    deleteContactFile: deleteContactFileInternal,

    async listLeads(query: LeadListQuery) {
      await wait()
      assertCapability(capabilities, 'deal:view')
      const page = query.page ?? 1
      const pageSize = query.pageSize ?? 20
      const filtered = localLeads.filter((lead) =>
        canAccessLead(lead) &&
        (!query.search || includes(`${lead.name} ${lead.company} ${lead.title} ${lead.phone ?? ''} ${lead.email ?? ''} ${lead.interest}`, query.search)) &&
        (!query.status || query.status === 'All' || lead.status === query.status) &&
        (!query.source || query.source === 'All' || lead.source === query.source) &&
        (!query.owner || query.owner === 'All' || lead.owner === query.owner),
      )
      const start = (page - 1) * pageSize
      const result = response({ items: filtered.slice(start, start + pageSize) })
      result.meta = { ...result.meta!, page, pageSize, total: filtered.length }
      return result
    },

    async getLead(id: string) {
      await wait()
      assertCapability(capabilities, 'deal:view')
      return response(assertLead(id))
    },

    async createLead(input: CreateLeadInput) {
      return saveLeadInternal(input)
    },

    async updateLead(id: string, input: UpdateLeadInput) {
      return saveLeadInternal(input, id)
    },

    // The archive is a server rule with no behaviour here; tests stub these (AGENTS.md).
    async archiveLead(id: string) {
      await wait()
      throw new CrmApiError('INVALID_TRANSITION', `The mock API does not archive Leads (${id}).`, requestId(), false)
    },

    async unarchiveLead(id: string) {
      await wait()
      throw new CrmApiError('INVALID_TRANSITION', `The mock API does not archive Leads (${id}).`, requestId(), false)
    },

    async convertLead(id: string, input: LeadConversionInput) {
      await wait()
      assertCapability(capabilities, 'deal:write')
      const lead = assertLead(id)
      if (lead.status === 'Converted') {
        if (!lead.convertedAccountId || !lead.convertedContactId || !lead.convertedOpportunityId) {
          throw new CrmApiError('LEAD_CONVERSION_INCOMPLETE', 'Lead 转换记录不完整，请联系管理员', requestId(), false)
        }
        const existingResult: LeadConversionResult = {
          lead,
          accountId: lead.convertedAccountId,
          contactId: lead.convertedContactId,
          opportunityId: lead.convertedOpportunityId,
          reusedAccount: lead.convertedReusedAccount ?? false,
          reusedContact: lead.convertedReusedContact ?? false,
        }
        return response(existingResult)
      }
      if (input.qualificationConfirmed !== true) {
        throw new CrmApiError('VALIDATION_ERROR', 'Confirm the customer need and the budget owner before creating the Opportunity.', requestId(), false, { qualificationConfirmed: 'Required' })
      }
      const conversionLevel = input.opportunityProbabilityLevel ?? ''
      if (!isOpportunityProbabilityLevelValue(conversionLevel)) {
        throw new CrmApiError('VALIDATION_ERROR', 'opportunityProbabilityLevel is invalid.', requestId(), false, { opportunityProbabilityLevel: 'Invalid value' })
      }
      if (!conversionLevel) {
        throw new CrmApiError('VALIDATION_ERROR', 'opportunityProbabilityLevel is required.', requestId(), false, { opportunityProbabilityLevel: 'Required' })
      }
      let validOpportunityAmount = true
      try { normalizeMoney(input.opportunityAmount) } catch { validOpportunityAmount = false }
      if ([input.opportunityTitle, input.opportunityCloseDate, input.opportunityOwner, input.toolType].some((value) => !String(value ?? '').trim()) ||
        !validOpportunityAmount) {
        throw new CrmApiError('VALIDATION_ERROR', '请完整填写 Opportunity 名称、金额、预计成交日期、负责人和产品', requestId(), false)
      }
      const opportunityAmountCny = requiredPositiveMoney(input.opportunityAmountCny, 'opportunityAmountCny')
      const opportunityOwner = validateOwner(input.opportunityOwner, ['Sales', 'Manager'])
      const toolType = equipmentTypeFor(input.toolType)

      let account = input.accountId
        ? localAccounts.find((item) => item.id === input.accountId)
        : localAccounts.find((item) => item.name.trim().toLocaleLowerCase() === lead.company.trim().toLocaleLowerCase())
      const reusedAccount = Boolean(account)
      if (input.accountId && !account) throw new CrmApiError('ACCOUNT_NOT_FOUND', '未找到所选客户', requestId(), false)
      if (account) assertAccountScope(account.id)
      if (!account) {
        const draft = input.newAccount
        const accountOwner = validateOwner(draft?.owner?.trim() || lead.owner, ['Sales'], true)
        account = {
          id: nextId('ACC', localAccounts),
          name: draft?.name.trim() || lead.company,
          shortName: draft?.shortName.trim() || lead.company.replace(/[（(].*$/, '').slice(0, 12),
          segment: draft?.segment ?? 'Frontend',
          tier: draft?.tier ?? 'B',
          city: draft?.city.trim() || '待补充',
          region: draft?.region.trim() ? accountRegion(draft.region) : '',
          owner: accountOwner,
          pipelineAmount: 0,
          intentScore: 50,
          stakeholderCount: 0,
          siteCount: 1,
          requirementCount: 0,
          completeness: 45,
          risk: '关注',
          nextAction: lead.nextAction || '补齐客户档案',
          nextActionDue: lead.nextActionDue || today,
          updatedAt: '刚刚',
        }
        localAccounts.unshift(account)
        if (account.region) localAccountRegions.add(account.region)
        const siteDraft = input.newSite
        localSites[account.id] = [{
          id: `${account.id}-SITE-01`,
          name: siteDraft?.name.trim() || `${account.shortName} Main Site`,
          city: siteDraft?.city.trim() || account.city,
          type: siteDraft?.type.trim() || 'Fab',
          process: siteDraft?.process.trim() || '待确认',
          status: siteDraft?.status ?? '规划中',
        }]
      }
      const site = input.siteId
        ? (localSites[account.id] ?? []).find((item) => item.id === input.siteId)
        : (localSites[account.id] ?? [])[0]
      if (!site) throw new CrmApiError('SITE_NOT_FOUND', '所选客户没有可用厂区', requestId(), false)

      let contact = input.contactId
        ? localContacts.find((item) => item.id === input.contactId)
        : localContacts.find((item) =>
            item.accountId === account!.id &&
            item.status === 'Active' &&
            ((lead.email && item.email?.toLocaleLowerCase() === lead.email.toLocaleLowerCase()) || item.name === lead.name),
          )
      const reusedContact = Boolean(contact)
      if (input.contactId) contact = assertActiveContactForAccount(input.contactId, account.id)
      if (!contact) {
        const contactDraft = input.newContact
        contact = {
          id: nextId('CON', localContacts),
          accountId: account.id,
          siteId: site.id,
          name: contactDraft?.name.trim() || lead.name,
          title: contactDraft?.title.trim() || lead.title || '待补充',
          department: contactDraft?.department.trim() || '待补充',
          phone: contactDraft?.phone?.trim() || lead.phone,
          email: contactDraft?.email?.trim() || lead.email,
          relationship: contactDraft?.relationship ?? 'Developing',
          owner: validateOwner(contactDraft?.owner?.trim() || lead.owner, ['Sales'], true),
          status: contactDraft?.status ?? 'Active',
          dataQuality: (contactDraft?.email || lead.email) && (contactDraft?.title || lead.title) ? 'Complete' : 'Needs Review',
          updatedAt: today,
        }
        localContacts.unshift(contact)
      }

      const opportunity: StrategyOpportunityDto = {
        id: nextId('OPP', localStrategyOpportunities),
        sourceLeadId: lead.id,
        accountId: account.id,
        siteId: site.id,
        title: input.opportunityTitle.trim(),
        account: account.name,
        site: site.name,
        owner: opportunityOwner,
        stage: 'qualified_opportunity',
        stageChangedAt: '',
        budgetApprovedOn: '',
        lostAtStage: '',
        lostAt: '',
        lostBy: '',
        stageHistory: [],
        internalValidation: null,
        liveBooking: null,
        amount: normalizeMoney(input.opportunityAmount),
        probabilityLevel: conversionLevel,
        probabilityHistory: [probabilityHistoryEntry('', conversionLevel)],
        poDate: input.opportunityCloseDate,
        updated: '刚刚',
        score: 20,
        toolType,
        saleType: 'New Equipment',
        subRegion: account.region,
        currency: 'CNY',
        originalAmount: normalizeMoney(input.opportunityAmount),
        amountCny: opportunityAmountCny,
        shipmentDate: '',
        fatDate: '',
        paymentMilestones: [],
        competition: '',
        winReason: '',
        lostReason: '',
        history: [{ at: historyAt, actor: userId, field: 'Lead Conversion', from: lead.id, to: input.opportunityTitle.trim() }],
        strengths: [],
        redFlags: [],
        informationNeeded: [],
        stakeholders: [{
          id: `STK-${nextId('OPP', localStrategyOpportunities)}-1`,
          contactId: contact.id,
          name: contact.name,
          title: contact.title,
          role: 'Primary Contact',
          influence: 'High',
          stance: 'Support',
          coverage: 'Lead conversion',
        }],
        actions: [],
      }
      const conversion = stageHistoryRow('', 'qualified_opportunity', { source: 'creation', event: 'lead_converted', referenceDoctype: 'Lead', referenceName: lead.id })
      opportunity.stageHistory.push(conversion)
      opportunity.stageChangedAt = conversion.recordedAt
      touchOpportunity(opportunity)
      localStrategyOpportunities.unshift(opportunity)
      localEquipmentTypes.add(toolType)
      Object.assign(lead, {
        status: 'Converted',
        convertedAt: now,
        convertedAccountId: account.id,
        convertedContactId: contact.id,
        convertedOpportunityId: opportunity.id,
        convertedReusedAccount: reusedAccount,
        convertedReusedContact: reusedContact,
        updatedAt: today,
      } satisfies Partial<LeadDto>)
      salesRepository.save()
      return response({
        lead,
        accountId: account.id,
        contactId: contact.id,
        opportunityId: opportunity.id,
        reusedAccount,
        reusedContact,
      })
    },

    listStakeholders: listContactsInternal,
    createStakeholder: (input: CreateStakeholderInput) => saveContactInternal(mapLegacyStakeholderInput(input)),
    updateStakeholder: (id: string, input: UpdateStakeholderInput) => saveContactInternal(mapLegacyStakeholderInput(input), id),

    async listRequirements(query: ListQuery) {
      await wait()
      assertCapability(capabilities, 'requirement:view')
      const page = query.page ?? 1
      const pageSize = query.pageSize ?? 20
      const filtered = scoped(requirements, canAccessRequirement).filter((item) =>
        (!query.search || includes(`${item.accountName} ${item.title} ${item.equipment}`, query.search)) &&
        (!query.accountId || query.accountId === 'All' || item.accountId === query.accountId) &&
        (!query.status || query.status === 'All' || item.status === query.status),
      )
      const start = (page - 1) * pageSize
      const result = response({ items: filtered.slice(start, start + pageSize) })
      result.meta = { ...result.meta!, page, pageSize, total: filtered.length }
      return result
    },

    async listPipeline(query: ListQuery) {
      await wait()
      assertCapability(capabilities, 'deal:view')
      const filteredOpps = scoped(currentPipelineOpportunities(), canAccessOpportunity).filter((item) =>
        (!query.search || includes(`${item.accountName} ${item.title}`, query.search)) &&
        (!query.accountId || query.accountId === 'All' || item.accountId === query.accountId) &&
        (!query.contactId || localStrategyOpportunities.find((opportunity) => opportunity.id === item.id)?.stakeholders.some((person) => person.contactId === query.contactId)) &&
        (!query.owner || query.owner === 'All' || item.owner === query.owner) &&
        (!query.status || query.status === 'All' || item.stage === query.status),
      )
      const filteredBookings = scoped(localBookings, canAccessBooking).filter((item) =>
        (!query.search || includes(`${item.accountName} ${item.title} ${item.equipment}`, query.search)) &&
        (!query.accountId || query.accountId === 'All' || item.accountId === query.accountId) &&
        (!query.contactId || item.primaryContactId === query.contactId) &&
        (!query.owner || query.owner === 'All' || item.owner === query.owner) &&
        (!query.source || query.source === 'All' || item.source === query.source) &&
        (!query.status || query.status === 'All' || item.status === query.status) &&
        (!query.dateFrom || item.ddl >= query.dateFrom) &&
        (!query.dateTo || item.ddl <= query.dateTo),
      ).map(expandBookingContact)
      const open = filteredOpps.filter((item) => isOpenOpportunityStage(item.stage))
      const currencies = [...new Set([...filteredOpps, ...filteredBookings].map((item) => item.currency))].sort()
      return response({
        opportunities: filteredOpps,
        bookings: filteredBookings,
        totals: currencies.map((currency) => {
          const currencyOpen = open.filter((item) => item.currency === currency)
          const currencyBookings = filteredBookings.filter((item) => item.currency === currency && item.status === 'Confirmed')
          return {
            currency,
            openPipeline: addMoney(currencyOpen.map((item) => item.amount)),
            confirmedBooking: addMoney(currencyBookings.map((item) => item.amount)),
          }
        }),
      })
    },

    async listBookings(query: ListQuery) {
      await wait()
      assertCapability(capabilities, 'deal:view')
      const filtered = scoped(localBookings, canAccessBooking).filter((item) =>
        (!query.search || includes(`${item.accountName} ${item.title} ${item.equipment}`, query.search)) &&
        (!query.accountId || query.accountId === 'All' || item.accountId === query.accountId) &&
        (!query.contactId || item.primaryContactId === query.contactId) &&
        (!query.status || query.status === 'All' || item.status === query.status) &&
        (!query.owner || query.owner === 'All' || item.owner === query.owner) &&
        (!query.source || query.source === 'All' || item.source === query.source) &&
        (!query.dateFrom || item.ddl >= query.dateFrom) &&
        (!query.dateTo || item.ddl <= query.dateTo) &&
        (!query.actualPoDateMissing || (!item.actualPoDate && (item.status === 'Confirmed' || item.status === 'Completed'))),
      ).map(expandBookingContact)
      return pageResponse(filtered, query)
    },

    async createBooking(input: UpsertBookingInput) {
      await wait()
      assertCapability(capabilities, 'deal:write')
      if (String(input.source ?? '').trim() === 'Opportunity') {
        throw new CrmApiError('BOOKING_SOURCE_INVALID', 'Opportunity Bookings are created by confirming the PO or approving an internal validation.', requestId(), false)
      }
      assertAccountScope(input.accountId)
      const account = localAccounts.find((item) => item.id === input.accountId)
      const contact = assertActiveContactForAccount(input.primaryContactId, input.accountId)
      if (!account) throw new CrmApiError('ACCOUNT_NOT_FOUND', '未找到该客户', requestId(), false)
      try { normalizeMoney(input.amount) }
      catch { throw new CrmApiError('VALIDATION_ERROR', '金额必须为 DECIMAL(20,2) 字符串', requestId(), false) }
      if (!input.equipment.trim() || !input.ddl || !input.owner.trim() || input.quantity < 1 || !input.currency.trim()) {
        throw new CrmApiError('VALIDATION_ERROR', '请完整填写设备需求、数量、DDL、金额与负责人', requestId(), false)
      }
      const owner = validateOwner(input.owner, ['Sales'])
      if (input.status === 'Completed') throw new CrmApiError('BOOKING_STATUS_INVALID', 'Completed 只能由转入 Installed Tool 自动生成', requestId(), false)
      validateBookingSource(input)
      const actualPoDate = validateActualPoDate(input.actualPoDate, false)
      const booking = {
        id: nextId('BKG', localBookings),
        accountId: account.id,
        accountName: account.name,
        title: `${input.equipment.trim()} · ${input.quantity} 台`,
        primaryContactId: contact.id,
        customerContact: contact.name,
        equipment: input.equipment.trim(),
        quantity: Number(input.quantity),
        ddl: input.ddl,
        amount: normalizeMoney(input.amount),
        currency: input.currency.trim().toUpperCase(),
        amountCny: bookingAmountCny(input.currency.trim().toUpperCase(), normalizeMoney(input.amount), input.amountCny, input.status === 'Confirmed'),
        amountCnyNote: '',
        status: input.status,
        bookingDate: today,
        owner,
        source: input.source,
        bookingType: input.source === 'Opportunity'
          ? (localStrategyOpportunities.find((item) => item.id === input.sourceOpportunityId)?.saleType === 'Service' ? 'Service' : 'Equipment')
          : input.bookingType ?? 'Equipment',
        sourceOpportunityId: input.sourceOpportunityId,
        note: input.note.trim(),
        actualPoDate,
        actualPoDateSource: actualPoDate ? 'booking_entry' as const : '' as const,
        actualPoDateNote: '',
      }
      localBookings.unshift(booking)
      salesRepository.save()
      return response(booking)
    },

    async updateBooking(id: string, input: UpsertBookingInput, expectedModified?: string) {
      await wait()
      assertCapability(capabilities, 'deal:write')
      const index = localBookings.findIndex((item) => item.id === id)
      if (index < 0) throw new CrmApiError('BOOKING_NOT_FOUND', '未找到该 Booking', requestId(), false)
      if (localBookings[index].installedToolId || localBookings[index].status === 'Completed') {
        throw new CrmApiError('BOOKING_LOCKED', '已转入 Installed Tool 的 Booking 不能再编辑', requestId(), false)
      }
      assertAccountScope(localBookings[index].accountId)
      // Mirrors update_booking: Opportunity Bookings only come from PO confirmation or internal validation.
      if (String(input.source ?? '').trim() !== localBookings[index].source) {
        throw new CrmApiError('BOOKING_SOURCE_INVALID', "A Booking's source cannot change.", requestId(), false)
      }
      assertOpportunityBookingEdit(localBookings[index], input)
      assertAccountScope(input.accountId)
      const account = localAccounts.find((item) => item.id === input.accountId)
      const contact = assertActiveContactForAccount(input.primaryContactId, input.accountId)
      if (!account) throw new CrmApiError('ACCOUNT_NOT_FOUND', '未找到该客户', requestId(), false)
      try { normalizeMoney(input.amount) }
      catch { throw new CrmApiError('VALIDATION_ERROR', '金额必须为 DECIMAL(20,2) 字符串', requestId(), false) }
      if (!input.equipment.trim() || !input.ddl || !input.owner.trim() || input.quantity < 1 || !input.currency.trim()) {
        throw new CrmApiError('VALIDATION_ERROR', '请完整填写设备需求、数量、DDL、金额与负责人', requestId(), false)
      }
      const owner = validateOwner(input.owner, ['Sales'])
      if (input.status === 'Completed') throw new CrmApiError('BOOKING_STATUS_INVALID', 'Completed 只能由转入 Installed Tool 自动生成', requestId(), false)
      validateBookingSource(input, id)
      // Mirrors bookings._edited_actual_po_date: an edit may only give an Upsell Booking its first date.
      const current = localBookings[index]
      const requestedPoDate = input.actualPoDate === undefined ? current.actualPoDate ?? '' : String(input.actualPoDate ?? '').trim()
      let poDate = { actualPoDate: current.actualPoDate ?? '', actualPoDateSource: current.actualPoDateSource ?? '', actualPoDateNote: current.actualPoDateNote ?? '' }
      if (requestedPoDate !== (current.actualPoDate ?? '')) {
        if (current.source === 'Opportunity' || current.actualPoDate) {
          throw new CrmApiError('VALIDATION_ERROR', "The actual PO date changes only through a Manager's correction.", requestId(), false, { actualPoDate: 'Manager correction only' })
        }
        poDate = { ...poDate, actualPoDate: validateActualPoDate(requestedPoDate, true), actualPoDateSource: 'booking_entry' }
      }
      // Mirrors update_booking: a stored CNY amount carries over unless the edit sends a new one.
      let requestedAmountCny = input.amountCny === undefined ? (current.currency === 'CNY' ? '' : current.amountCny ?? '') : input.amountCny
      // Mirrors bookings._assert_amount_cny_edit: once recorded, the CNY amount of an order changes only through a Manager's correction.
      const recordedAmountCny = current.currency === 'CNY' ? '' : current.amountCny ?? ''
      if (current.status !== 'Pending' && input.currency.trim().toUpperCase() !== 'CNY' && recordedAmountCny) {
        if (String(requestedAmountCny ?? '').trim() === '') requestedAmountCny = recordedAmountCny
        else if (requiredPositiveMoney(requestedAmountCny, 'amountCny') !== normalizeMoney(recordedAmountCny)) throw new CrmApiError('VALIDATION_ERROR', "The CNY amount changes only through a Manager's correction.", requestId(), false, { amountCny: 'Manager correction only' })
      }
      const amountCny = bookingAmountCny(input.currency.trim().toUpperCase(), normalizeMoney(input.amount), requestedAmountCny, input.status === 'Confirmed')
      localBookings[index] = {
        ...localBookings[index],
        ...clone(input),
        ...poDate,
        amountCny,
        // A correction's reason describes a CNY amount; it goes when the order turns into CNY.
        amountCnyNote: input.currency.trim().toUpperCase() !== 'CNY' && amountCny && amountCny === normalizeMoney(recordedAmountCny || '0') ? current.amountCnyNote ?? '' : '',
        bookingType: input.source === 'Opportunity'
          ? (localStrategyOpportunities.find((item) => item.id === input.sourceOpportunityId)?.saleType === 'Service' ? 'Service' : 'Equipment')
          : input.bookingType ?? 'Equipment',
        accountId: account.id,
        accountName: account.name,
        title: `${input.equipment.trim()} · ${input.quantity} 台`,
        equipment: input.equipment.trim(),
        primaryContactId: contact.id,
        customerContact: contact.name,
        amount: normalizeMoney(input.amount),
        currency: input.currency.trim().toUpperCase(),
        owner,
        note: input.note.trim(),
      }
      salesRepository.save()
      return response(localBookings[index])
    },

    // Server reads and rules with no behaviour here; tests stub these (AGENTS.md).
    async getBooking(id: string) {
      await wait()
      throw new CrmApiError('BOOKING_NOT_FOUND', `The mock API does not read a Booking by id (${id}).`, requestId(), false)
    },

    async archiveBooking(id: string) {
      await wait()
      throw new CrmApiError('INVALID_TRANSITION', `The mock API does not archive Bookings (${id}).`, requestId(), false)
    },

    async unarchiveBooking(id: string) {
      await wait()
      throw new CrmApiError('INVALID_TRANSITION', `The mock API does not archive Bookings (${id}).`, requestId(), false)
    },

    async convertBookingToInstalledTool(id: string, input: ConvertBookingToInstalledToolInput, expectedModified?: string) {
      await wait()
      assertCapability(capabilities, 'deal:write')
      const booking = localBookings.find((item) => item.id === id)
      if (!booking) throw new CrmApiError('BOOKING_NOT_FOUND', '未找到该 Booking', requestId(), false)
      assertAccountScope(booking.accountId)
      if (expectedModified !== undefined) {
        if (booking.modified && expectedModified !== booking.modified) throw new CrmApiError('VERSION_CONFLICT', 'Booking 已被其他请求修改', requestId(), false)
        booking.modified = expectedModified
      }
      if (booking.installedToolId || booking.status === 'Completed') {
        throw new CrmApiError('BOOKING_ALREADY_CONVERTED', '该 Booking 已转入 Installed Tool', requestId(), false)
      }
      if (booking.status !== 'Confirmed') {
        throw new CrmApiError('BOOKING_NOT_CONFIRMED', '只有 Confirmed Booking 可以转入 Installed Tool', requestId(), false)
      }
      if (booking.bookingType !== 'Equipment') {
        throw new CrmApiError('BOOKING_TYPE_INVALID', 'Service Booking 不能转入 Installed Tool', requestId(), false)
      }
      const site = (localSites[booking.accountId] ?? []).find((item) => item.id === input.siteId)
      if (!site) throw new CrmApiError('SITE_ACCOUNT_MISMATCH', '所选厂区不属于该 Booking 客户', requestId(), false)
      const engineerOwner = validateOwner(input.engineerOwner, ['Engineer'])
      const model = input.model.trim()
      if (!model) throw new CrmApiError('VALIDATION_ERROR', '请填写设备型号', requestId(), false)
      const fallback = (value?: string) => value?.trim() || '待确认'
      const installedToolId = nextId('TOOL', localInstalledTools)
      const installedTool: InstalledToolDto = {
        id: installedToolId,
        accountId: booking.accountId,
        siteId: site.id,
        serial: `CRM-SN-${installedToolId.split('-').at(-1)!.padStart(5, '0')}`,
        model,
        account: booking.accountName,
        site: site.name,
        location: fallback(input.location),
        status: 'Delivery Preparation',
        software: fallback(input.software),
        firmware: fallback(input.firmware),
        warrantyEnd: '待确认',
        completeness: 55,
        sourceBookingId: booking.id,
        sourceOpportunityId: booking.sourceOpportunityId,
        salesOwner: booking.owner,
        engineerOwner,
        salesOrder: fallback(input.salesOrder),
        contract: fallback(input.contract),
        warrantyStart: '待确认',
        serviceContract: '待确认',
        pmCycle: '待确认',
        lastService: '尚未开始',
        operatingSystem: '待确认',
        configuration: fallback(input.configuration),
        ownershipType: 'Customer Owned',
        milestones: [
          { label: 'FAT', date: '待确认', state: 'Current' },
          { label: 'Shipment', date: '待确认', state: 'Waiting' },
          { label: 'Installation', date: '待确认', state: 'Waiting' },
          { label: 'SAT', date: '待确认', state: 'Waiting' },
          { label: 'Warranty', date: '待确认', state: 'Waiting' },
        ],
        documents: [],
      }
      localInstalledTools.unshift(installedTool)
      booking.status = 'Completed'
      booking.installedToolId = installedTool.id
      booking.installedToolConvertedAt = now
      booking.modified = `${now}#${requestId()}`
      salesRepository.save()
      return response({ booking, installedTool })
    },

    async setBookingActualPoDate(id: string, input: SetActualPoDateInput, expectedModified?: string) {
      await wait()
      assertCapability(capabilities, 'deal:write')
      if (role !== 'Manager') throw new CrmApiError('PERMISSION_DENIED', 'Only a Manager can fill in or correct the actual PO date.', requestId(), false)
      const booking = localBookings.find((item) => item.id === id)
      if (!booking) throw new CrmApiError('BOOKING_NOT_FOUND', '未找到该 Booking', requestId(), false)
      assertAccountScope(booking.accountId)
      if (expectedModified && booking.modified && expectedModified !== booking.modified) {
        throw new CrmApiError('VERSION_CONFLICT', 'Booking 已被其他请求修改', requestId(), false)
      }
      if (booking.status !== 'Confirmed' && booking.status !== 'Completed') {
        throw new CrmApiError('BOOKING_STATUS_INVALID', 'Only a Confirmed or Completed Booking has an actual PO date.', requestId(), false)
      }
      const actualPoDate = validateActualPoDate(input?.actualPoDate, true)
      const previous = booking.actualPoDate ?? ''
      if (actualPoDate === previous) throw new CrmApiError('VALIDATION_ERROR', 'actualPoDate is unchanged.', requestId(), false, { actualPoDate: 'Unchanged' })
      const reason = String(input?.reason ?? '').trim()
      if (previous && !reason) throw new CrmApiError('VALIDATION_ERROR', 'A reason is required to correct the actual PO date.', requestId(), false, { reason: 'Required' })
      Object.assign(booking, { actualPoDate, actualPoDateSource: 'backfill', actualPoDateNote: reason, modified: `${now}#${requestId()}` })
      const opportunity = localStrategyOpportunities.find((item) => item.id === booking.sourceOpportunityId)
      if (opportunity) appendOpportunityHistory(opportunity, 'bookingPoDate', previous, actualPoDate)
      salesRepository.save()
      return response(booking)
    },

    async setBookingAmountCny(id: string, input: SetBookingAmountCnyInput, expectedModified?: string) {
      await wait()
      assertCapability(capabilities, 'deal:write')
      if (role !== 'Manager') throw new CrmApiError('PERMISSION_DENIED', 'Only a Manager can fill in or correct the CNY amount.', requestId(), false)
      const booking = localBookings.find((item) => item.id === id)
      if (!booking) throw new CrmApiError('BOOKING_NOT_FOUND', '未找到该 Booking', requestId(), false)
      assertAccountScope(booking.accountId)
      if (expectedModified && booking.modified && expectedModified !== booking.modified) {
        throw new CrmApiError('VERSION_CONFLICT', 'Booking 已被其他请求修改', requestId(), false)
      }
      if (booking.status !== 'Confirmed' && booking.status !== 'Completed') {
        throw new CrmApiError('BOOKING_STATUS_INVALID', 'Only a Confirmed or Completed Booking has a CNY amount to record.', requestId(), false)
      }
      if (booking.currency === 'CNY') throw new CrmApiError('VALIDATION_ERROR', 'A CNY Booking uses its amount.', requestId(), false, { amountCny: 'CNY Booking' })
      const amountCny = requiredPositiveMoney(input?.amountCny, 'amountCny')
      const previous = booking.amountCny ?? ''
      if (previous && normalizeMoney(previous) === amountCny) throw new CrmApiError('VALIDATION_ERROR', 'amountCny is unchanged.', requestId(), false, { amountCny: 'Unchanged' })
      const reason = String(input?.reason ?? '').trim()
      if (previous && !reason) throw new CrmApiError('VALIDATION_ERROR', 'A reason is required to correct the CNY amount.', requestId(), false, { reason: 'Required' })
      Object.assign(booking, { amountCny, amountCnyNote: reason, modified: `${now}#${requestId()}` })
      const opportunity = localStrategyOpportunities.find((item) => item.id === booking.sourceOpportunityId)
      if (opportunity) appendOpportunityHistory(opportunity, 'bookingAmountCny', previous, amountCny)
      salesRepository.save()
      return response(booking)
    },

    async completeServiceBooking(id: string, expectedModified?: string) {
      await wait()
      assertCapability(capabilities, 'deal:write')
      const booking = localBookings.find((item) => item.id === id)
      if (!booking) throw new CrmApiError('BOOKING_NOT_FOUND', '未找到该 Booking', requestId(), false)
      assertAccountScope(booking.accountId)
      if (expectedModified !== undefined) {
        if (booking.modified && expectedModified !== booking.modified) throw new CrmApiError('VERSION_CONFLICT', 'Booking 已被其他请求修改', requestId(), false)
        booking.modified = expectedModified
      }
      if (booking.bookingType !== 'Service') throw new CrmApiError('BOOKING_TYPE_INVALID', '只有 Service Booking 可以执行服务完成', requestId(), false)
      if (booking.installedToolId || booking.status === 'Completed') throw new CrmApiError('BOOKING_ALREADY_COMPLETED', '该 Booking 已完成', requestId(), false)
      if (booking.status !== 'Confirmed') throw new CrmApiError('BOOKING_NOT_CONFIRMED', '只有 Confirmed Service Booking 可以完成', requestId(), false)
      booking.status = 'Completed'
      booking.modified = `${now}#${requestId()}`
      salesRepository.save()
      return response(booking)
    },

    async listDemoRequests(query: ListQuery) {
      await ensureDemoPrimaryContacts()
      await wait()
      assertCapability(capabilities, 'demo_request:view')
      const snapshot = await repository.read()
      const filtered = snapshot.demoRequests.filter((item) =>
        canAccessDemo(item) &&
        (!query.search || includes(`${item.accountName} ${item.title} ${item.requestedEquipment}`, query.search)) &&
        (!query.accountId || query.accountId === 'All' || item.accountId === query.accountId) &&
        (!query.owner || query.owner === 'All' || item.salesOwner === query.owner) &&
        (!query.contactId || item.primaryContactId === query.contactId) &&
        (!query.status || query.status === 'All' || item.status === query.status),
      ).map(expandDemoContact)
      const result = response({ items: filtered })
      result.meta = { ...result.meta!, page: 1, pageSize: filtered.length, total: filtered.length }
      return result
    },

    async createDemoRequest(input: CreateDemoRequestInput) {
      await ensureDemoPrimaryContacts()
      await wait()
      return repository.transact((snapshot) => {
      assertCapability(capabilities, 'demo_request:create')
      const requestMode = input.requestMode ?? 'Opportunity'
      const accountId = input.accountId ?? ''
      if (requestMode === 'Opportunity') assertAccountScope(accountId)
      const account = localAccounts.find((item) => item.id === accountId)
      const contact = input.primaryContactId
        ? assertActiveContactForAccount(input.primaryContactId, accountId)
        : undefined
      if (requestMode === 'Opportunity' && !account) throw new CrmApiError('ACCOUNT_NOT_FOUND', '未找到申请客户', requestId(), false)
      if (requestMode === 'Opportunity' && !contact) throw new CrmApiError('VALIDATION_ERROR', '请选择主要联系人', requestId(), false, { primaryContactId: '请选择主要联系人' })
      if (input.requirementId && !requirements.some((item) => item.id === input.requirementId && item.accountId === input.accountId)) throw new CrmApiError('LINK_MISMATCH', '关联需求与客户不一致', requestId(), false)
       if (requestMode === 'Opportunity' && !(input.opportunityId ?? '').trim()) throw new CrmApiError('VALIDATION_ERROR', '请选择关联 Opportunity', requestId(), false, { opportunityId: '请选择关联 Opportunity' })
       const linkedOpportunity = requestMode === 'Opportunity'
         ? localStrategyOpportunities.find((item) => item.id === input.opportunityId && item.accountId === input.accountId)
         : undefined
       if (requestMode === 'Opportunity' && !linkedOpportunity) throw new CrmApiError('LINK_MISMATCH', '关联商机与客户不一致', requestId(), false)
       if (linkedOpportunity && !canCreateDemoRequestAt(linkedOpportunity.stage)) throw new CrmApiError('INVALID_TRANSITION', 'Demo Request can only be created for an Opportunity in qualified_opportunity or demo_done.', requestId(), false)
       if (requestMode === 'Opportunity' && snapshot.demoRequests.some((item) => item.opportunityId === input.opportunityId && !['Cancelled', 'Converted'].includes(item.status))) {
         throw new CrmApiError('CONFLICT', '该 Opportunity 已有活动中的 Demo Request', requestId(), false)
       }
      const formData = { ...clone(input.formData), contactPerson: contact ? formatContactDisplayLine(contact) : input.formData.contactPerson.trim() }
      validateOwner(formData.salesContact, ['Sales'])
      validateOwner(formData.demoOwner, ['Engineer'])
      const formErrors = validateDemoRequestFormData(formData, { requireCustomerInformation: requestMode !== 'Self Test' })
      const firstError = Object.values(formErrors)[0]
      if (firstError) throw new CrmApiError('VALIDATION_ERROR', firstError, requestId(), false)
      const accountName = account?.name ?? 'Self Test'
      const summary = deriveDemoRequestSummary(accountName, formData)
      const id = nextId('DR', snapshot.demoRequests)
      const request: DemoRequestDto = {
        id, accountId, accountName, primaryContactId: contact?.id ?? '', requirementId: input.requirementId,
        opportunityId: requestMode === 'Opportunity' ? input.opportunityId : undefined, requestMode,
        segment: account?.segment ?? '', salesOwner: formData.salesContact.trim(), createdBy: userId, ...summary,
        customerExpectedDate: input.customerExpectedDate,
        status: input.submit ? 'Engineer Review' : 'Draft', engineerOwner: formData.demoOwner.trim(), feasibility: '',
        testPlan: '', assignedEquipment: '', resourceWindow: '', estimatedCompletionDate: '', technicalRisk: '', engineerComment: '', managerDecision: '', managerComment: '',
        tracking: {
          lastProgressAt: now,
          lastProgressSummary: input.submit ? '创建并提交 FAE Review' : '创建 Demo Request 草稿',
          lastProgressActor: userId,
          nextAction: '',
          nextActionOwner: '',
          nextActionDue: '',
        },
        formData, preparedBy: userId, preparedDate: today, createdAt: now, updatedAt: now, history: [],
      }
      validateDemoRequest(request)
      addRequestHistory(request, '', request.status, userId, input.submit ? '创建并提交 FAE Review' : '创建 Demo Request 草稿')
       snapshot.demoRequests.unshift(request)
       return response(request)
      })
    },

    async importDemoRequestForm(file: MultipartFilePart) {
      await wait()
      if (!/\.(pdf|docx)$/i.test(file.fileName) || file.size <= 0 || file.blob.size <= 0) {
        throw new CrmApiError('VALIDATION_ERROR', '仅支持不超过 100 MiB 的 PDF 或 DOCX 文件', requestId(), false)
      }
      throw new CrmApiError('BACKEND_NOT_CONNECTED', 'DRF 自动识别需要连接 Frappe 后端', requestId(), false)
    },

    async updateDemoRequest(id: string, input: CreateDemoRequestInput, expectedModified?: string) {
      await ensureDemoPrimaryContacts()
      await wait()
      return repository.transact((snapshot) => {
      assertCapability(capabilities, 'demo_request:create')
      const request = snapshot.demoRequests.find((item) => item.id === id)
      if (!request) throw new CrmApiError('DEMO_REQUEST_NOT_FOUND', '未找到 Demo Request', requestId(), false)
      assertDemoScope(request)
      const accountId = input.accountId ?? ''
      if (request.requestMode === 'Opportunity') assertAccountScope(accountId)
      if (!['Draft', 'Engineer Returned', 'Manager Rejected'].includes(request.status)) throw new CrmApiError('INVALID_TRANSITION', '当前状态不能修改申请', requestId(), false)
      const account = localAccounts.find((item) => item.id === accountId)
      const contact = input.primaryContactId
        ? assertActiveContactForAccount(input.primaryContactId, accountId)
        : undefined
      if (request.requestMode === 'Opportunity' && !account) throw new CrmApiError('ACCOUNT_NOT_FOUND', '未找到申请客户', requestId(), false)
      const requirementId = input.requirementId ?? request.requirementId
       const requestMode = request.requestMode ?? 'Opportunity'
       const opportunityId = request.opportunityId
       if (requestMode === 'Opportunity' && !contact) throw new CrmApiError('VALIDATION_ERROR', '请选择主要联系人', requestId(), false, { primaryContactId: '请选择主要联系人' })
       if (input.requestMode !== requestMode || input.opportunityId !== opportunityId) throw new CrmApiError('VALIDATION_ERROR', 'Demo Request 类型和关联 Opportunity 不能修改', requestId(), false)
      if (requirementId && !requirements.some((item) => item.id === requirementId && item.accountId === input.accountId)) throw new CrmApiError('LINK_MISMATCH', '关联需求与客户不一致', requestId(), false)
      if (opportunityId && !localStrategyOpportunities.some((item) => item.id === opportunityId && item.accountId === input.accountId)) throw new CrmApiError('LINK_MISMATCH', '关联商机与客户不一致', requestId(), false)
      const from = request.status
      const formData = { ...clone(input.formData), contactPerson: contact ? formatContactDisplayLine(contact) : input.formData.contactPerson.trim() }
      validateOwner(formData.salesContact, ['Sales'])
      validateOwner(formData.demoOwner, ['Engineer'])
      const formErrors = validateDemoRequestFormData(formData, { requireCustomerInformation: requestMode !== 'Self Test' })
      const firstError = Object.values(formErrors)[0]
      if (firstError) throw new CrmApiError('VALIDATION_ERROR', firstError, requestId(), false)
      const accountName = account?.name ?? 'Self Test'
      const summary = deriveDemoRequestSummary(accountName, formData)
      const next: DemoRequestDto = {
        ...request,
        accountId,
        accountName,
        primaryContactId: contact?.id ?? '',
        requirementId,
        opportunityId,
        segment: account?.segment ?? '',
        salesOwner: formData.salesContact.trim(),
        engineerOwner: formData.demoOwner.trim(),
        ...summary,
        formData,
        customerExpectedDate: input.customerExpectedDate,
        preparedBy: userId,
        preparedDate: today,
        status: input.submit ? 'Engineer Review' : from,
        feasibility: input.submit ? 'Pending' : request.feasibility,
        managerDecision: input.submit ? '' : request.managerDecision,
        managerComment: input.submit ? '' : request.managerComment,
      }
      validateDemoRequest(next)
      Object.assign(request, next)
      addRequestHistory(request, from, request.status, userId, input.submit ? '更新申请并重新提交 FAE Review' : '更新申请内容')
      return response(request)
      })
    },

    async transitionDemoRequest(id: string, command: DemoRequestCommand) {
      await wait()
      return repository.transact((snapshot) => {
      if ((command.type === 'manager_reject' || command.type === 'manager_approve') && role !== 'Manager') {
        throw new CrmApiError('PERMISSION_DENIED', '只有 Boss 或 Demo 管理员可以执行审批', requestId(), false)
      }
      if (command.type === 'engineer_return' || command.type === 'engineer_approve') assertCapability(capabilities, 'demo_request:engineering_review')
      else if (command.type === 'manager_reject' || command.type === 'manager_approve') assertCapability(capabilities, 'demo_request:manager_approve')
      else assertCapability(capabilities, 'demo_request:create')
      const request = snapshot.demoRequests.find((item) => item.id === id)
      if (!request) throw new CrmApiError('DEMO_REQUEST_NOT_FOUND', '未找到 Demo Request', requestId(), false)
      assertDemoScope(request)
      if (command.type === 'manager_approve' && request.evaluationId) throw new CrmApiError('EVALUATION_EXISTS', '该申请已经生成 Evaluation', requestId(), false)
      const from = request.status
      let evaluation

      if (command.type === 'submit') {
        if (!['Draft', 'Engineer Returned', 'Manager Rejected'].includes(from)) throw new CrmApiError('INVALID_TRANSITION', '当前状态不能提交 FAE Review', requestId(), false)
        validateDemoRequest(request)
        request.status = 'Engineer Review'
        addRequestHistory(request, from, request.status, userId, 'Sales 提交 FAE Review')
      } else if (command.type === 'cancel') {
        if (!['Draft', 'Engineer Returned', 'Manager Rejected'].includes(from)) throw new CrmApiError('INVALID_TRANSITION', '当前状态不能取消', requestId(), false)
        request.status = 'Cancelled'
        addRequestHistory(request, from, request.status, userId, command.comment || 'Sales 取消申请')
      } else if (command.type === 'engineer_return') {
        if (from !== 'Engineer Review') throw new CrmApiError('INVALID_TRANSITION', '只有待 FAE Review 申请可以退回', requestId(), false)
        if (!command.comment.trim()) throw new CrmApiError('VALIDATION_ERROR', '退回原因不能为空', requestId(), false)
        request.status = 'Engineer Returned'; request.feasibility = 'Need More Info'; request.engineerComment = command.comment.trim()
        addRequestHistory(request, from, request.status, userId, `FAE Review：${command.comment.trim()}`)
      } else if (command.type === 'engineer_approve') {
        if (from !== 'Engineer Review') throw new CrmApiError('INVALID_TRANSITION', '只有待 FAE Review 申请可以确认', requestId(), false)
        const required = [command.engineerOwner, command.testPlan, command.assignedEquipment, command.resourceWindow, command.estimatedCompletionDate, command.technicalRisk, command.comment]
        if (required.some((value) => !value.trim())) throw new CrmApiError('VALIDATION_ERROR', 'FAE Review 字段必须完整', requestId(), false)
        const nextEngineer = command.engineerOwner.trim()
        validateOwner(nextEngineer, ['Engineer'])
        if (role === 'Engineer' && nextEngineer !== request.engineerOwner) {
          throw new CrmApiError('PERMISSION_DENIED', '工程师不能自行转派 Demo 负责人', requestId(), false)
        }
        const ownerChange = request.engineerOwner === nextEngineer
          ? ''
          : `；Engineer ${request.engineerOwner} → ${nextEngineer}`
        Object.assign(request, { status: 'Manager Approval' as const, feasibility: 'Feasible' as const, engineerOwner: nextEngineer, testPlan: command.testPlan.trim(), assignedEquipment: command.assignedEquipment.trim(), resourceWindow: command.resourceWindow.trim(), estimatedCompletionDate: command.estimatedCompletionDate, technicalRisk: command.technicalRisk.trim(), engineerComment: command.comment.trim(), managerDecision: 'Pending' as const })
        addRequestHistory(request, from, request.status, userId, `FAE Review：${command.comment.trim()}${ownerChange}`)
      } else if (command.type === 'manager_reject') {
        if (from !== 'Manager Approval') throw new CrmApiError('INVALID_TRANSITION', '只有待经理审批申请可以驳回', requestId(), false)
        if (!command.comment.trim()) throw new CrmApiError('VALIDATION_ERROR', '驳回原因不能为空', requestId(), false)
        request.status = 'Manager Rejected'; request.managerDecision = 'Rejected'; request.managerComment = command.comment.trim()
        addRequestHistory(request, from, request.status, userId, command.comment.trim())
      } else {
        if (from !== 'Manager Approval') throw new CrmApiError('INVALID_TRANSITION', '只有待经理审批申请可以批准', requestId(), false)
        evaluation = {
          id: nextId('EVAL', snapshot.evaluations), accountId: request.accountId, accountName: request.accountName, requirementId: request.requirementId, demoRequestId: request.id,
          segment: request.segment, title: request.title, status: 'Requested' as const, owner: request.engineerOwner, plannedEnd: request.estimatedCompletionDate || request.targetDate,
          testRunDeadline: '', wafers: 0, acceptance: 'Pending' as const,
          waferPreparationStatus: 'Pending' as const, testPreparationStatus: 'Pending' as const,
          reportStatus: 'Not Ready' as const, reportVersion: 0, testRound: 1,
          criteria: request.acceptanceCriteria, runs: [],
        }
        touchEvaluation(evaluation)
         snapshot.evaluations.unshift(evaluation)
         request.status = 'Converted'; request.managerDecision = 'Approved'; request.managerComment = command.comment.trim(); request.evaluationId = evaluation.id
        request.approvedBy = userId; request.approvedDate = today
        addRequestHistory(request, from, request.status, userId, `批准并生成 Demo ${evaluation.id}${request.managerComment ? `：${request.managerComment}` : ''}`)
      }
      return response({ request, evaluation })
      })
    },

    async listEvaluations(query: ListQuery) {
      await wait()
      assertCapability(capabilities, 'evaluation:view')
      const snapshot = await repository.read()
      const filtered = snapshot.evaluations.filter((item) =>
        canAccessEvaluation(snapshot.demoRequests, item) &&
        (!query.search || includes(`${item.accountName} ${item.title} ${item.owner}`, query.search)) &&
        (!query.accountId || query.accountId === 'All' || item.accountId === query.accountId) &&
        (!query.status || query.status === 'All' || item.status === query.status),
      )
      const result = response({ items: filtered })
      result.meta = { ...result.meta!, page: 1, pageSize: filtered.length, total: filtered.length }
      return result
    },

    async getEvaluation(id: string) {
      await wait()
      assertCapability(capabilities, 'evaluation:view')
      const snapshot = await repository.read()
      const evaluation = snapshot.evaluations.find((item) => item.id === id)
      if (!evaluation) throw new CrmApiError('EVALUATION_NOT_FOUND', '未找到 Evaluation', requestId(), false)
      assertEvaluationScope(snapshot.demoRequests, evaluation)
      return response(evaluation)
    },

    async completeEvaluationPreparation(id: string, branch: EvaluationPreparationBranch, _expectedModified: string) {
      await wait()
      return repository.transact((snapshot) => {
        assertCapability(capabilities, 'evaluation:write')
        const evaluation = snapshot.evaluations.find((item) => item.id === id)
        if (!evaluation) throw new CrmApiError('EVALUATION_NOT_FOUND', '未找到 Evaluation', requestId(), false)
        assertEvaluationScope(snapshot.demoRequests, evaluation)
        if (!['Requested', 'Scope Confirmed', 'Sample Received', 'Scheduled'].includes(evaluation.status)) {
          throw new CrmApiError('INVALID_TRANSITION', '当前阶段不能更新准备状态', requestId(), false)
        }
        if (evaluationPreparationStatus(evaluation, branch) === 'Completed') return response(evaluation)
        if (branch === 'wafer') {
          evaluation.waferPreparationStatus = 'Completed'
          evaluation.waferPreparationCompletedBy = userId
          evaluation.waferPreparationCompletedAt = now
        } else {
          evaluation.testPreparationStatus = 'Completed'
          evaluation.testPreparationCompletedBy = userId
          evaluation.testPreparationCompletedAt = now
        }
        if (isEvaluationPreparationComplete(evaluation)) evaluation.status = 'Scheduled'
        touchEvaluation(evaluation)
        markProgress(snapshot.demoRequests.find((item) => item.id === evaluation.demoRequestId), `Completed ${branch} preparation`)
        return response(evaluation)
      })
    },

    async updateEvaluationStatus(id: string, command: EvaluationStatusCommand, expectedModified?: string) {
      await wait()
      return repository.transact((snapshot) => {
      assertCapability(capabilities, 'evaluation:write')
      const evaluation = snapshot.evaluations.find((item) => item.id === id)
      if (!evaluation) throw new CrmApiError('EVALUATION_NOT_FOUND', '未找到 Evaluation', requestId(), false)
      assertEvaluationScope(snapshot.demoRequests, evaluation)
      if (!canTransitionEvaluation(evaluation.status, command.status)) throw new CrmApiError('INVALID_TRANSITION', `不能从 ${evaluation.status} 转为 ${command.status}`, requestId(), false)
      if (evaluation.status === 'Testing' && command.status === 'Internal Review') {
        // Same order and meaning as the backend gate: the run check names the round,
        // because earlier rounds' completed runs stay visible but no longer count.
        if (!hasCompletedTestRun(evaluation)) {
          throw new CrmApiError('INVALID_TRANSITION', `请先完成第 ${evaluation.testRound} 轮 Test Run，之前轮次的 Test Run 不计入。`, requestId(), false)
        }
        if (!snapshot.artifacts.some((item) => item.id === evaluation.internalReportArtifactId && item.type === 'Test Report')
          || !snapshot.artifacts.some((item) => item.id === evaluation.externalReportArtifactId && item.type === 'Test Report')) {
          throw new CrmApiError('INVALID_TRANSITION', '请先上传 Internal 和 External Test Report。', requestId(), false)
        }
      }
      if (command.status === 'Customer Review') {
        if (evaluation.reportStatus !== 'Ready') {
          throw new CrmApiError('REPORT_NOT_READY', '请先上传 Internal 和 External Test Report', requestId(), false)
        }
      }
      if (command.status === evaluation.status) return response(evaluation)
      // Customer Review is a record-keeping step: both of its exits (archive and retest)
      // must leave a comment behind, tagged with the round it was given for.
      const leavingCustomerReview = evaluation.status === 'Customer Review'
      const customerComment = leavingCustomerReview ? command.customerComment?.trim() ?? '' : ''
      if (leavingCustomerReview && !customerComment) {
        throw new CrmApiError('VALIDATION_ERROR', '请填写 Customer Comment。', requestId(), false)
      }
      const isRetest = leavingCustomerReview && command.status === 'Testing'
      // Reaching Customer Review completes the demo milestone; a retest that comes back here is a no-op.
      if (command.status === 'Customer Review') {
        const request = snapshot.demoRequests.find((item) => item.id === evaluation.demoRequestId)
        if (request?.opportunityId) {
          advanceOpportunityForEvent(request.opportunityId, 'demo_customer_review', { referenceDoctype: 'CRM Evaluation', referenceName: evaluation.id })
        }
      }
      const previousStatus = evaluation.status
      const commentedRound = evaluation.testRound
      const previousDeadline = evaluation.testRunDeadline
      if (customerComment) {
        evaluation.customerReviews = [...(evaluation.customerReviews ?? []), {
          id: `${evaluation.id}-CR-${(evaluation.customerReviews?.length ?? 0) + 1}`,
          round: commentedRound,
          comment: customerComment,
          author: userId,
          createdAt: shanghaiTimestamp(),
        }]
      }
      if (isRetest) {
        // A retest opens a fresh round. Previous artifacts are never touched — the round
        // stamp is what keeps them apart — but the report gate has to close again so the
        // new round cannot advance on the previous round's reports.
        evaluation.testRound = commentedRound + 1
        // The previous round's DDL is history too: kept, it would flag the new round
        // as overdue and keep the deadline reminders firing.
        evaluation.testRunDeadline = ''
        evaluation.reportStatus = 'Not Ready'
        evaluation.reportArtifactId = undefined
        evaluation.reportArtifact = undefined
        evaluation.internalReportArtifactId = undefined
        evaluation.internalReportArtifact = undefined
        evaluation.externalReportArtifactId = undefined
        evaluation.externalReportArtifact = undefined
        evaluation.customerReportArtifactId = undefined
        evaluation.customerReportArtifact = undefined
      }
      evaluation.status = command.status
      evaluation.acceptance = command.status === 'Accepted' || command.status === 'Rejected' ? command.status : 'Pending'
      if (isRetest && previousDeadline) {
        // Mirror set_evaluation_test_run_deadline: a deadline change always leaves a
        // Deadline row, so the cleared round DDL stays traceable in the history.
        evaluation.history = [{
          id: `${evaluation.id}-H-${(evaluation.history?.length ?? 0) + 1}`,
          actor: userId,
          at: shanghaiTimestamp(),
          eventType: 'Deadline',
          from: previousDeadline,
          to: '',
          summary: `Cleared round ${commentedRound} Test Run deadline for retest`,
        }, ...(evaluation.history ?? [])]
      }
      evaluation.history = [{
        id: `${evaluation.id}-H-${(evaluation.history?.length ?? 0) + 1}`,
        actor: userId,
        at: shanghaiTimestamp(),
        eventType: 'Status',
        from: previousStatus,
        to: command.status,
        summary: isRetest
          ? `Demo Test retest requested, round ${evaluation.testRound}: ${customerComment}`
          : command.status === 'Accepted' && customerComment
            ? `Demo Test archived with customer comment: ${customerComment}`
            : `Demo Test moved to ${command.status}`,
      }, ...(evaluation.history ?? [])]
      touchEvaluation(evaluation)
      markProgress(
        snapshot.demoRequests.find((item) => item.id === evaluation.demoRequestId),
        isRetest ? `Demo Test 第 ${evaluation.testRound} 轮重测` : `Demo Test 推进至 ${command.status}`,
      )
      return response(evaluation)
      })
    },

    async addEvaluationRun(id: string, input: CreateTestRunInput & { expectedModified?: string }) {
      await wait()
      return repository.transact((snapshot) => {
      assertCapability(capabilities, 'evaluation:write')
      const evaluation = snapshot.evaluations.find((item) => item.id === id)
      if (!evaluation) throw new CrmApiError('EVALUATION_NOT_FOUND', '未找到 Evaluation', requestId(), false)
      assertEvaluationScope(snapshot.demoRequests, evaluation)
      if (input.expectedModified !== undefined && input.expectedModified !== evaluation.modified) {
        throw new CrmApiError('VERSION_CONFLICT', 'Evaluation 已被其他请求修改', requestId(), false)
      }
      assertReportWritable(evaluation)
      if (!['Scheduled', 'Testing'].includes(evaluation.status)) {
        throw new CrmApiError('INVALID_RUN_STAGE', '只有 Test Execution 阶段可以录入 Test Run', requestId(), false)
      }
      const completeMetrics = validateTestRun(input)
      const nextRunNumber = Math.max(0, ...evaluation.runs.map((run) => Number(run.id.match(/-R(\d+)$/)?.[1] ?? 0))) + 1
      const runId = `${evaluation.id}-R${String(nextRunNumber).padStart(2, '0')}`
      const { expectedModified: _expected, ...fields } = input
      evaluation.runs.push({ ...fields, id: runId, round: evaluation.testRound, summary: input.summary.trim(), status: completeMetrics ? 'Completed' : 'Planned' })
      evaluation.wafers = activeRunWafers(evaluation)
      appendTestRunHistory(evaluation, `${completeMetrics ? 'Completed' : 'Planned'} Test Run ${runId}`, '', runId)
      touchEvaluation(evaluation)
      const request = snapshot.demoRequests.find((item) => item.id === evaluation.demoRequestId)
      if (request) markProgress(request, `${completeMetrics ? '完成' : '创建'} Test Run ${runId}`)
      return response(evaluation)
      })
    },

    async updateEvaluationRun() {
      throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Test Run edits require the Frappe API.', requestId(), false)
    },

    async cancelEvaluationRun() {
      throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Test Run cancellation requires the Frappe API.', requestId(), false)
    },

    async terminateEvaluation() {
      throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Demo Test termination requires the Frappe API.', requestId(), false)
    },
    async setEvaluationTestRunDeadline(id: string, input: { testRunDeadline: string; expectedModified?: string }) {
      await wait()
      return repository.transact((snapshot) => {
        assertCapability(capabilities, 'evaluation:write')
        const evaluation = snapshot.evaluations.find((item) => item.id === id)
        if (!evaluation) throw new CrmApiError('EVALUATION_NOT_FOUND', '未找到 Evaluation', requestId(), false)
        assertEvaluationScope(snapshot.demoRequests, evaluation)
        if (input.expectedModified !== undefined && input.expectedModified !== evaluation.modified) {
          throw new CrmApiError('VERSION_CONFLICT', 'Evaluation 已被其他请求修改', requestId(), false)
        }
        const request = snapshot.demoRequests.find((item) => item.id === evaluation.demoRequestId)
        if (!request) throw new CrmApiError('DEMO_REQUEST_NOT_FOUND', '未找到关联 Demo Request', requestId(), false)
        const testRunDeadline = input.testRunDeadline.trim()
        if (!isIsoDate(testRunDeadline) || testRunDeadline < today) {
          throw new CrmApiError('VALIDATION_ERROR', 'Test Run DDL 不能早于今天', requestId(), false)
        }
        evaluation.testRunDeadline = testRunDeadline
        touchEvaluation(evaluation)
        markProgress(request, `更新 Test Run DDL 为 ${testRunDeadline}`)
        const warnings = isIsoDate(request.customerExpectedDate) && testRunDeadline > request.customerExpectedDate
          ? ['Test Run DDL 晚于客户预期时间，请 Sales 与客户沟通']
          : []
        return response(evaluation, warnings)
      })
    },

    async saveDemoArtifact(input: DemoArtifactUploadInput) {
      await wait()
      return repository.transact((snapshot) => {
        assertCapability(capabilities, 'demo_request:create')
        const request = snapshot.demoRequests.find((item) => item.id === input.demoRequestId)
        if (!request) throw new CrmApiError('DEMO_REQUEST_NOT_FOUND', '未找到 Demo Request', requestId(), false)
        assertDemoScope(request)
        if (input.evaluationId) {
          const evaluation = snapshot.evaluations.find((item) => item.id === input.evaluationId)
          if (!evaluation || evaluation.demoRequestId !== request.id) {
            throw new CrmApiError('LINK_MISMATCH', 'Artifact 关联的 Request 与 Evaluation 不一致', requestId(), false)
          }
        }
        const version = Math.max(0, ...snapshot.artifacts
          .filter((item) => item.demoRequestId === input.demoRequestId && item.evaluationId === input.evaluationId && item.type === input.type)
          .map((item) => item.version)) + 1
        const artifact: StoredDemoArtifact = {
          demoRequestId: input.demoRequestId,
          evaluationId: input.evaluationId,
          type: input.type,
          visibility: input.visibility,
          fileName: input.file.fileName.trim(),
          mimeType: input.file.mimeType || 'application/octet-stream',
          blob: input.file.blob,
          id: nextId('ART', snapshot.artifacts),
          version,
          createdBy: userId,
          createdAt: now,
        }
        snapshot.artifacts.push(artifact)
        const { blob: _blob, ...meta } = artifact
        return response(meta)
      })
    },

    async getDemoArtifact(id: string) {
      await wait()
      assertAnyCapability(capabilities, ['demo_request:view', 'evaluation:view'])
      const snapshot = await repository.read()
      const artifact = snapshot.artifacts.find((item) => item.id === id)
      if (!artifact) throw new CrmApiError('DEMO_ARTIFACT_NOT_FOUND', '未找到 Demo Artifact', requestId(), false)
      const request = snapshot.demoRequests.find((item) => item.id === artifact.demoRequestId)
      const evaluation = artifact.evaluationId ? snapshot.evaluations.find((item) => item.id === artifact.evaluationId) : undefined
      if (!request && !evaluation) throw new CrmApiError('DEMO_REQUEST_NOT_FOUND', '未找到 Artifact 关联记录', requestId(), false)
      if (request) assertDemoScope(request)
      else assertEvaluationScope(snapshot.demoRequests, evaluation!)
      if (!request || !canReadDemoArtifact(request, evaluation, artifact, true)) {
        throw new CrmApiError('PERMISSION_DENIED', '当前角色无权读取该 Demo Artifact', requestId(), false)
      }
      return { blob: artifact.blob, fileName: artifact.fileName, mimeType: artifact.mimeType }
    },

    async releaseDemoTestReport(id, input) {
      await wait()
      return repository.transact((snapshot) => {
        assertCapability(capabilities, 'evaluation:write')
        const evaluation = snapshot.evaluations.find((item) => item.id === id)
        if (!evaluation) throw new CrmApiError('EVALUATION_NOT_FOUND', '未找到 Evaluation', requestId(), false)
        assertEvaluationScope(snapshot.demoRequests, evaluation)
        const request = snapshot.demoRequests.find((item) => item.id === evaluation.demoRequestId)
        if (!request) throw new CrmApiError('DEMO_REQUEST_NOT_FOUND', '未找到关联 Demo Request', requestId(), false)
        const files = [input.internalFile, input.externalFile]
        if (files.some((file) => !file.fileName.trim() || file.blob.size === 0)) throw new CrmApiError('VALIDATION_ERROR', 'Internal 和 External 报告均不能为空', requestId(), false)
        if (files.some((file) => file.size > 100 * 1024 * 1024)) throw new CrmApiError('VALIDATION_ERROR', '报告文件不能超过 100 MiB', requestId(), false)
        if (evaluation.status !== 'Testing') {
          throw new CrmApiError('INVALID_REPORT_STAGE', '测试报告只能在 Testing 阶段上传', requestId(), false)
        }
        assertExpectedRound(evaluation, input.expectedRound)
        const version = Math.max(evaluation.reportVersion, ...snapshot.artifacts
          .filter((item) => item.evaluationId === evaluation.id && item.type === 'Test Report')
          .map((item) => item.version), 0) + 1
        const createReport = (file: MultipartFilePart, label: 'Internal' | 'External', visibility: 'Internal' | 'Customer Review'): StoredDemoArtifact => ({
          id: nextId('ART', snapshot.artifacts), demoRequestId: request.id, evaluationId: evaluation.id,
          type: 'Test Report', fileName: `[${label}] ${file.fileName.trim().replace(/^\[(?:External|Internal)\]\s+/i, '')}`,
          mimeType: file.mimeType || 'application/pdf', blob: file.blob, version, round: evaluation.testRound, createdBy: userId, createdAt: now, visibility,
        })
        const internal = createReport(input.internalFile, 'Internal', 'Internal')
        snapshot.artifacts.push(internal)
        const external = createReport(input.externalFile, 'External', 'Customer Review')
        snapshot.artifacts.push(external)
        const { blob: _internalBlob, ...internalReportArtifact } = internal
        const { blob: _externalBlob, ...externalReportArtifact } = external
        Object.assign(evaluation, {
          reportStatus: 'Ready' as const,
          reportArtifactId: internal.id,
          reportArtifact: internalReportArtifact,
          internalReportArtifactId: internal.id,
          internalReportArtifact,
          externalReportArtifactId: external.id,
          externalReportArtifact,
          reportVersion: version,
        })
        touchEvaluation(evaluation)
        markProgress(request, `上传第 ${evaluation.testRound} 轮 Test Report v${version}`)
        return response({ internalReportArtifact, externalReportArtifact, version })
      })
    },

    async uploadCustomerReport(id, input) {
      await wait()
      return repository.transact((snapshot) => {
        assertCapability(capabilities, 'evaluation:write')
        const evaluation = snapshot.evaluations.find((item) => item.id === id)
        if (!evaluation) throw new CrmApiError('EVALUATION_NOT_FOUND', '未找到 Evaluation', requestId(), false)
        assertEvaluationScope(snapshot.demoRequests, evaluation)
        const request = snapshot.demoRequests.find((item) => item.id === evaluation.demoRequestId)
        if (!request) throw new CrmApiError('DEMO_REQUEST_NOT_FOUND', '未找到关联 Demo Request', requestId(), false)
        const file = input.file
        if (!file.fileName.trim() || file.blob.size === 0) throw new CrmApiError('VALIDATION_ERROR', 'Customer 报告不能为空', requestId(), false)
        if (file.size > 100 * 1024 * 1024) throw new CrmApiError('VALIDATION_ERROR', '报告文件不能超过 100 MiB', requestId(), false)
        if (evaluation.status !== 'Customer Review') {
          throw new CrmApiError('INVALID_REPORT_STAGE', 'Customer 报告只能在 Customer Review 阶段上传', requestId(), false)
        }
        assertExpectedRound(evaluation, input.expectedRound)
        const version = Math.max(...snapshot.artifacts
          .filter((item) => item.evaluationId === evaluation.id && item.type === 'Customer Report')
          .map((item) => item.version), 0) + 1
        const artifact: StoredDemoArtifact = {
          id: nextId('ART', snapshot.artifacts), demoRequestId: request.id, evaluationId: evaluation.id,
          type: 'Customer Report', fileName: `[Customer] ${file.fileName.trim().replace(/^\[Customer\]\s+/i, '')}`,
          mimeType: file.mimeType || 'application/pdf', blob: file.blob, version, round: evaluation.testRound,
          createdBy: userId, createdAt: now, visibility: 'Customer Review',
        }
        snapshot.artifacts.push(artifact)
        const { blob: _blob, ...meta } = artifact
        evaluation.customerReportArtifactId = artifact.id
        evaluation.customerReportArtifact = meta
        touchEvaluation(evaluation)
        markProgress(request, `上传第 ${evaluation.testRound} 轮 Customer Report v${version}`)
        return response({ artifact: meta, round: evaluation.testRound, version })
      })
    },

    async listContracts(query: ListQuery) {
      await wait()
      assertCapability(capabilities, 'contract:view')
      const filtered = scoped(localContracts).filter((item) =>
        (!query.search || includes(`${item.accountName} ${item.id} ${item.type}`, query.search)) &&
        (!query.accountId || query.accountId === 'All' || item.accountId === query.accountId) &&
        (!query.status || query.status === 'All' || item.status === query.status) &&
        (!query.type || query.type === 'All' || item.type === query.type),
      )
      const result = response({ items: filtered })
      result.meta = { ...result.meta!, page: 1, pageSize: filtered.length, total: filtered.length }
      return result
    },

    async listQuotationCatalog() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Quotation 仅支持 Frappe 运行时', requestId(), false) },
    async listQuotations() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Quotation 仅支持 Frappe 运行时', requestId(), false) },
    async getQuotationPlanning() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Quotation planning requires Frappe', requestId(), false) },
    async listEvents() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Events require Frappe', requestId(), false) },
    async getEvent() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Events require Frappe', requestId(), false) },
    async saveEvent() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Events require Frappe', requestId(), false) },
    async saveQuotationSchedule() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Quotation planning requires Frappe', requestId(), false) },
    async saveQuotationFollowUp() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Quotation planning requires Frappe', requestId(), false) },
    async getQuotation() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Quotation 仅支持 Frappe 运行时', requestId(), false) },
    async createQuotation() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Quotation 仅支持 Frappe 运行时', requestId(), false) },
    async linkQuotationOpportunity() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Quotation 仅支持 Frappe 运行时', requestId(), false) },
    async saveQuotationDraft() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Quotation 仅支持 Frappe 运行时', requestId(), false) },
    async createQuotationVersion() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Quotation 仅支持 Frappe 运行时', requestId(), false) },
    async discardQuotationDraft() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Quotation 仅支持 Frappe 运行时', requestId(), false) },
    async publishQuotation() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Quotation 仅支持 Frappe 运行时', requestId(), false) },
    async submitQuotationForApproval() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Quotation 仅支持 Frappe 运行时', requestId(), false) },
    async reviewQuotationApproval() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Quotation 仅支持 Frappe 运行时', requestId(), false) },
    async recordQuotationDecision() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Quotation 仅支持 Frappe 运行时', requestId(), false) },
    async getQuotationPreviewPdf() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Quotation 仅支持 Frappe 运行时', requestId(), false) },
    async getQuotationPdf() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Quotation 仅支持 Frappe 运行时', requestId(), false) },

    async listStrategyOpportunities(query: StrategyOpportunityListQuery = {}) {
      await wait()
      assertCapability(capabilities, 'deal:view')
      const filtered = scoped(localStrategyOpportunities, canAccessOpportunity).filter((opportunity) =>
        (!query.search || includes(`${opportunity.account} ${opportunity.title} ${opportunity.site}`, query.search)) &&
        (!query.accountId || query.accountId === 'All' || opportunity.accountId === query.accountId) &&
        (!query.opportunityId || opportunity.id === query.opportunityId) &&
        (!query.contactId || opportunity.stakeholders.some((person) => person.contactId === query.contactId)) &&
        (!query.status || query.status === 'All' || opportunity.stage === query.status) &&
        matchesOpportunityProbabilityLevelFilter(opportunity.probabilityLevel, query.probabilityLevel) &&
        (!query.owner || query.owner === 'All' || opportunity.owner === query.owner),
      ).map((opportunity) => ({
        ...withDerivedOpportunityState(opportunity),
        stakeholders: opportunity.stakeholders.map((link) => expandOpportunityContact(link, localContacts)),
      }))
      return pageResponse(filtered, query)
    },

    async getStrategyOpportunity(id: string) {
      await wait()
      assertCapability(capabilities, 'deal:view')
      return opportunityResponse(assertOpportunity(id))
    },
    saveBlueSheetFlags: reviewUnavailable,
    getBlueSheetAssessment: reviewUnavailable,
    applyBlueSheetSuggestion: reviewUnavailable,

    async createStrategyOpportunity(input: CreateStrategyOpportunityInput) {
      await wait()
      assertCapability(capabilities, 'deal:write')
      if (input.qualificationConfirmed !== true) {
        throw new CrmApiError('VALIDATION_ERROR', 'Confirm the customer need and the budget owner before creating the Opportunity.', requestId(), false, { qualificationConfirmed: 'Required' })
      }
      assertAccountScope(input.accountId)
      const score = Math.round(Number(input.intentScore))
      const probabilityLevel = input.probabilityLevel ?? ''
      validateOpportunity({ ...input, score, probabilityLevel })
      // Retired clients may still send a stage; every new Opportunity starts at the first milestone.
      const requestedStage = (input as CreateStrategyOpportunityInput & { stage?: unknown }).stage || 'qualified_opportunity'
      if (requestedStage !== 'qualified_opportunity') {
        throw new CrmApiError('INVALID_TRANSITION', 'New Opportunity must start at qualified_opportunity.', requestId(), false)
      }
      if (!probabilityLevel) {
        throw new CrmApiError('VALIDATION_ERROR', 'probabilityLevel is required.', requestId(), false, { probabilityLevel: 'Required' })
      }
      const account = localAccounts.find((item) => item.id === input.accountId)
      const site = (localSites[input.accountId] ?? []).find((item) => item.id === input.siteId)
      if (!account) throw new CrmApiError('ACCOUNT_NOT_FOUND', '未找到该客户', requestId(), false)
      if (!site) throw new CrmApiError('SITE_NOT_FOUND', '所选厂区不属于该客户', requestId(), false)
      const toolType = equipmentTypeFor(input.toolType)
      const created = stageHistoryRow('', 'qualified_opportunity', { source: 'creation', event: 'created' })
      const opportunity: StrategyOpportunityDto = {
        id: nextId('OPP', localStrategyOpportunities), accountId: account.id, siteId: site.id, title: input.title.trim(),
        account: account.name, site: site.name, owner: input.owner.trim(), stage: 'qualified_opportunity',
        stageChangedAt: created.recordedAt, budgetApprovedOn: '', lostAtStage: '', lostAt: '', lostBy: '',
        stageHistory: [created], internalValidation: null, liveBooking: null,
        amount: normalizeMoney(input.amount), probabilityLevel, probabilityHistory: [], poDate: input.poDate, updated: '刚刚',
        score, toolType, saleType: input.saleType.trim(),
        subRegion: opportunityRegion(input.subRegion), currency: input.currency, originalAmount: normalizeMoney(input.originalAmount ?? input.amount),
        amountCny: normalizeMoney(String(input.amountCny).trim()),
        shipmentDate: input.shipmentDate ?? '', fatDate: input.fatDate ?? '', paymentMilestones: clone(input.paymentMilestones ?? []),
        competition: input.competition?.trim() ?? '', winReason: input.winReason?.trim() ?? '', lostReason: input.lostReason?.trim() ?? '',
        history: [{ at: historyAt, actor: userId, field: 'Opportunity', from: '', to: input.title.trim() }],
        strengths: clone(input.strengths ?? []), redFlags: clone(input.redFlags ?? []), informationNeeded: clone(input.informationNeeded ?? []),
        stakeholders: [], actions: [],
      }
      opportunity.probabilityHistory.push(probabilityHistoryEntry('', probabilityLevel))
      touchOpportunity(opportunity)
      localStrategyOpportunities.unshift(opportunity)
      localEquipmentTypes.add(toolType)
      salesRepository.save()
      return opportunityResponse(opportunity)
    },

    async updateStrategyOpportunity(id: string, input: UpdateStrategyOpportunityInput, expectedModified?: string) {
      await wait()
      assertCapability(capabilities, 'deal:write')
      const opportunity = assertOpportunity(id)
      if (expectedModified !== undefined) requireOpportunityVersion(opportunity, expectedModified)
      if (input.accountId) assertAccountScope(input.accountId)
      const previous = clone(opportunity)
      // Retired clients may still send the percentage or forecast, which are ignored, or a stage, which only workflow actions change.
      const {
        intentScore,
        probabilityLevel: requestedLevel,
        probabilityReason: requestedReason,
        probabilityActionPlan: requestedPlan,
        probability: _retiredProbability,
        forecast: _retiredForecast,
        stage: requestedStage,
        qualificationConfirmed: _qualificationConfirmed,
        ...changesInput
      } = clone(input) as UpdateStrategyOpportunityInput & { probability?: unknown; forecast?: unknown; stage?: unknown; qualificationConfirmed?: unknown }
      const score = Math.round(Number(intentScore ?? opportunity.score))
      const probabilityLevel = requestedLevel ?? opportunity.probabilityLevel
      if (changesInput.subRegion !== undefined) changesInput.subRegion = opportunityRegion(changesInput.subRegion)
      // An unchanged type keeps its stored spelling, even one from before the catalog.
      if (changesInput.toolType !== undefined) {
        const current = opportunity.toolType ?? ''
        changesInput.toolType = typeof changesInput.toolType === 'string' && current.trim() && changesInput.toolType.trim() === current.trim()
          ? current
          : equipmentTypeFor(changesInput.toolType)
      }
      const next = {
        ...opportunity,
        ...changesInput,
        score,
        probabilityLevel,
      }
      validateOpportunity(next)
      // Stored normalized, so re-entering the same CNY amount is not recorded as a change.
      if (changesInput.amountCny !== undefined) next.amountCny = changesInput.amountCny = normalizeMoney(String(changesInput.amountCny).trim())
      if (requestedStage !== undefined && requestedStage !== opportunity.stage) {
        throw new CrmApiError('INVALID_TRANSITION', 'Opportunity stages change only through their workflow actions.', requestId(), false)
      }
      if (opportunity.stage === 'lost' && !String(next.lostReason ?? '').trim()) {
        throw new CrmApiError('VALIDATION_ERROR', 'Lost Reason is required for a lost Opportunity.', requestId(), false, { lostReason: 'Required' })
      }
      const probabilityLevelChanged = probabilityLevel !== previous.probabilityLevel
      const lowered = probabilityLevelChanged && Boolean(previous.probabilityLevel)
        && opportunityProbabilityLevelRank(probabilityLevel) < opportunityProbabilityLevelRank(previous.probabilityLevel)
      let plan: string | null = null
      if (probabilityLevelChanged) {
        assertProbabilityLevelOwner(previous.owner)
        if (isClosedOpportunityStage(opportunity.stage)) {
          throw new CrmApiError('INVALID_TRANSITION', 'The probability level is frozen once the PO is received or the Opportunity is lost.', requestId(), false)
        }
        // Empty is only where an Opportunity from before the levels starts; once set, a level stays set.
        if (!probabilityLevel) {
          throw new CrmApiError('VALIDATION_ERROR', 'probabilityLevel cannot be cleared once it is set.', requestId(), false, { probabilityLevel: 'Required' })
        }
        if (opportunityProbabilityLevelRank(probabilityLevel) < opportunityProbabilityLevelRank(previous.probabilityLevel) && !String(requestedReason ?? '').trim()) {
          throw new CrmApiError('VALIDATION_ERROR', 'A reason is required to lower the probability level.', requestId(), false, { probabilityReason: 'Required' })
        }
        if (lowered) {
          requireOpportunityVersion(opportunity, expectedModified)
          plan = recoveryPlan(requestedPlan, 'probabilityActionPlan')
        }
      }
      if ((next.accountId !== previous.accountId || next.saleType !== previous.saleType) && liveOpportunityBooking(opportunity.id)) {
        throw new CrmApiError('CONFLICT', 'Account and sale type cannot change while the Opportunity has a live Booking.', requestId(), false)
      }
      const account = localAccounts.find((item) => item.id === next.accountId)
      const site = (localSites[next.accountId] ?? []).find((item) => item.id === next.siteId)
      if (!account) throw new CrmApiError('ACCOUNT_NOT_FOUND', '未找到该客户', requestId(), false)
      if (!site) throw new CrmApiError('SITE_NOT_FOUND', '所选厂区不属于该客户', requestId(), false)
      const changes = Object.entries({ ...changesInput, score })
        .filter(([key, value]) => JSON.stringify(previous[key as keyof StrategyOpportunityDto]) !== JSON.stringify(value))
      const stakeholders = next.accountId === previous.accountId
        ? opportunity.stakeholders
        : opportunity.stakeholders.filter((link) => localContacts.some((contact) =>
          contact.id === link.contactId && contact.accountId === next.accountId,
        ))
      Object.assign(opportunity, next, { account: account.name, site: site.name, stakeholders })
      if (opportunity.toolType) localEquipmentTypes.add(opportunity.toolType)
      touchOpportunity(opportunity)
      for (const [field, value] of changes.reverse()) {
        opportunity.history.unshift({ at: historyAt, actor: userId, field, from: String(previous[field as keyof StrategyOpportunityDto] ?? ''), to: String(value ?? '') })
      }
      if (probabilityLevelChanged) {
        const event = probabilityHistoryEntry(previous.probabilityLevel, probabilityLevel, String(requestedReason ?? '').trim())
        opportunity.probabilityHistory.unshift({ ...event, recovery: plan === null ? null : newRecovery(event.id, plan) })
      }
      salesRepository.save()
      return opportunityResponse(opportunity)
    },

    async saveProbabilityRecovery(id, eventId, input, expectedModified) {
      await wait()
      assertCapability(capabilities, 'deal:write')
      const opportunity = assertOpportunity(id)
      requireOpportunityVersion(opportunity, expectedModified)
      if (role !== 'Manager' && opportunity.owner !== userId) {
        throw new CrmApiError('PERMISSION_DENIED', 'Only the Opportunity owner or a Manager can maintain recovery plans.', requestId(), false)
      }
      const event = opportunity.probabilityHistory.find(row => row.id === eventId)
      if (!event) throw new CrmApiError('NOT_FOUND', 'The probability change was not found.', requestId(), false)
      if (!event.from || opportunityProbabilityLevelRank(event.to) >= opportunityProbabilityLevelRank(event.from)) {
        throw new CrmApiError('INVALID_TRANSITION', 'Only a downgrade can have a recovery plan.', requestId(), false)
      }
      const plan = recoveryPlan(input.plan)
      if ((event.recovery?.modified ?? null) !== input.recoveryModified) {
        throw new CrmApiError('VERSION_CONFLICT', 'The recovery plan changed. Reload before editing.', requestId(), false)
      }
      const previousRecovery = event.recovery
      if (!event.recovery) event.recovery = newRecovery(event.id, plan)
      else if (event.recovery.plan !== plan) {
        const modified = nextRecoveryVersion(event.recovery.modified)
        event.recovery = { ...event.recovery, plan, modified, history: [
          { id: `${event.recovery.id}-${event.recovery.history.length + 1}`, kind: 'PlanUpdated', plan, actor: userId, at: modified },
          ...event.recovery.history,
        ] }
      }
      try { salesRepository.save() } catch (error) { event.recovery = previousRecovery; throw error }
      return response(event.recovery)
    },

    async recordProbabilityRecoveryAction(id, eventId, input, expectedModified) {
      await wait()
      assertCapability(capabilities, 'deal:write')
      const opportunity = assertOpportunity(id)
      requireOpportunityVersion(opportunity, expectedModified)
      if (opportunity.owner !== userId) throw new CrmApiError('PERMISSION_DENIED', 'Only the current Opportunity owner can record the action taken.', requestId(), false)
      const event = opportunity.probabilityHistory.find(row => row.id === eventId)
      if (!event) throw new CrmApiError('NOT_FOUND', 'The probability change was not found.', requestId(), false)
      if (!event.from || opportunityProbabilityLevelRank(event.to) >= opportunityProbabilityLevelRank(event.from)) {
        throw new CrmApiError('INVALID_TRANSITION', 'Only a downgrade can have a recovery plan.', requestId(), false)
      }
      const actionTaken = recoveryPlan(input.actionTaken, 'actionTaken')
      const recovery = event.recovery
      if (!recovery) throw new CrmApiError('INVALID_TRANSITION', 'Record a recovery plan before recording the action taken.', requestId(), false)
      if (!input.recoveryModified?.trim()) throw new CrmApiError('VALIDATION_ERROR', 'recoveryModified is required.', requestId(), false)
      if (recovery.modified !== input.recoveryModified) throw new CrmApiError('VERSION_CONFLICT', 'The recovery changed. Reload before recording an action.', requestId(), false)
      if (recovery.state === 'handled') throw new CrmApiError('INVALID_TRANSITION', 'An action was already recorded for this downgrade.', requestId(), false)
      const modified = nextRecoveryVersion(recovery.modified)
      event.recovery = { ...recovery, modified, state: 'handled', actionTaken, actedBy: userId, actedAt: modified, history: [
        { id: `${recovery.id}-${recovery.history.length + 1}`, kind: 'ActionRecorded', plan: recovery.plan, actionTaken, actor: userId, at: modified },
        ...recovery.history,
      ] }
      try { salesRepository.save() } catch (error) { event.recovery = recovery; throw error }
      return response(event.recovery)
    },

    async rollbackOpportunityStage(id: string, input: RollbackOpportunityStageInput, expectedModified?: string) {
      await wait()
      assertCapability(capabilities, 'deal:rollback')
      const target = input?.targetStage
      if (!isOpportunityMilestoneStage(target)) {
        throw new CrmApiError('VALIDATION_ERROR', 'targetStage is invalid.', requestId(), false, { targetStage: 'Invalid value' })
      }
      const reason = requiredActionText(input?.reason, 'reason')
      const opportunity = lockOpportunityForAction(id, expectedModified)
      const from = opportunity.stage
      const reopening = from === 'lost'
      if (reopening) {
        // Without a recorded loss stage, reopening stops below internal validation, which would claim an approval nobody can vouch for.
        const ceiling = opportunity.lostAtStage || 'quotation_sent'
        if (opportunityStageIndex(target) > opportunityStageIndex(ceiling)) {
          throw new CrmApiError('INVALID_TRANSITION', `A lost Opportunity can only reopen at or below ${ceiling}.`, requestId(), false)
        }
      } else if (opportunityStageIndex(target) >= opportunityStageIndex(from)) {
        throw new CrmApiError('INVALID_TRANSITION', 'Rollback target must be an earlier stage.', requestId(), false)
      }
      const booking = liveOpportunityBooking(opportunity.id)
      if (booking?.status === 'Completed') throw new CrmApiError('CONFLICT', 'A completed Booking blocks stage rollback.', requestId(), false)
      if (target === 'internal_validation') {
        const approved = localInternalValidations
          .filter((item) => item.opportunityId === opportunity.id && item.status === 'approved')
          .sort((left, right) => right.attemptNo - left.attemptNo)[0]
        // Bookings are unshifted when they are created, so the first match is the latest one.
        const latestBooking = localBookings.find((item) => item.source === 'Opportunity' && item.sourceOpportunityId === opportunity.id)
        // Only the Booking the approval created may carry the Opportunity back; a PO confirmed straight from quotation_sent never had that approval.
        if (!approved?.bookingId || latestBooking?.id !== approved.bookingId) {
          throw new CrmApiError('INVALID_TRANSITION', 'internal_validation requires the Booking created by an approved internal validation.', requestId(), false)
        }
      } else if (booking) {
        throw new CrmApiError('CONFLICT', 'Cancel the Booking before rolling the Opportunity back.', requestId(), false)
      }
      if (from === 'quotation_sent') cancelPendingInternalValidation(opportunity, `Opportunity rolled back to ${target}.`)
      if (booking?.status === 'Confirmed') {
        // Production carries on under the internal validation, but the PO is no longer confirmed,
        // so its date goes too; confirming the PO again asks for it.
        const previousPoDate = booking.actualPoDate ?? ''
        Object.assign(booking, { status: 'Pending', actualPoDate: '', actualPoDateSource: '', actualPoDateNote: '', modified: `${now}#${requestId()}` })
        if (previousPoDate) appendOpportunityHistory(opportunity, 'bookingPoDate', previousPoDate, '')
      }
      const rfq = localRfqs.find((item) => item.opportunity.id === opportunity.id)
      if (opportunityStageIndex(target) <= opportunityStageIndex('customer_budget_approved') && rfq?.status === 'Approved') {
        rfq.status = 'Sales Revision'
        rfq.approvedBy = ''
        rfq.approvedAt = ''
        Object.assign(rfq.currentVersion, { status: 'Returned', managerDecision: 'Returned', managerComment: reason, managerDecidedBy: userId, managerDecidedByName: userName, managerDecidedAt: now })
        rfq.modified = nextRfqModified()
      }
      if (opportunityStageIndex(target) < opportunityStageIndex('customer_budget_approved')) opportunity.budgetApprovedOn = ''
      if (reopening) Object.assign(opportunity, { lostReason: '', lostAtStage: '', lostAt: '', lostBy: '' })
      const moved = moveOpportunityStage(opportunity, target, { source: 'rollback', event: reopening ? 'reopened' : 'rollback', reason })
      if (reopening) markLossReviewsReopened(opportunity, moved)
      salesRepository.save()
      return opportunityResponse(opportunity)
    },

    async confirmBudgetApproved(id: string, input: ConfirmBudgetApprovedInput, expectedModified?: string) {
      await wait()
      assertCapability(capabilities, 'deal:write')
      const opportunity = lockOpportunityForAction(id, expectedModified)
      requireOpportunityStage(opportunity, ['demo_done'], 'Budget approval')
      const approvedOn = requiredActionDate(input?.approvedOn, 'approvedOn')
      if (approvedOn > today) {
        throw new CrmApiError('VALIDATION_ERROR', 'approvedOn cannot be in the future.', requestId(), false, { approvedOn: 'Cannot be in the future' })
      }
      requireProbabilityLevel(opportunity)
      opportunity.budgetApprovedOn = approvedOn
      // The approval day Sales declares is a Shanghai calendar date; the stage arrival follows it.
      moveOpportunityStage(opportunity, 'customer_budget_approved', {
        source: 'manual',
        event: 'budget_confirmed',
        reachedAt: new Date(`${approvedOn}T00:00:00+08:00`).toISOString(),
        reachedAtBasis: 'declared',
      })
      salesRepository.save()
      return opportunityResponse(opportunity)
    },

    async requestInternalValidation(id: string, input: RequestInternalValidationInput, expectedModified?: string) {
      await wait()
      assertCapability(capabilities, 'deal:write')
      const opportunity = lockOpportunityForAction(id, expectedModified)
      requireOpportunityStage(opportunity, ['quotation_sent'], 'Internal validation')
      if (opportunity.saleType === 'Service') {
        throw new CrmApiError('INVALID_TRANSITION', 'Internal validation is only available for equipment Opportunities.', requestId(), false)
      }
      requireProbabilityLevel(opportunity)
      const reason = requiredActionText(input?.reason, 'reason')
      const expectedPoDate = requiredActionDate(input?.expectedPoDate, 'expectedPoDate')
      const booking = validateOpportunityBookingDraft(opportunity, input?.booking)
      const attempts = localInternalValidations.filter((item) => item.opportunityId === opportunity.id)
      if (attempts.some((item) => item.status === 'pending')) {
        throw new CrmApiError('CONFLICT', 'The Opportunity already has a pending internal validation.', requestId(), false)
      }
      if (!PERSONNEL.some((person) => person.role === 'Manager' && person.availableForAssignment && person.id !== userId)) {
        throw new CrmApiError('CONFLICT', 'No other active Manager can review this internal validation.', requestId(), false)
      }
      const validation: StoredOpportunityInternalValidation = {
        id: nextInternalValidationId(),
        opportunityId: opportunity.id,
        attemptNo: attempts.length + 1,
        status: 'pending',
        reason,
        expectedPoDate,
        booking,
        requestedBy: userId,
        requestedAt: new Date(now).toISOString(),
        decidedBy: '',
        decidedAt: '',
        decisionComment: '',
        bookingId: '',
        cancelledBy: '',
        cancelledAt: '',
        cancelReason: '',
      }
      localInternalValidations.push(validation)
      // The stage does not change; the write still moves modified so stale clients see the request.
      touchOpportunity(opportunity)
      appendOpportunityHistory(opportunity, 'internalValidationRequested', '', validation.id)
      salesRepository.save()
      return opportunityResponse(opportunity)
    },

    async reviewInternalValidation(id: string, input: ReviewInternalValidationInput, expectedModified?: string) {
      await wait()
      assertCapability(capabilities, 'deal:internal_validation_approve')
      const opportunity = lockOpportunityForAction(id, expectedModified)
      const validationId = requiredActionText(input?.validationId, 'validationId')
      const decision = input?.decision
      if (decision !== 'approved' && decision !== 'rejected') {
        throw new CrmApiError('VALIDATION_ERROR', 'decision is invalid.', requestId(), false, { decision: 'Invalid value' })
      }
      const comment = typeof input.comment === 'string' ? input.comment.trim() : ''
      if (decision === 'rejected' && !comment) {
        throw new CrmApiError('VALIDATION_ERROR', 'A comment is required to reject an internal validation.', requestId(), false, { comment: 'Required' })
      }
      const validation = localInternalValidations.find((item) => item.id === validationId && item.opportunityId === opportunity.id)
      if (!validation) throw new CrmApiError('INTERNAL_VALIDATION_NOT_FOUND', 'Internal validation was not found.', requestId(), false)
      if (validation.status !== 'pending') {
        throw new CrmApiError('INVALID_TRANSITION', 'The internal validation was already decided or cancelled.', requestId(), false)
      }
      if (validation.requestedBy === userId) {
        throw new CrmApiError('PERMISSION_DENIED', 'Managers cannot review their own internal validation.', requestId(), false)
      }
      requireOpportunityStage(opportunity, ['quotation_sent'], 'Internal validation review')
      let draft: BookingDraft | null = null
      if (decision === 'approved') {
        if (opportunity.saleType === 'Service') {
          throw new CrmApiError('INVALID_TRANSITION', 'Internal validation is only available for equipment Opportunities.', requestId(), false)
        }
        // The request may be days old: its contact, owner and currency must still be valid now.
        draft = validateOpportunityBookingDraft(opportunity, validation.booking)
        if (liveOpportunityBooking(opportunity.id)) throw new CrmApiError('CONFLICT', 'The Opportunity already has a live Booking.', requestId(), false)
      }
      Object.assign(validation, { status: decision, decidedBy: userId, decidedAt: new Date(now).toISOString(), decisionComment: comment })
      if (draft) {
        const booking = createOpportunityBooking(opportunity, draft, 'Pending')
        validation.bookingId = booking.id
        moveOpportunityStage(opportunity, 'internal_validation', {
          source: 'approval',
          event: 'internal_validation_approved',
          referenceDoctype: 'CRM Opportunity Internal Validation',
          referenceName: validation.id,
        })
        appendOpportunityHistory(opportunity, 'internalValidationApproved', validation.id, booking.id)
      } else {
        touchOpportunity(opportunity)
        appendOpportunityHistory(opportunity, 'internalValidationRejected', validation.id, comment)
      }
      salesRepository.save()
      return opportunityResponse(opportunity)
    },

    async confirmPo(id: string, input: ConfirmPoInput, expectedModified?: string) {
      await wait()
      assertCapability(capabilities, 'deal:write')
      const opportunity = lockOpportunityForAction(id, expectedModified)
      // At po_received the only thing left is to replace a Booking that was cancelled by hand.
      const replacing = opportunity.stage === 'po_received'
      if (!replacing) {
        requireOpportunityStage(opportunity, PO_CONFIRMABLE_STAGES, 'PO confirmation')
        requireProbabilityLevel(opportunity)
      }
      // The CNY amount of a foreign-currency order is known once the PO is.
      const draft = validateOpportunityBookingDraft(opportunity, input?.booking, true)
      // The date on the customer's PO, as opposed to the Opportunity's expected poDate.
      const actualPoDate = validateActualPoDate(input?.actualPoDate, true)
      const live = liveOpportunityBooking(opportunity.id)
      if (live && (opportunity.stage !== 'internal_validation' || live.status !== 'Pending')) {
        throw new CrmApiError('CONFLICT', 'The Opportunity already has a live Booking.', requestId(), false)
      }
      if (live) {
        // The form is prefilled from this Pending Booking, so both scope and its own optimistic-lock token apply.
        if (!canAccessBooking(live)) throw new CrmApiError('SCOPE_DENIED', 'The Pending Booking is outside the current user scope.', requestId(), false)
        if (input?.expectedBookingModified && live.modified && input.expectedBookingModified !== live.modified) {
          throw new CrmApiError('VERSION_CONFLICT', 'The Pending Booking was changed by another request.', requestId(), false)
        }
      }
      if (opportunity.stage === 'quotation_sent') cancelPendingInternalValidation(opportunity, 'PO received before the internal validation was decided.')
      const replaced = replacing ? localBookings.filter((item) => item.sourceOpportunityId === opportunity.id && item.status === 'Cancelled').sort((a, b) => String(a.modified ?? '').localeCompare(String(b.modified ?? ''))).at(-1) : undefined
      const booking = live
        ? Object.assign(applyOpportunityBookingDraft(live, draft), {
          status: 'Confirmed' as const, actualPoDate, actualPoDateSource: 'po_confirmation' as const, actualPoDateNote: '',
        })
        : createOpportunityBooking(opportunity, draft, 'Confirmed', actualPoDate)
      if (replacing) {
        touchOpportunity(opportunity)
        // Mirrors confirm_po: a replacement keeps the trail of the cancelled order's CNY amount and PO date.
        if (replaced) {
          const cnyOf = (item: BookingDto) => item.currency === 'CNY' ? item.amount : item.amountCny ?? ''
          if (cnyOf(replaced) !== cnyOf(booking)) appendOpportunityHistory(opportunity, 'bookingAmountCny', cnyOf(replaced), cnyOf(booking))
          if ((replaced.actualPoDate ?? '') !== actualPoDate) appendOpportunityHistory(opportunity, 'bookingPoDate', replaced.actualPoDate ?? '', actualPoDate)
        }
        appendOpportunityHistory(opportunity, 'bookingReplaced', '', booking.id)
      } else {
        moveOpportunityStage(opportunity, 'po_received', { source: 'manual', event: 'po_confirmed', referenceDoctype: 'CRM Booking', referenceName: booking.id })
        appendOpportunityHistory(opportunity, 'poConfirmed', '', booking.id)
      }
      salesRepository.save()
      return opportunityResponse(opportunity)
    },

    async markOpportunityLost(id: string, input: MarkOpportunityLostInput, expectedModified?: string) {
      await wait()
      assertCapability(capabilities, 'deal:write')
      const opportunity = lockOpportunityForAction(id, expectedModified)
      requireOpportunityStage(opportunity, OPEN_OPPORTUNITY_STAGES, 'Marking the Opportunity lost')
      const lostReason = requiredActionText(input?.lostReason, 'lostReason')
      if (liveOpportunityBooking(opportunity.id)) {
        throw new CrmApiError('CONFLICT', 'Cancel the Booking before marking the Opportunity lost.', requestId(), false)
      }
      cancelPendingInternalValidation(opportunity, 'Opportunity marked lost.')
      Object.assign(opportunity, {
        lostReason,
        lostAtStage: opportunity.stage as OpenOpportunityStage,
        lostAt: new Date(now).toISOString(),
        lostBy: userId,
      })
      createLossReview(opportunity, moveOpportunityStage(opportunity, 'lost', { source: 'lost', event: 'marked_lost', reason: lostReason }))
      salesRepository.save()
      return opportunityResponse(opportunity)
    },

    // The archive is a server rule with no behaviour here; tests stub these (AGENTS.md).
    async archiveStrategyOpportunity(id: string) {
      await wait()
      throw new CrmApiError('INVALID_TRANSITION', `The mock API does not archive Opportunities (${id}).`, requestId(), false)
    },
    async unarchiveStrategyOpportunity(id: string) {
      await wait()
      throw new CrmApiError('INVALID_TRANSITION', `The mock API does not archive Opportunities (${id}).`, requestId(), false)
    },

    createOpportunityStakeholder: saveOpportunityStakeholderInternal,
    updateOpportunityStakeholder: (opportunityId: string, stakeholderId: string, input: UpdateOpportunityStakeholderInput) => saveOpportunityStakeholderInternal(opportunityId, input, stakeholderId),

    async deleteOpportunityStakeholder(opportunityId: string, stakeholderId: string) {
      await wait()
      assertCapability(capabilities, 'deal:write')
      const opportunity = assertOpportunity(opportunityId)
      const index = opportunity.stakeholders.findIndex((item) => item.id === stakeholderId)
      if (index < 0) throw new CrmApiError('STAKEHOLDER_NOT_FOUND', '未找到该关键人', requestId(), false)
      const [removed] = opportunity.stakeholders.splice(index, 1)
      opportunity.history.unshift({ at: historyAt, actor: userId, field: 'Stakeholder', from: removed.name, to: 'Deleted' })
      salesRepository.save()
      return response({ id: stakeholderId })
    },

    ...createMockStatusApi(salesRepository, userId, (opportunityId, write) => {
      assertCapability(capabilities, write ? 'deal:write' : 'deal:view')
      assertOpportunity(opportunityId)
    }),
    createOpportunityAction: saveOpportunityActionInternal,
    updateOpportunityAction: (opportunityId: string, actionId: string, input: UpdateOpportunityActionInput) => saveOpportunityActionInternal(opportunityId, input, actionId),

    async deleteOpportunityAction(opportunityId: string, actionId: string) {
      await wait()
      assertCapability(capabilities, 'deal:write')
      const opportunity = assertOpportunity(opportunityId)
      const index = opportunity.actions.findIndex((item) => item.id === actionId)
      if (index < 0) throw new CrmApiError('ACTION_NOT_FOUND', '未找到该 Action', requestId(), false)
      const [removed] = opportunity.actions.splice(index, 1)
      opportunity.history.unshift({ at: historyAt, actor: userId, field: 'Action', from: removed.title, to: 'Deleted' })
      salesRepository.save()
      return response({ id: actionId })
    },

    async getDemoResources() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Demo resources require Frappe.', 'demo-resources') },
    async saveDemoResource() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Demo resources require Frappe.', 'demo-resources') },
    async getDemoUnavailability() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Demo resources require Frappe.', 'demo-resources') },
    async saveDemoUnavailability() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Demo resources require Frappe.', 'demo-resources') },
    async getDemoResourceSchedule() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Demo resources require Frappe.', 'demo-resources') },
    async saveDemoResourceSchedule() { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Demo resources require Frappe.', 'demo-resources') },
    async listDemoWorkflows(query: ListQuery = {}) {
      await ensureDemoPrimaryContacts()
      await wait()
      assertCapability(capabilities, 'demo_request:view')
      const snapshot = await repository.read()
      const fullArchive = role === 'Manager'
      const engineeringArchive = capabilities.includes('demo_request:engineering_review')
      const workflows = snapshot.demoRequests
        .filter(canAccessDemo)
        .filter((request) => request.status !== 'Cancelled')
        .map((request): DemoWorkflowDto => {
          const evaluation = snapshot.evaluations.find((item) => item.demoRequestId === request.id)
          const opportunity = localStrategyOpportunities.find((item) => item.id === request.opportunityId)
          const form = getDemoRequestFormData(request)
          const status = evaluation?.status ?? request.status
          const managerDone = request.status === 'Converted'
          const faeDone = ['Manager Approval', 'Manager Rejected', 'Converted'].includes(request.status)
          const lifecycleStage = mapDemoLifecycleStage(request.status, evaluation?.status) ?? undefined
          const completed = ['Accepted', 'Rejected'].includes(evaluation?.status ?? '')
          const currentTimelineIndex = lifecycleStage === 'Engineer Review' ? 1
            : lifecycleStage === 'Manager Approval' ? 2
              : lifecycleStage === 'Test Preparation' ? 3
                : lifecycleStage === 'Test Execution' ? 4
                  : lifecycleStage === 'Internal Review' ? 5
                    : lifecycleStage === 'Customer Review' ? 6
                      : 0
          const timelineState = (index: number): 'Done' | 'Current' | 'Waiting' => {
            if (completed || index < currentTimelineIndex) return 'Done'
            return index === currentTimelineIndex ? 'Current' : 'Waiting'
          }
          const artifacts = snapshot.artifacts
            .filter((artifact) => artifact.demoRequestId === request.id)
            .filter((artifact) => canReadDemoArtifact(request, evaluation, artifact))
            .map(({ id, type, fileName, mimeType, version, round, createdBy, createdAt, visibility }) =>
            ({ id, type, fileName, mimeType, version, round, createdBy, createdAt, visibility }))
          const requestSnapshot: NonNullable<DemoWorkflowDto['request']> = {
            objective: request.objective,
            requestedEquipment: request.requestedEquipment,
            sampleType: request.sampleType,
            sampleQuantity: request.sampleQuantity,
            priority: request.priority,
            acceptanceCriteria: form.keySuccessFactors || request.acceptanceCriteria,
            salesOwner: request.salesOwner,
            specificRequest: form.specificRequest,
            detectMeasure: form.detectMeasure,
            expectedResults: form.expectedResults,
            complementaryTool: form.complementaryTool,
            ...(engineeringArchive || fullArchive ? {
              testPlan: request.testPlan,
              assignedEquipment: request.assignedEquipment,
              resourceWindow: request.resourceWindow,
              estimatedCompletionDate: request.estimatedCompletionDate,
              technicalRisk: request.technicalRisk,
              engineerComment: request.engineerComment,
              internalQuestions: form.internalQuestions.split(/\r?\n/).filter(Boolean),
              wafers: form.wafers
                .filter((wafer) => Object.values(wafer).some((value) => value.trim()))
                .map((wafer, index) => ({
                  id: wafer.wid || `${request.id}-W${index + 1}`,
                  specificity: wafer.waferSpecificity || request.sampleType,
                  detail: [form.sizeShape, wafer.doiMetrologyItems].filter(Boolean).join(' · '),
                })),
            } : {}),
            ...(fullArchive ? {
              contactPerson: form.contactPerson,
              industry: form.industry || request.segment,
              competition: form.otherTools,
              managerDecision: request.managerDecision,
              managerComment: request.managerComment,
            } : {}),
          }
          return {
            id: request.id,
            accountId: request.accountId,
            siteId: opportunity?.siteId ?? '',
            opportunityId: request.opportunityId ?? '',
            title: request.title,
            account: request.accountName,
            opportunity: opportunity?.title ?? request.opportunityId ?? '自测',
            salesOwner: request.salesOwner,
            engineerOwner: request.engineerOwner,
            equipment: request.requestedEquipment || request.assignedEquipment,
            owner: request.engineerOwner,
            status,
            archiveCategory: completed ? 'Completed' : 'In Progress',
            stage: lifecycleStage,
            health: deriveDemoHealth({
              lastProgressAt: request.tracking.lastProgressAt,
              customerExpectedDate: request.customerExpectedDate,
              testRunDeadline: evaluation?.testRunDeadline ?? '',
              today: healthToday,
            }),
            tracking: { ...request.tracking },
            customerExpectedDate: request.customerExpectedDate,
            projectTimeline: [
              {
                key: 'sales-preparation',
                label: 'Sales Preparation',
                state: timelineState(0),
                actor: request.createdBy,
                date: request.createdAt.slice(0, 10),
              },
              {
                key: 'engineer-review',
                label: 'Engineer Review',
                state: timelineState(1),
                actor: request.engineerOwner,
                date: request.history.find((item) => item.to === 'Engineer Review')?.at.slice(0, 10),
              },
              {
                key: 'manager-approval',
                label: 'Manager Approval',
                state: timelineState(2),
                actor: request.approvedBy,
                date: request.history.find((item) => item.to === 'Manager Approval')?.at.slice(0, 10),
              },
              {
                key: 'wafer-preparation',
                label: 'Wafer Preparation',
                state: completed || (evaluation && evaluationPreparationStatus(evaluation, 'wafer') === 'Completed') ? 'Done' : timelineState(3),
                actor: evaluation?.waferPreparationCompletedBy ?? evaluation?.owner ?? request.engineerOwner,
                date: evaluation?.waferPreparationCompletedAt?.slice(0, 10),
              },
              {
                key: 'test-preparation',
                label: 'Test Preparation',
                state: completed || (evaluation && evaluationPreparationStatus(evaluation, 'test') === 'Completed') ? 'Done' : timelineState(3),
                actor: evaluation?.testPreparationCompletedBy ?? evaluation?.owner ?? request.engineerOwner,
                date: evaluation?.testPreparationCompletedAt?.slice(0, 10),
              },
              {
                key: 'test-execution',
                label: 'Test Execution',
                state: timelineState(4),
                actor: evaluation?.owner ?? request.engineerOwner,
                date: evaluation?.runs.find((run) => run.status === 'Completed')?.date
                  ?? evaluation?.runs[0]?.date,
              },
              {
                key: 'internal-review',
                label: 'Internal Review',
                state: timelineState(5),
                actor: evaluation?.owner ?? request.engineerOwner,
                date: evaluation?.runs.filter((run) => run.status === 'Completed').at(-1)?.date,
              },
              {
                key: 'customer-review',
                label: 'Customer Review',
                state: timelineState(6),
                date: completed
                  ? evaluation?.runs.filter((run) => run.status === 'Completed').at(-1)?.date
                  : request.customerExpectedDate,
              },
            ],
            request: requestSnapshot,
            ...(evaluation ? {
              evaluation: {
                id: evaluation.id,
                status: evaluation.status,
                owner: evaluation.owner,
                testRunDeadline: evaluation.testRunDeadline,
                waferPreparationStatus: evaluationPreparationStatus(evaluation, 'wafer'),
                waferPreparationCompletedBy: evaluation.waferPreparationCompletedBy,
                waferPreparationCompletedAt: evaluation.waferPreparationCompletedAt,
                testPreparationStatus: evaluationPreparationStatus(evaluation, 'test'),
                testPreparationCompletedBy: evaluation.testPreparationCompletedBy,
                testPreparationCompletedAt: evaluation.testPreparationCompletedAt,
                runs: fullArchive || engineeringArchive ? evaluation.runs.map((run) => ({ ...run })) : [],
              },
            } : {}),
            artifacts,
            conclusion: {
              status: evaluation?.acceptance === 'Accepted' ? 'Accepted' : evaluation?.acceptance === 'Rejected' ? 'Rejected' : 'Pending',
              // Customer comments are customer-facing record-keeping, so the Sales owner
              // sees them too. Only the engineering test summary stays gated. This mirrors
              // list_demo_workflows in services/evaluations.py.
              customerFeedback: evaluation?.customerReviews?.at(-1)?.comment ?? '',
              ...(fullArchive || engineeringArchive ? {
                summary: evaluation?.runs.filter((run) => run.status === 'Completed').at(-1)?.summary ?? '',
              } : {}),
            },
            testRound: evaluation?.testRound ?? 1,
            customerReviews: (evaluation?.customerReviews ?? []).map((review) => ({ ...review })),
            approvals: [
              { label: 'Sales 提交', actor: request.history.find((item) => item.to === 'Engineer Review')?.actor ?? request.createdBy, status: 'Done' },
              { label: 'FAE Review', actor: request.history.find((item) => item.to === 'Manager Approval')?.actor ?? request.engineerOwner, status: faeDone ? 'Done' : 'Current' },
              { label: 'Boss Approval', actor: request.approvedBy ?? '', status: managerDone ? 'Done' : faeDone ? 'Current' : 'Waiting' },
              { label: 'Internal Review', actor: evaluation?.owner ?? request.engineerOwner, status: evaluation?.status === 'Internal Review' || evaluation?.status === 'Analysis' ? 'Current' : ['Customer Review', 'Accepted', 'Rejected'].includes(evaluation?.status ?? '') ? 'Done' : 'Waiting' },
              { label: 'Customer Review', actor: '', status: evaluation?.status === 'Customer Review' ? 'Current' : ['Accepted', 'Rejected'].includes(evaluation?.status ?? '') ? 'Done' : 'Waiting' },
            ],
            executions: [],
            wafers: [],
            testRuns: [],
          }
        })
      return pageResponse(workflows, query)
    },

    async getDemoWorkflow(id: string) {
      let page = 1
      while (true) {
        const result = await mockApi.listDemoWorkflows({ page, pageSize: 200 })
        const workflow = result.data.items.find((item) => item.id === id)
        if (workflow) return response(workflow)
        const total = result.meta?.total ?? result.data.items.length
        if (page * 200 >= total || result.data.items.length === 0) break
        page += 1
      }
      throw new CrmApiError('DEMO_REQUEST_NOT_FOUND', '未找到该 Demo 项目', requestId(), false)
    },

    async listDemoComments(demoRequestId: string, query: ListQuery = {}) {
      await wait()
      const snapshot = await repository.read()
      const request = snapshot.demoRequests.find((item) => item.id === demoRequestId)
      if (!request) throw new CrmApiError('DEMO_REQUEST_NOT_FOUND', '未找到关联 Demo Request', requestId(), false)
      assertDemoScope(request)
      const comments = (snapshot.comments ?? [])
        .filter((item) => item.demoRequestId === demoRequestId)
        .sort((left, right) => right.createdAt.localeCompare(left.createdAt) || right.id.localeCompare(left.id))
      return pageResponse(comments, query)
    },

    async addDemoComment(demoRequestId: string, input: { body: string; mentionedPersonIds?: string[] }) {
      await wait()
      return repository.transact((snapshot) => {
        const request = snapshot.demoRequests.find((item) => item.id === demoRequestId)
        if (!request) throw new CrmApiError('DEMO_REQUEST_NOT_FOUND', '未找到关联 Demo Request', requestId(), false)
        assertDemoScope(request)
        const body = input.body.trim()
        if (!body) throw new CrmApiError('VALIDATION_ERROR', 'Comment 不能为空', requestId(), false)
        const mentionedPeople = Array.from(new Set(input.mentionedPersonIds ?? []))
          .map((id) => PERSONNEL.find((person) => person.id === id))
          .filter((person): person is NonNullable<typeof person> => Boolean(person))
          .map((person) => ({ id: person.id, name: person.name }))
        snapshot.comments ??= []
        const comment: DemoCommentDto = {
          id: nextId('CMT', snapshot.comments),
          demoRequestId,
          author: userId,
          role,
          body,
          ...(mentionedPeople.length ? { mentionedPeople } : {}),
          createdAt: `${healthToday}T10:30:00+08:00`,
        }
        snapshot.comments.push(comment)
        return response(comment)
      })
    },

    async listInstalledTools(query: ListQuery = {}) {
      await wait()
      const visibleTools = role === 'Engineer'
        ? localInstalledTools.filter((tool) => tool.engineerOwner === userId)
        : scoped(localInstalledTools, canAccessInstalledTool)
      const filtered = visibleTools.filter((tool) =>
        (!query.accountId || query.accountId === 'All' || tool.accountId === query.accountId)
        && (!query.status || query.status === 'All' || tool.status === query.status)
        && (!query.owner || query.owner === 'All' || tool.engineerOwner === query.owner),
      )
      return pageResponse(filtered, query)
    },

    async getInstalledTool(id: string) {
      await wait()
      assertCapability(capabilities, 'service:view')
      const tool = localInstalledTools.find((item) => item.id === id)
      if (!tool) throw new CrmApiError('NOT_FOUND', 'Installed Tool was not found.', requestId(), false)
      assertInstalledToolRead(tool)
      return response(installedToolDetail(tool))
    },

    async transitionInstalledTool(id: string, input: TransitionInstalledToolInput, expectedModified?: string) {
      await wait()
      assertCapability(capabilities, 'installed_tool:write')
      const tool = localInstalledTools.find((item) => item.id === id)
      if (!tool) throw new CrmApiError('NOT_FOUND', 'Installed Tool was not found.', requestId(), false)
      assertInstalledToolOperator(tool); assertInstalledToolVersion(tool, expectedModified)
      const required = [input.completedAt, input.result, input.openIssues, input.customerSignoff, input.comment]
      if (required.some((value) => !value.trim()) || !isIsoDate(input.completedAt) || !Array.isArray(input.evidence) || input.evidence.some((item) => typeof item !== 'string' || !item.trim())) {
        throw new CrmApiError('VALIDATION_ERROR', 'Lifecycle completion fields are invalid.', requestId(), false)
      }
      const stage = inferredInstalledToolStage(tool); const history = installedToolLifecycleHistory.get(id) ?? []
      const index = installedToolStages.indexOf(stage ?? 'FAT')
      if (index < 0) throw new CrmApiError('INVALID_TRANSITION', 'Lifecycle stage is invalid.', requestId(), false)
      const toStage: string = installedToolStages[index + 1] ?? 'Completed'
      history.unshift({ id: `LIF-${id}-${history.length + 1}`, at: now, actor: userId, fromStage: stage ?? 'FAT', toStage, completedAt: input.completedAt, result: input.result.trim(), openIssues: input.openIssues.trim(), customerSignoff: input.customerSignoff.trim(), comment: input.comment.trim(), evidence: input.evidence.map((item) => item.trim()) })
      installedToolLifecycleHistory.set(id, history)
      tool.lifecycleStage = toStage === 'Completed' ? 'Warranty' : toStage as InstalledToolDto['lifecycleStage']
      const statusMap: Partial<Record<typeof installedToolStages[number], string>> = { FAT: 'Shipment', Shipment: 'Installation', Installation: 'Installation Complete', SAT: 'Production' }
      tool.status = statusMap[stage ?? 'FAT'] ?? tool.status; tool.modified = nextInstalledToolModified(); salesRepository.save()
      return response(installedToolDetail(tool))
    },

    async addInstalledToolVersionRecord(id: string, input: AddInstalledToolVersionRecordInput, expectedModified?: string) {
      await wait(); assertCapability(capabilities, 'installed_tool:write')
      const tool = localInstalledTools.find((item) => item.id === id); if (!tool) throw new CrmApiError('NOT_FOUND', 'Installed Tool was not found.', requestId(), false)
      assertInstalledToolOperator(tool); assertInstalledToolVersion(tool, expectedModified)
      const fieldMap = { Software: 'software', Firmware: 'firmware', 'Operating System': 'operatingSystem', Configuration: 'configuration' } as const
      const field = fieldMap[input.changeType]; const toValue = input.toValue.trim(); const reason = input.reason.trim()
      if (!field || !isIsoDate(input.changeDate) || !toValue || !reason) throw new CrmApiError('VALIDATION_ERROR', 'Version fields are invalid.', requestId(), false)
      const fromValue = String(tool[field] ?? ''); if (fromValue === toValue) throw new CrmApiError('VALIDATION_ERROR', 'Value did not change.', requestId(), false)
      const history = installedToolVersionHistory.get(id) ?? []; history.unshift({ id: `VER-${id}-${history.length + 1}`, at: now, actor: userId, changeDate: input.changeDate, changeType: input.changeType, fromValue, toValue, reason, comment: input.comment?.trim() ?? '' }); installedToolVersionHistory.set(id, history)
      tool[field] = toValue; tool.modified = nextInstalledToolModified(); salesRepository.save(); return response(installedToolDetail(tool))
    },

    async addInstalledToolServiceRecord(id: string, input: AddInstalledToolServiceRecordInput, expectedModified?: string) {
      await wait(); assertCapability(capabilities, 'installed_tool:write')
      const tool = localInstalledTools.find((item) => item.id === id); if (!tool) throw new CrmApiError('NOT_FOUND', 'Installed Tool was not found.', requestId(), false)
      assertInstalledToolOperator(tool); assertInstalledToolVersion(tool, expectedModified)
      const result = input.result.trim(); const openIssues = input.openIssues.trim(); const nextAction = input.nextAction?.trim() ?? ''
      const serviceTypes = ['Warranty Activation', 'Preventive Maintenance', 'Corrective Service', 'Remote Support', 'Installation Support', 'Contract Change']
      const actionOwner = input.actionOwner?.trim() ?? ''
      if (!serviceTypes.includes(input.serviceType) || !isIsoDate(input.serviceDate) || !result || !openIssues
        || (nextAction && (!actionOwner || !PERSONNEL.some((person) => person.id === actionOwner) || !input.due || !isIsoDate(input.due)))
        || Boolean(input.warrantyStart && input.warrantyEnd && input.warrantyStart > input.warrantyEnd)) throw new CrmApiError('VALIDATION_ERROR', 'Service fields are invalid.', requestId(), false)
      const history = installedToolServiceHistory.get(id) ?? []; history.unshift({ id: `SVC-${id}-${history.length + 1}`, at: now, actor: userId, serviceDate: input.serviceDate, serviceType: input.serviceType, result, openIssues, nextAction, actionOwner: nextAction ? input.actionOwner!.trim() : '', due: nextAction ? input.due! : '', comment: input.comment?.trim() ?? '', warrantyStart: input.warrantyStart ?? '', warrantyEnd: input.warrantyEnd ?? '', serviceContract: input.serviceContract?.trim() ?? '', pmCycle: input.pmCycle?.trim() ?? '' }); installedToolServiceHistory.set(id, history)
      tool.lastService = input.serviceDate; if (input.warrantyStart !== undefined) tool.warrantyStart = input.warrantyStart; if (input.warrantyEnd !== undefined) tool.warrantyEnd = input.warrantyEnd; if (input.serviceContract !== undefined) tool.serviceContract = input.serviceContract.trim(); if (input.pmCycle !== undefined) tool.pmCycle = input.pmCycle.trim(); tool.modified = nextInstalledToolModified(); salesRepository.save(); return response(installedToolDetail(tool))
    },

    async updateInstalledTool(id: string, input: UpdateInstalledToolInput, expectedModified?: string) {
      await wait()
      assertCapability(capabilities, 'installed_tool:write')
      const tool = localInstalledTools.find((item) => item.id === id)
      if (!tool) throw new CrmApiError('NOT_FOUND', 'Installed Tool was not found.', requestId(), false)
      assertInstalledToolOperator(tool); assertInstalledToolVersion(tool, expectedModified)
      if (role === 'Engineer' && input.engineerOwner !== tool.engineerOwner) throw new CrmApiError('SCOPE_DENIED', 'Engineer cannot reassign Installed Tool.', requestId(), false)
      const engineerOwner = validateOwner(input.engineerOwner, ['Engineer'])
      const site = (localSites[tool.accountId] ?? []).find((item) => item.id === input.siteId)
      if (!site) throw new CrmApiError('CONFLICT', 'Site belongs to another account.', requestId(), false)
      const model = input.model.trim(); const location = input.location.trim()
      const ownershipType = input.ownershipType === '' ? '' : input.ownershipType?.trim() || tool.ownershipType || 'Customer Owned'
      if (!model || !location || !ownershipType) throw new CrmApiError('VALIDATION_ERROR', 'Master fields are required.', requestId(), false)
      Object.assign(tool, { siteId: site.id, site: site.name, model, location, engineerOwner, operatingSystem: input.operatingSystem?.trim() ?? '', warrantyStart: input.warrantyStart ?? '', warrantyEnd: input.warrantyEnd, serviceContract: input.serviceContract?.trim() ?? '', pmCycle: input.pmCycle?.trim() ?? '', ownershipType, salesOrder: input.salesOrder.trim(), contract: input.contract.trim(), modified: nextInstalledToolModified() })
      salesRepository.save(); return response(tool)
    },

    async listRfqs(query = {}) {
      await wait()
      assertCapability(capabilities, 'rfq:view')
      const search = query.search?.trim().toLocaleLowerCase() ?? ''
      const items = localRfqs.filter((rfq) => {
        if (role === 'Sales' && rfq.salesOwner !== userId) return false
        if (role === 'Engineer' && rfq.engineerOwner !== userId) return false
        if (query.status && query.status !== 'All' && rfq.status !== query.status) return false
        if (query.owner && query.owner !== 'All' && ![rfq.salesOwner, rfq.engineerOwner].includes(query.owner)) return false
        if (query.opportunityId && rfq.opportunity.id !== query.opportunityId) return false
        return !search || `${rfq.id} ${rfq.opportunity.id} ${rfq.opportunity.title} ${rfq.opportunity.account} ${rfq.fileName}`.toLocaleLowerCase().includes(search)
      })
      return pageResponse(items, query)
    },

    async getRfq(id) {
      await wait()
      assertCapability(capabilities, 'rfq:view')
      const rfq = localRfqs.find((item) => item.id === id)
      if (!rfq) throw new CrmApiError('NOT_FOUND', 'RFQ was not found.', requestId(), false)
      assertRfqVisible(rfq)
      const opportunity = localStrategyOpportunities.find((item) => item.id === rfq.opportunity.id)
      if (opportunity) rfq.opportunity = rfqOpportunity(opportunity)
      return response(rfq)
    },

    async createRfq(input, file) {
      await wait()
      if (!['Sales', 'Manager'].includes(role)) throw new CrmApiError('PERMISSION_DENIED', 'CRM Sales or Manager role is required.', requestId(), false)
      assertCapability(capabilities, 'rfq:create')
      validateContactFileUpload(file)
      if (!/\.(pdf|png|jpe?g|docx|xlsx|pptx)$/i.test(file.fileName)) throw new CrmApiError('VALIDATION_ERROR', 'Unsupported RFQ file type.', requestId(), false)
      const opportunity = assertOpportunity(input.opportunityId)
      if (!canCreateRfqAt(opportunity.stage)) throw new CrmApiError('INVALID_TRANSITION', 'RFQ can only be created when the Opportunity is at customer_budget_approved.', requestId(), false)
      if (localRfqs.some((item) => item.opportunity.id === opportunity.id)) throw new CrmApiError('CONFLICT', 'This Opportunity already has an RFQ.', requestId(), false)
      assertPersonnelRole(input.engineerId, ['Engineer'])
      const sequence = String(localRfqs.length + 1).padStart(5, '0')
      const id = `CRM-RFQ-${sequence}`
      const versionId = `CRM-RFQV-${sequence}`
      const version: RfqVersionDto = {
        id: versionId, version: 1, status: 'Engineer Review', fileName: file.fileName,
        mimeType: file.mimeType, size: file.size, uploadedBy: userId, uploadedByName: userName,
        uploadedAt: now, engineerComment: '', engineerCommentedBy: '', engineerCommentedByName: '',
        engineerCommentedAt: '', managerDecision: '', managerComment: '', managerDecidedBy: '',
        managerDecidedByName: '', managerDecidedAt: '',
      }
      const rfq: RfqDetailDto = {
        id, opportunity: rfqOpportunity(opportunity), salesOwner: opportunity.owner, salesOwnerName: PERSONNEL.find((person) => person.id === opportunity.owner)?.name ?? opportunity.owner,
        engineerOwner: input.engineerId, engineerOwnerName: PERSONNEL.find((person) => person.id === input.engineerId)?.name ?? input.engineerId,
        status: 'Engineer Review', currentVersionId: versionId, latestVersion: 1, fileName: file.fileName,
        note: input.note?.trim() ?? '', approvedBy: '', approvedAt: '', modified: nextRfqModified(),
        currentVersion: version, versions: [version],
      }
      rfqFiles.set(versionId, { blob: file.blob, fileName: file.fileName, mimeType: file.mimeType })
      localRfqs.unshift(rfq)
      return response(rfq)
    },

    async reviseRfq(id, file, expectedModified) {
      await wait()
      if (!['Sales', 'Manager'].includes(role)) throw new CrmApiError('PERMISSION_DENIED', 'CRM Sales or Manager role is required.', requestId(), false)
      const rfq = localRfqs.find((item) => item.id === id)
      if (!rfq) throw new CrmApiError('NOT_FOUND', 'RFQ was not found.', requestId(), false)
      assertRfqVisible(rfq)
      assertRfqVersion(rfq, expectedModified)
      if (rfq.status !== 'Sales Revision') throw new CrmApiError('INVALID_TRANSITION', 'Only a returned RFQ can be revised.', requestId(), false)
      validateContactFileUpload(file)
      if (!/\.(pdf|png|jpe?g|docx|xlsx|pptx)$/i.test(file.fileName)) throw new CrmApiError('VALIDATION_ERROR', 'Unsupported RFQ file type.', requestId(), false)
      const number = rfq.latestVersion + 1
      const versionId = `${rfq.id}-V${number}`
      const version: RfqVersionDto = {
        id: versionId, version: number, status: 'Engineer Review', fileName: file.fileName,
        mimeType: file.mimeType, size: file.size, uploadedBy: userId, uploadedByName: userName,
        uploadedAt: now, engineerComment: '', engineerCommentedBy: '', engineerCommentedByName: '',
        engineerCommentedAt: '', managerDecision: '', managerComment: '', managerDecidedBy: '',
        managerDecidedByName: '', managerDecidedAt: '',
      }
      rfqFiles.set(versionId, { blob: file.blob, fileName: file.fileName, mimeType: file.mimeType })
      Object.assign(rfq, { status: 'Engineer Review', currentVersionId: versionId, latestVersion: number, fileName: file.fileName, modified: nextRfqModified(), currentVersion: version })
      rfq.versions.unshift(version)
      return response(rfq)
    },

    async submitRfqEngineerComment(id, comment, expectedModified) {
      await wait()
      if (role !== 'Engineer') throw new CrmApiError('PERMISSION_DENIED', 'CRM Engineer role is required.', requestId(), false)
      const rfq = localRfqs.find((item) => item.id === id)
      if (!rfq) throw new CrmApiError('NOT_FOUND', 'RFQ was not found.', requestId(), false)
      assertRfqVisible(rfq)
      assertRfqVersion(rfq, expectedModified)
      if (rfq.status !== 'Engineer Review') throw new CrmApiError('INVALID_TRANSITION', 'RFQ is not waiting for Engineer Comment.', requestId(), false)
      if (!comment.trim()) throw new CrmApiError('VALIDATION_ERROR', 'Engineer Comment is required.', requestId(), false)
      Object.assign(rfq.currentVersion, { status: 'Manager Approval', engineerComment: comment.trim(), engineerCommentedBy: userId, engineerCommentedByName: userName, engineerCommentedAt: now })
      rfq.status = 'Manager Approval'
      rfq.modified = nextRfqModified()
      return response(rfq)
    },

    async reviewRfq(id, input, expectedModified) {
      await wait()
      if (role !== 'Manager') throw new CrmApiError('PERMISSION_DENIED', 'CRM Manager role is required.', requestId(), false)
      const rfq = localRfqs.find((item) => item.id === id)
      if (!rfq) throw new CrmApiError('NOT_FOUND', 'RFQ was not found.', requestId(), false)
      assertRfqVersion(rfq, expectedModified)
      if (rfq.status !== 'Manager Approval') throw new CrmApiError('INVALID_TRANSITION', 'RFQ is not waiting for Manager approval.', requestId(), false)
      if (input.decision === 'Returned' && !input.comment.trim()) throw new CrmApiError('VALIDATION_ERROR', 'A return reason is required.', requestId(), false)
      // Approval moves the Opportunity first, so a refused move leaves the RFQ waiting for approval.
      if (input.decision === 'Approved') {
        advanceOpportunityForEvent(rfq.opportunity.id, 'rfq_approved', { referenceDoctype: 'CRM RFQ', referenceName: rfq.id })
        const opportunity = localStrategyOpportunities.find((item) => item.id === rfq.opportunity.id)
        if (opportunity) rfq.opportunity = rfqOpportunity(opportunity)
      }
      Object.assign(rfq.currentVersion, { status: input.decision === 'Approved' ? 'Approved' : 'Returned', managerDecision: input.decision, managerComment: input.comment.trim(), managerDecidedBy: userId, managerDecidedByName: userName, managerDecidedAt: now })
      rfq.status = input.decision === 'Approved' ? 'Approved' : 'Sales Revision'
      rfq.approvedBy = input.decision === 'Approved' ? userId : ''
      rfq.approvedAt = input.decision === 'Approved' ? now : ''
      rfq.modified = nextRfqModified()
      salesRepository.save()
      return response(rfq)
    },

    async previewRfqFile(id, versionId) {
      await wait()
      const rfq = localRfqs.find((item) => item.id === id)
      if (!rfq) throw new CrmApiError('NOT_FOUND', 'RFQ was not found.', requestId(), false)
      assertRfqVisible(rfq)
      const file = rfqFiles.get(versionId || rfq.currentVersionId)
      if (!file) throw new CrmApiError('NOT_FOUND', 'RFQ file was not found.', requestId(), false)
      const office = /officedocument/.test(file.mimeType)
      return office
        ? { blob: new Blob([`Mock PDF preview for ${file.fileName}`], { type: 'application/pdf' }), fileName: `${file.fileName}.pdf`, mimeType: 'application/pdf' }
        : { ...file }
    },

    async downloadRfqFile(id, versionId) {
      await wait()
      if (role === 'Engineer') throw new CrmApiError('PERMISSION_DENIED', 'Engineers cannot download original RFQ files.', requestId(), false)
      const rfq = localRfqs.find((item) => item.id === id)
      if (!rfq) throw new CrmApiError('NOT_FOUND', 'RFQ was not found.', requestId(), false)
      assertRfqVisible(rfq)
      const file = rfqFiles.get(versionId || rfq.currentVersionId)
      if (!file) throw new CrmApiError('NOT_FOUND', 'RFQ file was not found.', requestId(), false)
      return { ...file }
    },

    async listControlledDocuments(query: ListQuery = {}) {
      await wait()
      return pageResponse(localControlledDocuments.map((document) => {
        const accessRequest = localDocumentRequests.find((item) => item.documentId === document.id && item.requester === userId)
        const approved = accessRequest?.status === 'Approved'
        return {
          ...clone(document),
          versionId: `${document.id}-${document.version}-${document.revision}`,
          mimeType: document.mimeType || 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
          size: document.size || 0,
          hasPreview: document.hasPreview ?? true,
          canPreview: (document.hasPreview ?? true) && (document.access === 'Direct' || role === 'Manager' || approved),
          canDownload: document.access === 'Direct' || role === 'Manager' || approved,
          deliveryMode: document.access === 'Direct' || role === 'Manager' ? 'Original' : accessRequest?.deliveryMode || '',
          accessRequest: accessRequest ? clone(accessRequest) : null,
        }
      }), query)
    },

    async previewControlledDocument(documentId: string) {
      await wait()
      const approved = localDocumentRequests.some((item) => item.documentId === documentId && item.requester === userId && item.status === 'Approved')
      const document = localControlledDocuments.find((item) => item.id === documentId && (item.access === 'Direct' || role === 'Manager' || approved))
      if (!document) throw new CrmApiError('NOT_FOUND', '受控文档不存在或不可预览', requestId(), false)
      const fileName = `${document.id}-Controlled.pdf`
      return { blob: new Blob([`Mock preview for ${document.id}`], { type: 'application/pdf' }), fileName, mimeType: 'application/pdf' }
    },

    async downloadControlledDocument(documentId: string) {
      await wait()
      const accessRequest = localDocumentRequests.find((item) => item.documentId === documentId && item.requester === userId && item.status === 'Approved')
      const document = localControlledDocuments.find((item) => item.id === documentId && (item.access === 'Direct' || role === 'Manager' || accessRequest))
      if (!document) throw new CrmApiError('NOT_FOUND', '受控文档不存在或不可下载', requestId(), false)
      const original = accessRequest?.deliveryMode === 'Original'
      const mimeType = original ? 'application/vnd.openxmlformats-officedocument.presentationml.presentation' : 'application/pdf'
      const fileName = original ? `${document.id}.pptx` : `${document.id}-Watermarked.pdf`
      return { blob: new Blob([`Mock download for ${document.id}`], { type: mimeType }), fileName, mimeType }
    },

    async requestControlledDocumentAccess(versionId: string, reason: string) {
      await wait()
      const requestReason = reason.trim()
      if (!requestReason) throw new CrmApiError('VALIDATION_ERROR', '访问原因不能为空。', requestId(), false)
      const document = localControlledDocuments.find((item) => `${item.id}-${item.version}-${item.revision}` === versionId)
      if (!document) throw new CrmApiError('NOT_FOUND', 'Controlled document was not found.', requestId(), false)
      if (document.status !== 'Released' || document.access !== 'Request') throw new CrmApiError('PERMISSION_DENIED', 'This document does not accept access requests.', requestId(), false)
      const existing = localDocumentRequests.find((item) => item.documentId === document.id && item.requester === userId && item.versionId === versionId && item.status === 'Pending')
      if (existing) return response(existing)
      const request: ControlledDocumentAccessRequestDto = {
        id: `ACCESS-${localDocumentRequests.length + 1}`,
        requester: userId,
        requesterName: userName,
        requesterRole: role,
        documentId: document.id,
        documentTitle: document.title,
        versionId,
        version: document.version,
        revision: document.revision,
        reason: requestReason,
        status: 'Pending',
        deliveryMode: '',
        submittedAt: now,
        decidedBy: '',
        decidedAt: '',
        decisionNote: '',
      }
      localDocumentRequests.unshift(request)
      return response(request)
    },

    async listControlledDocumentRequests(query: ListQuery = {}) {
      await wait()
      if (role !== 'Manager') throw new CrmApiError('PERMISSION_DENIED', 'Manager approval is required.', requestId(), false)
      return pageResponse(localDocumentRequests, query)
    },

    async decideControlledDocumentRequest(requestIdValue, decision) {
      await wait()
      if (role !== 'Manager') throw new CrmApiError('PERMISSION_DENIED', 'Manager approval is required.', requestId(), false)
      const request = localDocumentRequests.find((item) => item.id === requestIdValue)
      if (!request) throw new CrmApiError('NOT_FOUND', 'Controlled-document request was not found.', requestId(), false)
      request.status = decision === 'reject' ? 'Rejected' : decision === 'more-info' ? 'More Info Required' : 'Approved'
      request.deliveryMode = decision === 'approve-original' ? 'Original' : decision === 'approve-watermarked' ? 'Watermarked' : ''
      request.decidedBy = userId
      request.decidedAt = now
      return response(request)
    },

    async submitControlledDocumentUpload(input, file) {
      await wait()
      if (!file.fileName.match(/\.(pdf|docx|xlsx|pptx)$/i) || file.size <= 0) throw new CrmApiError('VALIDATION_ERROR', 'Unsupported document upload.', requestId(), false)
      const sequence = String(localDocumentUploadRequests.length + 1).padStart(5, '0')
      const request: DocumentUploadRequestDto = {
        ...clone(input), id: `DOCUP-${sequence}`, product: input.product || 'General', version: input.version || '1.0', revision: input.revision || 'R1',
        reviewDate: input.reviewDate || `${Number(today.slice(0, 4)) + 1}${today.slice(4)}`, fileName: file.fileName,
        mimeType: file.mimeType, size: file.size, status: role === 'Manager' ? 'Published' : 'Pending', submittedBy: userId,
        submittedByName: userName, submittedByRole: role, submittedAt: now, decidedBy: role === 'Manager' ? userId : '',
        decidedAt: role === 'Manager' ? now : '', decisionReason: '', publishedDocumentId: role === 'Manager' ? `DOC-UPL-${sequence}` : '',
      }
      localDocumentUploadRequests.unshift(request)
      if (role === 'Manager') localControlledDocuments.unshift({
        id: request.publishedDocumentId, versionId: `${request.publishedDocumentId}-${request.version}-${request.revision}`,
        title: request.title, category: request.category, type: request.documentType, product: request.product || 'General',
        version: request.version || '1.0', revision: request.revision || 'R1', status: 'Released', confidentiality: request.confidentiality,
        access: request.accessMode, reviewDate: request.reviewDate || '', owner: userId, mimeType: file.mimeType, size: file.size,
        hasPreview: file.mimeType === 'application/pdf', fileName: file.fileName, versions: [], audit: [], applicableTool: request.applicableTool || '',
      })
      return response(request)
    },

    async listControlledDocumentUploadRequests(query = {}) {
      await wait()
      if (role !== 'Manager') throw new CrmApiError('PERMISSION_DENIED', 'Manager approval is required.', requestId(), false)
      return pageResponse(localDocumentUploadRequests.filter((item) => item.status === 'Pending'), query)
    },

    async decideControlledDocumentUploadRequest(requestIdValue, input) {
      await wait()
      if (role !== 'Manager') throw new CrmApiError('PERMISSION_DENIED', 'Manager approval is required.', requestId(), false)
      const request = localDocumentUploadRequests.find((item) => item.id === requestIdValue)
      if (!request || request.status !== 'Pending') throw new CrmApiError('CONFLICT', 'Upload request is unavailable.', requestId(), false)
      if (input.decision === 'reject') {
        if (!input.reason.trim()) throw new CrmApiError('VALIDATION_ERROR', 'Rejection reason is required.', requestId(), false)
        Object.assign(request, { status: 'Rejected', decisionReason: input.reason, decidedBy: userId, decidedAt: now })
      } else {
        Object.assign(request, { status: 'Published', category: input.category, confidentiality: input.confidentiality, accessMode: input.accessMode, publishedDocumentId: `DOC-UPL-${request.id.slice(-5)}`, decidedBy: userId, decidedAt: now })
      }
      return response(request)
    },

    async changeCurrentUserPassword() {
      await wait()
      throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Mock 模式不修改真实账号密码', requestId(), false)
    },

    async signOut() {
      await wait()
      throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Mock 模式没有会话可退出', requestId(), false)
    },

    async listNotifications(query = {}) {
      await wait()
      const page = Number.isInteger(query.page) && Number(query.page) > 0 ? Number(query.page) : 1
      const pageSize = Number.isInteger(query.pageSize) && Number(query.pageSize) > 0
        ? Math.min(Number(query.pageSize), 200)
        : 20
      const result = response({ items: [] })
      result.meta = { ...result.meta!, page, pageSize, total: 0 }
      return result
    },

    async markNotificationRead(id: string) {
      await wait()
      throw new CrmApiError('NOTIFICATION_NOT_FOUND', `Notification ${id} was not found`, requestId(), false)
    },

    async markAllNotificationsRead() {
      await wait()
      return response({ updated: 0, readAt: new Date().toISOString() })
    },
  }
  return mockApi
}
