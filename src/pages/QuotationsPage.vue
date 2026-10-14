<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { FilePlus2, FileText } from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import { api as defaultApi, type CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import PageHeader from '@/design-system/PageHeader.vue'
import DataState from '@/design-system/DataState.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import ModalShell from '@/design-system/ModalShell.vue'
import FilterBar from '@/features/shared/FilterBar.vue'
import { formatDisplayDate } from '@/domain/time'
import { useAppStore } from '@/stores/app'
import type { AccountSummaryDto, Tone } from '@/types/crm'
import type { StrategyOpportunityDto } from '@/types/workspaces'
import type { QuotationApprovalStatus, QuotationStatus, QuotationSummaryDto, QuotationType } from '@/features/quotations/types'
import { localeMessage, useI18n, useLocaleMessage } from '@/i18n'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const route = useRoute()
const router = useRouter()
const app = useAppStore()
const { locale, t } = useI18n()
const ui = (english: string, chinese: string) => localeMessage(english, chinese)[locale.value]
const rows = ref<QuotationSummaryDto[]>([])
const opportunities = ref<StrategyOpportunityDto[]>([])
const accounts = ref<AccountSummaryDto[]>([])
const loading = ref(false)
const denied = ref(false)
const error = useLocaleMessage()
const requestId = ref('')
const total = ref(0)
const status = ref<QuotationStatus | 'All'>('All')
const approvalStatus = ref<QuotationApprovalStatus | 'All'>('All')
const quotationType = ref<QuotationType | 'All'>('All')
const modalOpen = ref(false)
const modalBusy = ref(false)
const modalError = useLocaleMessage()
const selectedOpportunityId = ref('')
const selectedAccountId = ref('')
const createType = ref<QuotationType>('Device')
const createSource = ref<'Opportunity' | 'Others'>('Opportunity')
const page = ref(1)
const pageSize = ref(10)
let loadSequence = 0

const statusTones: Record<QuotationStatus, Tone> = {
  Draft: 'neutral',
  Published: 'info',
  Accepted: 'positive',
  Rejected: 'danger',
  Expired: 'warning',
  Superseded: 'neutral',
}
const approvalTones: Record<QuotationApprovalStatus, Tone> = {
  'Not Submitted': 'neutral', Pending: 'warning', Approved: 'positive', Rejected: 'danger', 'Not Required': 'neutral',
}
const quotedOpportunityIds = ref(new Set<string>())
const writableAccounts = computed(() => {
  const user = app.bootstrap?.user
  if (user?.role === 'Manager') return accounts.value
  return user?.role === 'Sales' ? accounts.value.filter((account) => account.owner === user.id) : []
})
const writableAccountIds = computed(() => new Set(writableAccounts.value.map((account) => account.id)))
const availableOpportunities = computed(() => opportunities.value.filter((item) =>
  !item.siteRestricted && writableAccountIds.value.has(item.accountId) && !quotedOpportunityIds.value.has(item.id),
))
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const canCreate = computed(() => createSource.value === 'Opportunity'
  ? availableOpportunities.value.some((item) => item.id === selectedOpportunityId.value)
  : writableAccountIds.value.has(selectedAccountId.value))

function quotationStatusLabel(value: QuotationStatus) {
  return ({
    Draft: ui('Draft', '草稿'), Published: ui('Published', '已发布'), Accepted: ui('Accepted', '已接受'),
    Rejected: ui('Rejected', '已驳回'), Expired: ui('Expired', '已过期'), Superseded: ui('Superseded', '已被替代'),
  } satisfies Record<QuotationStatus, string>)[value]
}
function approvalStatusLabel(value: QuotationApprovalStatus) {
  return ({
    'Not Submitted': ui('Not submitted', '未提交'), Pending: ui('Pending', '待审批'), Approved: ui('Approved', '已批准'),
    Rejected: ui('Rejected', '已驳回'), 'Not Required': ui('Not required', '无需审批'),
  } satisfies Record<QuotationApprovalStatus, string>)[value]
}
function quotationTypeLabel(value: QuotationType) {
  return value === 'Device' ? ui('Device', '设备') : ui('Service', '服务')
}

async function load() {
  const sequence = ++loadSequence
  loading.value = true
  error.value = ''
  denied.value = false
  try {
    const query = { status: status.value, approvalStatus: approvalStatus.value, page: page.value, pageSize: pageSize.value, ...(quotationType.value === 'All' ? {} : { quotationType: quotationType.value }) }
    const result = await props.apiClient.listQuotations(query)
    if (sequence !== loadSequence) return
    rows.value = result.data.items
    total.value = result.meta?.total ?? rows.value.length
  } catch (cause) {
    if (sequence !== loadSequence) return
    const mapped = mapRequestError(cause)
    error.value = mapped.localizedMessage ?? mapped.message
    requestId.value = mapped.requestId
    denied.value = mapped.denied
    rows.value = []
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

function resetFilters() {
  status.value = 'All'
  approvalStatus.value = 'All'
  quotationType.value = 'All'
  page.value = 1
  void load()
}

function changePage(nextPage: number) {
  if (nextPage < 1 || nextPage > totalPages.value || nextPage === page.value) return
  page.value = nextPage
  void load()
}
function changePageSize(value: number) {
  pageSize.value = value
  page.value = 1
  void load()
}

async function openDetail(row: QuotationSummaryDto) {
  await router.push({ name: 'quotation-detail', params: { quotationId: row.id } })
}

async function loadQuotedOpportunityIds() {
  const ids = new Set<string>()
  let nextPage = 1
  let loaded = 0
  let expectedTotal = 0
  do {
    const result = await props.apiClient.listQuotations({ page: nextPage, pageSize: 200 })
    result.data.items.forEach((item) => { if (item.opportunityId) ids.add(item.opportunityId) })
    loaded += result.data.items.length
    expectedTotal = result.meta?.total ?? loaded
    nextPage += 1
  } while (loaded < expectedTotal)
  quotedOpportunityIds.value = ids
}

async function loadAllOpportunities() {
  const items: StrategyOpportunityDto[] = []
  let nextPage = 1
  let expectedTotal = 0
  do {
    const result = await props.apiClient.listStrategyOpportunities({ page: nextPage, pageSize: 200 })
    items.push(...result.data.items)
    expectedTotal = result.meta?.total ?? items.length
    nextPage += 1
    if (!result.data.items.length) break
  } while (items.length < expectedTotal)
  return items
}

async function loadAllAccounts() {
  const items: AccountSummaryDto[] = []
  let nextPage = 1
  let expectedTotal = 0
  do {
    const result = await props.apiClient.listAccounts({ page: nextPage, pageSize: 200 })
    items.push(...result.data.items)
    expectedTotal = result.meta?.total ?? items.length
    nextPage += 1
    if (!result.data.items.length) break
  } while (items.length < expectedTotal)
  return items
}

async function openCreate(opportunityId = '') {
  modalError.value = ''
  selectedOpportunityId.value = ''
  selectedAccountId.value = ''
  createType.value = 'Device'
  createSource.value = 'Opportunity'
  try {
    if (opportunityId) {
      const existing = (await props.apiClient.listQuotations({ opportunityId, page: 1, pageSize: 1 })).data.items[0]
      if (existing) {
        await openDetail(existing)
        return
      }
    }
    ;[opportunities.value, accounts.value] = await Promise.all([loadAllOpportunities(), loadAllAccounts()])
    await loadQuotedOpportunityIds()
    selectedOpportunityId.value = availableOpportunities.value.some((item) => item.id === opportunityId) ? opportunityId : ''
    modalOpen.value = true
  } catch (cause) {
    const mapped = mapRequestError(cause)
    modalError.value = mapped.localizedMessage ?? mapped.message
  }
}

async function createQuotation() {
  modalBusy.value = true
  modalError.value = ''
  try {
    const input = createSource.value === 'Opportunity'
      ? { ...(createType.value === 'Device' ? {} : { quotationType: createType.value }), opportunityId: selectedOpportunityId.value }
      : { quotationType: createType.value, accountId: selectedAccountId.value }
    const result = await props.apiClient.createQuotation(input as Parameters<CrmApi['createQuotation']>[0])
    modalOpen.value = false
    await router.push(`/quotations/${result.data.quotation.id}`)
  } catch (cause) {
    const mapped = mapRequestError(cause)
    modalError.value = mapped.localizedMessage ?? mapped.message
  } finally {
    modalBusy.value = false
  }
}

function opportunityAccount(item: StrategyOpportunityDto) {
  return item.account || item.accountId
}

watch([status, approvalStatus, quotationType], () => {
  page.value = 1
  void load()
})

onMounted(async () => {
  await app.loadBootstrap(props.apiClient)
  await load()
  const opportunityId = typeof route.query.opportunityId === 'string' ? route.query.opportunityId : ''
  if (opportunityId && app.can('quotation:write')) await openCreate(opportunityId)
})
</script>

<template>
  <div class="quotations-page">
    <PageHeader :eyebrow="ui('SALES QUOTATION', '销售报价')" :title="t('quotations.title')" :description="t('quotations.description')">
      <button v-if="app.can('quotation:write')" class="primary-button" data-testid="new-quotation" type="button" @click="openCreate()">
        <FilePlus2 :size="15" />{{ t('quotations.new') }}
      </button>
    </PageHeader>

    <FilterBar :result-label="t('quotations.result', { count: total })" @reset="resetFilters">
      <select v-model="status" class="filter-control" :aria-label="locale === 'en-US' ? 'Quotation status' : '报价状态'">
        <option value="All">{{ t('quotations.allStatuses') }}</option>
        <option value="Draft">{{ quotationStatusLabel('Draft') }}</option>
        <option value="Published">{{ quotationStatusLabel('Published') }}</option>
        <option value="Accepted">{{ quotationStatusLabel('Accepted') }}</option>
        <option value="Rejected">{{ quotationStatusLabel('Rejected') }}</option>
        <option value="Expired">{{ quotationStatusLabel('Expired') }}</option>
      </select>
      <select v-model="approvalStatus" class="filter-control" :aria-label="locale === 'en-US' ? 'Approval status' : '审批状态'">
        <option value="All">{{ t('quotations.allApprovalStatuses') }}</option><option value="Not Submitted">{{ approvalStatusLabel('Not Submitted') }}</option><option value="Pending">{{ approvalStatusLabel('Pending') }}</option><option value="Approved">{{ approvalStatusLabel('Approved') }}</option><option value="Rejected">{{ approvalStatusLabel('Rejected') }}</option><option value="Not Required">{{ approvalStatusLabel('Not Required') }}</option>
      </select>
      <select v-model="quotationType" class="filter-control" :aria-label="locale === 'en-US' ? 'Quotation type' : '报价类型'">
        <option value="All">{{ t('quotations.allTypes') }}</option><option value="Device">{{ quotationTypeLabel('Device') }}</option><option value="Service">{{ quotationTypeLabel('Service') }}</option>
      </select>
    </FilterBar>

    <section class="quotations-card">
      <DataState v-if="loading && !rows.length" type="loading" />
      <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
      <DataState v-else-if="error" type="error" :message="error" :request-id="requestId" @retry="load" />
      <div v-else-if="rows.length" class="table-scroll">
        <table class="crm-table quotation-table is-responsive">
          <thead><tr><th>{{ (locale === 'en-US' ? 'Name' : '报价单') }}</th><th>{{ (locale === 'en-US' ? 'Type' : '类型') }}</th><th>{{ (locale === 'en-US' ? 'Opportunity' : '关联商机') }}</th><th>{{ (locale === 'en-US' ? 'Last modified' : '上一次修改日期') }}</th><th>{{ (locale === 'en-US' ? 'Status' : '状态') }}</th><th>{{ (locale === 'en-US' ? 'Approval' : '审批') }}</th></tr></thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id" class="quotation-row" tabindex="0" @click="openDetail(row)" @keydown.enter="openDetail(row)">
              <td :data-label="(locale === 'en-US' ? 'Quotation' : '报价单')">
                <button class="quotation-link record-name-link" type="button" :data-quotation-id="row.id" @click.stop="openDetail(row)">
                  <span class="quotation-link__mark"><FileText :size="14" /></span>
                  <span class="quotation-link__copy"><strong>{{ row.refNo }}</strong><small>{{ row.accountName }}</small></span>
                </button>
              </td>
              <td :data-label="(locale === 'en-US' ? 'Type' : '类型')"><strong>{{ quotationTypeLabel(row.quotationType) }}</strong></td>
              <td :data-label="(locale === 'en-US' ? 'Opportunity' : '关联商机')"><strong>{{ row.opportunityTitle || ui('Others', '其他') }}</strong><small>{{ row.opportunityId || row.accountId }} · V{{ row.latestVersion }}</small></td>
              <td :data-label="(locale === 'en-US' ? 'Last modified' : '修改日期')">{{ formatDisplayDate(row.modified) }}</td>
              <td :data-label="(locale === 'en-US' ? 'Status' : '状态')"><StatusBadge :label="quotationStatusLabel(row.status)" :tone="statusTones[row.status]" /></td>
              <td :data-label="(locale === 'en-US' ? 'Approval' : '审批')"><StatusBadge :label="approvalStatusLabel(row.approvalStatus)" :tone="approvalTones[row.approvalStatus]" /></td>
            </tr>
          </tbody>
        </table>
      </div>
      <DataState v-else type="empty" :title="t('quotations.emptyTitle')" :message="t('quotations.emptyMessage')" />

      <nav v-if="totalPages > 1" class="quotation-pager" :aria-label="(locale === 'en-US' ? 'Quotation pagination' : '报价分页')">
        <button class="secondary-button" type="button" :disabled="page <= 1" @click="changePage(page - 1)">{{ (locale === 'en-US' ? 'Previous' : '上一页') }}</button>
        <span>{{ (locale === 'en-US' ? `${total} records · Page ${page} / ${totalPages}` : `共 ${total} 条 · 第 ${page} / ${totalPages} 页`) }}</span><label>{{ (locale === 'en-US' ? 'Per page' : '每页') }}<select :value="pageSize" :aria-label="(locale === 'en-US' ? 'Quotations per page' : '报价每页数量')" @change="changePageSize(Number(($event.target as HTMLSelectElement).value))"><option :value="10">10</option><option :value="25">25</option><option :value="50">50</option></select></label>
        <button class="secondary-button" data-testid="quotation-next" type="button" :disabled="page >= totalPages" @click="changePage(page + 1)">{{ (locale === 'en-US' ? 'Next' : '下一页') }}</button>
      </nav>
    </section>

    <ModalShell v-if="modalOpen" :title="t('quotations.new')" :eyebrow="ui('QUOTATION', '报价单')" :busy="modalBusy" :submit-disabled="!canCreate" @close="modalOpen = false" @submit="createQuotation">
      <p v-if="modalError" class="form-error">{{ modalError }}</p>
      <p v-if="createSource === 'Opportunity' && !availableOpportunities.length" class="form-hint">{{ t('quotations.noOpportunities') }}</p>
      <div class="form-grid">
        <label><span>{{ t('quotations.type') }}</span><select v-model="createType" data-testid="quotation-type" :aria-label="t('quotations.type')"><option value="Device">{{ quotationTypeLabel('Device') }}</option><option value="Service">{{ quotationTypeLabel('Service') }}</option></select></label>
        <label><span>{{ t('quotations.source') }}</span><select v-model="createSource" data-testid="quotation-source" :aria-label="t('quotations.source')"><option value="Opportunity">{{ ui('Opportunity', '商机') }}</option><option value="Others">{{ ui('Others', '其他') }}</option></select></label>
        <label v-if="createSource === 'Opportunity'"><span>{{ ui('Opportunity', '商机') }}</span><select v-model="selectedOpportunityId" :aria-label="t('quotations.selectOpportunity')" required><option value="">{{ t('quotations.selectOpportunity') }}</option><option v-for="item in availableOpportunities" :key="item.id" :value="item.id">{{ item.title }} · {{ opportunityAccount(item) }}</option></select></label>
        <label v-else><span>{{ (locale === 'en-US' ? 'Account' : '客户') }}</span><select v-model="selectedAccountId" data-testid="quotation-account" :aria-label="t('quotations.selectAccount')" required><option value="">{{ t('quotations.selectAccount') }}</option><option v-for="item in writableAccounts" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
      </div>
    </ModalShell>
  </div>
</template>

<style scoped>
.quotations-page{display:grid;gap:14px}.quotations-card{overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:14px;box-shadow:var(--shadow-card)}.quotation-row{cursor:pointer;transition:background .15s}.quotation-row:hover,.quotation-row:focus{background:#f4f8f8;outline:none}.quotation-link{display:flex;align-items:center;gap:8px;padding:0;color:inherit;text-align:left;cursor:pointer;background:transparent;border:0;font:inherit}.quotation-link__mark{display:grid;width:30px;height:30px;flex:0 0 auto;place-items:center;color:var(--crm-brand-ink);background:var(--crm-brand-soft);border-radius:9px}.quotation-link__copy{display:grid;gap:3px}.quotation-link strong{font-size:12px}.quotation-table td strong,.quotation-table td small{display:block}.quotation-table td small{margin-top:4px;color:var(--crm-muted);font-size:10px}.form-grid{display:grid;grid-template-columns:minmax(0,1fr);gap:14px}.form-grid label{display:grid;min-width:0;gap:6px;align-content:start}.form-grid span{font-size:11px;font-weight:700}.form-grid input,.form-grid select{width:100%;min-width:0;height:38px;padding:0 12px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:8px;outline:0;font-size:var(--crm-font-md);transition:border-color .15s,box-shadow .15s}.form-grid input:focus,.form-grid select:focus{border-color:var(--crm-teal);box-shadow:0 0 0 3px color-mix(in srgb,var(--crm-teal) 12%,transparent)}.quotation-pager{display:flex;align-items:center;justify-content:flex-end;gap:10px;padding:10px 14px;border-top:1px solid var(--crm-line)}.quotation-pager .secondary-button{min-height:32px;padding:0 12px}.quotation-pager button:disabled{opacity:.45}.quotation-pager span{color:var(--crm-muted);font-size:11px}.form-error{color:#a63c3c}.form-hint{margin:0 0 12px;padding:10px;color:#735f25;font-size:11px;background:#fff7e5;border-radius:8px}
@media(max-width:839px){.quotation-link{min-width:0}.quotation-link__copy{min-width:0}.quotation-link__copy strong,.quotation-link__copy small{overflow-wrap:anywhere}.quotation-pager{justify-content:center}}
</style>
