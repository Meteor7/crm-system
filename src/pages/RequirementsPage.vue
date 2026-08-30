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

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const rows = ref<RequirementDto[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(12)
const loading = ref(false)
const error = ref('')
const denied = ref(false)
const requestId = ref('')
const meta = ref<RequestMetaState | null>(null)
const status = ref('All')
let loadSequence = 0
const money = (value: number) => `¥${(value / 10000).toFixed(0)}万`
const statusTone = (value: RequirementDto['status']): Tone => value === '已确认' ? 'positive' : value === '预算审批' || value === '采购计划' ? 'warning' : 'info'

async function load() {
  const sequence = ++loadSequence
  loading.value = true; error.value = ''; meta.value = null
  denied.value = false
  try { const result = await props.apiClient.listRequirements({ status: status.value, page: page.value, pageSize: pageSize.value }); if (sequence !== loadSequence) return; rows.value = result.data.items; total.value = result.meta?.total ?? rows.value.length; meta.value = readRequestMeta(result) }
  catch (reason) { if (sequence !== loadSequence) return; const mapped = mapRequestError(reason); error.value = mapped.message; requestId.value = mapped.requestId; denied.value = mapped.denied; if (mapped.denied) { rows.value = []; total.value = 0 } }
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
    <PageHeader eyebrow="PROCUREMENT SIGNALS" title="采购需求" description="把预算、设备/应用、完整度、负责人和下一步行动放在同一条记录中，避免不完整需求过早进入商机。">
      <button class="primary-button" type="button" disabled title="接入 Frappe 写接口后启用"><Plus :size="15" />新增需求 · 接入后启用</button>
    </PageHeader>
    <section v-if="!denied" class="requirement-summary">
      <div><Wrench :size="18" /><span><small>有效需求</small><strong>{{ total }}</strong></span></div>
      <div><CircleDollarSign :size="18" /><span><small>预算金额</small><strong>{{ money(rows.reduce((sum,item) => sum + item.budgetAmount, 0)) }}</strong></span></div>
      <div><FileCheck2 :size="18" /><span><small>完整需求</small><strong>{{ rows.filter(item => item.completeness >= 80).length }}</strong></span></div>
    </section>
    <FilterBar :result-label="`${total} 条需求`" @reset="reset">
      <select v-model="status" class="filter-control" aria-label="需求状态"><option value="All">全部状态</option><option>需求识别</option><option>技术确认</option><option>Demo验证</option><option>预算审批</option><option>采购计划</option><option>已确认</option></select>
    </FilterBar>
    <DataNotice v-if="meta?.stale" :message="meta.message" :request-id="meta.requestId" @refresh="load" />
    <section class="table-panel">
      <DataState v-if="loading && !rows.length" type="loading" />
      <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
      <DataState v-else-if="error" type="error" :message="error" :request-id="requestId" @retry="load" />
      <DataState v-else-if="!rows.length" type="empty" />
      <div v-else class="table-scroll"><table class="crm-table requirement-table is-responsive"><thead><tr><th>客户 / 需求</th><th>设备 / 应用</th><th>数量 / 预算</th><th>状态 / 完整度</th><th>Owner / Next Action</th><th>关联业务</th></tr></thead><tbody>
        <tr v-for="item in rows" :key="item.id"><td data-label="客户 / 需求"><strong>{{ item.accountName }}</strong><small>{{ item.id }} · {{ item.title }}</small></td><td data-label="设备 / 应用"><strong>{{ item.equipment }}</strong><small>{{ item.application }} · {{ item.site }}</small></td><td data-label="数量 / 预算"><b class="money">{{ money(item.budgetAmount) }}</b><small>{{ item.quantity }} 台 · {{ item.budgetStatus }}</small></td><td data-label="状态 / 完整度"><StatusBadge :label="item.status" :tone="statusTone(item.status)" /><div class="completeness"><i><em :style="{ width: `${item.completeness}%` }" /></i><span>{{ item.completeness }}%</span></div></td><td data-label="Next Action"><strong>{{ item.nextAction }}</strong><small>{{ personnelDisplayName(item.owner) }} · {{ formatDisplayDate(item.due) }}</small></td><td data-label="关联业务"><StatusBadge v-if="item.linkedDealId" :label="item.linkedDealId" tone="info" /><StatusBadge v-if="item.linkedEvaluationId" :label="item.linkedEvaluationId" tone="warning" /><small v-if="!item.linkedDealId && !item.linkedEvaluationId">尚未转业务</small></td></tr>
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
