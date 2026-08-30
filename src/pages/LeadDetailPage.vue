<script setup lang="ts">
import { personnelDisplayName } from '@/demo/personnel'
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft, Building2, CheckCircle2, Edit3, Mail, Phone, Plus, UserRoundSearch } from '@lucide/vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api as defaultApi, type CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import type { AccountSummaryDto, ContactSummaryDto, CreateLeadInput, LeadActivityDto, LeadConversionInput, LeadConversionResult, LeadDto, LeadStatus, SiteDto, Tone } from '@/types/crm'
import PageHeader from '@/design-system/PageHeader.vue'
import DataState from '@/design-system/DataState.vue'
import SectionCard from '@/design-system/SectionCard.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import LeadEditorModal from '@/features/leads/LeadEditorModal.vue'
import LeadConvertModal from '@/features/leads/LeadConvertModal.vue'
import { readAllPages } from '@/features/shared/read-all-pages'
import { formatDisplayDate } from '@/domain/time'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const route = useRoute()
const router = useRouter()
const app = useAppStore()
const lead = ref<LeadDto | null>(null)
const accounts = ref<AccountSummaryDto[]>([])
const segments = ref<string[]>(['Frontend', 'Advanced Packaging'])
const contacts = ref<ContactSummaryDto[]>([])
const sites = ref<Array<SiteDto & { accountId: string }>>([])
const loading = ref(false)
const denied = ref(false)
const error = ref('')
const requestId = ref('')
const editOpen = ref(false)
const convertOpen = ref(false)
const busy = ref(false)
const actionError = ref('')
const deleting = ref(false), deleteError = ref(''), deleteRequestId = ref('')
const referencesMessage = ref('')
const conversion = ref<LeadConversionResult | null>(null)
const qualificationOpen = ref(false)
const qualificationNote = ref('')
const qualificationStatus = ref<LeadStatus>('New')
const arrangementOpen = ref(false)
const arrangementAction = ref('')
const arrangementDue = ref('')
const canWrite = computed(() => app.can('deal:write'))
const canDelete = computed(() => app.bootstrap?.user.role === 'Manager')
async function deleteLead() {
  if (!lead.value || deleting.value || !window.confirm(`确认删除 Lead ${lead.value.name}？`)) return
  deleting.value = true
  deleteError.value = ''
  deleteRequestId.value = ''
  try {
    await props.apiClient.deleteLead(lead.value.id)
    await router.push({ name: 'leads' })
  } catch (reason) {
    const mapped = mapRequestError(reason)
    deleteError.value = mapped.message
    deleteRequestId.value = mapped.requestId
  } finally {
    deleting.value = false
  }
}
const canConvert = computed(() => canWrite.value && lead.value?.status !== 'Converted')
const timelineActivities = computed<LeadActivityDto[]>(() => {
  if (!lead.value) return []
  if (lead.value.activities?.length) return lead.value.activities
  if (!lead.value.nextAction) return []
  return [{
    id: `${lead.value.id}-ACT-001`,
    action: lead.value.nextAction,
    dueDate: lead.value.nextActionDue,
  }]
})
const statusTone = computed<Tone>(() => {
  if (lead.value?.status === 'Qualified' || lead.value?.status === 'Converted') return 'positive'
  if (lead.value?.status === 'Working' || lead.value?.status === 'Nurturing') return 'info'
  if (lead.value?.status === 'Disqualified') return 'danger'
  return 'neutral'
})
let sequence = 0

async function loadReferences() {
  accounts.value = await readAllPages((page, pageSize) => props.apiClient.listAccounts({ page, pageSize }))
  try {
    segments.value = (await props.apiClient.listAccountSegments()).data
  } catch {
    segments.value = ['Frontend', 'Advanced Packaging']
  }
  if (!app.can('contact:view')) {
    contacts.value = []
    sites.value = []
    return
  }
  const details = await Promise.allSettled(accounts.value.map((account) => props.apiClient.getAccount360(account.id)))
  contacts.value = details.flatMap((result) => result.status === 'fulfilled' ? result.value.data.contacts : [])
  sites.value = details.flatMap((result, index) => result.status === 'fulfilled'
    ? result.value.data.sites.map((site) => ({ ...site, accountId: accounts.value[index].id }))
    : [])
}
async function load() {
  const current = ++sequence
  loading.value = true
  denied.value = false
  error.value = ''
  lead.value = null
  try {
    const result = await props.apiClient.getLead(String(route.params.leadId))
    if (current !== sequence) return
    lead.value = result.data
    if (result.data.status === 'Converted' && result.data.convertedAccountId && result.data.convertedContactId && result.data.convertedOpportunityId) {
      conversion.value = {
        lead: result.data,
        accountId: result.data.convertedAccountId,
        contactId: result.data.convertedContactId,
        opportunityId: result.data.convertedOpportunityId,
        reusedAccount: result.data.convertedReusedAccount ?? false,
        reusedContact: result.data.convertedReusedContact ?? false,
      }
    }
  } catch (reason) {
    if (current !== sequence) return
    const mapped = mapRequestError(reason)
    error.value = mapped.message
    requestId.value = mapped.requestId
    denied.value = mapped.denied
  } finally {
    if (current === sequence) loading.value = false
  }
  if (!lead.value || current !== sequence) return
  try {
    await loadReferences()
  } catch {
    referencesMessage.value = 'Account、Contact 与厂区选项暂时无法加载；Lead 详情仍可查看。'
  }
}
async function saveLead(payload: CreateLeadInput) {
  busy.value = true
  actionError.value = ''
  try {
    const result = await props.apiClient.updateLead(lead.value!.id, payload, lead.value!.modified)
    lead.value = result.data
    editOpen.value = false
    return true
  } catch (reason) {
    actionError.value = mapRequestError(reason).message
    return false
  } finally {
    busy.value = false
  }
}
function leadInput(changes: Partial<Pick<CreateLeadInput, 'firstContactNote' | 'status' | 'nextAction' | 'nextActionDue' | 'activities'>>): CreateLeadInput {
  const current = lead.value!
  return {
    name: current.name,
    company: current.company,
    title: current.title,
    ...(current.phone ? { phone: current.phone } : {}),
    ...(current.email ? { email: current.email } : {}),
    source: current.source,
    status: current.status,
    owner: current.owner,
    interest: current.interest,
    firstContactNote: current.firstContactNote,
    nextAction: current.nextAction,
    nextActionDue: current.nextActionDue,
    activities: current.activities,
    ...changes,
  }
}
function startQualificationEdit() {
  if (!lead.value) return
  actionError.value = ''
  qualificationNote.value = lead.value.firstContactNote
  qualificationStatus.value = lead.value.status
  qualificationOpen.value = true
}
async function saveQualification() {
  const saved = await saveLead(leadInput({
    firstContactNote: qualificationNote.value,
    status: qualificationStatus.value,
  }))
  if (saved) qualificationOpen.value = false
}
function startArrangement() {
  if (!lead.value) return
  actionError.value = ''
  arrangementAction.value = ''
  arrangementDue.value = ''
  arrangementOpen.value = true
}
async function saveArrangement() {
  const activities = timelineActivities.value
  const saved = await saveLead(leadInput({
    nextAction: arrangementAction.value,
    nextActionDue: arrangementDue.value,
    activities: [
      ...activities,
      {
        id: `${lead.value!.id}-ACT-${String(activities.length + 1).padStart(3, '0')}`,
        action: arrangementAction.value,
        dueDate: arrangementDue.value,
      },
    ],
  }))
  if (saved) arrangementOpen.value = false
}
async function convertLead(payload: LeadConversionInput) {
  if (!lead.value) return
  busy.value = true
  actionError.value = ''
  try {
    const result = await props.apiClient.convertLead(lead.value.id, payload)
    lead.value = result.data.lead
    conversion.value = result.data
    convertOpen.value = false
  } catch (reason) {
    actionError.value = mapRequestError(reason).message
  } finally {
    busy.value = false
  }
}

watch(() => route.params.leadId, load)
onMounted(async () => {
  await app.loadBootstrap(props.apiClient)
  await load()
})
</script>

<template>
  <div class="lead-detail-page">
    <DataState v-if="loading && !lead" type="loading" />
    <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
    <DataState v-else-if="error || !lead" type="error" :message="error || '未找到 Lead'" :request-id="requestId" @retry="load" />
    <template v-else>
      <RouterLink class="back-link detail-back-button" :to="{ name: 'leads' }"><ArrowLeft :size="14" />返回 Leads</RouterLink>
      <PageHeader eyebrow="LEAD 360" :title="lead.name" :description="`${lead.company} · ${lead.title} · ${personnelDisplayName(lead.owner)}`">
        <button v-if="canDelete" class="danger-button" type="button" data-delete-lead :disabled="deleting" @click="deleteLead">删除 Lead</button>
        <button v-if="canConvert" class="primary-button" type="button" data-testid="convert-lead" @click="actionError = ''; convertOpen = true"><CheckCircle2 :size="14" />转换 Lead</button>
        <button v-if="canWrite && lead.status !== 'Converted'" class="secondary-button" type="button" data-testid="edit-lead" @click="actionError = ''; editOpen = true"><Edit3 :size="14" />编辑 Lead</button>
      </PageHeader>
      <p v-if="deleteError" class="inline-error" data-delete-error>{{ deleteError }}<small v-if="deleteRequestId">Request ID {{ deleteRequestId }}</small></p>

      <div class="lead-summary">
        <span class="avatar"><UserRoundSearch :size="24" /></span>
        <div><small>Lead 状态</small><StatusBadge :label="lead.status" :tone="statusTone" /></div>
        <div><small>线索来源</small><strong>{{ lead.source }}</strong></div>
        <div><small>负责人</small><strong>{{ personnelDisplayName(lead.owner) }}</strong></div>
        <div><small>最近更新</small><strong>{{ formatDisplayDate(lead.updatedAt) }}</strong></div>
      </div>
      <p v-if="referencesMessage" class="reference-note">{{ referencesMessage }}</p>

      <section v-if="conversion" class="conversion-result" data-testid="conversion-result">
        <CheckCircle2 :size="20" />
        <div><strong>转换已完成</strong><p>Lead 已从潜在线索转为正式业务记录，重复提交不会再次创建。</p></div>
        <RouterLink :to="{ name: 'account-detail', params: { accountId: conversion.accountId } }">Account · {{ conversion.accountId }}</RouterLink>
        <RouterLink :to="{ name: 'contact-detail', params: { contactId: conversion.contactId } }">Contact · {{ conversion.contactId }}</RouterLink>
        <RouterLink :to="{ name: 'opportunities', query: { opportunityId: conversion.opportunityId } }">Opportunity · {{ conversion.opportunityId }}</RouterLink>
      </section>

      <div class="detail-grid">
        <SectionCard title="线索资料" eyebrow="LEAD PROFILE">
          <dl class="profile-list">
            <div><dt>公司</dt><dd><Building2 :size="13" />{{ lead.company }}</dd></div>
            <div><dt>职位</dt><dd>{{ lead.title }}</dd></div>
            <div><dt>电话</dt><dd><a v-if="lead.phone" :href="`tel:${lead.phone}`"><Phone :size="13" />{{ lead.phone }}</a><span v-else>—</span></dd></div>
            <div><dt>邮箱</dt><dd><a v-if="lead.email" :href="`mailto:${lead.email}`"><Mail :size="13" />{{ lead.email }}</a><span v-else>—</span></dd></div>
            <div><dt>初步兴趣</dt><dd>{{ lead.interest || '未记录' }}</dd></div>
            <div><dt>下一步</dt><dd>{{ lead.nextAction || '未设置' }}<span v-if="lead.nextActionDue">· {{ lead.nextActionDue }}</span></dd></div>
          </dl>
        </SectionCard>
        <SectionCard title="首次联系与判断" eyebrow="QUALIFICATION">
          <template v-if="canWrite && lead.status !== 'Converted'" #action>
            <button class="card-action" type="button" data-testid="edit-qualification" @click="startQualificationEdit"><Edit3 :size="13" />更改</button>
          </template>
          <form v-if="qualificationOpen" class="inline-form" @submit.prevent="saveQualification">
            <label><span>首次联系与判断</span><textarea v-model="qualificationNote" aria-label="首次联系与判断" rows="4" required /></label>
            <label><span>判断结果</span><select v-model="qualificationStatus" aria-label="判断结果"><option>New</option><option>Working</option><option>Qualified</option><option>Nurturing</option><option>Disqualified</option></select></label>
            <p v-if="actionError" class="inline-error">{{ actionError }}</p>
            <div class="inline-actions"><button class="text-button" type="button" @click="qualificationOpen = false">取消</button><button class="primary-button compact" type="submit" data-testid="save-qualification" :disabled="busy">保存判断</button></div>
          </form>
          <template v-else>
            <div class="note-card"><small>FIRST CONTACT NOTE</small><p>{{ lead.firstContactNote || '尚未记录首次联系结果。' }}</p></div>
            <div class="qualification-copy"><strong>Lead 回答“这个人值不值得跟进”</strong><p>判断结果用于安排跟进策略，不限制是否可以转换为 Opportunity。</p></div>
          </template>
        </SectionCard>
        <SectionCard title="活动时间线" eyebrow="ACTIVITY TIMELINE">
          <template v-if="canWrite && lead.status !== 'Converted'" #action>
            <button class="card-action" type="button" data-testid="add-arrangement" @click="startArrangement"><Plus :size="13" />增添安排</button>
          </template>
          <form v-if="arrangementOpen" class="inline-form arrangement-form" @submit.prevent="saveArrangement">
            <label><span>后续安排</span><input v-model="arrangementAction" aria-label="后续安排" required /></label>
            <label><span>安排日期</span><input v-model="arrangementDue" aria-label="安排日期" type="date" required /></label>
            <p v-if="actionError" class="inline-error">{{ actionError }}</p>
            <div class="inline-actions"><button class="text-button" type="button" @click="arrangementOpen = false">取消</button><button class="primary-button compact" type="submit" data-testid="save-arrangement" :disabled="busy">保存安排</button></div>
          </form>
          <div class="timeline">
            <article><span></span><div><small>{{ formatDisplayDate(lead.createdAt) }}</small><strong>Lead 创建</strong><p>来源：{{ lead.source }}</p></div></article>
            <article v-for="activity in timelineActivities" :key="activity.id"><span></span><div><small>{{ formatDisplayDate(activity.dueDate || lead.updatedAt) }}</small><strong>后续安排</strong><p>{{ activity.action }}</p></div></article>
            <article v-if="!timelineActivities.length"><span></span><div><small>{{ formatDisplayDate(lead.updatedAt) }}</small><strong>后续安排</strong><p>暂无下一步任务</p></div></article>
            <article v-if="lead.convertedAt"><span></span><div><small>{{ lead.convertedAt }}</small><strong>转换为正式业务记录</strong><p>{{ lead.convertedOpportunityId }}</p></div></article>
          </div>
        </SectionCard>
      </div>

      <LeadEditorModal v-if="editOpen" :lead="lead" :busy="busy" :error="actionError" @close="editOpen = false" @submit="saveLead" />
      <LeadConvertModal v-if="convertOpen" :lead="lead" :accounts="accounts" :contacts="contacts" :sites="sites" :segments="segments" :busy="busy" :error="actionError" @close="convertOpen = false" @submit="convertLead" />
    </template>
  </div>
</template>

<style scoped>
.back-link{display:inline-flex;align-items:center;gap:5px;margin-bottom:14px;color:var(--crm-teal);font-size:11px;font-weight:700}.lead-detail-page :deep(.page-header-actions){align-items:center}.lead-summary{display:grid;grid-template-columns:auto repeat(4,minmax(0,1fr));align-items:center;gap:12px;margin-bottom:14px;padding:14px 16px;background:#fff;border:1px solid var(--crm-line);border-radius:13px}.lead-summary .avatar{display:grid;width:46px;height:46px;place-items:center;color:var(--crm-brand-ink);background:var(--crm-teal-soft);border-radius:13px}.lead-summary div{display:grid;gap:5px}.lead-summary small{color:var(--crm-text-muted);font-size:9px}.lead-summary strong{color:var(--crm-navy);font-size:11px}.reference-note{margin:0 0 12px;color:var(--crm-warning);font-size:10px}.conversion-result{display:grid;grid-template-columns:auto minmax(220px,1fr) repeat(3,auto);align-items:center;gap:12px;margin-bottom:14px;padding:13px 15px;color:var(--crm-brand-ink);background:#edf8f5;border:1px solid #b8ded7;border-radius:12px}.conversion-result>div{display:grid;gap:3px}.conversion-result p{margin:0;color:var(--crm-text-muted);font-size:9px}.conversion-result a{padding:8px 9px;color:var(--crm-teal);background:#fff;border:1px solid #cfe6e1;border-radius:8px;font-size:9px;font-weight:800}.detail-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;align-items:start}.profile-list{display:grid;margin:0}.profile-list div{display:grid;grid-template-columns:85px minmax(0,1fr);gap:10px;padding:11px 0;border-bottom:1px solid var(--crm-line)}.profile-list div:last-child{border-bottom:0}.profile-list dt{color:var(--crm-text-muted);font-size:10px}.profile-list dd{display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin:0;color:var(--crm-navy);font-size:11px}.profile-list a{display:inline-flex;align-items:center;gap:5px;color:var(--crm-teal)}.card-action{display:inline-flex;align-items:center;gap:5px;padding:6px 9px;color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line);border-radius:7px;font-size:9px;font-weight:800;cursor:pointer}.note-card{padding:13px;background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:10px}.note-card small{color:var(--crm-teal);font-size:8px;font-weight:800;letter-spacing:.08em}.note-card p,.qualification-copy p{margin:7px 0 0;color:var(--crm-text-muted);font-size:10px;line-height:1.65}.qualification-copy{margin-top:12px;padding:13px;color:var(--crm-navy);background:#fff8ea;border-left:3px solid var(--crm-warning);border-radius:8px}.qualification-copy strong{font-size:10px}.inline-form{display:grid;gap:10px;margin-bottom:14px;padding:12px;background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:10px}.inline-form label{display:grid;gap:5px;color:var(--crm-text-muted);font-size:9px;font-weight:800}.inline-form input,.inline-form select,.inline-form textarea{width:100%;min-height:36px;padding:8px 9px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:7px;outline:0;font:inherit}.inline-form textarea{resize:vertical}.inline-form input:focus,.inline-form select:focus,.inline-form textarea:focus{border-color:var(--crm-teal)}.inline-actions{display:flex;justify-content:flex-end;gap:8px}.inline-actions .compact{min-height:32px;padding:6px 11px;font-size:9px}.text-button{padding:6px 9px;color:var(--crm-text-muted);background:transparent;border:0;font-size:9px;font-weight:800;cursor:pointer}.inline-error{margin:0;color:var(--crm-danger);font-size:9px}.timeline{display:grid;gap:12px}.timeline article{display:grid;grid-template-columns:10px 1fr;gap:8px}.timeline article>span{width:7px;height:7px;margin-top:4px;background:var(--crm-teal);border:2px solid #d9efeb;border-radius:50%}.timeline article>div{display:grid;gap:3px}.timeline small{color:var(--crm-text-muted);font-size:8px}.timeline strong{color:var(--crm-navy);font-size:10px}.timeline p{margin:0;color:var(--crm-text-muted);font-size:9px}@media(max-width:1100px){.detail-grid{grid-template-columns:1fr 1fr}.detail-grid>*:last-child{grid-column:1/-1}.conversion-result{grid-template-columns:auto 1fr}.conversion-result a{grid-column:2}}@media(max-width:700px){.lead-summary,.detail-grid{grid-template-columns:1fr}.lead-summary{grid-template-columns:auto 1fr 1fr}.detail-grid>*:last-child{grid-column:auto}.profile-list div{grid-template-columns:1fr}}
</style>
