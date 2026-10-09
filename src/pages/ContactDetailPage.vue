<script setup lang="ts">
import { bookingTimelineTitle } from '@/features/shared/system-labels'
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft, BriefcaseBusiness, CalendarPlus, Edit3, GitMerge, Mail, Phone, Trash2, UserRound } from '@lucide/vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api as defaultApi, CrmApiError, type CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import type { AccountSummaryDto, ContactDetailDto, ContactSummaryDto, CreateContactInput, SiteDto, Tone } from '@/types/crm'
import PageHeader from '@/design-system/PageHeader.vue'
import DataState from '@/design-system/DataState.vue'
import SectionCard from '@/design-system/SectionCard.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import ContactModal from '@/features/contacts/ContactModal.vue'
import ContactMergeModal from '@/features/contacts/ContactMergeModal.vue'
import ContactFilesCard from '@/features/contacts/ContactFilesCard.vue'
import ModalShell from '@/design-system/ModalShell.vue'
import { personnelDisplayName } from '@/demo/personnel'
import { formatDisplayDate } from '@/domain/time'
import { readAllPages } from '@/features/shared/read-all-pages'
import { useI18n, useLocaleMessage, localeMessage } from '@/i18n'
import { contactStatusLabel, salesEnumLabel, recordTypeLabel } from '@/features/shared/sales-i18n'
import { isOpportunityStage, opportunityStageLabel } from '@/domain/opportunity-stages'
import { listReturnTarget } from '@/features/shared/list-return'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const route = useRoute()
const router = useRouter()
// Back to the list as it was (its search, filters and page) when the Contact was opened from it.
const backTo = computed(() => listReturnTarget(router, route.query, 'contacts'))
const app = useAppStore()
const { locale, t } = useI18n()
const detail = ref<ContactDetailDto | null>(null)
const accounts = ref<AccountSummaryDto[]>([])
const sites = ref<Array<SiteDto & { accountId: string }>>([])
const contacts = ref<ContactSummaryDto[]>([])
const loading = ref(false)
const denied = ref(false)
const notFound = ref(false)
const error = useLocaleMessage()
const requestId = ref('')
const editOpen = ref(false)
const mergeOpen = ref(false)
const deleteOpen = ref(false)
const busy = ref(false)
const actionError = useLocaleMessage()
const referencesReady = ref(false)
const referencesError = useLocaleMessage()
const currentAccount = computed(() => accounts.value.find((account) => account.id === detail.value?.contact.accountId))
// The owner of the Contact's Account: from the Account list, or from the Contact's own answer when the list does not
// have it (an archived Account is out of the list).
const accountOwner = computed(() => currentAccount.value?.owner ?? detail.value?.accountOwner ?? '')
// The Account archived (a Manager's archive, in place of a delete): the Contact and its files take no change,
// no merge, no archive, and start no Opportunity or Visit, until the Account is restored.
const accountArchived = computed(() => detail.value?.accountArchived === true)
const canWrite = computed(() => {
  const user = app.bootstrap?.user
  if (!user || !detail.value || !app.can('contact:write') || accountArchived.value) return false
  if (user.role === 'Manager') return true
  return user.role === 'Sales' && accountOwner.value === user.id
})
const canDeleteContactFiles = computed(() => canWrite.value)
const siteRestricted = computed(() => {
  const user = app.bootstrap?.user
  return user?.role === 'Sales' && Boolean(accountOwner.value) && accountOwner.value !== user.id
})
const siteDisplay = computed(() => {
  if (siteRestricted.value) return t('contacts.ownerOnly')
  return detail.value?.contact.siteName || detail.value?.contact.siteId || t('detail.notSpecified')
})
const canMerge = computed(() => app.can('contact:merge') && !accountArchived.value)
const canCreateOpportunity = computed(() => canWrite.value && app.can('deal:write'))
const canCreateVisit = computed(() => canWrite.value && app.can('visit:create') && app.can('visit:write'))
const isActive = computed(() => detail.value?.contact.status === 'Active')
const canDelete = computed(() => app.can('contact:delete') && !accountArchived.value)
const statusTone = computed<Tone>(() => detail.value?.contact.status === 'Active' ? 'positive' : detail.value?.contact.status === 'Left Company' ? 'warning' : 'neutral')
let loadSequence = 0

function relatedRoute(kind: 'opportunities' | 'visits' | 'demo-requests' | 'bookings') {
  const contact = detail.value?.contact
  if (!contact) return { path: '/contacts' }
  if (kind === 'opportunities') return { name: 'opportunities', query: { contactId: contact.id } }
  if (kind === 'bookings') return { name: 'booking', query: { contactId: contact.id } }
  if (kind === 'demo-requests') return { name: 'demo-requests', query: { contactId: contact.id } }
  return { name: 'visits', query: { contactId: contact.id } }
}
function timelineRoute(type: ContactDetailDto['timeline'][number]['type']) {
  if (type === 'Opportunity') return relatedRoute('opportunities')
  if (type === 'Booking') return relatedRoute('bookings')
  if (type === 'Demo Request') return relatedRoute('demo-requests')
  return relatedRoute('visits')
}

async function loadReferences(contact: ContactSummaryDto) {
  const [accountRows, contactRows, accountDetail] = await Promise.all([
    readAllPages((page, pageSize) => props.apiClient.listAccounts({ page, pageSize })),
    readAllPages((page, pageSize) => props.apiClient.listContacts({ accountId: contact.accountId, page, pageSize })),
    props.apiClient.getAccount360(contact.accountId),
  ])
  accounts.value = accountRows
  contacts.value = contactRows
  sites.value = accountDetail.data.sites.map((site) => ({ ...site, accountId: contact.accountId }))
  referencesReady.value = true
}
async function load() {
  const sequence = ++loadSequence
  loading.value = true
  denied.value = false
  notFound.value = false
  error.value = ''
  referencesReady.value = false
  referencesError.value = ''
  accounts.value = []
  sites.value = []
  contacts.value = []
  detail.value = null
  try {
    const result = await props.apiClient.getContact(String(route.params.contactId))
    if (sequence !== loadSequence) return
    detail.value = result.data
  } catch (reason) {
    if (sequence !== loadSequence) return
    const mapped = mapRequestError(reason)
    error.value = mapped.localizedMessage ?? mapped.message
    requestId.value = mapped.requestId
    denied.value = mapped.denied
    // A Contact that does not exist and one the user may not see answer the same (F1-12): one state, no retry.
    notFound.value = reason instanceof CrmApiError && reason.code === 'NOT_FOUND'
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
  if (!detail.value || sequence !== loadSequence) return
  try {
    await loadReferences(detail.value.contact)
  } catch {
    if (sequence !== loadSequence) return
    referencesError.value = localeMessage('Accounts, sites, and reporting-line options for editing are unavailable.', '编辑所需的客户、厂区和直属上司选项暂时无法加载。')
  }
}
async function saveContact(payload: CreateContactInput) {
  busy.value = true
  actionError.value = ''
  try {
    await props.apiClient.updateContact(detail.value!.contact.id, payload, detail.value!.contact.modified)
    editOpen.value = false
    await load()
  } catch (reason) {
    const mapped = mapRequestError(reason); actionError.value = mapped.localizedMessage ?? mapped.message
  } finally {
    busy.value = false
  }
}
async function mergeContact(payload: { survivorId: string; duplicateId: string }) {
  busy.value = true
  actionError.value = ''
  try {
    const result = await props.apiClient.mergeContacts(payload)
    mergeOpen.value = false
    await router.replace({ name: 'contact-detail', params: { contactId: result.data.id } })
    await load()
  } catch (reason) {
    const mapped = mapRequestError(reason); actionError.value = mapped.localizedMessage ?? mapped.message
  } finally {
    busy.value = false
  }
}
async function deleteContact() {
  if (!detail.value) return
  busy.value = true
  actionError.value = ''
  try {
    await props.apiClient.deleteContact(detail.value.contact.id)
    deleteOpen.value = false
    await router.push({ name: 'contacts' })
  } catch (reason) {
    const mapped = mapRequestError(reason); actionError.value = mapped.localizedMessage ?? mapped.message
  } finally {
    busy.value = false
  }
}
function createOpportunity() {
  if (!detail.value) return
  void router.push({ name: 'opportunities', query: { create: '1', accountId: detail.value.contact.accountId, contactId: detail.value.contact.id } })
}
function createVisit() {
  if (!detail.value) return
  void router.push({ name: 'visits', query: { create: '1', accountId: detail.value.contact.accountId, primaryContactId: detail.value.contact.id } })
}
function requestDeleteFromEdit() {
  if (!canDelete.value) return
  editOpen.value = false
  actionError.value = ''
  deleteOpen.value = true
}

watch(() => route.params.contactId, load)
onMounted(async () => {
  await app.loadBootstrap(props.apiClient)
  await load()
})
</script>

<template>
  <div class="contact-detail-page">
    <DataState v-if="loading && !detail" type="loading" />
    <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
    <DataState v-else-if="notFound" type="denied" :title="t('state.unavailableTitle')" :message="error" :request-id="requestId" />
    <DataState v-else-if="error || !detail" type="error" :message="error || t('detail.notFoundContact')" :request-id="requestId" @retry="load" />
    <template v-else>
      <RouterLink class="back-link detail-back-button" :to="backTo"><ArrowLeft :size="14" />{{ t('detail.backContacts') }}</RouterLink>
      <PageHeader eyebrow="CONTACT 360" :title="detail.contact.name" :description="`${detail.contact.accountName} · ${detail.contact.title} · ${personnelDisplayName(detail.contact.owner)}`">
        <button v-if="isActive && canCreateOpportunity" class="secondary-button" type="button" data-testid="new-opportunity" @click="createOpportunity"><BriefcaseBusiness :size="14" />{{ locale === 'en-US' ? 'New opportunity' : '新建 Opportunity' }}</button>
        <button v-if="isActive && canCreateVisit" class="secondary-button" type="button" data-testid="record-visit" @click="createVisit"><CalendarPlus :size="14" />{{ locale === 'en-US' ? 'Record visit' : '记录拜访' }}</button>
        <button v-if="isActive && canWrite" class="primary-button" type="button" data-testid="edit-contact" :disabled="!referencesReady" @click="actionError = ''; editOpen = true"><Edit3 :size="14" />{{ locale === 'en-US' ? 'Edit contact' : '编辑联系人' }}</button>
        <button v-if="isActive && canMerge" class="secondary-button merge-action" type="button" data-testid="merge-contact" @click="actionError = ''; mergeOpen = true"><GitMerge :size="14" />{{ locale === 'en-US' ? 'Merge duplicate' : '合并重复联系人' }}</button>
        <button v-if="canDelete" class="delete-button" type="button" data-testid="delete-contact" @click="actionError = ''; deleteOpen = true"><Trash2 :size="14" />{{ t('detail.archiveContact') }}</button>
      </PageHeader>
      <p v-if="accountArchived" class="account-archived-notice" data-account-archived-notice>{{ t('detail.contactAccountArchived') }}</p>

      <div class="contact-summary">
        <span class="avatar"><UserRound :size="24" /></span>
        <div><small>{{ t('detail.contactStatus') }}</small><StatusBadge :label="contactStatusLabel(detail.contact.status, locale)" :tone="statusTone" /></div>
        <div><small>{{ t('detail.relationship') }}</small><strong>{{ salesEnumLabel(detail.contact.relationship, locale) }}</strong></div>
        <div><small>{{ t('detail.dataQuality') }}</small><StatusBadge v-if="detail.contact.dataQuality === 'Needs Review'" data-testid="needs-review" :label="salesEnumLabel(detail.contact.dataQuality, locale)" tone="warning" /><strong v-else>{{ detail.contact.dataQuality }}</strong></div>
        <div><small>{{ t('detail.updated') }}</small><strong>{{ formatDisplayDate(detail.contact.updatedAt) }}</strong></div>
      </div>
      <p v-if="referencesError" data-testid="contact-references-unavailable">{{ referencesError }}</p>

      <div class="detail-grid">
        <SectionCard :title="t('detail.profileRelations')" eyebrow="CONTACT PROFILE">
          <dl class="profile-list">
            <div><dt>{{ t('detail.account') }}</dt><dd><RouterLink :to="{ name: 'account-detail', params: { accountId: detail.contact.accountId } }">{{ detail.contact.accountName }}</RouterLink></dd></div>
            <div><dt>{{ t('detail.site') }}</dt><dd><RouterLink v-if="detail.contact.siteId && !siteRestricted" :to="{ name: 'account-detail', params: { accountId: detail.contact.accountId } }">{{ siteDisplay }}</RouterLink><span v-else>{{ siteDisplay }}</span></dd></div>
            <div><dt>{{ t('detail.department') }}</dt><dd>{{ detail.contact.title }} / {{ detail.contact.department }}</dd></div>
            <div><dt>{{ t('detail.phone') }}</dt><dd><a v-if="detail.contact.phone" :href="`tel:${detail.contact.phone}`"><Phone :size="13" />{{ detail.contact.phone }}</a><span v-else>—</span></dd></div>
            <div><dt>{{ t('detail.email') }}</dt><dd><a v-if="detail.contact.email" :href="`mailto:${detail.contact.email}`"><Mail :size="13" />{{ detail.contact.email }}</a><span v-else>—</span></dd></div>
            <div><dt>{{ t('detail.manager') }}</dt><dd><RouterLink v-if="detail.reportsTo" :to="{ name: 'contact-detail', params: { contactId: detail.reportsTo.id } }">{{ detail.reportsTo.name }} · {{ detail.reportsTo.title }}</RouterLink><span v-else>{{ t('detail.notMaintained') }}</span></dd></div>
            <div><dt>{{ t('detail.directReports') }}</dt><dd><span v-if="!detail.directReports.length">{{ t('detail.notMaintained') }}</span><RouterLink v-for="item in detail.directReports" v-else :key="item.id" class="report-link" :to="{ name: 'contact-detail', params: { contactId: item.id } }">{{ item.name }}</RouterLink></dd></div>
          </dl>
        </SectionCard>

        <SectionCard :title="t('detail.activityTimeline')" eyebrow="ACTIVITY TIMELINE">
          <div v-if="detail.timeline.length" class="timeline">
            <RouterLink v-for="item in detail.timeline" :key="item.id" :data-timeline-id="item.id" :to="item.href"><span>{{ recordTypeLabel(item.type, locale) }}</span><strong>{{ item.type === 'Booking' ? bookingTimelineTitle(item.title, locale) : item.title }}</strong><p>{{ item.type === 'Opportunity' ? (isOpportunityStage(item.summary) ? opportunityStageLabel(item.summary, locale) : salesEnumLabel(item.summary, locale)) : item.summary }}</p><time>{{ formatDisplayDate(item.at) }}</time></RouterLink>
          </div>
          <DataState v-else type="empty" :title="t('detail.noRelatedActivity')" :message="t('detail.relatedActivityHint')" />
        </SectionCard>

        <div class="related-column">
          <SectionCard :title="t('detail.relatedBusiness')" eyebrow="RELATED BUSINESS">
            <nav class="related-links">
              <RouterLink data-related="opportunities" :to="relatedRoute('opportunities')"><span>{{ locale === 'en-US' ? 'Opportunities' : '商机' }}</span><strong>{{ detail.opportunities.length }}</strong></RouterLink>
              <RouterLink data-related="visits" :to="relatedRoute('visits')"><span>{{ t('detail.relatedVisits') }}</span><strong>{{ detail.visits.length }}</strong></RouterLink>
              <RouterLink data-related="demo-requests" :to="relatedRoute('demo-requests')"><span>{{ locale === 'en-US' ? 'Demo Requests' : 'Demo Request' }}</span><strong>{{ detail.demoRequests.length }}</strong></RouterLink>
              <RouterLink data-related="bookings" :to="relatedRoute('bookings')"><span>{{ locale === 'en-US' ? 'Bookings' : 'Booking' }}</span><strong>{{ detail.bookings.length }}</strong></RouterLink>
            </nav>
          </SectionCard>
          <ContactFilesCard :contact-id="detail.contact.id" :can-write="isActive && canWrite" :can-delete="isActive && canDeleteContactFiles" :api-client="apiClient" />
        </div>
      </div>

      <ContactModal v-if="editOpen" :contact="detail.contact" :accounts="accounts" :sites="sites" :contacts="contacts" :busy="busy" :error="actionError" :can-delete="canDelete" @close="editOpen = false" @submit="saveContact" @delete="requestDeleteFromEdit" />
      <ContactMergeModal v-if="mergeOpen" :contact="detail.contact" :contacts="contacts" :busy="busy" :error="actionError" @close="mergeOpen = false" @submit="mergeContact" />
      <ModalShell v-if="deleteOpen" :title="t('detail.archiveContact')" eyebrow="ARCHIVE" :busy="busy" :submit-label="t('detail.archiveContactAction')" danger @close="deleteOpen = false" @submit="deleteContact">
        <p class="delete-note">{{ t('detail.archiveContactWarning', { name: detail.contact.name }) }}</p>
        <p v-if="actionError" class="form-error">{{ actionError }}</p>
      </ModalShell>
    </template>
  </div>
</template>

<style scoped>
.account-archived-notice{margin:0 0 12px;padding:10px 12px;color:#5c4a16;background:#fff5df;border:1px solid #f0dda9;border-radius:9px;font-size:10px;line-height:1.6}
.back-link{display:inline-flex;align-items:center;gap:5px;margin-bottom:14px;color:var(--crm-link);font-size:11px;font-weight:700}.primary-button,.secondary-button{display:flex;align-items:center;gap:6px}.merge-action{white-space:nowrap}.delete-button{display:inline-flex;min-height:36px;align-items:center;justify-content:center;gap:6px;padding:0 12px;color:var(--crm-danger);background:#fffafa;border:1px solid #e3b9b9;border-radius:8px;outline:0;font:inherit;font-size:11px;font-weight:800;white-space:nowrap;cursor:pointer;transition:background-color .16s ease,border-color .16s ease,box-shadow .16s ease,transform .16s ease}.delete-button:hover{color:#a93333;background:var(--crm-danger-soft);border-color:#cf8585;box-shadow:0 3px 10px rgba(166,51,51,.1);transform:translateY(-1px)}.delete-button:focus-visible{border-color:var(--crm-danger);box-shadow:0 0 0 3px rgba(182,69,69,.16)}.delete-button:active{transform:translateY(0)}.contact-summary{display:grid;grid-template-columns:auto repeat(4,minmax(0,1fr));align-items:center;gap:12px;margin-bottom:14px;padding:14px 16px;background:#fff;border:1px solid var(--crm-line);border-radius:13px}.contact-summary .avatar{display:grid;width:46px;height:46px;place-items:center;color:var(--crm-brand-ink);background:var(--crm-teal-soft);border-radius:13px}.contact-summary div{display:grid;gap:5px}.contact-summary small{color:var(--crm-text-muted);font-size:9px}.contact-summary strong{color:var(--crm-navy);font-size:11px}.detail-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.15fr) minmax(240px,.72fr);gap:14px;align-items:start}.profile-list{display:grid;margin:0}.profile-list div{display:grid;grid-template-columns:90px minmax(0,1fr);gap:10px;padding:11px 0;border-bottom:1px solid var(--crm-line)}.profile-list div:last-child{border-bottom:0}.profile-list dt{color:var(--crm-text-muted);font-size:10px}.profile-list dd{display:flex;flex-wrap:wrap;gap:7px;margin:0;color:var(--crm-navy);font-size:11px}.profile-list a{display:inline-flex;align-items:center;gap:5px;color:var(--crm-link);font-weight:700}.report-link+.report-link::before{content:'·';margin-right:7px;color:var(--crm-text-muted)}.timeline{display:grid;gap:9px}.timeline>a{position:relative;display:grid;gap:4px;padding:11px 12px 11px 18px;color:inherit;background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:10px}.timeline>a::before{position:absolute;top:15px;left:8px;width:4px;height:4px;background:var(--crm-teal);border-radius:50%;content:''}.timeline span,.timeline time{color:var(--crm-text-muted);font-size:8px}.timeline strong{color:var(--crm-navy);font-size:11px}.timeline p{margin:0;color:var(--crm-text-muted);font-size:10px;line-height:1.5}.related-column{display:grid;gap:14px}.related-links{display:grid;gap:8px}.related-links a{display:flex;align-items:center;justify-content:space-between;padding:11px 12px;color:var(--crm-navy);background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:9px;font-size:10px}.related-links strong{display:grid;width:26px;height:26px;place-items:center;color:var(--crm-brand-ink);background:var(--crm-teal-soft);border-radius:8px}@media(max-width:1080px){.detail-grid{grid-template-columns:1fr 1fr}.related-column{grid-column:1/-1;grid-template-columns:1fr 1fr}}@media(max-width:700px){.contact-summary{grid-template-columns:auto 1fr 1fr}.detail-grid,.related-column{grid-template-columns:1fr}.related-column{grid-column:auto}.profile-list div{grid-template-columns:1fr}}
</style>
