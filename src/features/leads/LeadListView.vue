<script setup lang="ts">
import { personnelDisplayName } from '@/demo/personnel'
import { computed, onMounted, ref, watch } from 'vue'
import { Edit3, Plus, UserRoundSearch } from '@lucide/vue'
import { useRouter } from 'vue-router'
import { api as defaultApi, type CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import type { CreateLeadInput, LeadDto, LeadSource, LeadStatus, Tone } from '@/types/crm'
import DataState from '@/design-system/DataState.vue'
import FilterBar from '@/features/shared/FilterBar.vue'
import PaginationControls from '@/features/shared/PaginationControls.vue'
import { ownerFilterOptions } from '@/features/shared/owner-filter'
import StatusBadge from '@/design-system/StatusBadge.vue'
import LeadEditorModal from './LeadEditorModal.vue'
import { formatDisplayDate } from '@/domain/time'
import { useI18n, useLocaleMessage } from '@/i18n'
import { salesEnumLabel } from '@/features/shared/sales-i18n'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const router = useRouter()
const app = useAppStore()
const { t, locale } = useI18n()
const rows = ref<LeadDto[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(12)
const loading = ref(false)
const denied = ref(false)
const error = useLocaleMessage()
const requestId = ref('')
const status = ref<LeadStatus | 'All'>('All')
const source = ref<LeadSource | 'All'>('All')
const owner = ref('All')
const editorOpen = ref(false)
const editing = ref<LeadDto | null>(null)
const busy = ref(false)
const editorError = useLocaleMessage()
const canWrite = computed(() => app.can('deal:write'))
const owners = computed(() => ownerFilterOptions(app.bootstrap?.user, rows.value.map((lead) => lead.owner), owner.value))
let sequence = 0

function statusTone(value: LeadStatus): Tone {
  if (value === 'Qualified' || value === 'Converted') return 'positive'
  if (value === 'Working' || value === 'Nurturing') return 'info'
  if (value === 'Disqualified') return 'danger'
  return 'neutral'
}
async function load() {
  const current = ++sequence
  loading.value = true
  error.value = ''
  denied.value = false
  try {
    const result = await props.apiClient.listLeads({ status: status.value, source: source.value, owner: owner.value, page: page.value, pageSize: pageSize.value })
    if (current !== sequence) return
    rows.value = result.data.items
    total.value = result.meta?.total ?? rows.value.length
  } catch (reason) {
    if (current !== sequence) return
    const mapped = mapRequestError(reason)
    rows.value = []
    total.value = 0
    error.value = mapped.localizedMessage ?? mapped.message
    requestId.value = mapped.requestId
    denied.value = mapped.denied
  } finally {
    if (current === sequence) loading.value = false
  }
}
function resetFilters() {
  page.value = 1
  status.value = 'All'
  source.value = 'All'
  owner.value = 'All'
}
function changeFilters() { page.value = 1; void load() }
function goPage(target: number) { page.value = target; void load() }
function changePageSize(value: number) { pageSize.value = value; page.value = 1; void load() }
function openCreate() {
  editing.value = null
  editorError.value = ''
  editorOpen.value = true
}
function openEdit(lead: LeadDto) {
  editing.value = lead
  editorError.value = ''
  editorOpen.value = true
}
async function saveLead(payload: CreateLeadInput) {
  busy.value = true
  editorError.value = ''
  try {
    if (editing.value) await props.apiClient.updateLead(editing.value.id, payload, editing.value.modified)
    else {
      await props.apiClient.createLead(payload)
      resetFilters()
    }
    editorOpen.value = false
    editing.value = null
    await load()
  } catch (reason) {
    const mapped = mapRequestError(reason); editorError.value = mapped.localizedMessage ?? mapped.message
  } finally {
    busy.value = false
  }
}
function openDetail(lead: LeadDto) {
  void router.push({ name: 'lead-detail', params: { leadId: lead.id } })
}

watch([status, source, owner], changeFilters)
onMounted(async () => {
  await app.loadBootstrap(props.apiClient)
  await load()
})
</script>

<template>
  <div class="lead-list-view">
    <div class="lead-actions">
      <div><span>{{ t('leads.qualificationEyebrow') }}</span><strong>{{ t('leads.qualificationTitle') }}</strong><small>{{ t('leads.qualificationDescription') }}</small></div>
      <button v-if="canWrite" class="primary-button" type="button" data-testid="new-lead" @click="openCreate"><Plus :size="14" />{{ t('leads.new') }}</button>
    </div>
     <FilterBar :result-label="locale === 'en-US' ? `${total} Leads` : `${total} 条 Leads`" @reset="resetFilters">
       <select v-model="status" class="filter-control" :aria-label="t('leads.status')"><option value="All">{{ t('leads.allStatuses') }}</option><option v-for="item in ['New', 'Working', 'Qualified', 'Nurturing', 'Disqualified', 'Converted']" :key="item" :value="item">{{ salesEnumLabel(item, locale) }}</option></select>
       <select v-model="source" class="filter-control" :aria-label="t('leads.source')"><option value="All">{{ t('leads.allSources') }}</option><option v-for="item in ['Website', 'Trade Show', 'Partner Referral', 'Outbound', 'Customer Referral', 'Other']" :key="item" :value="item">{{ salesEnumLabel(item, locale) }}</option></select>
      <select v-model="owner" class="filter-control" :aria-label="t('leads.owner')"><option value="All">{{ t('leads.allOwners') }}</option><option v-for="item in owners" :key="item" :value="item">{{ personnelDisplayName(item) }}</option></select>
    </FilterBar>

    <section class="lead-table-card">
      <DataState v-if="loading && !rows.length" type="loading" />
      <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
      <DataState v-else-if="error" type="error" :message="error" :request-id="requestId" @retry="load" />
      <DataState v-else-if="!rows.length" type="empty" :title="t('leads.emptyTitle')" :message="t('leads.emptyMessage')" />
      <div v-else class="table-scroll">
        <table class="crm-table lead-table">
          <thead><tr><th>{{ t('leads.name') }}</th><th>{{ t('leads.companyTitle') }}</th><th>{{ t('leads.contact') }}</th><th>{{ t('leads.source') }}</th><th>{{ t('leads.status') }}</th><th>{{ t('leads.owner') }}</th><th>{{ t('leads.nextStep') }}</th><th>{{ t('leads.updated') }}</th><th v-if="canWrite">{{ t('leads.actions') }}</th></tr></thead>
          <tbody>
            <tr v-for="lead in rows" :key="lead.id">
              <td><button class="lead-link record-name-link" type="button" :data-lead-id="lead.id" @click="openDetail(lead)"><span><UserRoundSearch :size="14" /></span><strong>{{ lead.name }}</strong></button></td>
              <td><strong>{{ lead.company }}</strong><small>{{ lead.title }}</small></td>
              <td><strong>{{ lead.phone || '—' }}</strong><small>{{ lead.email || '—' }}</small></td>
               <td>{{ salesEnumLabel(lead.source, locale) }}</td>
               <td><StatusBadge :label="salesEnumLabel(lead.status, locale)" :tone="statusTone(lead.status)" /></td>
              <td>{{ personnelDisplayName(lead.owner) }}</td>
              <td><strong>{{ lead.nextAction || '—' }}</strong><small>{{ lead.nextActionDue || t('leads.noDate') }}</small></td>
              <td>{{ formatDisplayDate(lead.updatedAt) }}</td>
              <td v-if="canWrite"><button v-if="lead.status !== 'Converted'" class="edit-button" type="button" data-testid="edit-lead" @click="openEdit(lead)"><Edit3 :size="13" />{{ t('leads.edit') }}</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <PaginationControls v-if="!denied && !error && total > pageSize" :page="page" :page-size="pageSize" :total="total" @change="goPage" @page-size-change="changePageSize" />
    </section>
    <LeadEditorModal v-if="editorOpen" :lead="editing" :busy="busy" :error="editorError" @close="editorOpen = false" @submit="saveLead" />
  </div>
</template>

<style scoped>
.lead-list-view{display:grid;gap:12px}.lead-actions{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;padding:14px 16px;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.lead-actions>div{display:grid;gap:3px}.lead-actions span{color:var(--crm-teal);font-size:8px;font-weight:800;letter-spacing:.12em}.lead-actions strong{color:var(--crm-navy);font-size:15px}.lead-actions small{color:var(--crm-text-muted);font-size:10px}.lead-actions button{display:flex;align-items:center;gap:6px}.lead-table-card{overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.lead-link{display:inline-flex;align-items:center;gap:7px;padding:0;color:var(--crm-teal);background:transparent;border:0;cursor:pointer}.lead-link span{display:grid;width:27px;height:27px;place-items:center;color:var(--crm-brand-ink);background:var(--crm-teal-soft);border-radius:8px}.lead-table td>strong,.lead-table td>small{display:block}.lead-table td>small{margin-top:3px;color:var(--crm-text-muted);font-size:9px}.edit-button{display:inline-flex;align-items:center;gap:4px;padding:6px 8px;color:var(--crm-navy);background:#fff;border:1px solid var(--crm-line);border-radius:7px;cursor:pointer}@media(max-width:700px){.lead-actions{align-items:stretch;flex-direction:column}.lead-actions button{justify-content:center}}
</style>
