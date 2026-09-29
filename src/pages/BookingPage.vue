<script setup lang="ts">
import { bookingTitle } from '@/features/shared/system-labels'
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
import { useI18n, useLocaleMessage, localeMessage } from '@/i18n'
import { salesEnumLabel, salesUnits } from '@/features/shared/sales-i18n'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const app = useAppStore()
const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()
const rows = ref<BookingDto[]>([])
const total = ref(0)
const page = ref(typeof route.query.page === 'string' && Number(route.query.page) > 0 ? Number(route.query.page) : 1)
const pageSize = ref(typeof route.query.pageSize === 'string' && [10, 25, 50].includes(Number(route.query.pageSize)) ? Number(route.query.pageSize) : 10)
const opportunities = ref<OpportunityDto[]>([])
const accounts = ref<AccountSummaryDto[]>([])
const contacts = ref<ContactSummaryDto[]>([])
const loading = ref(false)
const denied = ref(false)
const error = useLocaleMessage()
const requestId = ref('')
const referencesUnavailable = ref(false)
const referenceWarning = computed(() => referencesUnavailable.value
  ? localeMessage('Reference data is temporarily unavailable. The Booking list remains available; create or edit after Account / Contact data recovers.', '参考数据暂时不可用：Booking 列表仍可查看，新建或编辑需待 Account / Contact 恢复。')[locale.value]
  : '')
const status = ref<BookingDto['status'] | 'All'>(typeof route.query.status === 'string' ? route.query.status as BookingDto['status'] | 'All' : 'All')
const bookingSource = ref<BookingSource | 'All'>(typeof route.query.source === 'string' ? route.query.source as BookingSource | 'All' : 'All')
const poDateFilter = ref<'All' | 'missing'>(route.query.actualPoDate === 'missing' ? 'missing' : 'All')
const modalOpen = ref(false)
const editing = ref<BookingDto | null>(null)
const contactModal = ref(false)
const contactAccountId = ref('')
const selectedContactId = ref('')
const busy = ref(false)
const modalError = useLocaleMessage()
const transferOpen = ref(false)
const transferBooking = ref<BookingDto | null>(null)
const transferSites = ref<SiteDto[]>([])
const transferBusy = ref(false)
const transferError = useLocaleMessage()
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
  referencesUnavailable.value = accountResult.status === 'rejected' || contactResult.status === 'rejected'
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
      ...(poDateFilter.value === 'missing' ? { actualPoDateMissing: '1' } : {}),
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
    error.value = mapped.localizedMessage ?? mapped.message
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
    const mapped = mapRequestError(reason); modalError.value = mapped.localizedMessage ?? mapped.message
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
    const mapped = mapRequestError(reason); modalError.value = mapped.localizedMessage ?? mapped.message
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
    const mapped = mapRequestError(reason); transferError.value = mapped.localizedMessage ?? mapped.message
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
    const mapped = mapRequestError(reason); transferError.value = mapped.localizedMessage ?? mapped.message
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
    error.value = mapped.localizedMessage ?? mapped.message
    requestId.value = mapped.requestId
  } finally {
    busy.value = false
  }
}

let restoringRoute = false
function syncUrl() { if (!restoringRoute) void router.replace({ query: { ...route.query, page: String(page.value), pageSize: String(pageSize.value), status: status.value === 'All' ? undefined : status.value, source: bookingSource.value === 'All' ? undefined : bookingSource.value, actualPoDate: poDateFilter.value === 'missing' ? 'missing' : undefined } }) }
function reloadFromFirstPage() { if (restoringRoute) return; page.value = 1; syncUrl(); void load() }
function goPage(value: number) { page.value = value; syncUrl(); void load() }
function changePageSize(value: number) { pageSize.value = value; page.value = 1; syncUrl(); void load() }
watch([status, bookingSource, poDateFilter], reloadFromFirstPage, { flush: 'sync' })
watch(() => [route.query.page, route.query.pageSize, route.query.status, route.query.source, route.query.actualPoDate], ([nextPage, nextSize, nextStatus, nextSource, nextPoDate]) => {
  const restoredPage = typeof nextPage === 'string' && Number(nextPage) > 0 ? Number(nextPage) : 1
  const restoredSize = typeof nextSize === 'string' && [10, 25, 50].includes(Number(nextSize)) ? Number(nextSize) : 10
  const restoredStatus = typeof nextStatus === 'string' ? nextStatus as BookingDto['status'] : 'All'
  const restoredSource = typeof nextSource === 'string' ? nextSource as BookingSource : 'All'
  const restoredPoDate = nextPoDate === 'missing' ? 'missing' : 'All'
  if (restoredPage === page.value && restoredSize === pageSize.value && restoredStatus === status.value && restoredSource === bookingSource.value && restoredPoDate === poDateFilter.value) return
  restoringRoute = true; page.value = restoredPage; pageSize.value = restoredSize; status.value = restoredStatus; bookingSource.value = restoredSource; poDateFilter.value = restoredPoDate; restoringRoute = false; void load()
})

onMounted(async () => {
  await app.loadBootstrap(props.apiClient)
  await loadReferences()
  await load()
})
</script>

<template>
  <div class="booking-page">
    <PageHeader eyebrow="ORDER EXPECTATION" :title="t('booking.title')" :description="t('booking.description')">
      <button v-if="canWrite" class="primary-button" type="button" data-testid="new-booking" :disabled="!referencesReady" @click="openCreate"><Plus :size="14" />{{ t('bookingEditor.new') }}</button>
    </PageHeader>

    <section class="booking-metrics">
      <article><span><PackageCheck :size="17" /></span><div><small>{{ t('booking.total') }}</small><strong>{{ rows.length }}</strong><p>{{ t('booking.scope') }}</p></div></article>
      <article><span><CircleDollarSign :size="17" /></span><div><small>{{ t('booking.confirmedAmount') }}</small><strong v-for="total in confirmedAmounts" :key="total.currency">{{ formatMoney(total.amount, total.currency) }}</strong><p>{{ t('booking.confirmedCount', { count: rows.filter((item) => item.status === 'Confirmed').length }) }}</p></div></article>
      <article><span><CalendarClock :size="17" /></span><div><small>{{ t('booking.pending') }}</small><strong>{{ pendingCount }}</strong><p>{{ t('booking.pendingHint') }}</p></div></article>
    </section>

    <p v-if="referenceWarning" class="reference-warning">{{ referenceWarning }}</p>
    <section class="booking-card">
      <header class="booking-toolbar">
        <div><strong>{{ t('booking.list') }}</strong><small>{{ t('booking.listHint') }}</small></div>
        <div class="booking-filters">
          <select v-model="bookingSource" :aria-label="t('booking.source')"><option value="All">{{ t('booking.allSources') }}</option><option v-for="item in ['Opportunity', 'Upsell']" :key="item" :value="item">{{ salesEnumLabel(item, locale) }}</option></select>
          <select v-model="status" :aria-label="t('booking.status')"><option value="All">{{ t('booking.allStatuses') }}</option><option v-for="item in ['Pending', 'Confirmed', 'Completed', 'Cancelled']" :key="item" :value="item">{{ salesEnumLabel(item, locale) }}</option></select>
          <select v-model="poDateFilter" :aria-label="t('actualPoDate.label')" data-testid="actual-po-date-filter"><option value="All">{{ t('actualPoDate.filterAll') }}</option><option value="missing">{{ t('actualPoDate.filterMissing') }}</option></select>
        </div>
      </header>
      <DataState v-if="loading && !rows.length" type="loading" />
      <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
      <DataState v-else-if="error" type="error" :message="error" :request-id="requestId" @retry="load" />
      <DataState v-else-if="!visibleRows.length" type="empty" :title="t('booking.emptyTitle')" :message="t('booking.emptyMessage')" />
      <div v-else class="table-scroll">
        <table class="crm-table booking-table">
          <thead><tr><th>{{ t('booking.bookingAccount') }}</th><th>{{ t('booking.source') }}</th><th>{{ t('booking.equipment') }}</th><th>{{ t('booking.customerDdl') }}</th><th>{{ t('booking.amountStatus') }}</th><th>{{ t('booking.owner') }}</th><th>{{ t('booking.note') }}</th><th v-if="canWrite">{{ locale === 'en-US' ? 'Actions' : '操作' }}</th></tr></thead>
          <tbody>
            <tr v-for="item in visibleRows" :key="item.id" :data-booking-id="item.id">
              <td><button class="booking-link record-name-link" type="button" :data-open-booking-detail="item.id" @click="openDetail(item)"><span><PackageCheck :size="14" /></span><div><strong>{{ item.id }}</strong><small>{{ bookingTitle(item, locale) }}</small></div></button><small>{{ item.accountName }}</small><RouterLink v-if="item.primaryContactId" :to="{ name: 'contact-detail', params: { contactId: item.primaryContactId } }">{{ item.customerContact }}</RouterLink><span v-else>{{ item.customerContact || t('booking.missingContact') }}</span></td>
              <td><StatusBadge :label="salesEnumLabel(item.source ?? '', locale)" :tone="item.source === 'Opportunity' ? 'info' : 'neutral'" /><RouterLink v-if="item.sourceOpportunityId" :data-booking-source="item.sourceOpportunityId" :to="{ name: 'opportunity-detail', params: { opportunityId: item.sourceOpportunityId } }">{{ item.sourceOpportunityId }}</RouterLink><small v-else>{{ salesEnumLabel('Existing Customer Upsell', locale) }}</small></td>
              <td><strong>{{ item.equipment }}</strong><small>{{ salesEnumLabel(item.bookingType ?? '', locale) }} · {{ item.quantity }} {{ salesUnits(locale) }}</small><small v-if="item.installedToolId" class="installed-tool-link">{{ locale === 'en-US' ? 'Installed tool' : '已安装设备' }} · {{ item.installedToolId }}</small></td>
              <td><strong>{{ formatDisplayDate(item.ddl) }}</strong><small>{{ t('booking.entered') }} {{ formatDisplayDate(item.bookingDate) }}</small><small v-if="item.actualPoDate || item.status === 'Confirmed' || item.status === 'Completed'" :data-booking-actual-po-date="item.id">{{ t('actualPoDate.label') }} {{ item.actualPoDate ? formatDisplayDate(item.actualPoDate) : t('actualPoDate.missing') }}</small></td>
              <td><strong>{{ formatMoney(item.amount, item.currency) }}</strong><small v-if="item.currency !== 'CNY'" :data-booking-amount-cny="item.id">{{ item.amountCny ? `${t('bookingEditor.amountCny')} ${formatMoney(item.amountCny, 'CNY')}` : t('booking.amountCnyPending') }}</small><StatusBadge :label="salesEnumLabel(item.status, locale)" :tone="item.status === 'Confirmed' || item.status === 'Completed' ? 'positive' : item.status === 'Cancelled' ? 'danger' : 'warning'" /></td>
              <td>{{ personnelDisplayName(item.owner) }}</td>
              <td>{{ item.note || '—' }}</td>
              <td v-if="canWrite">
                <div class="booking-actions">
                  <button v-if="item.status !== 'Completed'" class="edit-button" type="button" :aria-label="t('booking.edit')" :disabled="!referencesReady" @click="openEdit(item)"><Pencil :size="13" /></button>
                  <button v-if="item.status === 'Confirmed' && !item.installedToolId && item.bookingType === 'Equipment'" class="convert-button" type="button" :data-testid="`convert-${item.id}`" @click="openTransfer(item)"><ArrowRight :size="13" />{{ t('booking.convertTool') }}</button>
                  <button v-if="item.status === 'Confirmed' && !item.installedToolId && item.bookingType === 'Service'" class="convert-button" type="button" :data-testid="`complete-service-${item.id}`" :disabled="busy" @click="completeService(item)"><CheckCircle2 :size="13" />{{ t('booking.serviceComplete') }}</button>
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
