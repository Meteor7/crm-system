<script setup lang="ts">
import { personnelDisplayName } from '@/demo/personnel'
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft, Building2, Check, CircleDollarSign, FileText, PackageCheck, Pencil, Plus, Target, Trash2, Users } from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import { api as defaultApi, CrmApiError, type CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import DataState from '@/design-system/DataState.vue'
import ModalShell from '@/design-system/ModalShell.vue'
import { opportunityProbabilityExplanation } from '@/domain/opportunity-probability'
import ContactModal from '@/features/contacts/ContactModal.vue'
import ActionEditorModal from '@/features/opportunities/ActionEditorModal.vue'
import OpportunityEditorModal from '@/features/opportunities/OpportunityEditorModal.vue'
import StakeholderEditorModal from '@/features/opportunities/StakeholderEditorModal.vue'
import BookingEditorModal from '@/features/opportunities/BookingEditorModal.vue'
import { useAppStore } from '@/stores/app'
import type { AccountSummaryDto, BookingDto, ContactSummaryDto, CreateContactInput, SiteDto, UpsertBookingInput } from '@/types/crm'
import { STRATEGY_OPPORTUNITY_STAGES, type CreateOpportunityActionInput, type CreateOpportunityStakeholderInput, type CreateStrategyOpportunityInput, type OpportunityActionDto, type OpportunityStakeholderDto, type OpportunityStakeholderStance, type StrategyOpportunityDto } from '@/types/workspaces'
import { formatMoney } from '@/domain/money'
import { formatDisplayDate } from '@/domain/time'
import { readAllPages } from '@/features/shared/read-all-pages'

const OPPORTUNITY_STAGES = STRATEGY_OPPORTUNITY_STAGES

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const app = useAppStore()
const route = useRoute()
const router = useRouter()
const selected = ref<StrategyOpportunityDto | null>(null)
const bookings = ref<BookingDto[]>([])
const quotationId = ref('')
const rfqId = ref('')
const rfqStatus = ref('')
const accounts = ref<AccountSummaryDto[]>([])
const contacts = ref<ContactSummaryDto[]>([])
const sitesByAccount = ref<Record<string, SiteDto[]>>({})
const loading = ref(true)
const error = ref('')
const requestId = ref('')
const denied = ref(false)
const notFound = ref(false)
const busy = ref(false)
const modalError = ref('')
const opportunityModal = ref(false)
const stakeholderModal = ref(false)
const actionModal = ref(false)
const contactModal = ref(false)
const bookingModal = ref(false)
const lostModal = ref(false)
const lostReason = ref('')
const rollbackModal = ref(false)
const rollbackReason = ref('')
const rollbackTarget = ref('')
const rollbackErrors = ref<Record<string, string>>({})
const deleting = ref(false), deleteError = ref(''), deleteRequestId = ref('')
const editingStakeholder = ref<OpportunityStakeholderDto | null>(null)
const editingAction = ref<OpportunityActionDto | null>(null)
const selectedContactId = ref('')
const bookingContactId = ref('')
const contactAccountId = ref('')
const contactContext = ref<'stakeholder' | 'booking'>('stakeholder')
const canWrite = computed(() => app.can('deal:write'))
const canDelete = computed(() => app.bootstrap?.user.role === 'Manager')
const canMarkLost = computed(() => canWrite.value && Boolean(selected.value) && !['Won', 'Lost'].includes(selected.value?.stage ?? ''))
const lostHistory = computed(() => selected.value?.history.find((item) => item.field === 'stage' && item.to === 'Lost'))
async function deleteOpportunity() {
  if (!selected.value || deleting.value || !window.confirm(`确认删除 Opportunity ${selected.value.title}？`)) return
  deleting.value = true
  deleteError.value = ''
  deleteRequestId.value = ''
  try {
    await props.apiClient.deleteStrategyOpportunity(selected.value.id)
    await router.push({ name: 'opportunities' })
  } catch (reason) {
    const mapped = mapRequestError(reason)
    deleteError.value = mapped.message
    deleteRequestId.value = mapped.requestId
  } finally {
    deleting.value = false
  }
}
const routeOpportunityId = computed(() => typeof route.params.opportunityId === 'string' ? route.params.opportunityId : '')
const contactSites = computed(() => Object.entries(sitesByAccount.value).flatMap(([accountId, sites]) =>
  sites.map((site) => ({ ...site, accountId })),
))
const currentStageIndex = computed(() => {
  if (!selected.value) return -1
  return OPPORTUNITY_STAGES.indexOf(selected.value.stage as typeof OPPORTUNITY_STAGES[number])
})
const nextStage = computed(() => {
  if (!selected.value || selected.value.stage === 'Lost' || currentStageIndex.value < 0) return ''
  return OPPORTUNITY_STAGES[currentStageIndex.value + 1] ?? ''
})
const canAdvanceManually = computed(() => canWrite.value
  && Boolean(nextStage.value)
  && ['预算审批', '采购流程'].includes(selected.value?.stage ?? ''))
const rollbackTargets = computed(() => OPPORTUNITY_STAGES
  .slice(0, Math.max(0, currentStageIndex.value))
  .filter((stage) => stage !== 'Won' && stage !== 'Lost'))
const canRollback = computed(() => app.can('deal:rollback') && rollbackTargets.value.length > 0)
const nextAction = computed(() => selected.value?.actions.find((item) => item.status === 'Open'))
const probabilityExplanation = computed(() => selected.value
  ? opportunityProbabilityExplanation(selected.value.stage, selected.value.score)
  : '')
const existingBooking = computed(() =>
  bookings.value.find((booking) => booking.sourceOpportunityId === selected.value?.id && booking.status !== 'Cancelled'),
)
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
    if (!notFound.value) error.value = mapped.message
  } finally {
    if (currentRequest === opportunityRequest) loading.value = false
  }
}
async function loadReferences() {
  const accountRowsPromise = readAllPages((page, pageSize) => props.apiClient.listAccounts({ page, pageSize }))
  const contactRowsPromise = app.can('contact:view')
    ? readAllPages((page, pageSize) => props.apiClient.listContacts({ page, pageSize }))
    : Promise.resolve([] as ContactSummaryDto[])
  const [accountRows, contactRows, pipelineResult] = await Promise.all([
    accountRowsPromise,
    contactRowsPromise,
    props.apiClient.listPipeline({}),
  ])
  accounts.value = accountRows
  contacts.value = contactRows
  bookings.value = pipelineResult.data.bookings
  if (!app.can('contact:view')) {
    sitesByAccount.value = {}
    return
  }
  const details = await Promise.all(accounts.value.map((account) => props.apiClient.getAccount360(account.id)))
  sitesByAccount.value = Object.fromEntries(details.map((detail) => [detail.data.account.id, detail.data.sites]))
}
async function saveBooking(input: UpsertBookingInput) {
  busy.value = true
  modalError.value = ''
  try {
    await props.apiClient.createBooking(input)
    bookingModal.value = false
    await loadReferences()
  } catch (reason) {
    modalError.value = mapRequestError(reason).message
  } finally {
    busy.value = false
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
    modalError.value = mapRequestError(reason).message
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
  if (!selected.value) return
  const reason = lostReason.value.trim()
  if (!reason) {
    modalError.value = '请填写 Lost Reason'
    return
  }
  busy.value = true
  modalError.value = ''
  try {
    await props.apiClient.updateStrategyOpportunity(selected.value.id, { stage: 'Lost', lostReason: reason }, selected.value.modified)
    lostModal.value = false
    await loadOpportunity()
  } catch (reason) {
    modalError.value = mapRequestError(reason).message
  } finally {
    busy.value = false
  }
}
async function advanceStage() {
  if (!selected.value || !canAdvanceManually.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    await props.apiClient.updateStrategyOpportunity(selected.value.id, { stage: nextStage.value as typeof OPPORTUNITY_STAGES[number] }, selected.value.modified)
    await loadOpportunity()
  } catch (reason) {
    error.value = mapRequestError(reason).message
  } finally {
    busy.value = false
  }
}
function openRollback() {
  rollbackReason.value = ''
  rollbackTarget.value = rollbackTargets.value.at(-1) ?? ''
  rollbackErrors.value = {}
  modalError.value = ''
  rollbackModal.value = true
}
async function rollbackStage() {
  if (!selected.value || busy.value) return
  rollbackErrors.value = {}
  const reason = rollbackReason.value.trim()
  if (!rollbackTarget.value) rollbackErrors.value.rollbackTarget = '请选择回退阶段'
  if (!reason) rollbackErrors.value.rollbackReason = '请填写阶段回退原因'
  if (Object.keys(rollbackErrors.value).length) return
  busy.value = true
  modalError.value = ''
  try {
    await props.apiClient.rollbackOpportunityStage(selected.value.id, {
      targetStage: rollbackTarget.value as typeof OPPORTUNITY_STAGES[number],
      reason,
    }, selected.value.modified)
    rollbackModal.value = false
    await loadOpportunity()
  } catch (reason) {
    const mapped = mapRequestError(reason)
    modalError.value = mapped.requestId ? `${mapped.message}（Request ID: ${mapped.requestId}）` : mapped.message
  } finally {
    busy.value = false
  }
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
    modalError.value = mapRequestError(reason).message
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
    error.value = mapRequestError(reason).message
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
    modalError.value = mapRequestError(reason).message
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
    error.value = mapRequestError(reason).message
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
function openBooking() {
  modalError.value = ''
  bookingContactId.value = contacts.value.find((contact) =>
    contact.accountId === selected.value?.accountId && contact.status === 'Active')?.id ?? ''
  bookingModal.value = true
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
    modalError.value = mapRequestError(reason).message
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
    error.value = mapped.message
    requestId.value = mapped.requestId
    denied.value = mapped.denied
    loading.value = false
  }
})
</script>

<template>
  <div class="opportunity-detail-page">
    <DataState v-if="loading" type="loading" title="正在读取 Opportunity" />
    <section v-else-if="notFound" class="detail-state">未找到指定 Opportunity。</section>
    <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
    <DataState v-else-if="error && !selected" type="error" :message="error" :request-id="requestId" @retry="loadOpportunity" />
    <section v-else-if="!selected" class="detail-state">未找到指定 Opportunity。</section>
    <template v-else>
      <header class="opportunity-record-header">
        <RouterLink class="back-opportunities detail-back-button" data-testid="back-opportunities" :to="{ name: 'opportunities' }"><ArrowLeft :size="15" />返回 Opportunities</RouterLink>
        <div class="record-identity">
          <span><Target :size="22" /></span>
          <div><small>Opportunity · {{ selected.id }}</small><h1>{{ selected.title }}</h1><p>{{ selected.account }} · {{ selected.site }}</p></div>
        </div>
        <div class="record-actions">
          <RouterLink v-if="quotationId" class="secondary-button" data-testid="opportunity-quotation-link" :to="{ name: 'quotation-detail', params: { quotationId } }"><FileText :size="14" />查看 Quotation</RouterLink>
          <RouterLink v-else-if="app.can('quotation:write') && selected.stage === '报价'" class="secondary-button" data-testid="create-quotation-from-opportunity" :to="{ name: 'quotations', query: { opportunityId: selected.id } }"><FileText :size="14" />新建 Quotation</RouterLink>
          <RouterLink v-if="rfqId" class="secondary-button" data-testid="opportunity-rfq-link" :to="{ name: 'rfq-detail', params: { rfqId } }"><FileText :size="14" />RFQ · {{ rfqStatus }}</RouterLink>
          <RouterLink v-else-if="app.can('rfq:view') && selected.stage === '设备规格确认'" class="secondary-button" data-testid="opportunity-rfq-center-link" :to="{ name: 'rfqs', query: { opportunityId: selected.id } }"><FileText :size="14" />RFQ 未创建</RouterLink>
          <RouterLink v-if="existingBooking" class="secondary-button" data-testid="opportunity-booking-link" :to="{ name: 'booking' }"><PackageCheck :size="14" />Booking · {{ existingBooking.id }}</RouterLink>
          <button v-else-if="canWrite && selected.stage === 'Won'" class="primary-button" type="button" data-testid="create-booking-from-opportunity" @click="openBooking"><PackageCheck :size="14" />生成 Booking</button>
          <button v-if="canWrite" class="secondary-button" type="button" data-testid="new-opportunity-action" @click="openAction()"><Plus :size="14" />新增 Action</button>
          <button v-if="canWrite" class="primary-button" type="button" data-testid="edit-opportunity" @click="opportunityModal = true"><Pencil :size="14" />编辑</button>
          <button v-if="canMarkLost" class="secondary-button lost-action-button" type="button" data-testid="mark-opportunity-lost" @click="openLostModal">标记为 Lost</button>
          <button v-if="canDelete" class="secondary-button" type="button" data-delete-opportunity :disabled="deleting" @click="deleteOpportunity">删除</button>
        </div>
      </header>
      <p v-if="deleteError" class="inline-error" data-delete-error>{{ deleteError }}<small v-if="deleteRequestId">Request ID {{ deleteRequestId }}</small></p>

      <section class="opportunity-path" aria-label="Opportunity Stage Path">
        <div class="path-scroll">
          <ol>
            <li
              v-for="(item, index) in OPPORTUNITY_STAGES.slice(0, 6)"
              :key="item"
              :data-stage-path="item"
              :class="{ 'is-complete': index < currentStageIndex, 'is-current': index === currentStageIndex }"
            >
              <Check v-if="index < currentStageIndex" :size="14" />
              <span>{{ item }}</span>
            </li>
          </ol>
        </div>
        <div class="opportunity-outcomes" aria-label="Opportunity Result">
          <div v-for="item in OPPORTUNITY_STAGES.slice(6)" :key="item" class="opportunity-outcome">
            <span class="outcome-label">{{ item }}</span>
            <span
              :data-stage-path="item"
              :class="['outcome-node', { 'is-current': selected.stage === item }]"
            >
              <Check v-if="selected.stage === item" :size="14" />
              <span>{{ item }}</span>
            </span>
          </div>
        </div>
        <button v-if="canAdvanceManually" type="button" data-testid="advance-opportunity-stage" :disabled="busy" @click="advanceStage">
          <Check :size="14" />{{ nextStage ? `推进到 ${nextStage}` : selected.stage === 'Won' ? '已赢单' : '阶段已关闭' }}
        </button>
        <button v-if="canRollback" type="button" data-testid="rollback-opportunity-stage" :disabled="busy" @click="openRollback">
          阶段回退
        </button>
      </section>

      <p v-if="error" class="inline-error">{{ error }}</p>

      <main class="opportunity-detail-grid" data-testid="selected-opportunity">
        <div class="detail-column detail-left">
          <section class="detail-card">
            <header><Building2 :size="16" /><h2>About</h2></header>
            <dl class="field-list">
              <div><dt>Opportunity Name</dt><dd>{{ selected.title }}</dd></div>
              <div><dt>Account Name</dt><dd>{{ selected.account }}</dd></div>
              <div><dt>Site</dt><dd>{{ selected.site }}</dd></div>
              <div><dt>Close Date</dt><dd>{{ formatDisplayDate(selected.poDate) }}</dd></div>
              <div><dt>Amount</dt><dd>{{ formatMoney(selected.amount, selected.currency) }}</dd></div>
              <div><dt>Opportunity Owner</dt><dd>{{ personnelDisplayName(selected.owner) }}</dd></div>
              <div><dt>Tool / Sale Type</dt><dd>{{ selected.toolType }} · {{ selected.saleType }}</dd></div>
            </dl>
          </section>

          <section class="detail-card">
            <header><Target :size="16" /><h2>Status</h2></header>
            <dl class="field-list">
              <div><dt>Stage</dt><dd>{{ selected.stage }}</dd></div>
              <div><dt>成交概率</dt><dd data-testid="opportunity-probability">{{ selected.probability }}%</dd></div>
              <div><dt>Forecast Category</dt><dd>{{ selected.forecast }}</dd></div>
              <div><dt>购买意愿</dt><dd data-testid="opportunity-intent">{{ selected.score }}/100</dd></div>
              <div><dt>Next Step</dt><dd>{{ nextAction?.title || '暂无开放 Action' }}</dd></div>
              <div><dt>Updated</dt><dd>{{ formatDisplayDate(selected.updated) }}</dd></div>
            </dl>
            <p class="probability-explanation" data-testid="opportunity-probability-explanation">{{ probabilityExplanation }}</p>
          </section>
        </div>

        <div class="detail-column detail-center">
          <section class="detail-card action-card">
            <header><div><CircleDollarSign :size="16" /><h2>Action Plan</h2></div><button v-if="canWrite" type="button" @click="openAction()"><Plus :size="13" />新增</button></header>
            <div v-if="selected.actions.length" class="activity-list">
              <article v-for="action in selected.actions" :key="action.id" :data-action-title="action.title">
                <i :class="{ done: action.status === 'Done' }"></i>
                <div><strong>{{ action.title }}</strong><span>{{ personnelDisplayName(action.owner) }} · Due {{ formatDisplayDate(action.due) }}</span></div>
                <b :class="{ done: action.status === 'Done' }">{{ action.status }}</b>
                <div v-if="canWrite" class="compact-actions"><button type="button" data-action="edit" aria-label="编辑 Action" @click="openAction(action)"><Pencil :size="12" /></button><button type="button" data-action="delete" aria-label="删除 Action" @click="removeAction(action)"><Trash2 :size="12" /></button></div>
              </article>
            </div>
            <p v-else class="empty-copy">暂无活动，创建 Action 记录下一步工作。</p>
          </section>

          <section class="detail-card commercial-card">
            <header><CircleDollarSign :size="16" /><h2>Commercial Forecast</h2></header>
            <div class="commercial-grid">
              <div><small>Currency / Original Amount</small><strong>{{ formatMoney(selected.originalAmount, selected.currency) }}</strong></div>
              <div><small>Shipment / FAT</small><strong>{{ formatDisplayDate(selected.shipmentDate) }} · {{ formatDisplayDate(selected.fatDate) }}</strong></div>
              <div><small>Payment Milestones</small><strong>{{ selected.paymentMilestones.join(' · ') }}</strong></div>
              <div><small>Competition</small><strong>{{ selected.competition }}</strong></div>
              <div v-if="selected.stage === 'Lost'" class="wide lost-reason-field"><small>Lost Reason</small><strong>{{ selected.lostReason || '未填写 Lost Reason' }}</strong></div>
              <div v-else class="wide"><small>Win Reason</small><strong>{{ selected.winReason || 'Pending confirmation' }}</strong></div>
            </div>
          </section>
          <section v-if="selected.stage === 'Lost'" class="detail-card lost-detail-card" data-testid="lost-detail">
            <header><h2>Lost 信息</h2><span>已关闭</span></header>
            <dl class="field-list">
              <div><dt>Lost Reason</dt><dd>{{ selected.lostReason || '未填写' }}</dd></div>
              <div><dt>设置人</dt><dd>{{ lostHistory ? personnelDisplayName(lostHistory.actor) : '历史记录不可用' }}</dd></div>
              <div><dt>设置时间</dt><dd>{{ lostHistory ? formatDisplayDate(lostHistory.at) : '历史记录不可用' }}</dd></div>
            </dl>
          </section>
        </div>

        <aside class="detail-column detail-right">
          <section class="detail-card influence-card">
            <header><div><Users :size="16" /><h2>Buying Influence</h2></div><button v-if="canWrite" type="button" data-testid="new-opportunity-stakeholder" @click="openStakeholder()"><Plus :size="13" />新增</button></header>
            <div class="influence-list">
              <article v-for="person in selected.stakeholders" :key="person.id" :data-stakeholder-name="person.name">
                <RouterLink class="record-link" :to="{ name: 'contact-detail', params: { contactId: person.contactId } }"><strong>{{ person.name }}</strong><span>{{ person.title }}</span></RouterLink>
                <small>{{ person.role }} · {{ person.influence }}</small>
                <b :class="stanceClass(person.stance)">{{ person.stance }}</b>
                <p>{{ person.coverage }}</p>
                <div v-if="canWrite" class="compact-actions"><button type="button" data-action="edit" aria-label="编辑关键人" @click="openStakeholder(person)"><Pencil :size="12" /></button><button type="button" data-action="delete" aria-label="删除关键人" @click="removeStakeholder(person)"><Trash2 :size="12" /></button></div>
              </article>
              <p v-if="!selected.stakeholders.length" class="empty-copy">尚未添加机会关键人。</p>
            </div>
          </section>

          <section class="detail-card evidence-card strength-card">
            <header><h2>Strength</h2><span>{{ selected.strengths.length }}</span></header>
            <ul><li v-for="item in selected.strengths" :key="item">{{ item }}</li></ul>
          </section>
          <section class="detail-card evidence-card risk-card">
            <header><h2>Red Flag</h2><span>{{ selected.redFlags.length }}</span></header>
            <ul><li v-for="item in selected.redFlags" :key="item">{{ item }}</li></ul>
          </section>
          <section class="detail-card evidence-card information-card">
            <header><h2>Information Needed</h2><span>{{ selected.informationNeeded.length }}</span></header>
            <ul><li v-for="item in selected.informationNeeded" :key="item">{{ item }}</li></ul>
          </section>
        </aside>
      </main>

      <OpportunityEditorModal v-if="opportunityModal" :opportunity="selected" :accounts="accounts" :sites-by-account="sitesByAccount" :default-owner="app.bootstrap?.user.id ?? ''" :busy="busy" :error="modalError" @close="opportunityModal = false" @submit="saveOpportunity" />
      <StakeholderEditorModal v-if="stakeholderModal" :stakeholder="editingStakeholder" :contacts="contacts" :account-id="selected.accountId" :selected-contact-id="selectedContactId" :busy="busy" :error="modalError" @close="stakeholderModal = false" @create-contact="openContact" @submit="saveStakeholder" />
      <ContactModal v-if="contactModal" :accounts="accounts" :sites="contactSites" :contacts="contacts" :fixed-account-id="contactAccountId" :busy="busy" :error="modalError" @close="contactModal = false" @submit="saveContact" />
      <ActionEditorModal v-if="actionModal" :action="editingAction" :default-owner="app.bootstrap?.user.id ?? ''" :busy="busy" :error="modalError" @close="actionModal = false" @submit="saveAction" />
      <BookingEditorModal
        v-if="bookingModal"
        :accounts="accounts"
        :opportunities="[selected]"
        :contacts="contacts"
        :selected-contact-id="bookingContactId"
        :source-opportunity-id="selected.id"
        :default-owner="selected.owner"
        :busy="busy"
        :error="modalError"
        @close="bookingModal = false"
        @create-contact="openBookingContact"
        @submit="saveBooking"
      />
      <ModalShell v-if="lostModal" title="标记为 Lost" eyebrow="OPPORTUNITY RESULT" :busy="busy" @close="lostModal = false" @submit="markLost">
        <p v-if="modalError" class="form-error">{{ modalError }}</p>
        <div class="lost-form">
          <p>当前账号：{{ app.bootstrap?.user.name || app.bootstrap?.user.id || '当前登录用户' }}（{{ app.bootstrap?.user.role || '未知角色' }}）</p>
          <label><span>Lost Reason</span><textarea v-model="lostReason" aria-label="Lost Reason" rows="4" required placeholder="请填写客户未成交的主要原因" /></label>
        </div>
      </ModalShell>
      <ModalShell v-if="rollbackModal" title="回退 Opportunity 阶段" eyebrow="MANAGER CONTROL" :busy="busy" @close="rollbackModal = false" @submit="rollbackStage">
        <p v-if="modalError" class="form-error">{{ modalError }}</p>
        <div class="rollback-form">
          <label>目标阶段
            <select v-model="rollbackTarget" aria-label="阶段回退目标">
              <option v-for="stage in rollbackTargets" :key="stage" :value="stage">{{ stage }}</option>
            </select>
            <small v-if="rollbackErrors.rollbackTarget" data-field-error="rollbackTarget">{{ rollbackErrors.rollbackTarget }}</small>
          </label>
          <label>回退原因
            <textarea v-model="rollbackReason" aria-label="阶段回退原因" rows="4" />
            <small v-if="rollbackErrors.rollbackReason" data-field-error="rollbackReason">{{ rollbackErrors.rollbackReason }}</small>
          </label>
        </div>
      </ModalShell>
    </template>
  </div>
</template>

<style scoped>
.opportunity-detail-page{display:grid;gap:14px}.detail-state{padding:28px;color:var(--crm-text-muted);background:#fff;border:1px solid var(--crm-line);border-radius:12px}.opportunity-record-header{display:grid;grid-template-columns:1fr auto;gap:10px 18px;align-items:end}.back-opportunities{grid-column:1/-1;display:inline-flex;width:fit-content;align-items:center;gap:6px;color:var(--crm-teal);font-size:10px;font-weight:800}.record-identity{display:flex;align-items:center;gap:12px}.record-identity>span{display:grid;width:46px;height:46px;place-items:center;color:var(--crm-brand-ink);background:var(--crm-brand-soft);border-radius:13px}.record-identity small{color:var(--crm-text-muted);font-size:9px}.record-identity h1{margin:2px 0 3px;color:var(--crm-navy);font-size:clamp(23px,2.3vw,32px);letter-spacing:-.03em}.record-identity p{margin:0;color:var(--crm-text-muted);font-size:10px}.record-actions{display:flex;gap:7px}.record-actions button{display:flex;align-items:center;gap:6px}.opportunity-path{display:flex;align-items:center;gap:12px;padding:11px 12px;background:#fff;border:1px solid var(--crm-line);border-radius:13px}.path-scroll{min-width:0;flex:1;overflow-x:auto}.opportunity-path ol{display:grid;min-width:620px;grid-template-columns:repeat(6,1fr);margin:0;padding:0;list-style:none}.opportunity-path li{display:flex;height:36px;align-items:center;justify-content:center;gap:5px;margin-right:-8px;padding:0 18px;color:var(--crm-text-muted);background:#eeeae4;clip-path:polygon(0 0,calc(100% - 12px) 0,100% 50%,calc(100% - 12px) 100%,0 100%,12px 50%);font-size:9px;font-weight:800}.opportunity-path li:first-child{clip-path:polygon(0 0,calc(100% - 12px) 0,100% 50%,calc(100% - 12px) 100%,0 100%)}.opportunity-path li.is-complete{color:#24633f;background:#dff3e8}.opportunity-path li.is-current{position:relative;color:var(--crm-brand-ink);background:var(--crm-brand);z-index:1}.opportunity-path>button{display:flex;min-height:36px;align-items:center;gap:6px;padding:0 13px;color:var(--crm-brand-ink);background:var(--crm-brand);border:1px solid var(--crm-brand);border-radius:9px;font:inherit;font-size:9px;font-weight:800;white-space:nowrap;cursor:pointer}.opportunity-path>button:disabled{color:var(--crm-text-muted);background:var(--crm-surface-muted);border-color:var(--crm-line);cursor:not-allowed}.inline-error{margin:0;padding:10px 12px;color:var(--crm-danger);background:var(--crm-danger-soft);border:1px solid rgba(200,78,78,.2);border-radius:9px;font-size:10px}.opportunity-detail-grid{display:grid;grid-template-columns:minmax(260px,.78fr) minmax(420px,1.34fr) minmax(270px,.88fr);gap:14px;align-items:start}.detail-column{display:grid;gap:14px}.detail-card{overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:12px;box-shadow:0 8px 24px rgba(31,35,41,.035)}.detail-card>header{display:flex;min-height:50px;align-items:center;gap:8px;padding:0 14px;background:#faf9f7;border-bottom:1px solid var(--crm-line)}.detail-card>header>div{display:flex;align-items:center;gap:8px}.detail-card>header h2{margin:0;color:var(--crm-navy);font-size:12px}.detail-card>header>span{margin-left:auto;color:var(--crm-text-muted);font-size:9px}.detail-card>header button{display:flex;align-items:center;gap:4px;margin-left:auto;padding:6px 8px;color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line);border-radius:7px;font:inherit;font-size:8px;font-weight:800;cursor:pointer}.field-list{display:grid;margin:0;padding:2px 14px 10px}.field-list>div{display:grid;gap:4px;padding:10px 0;border-bottom:1px solid var(--crm-line)}.field-list>div:last-child{border-bottom:0}.field-list dt{color:var(--crm-text-muted);font-size:8px;font-weight:700}.field-list dd{margin:0;color:var(--crm-text);font-size:10px;line-height:1.45}.probability-explanation{margin:0 14px 13px;padding:8px 9px;color:var(--crm-teal);background:var(--crm-teal-soft);border-radius:8px;font-size:8px;line-height:1.45}.activity-list{display:grid}.activity-list article{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;align-items:center;gap:9px;padding:12px 14px;border-bottom:1px solid var(--crm-line)}.activity-list article:last-child{border-bottom:0}.activity-list i{width:10px;height:10px;border:2px solid var(--crm-warning);border-radius:50%}.activity-list i.done{background:var(--crm-positive);border-color:var(--crm-positive)}.activity-list article>div:nth-child(2){display:grid;gap:4px}.activity-list strong{color:var(--crm-text);font-size:10px}.activity-list span{color:var(--crm-text-muted);font-size:8px}.activity-list article>b{padding:4px 7px;color:#8a651d;background:var(--crm-warning-soft);border-radius:999px;font-size:7px}.activity-list article>b.done{color:var(--crm-positive-ink);background:#e8f5ed}.compact-actions{display:flex!important;gap:4px!important}.compact-actions button{display:grid;width:25px;height:25px;place-items:center;padding:0;color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line);border-radius:6px;cursor:pointer}.compact-actions button:last-child{color:var(--crm-danger)}.empty-copy{margin:0;padding:22px;color:var(--crm-text-muted);font-size:9px;text-align:center}.history-list{display:grid;padding:0 14px}.history-list article{display:grid;grid-template-columns:110px 90px minmax(0,1fr) 80px;gap:10px;padding:11px 0;border-bottom:1px solid var(--crm-line);font-size:8px}.history-list article:last-child{border-bottom:0}.history-list time,.history-list small{color:var(--crm-text-muted)}.history-list strong{color:var(--crm-navy)}.commercial-grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--crm-line)}.commercial-grid>div{display:grid;gap:5px;padding:13px;background:#fff}.commercial-grid .wide{grid-column:1/-1}.commercial-grid small,.commercial-grid span{color:var(--crm-text-muted);font-size:8px}.commercial-grid strong{color:var(--crm-text);font-size:9px;line-height:1.45}.influence-list{display:grid;padding:8px}.influence-list article{position:relative;display:grid;gap:5px;padding:10px 62px 10px 10px;border-bottom:1px solid var(--crm-line)}.influence-list article:last-child{border-bottom:0}.influence-list a{display:grid;gap:3px;color:var(--crm-teal)}.influence-list a strong{font-size:10px}.influence-list a span,.influence-list small,.influence-list p{color:var(--crm-text-muted);font-size:8px}.influence-list p{margin:0;line-height:1.45}.influence-list article>b{position:absolute;top:10px;right:10px;padding:4px 6px;border-radius:999px;font-size:7px}.influence-list article>b.positive{color:var(--crm-positive-ink);background:#e8f5ed}.influence-list article>b.warning{color:#8a651d;background:var(--crm-warning-soft)}.influence-list article>b.danger{color:var(--crm-danger);background:var(--crm-danger-soft)}.influence-list .compact-actions{position:absolute;right:8px;bottom:9px}.evidence-card ul{display:grid;gap:8px;margin:0;padding:13px 16px 15px 29px}.evidence-card li{color:var(--crm-text);font-size:9px;line-height:1.5}.strength-card li::marker{color:var(--crm-positive)}.risk-card li::marker{color:var(--crm-danger)}.information-card li::marker{color:var(--crm-warning)}@media(max-width:1180px){.opportunity-detail-grid{grid-template-columns:minmax(250px,.8fr) minmax(0,1.2fr)}.detail-right{grid-column:1/-1;grid-template-columns:repeat(3,1fr)}.detail-right .influence-card{grid-column:1/-1}}@media(max-width:780px){.opportunity-record-header{grid-template-columns:1fr}.record-actions{flex-wrap:wrap}.opportunity-path{align-items:stretch;flex-direction:column}.opportunity-path>button{justify-content:center}.opportunity-detail-grid{grid-template-columns:1fr}.detail-right{grid-column:auto;grid-template-columns:1fr}.history-list article{grid-template-columns:1fr 1fr}.commercial-grid{grid-template-columns:1fr}.commercial-grid .wide{grid-column:auto}}@media(max-width:520px){.record-identity{align-items:flex-start}.record-identity h1{font-size:22px}.record-actions button{flex:1;justify-content:center}}
.path-scroll{overflow-x:hidden}
@media(max-width:640px){.path-scroll{overflow-x:auto}}
.rollback-form{display:grid;gap:13px}.rollback-form label{display:grid;gap:6px;color:var(--crm-text-muted);font-size:9px;font-weight:700}.rollback-form select,.rollback-form textarea{box-sizing:border-box;width:100%;padding:9px 10px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.rollback-form small{color:var(--crm-danger)}.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:9px}
</style>
<style scoped>
.opportunity-path ol{grid-template-columns:repeat(8, minmax(86px, 1fr));}
.opportunity-path ol{grid-template-columns:repeat(6, minmax(86px, 1fr));}
.opportunity-outcomes{display:flex;align-items:stretch;gap:8px;flex:0 0 auto;padding-left:8px;border-left:1px solid var(--crm-line)}
.opportunity-outcome{display:grid;justify-items:center;gap:4px;min-width:58px;padding:0 4px}
.outcome-label{color:var(--crm-text-muted);font-size:8px;font-weight:800;white-space:nowrap}
.outcome-node{display:flex;height:36px;box-sizing:border-box;align-items:center;justify-content:center;gap:4px;width:100%;padding:0 8px;color:var(--crm-text-muted);background:#eeeae4;border:1px solid var(--crm-line);border-radius:8px;font-size:9px;font-weight:800;white-space:nowrap}
.outcome-node.is-current{color:var(--crm-brand-ink);background:var(--crm-brand);border-color:var(--crm-brand)}
.lost-reason-field{background:#fff5f2!important}
.lost-reason-field strong{color:var(--crm-danger)!important}
.lost-action-button{color:var(--crm-danger)!important;border-color:rgba(200,78,78,.35)!important}
.lost-detail-card{border-color:rgba(200,78,78,.35)}
.lost-detail-card>header{background:#fff5f2}
.lost-detail-card>header h2,.lost-detail-card>header span{color:var(--crm-danger)}
.lost-form{display:grid;gap:13px}.lost-form>p{margin:0;padding:9px 10px;color:var(--crm-text-muted);background:var(--crm-surface-muted);border-radius:8px;font-size:9px}.lost-form label{display:grid;gap:6px;color:var(--crm-text-muted);font-size:9px;font-weight:700}.lost-form textarea{box-sizing:border-box;width:100%;padding:9px 10px;border:1px solid var(--crm-line);border-radius:8px;font:inherit;resize:vertical}
@media(max-width:780px){.opportunity-outcomes{padding-top:8px;padding-left:0;border-top:1px solid var(--crm-line);border-left:0}.opportunity-outcome{flex:1}.outcome-node{justify-content:center}}
</style>
