<script setup lang="ts">
import { personnelDisplayName, personnelForRole } from '@/demo/personnel'
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowRight, CalendarClock, CheckCircle2, CircleDollarSign, PackageCheck, Pencil, Plus } from '@lucide/vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api as defaultApi, type CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import type { AccountSummaryDto, BookingDto, BookingSource, ContactSummaryDto, CreateContactInput, OpportunityDto, SiteDto, UpsertBookingInput } from '@/types/crm'
import type { ConvertBookingToInstalledToolInput } from '@/types/workspaces'
import PageHeader from '@/design-system/PageHeader.vue'
import DataState from '@/design-system/DataState.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import BookingEditorModal from '@/features/opportunities/BookingEditorModal.vue'
import BookingInstalledToolModal from '@/features/opportunities/BookingInstalledToolModal.vue'
import ContactModal from '@/features/contacts/ContactModal.vue'
import { formatMoney, moneyByCurrency } from '@/domain/money'
import { formatDisplayDate } from '@/domain/time'
import { readAllPages } from '@/features/shared/read-all-pages'
import PaginationControls from '@/features/shared/PaginationControls.vue'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const app = useAppStore()
const route = useRoute()
const router = useRouter()
const rows = ref<BookingDto[]>([])
const total = ref(0)
const page = ref(typeof route.query.page === 'string' && Number(route.query.page) > 0 ? Number(route.query.page) : 1)
const pageSize = ref(typeof route.query.pageSize === 'string' && [10, 25, 50].includes(Number(route.query.pageSize)) ? Number(route.query.pageSize) : 10)
const opportunities = ref<OpportunityDto[]>([])
const accounts = ref<AccountSummaryDto[]>([])
const contacts = ref<ContactSummaryDto[]>([])
const loading = ref(false)
const denied = ref(false)
const error = ref('')
const requestId = ref('')
const referenceWarning = ref('')
const status = ref<BookingDto['status'] | 'All'>(typeof route.query.status === 'string' ? route.query.status as BookingDto['status'] | 'All' : 'All')
const bookingSource = ref<BookingSource | 'All'>(typeof route.query.source === 'string' ? route.query.source as BookingSource | 'All' : 'All')
const modalOpen = ref(false)
const editing = ref<BookingDto | null>(null)
const contactModal = ref(false)
const contactAccountId = ref('')
const selectedContactId = ref('')
const busy = ref(false)
const modalError = ref('')
const transferOpen = ref(false)
const transferBooking = ref<BookingDto | null>(null)
const transferSites = ref<SiteDto[]>([])
const transferBusy = ref(false)
const transferError = ref('')
const canWrite = computed(() => app.can('deal:write'))
const engineerOptions = computed(() => (app.bootstrap?.personnel ?? personnelForRole('Engineer'))
  .filter((person) => person.role === 'Engineer' && person.availableForAssignment))
const referencesReady = computed(() => accounts.value.length > 0 && contacts.value.length > 0)
const visibleRows = computed(() => rows.value)
const confirmedAmounts = computed(() => moneyByCurrency(rows.value.filter((item) => item.status === 'Confirmed')))
const pendingCount = computed(() => rows.value.filter((item) => item.status === 'Pending').length)
let sequence = 0

async function loadReferences() {
  const [accountResult, contactResult] = await Promise.allSettled([
    readAllPages((page, pageSize) => props.apiClient.listAccounts({ page, pageSize })),
    readAllPages((page, pageSize) => props.apiClient.listContacts({ contactStatus: 'Active', page, pageSize })),
  ])
  accounts.value = accountResult.status === 'fulfilled' ? accountResult.value : []
  contacts.value = contactResult.status === 'fulfilled' ? contactResult.value : []
  referenceWarning.value = accountResult.status === 'rejected' || contactResult.status === 'rejected'
    ? '参考数据暂时不可用：Booking 列表仍可查看，新建或编辑需待 Account / Contact 恢复。'
    : ''
  try { opportunities.value = (await props.apiClient.listPipeline({})).data.opportunities }
  catch { opportunities.value = [] }
}
async function load() {
  const current = ++sequence
  loading.value = true
  denied.value = false
  error.value = ''
  try {
    const contactId = typeof route.query.contactId === 'string' ? route.query.contactId : ''
    const accountId = typeof route.query.accountId === 'string' ? route.query.accountId : ''
    const result = await props.apiClient.listBookings({
      contactId, accountId, status: status.value, source: bookingSource.value,
      page: page.value, pageSize: pageSize.value,
    })
    if (current !== sequence) return
    rows.value = result.data.items
    total.value = result.meta?.total ?? rows.value.length
  } catch (reason) {
    if (current !== sequence) return
    const mapped = mapRequestError(reason)
    rows.value = []
    opportunities.value = []
    error.value = mapped.message
    requestId.value = mapped.requestId
    denied.value = mapped.denied
  } finally {
    if (current === sequence) loading.value = false
  }
}
function openCreate() {
  editing.value = null
  selectedContactId.value = ''
  modalError.value = ''
  modalOpen.value = true
}
function openEdit(booking: BookingDto) {
  editing.value = booking
  selectedContactId.value = booking.primaryContactId ?? ''
  modalError.value = ''
  modalOpen.value = true
}
function openContact(accountId: string) {
  contactAccountId.value = accountId
  modalError.value = ''
  contactModal.value = true
}
async function saveContact(input: CreateContactInput) {
  busy.value = true
  modalError.value = ''
  try {
    const created = await props.apiClient.createContact(input)
    selectedContactId.value = created.data.id
    contacts.value = await readAllPages((page, pageSize) => props.apiClient.listContacts({ contactStatus: 'Active', page, pageSize }))
    contactModal.value = false
  } catch (reason) {
    modalError.value = mapRequestError(reason).message
  } finally {
    busy.value = false
  }
}
function openDetail(booking: BookingDto) { void router.push({ name: 'booking-detail', params: { bookingId: booking.id } }) }
async function saveBooking(input: UpsertBookingInput) {
  busy.value = true
  modalError.value = ''
  try {
    if (editing.value) await props.apiClient.updateBooking(editing.value.id, input, editing.value.modified)
    else await props.apiClient.createBooking(input)
    modalOpen.value = false
    editing.value = null
    await load()
  } catch (reason) {
    modalError.value = mapRequestError(reason).message
  } finally {
    busy.value = false
  }
}
async function openTransfer(booking: BookingDto) {
  transferBooking.value = booking
  transferSites.value = []
  transferError.value = ''
  transferOpen.value = true
  try {
    transferSites.value = (await props.apiClient.getAccount360(booking.accountId)).data.sites
  } catch (reason) {
    transferError.value = mapRequestError(reason).message
  }
}
async function transferToInstalledTool(input: ConvertBookingToInstalledToolInput) {
  if (!transferBooking.value) return
  transferBusy.value = true
  transferError.value = ''
  try {
    await props.apiClient.convertBookingToInstalledTool(transferBooking.value.id, input, transferBooking.value.modified)
    transferOpen.value = false
    transferBooking.value = null
    await load()
  } catch (reason) {
    transferError.value = mapRequestError(reason).message
  } finally {
    transferBusy.value = false
  }
}

async function completeService(booking: BookingDto) {
  busy.value = true
  error.value = ''
  try {
    await props.apiClient.completeServiceBooking(booking.id, booking.modified)
    await load()
  } catch (reason) {
    const mapped = mapRequestError(reason)
    error.value = mapped.message
    requestId.value = mapped.requestId
  } finally {
    busy.value = false
  }
}

let restoringRoute = false
function syncUrl() { if (!restoringRoute) void router.replace({ query: { ...route.query, page: String(page.value), pageSize: String(pageSize.value), status: status.value === 'All' ? undefined : status.value, source: bookingSource.value === 'All' ? undefined : bookingSource.value } }) }
function reloadFromFirstPage() { if (restoringRoute) return; page.value = 1; syncUrl(); void load() }
function goPage(value: number) { page.value = value; syncUrl(); void load() }
function changePageSize(value: number) { pageSize.value = value; page.value = 1; syncUrl(); void load() }
watch([status, bookingSource], reloadFromFirstPage, { flush: 'sync' })
watch(() => [route.query.page, route.query.pageSize, route.query.status, route.query.source], ([nextPage, nextSize, nextStatus, nextSource]) => {
  const restoredPage = typeof nextPage === 'string' && Number(nextPage) > 0 ? Number(nextPage) : 1
  const restoredSize = typeof nextSize === 'string' && [10, 25, 50].includes(Number(nextSize)) ? Number(nextSize) : 10
  const restoredStatus = typeof nextStatus === 'string' ? nextStatus as BookingDto['status'] : 'All'
  const restoredSource = typeof nextSource === 'string' ? nextSource as BookingSource : 'All'
  if (restoredPage === page.value && restoredSize === pageSize.value && restoredStatus === status.value && restoredSource === bookingSource.value) return
  restoringRoute = true; page.value = restoredPage; pageSize.value = restoredSize; status.value = restoredStatus; bookingSource.value = restoredSource; restoringRoute = false; void load()
})

onMounted(async () => {
  await app.loadBootstrap(props.apiClient)
  await loadReferences()
  await load()
})
</script>

<template>
  <div class="booking-page">
    <PageHeader eyebrow="ORDER EXPECTATION" title="Booking" description="统一管理来自 Won Opportunity 或现有客户 Upsell 的设备订单预期。">
      <button v-if="canWrite" class="primary-button" type="button" data-testid="new-booking" :disabled="!referencesReady" @click="openCreate"><Plus :size="14" />新增 Booking</button>
    </PageHeader>

    <section class="booking-metrics">
      <article><span><PackageCheck :size="17" /></span><div><small>Booking 总数</small><strong>{{ rows.length }}</strong><p>当前权限范围</p></div></article>
      <article><span><CircleDollarSign :size="17" /></span><div><small>Confirmed 金额</small><strong v-for="total in confirmedAmounts" :key="total.currency">{{ formatMoney(total.amount, total.currency) }}</strong><p>{{ rows.filter((item) => item.status === 'Confirmed').length }} 条已确认</p></div></article>
      <article><span><CalendarClock :size="17" /></span><div><small>待确认</small><strong>{{ pendingCount }}</strong><p>等待客户或内部确认</p></div></article>
    </section>

    <p v-if="referenceWarning" class="reference-warning">{{ referenceWarning }}</p>
    <section class="booking-card">
      <header class="booking-toolbar">
        <div><strong>Booking List</strong><small>Opportunity 必须关联 Won Opportunity；Upsell 直接关联现有客户。</small></div>
        <div class="booking-filters">
          <select v-model="bookingSource" aria-label="Booking 来源筛选"><option value="All">全部来源</option><option>Opportunity</option><option>Upsell</option></select>
          <select v-model="status" aria-label="Booking 状态筛选"><option value="All">全部状态</option><option>Pending</option><option>Confirmed</option><option>Completed</option><option>Cancelled</option></select>
        </div>
      </header>
      <DataState v-if="loading && !rows.length" type="loading" />
      <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
      <DataState v-else-if="error" type="error" :message="error" :request-id="requestId" @retry="load" />
      <DataState v-else-if="!visibleRows.length" type="empty" title="没有匹配的 Booking" message="调整筛选条件，或从已赢单 Opportunity 创建设备 Booking。" />
      <div v-else class="table-scroll">
        <table class="crm-table booking-table">
          <thead><tr><th>Booking / 客户</th><th>来源</th><th>设备需求</th><th>客户 DDL</th><th>金额 / 状态</th><th>Owner</th><th>备注</th><th v-if="canWrite">操作</th></tr></thead>
          <tbody>
            <tr v-for="item in visibleRows" :key="item.id" :data-booking-id="item.id">
              <td><button class="booking-link record-name-link" type="button" :data-open-booking-detail="item.id" @click="openDetail(item)"><span><PackageCheck :size="14" /></span><div><strong>{{ item.id }}</strong><small>{{ item.title }}</small></div></button><small>{{ item.accountName }}</small><RouterLink v-if="item.primaryContactId" :to="{ name: 'contact-detail', params: { contactId: item.primaryContactId } }">{{ item.customerContact }}</RouterLink><span v-else>{{ item.customerContact || '联系人缺失' }}</span></td>
              <td><StatusBadge :label="item.source" :tone="item.source === 'Opportunity' ? 'info' : 'neutral'" /><RouterLink v-if="item.sourceOpportunityId" :data-booking-source="item.sourceOpportunityId" :to="{ name: 'opportunity-detail', params: { opportunityId: item.sourceOpportunityId } }">{{ item.sourceOpportunityId }}</RouterLink><small v-else>Existing Customer Upsell</small></td>
              <td><strong>{{ item.equipment }}</strong><small>{{ item.bookingType }} · {{ item.quantity }} 台 / 项</small><small v-if="item.installedToolId" class="installed-tool-link">Installed Tool · {{ item.installedToolId }}</small></td>
              <td><strong>{{ formatDisplayDate(item.ddl) }}</strong><small>录入 {{ formatDisplayDate(item.bookingDate) }}</small></td>
              <td><strong>{{ formatMoney(item.amount, item.currency) }}</strong><StatusBadge :label="item.status" :tone="item.status === 'Confirmed' || item.status === 'Completed' ? 'positive' : item.status === 'Cancelled' ? 'danger' : 'warning'" /></td>
              <td>{{ personnelDisplayName(item.owner) }}</td>
              <td>{{ item.note || '—' }}</td>
              <td v-if="canWrite">
                <div class="booking-actions">
                  <button v-if="item.status !== 'Completed'" class="edit-button" type="button" aria-label="编辑 Booking" :disabled="!referencesReady" @click="openEdit(item)"><Pencil :size="13" /></button>
                  <button v-if="item.status === 'Confirmed' && !item.installedToolId && item.bookingType === 'Equipment'" class="convert-button" type="button" :data-testid="`convert-${item.id}`" @click="openTransfer(item)"><ArrowRight :size="13" />转入 Installed Tool</button>
                  <button v-if="item.status === 'Confirmed' && !item.installedToolId && item.bookingType === 'Service'" class="convert-button" type="button" :data-testid="`complete-service-${item.id}`" :disabled="busy" @click="completeService(item)"><CheckCircle2 :size="13" />服务完成</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <PaginationControls v-if="!denied && !error && total > pageSize" :page="page" :page-size="pageSize" :total="total" @change="goPage" @page-size-change="changePageSize" />
    </section>

    <BookingEditorModal
      v-if="modalOpen"
      :booking="editing"
      :accounts="accounts"
      :opportunities="opportunities"
      :contacts="contacts"
      :selected-contact-id="selectedContactId"
      :default-owner="app.bootstrap?.user.id ?? ''"
      :busy="busy"
      :error="modalError"
      @close="modalOpen = false"
      @create-contact="openContact"
      @submit="saveBooking"
    />
    <ContactModal
      v-if="contactModal"
      :accounts="accounts"
      :sites="[]"
      :contacts="contacts"
      :fixed-account-id="contactAccountId"
      :busy="busy"
      :error="modalError"
      @close="contactModal = false"
      @submit="saveContact"
    />
    <BookingInstalledToolModal
      v-if="transferOpen && transferBooking"
      :booking="transferBooking"
      :sites="transferSites"
      :engineers="engineerOptions"
      :busy="transferBusy"
      :error="transferError"
      @close="transferOpen = false"
      @submit="transferToInstalledTool"
    />
  </div>
</template>

<style scoped>
.booking-page{display:grid;gap:14px}.booking-page :deep(.page-header){margin-bottom:0}.booking-page .primary-button{display:flex;align-items:center;gap:6px}.booking-page .primary-button:disabled{opacity:.55;cursor:not-allowed}.booking-metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.booking-metrics article{display:flex;align-items:center;gap:11px;padding:14px 15px;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.booking-metrics article>span{display:grid;width:38px;height:38px;place-items:center;color:var(--crm-brand-ink);background:var(--crm-teal-soft);border-radius:10px}.booking-metrics article>div{display:grid;gap:2px}.booking-metrics small,.booking-metrics p{margin:0;color:var(--crm-text-muted);font-size:8px}.booking-metrics strong{color:var(--crm-navy);font-size:16px}.reference-warning{margin:0;padding:10px 12px;color:#7b5c15;background:#fff8e8;border:1px solid #ead49f;border-radius:9px;font-size:10px}.booking-card{overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.booking-toolbar{display:flex;align-items:center;justify-content:space-between;gap:15px;padding:14px 16px;border-bottom:1px solid var(--crm-line)}.booking-toolbar>div:first-child{display:grid;gap:3px}.booking-toolbar strong{color:var(--crm-navy);font-size:13px}.booking-toolbar small{color:var(--crm-text-muted);font-size:8px}.booking-filters{display:flex;gap:7px}.booking-filters select{height:38px;padding:0 10px;background:#fff;border:1px solid var(--crm-line);border-radius:10px;font:inherit;font-size:9px}.booking-table{min-width:1180px}.booking-table td>strong,.booking-table td>small,.booking-table td>a,.booking-table td>span{display:block;margin-top:3px}.booking-table td>a,.installed-tool-link{color:var(--crm-link)!important;font-size:9px}.booking-table td>small,.booking-table td>span:not(.status-badge){color:var(--crm-text-muted);font-size:8px;line-height:1.5}.booking-actions{display:flex;align-items:center;gap:6px}.edit-button{display:grid;width:29px;height:29px;place-items:center;color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line);border-radius:7px;cursor:pointer}.convert-button{display:inline-flex;align-items:center;gap:5px;min-height:29px;padding:0 9px;color:#fff;background:var(--crm-teal);border:0;border-radius:7px;font-size:8px;font-weight:800;white-space:nowrap;cursor:pointer}.edit-button:disabled{opacity:.45;cursor:not-allowed}@media(max-width:900px){.booking-toolbar{align-items:stretch;flex-direction:column}.booking-filters{flex-wrap:wrap}.booking-metrics{grid-template-columns:1fr}}@media(max-width:560px){.booking-filters{display:grid}.booking-filters label{min-width:0}}
.booking-link{display:flex;min-width:180px;align-items:center;gap:8px;padding:0;color:inherit;background:transparent;border:0;font:inherit;text-align:left;cursor:pointer}.booking-link>span{display:grid;width:30px;height:30px;place-items:center;color:var(--crm-brand-ink);background:var(--crm-teal-soft);border-radius:9px}.booking-link>div{display:grid;gap:3px}.booking-link strong{color:var(--crm-link);font-size:12px}.booking-link small{color:var(--crm-text-muted);font-size:9px}.booking-link:hover strong{color:var(--crm-link-hover);text-decoration:none}
</style>
