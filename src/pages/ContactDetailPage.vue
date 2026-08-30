<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft, BriefcaseBusiness, CalendarPlus, Edit3, GitMerge, Mail, Phone, Trash2, UserRound } from '@lucide/vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api as defaultApi, type CrmApi } from '@/api'
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

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const route = useRoute()
const router = useRouter()
const app = useAppStore()
const detail = ref<ContactDetailDto | null>(null)
const accounts = ref<AccountSummaryDto[]>([])
const sites = ref<Array<SiteDto & { accountId: string }>>([])
const contacts = ref<ContactSummaryDto[]>([])
const loading = ref(false)
const denied = ref(false)
const error = ref('')
const requestId = ref('')
const editOpen = ref(false)
const mergeOpen = ref(false)
const deleteOpen = ref(false)
const busy = ref(false)
const actionError = ref('')
const referencesReady = ref(false)
const referencesError = ref('')
const canWrite = computed(() => app.can('contact:write'))
const canDeleteContactFiles = computed(() => {
  const user = app.bootstrap?.user
  if (!user || !detail.value) return false
  if (user.role === 'Manager') return true
  return user.role === 'Sales'
    && accounts.value.find((account) => account.id === detail.value?.contact.accountId)?.owner === user.id
})
const canMerge = computed(() => app.can('contact:merge'))
const canCreateOpportunity = computed(() => app.can('deal:write'))
const canCreateVisit = computed(() => app.can('visit:create') && app.can('visit:write'))
const isActive = computed(() => detail.value?.contact.status === 'Active')
const canDelete = computed(() => app.can('contact:delete'))
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
    error.value = mapped.message
    requestId.value = mapped.requestId
    denied.value = mapped.denied
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
  if (!detail.value || sequence !== loadSequence) return
  try {
    await loadReferences(detail.value.contact)
  } catch {
    if (sequence !== loadSequence) return
    referencesError.value = '编辑所需的客户、厂区和直属上司选项暂时无法加载。'
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
    actionError.value = mapRequestError(reason).message
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
    actionError.value = mapRequestError(reason).message
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
    actionError.value = mapRequestError(reason).message
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
    <DataState v-else-if="error || !detail" type="error" :message="error || '未找到联系人'" :request-id="requestId" @retry="load" />
    <template v-else>
      <RouterLink class="back-link detail-back-button" :to="{ name: 'contacts' }"><ArrowLeft :size="14" />返回联系人列表</RouterLink>
      <PageHeader eyebrow="CONTACT 360" :title="detail.contact.name" :description="`${detail.contact.accountName} · ${detail.contact.title} · ${personnelDisplayName(detail.contact.owner)}`">
        <button v-if="isActive && canCreateOpportunity" class="secondary-button" type="button" data-testid="new-opportunity" @click="createOpportunity"><BriefcaseBusiness :size="14" />新建 Opportunity</button>
        <button v-if="isActive && canCreateVisit" class="secondary-button" type="button" data-testid="record-visit" @click="createVisit"><CalendarPlus :size="14" />记录拜访</button>
        <button v-if="isActive && canWrite" class="primary-button" type="button" data-testid="edit-contact" :disabled="!referencesReady" @click="actionError = ''; editOpen = true"><Edit3 :size="14" />编辑联系人</button>
        <button v-if="isActive && canMerge" class="secondary-button merge-action" type="button" data-testid="merge-contact" @click="actionError = ''; mergeOpen = true"><GitMerge :size="14" />合并重复联系人</button>
        <button v-if="canDelete" class="delete-button" type="button" data-testid="delete-contact" @click="actionError = ''; deleteOpen = true"><Trash2 :size="14" />删除联系人</button>
      </PageHeader>

      <div class="contact-summary">
        <span class="avatar"><UserRound :size="24" /></span>
        <div><small>联系人状态</small><StatusBadge :label="detail.contact.status" :tone="statusTone" /></div>
        <div><small>关系强度</small><strong>{{ detail.contact.relationship }}</strong></div>
        <div><small>数据质量</small><StatusBadge v-if="detail.contact.dataQuality === 'Needs Review'" data-testid="needs-review" label="Needs Review" tone="warning" /><strong v-else>{{ detail.contact.dataQuality }}</strong></div>
        <div><small>最近更新</small><strong>{{ formatDisplayDate(detail.contact.updatedAt) }}</strong></div>
      </div>
      <p v-if="referencesError" data-testid="contact-references-unavailable">{{ referencesError }}</p>

      <div class="detail-grid">
        <SectionCard title="资料与组织关系" eyebrow="CONTACT PROFILE">
          <dl class="profile-list">
            <div><dt>客户</dt><dd><RouterLink :to="{ name: 'account-detail', params: { accountId: detail.contact.accountId } }">{{ detail.contact.accountName }}</RouterLink></dd></div>
            <div><dt>厂区</dt><dd><RouterLink v-if="detail.contact.siteId" :to="{ name: 'account-detail', params: { accountId: detail.contact.accountId } }">{{ detail.contact.siteName || detail.contact.siteId }}</RouterLink><span v-else>未指定</span></dd></div>
            <div><dt>职位 / 部门</dt><dd>{{ detail.contact.title }} / {{ detail.contact.department }}</dd></div>
            <div><dt>电话</dt><dd><a v-if="detail.contact.phone" :href="`tel:${detail.contact.phone}`"><Phone :size="13" />{{ detail.contact.phone }}</a><span v-else>—</span></dd></div>
            <div><dt>邮箱</dt><dd><a v-if="detail.contact.email" :href="`mailto:${detail.contact.email}`"><Mail :size="13" />{{ detail.contact.email }}</a><span v-else>—</span></dd></div>
            <div><dt>直属上司</dt><dd><RouterLink v-if="detail.reportsTo" :to="{ name: 'contact-detail', params: { contactId: detail.reportsTo.id } }">{{ detail.reportsTo.name }} · {{ detail.reportsTo.title }}</RouterLink><span v-else>未维护</span></dd></div>
            <div><dt>直接下属</dt><dd><span v-if="!detail.directReports.length">未维护</span><RouterLink v-for="item in detail.directReports" v-else :key="item.id" class="report-link" :to="{ name: 'contact-detail', params: { contactId: item.id } }">{{ item.name }}</RouterLink></dd></div>
          </dl>
        </SectionCard>

        <SectionCard title="活动时间线" eyebrow="ACTIVITY TIMELINE">
          <div v-if="detail.timeline.length" class="timeline">
            <RouterLink v-for="item in detail.timeline" :key="item.id" :data-timeline-id="item.id" :to="item.href"><span>{{ item.type }}</span><strong>{{ item.title }}</strong><p>{{ item.summary }}</p><time>{{ formatDisplayDate(item.at) }}</time></RouterLink>
          </div>
          <DataState v-else type="empty" title="暂无关联活动" message="联系人参与业务后，记录会汇总到这里。" />
        </SectionCard>

        <div class="related-column">
          <SectionCard title="关联业务" eyebrow="RELATED BUSINESS">
            <nav class="related-links">
              <RouterLink data-related="opportunities" :to="relatedRoute('opportunities')"><span>Opportunities</span><strong>{{ detail.opportunities.length }}</strong></RouterLink>
              <RouterLink data-related="visits" :to="relatedRoute('visits')"><span>拜访记录</span><strong>{{ detail.visits.length }}</strong></RouterLink>
              <RouterLink data-related="demo-requests" :to="relatedRoute('demo-requests')"><span>Demo Requests</span><strong>{{ detail.demoRequests.length }}</strong></RouterLink>
              <RouterLink data-related="bookings" :to="relatedRoute('bookings')"><span>Bookings</span><strong>{{ detail.bookings.length }}</strong></RouterLink>
            </nav>
          </SectionCard>
          <ContactFilesCard :contact-id="detail.contact.id" :can-write="isActive && canWrite" :can-delete="isActive && canDeleteContactFiles" :api-client="apiClient" />
        </div>
      </div>

      <ContactModal v-if="editOpen" :contact="detail.contact" :accounts="accounts" :sites="sites" :contacts="contacts" :busy="busy" :error="actionError" :can-delete="canDelete" @close="editOpen = false" @submit="saveContact" @delete="requestDeleteFromEdit" />
      <ContactMergeModal v-if="mergeOpen" :contact="detail.contact" :contacts="contacts" :busy="busy" :error="actionError" @close="mergeOpen = false" @submit="mergeContact" />
      <ModalShell v-if="deleteOpen" title="永久删除联系人" eyebrow="HARD DELETE" :busy="busy" @close="deleteOpen = false" @submit="deleteContact">
        <p class="delete-note">此操作不可恢复。联系人会从本地数据中物理删除；Opportunity 中对应关键人关联会移除，Booking 与 Demo Request 会优先改绑到同客户的现有联系人。</p>
        <p v-if="actionError" class="form-error">{{ actionError }}</p>
      </ModalShell>
    </template>
  </div>
</template>

<style scoped>
.back-link{display:inline-flex;align-items:center;gap:5px;margin-bottom:14px;color:var(--crm-teal);font-size:11px;font-weight:700}.primary-button,.secondary-button{display:flex;align-items:center;gap:6px}.merge-action{white-space:nowrap}.delete-button{display:inline-flex;min-height:36px;align-items:center;justify-content:center;gap:6px;padding:0 12px;color:var(--crm-danger);background:#fffafa;border:1px solid #e3b9b9;border-radius:8px;outline:0;font:inherit;font-size:11px;font-weight:800;white-space:nowrap;cursor:pointer;transition:background-color .16s ease,border-color .16s ease,box-shadow .16s ease,transform .16s ease}.delete-button:hover{color:#a93333;background:var(--crm-danger-soft);border-color:#cf8585;box-shadow:0 3px 10px rgba(166,51,51,.1);transform:translateY(-1px)}.delete-button:focus-visible{border-color:var(--crm-danger);box-shadow:0 0 0 3px rgba(182,69,69,.16)}.delete-button:active{transform:translateY(0)}.contact-summary{display:grid;grid-template-columns:auto repeat(4,minmax(0,1fr));align-items:center;gap:12px;margin-bottom:14px;padding:14px 16px;background:#fff;border:1px solid var(--crm-line);border-radius:13px}.contact-summary .avatar{display:grid;width:46px;height:46px;place-items:center;color:var(--crm-brand-ink);background:var(--crm-teal-soft);border-radius:13px}.contact-summary div{display:grid;gap:5px}.contact-summary small{color:var(--crm-text-muted);font-size:9px}.contact-summary strong{color:var(--crm-navy);font-size:11px}.detail-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.15fr) minmax(240px,.72fr);gap:14px;align-items:start}.profile-list{display:grid;margin:0}.profile-list div{display:grid;grid-template-columns:90px minmax(0,1fr);gap:10px;padding:11px 0;border-bottom:1px solid var(--crm-line)}.profile-list div:last-child{border-bottom:0}.profile-list dt{color:var(--crm-text-muted);font-size:10px}.profile-list dd{display:flex;flex-wrap:wrap;gap:7px;margin:0;color:var(--crm-navy);font-size:11px}.profile-list a{display:inline-flex;align-items:center;gap:5px;color:var(--crm-teal);font-weight:700}.report-link+.report-link::before{content:'·';margin-right:7px;color:var(--crm-text-muted)}.timeline{display:grid;gap:9px}.timeline>a{position:relative;display:grid;gap:4px;padding:11px 12px 11px 18px;color:inherit;background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:10px}.timeline>a::before{position:absolute;top:15px;left:8px;width:4px;height:4px;background:var(--crm-teal);border-radius:50%;content:''}.timeline span,.timeline time{color:var(--crm-text-muted);font-size:8px}.timeline strong{color:var(--crm-navy);font-size:11px}.timeline p{margin:0;color:var(--crm-text-muted);font-size:10px;line-height:1.5}.related-column{display:grid;gap:14px}.related-links{display:grid;gap:8px}.related-links a{display:flex;align-items:center;justify-content:space-between;padding:11px 12px;color:var(--crm-navy);background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:9px;font-size:10px}.related-links strong{display:grid;width:26px;height:26px;place-items:center;color:var(--crm-brand-ink);background:var(--crm-teal-soft);border-radius:8px}@media(max-width:1080px){.detail-grid{grid-template-columns:1fr 1fr}.related-column{grid-column:1/-1;grid-template-columns:1fr 1fr}}@media(max-width:700px){.contact-summary{grid-template-columns:auto 1fr 1fr}.detail-grid,.related-column{grid-template-columns:1fr}.related-column{grid-column:auto}.profile-list div{grid-template-columns:1fr}}
</style>
