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

async function load() {
  const current = ++sequence
  loading.value = true
  error.value = ''
  denied.value = false
  try {
    const result = await props.apiClient.listContacts({
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
    if (!allContacts.value.length && accountId.value === 'All' && siteId.value === 'All' && owner.value === 'All' && contactStatus.value === 'Active') {
      allContacts.value = rows.value
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
  allContacts.value = await readAllPages((page, pageSize) => props.apiClient.listContacts({ contactStatus: 'Active', page, pageSize }))
}

function resetFilters() {
  page.value = 1
  accountId.value = 'All'
  siteId.value = 'All'
  owner.value = 'All'
  contactStatus.value = 'Active'
}
let restoringRoute = false
function syncUrl() { if (!restoringRoute) void router.replace({ query: { ...route.query, page: String(page.value), pageSize: String(pageSize.value), accountId: accountId.value === 'All' ? undefined : accountId.value, siteId: siteId.value === 'All' ? undefined : siteId.value, owner: owner.value === 'All' ? undefined : owner.value, contactStatus: contactStatus.value === 'Active' ? undefined : contactStatus.value } }) }
function changeFilters() { if (restoringRoute) return; page.value = 1; syncUrl(); void load() }
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
    deleteOpen.value = false
    deleteTarget.value = null
    editing.value = null
    if (rows.value.length === 1 && page.value > 1) page.value -= 1
    await load()
    try {
      await loadAllContacts()
    } catch {
      allContacts.value = rows.value
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
    if (editing.value) await props.apiClient.updateContact(editing.value.id, payload, editing.value.modified)
    else await props.apiClient.createContact(payload)
    modalOpen.value = false
    editing.value = null
    await load()
    try {
      await loadAllContacts()
    } catch {
      allContacts.value = rows.value
    }
  } catch (reason) {
    const mapped = mapRequestError(reason); modalError.value = mapped.localizedMessage ?? mapped.message
  } finally {
    busy.value = false
  }
}
async function openDetail(contact: ContactSummaryDto) {
  await router.push({ name: 'contact-detail', params: { contactId: contact.id } })
}

watch([accountId, siteId, owner, contactStatus], changeFilters, { flush: 'sync' })
watch(() => [route.query.page, route.query.pageSize, route.query.accountId, route.query.siteId, route.query.owner, route.query.contactStatus], ([nextPage, nextSize, nextAccount, nextSite, nextOwner, nextStatus]) => {
  const restoredPage = typeof nextPage === 'string' && Number(nextPage) > 0 ? Number(nextPage) : 1
  const restoredSize = typeof nextSize === 'string' && [10, 12, 25, 50].includes(Number(nextSize)) ? Number(nextSize) : 12
  const values = [typeof nextAccount === 'string' ? nextAccount : 'All', typeof nextSite === 'string' ? nextSite : 'All', typeof nextOwner === 'string' ? nextOwner : 'All', typeof nextStatus === 'string' ? nextStatus : 'Active']
  if (restoredPage === page.value && restoredSize === pageSize.value && values[0] === accountId.value && values[1] === siteId.value && values[2] === owner.value && values[3] === contactStatus.value) return
  restoringRoute = true; page.value = restoredPage; pageSize.value = restoredSize; accountId.value = values[0]!; siteId.value = values[1]!; owner.value = values[2]!; contactStatus.value = values[3] as ContactStatus | 'All'; restoringRoute = false; void load()
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
  if (!allContacts.value.length) try { await loadAllContacts() } catch { allContacts.value = rows.value }
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
               <td :data-label="t('contacts.status')"><StatusBadge :label="contactStatusLabel(contact.status, locale)" :tone="statusTone(contact.status)" /></td><td :data-label="t('contacts.updated')">{{ formatDisplayDate(contact.updatedAt) }}</td>
              <td v-if="showActions" :data-label="t('contacts.actions')"><button v-if="canEditContact(contact)" class="edit-button" type="button" data-testid="edit-contact" @click="openEdit(contact)"><Edit3 :size="13" />{{ t('contacts.edit') }}</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <PaginationControls v-if="!denied && !error && total > pageSize" :page="page" :page-size="pageSize" :total="total" @change="goPage" @page-size-change="changePageSize" />
    </section>

    <ContactModal v-if="modalOpen" :contact="editing" :accounts="writableAccounts" :sites="writableSites" :contacts="allContacts" :busy="busy" :error="modalError" :can-delete="Boolean(editing && canDelete)" @close="modalOpen = false" @submit="saveContact" @delete="requestDeleteFromEdit" />
    <ModalShell v-if="deleteOpen && deleteTarget" :title="locale === 'en-US' ? 'Permanently delete contact' : '永久删除联系人'" eyebrow="HARD DELETE" :busy="busy" @close="deleteOpen = false" @submit="deleteContact">
      <p class="delete-note">{{ locale === 'en-US' ? 'This cannot be undone. “' : '此操作不可恢复。“' }}{{ deleteTarget.name }}{{ locale === 'en-US' ? '” will be physically removed. Linked stakeholders are removed; Booking and Demo Request are rebound to another contact at the same account when possible.' : '”会从本地数据中物理删除；Opportunity 中对应关键人关联会移除，Booking 与 Demo Request 会优先改绑到同客户的现有联系人。' }}</p>
      <p v-if="modalError" class="form-error">{{ modalError }}</p>
    </ModalShell>
  </div>
</template>

<style scoped>
.primary-button{display:flex;align-items:center;gap:6px}.search-control{display:flex;min-width:230px;height:36px;align-items:center;gap:7px;padding:0 10px;color:var(--crm-text-muted);background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:8px}.search-control input{min-width:0;flex:1;background:transparent;border:0;outline:0}.filter-control{min-height:36px;padding:0 9px;background:#fff;border:1px solid var(--crm-line);border-radius:8px}.quality-hint{margin:-8px 0 12px;padding:8px 10px;color:#7d611f;background:var(--crm-warning-soft);border:1px solid #ecd99d;border-radius:8px;font-size:9px}.contacts-card{overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:14px}.table-scroll{overflow:auto}.contacts-table{min-width:1180px}.contacts-table td strong,.contacts-table td small{display:block}.contacts-table td small{margin-top:4px;color:var(--crm-text-muted);font-size:10px}.contact-link{display:flex;align-items:center;gap:8px;color:var(--crm-navy);background:transparent;border:0;font:inherit;cursor:pointer}.contact-link span{display:grid;width:30px;height:30px;place-items:center;color:var(--crm-brand-ink);background:var(--crm-teal-soft);border-radius:9px}.contact-link strong{color:var(--crm-link);font-size:12px}.edit-button{display:flex;align-items:center;gap:4px;color:var(--crm-teal);background:transparent;border:0;font-weight:700;cursor:pointer}
@media(max-width:839px){.search-control{width:100%;min-width:0}.contact-link{min-width:0}.contact-link strong{overflow-wrap:anywhere}}
</style>
