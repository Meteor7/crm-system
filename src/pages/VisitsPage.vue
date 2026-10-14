<script setup lang="ts">
import { personnelDisplayName } from '@/demo/personnel'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { CalendarPlus, Pencil } from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import type { MultipartFilePart } from '@/api/binary-transport'
import { api as defaultApi, CrmApiError, type CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import type { AccountSummaryDto, ContactSummaryDto, CreateContactInput, CreateVisitInput, Tone, UpdateVisitInput, VisitDto, VisitStatus } from '@/types/crm'
import { VISIT_STATUS_ORDER, canChangeVisit } from '@/domain/visits'
import { formatDisplayDate } from '@/domain/time'
import PageHeader from '@/design-system/PageHeader.vue'
import DataState from '@/design-system/DataState.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import FilterBar from '@/features/shared/FilterBar.vue'
import VisitModal from '@/features/visits/VisitModal.vue'
import PaginationControls from '@/features/shared/PaginationControls.vue'
import { readAllPages } from '@/features/shared/read-all-pages'
import ContactModal from '@/features/contacts/ContactModal.vue'
import { useI18n, useLocaleMessage } from '@/i18n'
import { salesEnumLabel } from '@/features/shared/sales-i18n'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const app = useAppStore()
const route = useRoute()
const router = useRouter()
const { t, locale, message } = useI18n()
const rows = ref<VisitDto[]>([]), accounts = ref<AccountSummaryDto[]>([]), contacts = ref<ContactSummaryDto[]>([]), loading = ref(false), busy = ref(false), error = useLocaleMessage(), requestId = ref('')
const total = ref(0), page = ref(1)
const pageSize = ref(10)
const accountId = ref('All'), status = ref('All'), owner = ref('All')
const modal = ref<'create' | 'review' | 'edit' | null>(null), selected = ref<VisitDto | null>(null), visitConflict = ref(false)
const contactModal = ref(false), contactAccountId = ref(''), selectedContactId = ref('')
const canCreate = computed(() => app.can('visit:create'))
const canReview = computed(() => app.can('visit:review'))
const canEdit = computed(() => app.can('visit:write'))
// Customers reschedule often, so basic fields stay editable until the Manager has reviewed the
// minutes -- by the visit owner or a Manager, not by a colleague who only holds its action.
const canEditVisit = (visit: VisitDto) => canEdit.value && canChangeVisit(visit, app.bootstrap?.user)
const focusedVisitId = computed(() => typeof route.query.focus === 'string' ? route.query.focus : '')
const owners = computed(() => [...new Set([...accounts.value.map((item) => item.owner), ...rows.value.map((item) => item.owner)])])
const statusLabel = computed<Record<VisitStatus, string>>(() => ({
  Planned: t('visits.status.planned'),
  Visited: t('visits.status.visited'),
  'Minutes Submitted': t('visits.status.minutesSubmitted'),
  'Manager Reviewed': t('visits.status.managerReviewed'),
}))
const statusTone: Record<VisitStatus, Tone> = { Planned: 'neutral', Visited: 'info', 'Minutes Submitted': 'warning', 'Manager Reviewed': 'positive' }
let sequence = 0
let openedReviewLink = ''

async function load(): Promise<boolean> {
  const current = ++sequence
  loading.value = true; error.value = ''
  try {
    const contactId = typeof route.query.contactId === 'string' ? route.query.contactId : ''
    const focusId = focusedVisitId.value
    const [accountRows, visitResult, contactRows, focusResult] = await Promise.all([
      readAllPages((referencePage, referencePageSize) => props.apiClient.listAccounts({ page: referencePage, pageSize: referencePageSize })),
      props.apiClient.listVisits({ accountId: accountId.value, status: status.value, owner: owner.value, contactId, page: page.value, pageSize: pageSize.value }),
      app.can('contact:view') ? readAllPages((referencePage, referencePageSize) => props.apiClient.listContacts({ page: referencePage, pageSize: referencePageSize })) : Promise.resolve(null),
      focusId ? props.apiClient.getVisit(focusId) : Promise.resolve(null),
    ])
    if (current !== sequence) return false
    accounts.value = accountRows; rows.value = visitResult.data.items; total.value = visitResult.meta?.total ?? rows.value.length; contacts.value = contactRows ?? []
    if (focusResult && !rows.value.some((item) => item.id === focusResult.data.id)) rows.value.push(focusResult.data)
    await nextTick()
    const focusedRow = Array.from(document.querySelectorAll<HTMLElement>('[data-visit-id]'))
      .find((element) => element.dataset.visitId === focusId)
    focusedRow?.scrollIntoView?.({ block: 'center' })
    if (route.query.review === '1' && openedReviewLink !== focusId) {
      const focused = rows.value.find(item => item.id === focusId)
      if (canReview.value && focused?.status === 'Minutes Submitted') { openedReviewLink = focusId; open('review', focused) }
    }
    return true
  } catch (reason) {
    if (current !== sequence) return false
    const mapped = mapRequestError(reason); error.value = mapped.localizedMessage ?? mapped.message; requestId.value = mapped.requestId
    return false
  } finally { if (current === sequence) loading.value = false }
}
function reset() { page.value = 1; accountId.value = status.value = owner.value = 'All'; void load() }
function changeFilters() { page.value = 1; void load() }
function goPage(target: number) { page.value = target; void load() }
function changePageSize(value: number) { pageSize.value = value; page.value = 1; void load() }
function open(mode: NonNullable<typeof modal.value>, visit: VisitDto | null = null) { selected.value = visit; modal.value = mode; clearModalError() }
function clearModalError() { error.value = ''; requestId.value = ''; visitConflict.value = false }
function closeModal() {
  const stale = visitConflict.value
  modal.value = null; selected.value = null
  clearModalError()
  // After a conflict the row still carries a stale version token, so refresh it on the way out.
  if (stale) void load()
}
// Discards the draft on purpose: it is the way out of a stale version token.
async function reloadVisit() {
  const id = selected.value?.id
  if (!id) return
  if (!(await load())) return
  const refreshed = rows.value.find((item) => item.id === id)
  if (refreshed) {
    selected.value = refreshed
    clearModalError()
    return
  }
  // The visit left the current filter or page, so `load()` cannot return it.
  // Falling back to the stale object would keep the old `modified` token, and
  // every later save would conflict again, so replace it with a direct fetch.
  try {
    const response = await props.apiClient.getVisit(id)
    selected.value = response.data
    clearModalError()
  } catch (reason) {
    const mapped = mapRequestError(reason); error.value = mapped.localizedMessage ?? mapped.message; requestId.value = mapped.requestId
  }
}
function openContact(accountId: string) { contactAccountId.value = accountId; contactModal.value = true }
async function saveContact(payload: CreateContactInput) {
  busy.value = true; error.value = ''; requestId.value = ''
  try {
    const created = await props.apiClient.createContact(payload)
    selectedContactId.value = created.data.id
    contacts.value = await readAllPages((referencePage, referencePageSize) => props.apiClient.listContacts({ page: referencePage, pageSize: referencePageSize }))
    contactModal.value = false
  } catch (reason) { const mapped = mapRequestError(reason); error.value = mapped.localizedMessage ?? mapped.message; requestId.value = mapped.requestId }
  finally { busy.value = false }
}
async function submit(payload: CreateVisitInput | UpdateVisitInput, meetingFile?: MultipartFilePart) {
  busy.value = true; clearModalError()
  try {
    if (modal.value === 'create') {
      const input = payload as CreateVisitInput
      const created = await props.apiClient.createVisit(input)
      if (meetingFile) {
        await props.apiClient.submitVisitRecord(created.data.id, meetingFile)
        modal.value = null; selected.value = null
        await router.push({ name: 'visit-detail', params: { visitId: created.data.id } })
        return
      }
    }
    else if (modal.value === 'review' && selected.value) await props.apiClient.reviewVisit(selected.value.id, selected.value.modified)
    else if (modal.value === 'edit' && selected.value) await props.apiClient.updateVisit(selected.value.id, payload as UpdateVisitInput, selected.value.modified)
    modal.value = null; selected.value = null; await load()
  } catch (reason) {
    const mapped = mapRequestError(reason)
    // Refreshing the row here would refill the open modal from the server and throw away what
    // the user just typed, so the draft stays until they ask for the latest version.
    visitConflict.value = reason instanceof CrmApiError && reason.code === 'VERSION_CONFLICT'
    error.value = visitConflict.value ? message('visitModal.versionConflict') : mapped.localizedMessage ?? mapped.message
    requestId.value = mapped.requestId
  }
  finally { busy.value = false }
}
onMounted(async () => {
  await app.loadBootstrap(props.apiClient)
  if (typeof route.query.accountId === 'string') accountId.value = route.query.accountId
  await load()
  if (route.query.create === '1' && canCreate.value) open('create')
})
watch([focusedVisitId, () => route.query.review], () => { modal.value = null; selected.value = null; openedReviewLink = ''; void load() })
</script>

<template>
  <div class="visits-page">
    <PageHeader eyebrow="CUSTOMER ENGAGEMENT" :title="t('visits.title')" :description="t('visits.description')">
      <button v-if="canCreate" class="primary-button" type="button" data-testid="new-visit" @click="open('create')"><CalendarPlus :size="15" />{{ locale === 'en-US' ? 'New visit' : '新建拜访' }}</button>
    </PageHeader>

    <FilterBar :result-label="t('visits.result', { count: rows.length })" @reset="reset">
      <select v-model="accountId" class="filter-control" :aria-label="t('visits.account')" @change="changeFilters"><option value="All">{{ t('visits.allAccounts') }}</option><option v-for="account in accounts" :key="account.id" :value="account.id">{{ account.shortName }}</option></select>
      <select v-model="status" class="filter-control" :aria-label="t('visits.status')" @change="changeFilters"><option value="All">{{ t('visits.allStatuses') }}</option><option v-for="item in VISIT_STATUS_ORDER" :key="item" :value="item">{{ statusLabel[item] }}</option></select>
      <select v-model="owner" class="filter-control" :aria-label="t('visits.owner')" @change="changeFilters"><option value="All">{{ t('visits.allOwners') }}</option><option v-for="item in owners" :key="item" :value="item">{{ personnelDisplayName(item) }}</option></select>
    </FilterBar>

    <!-- While a modal is open it renders the same message itself; showing both duplicates it. -->
    <p v-if="error && !modal" class="form-error" data-delete-error>{{ error }}<small v-if="requestId">{{ locale === 'en-US' ? 'Request ID' : '请求编号' }} {{ requestId }}</small></p>
    <DataState v-if="loading && !rows.length" type="loading" />
    <DataState v-else-if="!rows.length" type="empty" :title="t('visits.emptyTitle')" :message="t('visits.emptyMessage')" />
    <section v-else class="visits-card">
      <div class="table-scroll">
        <table class="crm-table visits-table is-responsive">
          <thead><tr><th>{{ t('visits.subject') }}</th><th>{{ t('visits.account') }}</th><th>{{ t('visits.dateType') }}</th><th>{{ t('visits.owner') }}</th><th>{{ t('visits.objective') }}</th><th>{{ t('visits.outcome') }}</th><th>{{ t('visits.status') }}</th><th>{{ t('visits.actions') }}</th></tr></thead>
          <tbody>
            <tr v-for="visit in rows" :key="visit.id" :data-visit-id="visit.id" :class="{ focused: visit.id === focusedVisitId }">
              <td class="visit-subject" :data-label="t('visits.subject')"><RouterLink class="record-link" :to="`/visits/${visit.id}`"><strong>{{ visit.subject }}</strong></RouterLink><small>{{ visit.id }}</small></td>
              <td class="visit-account" :data-label="t('visits.account')"><strong>{{ visit.accountName }}</strong></td>
              <td class="visit-date" :data-label="t('visits.dateType')"><strong>{{ formatDisplayDate(visit.date) }}</strong><small>{{ salesEnumLabel(visit.type, locale) }}</small></td>
              <td :data-label="t('visits.owner')">{{ personnelDisplayName(visit.owner) }}</td>
              <td class="visit-text" :data-label="t('visits.objective')">{{ visit.objective }}</td>
              <td class="visit-text" :data-label="t('visits.outcome')">{{ visit.outcome || '—' }}</td>
              <td :data-label="t('visits.status')"><StatusBadge :label="statusLabel[visit.status]" :tone="statusTone[visit.status]" /></td>
              <td :data-label="t('visits.actions')">
                <div class="visit-actions">
                  <button v-if="canEditVisit(visit)" class="edit-button" type="button" :data-edit-visit="visit.id" :aria-label="t('visits.edit')" :title="t('visits.edit')" :disabled="busy" @click="open('edit', visit)"><Pencil :size="13" /></button>
                  <button v-if="canReview && visit.status === 'Minutes Submitted'" class="primary-button" type="button" @click="open('review', visit)">{{ t('visits.review') }}</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
    <PaginationControls v-if="!error && total > pageSize" :page="page" :page-size="pageSize" :total="total" @change="goPage" @page-size-change="changePageSize" />

    <VisitModal v-if="modal" :mode="modal" :visit="selected" :accounts="accounts" :contacts="contacts" :initial-account-id="typeof route.query.accountId === 'string' ? route.query.accountId : ''" :initial-primary-contact-id="selectedContactId || (typeof route.query.primaryContactId === 'string' ? route.query.primaryContactId : '')" :initial-opportunity-id="typeof route.query.opportunityId === 'string' ? route.query.opportunityId : ''" :busy="busy" :error="error" :request-id="requestId" :conflict="visitConflict" @close="closeModal" @reload="reloadVisit" @create-contact="openContact" @submit="submit" />
    <ContactModal v-if="contactModal" :accounts="accounts" :sites="[]" :contacts="contacts" :fixed-account-id="contactAccountId" :busy="busy" :error="error" @close="contactModal = false" @submit="saveContact" />
  </div>
</template>

<style scoped>
.primary-button{display:flex;align-items:center;gap:7px}.search-control{display:flex;min-width:190px;height:34px;align-items:center;gap:7px;padding:0 10px;color:var(--crm-text-muted);background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:8px}.search-control input{min-width:0;flex:1;background:transparent;border:0;outline:0;font-size:10px}.form-error{display:flex;justify-content:space-between;padding:10px 12px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:9px;font-size:10px}.visits-card{overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:14px}.table-scroll{overflow:auto}.visits-table{min-width:1060px}.visits-table tbody tr.focused{background:var(--crm-teal-soft);box-shadow:inset 3px 0 0 var(--crm-teal)}.visits-table td{vertical-align:top}.visits-table td strong,.visits-table td small{display:block}.visits-table td small{margin-top:4px;color:var(--crm-text-muted);font-size:10px}.visit-subject{min-width:170px}.visit-subject strong{color:var(--crm-brand-strong);font-size:12px}.visit-account{min-width:150px}.visit-date{min-width:110px;font-variant-numeric:tabular-nums}.visit-text{min-width:150px;max-width:240px;line-height:1.55}.visit-next-action{min-width:200px}.visit-actions{display:flex;min-width:120px;flex-wrap:wrap;align-items:center;gap:7px}.text-button{display:flex;align-items:center;gap:4px;color:var(--crm-teal);background:transparent;border:0;font-size:9px;font-weight:700;cursor:pointer}.secondary-button,.visit-actions .primary-button{min-height:30px;padding:0 10px;font-size:9px}.edit-button{display:grid;width:30px;height:30px;place-items:center;color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line);border-radius:7px;cursor:pointer}.edit-button:disabled{opacity:.45;cursor:not-allowed}
@media(max-width:839px){.search-control{width:100%;min-width:0}.visits-table .visit-subject,.visits-table .visit-account,.visits-table .visit-date,.visits-table .visit-text{min-width:0;max-width:none}.visit-actions{min-width:0}.form-error{align-items:flex-start;flex-direction:column;gap:4px}}
</style>
