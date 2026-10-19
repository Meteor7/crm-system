<script setup lang="ts">
import { personnelDisplayName } from '@/demo/personnel'
import { computed, onMounted, ref, watch } from 'vue'
import { FileCheck2, ShieldAlert } from '@lucide/vue'
import { api as defaultApi, type CrmApi } from '@/api'
import type { ContractDto, Tone } from '@/types/crm'
import { getContractRisk } from '@/domain/contracts'
import { mapRequestError, readRequestMeta, type RequestMetaState } from '@/api/request-state'
import PageHeader from '@/design-system/PageHeader.vue'
import DataState from '@/design-system/DataState.vue'
import DataNotice from '@/design-system/DataNotice.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import FilterBar from '@/features/shared/FilterBar.vue'
import PaginationControls from '@/features/shared/PaginationControls.vue'
import { localeMessage, useI18n, useLocaleMessage } from '@/i18n'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const { t, locale } = useI18n()
const ui = (english: string, chinese: string) => localeMessage(english, chinese)[locale.value]
const rows = ref<ContractDto[]>([]), loading = ref(false), denied = ref(false), error = useLocaleMessage(), requestId = ref(''), meta = ref<RequestMetaState | null>(null), status = ref('All'), type = ref('All')
const total = ref(0), page = ref(1)
const pageSize = ref(10)
const money = (value: number) => locale.value === 'en-US' ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'CNY', notation: 'compact' }).format(value) : `¥${(value / 10000).toFixed(value < 100000 ? 1 : 0)}万`
const risks = computed(() => rows.value.map((contract) => ({ contract, risk: getContractRisk(contract.end) })))
const expiring = computed(() => risks.value.filter(({ risk }) => risk.band !== 'normal').length)
const riskTone = (band: ReturnType<typeof getContractRisk>['band']): Tone => band === 'expired' || band === '30d' ? 'danger' : band === '60d' || band === '90d' ? 'warning' : 'positive'
const contractStatusLabel = (value: ContractDto['status']) => ({ Draft: ui('Draft', '草稿'), Unsigned: ui('Unsigned', '未签署'), Active: ui('Active', '生效中'), Expired: ui('Expired', '已过期'), Terminated: ui('Terminated', '已终止') }[value])
const contractTypeLabel = (value: ContractDto['type']) => ({ NDA: 'NDA', 'Evaluation Agreement': ui('Evaluation Agreement', '评估协议'), 'Service Contract': ui('Service Contract', '服务演示员工116'), 'Sales Contract': ui('Sales Contract', '销售演示员工116') }[value])
const riskLabel = (risk: ReturnType<typeof getContractRisk>) => risk.band === 'expired' ? ui('Expired', '已到期') : risk.days === 0 ? ui('Due today', '今天到期') : risk.band === 'normal' ? ui('Normal', '演示员工152') : ui(`${risk.days} days`, `${risk.days} 天内`)
let sequence = 0
async function load() { const current = ++sequence; loading.value = true; error.value = ''; denied.value = false; meta.value = null; try { const result = await props.apiClient.listContracts({ status: status.value, type: type.value, page: page.value, pageSize: pageSize.value }); if (current !== sequence) return; rows.value = result.data.items; total.value = result.meta?.total ?? rows.value.length; meta.value = readRequestMeta(result) } catch (reason) { if (current !== sequence) return; const mapped = mapRequestError(reason); error.value = mapped.localizedMessage ?? mapped.message; requestId.value = mapped.requestId; denied.value = mapped.denied; if (mapped.denied) rows.value = [] } finally { if (current === sequence) loading.value = false } }
function reset() { page.value = 1; status.value = type.value = 'All' }
function changeFilters() { page.value = 1; void load() }
function goPage(target: number) { page.value = target; void load() }
function changePageSize(value: number) { pageSize.value = value; page.value = 1; void load() }
watch([status, type], changeFilters)
onMounted(load)
</script>

<template>
  <div><PageHeader :eyebrow="ui('CONTRACT CONTROL', '演示员工116管控')" :title="t('contracts.title')" :description="t('contracts.description')"><span class="header-note"><ShieldAlert :size="15" />{{ t('contracts.backendNote') }}</span></PageHeader>
    <section v-if="!denied" class="contract-summary"><div><FileCheck2 :size="17" /><span><small>{{ t('contracts.total') }}</small><strong>{{ rows.length }}</strong></span></div><div><span><small>{{ t('contracts.unsigned') }}</small><strong>{{ rows.filter((item) => !item.signed).length }}</strong></span></div><div><span><small>{{ t('contracts.expiring') }}</small><strong>{{ expiring }}</strong></span></div><div><span><small>{{ t('contracts.amount') }}</small><strong>{{ money(rows.reduce((sum,item) => sum + item.amount, 0)) }}</strong></span></div></section>
    <FilterBar :result-label="t('contracts.result', { count: rows.length })" @reset="reset"><select v-model="status" class="filter-control" :aria-label="t('contracts.status')"><option value="All">{{ t('contracts.allStatuses') }}</option><option value="Draft">{{ contractStatusLabel('Draft') }}</option><option value="Unsigned">{{ contractStatusLabel('Unsigned') }}</option><option value="Active">{{ contractStatusLabel('Active') }}</option><option value="Expired">{{ contractStatusLabel('Expired') }}</option><option value="Terminated">{{ contractStatusLabel('Terminated') }}</option></select><select v-model="type" class="filter-control" :aria-label="t('contracts.type')"><option value="All">{{ t('contracts.allTypes') }}</option><option value="NDA">{{ contractTypeLabel('NDA') }}</option><option value="Evaluation Agreement">{{ contractTypeLabel('Evaluation Agreement') }}</option><option value="Service Contract">{{ contractTypeLabel('Service Contract') }}</option><option value="Sales Contract">{{ contractTypeLabel('Sales Contract') }}</option></select></FilterBar>
    <DataNotice v-if="meta?.stale" :message="meta.localizedMessage ?? meta.message" :request-id="meta.requestId" @refresh="load" /><section class="table-panel"><DataState v-if="loading && !rows.length" type="loading" /><DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" /><DataState v-else-if="error" type="error" :message="error" :request-id="requestId" @retry="load" /><DataState v-else-if="!rows.length" type="empty" :title="t('contracts.emptyTitle')" :message="t('contracts.emptyMessage')" /><div v-else class="table-scroll"><table class="crm-table contract-table is-responsive"><thead><tr><th>{{ t('contracts.contract') }}</th><th>{{ t('detail.account') }}</th><th>{{ t('contracts.type') }}</th><th>{{ t('detail.status') }}</th><th>{{ t('contracts.amount') }}</th><th>{{ t('contracts.start') }}</th><th>{{ t('contracts.end') }}</th><th>{{ t('contracts.expiryRisk') }}</th></tr></thead><tbody><tr v-for="item in risks" :key="item.contract.id"><td :data-label="t('contracts.contract')"><strong>{{ item.contract.id }}</strong><small>{{ ui('Owner', '负责人') }} {{ personnelDisplayName(item.contract.owner) }}</small></td><td :data-label="t('detail.account')"><strong>{{ item.contract.accountName }}</strong><small>{{ item.contract.segment }}</small></td><td :data-label="t('contracts.type')">{{ contractTypeLabel(item.contract.type) }}</td><td :data-label="t('detail.status')"><StatusBadge :label="contractStatusLabel(item.contract.status)" :tone="item.contract.signed ? 'positive' : 'warning'" /></td><td :data-label="t('contracts.amount')"><b class="money">{{ money(item.contract.amount) }}</b></td><td :data-label="t('contracts.start')"><span>{{ item.contract.start }}</span></td><td :data-label="t('contracts.end')"><span>{{ item.contract.end }}</span></td><td :data-label="t('contracts.expiryRisk')"><StatusBadge :label="riskLabel(item.risk)" :tone="riskTone(item.risk.band)" /></td></tr></tbody></table></div><PaginationControls v-if="!denied && !error && total > pageSize" :page="page" :page-size="pageSize" :total="total" @change="goPage" @page-size-change="changePageSize" /></section>
  </div>
</template>

<style scoped>
.header-note{display:flex;align-items:center;gap:6px;padding:9px 11px;color:var(--crm-text-muted);background:#fff;border:1px solid var(--crm-line);border-radius:9px;font-size:8px}.contract-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}.contract-summary>div{display:flex;align-items:center;gap:10px;padding:14px 16px;color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line);border-radius:11px}.contract-summary span{display:grid;gap:3px}.contract-summary small{color:var(--crm-text-muted);font-size:8px}.contract-summary strong{color:var(--crm-navy);font-size:19px}.search-control{display:flex;min-width:220px;height:34px;align-items:center;gap:7px;padding:0 10px;color:var(--crm-text-muted);background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:8px}.search-control input{min-width:0;flex:1;background:transparent;border:0;outline:0;font-size:10px}.table-panel{overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:13px}.table-scroll{overflow:auto}.contract-table{min-width:950px}.contract-table td strong{display:block;font-size:10px}.contract-table td small{display:block;margin-top:4px;color:var(--crm-text-muted);font-size:8px}.money{color:var(--crm-navy);font-variant-numeric:tabular-nums}@media(max-width:800px){.contract-summary{grid-template-columns:1fr 1fr}}@media(max-width:450px){.contract-summary{grid-template-columns:1fr}}
</style>
