<script setup lang="ts">
import { personnelDisplayName } from '@/demo/personnel'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Banknote, BriefcaseBusiness, Plus, Scale } from '@lucide/vue'
import { api as defaultApi, type CrmApi } from '@/api'
import type { PipelineDto, Tone } from '@/types/crm'
import PageHeader from '@/design-system/PageHeader.vue'
import DataState from '@/design-system/DataState.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import FilterBar from '@/features/shared/FilterBar.vue'
import DataNotice from '@/design-system/DataNotice.vue'
import { mapRequestError, readRequestMeta, type RequestMetaState } from '@/api/request-state'
import { formatMoney, weightedMoney } from '@/domain/money'
import { formatDisplayDate } from '@/domain/time'
import { useI18n } from '@/i18n'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const { t, locale } = useI18n()
const data = ref<PipelineDto | null>(null)
const loading = ref(false)
const error = ref('')
const denied = ref(false)
const requestId = ref('')
const meta = ref<RequestMetaState | null>(null)
const stage = ref('All')
const mode = ref<'opportunity' | 'booking'>('opportunity')
let loadSequence = 0
const stageTone = (value: string): Tone => value === 'Won' || value === '采购流程' || value === 'Confirmed' ? 'positive' : value === '预算审批' || value === '报价' ? 'warning' : 'info'
const visibleCount = computed(() => mode.value === 'opportunity' ? data.value?.opportunities.length ?? 0 : data.value?.bookings.length ?? 0)

async function load() {
  const sequence = ++loadSequence
  loading.value = true; error.value = ''; denied.value = false; meta.value = null
  try { const result = await props.apiClient.listPipeline({ status: stage.value }); if (sequence !== loadSequence) return; data.value = result.data; meta.value = readRequestMeta(result) }
  catch (reason) { if (sequence !== loadSequence) return; const mapped = mapRequestError(reason); error.value = mapped.message; requestId.value = mapped.requestId; denied.value = mapped.denied; if (mapped.denied) data.value = null }
  finally { if (sequence === loadSequence) loading.value = false }
}
function reset() { stage.value = 'All' }
watch(stage, load)
onMounted(load)
onBeforeUnmount(() => { loadSequence += 1 })
</script>

<template>
  <div>
    <PageHeader eyebrow="PIPELINE CONTROL" :title="t('pipeline.title')" :description="t('pipeline.description')">
      <button class="primary-button" type="button" disabled :title="locale === 'en-US' ? 'Available after the Frappe write API is connected' : '接入 Frappe 写接口后启用'"><Plus :size="15" />{{ mode === 'opportunity' ? (locale === 'en-US' ? 'New opportunity · API pending' : '新建商机 · 接入后启用') : (locale === 'en-US' ? 'New booking · API pending' : '新建 Booking · 接入后启用') }}</button>
    </PageHeader>
    <section v-if="data" class="pipeline-summary">
      <div><span class="metric-icon navy"><BriefcaseBusiness :size="18" /></span><p><small>Open Pipeline</small><strong v-for="total in data.totals" :key="total.currency">{{ formatMoney(total.openPipeline, total.currency) }}</strong><em>{{ locale === 'en-US' ? 'Excludes Won / Lost opportunities' : '商机口径不包含 Won / Lost' }}</em></p></div>
      <div><span class="metric-icon teal"><Scale :size="18" /></span><p><small>Weighted Pipeline</small><strong v-for="total in data.totals" :key="total.currency">{{ formatMoney(total.weightedPipeline, total.currency) }}</strong><em>{{ locale === 'en-US' ? 'Stage probability × opportunity amount' : '阶段概率 × 商机金额' }}</em></p></div>
      <div><span class="metric-icon lime"><Banknote :size="18" /></span><p><small>Confirmed Booking</small><strong v-for="total in data.totals" :key="total.currency">{{ formatMoney(total.confirmedBooking, total.currency) }}</strong><em>{{ locale === 'en-US' ? 'Confirmed order snapshot, tracked separately' : '确认订单快照，独立统计' }}</em></p></div>
    </section>
    <div class="pipeline-tabs" role="tablist"><button :class="{ active: mode === 'opportunity' }" :aria-selected="mode === 'opportunity'" role="tab" type="button" @click="mode = 'opportunity'">{{ locale === 'en-US' ? 'Opportunity' : 'Opportunity · 商机' }}</button><button :class="{ active: mode === 'booking' }" :aria-selected="mode === 'booking'" role="tab" type="button" @click="mode = 'booking'">{{ locale === 'en-US' ? 'Booking' : 'Booking · 已确认订单' }}</button></div>
    <FilterBar :result-label="locale === 'en-US' ? `${visibleCount} records` : `${visibleCount} 条记录`" @reset="reset">
      <select v-if="mode === 'opportunity'" v-model="stage" class="filter-control" :aria-label="locale === 'en-US' ? 'Opportunity stage' : '商机阶段'"><option value="All">{{ locale === 'en-US' ? 'All stages' : '全部阶段' }}</option><option>需求发现</option><option>Wafer Demo确认</option><option>预算审批</option><option>设备规格确认</option><option>报价</option><option>采购流程</option><option>Won</option></select>
    </FilterBar>
    <DataNotice v-if="meta?.stale" :message="meta.message" :request-id="meta.requestId" @refresh="load" />
    <section class="table-panel">
      <DataState v-if="loading && !data" type="loading" />
      <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
      <DataState v-else-if="error" type="error" :message="error" :request-id="requestId" @retry="load" />
      <template v-else-if="data">
        <DataState v-if="mode === 'opportunity' && !data.opportunities.length" type="empty" :title="locale === 'en-US' ? 'No matching opportunities' : '没有匹配的商机'" :message="locale === 'en-US' ? 'Adjust filters and try again.' : '调整筛选条件，或清除搜索关键词后重试。'" />
        <DataState v-else-if="mode === 'booking' && !data.bookings.length" type="empty" :title="locale === 'en-US' ? 'No matching Confirmed Bookings' : '没有匹配的 Confirmed Booking'" :message="locale === 'en-US' ? 'Adjust filters and try again.' : '调整筛选条件，或清除搜索关键词后重试。'" />
        <div v-else-if="mode === 'opportunity'" class="table-scroll"><table class="crm-table pipeline-table is-responsive"><thead><tr><th>{{ locale === 'en-US' ? 'Opportunity / account' : '商机 / 客户' }}</th><th>{{ locale === 'en-US' ? 'Amount' : '金额' }}</th><th>{{ locale === 'en-US' ? 'Sales stage' : '销售阶段' }}</th><th>{{ locale === 'en-US' ? 'Probability' : '概率' }}</th><th>{{ locale === 'en-US' ? 'Intent score' : '意愿评分' }}</th><th>{{ locale === 'en-US' ? 'Budget' : '预算' }}</th><th>Next Action / Due</th></tr></thead><tbody><tr v-for="item in data.opportunities" :key="item.id"><td :data-label="locale === 'en-US' ? 'Opportunity / account' : '商机 / 客户'"><strong>{{ item.title }}</strong><small>{{ item.accountName }} · {{ item.id }}</small></td><td :data-label="locale === 'en-US' ? 'Amount' : '金额'"><b class="money">{{ formatMoney(item.amount, item.currency) }}</b><small>{{ locale === 'en-US' ? 'Weighted' : '加权' }} {{ formatMoney(weightedMoney(item.amount, item.probability), item.currency) }}</small></td><td :data-label="locale === 'en-US' ? 'Sales stage' : '销售阶段'"><StatusBadge :label="item.stage" :tone="stageTone(item.stage)" /></td><td :data-label="locale === 'en-US' ? 'Probability' : '概率'"><strong class="probability">{{ item.probability }}%</strong></td><td :data-label="locale === 'en-US' ? 'Intent score' : '意愿评分'"><strong class="score">{{ item.intentScore }}</strong></td><td :data-label="locale === 'en-US' ? 'Budget' : '预算'"><StatusBadge :label="item.budgetStatus" :tone="item.budgetStatus === 'Confirmed' ? 'positive' : 'warning'" /></td><td data-label="Next Action"><strong>{{ item.nextAction }}</strong><small>{{ personnelDisplayName(item.owner) }} · {{ formatDisplayDate(item.due) }}</small></td></tr></tbody></table></div>
        <div v-else class="table-scroll"><table class="crm-table pipeline-table is-responsive"><thead><tr><th>{{ locale === 'en-US' ? 'Booking / account' : 'Booking / 客户' }}</th><th>{{ locale === 'en-US' ? 'Amount' : '金额' }}</th><th>{{ locale === 'en-US' ? 'Order status' : '订单状态' }}</th><th>{{ locale === 'en-US' ? 'Booking date' : 'Booking 日期' }}</th><th>{{ locale === 'en-US' ? 'Owner' : '负责人' }}</th><th>{{ locale === 'en-US' ? 'Source opportunity' : '来源商机' }}</th></tr></thead><tbody><tr v-for="item in data.bookings" :key="item.id"><td :data-label="locale === 'en-US' ? 'Booking / account' : 'Booking / 客户'"><strong>{{ item.title }}</strong><small>{{ item.accountName }} · {{ item.id }}</small></td><td :data-label="locale === 'en-US' ? 'Amount' : '金额'"><b class="money">{{ formatMoney(item.amount, item.currency) }}</b></td><td :data-label="locale === 'en-US' ? 'Order status' : '订单状态'"><StatusBadge :label="item.status" :tone="stageTone(item.status)" /></td><td :data-label="locale === 'en-US' ? 'Booking date' : 'Booking 日期'"><span>{{ formatDisplayDate(item.bookingDate) }}</span></td><td :data-label="locale === 'en-US' ? 'Owner' : '负责人'"><span>{{ personnelDisplayName(item.owner) }}</span></td><td :data-label="locale === 'en-US' ? 'Source opportunity' : '来源商机'"><StatusBadge :label="item.sourceOpportunityId || (locale === 'en-US' ? 'Non-opportunity source' : '非商机来源')" tone="info" /></td></tr></tbody></table></div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.pipeline-summary { display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; margin-bottom: 16px; }
.pipeline-summary > div { display: flex; align-items: center; gap: 13px; padding: 15px; background: #fff; border: 1px solid var(--crm-line); border-radius: 12px; }
.metric-icon { display: grid; width: 38px; height: 38px; place-items: center; border-radius: 11px; }.metric-icon.navy{color:var(--crm-navy);background:#e7eff1}.metric-icon.teal{color:var(--crm-teal);background:var(--crm-teal-soft)}.metric-icon.lime{color:#778c25;background:#eff4d7}
.pipeline-summary p { display: grid; margin: 0; gap: 2px; }.pipeline-summary small{color:var(--crm-text-muted);font-size:8px}.pipeline-summary strong{color:var(--crm-navy);font-size:20px;font-variant-numeric:tabular-nums}.pipeline-summary em{color:#95a3a5;font-size:8px;font-style:normal}
.pipeline-tabs { display: flex; gap: 4px; margin-bottom: 10px; padding: 4px; width: fit-content; background: #EEEAE4; border-radius: 10px; }.pipeline-tabs button{padding:8px 13px;color:var(--crm-text-muted);background:transparent;border:0;border-radius:7px;font-size:10px;font-weight:700;cursor:pointer}.pipeline-tabs button.active{color:var(--crm-navy);background:#fff;box-shadow:0 1px 4px rgba(31,35,41,.08)}
.search-control{display:flex;min-width:230px;height:34px;align-items:center;gap:7px;padding:0 10px;color:var(--crm-text-muted);background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:8px}.search-control input{min-width:0;flex:1;background:transparent;border:0;outline:0;font-size:10px}
.table-panel{overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:13px}.table-scroll{overflow:auto}.pipeline-table{min-width:1050px}td strong{display:block;color:var(--crm-text);font-size:10px}td small{display:block;margin-top:5px;color:var(--crm-text-muted);font-size:8px}.money{color:var(--crm-navy);font-size:12px;font-variant-numeric:tabular-nums}.probability,.score{color:var(--crm-teal);font-size:13px;font-variant-numeric:tabular-nums}
@media(max-width:780px){.pipeline-summary{grid-template-columns:1fr}.pipeline-tabs{width:100%}.pipeline-tabs button{flex:1}}
</style>
