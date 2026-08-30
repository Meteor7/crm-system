<script setup lang="ts">
import { personnelDisplayName } from '@/demo/personnel'
import { computed, reactive, ref, watch } from 'vue'
import { CalendarDays, Download, Factory, FileSignature, FlaskConical, MapPin, Target, Users } from '@lucide/vue'
import type { CrmApi } from '@/api'
import type { Account360Dto, Tone } from '@/types/crm'
import { useAppStore } from '@/stores/app'
import { mapRequestError, readRequestMeta, type RequestMetaState } from '@/api/request-state'
import { buildCustomerReportModel } from './customer-report-model'
import { downloadCustomerReport } from './xlsx-writer'
import DataState from '@/design-system/DataState.vue'
import DataNotice from '@/design-system/DataNotice.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import PaginationControls from '@/features/shared/PaginationControls.vue'
import { formatMoney, moneyByCurrency } from '@/domain/money'
import { formatDisplayDate } from '@/domain/time'

const props = defineProps<{ accountId: string; apiClient: CrmApi }>()
const emit = defineEmits<{ loaded: [detail: Account360Dto]; 'manage-sites': [] }>()
const app = useAppStore()
const detail = ref<Account360Dto | null>(null), loading = ref(false), error = ref(''), exportError = ref(''), denied = ref(false), requestId = ref(''), meta = ref<RequestMetaState | null>(null)
const canExport = computed(() => app.can('account:view'))
const canWrite = computed(() => {
  if (!app.can('account:write') || !detail.value) return false
  return app.bootstrap?.user.role === 'Manager' || app.bootstrap?.user.id === detail.value.account.owner
})
const confirmedBooking = computed(() => detail.value ? moneyByCurrency(detail.value.bookings.filter((item) => item.status === 'Confirmed')) : [])
const relationshipTone = (value: string): Tone => value === 'Strong' ? 'positive' : value === 'Weak' ? 'danger' : 'warning'
type ProjectSection = 'deals' | 'contracts' | 'activities' | 'demos'
type ProjectTypeFilter = 'all' | 'booking' | 'opportunity'
interface ProjectRow {
  id: string
  title: string
  meta: string
  status: string
  tone: Tone
}
const selectedProjectType = ref<ProjectTypeFilter>('all')
const selectedProject = ref('all')
const PROJECT_PAGE_SIZE = 5
const sectionPages = reactive<Record<ProjectSection, number>>({ deals: 1, contracts: 1, activities: 1, demos: 1 })
const projectOptions = computed(() => {
  if (!detail.value) return []
  const opportunities = detail.value.opportunities.map((item) => ({
    key: `opportunity:${item.id}`,
    label: `${item.id} · ${item.title}`,
    owner: item.owner,
    type: 'opportunity' as const,
  }))
  const bookings = detail.value.bookings.map((item) => ({
    key: `booking:${item.id}`,
    label: `${item.id} · ${item.title}`,
    owner: item.owner,
    type: 'booking' as const,
  }))
  return [...opportunities, ...bookings].filter((item) =>
    selectedProjectType.value === 'all' || item.type === selectedProjectType.value)
})
const selectedOpportunityId = computed(() => selectedProject.value.startsWith('opportunity:') ? selectedProject.value.slice(12) : '')
const selectedBookingId = computed(() => selectedProject.value.startsWith('booking:') ? selectedProject.value.slice(8) : '')
const selectedBooking = computed(() => detail.value?.bookings.find((item) => item.id === selectedBookingId.value))
const relevantOpportunityIds = computed(() => {
  if (!detail.value) return new Set<string>()
  if (selectedOpportunityId.value) return new Set([selectedOpportunityId.value])
  if (selectedBooking.value?.sourceOpportunityId) return new Set([selectedBooking.value.sourceOpportunityId])
  if (selectedProject.value === 'all' && selectedProjectType.value === 'opportunity') {
    return new Set(detail.value.opportunities.map((item) => item.id))
  }
  if (selectedProject.value === 'all' && selectedProjectType.value === 'booking') {
    return new Set(detail.value.bookings.map((item) => item.sourceOpportunityId).filter(Boolean) as string[])
  }
  return new Set<string>()
})
const showAllRelatedRecords = computed(() => selectedProject.value === 'all' && selectedProjectType.value === 'all')
const filteredOpportunities = computed(() => {
  if (!detail.value) return []
  if (selectedProject.value === 'all') return selectedProjectType.value === 'booking' ? [] : detail.value.opportunities
  return selectedOpportunityId.value ? detail.value.opportunities.filter((item) => item.id === selectedOpportunityId.value) : []
})
const filteredBookings = computed(() => {
  if (!detail.value) return []
  if (selectedProject.value === 'all') return selectedProjectType.value === 'opportunity' ? [] : detail.value.bookings
  if (selectedOpportunityId.value) {
    return selectedProjectType.value === 'all'
      ? detail.value.bookings.filter((item) => item.sourceOpportunityId === selectedOpportunityId.value)
      : []
  }
  return detail.value.bookings.filter((item) => item.id === selectedBookingId.value)
})
const filteredContracts = computed(() => {
  if (!detail.value) return []
  if (showAllRelatedRecords.value) return detail.value.quotations
  return detail.value.quotations.filter((item) => Boolean(item.opportunityId && relevantOpportunityIds.value.has(item.opportunityId)))
})
const filteredVisits = computed(() => {
  if (!detail.value) return []
  if (showAllRelatedRecords.value) return detail.value.visits
  return detail.value.visits.filter((item) => Boolean(item.opportunityId && relevantOpportunityIds.value.has(item.opportunityId)))
})
const filteredActions = computed(() => {
  if (!detail.value) return []
  if (showAllRelatedRecords.value) return detail.value.actions
  return detail.value.actions.filter((item) => Boolean(item.opportunityId && relevantOpportunityIds.value.has(item.opportunityId)))
})
const filteredDemoRequests = computed(() => {
  if (!detail.value) return []
  if (showAllRelatedRecords.value) return detail.value.demoRequests
  return detail.value.demoRequests.filter((item) => Boolean(item.opportunityId && relevantOpportunityIds.value.has(item.opportunityId)))
})
const filteredEvaluations = computed(() => {
  if (!detail.value) return []
  if (showAllRelatedRecords.value) return detail.value.evaluations
  const requestIds = new Set(filteredDemoRequests.value.map((item) => item.id))
  const requirementIds = new Set(detail.value.opportunities
    .filter((item) => relevantOpportunityIds.value.has(item.id))
    .map((item) => item.sourceRequirementId)
    .filter(Boolean))
  return detail.value.evaluations.filter((item) =>
    Boolean(item.demoRequestId && requestIds.has(item.demoRequestId))
    || Boolean(item.requirementId && requirementIds.has(item.requirementId)))
})
const dealRows = computed<ProjectRow[]>(() => [
  ...filteredOpportunities.value.map((item) => ({
    id: item.id, title: item.title, meta: `${item.id} · ${formatMoney(item.amount, item.currency)} · ${item.owner}`,
    status: item.stage, tone: item.stage === 'Won' ? 'positive' as const : item.stage === 'Lost' ? 'danger' as const : 'info' as const,
  })),
  ...filteredBookings.value.map((item) => ({
    id: item.id, title: item.title, meta: `${item.id} · ${formatMoney(item.amount, item.currency)} · ${formatDisplayDate(item.bookingDate)}`,
    status: item.status, tone: item.status === 'Confirmed' ? 'positive' as const : 'warning' as const,
  })),
])
const contractRows = computed<ProjectRow[]>(() => filteredContracts.value.map((item) => ({
  id: item.id, title: `${item.quotationType} Quotation · ${item.refNo}`, meta: `${item.id} · ${item.opportunityTitle || 'Others'} · ${personnelDisplayName(item.owner)}`,
  status: item.status, tone: item.status === 'Accepted' ? 'positive' : item.status === 'Rejected' || item.status === 'Expired' ? 'danger' : item.status === 'Published' ? 'info' : 'warning',
})))
const activityRows = computed<ProjectRow[]>(() => [
  ...filteredVisits.value.map((item) => ({
    id: item.id, title: item.subject, meta: `${formatDisplayDate(item.date)} · ${item.type} · ${item.nextAction || '—'}`,
    status: item.status, tone: item.status === 'Manager Reviewed' ? 'positive' as const : 'info' as const,
  })),
  ...filteredActions.value.map((item) => ({
    id: item.id, title: item.title, meta: `${item.owner} · ${formatDisplayDate(item.due)} · ${item.sourceType}`,
    status: item.status, tone: item.status === 'Completed' ? 'positive' as const : 'warning' as const,
  })),
])
const demoRows = computed<ProjectRow[]>(() => [
  ...filteredDemoRequests.value.map((item) => ({
    id: item.id, title: item.title, meta: `${item.id} · ${item.requestedEquipment} · ${item.targetDate}`,
    status: item.status, tone: item.status === 'Converted' ? 'positive' as const : 'info' as const,
  })),
  ...filteredEvaluations.value.map((item) => ({
    id: item.id, title: item.title, meta: `${item.id} · ${item.wafers} Wafers · ${item.owner}`,
    status: item.status, tone: 'info' as const,
  })),
])
function pagedRows(rows: ProjectRow[], section: ProjectSection) {
  const start = (sectionPages[section] - 1) * PROJECT_PAGE_SIZE
  return rows.slice(start, start + PROJECT_PAGE_SIZE)
}
function resetSectionPages() {
  Object.keys(sectionPages).forEach((key) => { sectionPages[key as ProjectSection] = 1 })
}
function selectProjectType(type: ProjectTypeFilter) {
  selectedProjectType.value = type
  selectedProject.value = 'all'
  resetSectionPages()
}
let loadSequence = 0

async function load() {
  if (!props.accountId) { detail.value = null; return }
  await app.loadBootstrap(props.apiClient)
  const sequence = ++loadSequence, accountId = props.accountId
  detail.value = null; loading.value = true; error.value = ''; denied.value = false; requestId.value = ''; meta.value = null
  try {
    const result = await props.apiClient.getAccount360(accountId)
    if (sequence === loadSequence && accountId === props.accountId) { detail.value = result.data; meta.value = readRequestMeta(result); emit('loaded', result.data) }
  } catch (reason) {
    if (sequence === loadSequence && accountId === props.accountId) { const mapped = mapRequestError(reason); error.value = mapped.message; requestId.value = mapped.requestId; denied.value = mapped.denied }
  } finally { if (sequence === loadSequence && accountId === props.accountId) loading.value = false }
}
function exportReport() {
  if (!detail.value) return
  exportError.value = ''
  try { downloadCustomerReport(buildCustomerReportModel(detail.value, new Date().toISOString().slice(0, 10))) }
  catch (reason) { exportError.value = reason instanceof Error ? reason.message : '客户报告导出失败，请重试' }
}
watch(() => props.accountId, () => {
  selectedProjectType.value = 'all'
  selectedProject.value = 'all'
  resetSectionPages()
  load()
}, { immediate: true })
watch(selectedProject, resetSectionPages)
</script>

<template>
  <section class="account-profile">
    <DataState v-if="!accountId" type="empty" title="请选择客户" message="从左侧客户列表选择后查看完整档案。" />
    <DataState v-else-if="loading" type="loading" />
    <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
    <DataState v-else-if="error" type="error" :message="error" :request-id="requestId" @retry="load" />
    <template v-else-if="detail">
      <DataNotice v-if="meta?.stale" :message="meta.message" :request-id="meta.requestId" @refresh="load" />
      <div class="account-360" data-testid="account-360">
        <header class="profile-hero">
          <span class="hero-mark">{{ detail.account.shortName.slice(0, 2) }}</span>
          <div><span class="eyebrow">ACCOUNT 360</span><h2>{{ detail.account.name }}</h2><p><MapPin :size="13" />{{ detail.account.city }} · {{ detail.account.region }} · {{ detail.account.segment }} · Owner {{ personnelDisplayName(detail.account.owner) }}</p></div>
          <div class="hero-actions"><StatusBadge :label="`${detail.account.tier} 级客户`" tone="positive" /><button v-if="canExport" class="report-button" type="button" data-testid="export-customer-report" @click="exportReport"><Download :size="14" />导出客户报告</button><small v-if="exportError" class="export-error">{{ exportError }}</small></div>
        </header>

        <section class="profile-kpis">
          <div><span>CONFIRMED BOOKING</span><strong v-for="total in confirmedBooking" :key="total.currency">{{ formatMoney(total.amount, total.currency) }}</strong></div><div><span>关键人</span><strong>{{ detail.contacts.length }}</strong></div><div><span>拜访记录</span><strong>{{ detail.visits.length }}</strong></div><div><span>数据完整度</span><strong>{{ detail.account.completeness }}%</strong></div>
        </section>

        <div class="profile-grid">
          <section class="profile-section"><header><Factory :size="16" /><strong>Site / 厂区</strong><span>{{ detail.sites.length }}</span><button v-if="canWrite" type="button" class="profile-section-action" data-manage-sites @click="emit('manage-sites')">管理厂区</button></header><article v-for="site in detail.sites" :key="site.id"><div><strong>{{ site.name }}</strong><small>{{ site.city }} · {{ site.type }} · {{ site.process }}</small></div><StatusBadge :label="site.status" tone="positive" /></article><div v-if="!detail.sites.length" class="mini-empty">暂无厂区记录</div></section>
          <section class="profile-section"><header><Users :size="16" /><strong>关键人与组织关系</strong><span>{{ detail.contacts.length }}</span></header><article v-for="contact in detail.contacts" :key="contact.id"><span class="avatar">{{ contact.name.slice(-1) }}</span><div><strong>{{ contact.name }} · {{ contact.title }}</strong><small>{{ contact.department }} · {{ contact.role }} · {{ contact.email || '—' }}</small></div><StatusBadge :label="contact.relationship" :tone="relationshipTone(contact.relationship)" /></article><div v-if="!detail.contacts.length" class="mini-empty">关键人关系待补充</div></section>
          <section class="project-workspace">
            <header class="project-workspace-header">
              <div><span class="eyebrow">PROJECT BUSINESS VIEW</span><h3>项目业务视图</h3><p>选择项目后，商机、合同、拜访与 Demo 信息同步切换。</p></div>
              <div class="project-filter-controls">
                <div class="project-type-filter" aria-label="项目类型筛选">
                  <button type="button" data-testid="project-type-all" :class="{ active: selectedProjectType === 'all' }" @click="selectProjectType('all')">全部</button>
                  <button type="button" data-testid="project-type-booking" :class="{ active: selectedProjectType === 'booking' }" @click="selectProjectType('booking')">Booking</button>
                  <button type="button" data-testid="project-type-opportunity" :class="{ active: selectedProjectType === 'opportunity' }" @click="selectProjectType('opportunity')">Opportunities</button>
                </div>
                <label>
                  <span>对应项目与负责人</span>
                  <select v-model="selectedProject" data-testid="account-project-filter" aria-label="对应项目与负责人">
                    <option value="all">{{ selectedProjectType === 'booking' ? '全部 Booking' : selectedProjectType === 'opportunity' ? '全部 Opportunities' : '全部项目' }}</option>
                    <option v-for="project in projectOptions" :key="project.key" :value="project.key">{{ project.label }} · {{ personnelDisplayName(project.owner) }}</option>
                  </select>
                </label>
              </div>
            </header>

            <div class="project-section-grid">
              <section class="project-section">
                <header><Target :size="16" /><strong>商机与 Booking</strong><span>{{ dealRows.length }}</span></header>
                <article v-for="item in pagedRows(dealRows, 'deals')" :key="item.id"><div><strong>{{ item.title }}</strong><small>{{ item.meta }}</small></div><StatusBadge :label="item.status" :tone="item.tone" /></article>
                <div v-if="!dealRows.length" class="mini-empty">该项目暂无商机或 Booking</div>
                <PaginationControls v-if="dealRows.length > PROJECT_PAGE_SIZE" :page="sectionPages.deals" :page-size="PROJECT_PAGE_SIZE" :total="dealRows.length" @change="sectionPages.deals = $event" />
              </section>
              <section class="project-section">
                <header><FileSignature :size="16" /><strong>合同</strong><span>{{ contractRows.length }}</span></header>
                <article v-for="item in pagedRows(contractRows, 'contracts')" :key="item.id"><div><strong>{{ item.title }}</strong><small>{{ item.meta }}</small></div><StatusBadge :label="item.status" :tone="item.tone" /></article>
                <div v-if="!contractRows.length" class="mini-empty">该项目暂无关联合同</div>
                <PaginationControls v-if="contractRows.length > PROJECT_PAGE_SIZE" :page="sectionPages.contracts" :page-size="PROJECT_PAGE_SIZE" :total="contractRows.length" @change="sectionPages.contracts = $event" />
              </section>
              <section class="project-section">
                <header><CalendarDays :size="16" /><strong>拜访与下一步</strong><span>{{ activityRows.length }}</span></header>
                <article v-for="item in pagedRows(activityRows, 'activities')" :key="item.id"><div><strong>{{ item.title }}</strong><small>{{ item.meta }}</small></div><StatusBadge :label="item.status" :tone="item.tone" /></article>
                <div v-if="!activityRows.length" class="mini-empty">该项目暂无拜访或行动</div>
                <PaginationControls v-if="activityRows.length > PROJECT_PAGE_SIZE" :page="sectionPages.activities" :page-size="PROJECT_PAGE_SIZE" :total="activityRows.length" @change="sectionPages.activities = $event" />
              </section>
              <section class="project-section">
                <header><FlaskConical :size="16" /><strong>Demo / Wafer Test</strong><span>{{ demoRows.length }}</span></header>
                <article v-for="item in pagedRows(demoRows, 'demos')" :key="item.id"><div><strong>{{ item.title }}</strong><small>{{ item.meta }}</small></div><StatusBadge :label="item.status" :tone="item.tone" /></article>
                <div v-if="!demoRows.length" class="mini-empty">该项目暂无 Demo 或 Test</div>
                <PaginationControls v-if="demoRows.length > PROJECT_PAGE_SIZE" :page="sectionPages.demos" :page-size="PROJECT_PAGE_SIZE" :total="demoRows.length" @change="sectionPages.demos = $event" />
              </section>
            </div>
          </section>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.export-error{max-width:180px;color:#ffd7d0;font-size:8px}
.account-profile{min-width:0;min-height:620px;overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:14px}.account-360{min-height:100%}.profile-hero{display:grid;grid-template-columns:50px minmax(0,1fr) auto;align-items:center;gap:14px;padding:22px 24px;color:#fff;background:var(--crm-navy)}.hero-mark{display:grid;width:50px;height:50px;place-items:center;color:var(--crm-positive);background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.13);border-radius:14px;font-size:12px;font-weight:800}.eyebrow{color:#93c7c1;font-size:8px;font-weight:800;letter-spacing:.13em}.profile-hero h2{margin:4px 0;color:#fff;font-size:18px}.profile-hero p{display:flex;align-items:center;gap:4px;margin:0;color:rgba(255,255,255,.58);font-size:9px}.hero-actions{display:flex;align-items:center;gap:8px}.report-button{display:flex;height:34px;align-items:center;gap:6px;padding:0 10px;color:#fff;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.2);border-radius:9px;font-size:9px;font-weight:700;cursor:pointer}.profile-kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:1px;background:var(--crm-line);border-bottom:1px solid var(--crm-line)}.profile-kpis div{display:grid;gap:4px;padding:12px 14px;background:#fff}.profile-kpis span{color:var(--crm-text-muted);font-size:7px;font-weight:700;letter-spacing:.05em}.profile-kpis strong{color:var(--crm-navy);font-size:15px;font-variant-numeric:tabular-nums}.profile-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:14px;background:var(--crm-surface)}.profile-section{padding:13px;background:#fff;border:1px solid var(--crm-line);border-radius:11px}.profile-section>header{display:flex;align-items:center;gap:7px;margin-bottom:7px;color:var(--crm-teal)}.profile-section>header strong{flex:1;color:var(--crm-navy);font-size:10px}.profile-section>header span{color:var(--crm-text-muted);font-size:8px}.profile-section-action{padding:4px 10px;font-size:8px;font-weight:800;color:var(--crm-teal);background:var(--crm-teal-soft);border:1px solid transparent;border-radius:7px;cursor:pointer}.profile-section article{display:flex;align-items:center;gap:8px;min-height:46px;padding:7px 0;border-bottom:1px solid var(--crm-line)}.profile-section article:last-child{border-bottom:0}.profile-section article>div{display:grid;min-width:0;flex:1;gap:4px}.profile-section article strong{overflow:hidden;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.profile-section article small{overflow:hidden;color:var(--crm-text-muted);font-size:8px;text-overflow:ellipsis;white-space:nowrap}.avatar{display:grid;width:28px;height:28px;flex:0 0 auto;place-items:center;color:var(--crm-teal);background:var(--crm-teal-soft);border-radius:8px;font-size:9px;font-weight:800}.project-workspace{grid-column:1/-1;overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.project-workspace-header{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:15px 16px;border-bottom:1px solid var(--crm-line)}.project-workspace-header h3{margin:4px 0;color:var(--crm-navy);font-size:13px}.project-workspace-header p{margin:0;color:var(--crm-text-muted);font-size:8px}.project-filter-controls{display:flex;align-items:flex-end;gap:10px}.project-type-filter{display:flex;padding:3px;background:#f1f5f4;border:1px solid var(--crm-line);border-radius:9px}.project-type-filter button{height:28px;padding:0 10px;color:var(--crm-text-muted);background:transparent;border:0;border-radius:6px;font-size:8px;font-weight:800;cursor:pointer}.project-type-filter button.active{color:var(--crm-brand-ink);background:var(--crm-teal);box-shadow:0 2px 6px rgba(217,119,6,.18)}.project-workspace-header label{display:grid;min-width:300px;gap:5px;color:var(--crm-text-muted);font-size:8px;font-weight:700}.project-workspace-header select{height:34px;padding:0 30px 0 10px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:8px;font-size:8px}.project-section-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:12px;background:var(--crm-surface)}.project-section{position:relative;min-height:118px;padding:13px;background:#fff;border:1px solid var(--crm-line);border-radius:10px}.project-section>header{display:flex;align-items:center;gap:7px;margin-bottom:7px;color:var(--crm-teal)}.project-section>header strong{flex:1;color:var(--crm-navy);font-size:10px}.project-section>header span{color:var(--crm-text-muted);font-size:8px}.project-section article{display:flex;align-items:center;gap:8px;min-height:46px;padding:7px 0;border-bottom:1px solid var(--crm-line)}.project-section article>div{display:grid;min-width:0;flex:1;gap:4px}.project-section article strong{overflow:hidden;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.project-section article small{overflow:hidden;color:var(--crm-text-muted);font-size:8px;text-overflow:ellipsis;white-space:nowrap}.show-more{display:block;width:100%;padding:8px 0 1px;color:var(--crm-teal);background:transparent;border:0;cursor:pointer;font-size:8px;font-weight:800;text-align:center}.mini-empty{padding:18px;color:var(--crm-text-muted);font-size:9px;text-align:center}@media(max-width:1250px){.profile-kpis{grid-template-columns:repeat(3,1fr)}.profile-grid{grid-template-columns:1fr}.project-section-grid{grid-template-columns:1fr}.project-workspace-header{align-items:flex-start;flex-direction:column}.project-filter-controls{width:100%}.project-workspace-header label{min-width:0;flex:1}}@media(max-width:620px){.profile-hero{grid-template-columns:42px 1fr;padding:18px}.hero-mark{width:42px;height:42px}.hero-actions{grid-column:1/-1}.profile-kpis{grid-template-columns:repeat(2,1fr)}.project-filter-controls{align-items:stretch;flex-direction:column}.project-type-filter{align-self:flex-start}.project-workspace-header label{width:100%}}
.profile-kpis{grid-template-columns:repeat(5,1fr)}
</style>
