<script setup lang="ts">
import { personnelDisplayName } from '@/demo/personnel'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { AlertTriangle, CalendarClock, CircleDollarSign, Pencil, Plus, Target, Trash2, Users } from '@lucide/vue'
import { api as defaultApi } from '@/api'
import type { CrmApi } from '@/api'
import type { AccountSummaryDto, BookingDto, ContactSummaryDto, CreateContactInput, SiteDto, UpsertBookingInput } from '@/types/crm'
import type { CreateOpportunityActionInput, CreateOpportunityStakeholderInput, CreateStrategyOpportunityInput, OpportunityActionDto, OpportunityStakeholderDto, OpportunityStakeholderStance, StrategyOpportunityDto } from '@/types/workspaces'
import { useAppStore } from '@/stores/app'
import { mapRequestError } from '@/api/request-state'
import WorkspaceMetric from '@/features/workspace/WorkspaceMetric.vue'
import OpportunityEditorModal from '@/features/opportunities/OpportunityEditorModal.vue'
import StakeholderEditorModal from '@/features/opportunities/StakeholderEditorModal.vue'
import ActionEditorModal from '@/features/opportunities/ActionEditorModal.vue'
import BookingEditorModal from '@/features/opportunities/BookingEditorModal.vue'
import ContactModal from '@/features/contacts/ContactModal.vue'
import { formatMoney, moneyByCurrency } from '@/domain/money'
import { formatDisplayDate } from '@/domain/time'
import { opportunityProbabilityLevelLabel, opportunityProbabilityLevelTone } from '@/domain/opportunity-probability'
import { opportunityStageLabel } from '@/domain/opportunity-stages'
import { regionLabel } from '@/domain/regions'
import { useI18n } from '@/i18n'

const props = withDefaults(defineProps<{ apiClient?: CrmApi; embedded?: boolean }>(), { apiClient: () => defaultApi, embedded: false })
const app = useAppStore()
const { locale } = useI18n()
const route = useRoute()
const router = useRouter()
const opportunities = ref<StrategyOpportunityDto[]>([])
const bookings = ref<BookingDto[]>([])
const accounts = ref<AccountSummaryDto[]>([])
const contacts = ref<ContactSummaryDto[]>([])
const sitesByAccount = ref<Record<string, SiteDto[]>>({})
const selectedId = ref('')
const loading = ref(true)
const error = ref('')
const busy = ref(false)
const modalError = ref('')
const opportunityModal = ref<'create' | 'edit' | null>(null)
const bookingModal = ref<'create' | 'edit' | null>(null)
const editingBooking = ref<BookingDto | null>(null)
const mode = ref<'opportunity' | 'booking'>('opportunity')
const stakeholderModal = ref(false), actionModal = ref(false)
const contactModal = ref(false)
const editingStakeholder = ref<OpportunityStakeholderDto | null>(null)
const editingAction = ref<OpportunityActionDto | null>(null)
const selectedContactId = ref('')
const bookingContactId = ref('')
const contactAccountId = ref('')
const contactContext = ref<'stakeholder' | 'booking'>('stakeholder')
const canWrite = computed(() => app.can('deal:write'))
const requestedAccountId = computed(() => typeof route.query.accountId === 'string' ? route.query.accountId : '')
const opportunityAccounts = computed(() => {
  const requested = accounts.value.find((account) => account.id === requestedAccountId.value)
  return requested ? [requested, ...accounts.value.filter((account) => account.id !== requested.id)] : accounts.value
})
const contactSites = computed(() => Object.entries(sitesByAccount.value).flatMap(([accountId, sites]) =>
  sites.map((site) => ({ ...site, accountId })),
))
const selected = computed(() => opportunities.value.find((item) => item.id === selectedId.value) ?? opportunities.value[0])
const committedOpportunities = computed(() => opportunities.value.filter((item) => item.probabilityLevel === 'committed'))
const coverageGapCount = computed(() => opportunities.value.reduce(
  (sum, item) => sum + item.stakeholders.filter((person) => !person.coverage || person.coverage === '尚未记录').length,
  0,
))
const redFlagCount = computed(() => opportunities.value.reduce((sum, item) => sum + item.redFlags.length, 0))
const confirmedBookingAmount = computed(() => currencyTotals(bookings.value.filter((item) => item.status === 'Confirmed')))
const upcomingBookings = computed(() => bookings.value.filter((item) => item.status !== 'Cancelled').sort((a, b) => a.ddl.localeCompare(b.ddl)))
const nearDueActions = computed(() => {
  const end = new Date()
  end.setHours(23, 59, 59, 999)
  end.setDate(end.getDate() + 7)
  return opportunities.value.flatMap((item) => item.actions).filter((action) => {
    if (!action.due || action.status === 'Done') return false
    const due = new Date(`${action.due}T23:59:59`)
    return !Number.isNaN(due.getTime()) && due <= end
  })
})
const nearDueOwnerCount = computed(() => new Set(nearDueActions.value.map((action) => action.owner)).size)
const currencyTotals = <T extends { currency: string; amount: string }>(rows: T[]) => moneyByCurrency(rows)
  .map((item) => formatMoney(item.amount, item.currency)).join(' · ')
const stanceTone = (stance: OpportunityStakeholderStance) => stance === 'Support' ? 'positive' : stance === 'Against' ? 'danger' : 'warning'

async function loadOpportunities(preferredId = selectedId.value) {
  const result = await props.apiClient.listStrategyOpportunities({ pageSize: 200 })
  const contactId = typeof route.query.contactId === 'string' ? route.query.contactId : ''
  opportunities.value = contactId ? result.data.items.filter((item) => item.stakeholders.some((person) => person.contactId === contactId)) : result.data.items
  selectedId.value = opportunities.value.some((item) => item.id === preferredId) ? preferredId : opportunities.value[0]?.id ?? ''
}

async function loadAccounts() {
  const result = await props.apiClient.listAccounts({ page: 1, pageSize: 100 })
  accounts.value = result.data.items
  const details = await Promise.all(accounts.value.map((account) => props.apiClient.getAccount360(account.id)))
  sitesByAccount.value = Object.fromEntries(details.map((detail) => [detail.data.account.id, detail.data.sites]))
}
async function loadBookings() {
  const result = await props.apiClient.listPipeline({})
  const contactId = typeof route.query.contactId === 'string' ? route.query.contactId : ''
  bookings.value = contactId ? result.data.bookings.filter((item) => item.primaryContactId === contactId) : result.data.bookings
}
async function loadContacts() {
  const result = await props.apiClient.listContacts({ page: 1, pageSize: 100 })
  contacts.value = result.data.items
}

function applyRouteView() {
  mode.value = 'opportunity'
}
async function consumeCreateQuery() {
  if (route.query.create !== '1' || !canWrite.value || opportunityModal.value) return
  openOpportunity('create')
  const { create: _create, ...query } = route.query
  await router.replace({ query })
}

watch(
  () => [route.query.contactId, route.query.view, route.query.accountId, route.query.create] as const,
  async () => {
    if (loading.value) return
    applyRouteView()
    await Promise.all([loadOpportunities(), ...(props.embedded ? [] : [loadBookings()])])
    await consumeCreateQuery()
  },
)

function openOpportunity(mode: 'create' | 'edit') { modalError.value = ''; opportunityModal.value = mode }
function openStakeholder(stakeholder: OpportunityStakeholderDto | null = null) {
  modalError.value = ''
  selectedContactId.value = stakeholder?.contactId ?? ''
  editingStakeholder.value = stakeholder
  stakeholderModal.value = true
}
function openContact() {
  modalError.value = ''
  contactContext.value = 'stakeholder'
  contactAccountId.value = selected.value?.accountId ?? ''
  contactModal.value = true
}
function openBookingContact(accountId: string) {
  modalError.value = ''
  contactContext.value = 'booking'
  contactAccountId.value = accountId
  contactModal.value = true
}
function openAction(action: OpportunityActionDto | null = null) { modalError.value = ''; editingAction.value = action; actionModal.value = true }
function openBooking(booking: BookingDto | null = null) {
  modalError.value = ''
  editingBooking.value = booking
  bookingContactId.value = booking?.primaryContactId ?? ''
  bookingModal.value = booking ? 'edit' : 'create'
}
async function saveOpportunity(input: CreateStrategyOpportunityInput) {
  busy.value = true; modalError.value = ''
  try {
    const result = opportunityModal.value === 'edit' && selected.value
      ? await props.apiClient.updateStrategyOpportunity(selected.value.id, input, selected.value.modified)
      : await props.apiClient.createStrategyOpportunity(input)
    opportunityModal.value = null
    await loadOpportunities(result.data.id)
  } catch (reason) { modalError.value = mapRequestError(reason).message }
  finally { busy.value = false }
}
async function saveStakeholder(input: CreateOpportunityStakeholderInput) {
  if (!selected.value) return
  busy.value = true; modalError.value = ''
  try {
    if (editingStakeholder.value) await props.apiClient.updateOpportunityStakeholder(selected.value.id, editingStakeholder.value.id, input)
    else await props.apiClient.createOpportunityStakeholder(selected.value.id, input)
    stakeholderModal.value = false; await loadOpportunities(selected.value.id)
  }
  catch (reason) { modalError.value = mapRequestError(reason).message }
  finally { busy.value = false }
}
async function saveContact(input: CreateContactInput) {
  busy.value = true; modalError.value = ''
  try {
    const result = await props.apiClient.createContact(input)
    if (contactContext.value === 'booking') bookingContactId.value = result.data.id
    else selectedContactId.value = result.data.id
    await loadContacts()
    contactModal.value = false
  } catch (reason) { modalError.value = mapRequestError(reason).message }
  finally { busy.value = false }
}
async function removeStakeholder(stakeholder: OpportunityStakeholderDto) {
  if (!selected.value) return
  busy.value = true
  try { await props.apiClient.deleteOpportunityStakeholder(selected.value.id, stakeholder.id); await loadOpportunities(selected.value.id) }
  catch (reason) { error.value = mapRequestError(reason).message }
  finally { busy.value = false }
}
async function saveAction(input: CreateOpportunityActionInput) {
  if (!selected.value) return
  busy.value = true; modalError.value = ''
  try {
    if (editingAction.value) await props.apiClient.updateOpportunityAction(selected.value.id, editingAction.value.id, input)
    else await props.apiClient.createOpportunityAction(selected.value.id, input)
    actionModal.value = false; await loadOpportunities(selected.value.id)
  }
  catch (reason) { modalError.value = mapRequestError(reason).message }
  finally { busy.value = false }
}
async function removeAction(action: OpportunityActionDto) {
  if (!selected.value) return
  busy.value = true
  try { await props.apiClient.deleteOpportunityAction(selected.value.id, action.id); await loadOpportunities(selected.value.id) }
  catch (reason) { error.value = mapRequestError(reason).message }
  finally { busy.value = false }
}
async function saveBooking(input: UpsertBookingInput) {
  busy.value = true; modalError.value = ''
  try {
    if (bookingModal.value === 'edit' && editingBooking.value) await props.apiClient.updateBooking(editingBooking.value.id, input, editingBooking.value.modified)
    else await props.apiClient.createBooking(input)
    bookingModal.value = null
    editingBooking.value = null
    await loadBookings()
  } catch (reason) { modalError.value = mapRequestError(reason).message }
  finally { busy.value = false }
}

onMounted(async () => {
  try {
    applyRouteView()
    await Promise.all([loadOpportunities(), loadAccounts(), loadContacts(), ...(props.embedded ? [] : [loadBookings()])])
    await consumeCreateQuery()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '商机策略数据加载失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="workspace-page" data-page="opportunity-strategy">
    <header v-if="!embedded" class="page-title-row">
      <div><span class="eyebrow">OPPORTUNITY MANAGEMENT</span><h1>Opportunities</h1><p>管理具体生意的金额、成交日期、阶段、产品、下一步任务和赢单概率。</p></div>
      <div class="page-toolbar"><span class="context-chip"><Target :size="15" />{{ opportunities.length }} Opportunities</span><button v-if="canWrite" class="primary-button" type="button" data-testid="new-opportunity" @click="openOpportunity('create')"><Plus :size="14" />新增 Opportunity</button></div>
    </header>

    <section v-if="loading" class="workspace-panel workspace-panel-body">正在读取商机策略数据…</section>
    <section v-else-if="error" class="workspace-panel workspace-panel-body">{{ error }}</section>
    <section v-else-if="mode === 'opportunity' && !selected" class="workspace-panel workspace-panel-body">当前权限范围内暂无商机数据。</section>
    <template v-else-if="mode === 'opportunity' && selected">
    <section class="workspace-metrics">
      <WorkspaceMetric label="重点机会金额" :value="currencyTotals(opportunities)" :detail="`${opportunities.length} 个重点机会`" delta="本季度" tone="info" :icon="CircleDollarSign" />
      <WorkspaceMetric :label="opportunityProbabilityLevelLabel('committed', locale)" :value="currencyTotals(committedOpportunities)" detail="高确定性预测" :delta="`${committedOpportunities.length} 个`" tone="positive" :icon="Target" />
      <WorkspaceMetric label="关系覆盖缺口" :value="String(coverageGapCount)" detail="尚无机会级覆盖证据" :delta="coverageGapCount ? '需管理介入' : '覆盖完整'" tone="warning" :icon="Users" />
      <WorkspaceMetric label="开放 Red Flag" :value="String(redFlagCount)" detail="当前已记录风险" :delta="redFlagCount ? '需本周处理' : '暂无风险记录'" tone="danger" :icon="AlertTriangle" />
      <WorkspaceMetric label="逾期 / 临期 Action" :value="String(nearDueActions.length)" detail="截至未来 7 天" :delta="`${nearDueOwnerCount} 位 Owner`" tone="warning" :icon="CalendarClock" />
    </section>

    <section class="strategy-layout">
      <aside class="workspace-panel opportunity-list">
        <header><h2>重点商机</h2><span>按管理优先级</span></header>
        <div class="workspace-panel-body workspace-list">
          <button v-for="item in opportunities" :key="item.id" class="workspace-select-card" :class="{ active: item.id === selected.id }" type="button" :data-opportunity-id="item.id" @click="selectedId = item.id">
            <div class="card-line"><span class="workspace-badge" :class="opportunityProbabilityLevelTone(item.probabilityLevel)">{{ opportunityProbabilityLevelLabel(item.probabilityLevel, locale) }}</span></div>
            <strong>{{ item.title }}</strong><small>{{ item.account }} · {{ item.site }}</small>
            <div class="card-line"><span>{{ formatMoney(item.amount, item.currency) }}</span><em>{{ formatDisplayDate(item.updated) }}</em></div>
          </button>
        </div>
      </aside>

      <div class="strategy-main" data-testid="selected-opportunity">
        <section class="workspace-panel strategy-overview">
          <header><div><span class="eyebrow">{{ selected.id }}</span><h2>{{ selected.title }}</h2></div><div class="inline-actions"><span class="workspace-badge" :class="opportunityProbabilityLevelTone(selected.probabilityLevel)">{{ opportunityProbabilityLevelLabel(selected.probabilityLevel, locale) }}</span><button v-if="canWrite" class="secondary-button" type="button" data-testid="edit-opportunity" @click="openOpportunity('edit')"><Pencil :size="13" />编辑</button></div></header>
          <div class="workspace-panel-body overview-grid">
            <div><small>Customer / Site</small><strong>{{ selected.account }}</strong><span>{{ selected.site }}</span></div>
            <div><small>Stage / Probability</small><strong>{{ opportunityStageLabel(selected.stage, locale) }}</strong><span>{{ opportunityProbabilityLevelLabel(selected.probabilityLevel, locale) }}</span></div>
            <div><small>Amount</small><strong>{{ formatMoney(selected.amount, selected.currency) }}</strong><span>预计PO {{ formatDisplayDate(selected.poDate) }}</span></div>
            <div><small>Owner / Health</small><strong>{{ personnelDisplayName(selected.owner) }}</strong><span>策略评分 {{ selected.score }}/100</span></div>
          </div>
        </section>

        <section class="workspace-panel commercial-panel">
          <header><h2>Commercial Forecast</h2><span>Commercial master data · dates · payment · competition</span></header>
          <div class="workspace-panel-body commercial-grid">
            <div><small>Tool / Sale Type</small><strong>{{ selected.toolType }} · {{ selected.saleType }}</strong><span>{{ regionLabel(selected.subRegion, locale) }}</span></div>
            <div><small>Currency / Original Amount</small><strong>{{ formatMoney(selected.originalAmount, selected.currency) }}</strong><span>CRM amount {{ formatMoney(selected.amount, selected.currency) }}</span></div>
            <div><small>PO / Shipment / FAT</small><strong>{{ formatDisplayDate(selected.poDate) }}</strong><span>{{ formatDisplayDate(selected.shipmentDate) }} · {{ formatDisplayDate(selected.fatDate) }}</span></div>
            <div><small>Payment Milestones</small><strong>{{ selected.paymentMilestones.join(' · ') }}</strong><span>{{ selected.competition }}</span></div>
            <div class="commercial-wide"><small>Win / Lost Reason</small><strong>{{ selected.winReason || 'Pending confirmation' }}</strong><span>{{ selected.lostReason || 'No lost reason recorded' }}</span></div>
          </div>
        </section>

        <section class="workspace-panel history-panel">
          <header><h2>Change History</h2><span>Who changed what and when</span></header>
          <div class="history-list"><div v-for="entry in selected.history" :key="`${entry.at}-${entry.field}`"><time>{{ formatDisplayDate(entry.at) }}</time><strong>{{ entry.field }}</strong><span>{{ entry.from }} → {{ entry.to }}</span><small>{{ personnelDisplayName(entry.actor) }}</small></div></div>
        </section>

        <section class="workspace-panel influence-panel">
          <header><div><h2>Buying Influence Coverage</h2><span>联系人主档 + 机会级关系记录</span></div><button v-if="canWrite" class="secondary-button" type="button" data-testid="new-opportunity-stakeholder" @click="openStakeholder()"><Plus :size="13" />新增关键人</button></header>
          <div class="influence-table-wrap"><table class="crm-table influence-table"><thead><tr><th>Stakeholder</th><th>Buying Role</th><th>Influence</th><th>Attitude</th><th>Coverage Evidence</th><th v-if="canWrite">操作</th></tr></thead><tbody><tr v-for="person in selected.stakeholders" :key="person.id" :data-stakeholder-name="person.name"><td><RouterLink :to="{ name: 'contact-detail', params: { contactId: person.contactId } }"><strong>{{ person.name }}</strong></RouterLink><small>{{ person.title }}</small></td><td>{{ person.role }}</td><td>{{ person.influence }}</td><td><span class="workspace-badge" :class="stanceTone(person.stance)">{{ person.stance }}</span></td><td>{{ person.coverage }}</td><td v-if="canWrite"><div class="row-actions"><button type="button" data-action="edit" aria-label="编辑关键人" @click="openStakeholder(person)"><Pencil :size="13" /></button><button type="button" data-action="delete" aria-label="删除关键人" @click="removeStakeholder(person)"><Trash2 :size="13" /></button></div></td></tr></tbody></table></div>
        </section>

        <section class="strategy-columns">
          <article class="workspace-panel evidence-card positive-card"><header><h2>Strength</h2><span>{{ selected.strengths.length }}</span></header><ul><li v-for="item in selected.strengths" :key="item">{{ item }}</li></ul></article>
          <article class="workspace-panel evidence-card danger-card"><header><h2>Red Flag</h2><span>{{ selected.redFlags.length }}</span></header><ul><li v-for="item in selected.redFlags" :key="item">{{ item }}</li></ul></article>
          <article class="workspace-panel evidence-card info-card"><header><h2>Information Needed</h2><span>{{ selected.informationNeeded.length }}</span></header><ul><li v-for="item in selected.informationNeeded" :key="item">{{ item }}</li></ul></article>
        </section>

        <section class="workspace-panel action-panel"><header><div><h2>Action Plan</h2><span>多行动 · 每项独立Owner与Due Date</span></div><button v-if="canWrite" class="secondary-button" type="button" data-testid="new-opportunity-action" @click="openAction()"><Plus :size="13" />新增 Action</button></header><div class="action-list"><div v-for="action in selected.actions" :key="action.id" :data-action-title="action.title"><i :class="{ done: action.status === 'Done' }" /><strong>{{ action.title }}</strong><span>{{ personnelDisplayName(action.owner) }}</span><time>{{ formatDisplayDate(action.due) }}</time><b class="workspace-badge" :class="action.status === 'Done' ? 'positive' : 'warning'">{{ action.status }}</b><div v-if="canWrite" class="row-actions"><button type="button" data-action="edit" aria-label="编辑 Action" @click="openAction(action)"><Pencil :size="13" /></button><button type="button" data-action="delete" aria-label="删除 Action" @click="removeAction(action)"><Trash2 :size="13" /></button></div></div></div></section>
      </div>
    </section>
    </template>
    <template v-else>
      <section class="workspace-metrics booking-metrics">
        <WorkspaceMetric label="Booking 总数" :value="String(bookings.length)" detail="当前权限范围内" delta="Sales 录入" tone="info" :icon="Target" />
        <WorkspaceMetric label="已确认金额" :value="confirmedBookingAmount" detail="Confirmed Booking" :delta="`${bookings.filter((item) => item.status === 'Confirmed').length} 个`" tone="positive" :icon="CircleDollarSign" />
        <WorkspaceMetric label="待确认" :value="String(bookings.filter((item) => item.status === 'Pending').length)" detail="等待客户或内部确认" delta="需持续跟进" tone="warning" :icon="CalendarClock" />
      </section>
      <section class="workspace-panel booking-panel">
        <header><div><h2>Booking List</h2><span>客户信息 · 设备需求 · DDL</span></div><span>{{ upcomingBookings.length }} 个有效 Booking</span></header>
        <div v-if="!bookings.length" class="workspace-panel-body">当前权限范围内暂无 Booking。</div>
        <div v-else class="booking-table-wrap">
          <table class="crm-table booking-table">
            <thead><tr><th>Booking / 客户</th><th>设备需求</th><th>客户 DDL</th><th>金额 / 状态</th><th>Sales Owner</th><th>备注</th><th v-if="canWrite">操作</th></tr></thead>
            <tbody><tr v-for="item in bookings" :key="item.id" :data-booking-id="item.id">
              <td><strong>{{ item.id }}</strong><small>{{ item.accountName }}</small><small><RouterLink :to="{ name: 'contact-detail', params: { contactId: item.primaryContactId } }">{{ item.customerContact }}</RouterLink></small></td>
              <td><strong>{{ item.equipment }}</strong><small>{{ item.quantity }} 台 · {{ item.sourceOpportunityId || '非商机来源' }}</small></td>
              <td><strong>{{ formatDisplayDate(item.ddl) }}</strong><small>录入 {{ formatDisplayDate(item.bookingDate) }}</small></td>
              <td><strong>{{ formatMoney(item.amount, item.currency) }}</strong><span class="workspace-badge" :class="item.status === 'Confirmed' ? 'positive' : item.status === 'Cancelled' ? 'danger' : 'warning'">{{ item.status }}</span></td>
              <td><strong>{{ personnelDisplayName(item.owner) }}</strong></td>
              <td><span>{{ item.note || '—' }}</span></td>
              <td v-if="canWrite"><button class="icon-edit" type="button" aria-label="编辑 Booking" @click="openBooking(item)"><Pencil :size="13" /></button></td>
            </tr></tbody>
          </table>
        </div>
      </section>
    </template>
    <OpportunityEditorModal v-if="opportunityModal" :opportunity="opportunityModal === 'edit' ? selected : null" :accounts="opportunityAccounts" :sites-by-account="sitesByAccount" :default-owner="app.bootstrap?.user.id ?? ''" :current-user-id="app.bootstrap?.user.id ?? ''" :busy="busy" :error="modalError" @close="opportunityModal = null" @submit="saveOpportunity" />
    <StakeholderEditorModal v-if="stakeholderModal && selected" :stakeholder="editingStakeholder" :contacts="contacts" :account-id="selected.accountId" :selected-contact-id="selectedContactId" :busy="busy" :error="modalError" @close="stakeholderModal = false" @create-contact="openContact" @submit="saveStakeholder" />
    <ContactModal v-if="contactModal" :accounts="accounts" :sites="contactSites" :contacts="contacts" :fixed-account-id="contactAccountId" :busy="busy" :error="modalError" @close="contactModal = false" @submit="saveContact" />
    <ActionEditorModal v-if="actionModal" :action="editingAction" :default-owner="app.bootstrap?.user.id ?? ''" :busy="busy" :error="modalError" @close="actionModal = false" @submit="saveAction" />
    <BookingEditorModal v-if="!embedded && bookingModal" :booking="editingBooking" :accounts="accounts" :opportunities="opportunities" :contacts="contacts" :selected-contact-id="bookingContactId" :default-owner="app.bootstrap?.user.id ?? ''" :busy="busy" :error="modalError" @close="bookingModal = null" @create-contact="openBookingContact" @submit="saveBooking" />
  </div>
</template>

<style scoped>
.strategy-layout{display:grid;grid-template-columns:280px minmax(0,1fr);gap:14px;align-items:start}.opportunity-list{position:sticky;top:88px}.card-line{display:flex;align-items:center;justify-content:space-between;color:var(--crm-text-muted);font-size:8px}.card-line b{color:var(--crm-teal);font-size:15px}.card-line em{font-style:normal}.strategy-main{display:grid;gap:14px}.strategy-overview>header{min-height:68px}.strategy-overview>header h2{margin-top:4px;font-size:16px}.overview-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;padding:0;background:var(--crm-line)}.overview-grid>div{display:grid;gap:5px;padding:15px;background:#fff}.overview-grid small{color:var(--crm-text-muted);font-size:7px}.overview-grid strong{color:var(--crm-navy);font-size:12px}.overview-grid span{color:var(--crm-text-muted);font-size:8px}.influence-table-wrap{overflow:auto}.influence-table{min-width:800px}.influence-table td strong,.influence-table td small{display:block}.influence-table td small{margin-top:3px;color:var(--crm-text-muted);font-size:8px}.strategy-columns{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.evidence-card ul{display:grid;gap:9px;margin:0;padding:14px 18px 16px 32px;color:var(--crm-text);font-size:9px;line-height:1.6}.evidence-card li::marker{color:var(--crm-teal)}.danger-card li::marker{color:var(--crm-danger)}.info-card li::marker{color:var(--crm-warning)}.action-list{display:grid}.action-list>div{display:grid;grid-template-columns:12px minmax(180px,1fr) 100px 80px auto 64px;align-items:center;gap:10px;min-height:48px;padding:0 16px;border-bottom:1px solid var(--crm-line);font-size:8px}.action-list>div:last-child{border:0}.action-list i{width:9px;height:9px;border:2px solid var(--crm-warning);border-radius:50%}.action-list i.done{background:var(--crm-positive);border-color:var(--crm-positive)}.action-list strong{color:var(--crm-text);font-size:9px}.action-list span,.action-list time{color:var(--crm-text-muted)}.page-toolbar,.inline-actions,.row-actions{display:flex;align-items:center;gap:7px}.primary-button,.secondary-button{display:inline-flex;align-items:center;justify-content:center;gap:5px}.row-actions button{display:grid;width:27px;height:27px;place-items:center;color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line);border-radius:7px;cursor:pointer}.row-actions button:last-child{color:var(--crm-danger)}@media(max-width:1050px){.strategy-layout{grid-template-columns:1fr}.opportunity-list{position:static}.workspace-list{grid-template-columns:repeat(3,1fr)}.overview-grid{grid-template-columns:1fr 1fr}}@media(max-width:720px){.workspace-list,.strategy-columns{grid-template-columns:1fr}.overview-grid{grid-template-columns:1fr}.page-toolbar{align-items:flex-end;flex-direction:column}.action-list>div{grid-template-columns:12px 1fr auto}.action-list span{grid-column:2}.action-list time{grid-column:3;grid-row:1}.action-list b{grid-column:3;grid-row:2}.action-list .row-actions{grid-column:2/-1}}
.commercial-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;padding:0;background:var(--crm-line)}.commercial-grid>div{display:grid;gap:5px;padding:14px;background:#fff}.commercial-grid small,.history-list small,.history-list time{color:var(--crm-text-muted);font-size:8px}.commercial-grid strong{color:var(--crm-navy);font-size:9px}.commercial-grid span{color:var(--crm-text-muted);font-size:8px}.commercial-wide{grid-column:span 4}.history-list>div{display:grid;grid-template-columns:130px 110px 1fr 100px;gap:12px;align-items:center;padding:12px 16px;border-bottom:1px solid var(--crm-line);font-size:9px}.history-list>div:last-child{border-bottom:0}.history-list strong{color:var(--crm-navy)}@media(max-width:720px){.commercial-grid{grid-template-columns:1fr}.commercial-wide{grid-column:auto}.history-list>div{grid-template-columns:1fr 1fr}}
.sales-subnav{display:flex;width:fit-content;gap:4px;margin:0 0 16px;padding:4px;background:#EEEAE4;border-radius:11px}.sales-subnav button{min-width:138px;padding:9px 15px;color:var(--crm-text-muted);background:transparent;border:0;border-radius:8px;font-size:10px;font-weight:800;cursor:pointer}.sales-subnav button.active{color:var(--crm-navy);background:#fff;box-shadow:0 1px 5px rgba(31,35,41,.1)}.booking-metrics{grid-template-columns:repeat(3,1fr)}.booking-panel>header>div{display:grid;gap:3px}.booking-table-wrap{overflow:auto}.booking-table{min-width:1040px}.booking-table td strong,.booking-table td small{display:block}.booking-table td small{margin-top:4px;color:var(--crm-text-muted);font-size:8px}.booking-table td>span:not(.workspace-badge){color:var(--crm-text-muted);font-size:8px;line-height:1.5}.booking-table .workspace-badge{display:inline-block;margin-top:5px}.icon-edit{display:grid;width:29px;height:29px;place-items:center;color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line);border-radius:7px;cursor:pointer}@media(max-width:720px){.sales-subnav{width:100%}.sales-subnav button{min-width:0;flex:1}.booking-metrics{grid-template-columns:1fr}}
</style>
