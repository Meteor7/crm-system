<script setup lang="ts">
import { systemValueLabel } from '@/features/shared/system-labels'
import { personnelDisplayName } from '@/demo/personnel'
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft, Building2, CircleDollarSign, ClipboardCheck, FileCheck2, FileText, PackageCheck, Pencil, Plus, RotateCcw, ShieldCheck, Target, Trash2, Users } from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import { api as defaultApi, CrmApiError, type CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import DataState from '@/design-system/DataState.vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import ContactModal from '@/features/contacts/ContactModal.vue'
import ActionEditorModal from '@/features/opportunities/ActionEditorModal.vue'
import BudgetApprovalModal from '@/features/opportunities/BudgetApprovalModal.vue'
import InternalValidationPanel from '@/features/opportunities/InternalValidationPanel.vue'
import InternalValidationRequestModal from '@/features/opportunities/InternalValidationRequestModal.vue'
import OpportunityStatusCard from '@/features/opportunities/OpportunityStatusCard.vue'
import OpportunityEditorModal from '@/features/opportunities/OpportunityEditorModal.vue'
import OpportunityMilestoneBar from '@/features/opportunities/OpportunityMilestoneBar.vue'
import OpportunityStageTimeline from '@/features/opportunities/OpportunityStageTimeline.vue'
import ProbabilityRecoveryPanel from '@/features/opportunities/ProbabilityRecoveryPanel.vue'
import LossReviewCard from '@/features/opportunities/LossReviewCard.vue'
import PoConfirmationModal from '@/features/opportunities/PoConfirmationModal.vue'
import StakeholderEditorModal from '@/features/opportunities/StakeholderEditorModal.vue'
import { useAppStore } from '@/stores/app'
import type { AccountSummaryDto, ContactSummaryDto, CreateContactInput, SiteDto } from '@/types/crm'
import type {
  ConfirmBudgetApprovedInput,
  ConfirmPoInput,
  CreateOpportunityActionInput,
  CreateOpportunityStakeholderInput,
  CreateStrategyOpportunityInput,
  OpportunityActionDto,
  OpportunityStakeholderDto,
  OpportunityStakeholderStance,
  RequestInternalValidationInput,
  ReviewInternalValidationInput,
  StrategyOpportunityDto,
} from '@/types/workspaces'
import { formatMoney } from '@/domain/money'
import { EQUIPMENT_PRESETS } from '@/domain/equipment'
import { loadEquipmentTypes } from '@/features/opportunities/equipment-types'
import { formatDisplayDate, formatDisplayDateTime } from '@/domain/time'
import { opportunityProbabilityLevelLabel, opportunityProbabilityLevelTone } from '@/domain/opportunity-probability'
import {
  canConfirmPoAt,
  canCreateRfqAt,
  canWorkQuotationAt,
  isOpenOpportunityStage,
  opportunityRollbackOptions,
  opportunityRollbackTargets,
  opportunityStageLabel,
  opportunityStageTone,
  type OpportunityMilestoneStage,
} from '@/domain/opportunity-stages'
import { readAllPages } from '@/features/shared/read-all-pages'
import { sitesByAccountId } from '@/features/accounts/account-sites'
import { useI18n, useLocaleMessage, localeMessage } from '@/i18n'
import { salesEnumLabel } from '@/features/shared/sales-i18n'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const { locale, t } = useI18n()
const app = useAppStore()
const route = useRoute()
const router = useRouter()
const selected = ref<StrategyOpportunityDto | null>(null)
const quotationId = ref('')
const rfqId = ref('')
const rfqStatus = ref('')
const accounts = ref<AccountSummaryDto[]>([])
const contacts = ref<ContactSummaryDto[]>([])
const sitesByAccount = ref<Record<string, SiteDto[]>>({})
// The editors open before these arrive (the Opportunity is read alongside); they say so while that lasts.
const referencesLoading = ref(true)
const loading = ref(true)
const error = useLocaleMessage()
const requestId = ref('')
const denied = ref(false)
const notFound = ref(false)
const busy = ref(false)
const modalError = useLocaleMessage()
const validationError = useLocaleMessage()
const opportunityModal = ref(false)
const equipmentTypes = ref<string[]>([...EQUIPMENT_PRESETS])
watch(opportunityModal, (open) => { if (open) void loadEquipmentTypes(props.apiClient).then((types) => { equipmentTypes.value = types }) })
const stakeholderModal = ref(false)
const actionModal = ref(false)
const contactModal = ref(false)
const budgetModal = ref(false)
const validationRequestModal = ref(false)
const poModal = ref<'confirm' | 'replace' | null>(null)
const lostModal = ref(false)
const lostReason = ref('')
const rollbackModal = ref(false)
const rollbackReason = ref('')
const rollbackTarget = ref<OpportunityMilestoneStage | ''>('')
const rollbackErrors = ref<Record<string, string>>({})
const deleting = ref(false), deleteError = useLocaleMessage(), deleteRequestId = ref('')
const editingStakeholder = ref<OpportunityStakeholderDto | null>(null)
const editingAction = ref<OpportunityActionDto | null>(null)
const selectedContactId = ref('')
const bookingContactId = ref('')
const contactAccountId = ref('')
const contactContext = ref<'stakeholder' | 'booking'>('stakeholder')
const currentUserId = computed(() => app.bootstrap?.user.id ?? '')
const canWrite = computed(() => app.can('deal:write'))
const canMutateOpportunity = computed(() => canWrite.value && !selected.value?.siteRestricted)
const canDelete = computed(() => app.bootstrap?.user.role === 'Manager')
const stage = computed(() => selected.value?.stage ?? '')
const liveBooking = computed(() => selected.value?.liveBooking ?? null)
const internalValidation = computed(() => selected.value?.internalValidation ?? null)
const levelMissing = computed(() => !selected.value?.probabilityLevel)
// Each workflow action belongs to the milestone the Opportunity has reached.
const canConfirmBudget = computed(() => canMutateOpportunity.value && stage.value === 'demo_done')
const canRequestValidation = computed(() => canMutateOpportunity.value
  && stage.value === 'quotation_sent'
  && selected.value?.saleType !== 'Service'
  && internalValidation.value?.status !== 'pending')
const canConfirmPo = computed(() => canMutateOpportunity.value && canConfirmPoAt(stage.value))
// At PO received a Booking cancelled by hand can be replaced; the stage stays.
const canReplaceBooking = computed(() => canMutateOpportunity.value && stage.value === 'po_received' && !liveBooking.value)
const canMarkLost = computed(() => canMutateOpportunity.value && isOpenOpportunityStage(stage.value))
const stageRollbackTargets = computed(() => selected.value ? opportunityRollbackTargets(selected.value.stage, selected.value.lostAtStage) : [])
const rollbackOptions = computed(() => selected.value ? opportunityRollbackOptions(selected.value) : { targets: [], blocker: null })
const canRollback = computed(() => app.can('deal:rollback') && stageRollbackTargets.value.length > 0)
const canReviewValidation = computed(() => app.can('deal:internal_validation_approve'))
// A Sales user can only assign a Booking to themselves.
const lockedBookingOwner = computed(() => app.bootstrap?.user.role === 'Sales' ? currentUserId.value : '')
const defaultBookingOwner = computed(() => lockedBookingOwner.value || selected.value?.owner || currentUserId.value)
const siteDisplay = computed(() => selected.value?.siteRestricted ? t('contacts.ownerOnly') : (selected.value?.site || t('detail.notSpecified')))
async function deleteOpportunity() {
  if (!selected.value || deleting.value || !window.confirm(t('detail.confirmDeleteOpportunity', { title: selected.value.title }))) return
  deleting.value = true
  deleteError.value = ''
  deleteRequestId.value = ''
  try {
    await props.apiClient.deleteStrategyOpportunity(selected.value.id)
    await router.push({ name: 'opportunities' })
  } catch (reason) {
    const mapped = mapRequestError(reason)
    deleteError.value = mapped.localizedMessage ?? mapped.message
    deleteRequestId.value = mapped.requestId
  } finally {
    deleting.value = false
  }
}
const routeOpportunityId = computed(() => typeof route.params.opportunityId === 'string' ? route.params.opportunityId : '')
const contactSites = computed(() => Object.entries(sitesByAccount.value).flatMap(([accountId, sites]) =>
  sites.map((site) => ({ ...site, accountId })),
))
const nextAction = computed(() => selected.value?.actions.find((item) => item.status === 'Open'))
function stanceClass(stance: OpportunityStakeholderStance) {
  if (stance === 'Support') return 'positive'
  if (stance === 'Against') return 'danger'
  return 'warning'
}
let opportunityRequest = 0
let mounted = false
async function loadQuotation(currentRequest: number) {
  quotationId.value = ''
  if (!selected.value || !app.can('quotation:view')) return
  const opportunityId = selected.value.id
  const result = await props.apiClient.listQuotations({ opportunityId, page: 1, pageSize: 1 })
  if (currentRequest !== opportunityRequest || selected.value?.id !== opportunityId) return
  quotationId.value = result.data.items.find((item) => item.opportunityId === opportunityId)?.id ?? ''
}
async function loadRfq(currentRequest: number) {
  rfqId.value = ''
  rfqStatus.value = ''
  if (!selected.value || !app.can('rfq:view')) return
  const opportunityId = selected.value.id
  const result = await props.apiClient.listRfqs({ opportunityId, page: 1, pageSize: 1 })
  if (currentRequest !== opportunityRequest || selected.value?.id !== opportunityId) return
  const rfq = result.data.items.find((item) => item.opportunity.id === opportunityId)
  rfqId.value = rfq?.id ?? ''
  rfqStatus.value = rfq?.status ?? ''
}
async function loadOpportunity() {
  const currentRequest = ++opportunityRequest
  loading.value = true
  error.value = ''
  requestId.value = ''
  denied.value = false
  notFound.value = false
  selected.value = null
  try {
    const result = await props.apiClient.getStrategyOpportunity(routeOpportunityId.value)
    if (currentRequest !== opportunityRequest) return
    selected.value = result.data
    await Promise.all([loadQuotation(currentRequest), loadRfq(currentRequest)])
  } catch (reason) {
    if (currentRequest !== opportunityRequest) return
    const mapped = mapRequestError(reason)
    requestId.value = mapped.requestId
    denied.value = mapped.denied
    notFound.value = reason instanceof CrmApiError && reason.code === 'NOT_FOUND'
    if (!notFound.value) error.value = mapped.localizedMessage ?? mapped.message
  } finally {
    if (currentRequest === opportunityRequest) loading.value = false
  }
}
async function loadReferences() {
  referencesLoading.value = true
  try {
    const accountRowsPromise = readAllPages((page, pageSize) => props.apiClient.listAccounts({ page, pageSize }))
    const contactRowsPromise = app.can('contact:view')
      ? readAllPages((page, pageSize) => props.apiClient.listContacts({ page, pageSize }))
      : Promise.resolve([] as ContactSummaryDto[])
    const [accountRows, contactRows] = await Promise.all([accountRowsPromise, contactRowsPromise])
    accounts.value = accountRows
    contacts.value = contactRows
    if (!app.can('contact:view')) {
      sitesByAccount.value = {}
      return
    }
    sitesByAccount.value = sitesByAccountId(accounts.value, (await props.apiClient.listAccountSites()).data)
  } finally {
    referencesLoading.value = false
  }
}
async function saveOpportunity(input: CreateStrategyOpportunityInput) {
  if (!selected.value) return
  busy.value = true
  modalError.value = ''
  try {
    await props.apiClient.updateStrategyOpportunity(selected.value.id, input, selected.value.modified)
    opportunityModal.value = false
    await loadOpportunity()
  } catch (reason) {
    { const mapped = mapRequestError(reason); modalError.value = mapped.localizedMessage ?? mapped.message }
  } finally {
    busy.value = false
  }
}
// Workflow actions send the loaded version, close their modal on success and reload the Opportunity.
async function runOpportunityAction(action: (opportunity: StrategyOpportunityDto) => Promise<unknown>, close: () => void) {
  if (!selected.value || busy.value) return
  busy.value = true
  modalError.value = ''
  try {
    await action(selected.value)
    close()
    await loadOpportunity()
  } catch (reason) {
    const mapped = mapRequestError(reason)
    modalError.value = mapped.localizedMessage ?? mapped.message
  } finally {
    busy.value = false
  }
}
function openBudgetModal() {
  modalError.value = ''
  budgetModal.value = true
}
function confirmBudget(input: ConfirmBudgetApprovedInput) {
  return runOpportunityAction(
    (opportunity) => props.apiClient.confirmBudgetApproved(opportunity.id, input, opportunity.modified),
    () => { budgetModal.value = false },
  )
}
function openValidationRequest() {
  modalError.value = ''
  bookingContactId.value = ''
  validationRequestModal.value = true
}
function requestValidation(input: RequestInternalValidationInput) {
  return runOpportunityAction(
    (opportunity) => props.apiClient.requestInternalValidation(opportunity.id, input, opportunity.modified),
    () => { validationRequestModal.value = false },
  )
}
function openPoModal(mode: 'confirm' | 'replace') {
  modalError.value = ''
  bookingContactId.value = ''
  poModal.value = mode
}
function confirmPo(input: ConfirmPoInput) {
  return runOpportunityAction(
    (opportunity) => props.apiClient.confirmPo(opportunity.id, input, opportunity.modified),
    () => { poModal.value = null },
  )
}
async function reviewValidation(input: Omit<ReviewInternalValidationInput, 'validationId'>) {
  if (!selected.value || !internalValidation.value || busy.value) return
  busy.value = true
  validationError.value = ''
  try {
    await props.apiClient.reviewInternalValidation(
      selected.value.id,
      { ...input, validationId: internalValidation.value.id },
      selected.value.modified,
    )
    await loadOpportunity()
  } catch (reason) {
    const mapped = mapRequestError(reason)
    validationError.value = mapped.localizedMessage ?? mapped.message
  } finally {
    busy.value = false
  }
}
function openLostModal() {
  lostReason.value = selected.value?.lostReason ?? ''
  modalError.value = ''
  lostModal.value = true
}
async function markLost() {
  const reason = lostReason.value.trim()
  if (!reason) {
    modalError.value = localeMessage('Enter a lost reason', '请填写丢单原因')
    return
  }
  await runOpportunityAction(
    (opportunity) => props.apiClient.markOpportunityLost(opportunity.id, { lostReason: reason }, opportunity.modified),
    () => { lostModal.value = false },
  )
}
function openRollback() {
  rollbackReason.value = ''
  rollbackTarget.value = rollbackOptions.value.targets.at(-1) ?? ''
  rollbackErrors.value = {}
  modalError.value = ''
  rollbackModal.value = true
}
async function rollbackStage() {
  if (!selected.value || busy.value) return
  rollbackErrors.value = {}
  const reason = rollbackReason.value.trim()
  const target = rollbackTarget.value
  if (!target) rollbackErrors.value.rollbackTarget = locale.value === 'en-US' ? 'Select a rollback stage' : '请选择回退阶段'
  if (!reason) rollbackErrors.value.rollbackReason = locale.value === 'en-US' ? 'Enter a rollback reason' : '请填写阶段回退原因'
  if (!target || !reason) return
  await runOpportunityAction(
    (opportunity) => props.apiClient.rollbackOpportunityStage(opportunity.id, { targetStage: target, reason }, opportunity.modified),
    () => { rollbackModal.value = false },
  )
}
function openStakeholder(stakeholder: OpportunityStakeholderDto | null = null) {
  modalError.value = ''
  selectedContactId.value = stakeholder?.contactId ?? ''
  editingStakeholder.value = stakeholder
  stakeholderModal.value = true
}
async function saveStakeholder(input: CreateOpportunityStakeholderInput) {
  if (!selected.value) return
  busy.value = true
  modalError.value = ''
  try {
    if (editingStakeholder.value) {
      await props.apiClient.updateOpportunityStakeholder(selected.value.id, editingStakeholder.value.id, input)
    } else {
      await props.apiClient.createOpportunityStakeholder(selected.value.id, input)
    }
    stakeholderModal.value = false
    await loadOpportunity()
  } catch (reason) {
    { const mapped = mapRequestError(reason); modalError.value = mapped.localizedMessage ?? mapped.message }
  } finally {
    busy.value = false
  }
}
async function removeStakeholder(stakeholder: OpportunityStakeholderDto) {
  if (!selected.value) return
  busy.value = true
  try {
    await props.apiClient.deleteOpportunityStakeholder(selected.value.id, stakeholder.id)
    await loadOpportunity()
  } catch (reason) {
    { const mapped = mapRequestError(reason); error.value = mapped.localizedMessage ?? mapped.message }
  } finally {
    busy.value = false
  }
}
function openAction(action: OpportunityActionDto | null = null) {
  modalError.value = ''
  editingAction.value = action
  actionModal.value = true
}
async function saveAction(input: CreateOpportunityActionInput) {
  if (!selected.value) return
  busy.value = true
  modalError.value = ''
  try {
    if (editingAction.value) await props.apiClient.updateOpportunityAction(selected.value.id, editingAction.value.id, input)
    else await props.apiClient.createOpportunityAction(selected.value.id, input)
    actionModal.value = false
    await loadOpportunity()
  } catch (reason) {
    { const mapped = mapRequestError(reason); modalError.value = mapped.localizedMessage ?? mapped.message }
  } finally {
    busy.value = false
  }
}
async function removeAction(action: OpportunityActionDto) {
  if (!selected.value) return
  busy.value = true
  try {
    await props.apiClient.deleteOpportunityAction(selected.value.id, action.id)
    await loadOpportunity()
  } catch (reason) {
    { const mapped = mapRequestError(reason); error.value = mapped.localizedMessage ?? mapped.message }
  } finally {
    busy.value = false
  }
}
function openContact() {
  modalError.value = ''
  contactContext.value = 'stakeholder'
  contactAccountId.value = selected.value?.accountId ?? ''
  contactModal.value = true
}
function openBookingContact() {
  modalError.value = ''
  contactContext.value = 'booking'
  contactAccountId.value = selected.value?.accountId ?? ''
  contactModal.value = true
}
async function saveContact(input: CreateContactInput) {
  busy.value = true
  modalError.value = ''
  try {
    const result = await props.apiClient.createContact(input)
    if (contactContext.value === 'booking') bookingContactId.value = result.data.id
    else selectedContactId.value = result.data.id
    await loadReferences()
    contactModal.value = false
  } catch (reason) {
    { const mapped = mapRequestError(reason); modalError.value = mapped.localizedMessage ?? mapped.message }
  } finally {
    busy.value = false
  }
}

watch(routeOpportunityId, async () => {
  if (mounted) await loadOpportunity()
})
onMounted(async () => {
  try {
    await app.loadBootstrap(props.apiClient)
    mounted = true
    await Promise.all([loadOpportunity(), loadReferences()])
  } catch (reason) {
    const mapped = mapRequestError(reason)
    error.value = mapped.localizedMessage ?? mapped.message
    requestId.value = mapped.requestId
    denied.value = mapped.denied
    loading.value = false
  }
})
</script>

<template>
  <div class="opportunity-detail-page">
    <DataState v-if="loading" type="loading" :title="locale === 'en-US' ? 'Loading Opportunity' : '正在读取 Opportunity'" />
    <section v-else-if="notFound" class="detail-state">{{ locale === 'en-US' ? 'Opportunity not found.' : '未找到指定 Opportunity。' }}</section>
    <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
    <DataState v-else-if="error && !selected" type="error" :message="error" :request-id="requestId" @retry="loadOpportunity" />
    <section v-else-if="!selected" class="detail-state">{{ locale === 'en-US' ? 'Opportunity not found.' : '未找到指定 Opportunity。' }}</section>
    <template v-else>
      <header class="opportunity-record-header">
        <RouterLink class="back-opportunities detail-back-button" data-testid="back-opportunities" :to="{ name: 'opportunities' }"><ArrowLeft :size="15" />{{ t('detail.backOpportunities') }}</RouterLink>
        <div class="record-identity">
          <span><Target :size="22" /></span>
          <div><small>Opportunity · {{ selected.id }}</small><h1>{{ selected.title }}</h1><p>{{ selected.account }} · {{ siteDisplay }}</p></div>
        </div>
        <div class="record-actions">
          <RouterLink v-if="quotationId" class="secondary-button" data-testid="opportunity-quotation-link" :to="{ name: 'quotation-detail', params: { quotationId } }"><FileText :size="14" />{{ t('detail.viewQuotation') }}</RouterLink>
          <RouterLink v-else-if="app.can('quotation:write') && canMutateOpportunity && canWorkQuotationAt(selected.stage)" class="secondary-button" data-testid="create-quotation-from-opportunity" :to="{ name: 'quotations', query: { opportunityId: selected.id } }"><FileText :size="14" />{{ t('detail.newQuotation') }}</RouterLink>
          <RouterLink v-if="rfqId" class="secondary-button" data-testid="opportunity-rfq-link" :to="{ name: 'rfq-detail', params: { rfqId } }"><FileText :size="14" />RFQ · {{ salesEnumLabel(rfqStatus, locale) }}</RouterLink>
          <RouterLink v-else-if="app.can('rfq:view') && canCreateRfqAt(selected.stage)" class="secondary-button" data-testid="opportunity-rfq-center-link" :to="{ name: 'rfqs', query: { opportunityId: selected.id } }"><FileText :size="14" />{{ t('detail.rfqNotCreated') }}</RouterLink>
          <RouterLink v-if="liveBooking" class="secondary-button" data-testid="opportunity-booking-link" :to="{ name: 'booking-detail', params: { bookingId: liveBooking.id } }"><PackageCheck :size="14" />Booking · {{ liveBooking.id }} · {{ salesEnumLabel(liveBooking.status, locale) }}</RouterLink>
          <button v-if="canWrite" class="secondary-button" type="button" data-testid="new-opportunity-action" @click="openAction()"><Plus :size="14" />{{ t('detail.newAction') }}</button>
          <button v-if="canMutateOpportunity" class="primary-button" type="button" data-testid="edit-opportunity" @click="opportunityModal = true"><Pencil :size="14" />{{ t('detail.edit') }}</button>
          <button v-if="canMarkLost" class="secondary-button lost-action-button" type="button" data-testid="mark-opportunity-lost" @click="openLostModal">{{ t('detail.markLost') }}</button>
          <button v-if="canDelete" class="secondary-button" type="button" data-delete-opportunity :disabled="deleting" @click="deleteOpportunity">{{ t('detail.delete') }}</button>
        </div>
      </header>
      <p v-if="deleteError" class="inline-error" data-delete-error>{{ deleteError }}<small v-if="deleteRequestId">{{ locale === 'en-US' ? 'Request ID' : '请求编号' }} {{ deleteRequestId }}</small></p>

      <section class="opportunity-path" :aria-label="t('detail.stagePath')">
        <div class="path-scroll"><OpportunityMilestoneBar :opportunity="selected" /></div>
        <span v-if="selected.stage === 'lost'" class="lost-outcome" data-testid="opportunity-lost-outcome">{{ opportunityStageLabel('lost', locale) }}</span>
        <div v-if="canConfirmBudget || canRequestValidation || canConfirmPo || canReplaceBooking || canRollback" class="path-actions">
          <button v-if="canConfirmBudget" class="path-primary" type="button" data-testid="confirm-budget-approved" :disabled="busy" @click="openBudgetModal"><ClipboardCheck :size="14" />{{ t('detail.confirmBudget') }}</button>
          <button v-if="canRequestValidation" class="path-secondary" type="button" data-testid="request-internal-validation" :disabled="busy" @click="openValidationRequest"><ShieldCheck :size="14" />{{ t('detail.requestInternalValidation') }}</button>
          <button v-if="canConfirmPo" class="path-primary" type="button" data-testid="confirm-po" :disabled="busy" @click="openPoModal('confirm')"><FileCheck2 :size="14" />{{ t('detail.confirmPo') }}</button>
          <button v-if="canReplaceBooking" class="path-primary" type="button" data-testid="replace-booking" :disabled="busy" @click="openPoModal('replace')"><PackageCheck :size="14" />{{ t('detail.replaceBooking') }}</button>
          <button v-if="canRollback" class="path-secondary" type="button" data-testid="rollback-opportunity-stage" :disabled="busy" @click="openRollback"><RotateCcw :size="14" />{{ t('detail.stageRollback') }}</button>
        </div>
      </section>

      <p v-if="error" class="inline-error">{{ error }}</p>

      <main class="opportunity-detail-grid" data-testid="selected-opportunity">
        <div class="detail-column detail-left">
          <section class="detail-card">
            <header><Building2 :size="16" /><h2>{{ t('detail.about') }}</h2></header>
            <dl class="field-list">
              <div><dt>{{ t('detail.opportunityName') }}</dt><dd>{{ selected.title }}</dd></div>
              <div><dt>{{ t('detail.accountNameField') }}</dt><dd>{{ selected.account }}</dd></div>
              <div><dt>{{ t('detail.site') }}</dt><dd>{{ siteDisplay }}</dd></div>
              <div><dt>{{ t('detail.closeDate') }}</dt><dd>{{ formatDisplayDate(selected.poDate) }}</dd></div>
              <div><dt>{{ t('detail.amount') }}</dt><dd data-testid="opportunity-amount" :class="{ 'pending-value': !selected.amount }">{{ selected.amount ? formatMoney(selected.amount, selected.currency) : t('oppEditor.amountPending') }}</dd></div>
              <div><dt>{{ t('oppEditor.amountCny') }}</dt><dd data-testid="opportunity-amount-cny" :class="{ 'pending-value': !selected.amountCny }">{{ selected.amountCny ? formatMoney(selected.amountCny, 'CNY') : t('oppEditor.amountCnyPending') }}</dd></div>
              <div><dt>{{ t('detail.opportunityOwner') }}</dt><dd>{{ personnelDisplayName(selected.owner) }}</dd></div>
              <div><dt>{{ t('detail.toolSaleType') }}</dt><dd>{{ systemValueLabel(selected.toolType, locale) }} · {{ salesEnumLabel(selected.saleType, locale) }}</dd></div>
            </dl>
          </section>

          <section class="detail-card">
            <header><Target :size="16" /><h2>{{ t('detail.status') }}</h2></header>
            <dl class="field-list">
              <div><dt>{{ t('oppEditor.stage') }}</dt><dd data-testid="opportunity-stage"><StatusBadge :label="opportunityStageLabel(selected.stage, locale)" :tone="opportunityStageTone(selected.stage)" /><small v-if="selected.pendingStageAdvance === 'demo_done' && selected.stage === 'qualified_opportunity'" class="pending-stage-note" data-testid="opportunity-pending-demo-done">{{ t(selected.currency === 'CNY' ? 'oppEditor.pendingDemoDone' : 'oppEditor.pendingDemoDoneForeign') }}</small></dd></div>
              <div v-if="selected.stageChangedAt"><dt>{{ t('detail.stageChangedAt') }}</dt><dd>{{ formatDisplayDateTime(selected.stageChangedAt) }}</dd></div>
              <div v-if="selected.budgetApprovedOn"><dt>{{ t('detail.budgetApprovedOn') }}</dt><dd data-testid="opportunity-budget-approved-on">{{ formatDisplayDate(selected.budgetApprovedOn) }}</dd></div>
              <div><dt>{{ t('oppEditor.probabilityLevel') }}</dt><dd data-testid="opportunity-probability-level"><StatusBadge :label="opportunityProbabilityLevelLabel(selected.probabilityLevel, locale)" :tone="opportunityProbabilityLevelTone(selected.probabilityLevel)" /></dd></div>
              <div><dt>{{ t('detail.purchaseIntent') }}</dt><dd data-testid="opportunity-intent">{{ selected.score }}/100</dd></div>
              <div><dt>{{ t('detail.nextStep') }}</dt><dd>{{ nextAction?.title || t('detail.noOpenAction') }}</dd></div>
              <div><dt>{{ t('detail.updated') }}</dt><dd>{{ formatDisplayDate(selected.updated) }}</dd></div>
            </dl>
          </section>

          <InternalValidationPanel
            v-if="internalValidation"
            :validation="internalValidation"
            :stage="selected.stage"
            :current-user-id="currentUserId"
            :can-review="canReviewValidation"
            :busy="busy"
            :error="validationError"
            @review="reviewValidation"
          />

          <OpportunityStageTimeline :history="selected.stageHistory" />

        <ProbabilityRecoveryPanel :opportunity="selected" :api-client="apiClient" :highlight-event-id="typeof route.query.probabilityEvent === 'string' ? route.query.probabilityEvent : undefined" @updated="selected = $event" @denied="selected = null; denied = true; opportunityRequest++" />
        <LossReviewCard :opportunity="selected" />
        </div>
        <section class="opportunity-strategy-shell" data-testid="blue-sheet">
          <header class="strategy-shell-header">
            <Target :size="16" />
            <h2 data-testid="blue-sheet-title">{{ locale === 'en-US' ? 'Blue Sheet' : '战略分析' }}</h2>
          </header>
          <div class="strategy-shell-grid">

        <div class="detail-column detail-center">
          <OpportunityStatusCard :key="selected.id" :opportunity-id="selected.id" :api-client="apiClient" :can-write="canWrite" />
          <section class="detail-card action-card">
            <header><div><CircleDollarSign :size="16" /><h2>{{ t('detail.actionPlan') }}</h2></div><button v-if="canWrite" type="button" @click="openAction()"><Plus :size="13" />{{ t('detail.new') }}</button></header>
            <div v-if="selected.actions.length" class="activity-list">
              <article v-for="action in selected.actions" :key="action.id" :data-action-title="action.title">
                <i :class="{ done: action.status === 'Done' }"></i>
                <div><strong>{{ action.title }}</strong><span>{{ personnelDisplayName(action.owner) }} · {{ t('actionEditor.dueDate') }} {{ formatDisplayDate(action.due) }}</span><p v-if="action.remark" class="action-remark">{{ t('actionEditor.remark') }} · {{ action.remark }}</p></div>
                <b :class="{ done: action.status === 'Done' }">{{ salesEnumLabel(action.status, locale) }}</b>
                <div v-if="canWrite" class="compact-actions"><button type="button" data-action="edit" :aria-label="locale === 'en-US' ? 'Edit action' : '编辑 Action'" @click="openAction(action)"><Pencil :size="12" /></button><button type="button" data-action="delete" :aria-label="locale === 'en-US' ? 'Delete action' : '删除 Action'" @click="removeAction(action)"><Trash2 :size="12" /></button></div>
              </article>
            </div>
            <p v-else class="empty-copy">{{ t('detail.noActivity') }}</p>
          </section>

          <section class="detail-card commercial-card">
            <header><CircleDollarSign :size="16" /><h2>{{ t('detail.commercialForecast') }}</h2></header>
            <div class="commercial-grid">
              <div><small>{{ t('oppEditor.currency') }} / {{ t('oppEditor.originalAmount') }}</small><strong data-testid="opportunity-original-amount">{{ selected.originalAmount ? formatMoney(selected.originalAmount, selected.currency) : t('oppEditor.amountPending') }}</strong></div>
              <div><small>{{ t('oppEditor.shipmentDate') }} / {{ t('oppEditor.fatDate') }}</small><strong>{{ formatDisplayDate(selected.shipmentDate) }} · {{ formatDisplayDate(selected.fatDate) }}</strong></div>
              <div><small>{{ t('oppEditor.payment') }}</small><strong>{{ selected.paymentMilestones.join(' · ') }}</strong></div>
              <div><small>{{ t('oppEditor.competition') }}</small><strong>{{ selected.competition }}</strong></div>
              <div class="wide" data-testid="single-sales-objective"><small>{{ t('oppEditor.singleSalesObjective') }}</small><strong class="objective-text">{{ selected.singleSalesObjective || t('detail.notSet') }}</strong></div>
              <div v-if="selected.stage === 'lost'" class="wide lost-reason-field"><small>{{ t('detail.lostReason') }}</small><strong>{{ selected.lostReason || (locale === 'en-US' ? 'Not provided' : '未填写') }}</strong></div>
              <div v-else class="wide"><small>{{ locale === 'en-US' ? 'Win reason' : '赢单原因' }}</small><strong>{{ selected.winReason || (locale === 'en-US' ? 'Pending confirmation' : '待确认') }}</strong></div>
            </div>
          </section>
          <section v-if="selected.stage === 'lost'" class="detail-card lost-detail-card" data-testid="lost-detail">
            <header><h2>{{ t('detail.lostInfo') }}</h2><span>{{ t('detail.closed') }}</span></header>
            <dl class="field-list">
              <div><dt>{{ t('detail.lostReason') }}</dt><dd>{{ selected.lostReason || (locale === 'en-US' ? 'Not provided' : '未填写') }}</dd></div>
              <div><dt>{{ t('detail.lostAtStage') }}</dt><dd data-testid="lost-at-stage">{{ selected.lostAtStage ? opportunityStageLabel(selected.lostAtStage, locale) : (locale === 'en-US' ? 'Not recorded' : '未记录') }}</dd></div>
              <div><dt>{{ t('detail.setBy') }}</dt><dd>{{ selected.lostBy ? personnelDisplayName(selected.lostBy) : (locale === 'en-US' ? 'Not recorded' : '未记录') }}</dd></div>
              <div><dt>{{ t('detail.setAt') }}</dt><dd>{{ selected.lostAt ? formatDisplayDateTime(selected.lostAt) : (locale === 'en-US' ? 'Not recorded' : '未记录') }}</dd></div>
            </dl>
          </section>
        </div>

        <aside class="detail-column detail-right">
          <section class="detail-card influence-card">
            <header><div><Users :size="16" /><h2>{{ t('detail.buyingInfluence') }}</h2></div><button v-if="canWrite" type="button" data-testid="new-opportunity-stakeholder" @click="openStakeholder()"><Plus :size="13" />{{ t('detail.new') }}</button></header>
            <div class="influence-list">
              <article v-for="person in selected.stakeholders" :key="person.id" :data-stakeholder-name="person.name">
                <RouterLink class="record-link" :to="{ name: 'contact-detail', params: { contactId: person.contactId } }"><strong>{{ person.name }}</strong><span>{{ person.title }}</span></RouterLink>
                <small>{{ salesEnumLabel(person.role, locale) }} · {{ salesEnumLabel(person.influence, locale) }}<template v-if="person.responseMode"> · {{ t('detail.responseModeValue', { mode: salesEnumLabel(person.responseMode, locale) }) }}</template></small>
                <b :class="stanceClass(person.stance)">{{ salesEnumLabel(person.stance, locale) }}</b>
                <p>{{ systemValueLabel(person.coverage, locale) }}</p>
                <div v-if="canWrite" class="compact-actions"><button type="button" data-action="edit" :aria-label="locale === 'en-US' ? 'Edit stakeholder' : '编辑关键人'" @click="openStakeholder(person)"><Pencil :size="12" /></button><button type="button" data-action="delete" :aria-label="locale === 'en-US' ? 'Delete stakeholder' : '删除关键人'" @click="removeStakeholder(person)"><Trash2 :size="12" /></button></div>
              </article>
              <p v-if="!selected.stakeholders.length" class="empty-copy">{{ t('detail.noStakeholders') }}</p>
            </div>
          </section>

          <section class="detail-card evidence-card strength-card">
            <header><h2>{{ t('oppEditor.strength') }}</h2><span>{{ selected.strengths.length }}</span></header>
            <ul><li v-for="item in selected.strengths" :key="item">{{ item }}</li></ul>
          </section>
          <section class="detail-card evidence-card risk-card">
            <header><h2>{{ t('oppEditor.redFlag') }}</h2><span>{{ selected.redFlags.length }}</span></header>
            <ul><li v-for="item in selected.redFlags" :key="item">{{ item }}</li></ul>
          </section>
          <section class="detail-card evidence-card competitor-card" data-testid="opportunity-competitors">
            <header><h2>{{ t('oppEditor.competitors') }}</h2><span>{{ selected.competitors?.length ?? 0 }}</span></header>
            <div v-if="selected.competitors?.length" class="competitor-list">
              <article v-for="row in selected.competitors" :key="row.name" :data-competitor-name="row.name">
                <strong>{{ row.name }}</strong>
                <p v-if="row.strengths" data-competitor-field="strengths"><small>{{ t('oppEditor.competitorStrengths') }}</small>{{ row.strengths }}</p>
                <p v-if="row.response" data-competitor-field="response"><small>{{ t('oppEditor.competitorResponse') }}</small>{{ row.response }}</p>
              </article>
            </div>
            <p v-else class="empty-copy">{{ t('oppEditor.noCompetitors') }}</p>
          </section>
          <section class="detail-card evidence-card information-card">
            <header><h2>{{ t('oppEditor.infoNeeded') }}</h2><span>{{ selected.informationNeeded.length }}</span></header>
            <ul><li v-for="item in selected.informationNeeded" :key="item">{{ item }}</li></ul>
          </section>
        </aside>
          </div>
        </section>
      </main>

      <OpportunityEditorModal v-if="opportunityModal && canMutateOpportunity" :opportunity="selected" :accounts="accounts" :sites-by-account="sitesByAccount" :equipment-types="equipmentTypes" :default-owner="currentUserId" :current-user-id="currentUserId" :references-loading="referencesLoading" :busy="busy" :error="modalError" @close="opportunityModal = false" @submit="saveOpportunity" />
      <StakeholderEditorModal v-if="stakeholderModal && selected" :stakeholder="editingStakeholder" :contacts="contacts" :account-id="selected.accountId" :selected-contact-id="selectedContactId" :busy="busy" :error="modalError" @close="stakeholderModal = false" @create-contact="openContact" @submit="saveStakeholder" />
      <ContactModal v-if="contactModal" :accounts="accounts" :sites="contactSites" :contacts="contacts" :fixed-account-id="contactAccountId" :busy="busy" :error="modalError" @close="contactModal = false" @submit="saveContact" />
      <ActionEditorModal v-if="actionModal" :action="editingAction" :default-owner="currentUserId" :busy="busy" :error="modalError" @close="actionModal = false" @submit="saveAction" />
      <BudgetApprovalModal v-if="budgetModal" :busy="busy" :error="modalError" :level-missing="levelMissing" @close="budgetModal = false" @submit="confirmBudget" />
      <InternalValidationRequestModal
        v-if="validationRequestModal"
        :opportunity="selected"
        :contacts="contacts"
        :selected-contact-id="bookingContactId"
        :default-owner="defaultBookingOwner"
        :locked-owner="lockedBookingOwner"
        :busy="busy"
        :error="modalError"
        @close="validationRequestModal = false"
        @create-contact="openBookingContact"
        @submit="requestValidation"
      />
      <PoConfirmationModal
        v-if="poModal"
        :opportunity="selected"
        :contacts="contacts"
        :selected-contact-id="bookingContactId"
        :default-owner="defaultBookingOwner"
        :locked-owner="lockedBookingOwner"
        :replacing="poModal === 'replace'"
        :busy="busy"
        :error="modalError"
        @close="poModal = null"
        @create-contact="openBookingContact"
        @submit="confirmPo"
      />
      <ModalShell v-if="lostModal" :title="t('detail.markLostTitle')" eyebrow="OPPORTUNITY RESULT" :busy="busy" :submit-disabled="Boolean(liveBooking)" @close="lostModal = false" @submit="markLost">
        <p v-if="modalError" class="form-error">{{ modalError }}</p>
        <p v-if="liveBooking" class="form-warning" data-testid="lost-blocked-by-booking">{{ t('detail.lostBlockedBooking') }}</p>
        <div class="lost-form">
          <p>{{ locale === 'en-US' ? 'Current account: ' : '当前账号：' }}{{ app.bootstrap?.user.name || app.bootstrap?.user.id || (locale === 'en-US' ? 'Current user' : '当前登录用户') }}{{ locale === 'en-US' ? ' (' : '（' }}{{ app.bootstrap?.user.role || (locale === 'en-US' ? 'Unknown role' : '未知角色') }}{{ locale === 'en-US' ? ')' : '）' }}</p>
          <label><span>{{ t('detail.lostReason') }}<RequiredMark /></span><textarea v-model="lostReason" :aria-label="t('detail.lostReason')" rows="4" required :placeholder="locale === 'en-US' ? 'Enter the main reason the customer did not close' : '请填写客户未成交的主要原因'" /></label>
        </div>
      </ModalShell>
      <ModalShell v-if="rollbackModal" :title="t('detail.rollbackOpportunity')" eyebrow="MANAGER CONTROL" :busy="busy" :submit-disabled="!rollbackOptions.targets.length" @close="rollbackModal = false" @submit="rollbackStage">
        <p v-if="modalError" class="form-error">{{ modalError }}</p>
        <p v-if="selected.stage === 'lost'" class="form-hint" data-testid="rollback-reopen-hint">{{ t('detail.reopenHint') }}</p>
        <p v-if="rollbackOptions.blocker" class="form-warning" :data-rollback-blocker="rollbackOptions.blocker">{{ rollbackOptions.blocker === 'completed_booking' ? t('detail.rollbackBlockedCompleted') : t('detail.rollbackBlockedBooking') }}</p>
        <div class="rollback-form">
          <label><span>{{ t('detail.targetStage') }}<RequiredMark /></span>
            <select v-model="rollbackTarget" :aria-label="locale === 'en-US' ? 'Rollback stage' : '阶段回退目标'" required>
              <option v-for="target in rollbackOptions.targets" :key="target" :value="target">{{ opportunityStageLabel(target, locale) }}</option>
            </select>
            <small v-if="rollbackErrors.rollbackTarget" data-field-error="rollbackTarget">{{ rollbackErrors.rollbackTarget }}</small>
          </label>
          <label><span>{{ t('detail.rollbackReason') }}<RequiredMark /></span>
            <textarea v-model="rollbackReason" :aria-label="locale === 'en-US' ? 'Rollback reason' : '阶段回退原因'" rows="4" required />
            <small v-if="rollbackErrors.rollbackReason" data-field-error="rollbackReason">{{ rollbackErrors.rollbackReason }}</small>
          </label>
        </div>
      </ModalShell>
    </template>
  </div>
</template>

<style scoped>
.competitor-list{display:grid;padding:8px}.competitor-list article{display:grid;gap:4px;padding:8px 10px;border-bottom:1px solid var(--crm-line)}.competitor-list article:last-child{border-bottom:0}.competitor-list strong{color:var(--crm-text);font-size:10px;overflow-wrap:anywhere}.competitor-list p{margin:0;color:var(--crm-text);font-size:9px;line-height:1.5;white-space:pre-wrap;overflow-wrap:anywhere}.competitor-list small{display:block;color:var(--crm-text-muted);font-size:8px}
.objective-text{white-space:pre-wrap;overflow-wrap:anywhere}
.action-remark{margin:7px 0 0;color:var(--crm-text-muted);font-size:9px;line-height:1.6;white-space:pre-wrap;overflow-wrap:anywhere}
.opportunity-detail-page{display:grid;gap:14px}.detail-state{padding:28px;color:var(--crm-text-muted);background:#fff;border:1px solid var(--crm-line);border-radius:12px}.opportunity-record-header{display:grid;grid-template-columns:1fr auto;gap:10px 18px;align-items:end}.back-opportunities{grid-column:1/-1;display:inline-flex;width:fit-content;align-items:center;gap:6px;color:var(--crm-teal);font-size:10px;font-weight:800}.record-identity{display:flex;align-items:center;gap:12px}.record-identity>span{display:grid;width:46px;height:46px;place-items:center;color:var(--crm-brand-ink);background:var(--crm-brand-soft);border-radius:13px}.record-identity small{color:var(--crm-text-muted);font-size:9px}.record-identity h1{margin:2px 0 3px;color:var(--crm-navy);font-size:clamp(23px,2.3vw,32px);letter-spacing:-.03em}.record-identity p{margin:0;color:var(--crm-text-muted);font-size:10px}.record-actions{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:7px}.record-actions button,.record-actions a{display:flex;align-items:center;gap:6px}.inline-error{margin:0;padding:10px 12px;color:var(--crm-danger);background:var(--crm-danger-soft);border:1px solid rgba(200,78,78,.2);border-radius:9px;font-size:10px}.opportunity-detail-grid{display:grid;grid-template-columns:minmax(260px,.78fr) minmax(0,2.22fr);gap:14px;align-items:start}.opportunity-strategy-shell{min-width:0;overflow:hidden;background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:12px}.strategy-shell-header{display:flex;min-height:50px;align-items:center;gap:8px;padding:0 14px;color:var(--crm-teal);background:#fff;border-bottom:1px solid var(--crm-line)}.strategy-shell-header h2{margin:0;color:var(--crm-navy);font-size:13px}.strategy-shell-grid{display:grid;grid-template-columns:minmax(0,1.34fr) minmax(230px,.88fr);gap:14px;padding:14px;align-items:start}.detail-column{display:grid;gap:14px}.detail-card{overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:12px;box-shadow:0 8px 24px rgba(31,35,41,.035)}.detail-card>header{display:flex;min-height:50px;align-items:center;gap:8px;padding:0 14px;background:#faf9f7;border-bottom:1px solid var(--crm-line)}.detail-card>header>div{display:flex;align-items:center;gap:8px}.detail-card>header h2{margin:0;color:var(--crm-navy);font-size:12px}.detail-card>header>span{margin-left:auto;color:var(--crm-text-muted);font-size:9px}.detail-card>header button{display:flex;align-items:center;gap:4px;margin-left:auto;padding:6px 8px;color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line);border-radius:7px;font:inherit;font-size:8px;font-weight:800;cursor:pointer}.field-list{display:grid;margin:0;padding:2px 14px 10px}.field-list>div{display:grid;gap:4px;padding:10px 0;border-bottom:1px solid var(--crm-line)}.field-list>div:last-child{border-bottom:0}.field-list dt{color:var(--crm-text-muted);font-size:8px;font-weight:700}.field-list dd{margin:0;color:var(--crm-text);font-size:10px;line-height:1.45}.field-list dd.pending-value{color:var(--crm-text-muted)}.activity-list{display:grid}.activity-list article{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;align-items:center;gap:9px;padding:12px 14px;border-bottom:1px solid var(--crm-line)}.activity-list article:last-child{border-bottom:0}.activity-list i{width:10px;height:10px;border:2px solid var(--crm-warning);border-radius:50%}.activity-list i.done{background:var(--crm-positive);border-color:var(--crm-positive)}.activity-list article>div:nth-child(2){display:grid;gap:4px}.activity-list strong{color:var(--crm-text);font-size:10px}.activity-list span{color:var(--crm-text-muted);font-size:8px}.activity-list article>b{padding:4px 7px;color:#8a651d;background:var(--crm-warning-soft);border-radius:999px;font-size:7px}.activity-list article>b.done{color:var(--crm-positive-ink);background:#e8f5ed}.compact-actions{display:flex!important;gap:4px!important}.compact-actions button{display:grid;width:25px;height:25px;place-items:center;padding:0;color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line);border-radius:6px;cursor:pointer}.compact-actions button:last-child{color:var(--crm-danger)}.empty-copy{margin:0;padding:22px;color:var(--crm-text-muted);font-size:9px;text-align:center}.commercial-grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--crm-line)}.commercial-grid>div{display:grid;gap:5px;padding:13px;background:#fff}.commercial-grid .wide{grid-column:1/-1}.commercial-grid small,.commercial-grid span{color:var(--crm-text-muted);font-size:8px}.commercial-grid strong{color:var(--crm-text);font-size:9px;line-height:1.45}.influence-list{display:grid;padding:8px}.influence-list article{position:relative;display:grid;gap:5px;padding:10px 62px 10px 10px;border-bottom:1px solid var(--crm-line)}.influence-list article:last-child{border-bottom:0}.influence-list a{display:grid;gap:3px;color:var(--crm-teal)}.influence-list a strong{font-size:10px}.influence-list a span,.influence-list small,.influence-list p{color:var(--crm-text-muted);font-size:8px}.influence-list p{margin:0;line-height:1.45}.influence-list article>b{position:absolute;top:10px;right:10px;padding:4px 6px;border-radius:999px;font-size:7px}.influence-list article>b.positive{color:var(--crm-positive-ink);background:#e8f5ed}.influence-list article>b.warning{color:#8a651d;background:var(--crm-warning-soft)}.influence-list article>b.danger{color:var(--crm-danger);background:var(--crm-danger-soft)}.influence-list .compact-actions{position:absolute;right:8px;bottom:9px}.evidence-card ul{display:grid;gap:8px;margin:0;padding:13px 16px 15px 29px}.evidence-card li{color:var(--crm-text);font-size:9px;line-height:1.5}.strength-card li::marker{color:var(--crm-positive)}.risk-card li::marker{color:var(--crm-danger)}.information-card li::marker{color:var(--crm-warning)}@media(max-width:1180px){.opportunity-detail-grid{grid-template-columns:minmax(250px,.8fr) minmax(0,1.2fr)}.strategy-shell-grid{grid-template-columns:1fr}.detail-right{grid-column:1/-1;grid-template-columns:repeat(3,1fr)}.detail-right .influence-card{grid-column:1/-1}}@media(max-width:780px){.opportunity-record-header{grid-template-columns:1fr}.record-actions{justify-content:flex-start}.opportunity-detail-grid{grid-template-columns:1fr}.detail-right{grid-column:auto;grid-template-columns:1fr}.commercial-grid{grid-template-columns:1fr}.commercial-grid .wide{grid-column:auto}}@media(max-width:520px){.record-identity{align-items:flex-start}.record-identity h1{font-size:22px}.record-actions button,.record-actions a{flex:1;justify-content:center}.strategy-shell-grid{padding:10px}}
.opportunity-path{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:10px 12px;padding:11px 12px;background:#fff;border:1px solid var(--crm-line);border-radius:13px}
.path-scroll{min-width:0;overflow-x:auto}
.pending-stage-note{display:block;margin-top:4px;color:#8a651d;font-size:9px;line-height:1.45}
.lost-outcome{display:flex;min-height:44px;box-sizing:border-box;align-items:center;padding:0 14px;color:#fff;background:var(--crm-danger);border-radius:9px;font-size:10px;font-weight:800;white-space:nowrap}
.path-actions{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:7px;grid-column:1/-1}
.path-actions button{display:flex;min-height:34px;align-items:center;gap:6px;padding:0 12px;border-radius:9px;font:inherit;font-size:9px;font-weight:800;white-space:nowrap;cursor:pointer}
.path-actions .path-primary{color:var(--crm-brand-ink);background:var(--crm-brand);border:1px solid var(--crm-brand)}
.path-actions .path-secondary{color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line)}
.path-actions button:disabled{color:var(--crm-text-muted);background:var(--crm-surface-muted);border-color:var(--crm-line);cursor:not-allowed}
.rollback-form{display:grid;gap:13px}.rollback-form label{display:grid;gap:6px;color:var(--crm-text-muted);font-size:9px;font-weight:700}.rollback-form select,.rollback-form textarea{box-sizing:border-box;width:100%;padding:9px 10px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.rollback-form small{color:var(--crm-danger)}.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:9px}
.form-warning{margin:0 0 12px;padding:9px 10px;color:#8a651d;background:var(--crm-warning-soft);border-radius:8px;font-size:9px;line-height:1.5}
.form-hint{margin:0 0 12px;color:var(--crm-text-muted);font-size:9px;line-height:1.5}
.lost-reason-field{background:#fff5f2!important}
.lost-reason-field strong{color:var(--crm-danger)!important}
.lost-action-button{color:var(--crm-danger)!important;border-color:rgba(200,78,78,.35)!important}
.lost-detail-card{border-color:rgba(200,78,78,.35)}
.lost-detail-card>header{background:#fff5f2}
.lost-detail-card>header h2,.lost-detail-card>header span{color:var(--crm-danger)}
.probability-history-list{display:grid;margin:0;padding:2px 14px 10px;list-style:none}
.probability-history-list li{display:grid;gap:4px;padding:10px 0;border-bottom:1px solid var(--crm-line)}
.probability-history-list li:last-child{border-bottom:0}
.probability-history-list strong{color:var(--crm-text);font-size:10px}
.probability-history-list span{color:var(--crm-text-muted);font-size:8px}
.lost-form{display:grid;gap:13px}.lost-form>p{margin:0;padding:9px 10px;color:var(--crm-text-muted);background:var(--crm-surface-muted);border-radius:8px;font-size:9px}.lost-form label{display:grid;gap:6px;color:var(--crm-text-muted);font-size:9px;font-weight:700}.lost-form textarea{box-sizing:border-box;width:100%;padding:9px 10px;border:1px solid var(--crm-line);border-radius:8px;font:inherit;resize:vertical}
@media(max-width:780px){.opportunity-path{grid-template-columns:1fr}.path-actions{justify-content:stretch}.path-actions button{flex:1;justify-content:center}}
</style>
