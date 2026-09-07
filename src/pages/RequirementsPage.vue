<script setup lang="ts">
import { personnelDisplayName } from '@/demo/personnel'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { CircleDollarSign, FileCheck2, Plus, Wrench } from '@lucide/vue'
import { api as defaultApi, type CrmApi } from '@/api'
import type { RequirementDto, Tone } from '@/types/crm'
import PageHeader from '@/design-system/PageHeader.vue'
import DataState from '@/design-system/DataState.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import FilterBar from '@/features/shared/FilterBar.vue'
import DataNotice from '@/design-system/DataNotice.vue'
import PaginationControls from '@/features/shared/PaginationControls.vue'
import { mapRequestError, readRequestMeta, type RequestMetaState } from '@/api/request-state'
import { formatDisplayDate } from '@/domain/time'
import { localeMessage, useI18n, useLocaleMessage } from '@/i18n'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const { t, locale } = useI18n()
const ui = (english: string, chinese: string) => localeMessage(english, chinese)[locale.value]
const rows = ref<RequirementDto[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(12)
const loading = ref(false)
const error = useLocaleMessage()
const denied = ref(false)
const requestId = ref('')
const meta = ref<RequestMetaState | null>(null)
const status = ref('All')
let loadSequence = 0
const money = (value: number) => locale.value === 'en-US' ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'CNY', notation: 'compact' }).format(value) : `¥${(value / 10000).toFixed(0)}万`
const statusKeys: Record<RequirementDto['status'], string> = { '需求识别': 'discovery', '技术确认': 'technical', 'Demo验证': 'demo', '预算审批': 'budget', '采购计划': 'procurement', '已确认': 'confirmed' }
const statusLabel = (value: RequirementDto['status']) => t(`requirements.status.${statusKeys[value]}`)
const budgetStatusLabel = (value: RequirementDto['budgetStatus']) => ({ Confirmed: ui('Confirmed', '已确认'), 'In Review': ui('In review', '审核中'), Unknown: ui('Unknown', '未知') }[value])
const statusTone = (value: RequirementDto['status']): Tone => value === '已确认' ? 'positive' : value === '预算审批' || value === '采购计划' ? 'warning' : 'info'

async function load() {
  const sequence = ++loadSequence
  loading.value = true; error.value = ''; meta.value = null
  denied.value = false
  try { const result = await props.apiClient.listRequirements({ status: status.value, page: page.value, pageSize: pageSize.value }); if (sequence !== loadSequence) return; rows.value = result.data.items; total.value = result.meta?.total ?? rows.value.length; meta.value = readRequestMeta(result) }
  catch (reason) { if (sequence !== loadSequence) return; const mapped = mapRequestError(reason); error.value = mapped.localizedMessage ?? mapped.message; requestId.value = mapped.requestId; denied.value = mapped.denied; if (mapped.denied) { rows.value = []; total.value = 0 } }
  finally { if (sequence === loadSequence) loading.value = false }
}
function reset() { page.value = 1; status.value = 'All' }
function changeStatus() { page.value = 1; void load() }
function goPage(target: number) { page.value = target; void load() }
function changePageSize(value: number) { pageSize.value = value; page.value = 1; void load() }
watch(status, changeStatus)
onMounted(load)
onBeforeUnmount(() => { loadSequence += 1 })
</script>

<template>
  <div>
    <PageHeader :eyebrow="ui('PROCUREMENT SIGNALS', '采购需求')" :title="t('requirements.title')" :description="t('requirements.description')">
      <button class="primary-button" type="button" disabled :title="t('requirements.apiPending')"><Plus :size="15" />{{ t('requirements.newPending') }}</button>
    </PageHeader>
    <section v-if="!denied" class="requirement-summary">
      <div><Wrench :size="18" /><span><small>{{ t('requirements.valid') }}</small><strong>{{ total }}</strong></span></div>
      <div><CircleDollarSign :size="18" /><span><small>{{ t('requirements.budget') }}</small><strong>{{ money(rows.reduce((sum,item) => sum + item.budgetAmount, 0)) }}</strong></span></div>
      <div><FileCheck2 :size="18" /><span><small>{{ t('requirements.complete') }}</small><strong>{{ rows.filter(item => item.completeness >= 80).length }}</strong></span></div>
    </section>
    <FilterBar :result-label="t('requirements.result', { count: total })" @reset="reset">
      <select v-model="status" class="filter-control" :aria-label="t('requirements.status')"><option value="All">{{ t('requirements.allStatuses') }}</option><option v-for="(_, value) in statusKeys" :key="value" :value="value">{{ statusLabel(value) }}</option></select>
    </FilterBar>
    <DataNotice v-if="meta?.stale" :message="meta.localizedMessage ?? meta.message" :request-id="meta.requestId" @refresh="load" />
    <section class="table-panel">
      <DataState v-if="loading && !rows.length" type="loading" />
      <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
      <DataState v-else-if="error" type="error" :message="error" :request-id="requestId" @retry="load" />
      <DataState v-else-if="!rows.length" type="empty" :title="t('requirements.emptyTitle')" :message="t('requirements.emptyMessage')" />
       <div v-else class="table-scroll"><table class="crm-table requirement-table is-responsive"><thead><tr><th>{{ t('requirements.accountNeed') }}</th><th>{{ t('requirements.equipmentApplication') }}</th><th>{{ t('requirements.quantityBudget') }}</th><th>{{ t('requirements.statusCompleteness') }}</th><th>{{ ui('Owner / Next Action', '负责人 / 下一步行动') }}</th><th>{{ t('requirements.relatedBusiness') }}</th></tr></thead><tbody>
         <tr v-for="item in rows" :key="item.id"><td :data-label="t('requirements.accountNeed')"><strong>{{ item.accountName }}</strong><small>{{ item.id }} · {{ item.title }}</small></td><td :data-label="t('requirements.equipmentApplication')"><strong>{{ item.equipment }}</strong><small>{{ item.application }} · {{ item.site }}</small></td><td :data-label="t('requirements.quantityBudget')"><b class="money">{{ money(item.budgetAmount) }}</b><small>{{ item.quantity }} {{ ui('units', '台') }} · {{ budgetStatusLabel(item.budgetStatus) }}</small></td><td :data-label="t('requirements.statusCompleteness')"><StatusBadge :label="statusLabel(item.status)" :tone="statusTone(item.status)" /><div class="completeness"><i><em :style="{ width: `${item.completeness}%` }" /></i><span>{{ item.completeness }}%</span></div></td><td :data-label="ui('Next Action', '下一步行动')"><strong>{{ item.nextAction }}</strong><small>{{ personnelDisplayName(item.owner) }} · {{ formatDisplayDate(item.due) }}</small></td><td :data-label="t('requirements.relatedBusiness')"><StatusBadge v-if="item.linkedDealId" :label="item.linkedDealId" tone="info" /><StatusBadge v-if="item.linkedEvaluationId" :label="item.linkedEvaluationId" tone="warning" /><small v-if="!item.linkedDealId && !item.linkedEvaluationId">{{ t('requirements.notConverted') }}</small></td></tr>
      </tbody></table></div>
      <PaginationControls v-if="!denied && !error && total > pageSize" :page="page" :page-size="pageSize" :total="total" @change="goPage" @page-size-change="changePageSize" />
    </section>
  </div>
</template>

<style scoped>
.requirement-summary { display: flex; gap: 10px; margin-bottom: 14px; }
.requirement-summary > div { display: flex; min-width: 190px; align-items: center; gap: 11px; padding: 13px 15px; color: var(--crm-teal); background: #fff; border: 1px solid var(--crm-line); border-radius: 11px; }
.requirement-summary span { display: grid; gap: 2px; }
.requirement-summary small { color: var(--crm-text-muted); font-size: 8px; }
.requirement-summary strong { color: var(--crm-navy); font-size: 17px; font-variant-numeric: tabular-nums; }
.search-control { display: flex; min-width: 230px; height: 34px; align-items: center; gap: 7px; padding: 0 10px; color: var(--crm-text-muted); background: var(--crm-surface); border: 1px solid var(--crm-line); border-radius: 8px; }
.search-control input { min-width: 0; flex: 1; background: transparent; border: 0; outline: 0; font-size: 10px; }
.table-panel { overflow: hidden; background: #fff; border: 1px solid var(--crm-line); border-radius: 13px; }
.table-scroll { overflow: auto; }
.requirement-table { min-width: 1050px; }
td strong { display: block; color: var(--crm-text); font-size: 10px; }
td small { display: block; margin-top: 5px; color: var(--crm-text-muted); font-size: 8px; }
.money { color: var(--crm-navy); font-size: 12px; font-variant-numeric: tabular-nums; }
.completeness { display: flex; align-items: center; gap: 6px; margin-top: 7px; }
.completeness i { width: 54px; height: 4px; overflow: hidden; background: var(--crm-surface-muted); border-radius: 9px; }
.completeness em { display: block; height: 100%; background: var(--crm-teal); }
.completeness span { color: var(--crm-text-muted); font-size: 8px; }
@media (max-width: 700px) { .requirement-summary { overflow-x: auto; padding-bottom: 5px; } }
</style>
