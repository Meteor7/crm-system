<script setup lang="ts">
import { personnelDisplayName } from '@/demo/personnel'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Edit3, Plus, UserRound } from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import { api as defaultApi, type CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import type { AccountSummaryDto, ContactStatus, ContactSummaryDto, CreateContactInput, SiteDto, Tone } from '@/types/crm'
import PageHeader from '@/design-system/PageHeader.vue'
import DataState from '@/design-system/DataState.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import FilterBar from '@/features/shared/FilterBar.vue'
import PaginationControls from '@/features/shared/PaginationControls.vue'
import { readAllPages } from '@/features/shared/read-all-pages'
import { sitesInAccountOrder } from '@/features/accounts/account-sites'
import ContactModal from '@/features/contacts/ContactModal.vue'
import ModalShell from '@/design-system/ModalShell.vue'
import { formatDisplayDate } from '@/domain/time'
import { useI18n, useLocaleMessage } from '@/i18n'
import { contactStatusLabel, salesEnumLabel } from '@/features/shared/sales-i18n'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const route = useRoute()
const router = useRouter()
const app = useAppStore()
const { locale, t } = useI18n()
const rows = ref<ContactSummaryDto[]>([])
const accounts = ref<AccountSummaryDto[]>([])
const sites = ref<Array<SiteDto & { accountId: string }>>([])
const allContacts = ref<ContactSummaryDto[]>([])
// Whether the cache was ever the whole set (a page that was, or a read of them all): a Contact saved before that is in
// the cache, which is not the whole set yet, and the page's start still reads them all.
let wholeSetSeen = false
// The reads of every Contact, in order: one that an edit overtook (a save, a delete, a page that was the whole set)
// is stale, and changes nothing when it returns (it would bring back what the edit took out, or take out what it put in).
let allContactsRequest = 0
const total = ref(0)
const page = ref(typeof route.query.page === 'string' && Number(route.query.page) > 0 ? Number(route.query.page) : 1)
const pageSize = ref(typeof route.query.pageSize === 'string' && [10, 12, 25, 50].includes(Number(route.query.pageSize)) ? Number(route.query.pageSize) : 12)
const loading = ref(false)
const denied = ref(false)
const error = useLocaleMessage()
const requestId = ref('')
const accountId = ref(typeof route.query.accountId === 'string' ? route.query.accountId : 'All')
const siteId = ref(typeof route.query.siteId === 'string' ? route.query.siteId : 'All')
const owner = ref(typeof route.query.owner === 'string' ? route.query.owner : 'All')
// Matched by the server against the Contact's names and email (F1-09).
const search = ref(typeof route.query.search === 'string' ? route.query.search : '')
// The box's text is a draft until Enter applies it: every other load (a page turned, a refresh after a delete or
// a save, a retry) runs with the search in force, which the URL shows; text typed but not entered goes nowhere.
const searchDraft = ref(search.value)
const contactStatus = ref<ContactStatus | 'All'>(
  route.query.contactStatus === 'All' || route.query.contactStatus === 'Active' || route.query.contactStatus === 'Left Company' || route.query.contactStatus === 'Archived'
    ? route.query.contactStatus
    : 'Active',
)
const modalOpen = ref(false)
const editing = ref<ContactSummaryDto | null>(null)
const deleteOpen = ref(false)
const deleteTarget = ref<ContactSummaryDto | null>(null)
const busy = ref(false)
const modalError = useLocaleMessage()
const canWrite = computed(() => app.can('contact:write'))
const canDelete = computed(() => app.can('contact:delete'))
const writableAccounts = computed(() => {
  const user = app.bootstrap?.user
  if (!user || !canWrite.value) return []
  if (user.role === 'Manager') return accounts.value
  return user.role === 'Sales' ? accounts.value.filter((account) => account.owner === user.id) : []
})
const writableAccountIds = computed(() => new Set(writableAccounts.value.map((account) => account.id)))
const writableSites = computed(() => sites.value.filter((site) => writableAccountIds.value.has(site.accountId)))
const canCreate = computed(() => writableAccounts.value.length > 0)
const showActions = computed(() => rows.value.some((contact) => canEditContact(contact)))
const visibleSites = computed(() => sites.value.filter((item) => accountId.value === 'All' || item.accountId === accountId.value))
const owners = computed(() => [...new Set([...accounts.value.map((item) => item.owner), ...allContacts.value.map((item) => item.owner)])].sort())
const statusTone = (status: ContactStatus): Tone => status === 'Active' ? 'positive' : status === 'Left Company' ? 'warning' : 'neutral'
let sequence = 0

function canEditContact(contact: ContactSummaryDto) {
  const user = app.bootstrap?.user
  if (!user || !canWrite.value) return false
  if (user.role === 'Manager') return true
  return user.role === 'Sales' && writableAccountIds.value.has(contact.accountId)
}

function siteLabel(contact: ContactSummaryDto) {
  const user = app.bootstrap?.user
  const account = accounts.value.find((item) => item.id === contact.accountId)
  if (user?.role === 'Sales' && account && account.owner !== user.id) return t('contacts.ownerOnly')
  return contact.siteName || t('contacts.notSpecifiedSite')
}

async function loadReferences() {
  accounts.value = await readAllPages((page, pageSize) => props.apiClient.listAccounts({ page, pageSize }))
  try {
    sites.value = sitesInAccountOrder(accounts.value, (await props.apiClient.listAccountSites()).data)
  } catch {
    sites.value = []
  }
}

// Whether the list asks for every Active Contact: what the cache of them (the reporting-line choices) may be filled from.
function unfilteredNow() { return !search.value.trim() && accountId.value === 'All' && siteId.value === 'All' && owner.value === 'All' && contactStatus.value === 'Active' }
async function load() {
  const current = ++sequence
  // Decided as the request leaves: the search may be cleared before it returns.
  const unfiltered = unfilteredNow()
  loading.value = true
  error.value = ''
  denied.value = false
  try {
    const result = await props.apiClient.listContacts({
      search: search.value.trim() || undefined,
      accountId: accountId.value,
      siteId: siteId.value,
      owner: owner.value,
      contactStatus: contactStatus.value,
      page: page.value,
      pageSize: pageSize.value,
    })
    if (current !== sequence) return
    rows.value = result.data.items
    total.value = result.meta?.total ?? rows.value.length
    // A page that holds every Active Contact is the whole set, and refreshes the cache of them (the reporting-line
    // choices); a first page of more is not, and `loadAllContacts` reads them all. A load that fails, or a read of
    // them all that fails, leaves the cache as it was: the last whole set seen, less a Contact deleted since.
    if (unfiltered && rows.value.length >= total.value) {
      allContacts.value = rows.value
      wholeSetSeen = true
      allContactsRequest += 1
    }
  } catch (reason) {
    if (current !== sequence) return
    const mapped = mapRequestError(reason)
    error.value = mapped.localizedMessage ?? mapped.message
    requestId.value = mapped.requestId
    denied.value = mapped.denied
    rows.value = []
    total.value = 0
  } finally {
    if (current === sequence) loading.value = false
  }
}
async function loadAllContacts() {
  const current = ++allContactsRequest
  const rows = await readAllPages((page, pageSize) => props.apiClient.listContacts({ contactStatus: 'Active', page, pageSize }))
  if (current !== allContactsRequest) return
  allContacts.value = rows
  wholeSetSeen = true
}

function resetFilters() {
  // The filter watcher reloads on each change it sees; the reset reloads once for all of them, and also when
  // they already stood at their defaults, which used to leave the page where it was (F1-03).
  restoringRoute = true
  search.value = ''
  searchDraft.value = ''
  accountId.value = 'All'
  siteId.value = 'All'
  owner.value = 'All'
  contactStatus.value = 'Active'
  restoringRoute = false
  changeFilters()
}
let restoringRoute = false
function syncUrl() { if (!restoringRoute) void router.replace({ name: 'contacts', query: { ...route.query, page: String(page.value), pageSize: String(pageSize.value), search: search.value.trim() || undefined, accountId: accountId.value === 'All' ? undefined : accountId.value, siteId: siteId.value === 'All' ? undefined : siteId.value, owner: owner.value === 'All' ? undefined : owner.value, contactStatus: contactStatus.value === 'Active' ? undefined : contactStatus.value } }) }
function changeFilters() { if (restoringRoute) return; page.value = 1; syncUrl(); void load() }
// The search runs on Enter and is written into the URL, as a change of a filter is: a list is what its URL says
// (back, a reload and the link bring the search back). A reload per keystroke would rebuild the page under the
// cursor (the shell keys a page by its URL), and one that left the URL alone left the list and the address apart.
function submitSearch(event: KeyboardEvent) {
  // An Enter that ends an IME composition commits the characters; it is not the search, and the input keeps them
  // (WebKit sends that Enter after the composition, with keyCode 229 and `isComposing` false).
  if (event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  search.value = searchDraft.value.trim()
  changeFilters()
}
function goPage(target: number) { page.value = target; syncUrl(); void load() }
function changePageSize(value: number) { pageSize.value = value; page.value = 1; syncUrl(); void load() }
function openCreate() {
  editing.value = null
  modalError.value = ''
  modalOpen.value = true
}
function openEdit(contact: ContactSummaryDto) {
  if (!canEditContact(contact)) return
  editing.value = contact
  modalError.value = ''
  modalOpen.value = true
}
function requestDeleteFromEdit() {
  if (!editing.value || !canDelete.value) return
  deleteTarget.value = editing.value
  modalOpen.value = false
  modalError.value = ''
  deleteOpen.value = true
}
async function deleteContact() {
  if (!deleteTarget.value) return
  busy.value = true
  modalError.value = ''
  try {
    await props.apiClient.deleteContact(deleteTarget.value.id)
    // Out of the cache at once: a deleted Contact is no reporting line, whatever becomes of the read below; a read
    // still out is stale now.
    allContactsRequest += 1
    allContacts.value = allContacts.value.filter((item) => item.id !== deleteTarget.value?.id)
    deleteOpen.value = false
    deleteTarget.value = null
    editing.value = null
    if (rows.value.length === 1 && page.value > 1) page.value -= 1
    await load()
    try {
      await loadAllContacts()
    } catch {
      // The cache stays what the load above made of it.
    }
  } catch (reason) {
    const mapped = mapRequestError(reason); modalError.value = mapped.localizedMessage ?? mapped.message
  } finally {
    busy.value = false
  }
}
async function saveContact(payload: CreateContactInput) {
  busy.value = true
  modalError.value = ''
  try {
    const saved = editing.value
      ? await props.apiClient.updateContact(editing.value.id, payload, editing.value.modified)
      : await props.apiClient.createContact(payload)
    // Into the cache at once, as saved — out of it when no longer Active (a reporting line is an Active Contact) —
    // whatever becomes of the reads below; a read still out is stale now.
    allContactsRequest += 1
    allContacts.value = [...allContacts.value.filter((item) => item.id !== saved.data.id), ...(saved.data.status === 'Active' ? [saved.data] : [])]
    modalOpen.value = false
    editing.value = null
    await load()
    try {
      await loadAllContacts()
    } catch {
      // The cache stays what the load above made of it.
    }
  } catch (reason) {
    const mapped = mapRequestError(reason); modalError.value = mapped.localizedMessage ?? mapped.message
  } finally {
    busy.value = false
  }
}
async function openDetail(contact: ContactSummaryDto) {
  // The record carries the list's URL, for its "Back to Contacts" control.
  await router.push({ name: 'contact-detail', params: { contactId: contact.id }, query: { from: route.fullPath } })
}

// Synchronous, so that a reset or a route restore (which set `restoringRoute` around their assignments) is one reload.
watch([accountId, siteId, owner, contactStatus], changeFilters, { flush: 'sync' })
watch(() => [route.query.page, route.query.pageSize, route.query.search, route.query.accountId, route.query.siteId, route.query.owner, route.query.contactStatus], ([nextPage, nextSize, nextSearch, nextAccount, nextSite, nextOwner, nextStatus]) => {
  const restoredPage = typeof nextPage === 'string' && Number(nextPage) > 0 ? Number(nextPage) : 1
  const restoredSize = typeof nextSize === 'string' && [10, 12, 25, 50].includes(Number(nextSize)) ? Number(nextSize) : 12
  const restoredSearch = typeof nextSearch === 'string' ? nextSearch : ''
  const values = [typeof nextAccount === 'string' ? nextAccount : 'All', typeof nextSite === 'string' ? nextSite : 'All', typeof nextOwner === 'string' ? nextOwner : 'All', typeof nextStatus === 'string' ? nextStatus : 'Active']
  if (restoredPage === page.value && restoredSize === pageSize.value && restoredSearch === search.value.trim() && values[0] === accountId.value && values[1] === siteId.value && values[2] === owner.value && values[3] === contactStatus.value) return
  restoringRoute = true; page.value = restoredPage; pageSize.value = restoredSize; search.value = restoredSearch; searchDraft.value = restoredSearch; accountId.value = values[0]!; siteId.value = values[1]!; owner.value = values[2]!; contactStatus.value = values[3] as ContactStatus | 'All'; restoringRoute = false; void load()
})
watch(accountId, () => {
  if (!visibleSites.value.some((item) => item.id === siteId.value)) siteId.value = 'All'
})
onMounted(async () => {
  await app.loadBootstrap(props.apiClient)
  try {
    await loadReferences()
  } catch {
    // Contact permissions remain the authority; reference data is optional for read-only rendering.
  }
  await load()
  if (!wholeSetSeen) try { await loadAllContacts() } catch { /* the cache stays what the load above made of it */ }
})
onBeforeUnmount(() => {
  sequence += 1
})
</script>

<template>
  <div class="contacts-page">
    <PageHeader eyebrow="CONTACT MASTER" :title="t('contacts.title')" :description="t('contacts.description')">
      <button v-if="canCreate" class="primary-button" type="button" data-testid="new-contact" @click="openCreate"><Plus :size="15" />{{ t('contacts.new') }}</button>
    </PageHeader>

    <FilterBar :result-label="t('contacts.result', { count: total })" @reset="resetFilters">
      <input v-model="searchDraft" class="filter-control filter-search" type="search" data-contact-search :placeholder="t('contacts.searchPlaceholder')" :aria-label="t('contacts.searchPlaceholder')" @keydown.enter="submitSearch" />
      <select v-model="accountId" class="filter-control" :aria-label="locale === 'en-US' ? 'Account filter' : '客户筛选'"><option value="All">{{ t('contacts.allAccounts') }}</option><option v-for="account in accounts" :key="account.id" :value="account.id">{{ account.shortName }}</option></select>
      <select v-model="siteId" class="filter-control" :aria-label="locale === 'en-US' ? 'Site filter' : '厂区筛选'"><option value="All">{{ t('contacts.allSites') }}</option><option v-for="site in visibleSites" :key="site.id" :value="site.id">{{ site.name }}</option></select>
      <select v-model="owner" class="filter-control" :aria-label="locale === 'en-US' ? 'Owner filter' : '负责人筛选'"><option value="All">{{ t('contacts.allOwners') }}</option><option v-for="item in owners" :key="item" :value="item">{{ personnelDisplayName(item) }}</option></select>
       <select v-model="contactStatus" class="filter-control" :aria-label="locale === 'en-US' ? 'Status filter' : '状态筛选'"><option value="All">{{ t('contacts.allStatuses') }}</option><option v-for="item in ['Active', 'Left Company', 'Archived']" :key="item" :value="item">{{ contactStatusLabel(item, locale) }}</option></select>
    </FilterBar>
    <p v-if="rows.some((contact) => contact.dataQuality === 'Needs Review')" class="quality-hint" data-testid="needs-review-explanation">{{ t('contacts.needsReview') }}</p>

    <section class="contacts-card">
      <DataState v-if="loading && !rows.length" type="loading" />
      <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
      <DataState v-else-if="error" type="error" :message="error" :request-id="requestId" @retry="load" />
      <DataState v-else-if="!rows.length" type="empty" :title="t('contacts.emptyTitle')" :message="t('contacts.emptyMessage')" />
      <div v-else class="table-scroll">
        <table class="crm-table contacts-table is-responsive">
          <thead><tr><th>{{ t('contacts.title') }}</th><th>{{ t('contacts.accountSite') }}</th><th>{{ t('contacts.titleDepartment') }}</th><th>{{ t('contacts.phone') }}</th><th>{{ t('contacts.email') }}</th><th>{{ t('accounts.owner') }}</th><th>{{ t('contacts.status') }}</th><th>{{ t('contacts.updated') }}</th><th v-if="showActions">{{ t('contacts.actions') }}</th></tr></thead>
          <tbody>
            <tr v-for="contact in rows" :key="contact.id">
               <td :data-label="t('contacts.title')"><button class="contact-link record-name-link" type="button" :data-contact-id="contact.id" @click="openDetail(contact)"><span><UserRound :size="14" /></span><strong>{{ contact.name }}</strong><StatusBadge v-if="contact.dataQuality === 'Needs Review'" data-testid="needs-review" :label="salesEnumLabel(contact.dataQuality, locale)" tone="warning" /></button></td>
              <td :data-label="t('contacts.accountSite')"><strong>{{ contact.accountShortName }}</strong><small>{{ siteLabel(contact) }}</small></td>
              <td :data-label="t('contacts.titleDepartment')"><strong>{{ contact.title }}</strong><small>{{ contact.department }}</small></td>
              <td :data-label="t('contacts.phone')">{{ contact.phone || '—' }}</td><td :data-label="t('contacts.email')">{{ contact.email || '—' }}</td><td :data-label="t('accounts.owner')">{{ personnelDisplayName(contact.owner) }}</td>
               <td :data-label="t('contacts.status')"><StatusBadge :label="contactStatusLabel(contact.status, locale)" :tone="statusTone(contact.status)" /></td><td class="date-cell" :data-label="t('contacts.updated')">{{ formatDisplayDate(contact.updatedAt) }}</td>
              <td v-if="showActions" class="actions-cell" :data-label="t('contacts.actions')"><button v-if="canEditContact(contact)" class="edit-button" type="button" data-testid="edit-contact" @click="openEdit(contact)"><Edit3 :size="13" />{{ t('contacts.edit') }}</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <PaginationControls v-if="!denied && !error && total > pageSize" :page="page" :page-size="pageSize" :total="total" @change="goPage" @page-size-change="changePageSize" />
    </section>

    <ContactModal v-if="modalOpen" :contact="editing" :accounts="writableAccounts" :sites="writableSites" :contacts="allContacts" :busy="busy" :error="modalError" :can-delete="Boolean(editing && canDelete)" @close="modalOpen = false" @submit="saveContact" @delete="requestDeleteFromEdit" />
    <ModalShell v-if="deleteOpen && deleteTarget" :title="t('detail.archiveContact')" eyebrow="ARCHIVE" :busy="busy" :submit-label="t('detail.archiveContactAction')" danger @close="deleteOpen = false" @submit="deleteContact">
      <p class="delete-note">{{ t('detail.archiveContactWarning', { name: deleteTarget.name }) }}</p>
      <p v-if="modalError" class="form-error">{{ modalError }}</p>
    </ModalShell>
  </div>
</template>

<style scoped>
.primary-button{display:flex;align-items:center;gap:6px}.search-control{display:flex;min-width:230px;height:36px;align-items:center;gap:7px;padding:0 10px;color:var(--crm-text-muted);background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:8px}.search-control input{min-width:0;flex:1;background:transparent;border:0;outline:0}.filter-control{min-height:36px;padding:0 9px;background:#fff;border:1px solid var(--crm-line);border-radius:8px}.quality-hint{margin:-8px 0 12px;padding:8px 10px;color:#7d611f;background:var(--crm-warning-soft);border:1px solid #ecd99d;border-radius:8px;font-size:9px}.contacts-card{overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:14px}.table-scroll{overflow:auto}.contacts-table{min-width:1180px}.contacts-table td strong,.contacts-table td small{display:block}.contacts-table td small{margin-top:4px;color:var(--crm-text-muted);font-size:10px}.contact-link{display:flex;align-items:center;gap:8px;color:var(--crm-navy);background:transparent;border:0;font:inherit;cursor:pointer}.contact-link span{display:grid;width:30px;height:30px;place-items:center;color:var(--crm-brand-ink);background:var(--crm-teal-soft);border-radius:9px}.contact-link strong{color:var(--crm-link);font-size:12px}.contacts-table .date-cell{min-width:112px;white-space:nowrap;font-variant-numeric:tabular-nums}.contacts-table .actions-cell{min-width:88px}.edit-button{display:inline-flex;align-items:center;gap:4px;white-space:nowrap;color:var(--crm-teal);background:transparent;border:0;font-weight:700;cursor:pointer}
@media(max-width:839px){.search-control{width:100%;min-width:0}.contact-link{min-width:0}.contact-link strong{overflow-wrap:anywhere}}
</style>
