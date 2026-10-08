<script setup lang="ts">
import { bookingTitle, systemValueLabel } from '@/features/shared/system-labels'
import { personnelDisplayName } from '@/demo/personnel'
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft, Building2, CalendarClock, CircleDollarSign, Cpu, ExternalLink, PackageCheck, UserRound } from '@lucide/vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api as defaultApi, type CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import type { AccountSummaryDto, BookingDto, ContactSummaryDto, CreateContactInput, OpportunityDto, SetActualPoDateInput, SetBookingAmountCnyInput, Tone, UpsertBookingInput } from '@/types/crm'
import type { InstalledToolDto } from '@/types/workspaces'
import DataState from '@/design-system/DataState.vue'
import PageHeader from '@/design-system/PageHeader.vue'
import SectionCard from '@/design-system/SectionCard.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import ActualPoDateModal from '@/features/opportunities/ActualPoDateModal.vue'
import BookingAmountCnyModal from '@/features/opportunities/BookingAmountCnyModal.vue'
import BookingEditorModal from '@/features/opportunities/BookingEditorModal.vue'
import ContactModal from '@/features/contacts/ContactModal.vue'
import { readAllPages } from '@/features/shared/read-all-pages'
import { formatMoney } from '@/domain/money'
import { formatDisplayDate } from '@/domain/time'
import { useAppStore } from '@/stores/app'
import { useI18n, useLocaleMessage } from '@/i18n'
import { salesEnumLabel, salesUnits } from '@/features/shared/sales-i18n'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const route = useRoute()
const router = useRouter()
const app = useAppStore()
const { locale, t, message } = useI18n()
const canDelete = computed(() => app.bootstrap?.user.role === 'Manager')
const booking = ref<BookingDto | null>(null)
const tools = ref<InstalledToolDto[]>([])
const loading = ref(false)
const error = useLocaleMessage()
const requestId = ref('')
const deleting = ref(false), deleteError = useLocaleMessage(), deleteRequestId = ref('')
const equipmentWarning = useLocaleMessage()
const poDateModal = ref(false), poDateBusy = ref(false), poDateError = useLocaleMessage()
// Only a Manager fills in or corrects the date on a confirmed order's PO.
const canSetActualPoDate = computed(() => app.bootstrap?.user.role === 'Manager'
  && (booking.value?.status === 'Confirmed' || booking.value?.status === 'Completed'))
const amountCnyModal = ref(false), amountCnyBusy = ref(false), amountCnyError = useLocaleMessage()
// A CNY order's amount already is its CNY amount; a Manager fills in the rest, Completed orders included.
const canSetAmountCny = computed(() => canSetActualPoDate.value && booking.value?.currency !== 'CNY')
const equipmentWarningRequestId = ref('')
// Same rule as the edit button on the Booking list.
const canEdit = computed(() => app.can('deal:write') && booking.value?.status !== 'Completed')
const editOpen = ref(false), editBusy = ref(false), editError = useLocaleMessage()
const editAccounts = ref<AccountSummaryDto[]>([]), editContacts = ref<ContactSummaryDto[]>([]), editOpportunities = ref<OpportunityDto[]>([])
const contactModal = ref(false), contactAccountId = ref(''), selectedContactId = ref('')
let loadSequence = 0
async function deleteBooking() {
  if (!booking.value || deleting.value || !window.confirm(t('detail.confirmDeleteBooking', { id: booking.value.id }))) return
  deleting.value = true
  deleteError.value = ''
  deleteRequestId.value = ''
  try {
    await props.apiClient.deleteBooking(booking.value.id)
    await router.push({ name: 'booking' })
  } catch (reason) {
    const mapped = mapRequestError(reason)
    deleteError.value = mapped.localizedMessage ?? mapped.message
    deleteRequestId.value = mapped.requestId
  } finally {
    deleting.value = false
  }
}
async function saveActualPoDate(input: SetActualPoDateInput) {
  if (!booking.value || poDateBusy.value) return
  poDateBusy.value = true
  poDateError.value = ''
  try {
    booking.value = (await props.apiClient.setBookingActualPoDate(booking.value.id, input, booking.value.modified)).data
    poDateModal.value = false
  } catch (reason) {
    const mapped = mapRequestError(reason)
    poDateError.value = mapped.localizedMessage ?? mapped.message
  } finally {
    poDateBusy.value = false
  }
}
function openActualPoDate() {
  poDateError.value = ''
  poDateModal.value = true
}
async function saveAmountCny(input: SetBookingAmountCnyInput) {
  if (!booking.value || amountCnyBusy.value) return
  amountCnyBusy.value = true
  amountCnyError.value = ''
  try {
    booking.value = (await props.apiClient.setBookingAmountCny(booking.value.id, input, booking.value.modified)).data
    amountCnyModal.value = false
  } catch (reason) {
    const mapped = mapRequestError(reason)
    amountCnyError.value = mapped.localizedMessage ?? mapped.message
  } finally {
    amountCnyBusy.value = false
  }
}
function openAmountCny() {
  amountCnyError.value = ''
  amountCnyModal.value = true
}
const readActiveContacts = () => readAllPages((page, pageSize) => props.apiClient.listContacts({ contactStatus: 'Active', page, pageSize }))
async function openEdit() {
  if (!booking.value || editBusy.value) return
  editBusy.value = true
  editError.value = ''
  try {
    ;[editAccounts.value, editContacts.value] = await Promise.all([
      readAllPages((page, pageSize) => props.apiClient.listAccounts({ page, pageSize })),
      readActiveContacts(),
    ])
    selectedContactId.value = booking.value.primaryContactId ?? ''
    editOpen.value = true
  } catch (reason) {
    const mapped = mapRequestError(reason)
    editError.value = mapped.localizedMessage ?? mapped.message
  } finally {
    editBusy.value = false
  }
}
async function saveBooking(input: UpsertBookingInput) {
  if (!booking.value || editBusy.value) return
  editBusy.value = true
  editError.value = ''
  try {
    await props.apiClient.updateBooking(booking.value.id, input, booking.value.modified)
    editOpen.value = false
    await load()
  } catch (reason) {
    const mapped = mapRequestError(reason)
    editError.value = mapped.localizedMessage ?? mapped.message
  } finally {
    editBusy.value = false
  }
}
function openContact(accountId: string) {
  contactAccountId.value = accountId
  editError.value = ''
  contactModal.value = true
}
async function saveContact(input: CreateContactInput) {
  editBusy.value = true
  editError.value = ''
  try {
    selectedContactId.value = (await props.apiClient.createContact(input)).data.id
    editContacts.value = await readActiveContacts()
    contactModal.value = false
  } catch (reason) {
    const mapped = mapRequestError(reason)
    editError.value = mapped.localizedMessage ?? mapped.message
  } finally {
    editBusy.value = false
  }
}
const bookingId = computed(() => String(route.params.bookingId || ''))
const relatedTools = computed(() => tools.value.filter((item) => item.sourceBookingId === bookingId.value || item.id === booking.value?.installedToolId))
const statusTone = computed<Tone>(() => booking.value?.status === 'Confirmed' || booking.value?.status === 'Completed' ? 'positive' : booking.value?.status === 'Cancelled' ? 'danger' : 'warning')

async function load() {
  const sequence = ++loadSequence
  loading.value = true
  error.value = ''
  requestId.value = ''
  equipmentWarning.value = ''; equipmentWarningRequestId.value = ''
  booking.value = null
  tools.value = []
  const pipelineResult = await Promise.resolve(props.apiClient.listPipeline({})).then(
    (value) => ({ status: 'fulfilled' as const, value }),
    (reason) => ({ status: 'rejected' as const, reason }),
  )
  if (sequence !== loadSequence) return
  if (pipelineResult.status === 'rejected') {
    const mapped = mapRequestError(pipelineResult.reason)
    error.value = mapped.localizedMessage ?? mapped.message
    requestId.value = mapped.requestId
  } else {
    booking.value = pipelineResult.value.data.bookings.find((item) => item.id === bookingId.value) ?? null
    editOpportunities.value = pipelineResult.value.data.opportunities
    if (!booking.value) error.value = message('detail.notFoundBookingId', { id: bookingId.value })
  }
  if (booking.value?.installedToolId) {
    try {
      const toolResult = await props.apiClient.getInstalledTool(booking.value.installedToolId)
      if (sequence !== loadSequence) return
      tools.value = [toolResult.data]
    } catch (reason) {
      if (sequence !== loadSequence) return
      const mapped = mapRequestError(reason)
      equipmentWarning.value = mapped.localizedMessage ?? mapped.message
      equipmentWarningRequestId.value = mapped.requestId
    }
  }
  if (sequence === loadSequence) loading.value = false
}

watch(bookingId, load)
onMounted(load)
</script>

<template>
  <div class="booking-detail-page">
    <DataState v-if="loading && !booking" type="loading" />
    <DataState v-else-if="error || !booking" type="error" :message="error || t('detail.notFoundBooking')" :request-id="requestId" @retry="load" />
    <template v-else>
      <RouterLink class="detail-back-button" :to="{ name: 'booking' }"><ArrowLeft :size="14" />{{ t('detail.backBookings') }}</RouterLink>
      <PageHeader eyebrow="BOOKING DETAIL" :title="bookingTitle(booking, locale)" :description="`${booking.id} · ${booking.accountName} · ${t('detail.owner')} ${personnelDisplayName(booking.owner)}`"><button v-if="canEdit" class="secondary-button" type="button" data-testid="edit-booking" :disabled="editBusy" @click="openEdit">{{ t('bookingEditor.edit') }}</button><button v-if="canSetActualPoDate" class="secondary-button" type="button" data-testid="set-actual-po-date" @click="openActualPoDate">{{ t('actualPoDate.action') }}</button><button v-if="canSetAmountCny" class="secondary-button" type="button" data-testid="set-amount-cny" @click="openAmountCny">{{ t('amountCny.action') }}</button><button v-if="canDelete" class="danger-button" type="button" data-delete-booking :disabled="deleting" @click="deleteBooking">{{ t('detail.delete') }} Booking</button></PageHeader>
      <p v-if="deleteError" class="form-error" data-delete-error>{{ deleteError }}<small v-if="deleteRequestId">{{ locale === 'en-US' ? 'Request ID' : '请求编号' }} {{ deleteRequestId }}</small></p>
      <p v-if="editError && !editOpen && !contactModal" class="form-error" data-edit-error>{{ editError }}</p>

      <section class="booking-summary">
        <article><span><PackageCheck :size="18" /></span><div><small>{{ t('detail.currentStatus') }}</small><StatusBadge :label="salesEnumLabel(booking.status, locale)" :tone="statusTone" /></div></article>
        <article><span><CircleDollarSign :size="18" /></span><div><small>{{ t('detail.bookingAmount') }}</small><strong>{{ formatMoney(booking.amount, booking.currency) }}</strong><small v-if="booking.currency !== 'CNY'" data-testid="booking-amount-cny">{{ booking.amountCny ? `${t('bookingEditor.amountCny')} ${formatMoney(booking.amountCny, 'CNY')}` : t('booking.amountCnyPending') }}</small></div></article>
        <article><span><CalendarClock :size="18" /></span><div><small>{{ t('detail.customerDdl') }}</small><strong>{{ formatDisplayDate(booking.ddl) }}</strong></div></article>
        <article><span><Cpu :size="18" /></span><div><small>{{ t('detail.equipmentQuantity') }}</small><strong>{{ booking.quantity }} {{ salesUnits(locale) }}</strong></div></article>
      </section>

      <div class="booking-detail-grid">
        <div class="booking-main">
          <SectionCard :title="t('detail.bookingInfo')" eyebrow="INFORMATION">
            <dl class="booking-fields">
              <div><dt>{{ t('detail.bookingNumber') }}</dt><dd>{{ booking.id }}</dd></div><div><dt>{{ t('detail.enteredDate') }}</dt><dd>{{ formatDisplayDate(booking.bookingDate) }}</dd></div>
              <div><dt>{{ t('actualPoDate.label') }}</dt><dd data-testid="booking-actual-po-date">{{ booking.actualPoDate ? formatDisplayDate(booking.actualPoDate) : (booking.status === 'Confirmed' || booking.status === 'Completed' ? t('actualPoDate.missing') : '—') }}<small v-if="booking.actualPoDateSource">{{ t(`actualPoDate.source.${booking.actualPoDateSource}`) }}</small></dd></div>
              <div v-if="booking.actualPoDateNote"><dt>{{ t('actualPoDate.reason') }}</dt><dd data-testid="booking-actual-po-date-note">{{ booking.actualPoDateNote }}</dd></div>
              <div v-if="booking.amountCnyNote"><dt>{{ t('amountCny.reason') }}</dt><dd data-testid="booking-amount-cny-note">{{ booking.amountCnyNote }}</dd></div>
              <div><dt>{{ t('detail.equipmentNeed') }}</dt><dd>{{ booking.equipment }}</dd></div><div><dt>{{ t('detail.quantity') }}</dt><dd>{{ booking.quantity }} {{ salesUnits(locale) }}</dd></div>
              <div><dt>{{ t('detail.sourceType') }}</dt><dd><StatusBadge :label="salesEnumLabel(booking.source, locale)" :tone="booking.source === 'Opportunity' ? 'info' : 'neutral'" /></dd></div>
              <div><dt>{{ t('detail.owner') }}</dt><dd>{{ personnelDisplayName(booking.owner) }}</dd></div><div class="wide"><dt>{{ t('detail.notes') }}</dt><dd>{{ booking.note || '—' }}</dd></div>
            </dl>
          </SectionCard>
          <SectionCard :title="t('detail.relatedBusiness')" eyebrow="RELATED BUSINESS">
            <div class="related-links">
              <RouterLink :to="{ name: 'account-detail', params: { accountId: booking.accountId } }"><span><Building2 :size="15" />{{ t('detail.account') }}</span><strong>{{ booking.accountName }}</strong><ExternalLink :size="13" /></RouterLink>
              <RouterLink v-if="booking.primaryContactId" :to="{ name: 'contact-detail', params: { contactId: booking.primaryContactId } }"><span><UserRound :size="15" />{{ t('detail.primaryContact') }}</span><strong>{{ booking.customerContact }}</strong><ExternalLink :size="13" /></RouterLink>
              <RouterLink v-if="booking.sourceOpportunityId" :to="{ name: 'opportunity-detail', params: { opportunityId: booking.sourceOpportunityId } }"><span><CircleDollarSign :size="15" />{{ t('detail.sourceOpportunity') }}</span><strong>{{ booking.sourceOpportunityId }}</strong><ExternalLink :size="13" /></RouterLink>
            </div>
          </SectionCard>
        </div>
        <aside>
          <SectionCard :title="t('detail.equipmentRelation')" eyebrow="INSTALLED TOOL">
            <p v-if="equipmentWarning" class="equipment-note">{{ equipmentWarning }}<small v-if="equipmentWarningRequestId">{{ locale === 'en-US' ? 'Request ID' : '请求编号' }}: {{ equipmentWarningRequestId }}</small></p>
            <div v-else-if="relatedTools.length" class="tool-list">
              <article v-for="tool in relatedTools" :key="tool.id" :data-booking-tool="tool.id"><header><strong>{{ tool.model }}</strong><StatusBadge :label="salesEnumLabel(tool.status, locale)" :tone="tool.status === 'Active' ? 'positive' : 'warning'" /></header><b>{{ tool.serial }}</b><p>{{ tool.site }} · {{ systemValueLabel(tool.location, locale) }}</p><small>{{ personnelDisplayName(tool.engineerOwner) }}</small></article>
            </div>
            <p v-else class="equipment-note">{{ t('detail.notConvertedTool') }}</p>
            <RouterLink class="installed-link" :to="{ name: 'installed-tools', query: { accountId: booking.accountId } }">{{ t('detail.viewEquipment') }}<ExternalLink :size="13" /></RouterLink>
          </SectionCard>
        </aside>
      </div>
      <ActualPoDateModal v-if="poDateModal" :current-date="booking.actualPoDate" :busy="poDateBusy" :error="poDateError" @close="poDateModal = false" @submit="saveActualPoDate" />
      <BookingAmountCnyModal v-if="amountCnyModal" :current-amount="booking.amountCny" :busy="amountCnyBusy" :error="amountCnyError" @close="amountCnyModal = false" @submit="saveAmountCny" />
      <BookingEditorModal v-if="editOpen" :booking="booking" :accounts="editAccounts" :opportunities="editOpportunities" :contacts="editContacts" :selected-contact-id="selectedContactId" :default-owner="app.bootstrap?.user.id ?? ''" :busy="editBusy" :error="editError" @close="editOpen = false" @create-contact="openContact" @submit="saveBooking" />
      <ContactModal v-if="contactModal" :accounts="editAccounts" :sites="[]" :contacts="editContacts" :fixed-account-id="contactAccountId" :busy="editBusy" :error="editError" @close="contactModal = false" @submit="saveContact" />
    </template>
  </div>
</template>

<style scoped>
.booking-detail-page{display:grid;gap:14px}.detail-back-button{justify-self:start}.booking-detail-page :deep(.page-header){margin-bottom:0}.booking-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.booking-summary article{display:flex;align-items:center;gap:10px;padding:14px;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.booking-summary article>span{display:grid;width:38px;height:38px;place-items:center;color:var(--crm-brand-ink);background:var(--crm-teal-soft);border-radius:10px}.booking-summary article>div{display:grid;gap:5px}.booking-summary small{color:var(--crm-text-muted);font-size:9px}.booking-summary strong{color:var(--crm-navy);font-size:13px}.booking-detail-grid{display:grid;grid-template-columns:minmax(0,1fr) 290px;gap:14px;align-items:start}.booking-main{display:grid;gap:14px}.booking-detail-grid aside{position:sticky;top:16px}.booking-fields{display:grid;grid-template-columns:1fr 1fr;margin:0}.booking-fields div{display:grid;grid-template-columns:110px minmax(0,1fr);gap:10px;padding:12px 0;border-bottom:1px solid var(--crm-line)}.booking-fields div:nth-last-child(-n+2){border-bottom:0}.booking-fields .wide{grid-column:1/-1}.booking-fields dt{color:var(--crm-text-muted);font-size:10px}.booking-fields dd{margin:0;color:var(--crm-navy);font-size:11px;font-weight:700}.related-links{display:grid;gap:8px}.related-links a{display:grid;grid-template-columns:150px minmax(0,1fr) auto;align-items:center;gap:10px;padding:12px;color:var(--crm-navy);background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:10px}.related-links span{display:flex;align-items:center;gap:6px;color:var(--crm-text-muted);font-size:10px}.related-links strong{overflow:hidden;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.tool-list{display:grid;gap:9px}.tool-list article{display:grid;gap:6px;padding:11px;background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:10px}.tool-list header{display:flex;align-items:center;justify-content:space-between;gap:7px}.tool-list header strong{font-size:11px}.tool-list b{color:var(--crm-teal);font-size:9px}.tool-list p,.tool-list small{margin:0;color:var(--crm-text-muted);font-size:9px}.equipment-note{margin:0;padding:18px 8px;color:var(--crm-text-muted);font-size:10px;line-height:1.6;text-align:center}.installed-link{display:flex;align-items:center;justify-content:space-between;margin-top:10px;padding-top:10px;color:var(--crm-link);border-top:1px solid var(--crm-line);font-size:10px;font-weight:750}@media(max-width:1000px){.booking-summary{grid-template-columns:repeat(2,1fr)}.booking-detail-grid{grid-template-columns:1fr}.booking-detail-grid aside{position:static}}@media(max-width:620px){.booking-summary{grid-template-columns:1fr}.booking-fields{grid-template-columns:1fr}.booking-fields .wide{grid-column:auto}.booking-fields div,.related-links a{grid-template-columns:1fr}}
</style>
