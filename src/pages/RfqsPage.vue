<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { FileCheck2, FilePlus2 } from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import { api as defaultApi, type CrmApi } from '@/api'
import type { MultipartFilePart } from '@/api/binary-transport'
import { mapRequestError } from '@/api/request-state'
import PageHeader from '@/design-system/PageHeader.vue'
import DataState from '@/design-system/DataState.vue'
import ModalShell from '@/design-system/ModalShell.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import PaginationControls from '@/features/shared/PaginationControls.vue'
import { formatDisplayDate } from '@/domain/time'
import { personnelDisplayName } from '@/demo/personnel'
import { useAppStore } from '@/stores/app'
import type { Tone } from '@/types/crm'
import type { StrategyOpportunityDto } from '@/types/workspaces'
import type { RfqStatus, RfqSummaryDto } from '@/features/rfqs/types'
import { localeMessage, useI18n, useLocaleMessage } from '@/i18n'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const app = useAppStore()
const route = useRoute()
const router = useRouter()
const { locale, t, message } = useI18n()
const ui = (english: string, chinese: string) => localeMessage(english, chinese)[locale.value]
const rows = ref<RfqSummaryDto[]>([])
const opportunities = ref<StrategyOpportunityDto[]>([])
const loading = ref(true)
const error = useLocaleMessage()
const denied = ref(false)
const requestId = ref('')
const page = ref(1)
const pageSize = 50
const total = ref(0)
const status = ref<RfqStatus | 'All'>('All')
const owner = ref('All')
const modalOpen = ref(false)
const modalBusy = ref(false)
const modalError = useLocaleMessage()
const opportunityId = ref(typeof route.query.opportunityId === 'string' ? route.query.opportunityId : '')
const engineerId = ref('')
const note = ref('')
const file = ref<File | null>(null)
let sequence = 0
const MAX_FILE_BYTES = 100 * 1024 * 1024
const TIPRAY_HEADER = new TextEncoder().encode('%TSD-Header-###%')
const tipRayUploadConfirm = () => t('rfqs.tipRayConfirm')

const canCreate = computed(() => ['Sales', 'Manager'].includes(app.bootstrap?.user.role ?? '') && app.can('rfq:create'))
const engineers = computed(() => (app.bootstrap?.personnel ?? []).filter((person) => person.role === 'Engineer' && person.availableForAssignment))
const owners = computed(() => [...new Set([
  ...(app.bootstrap?.personnel ?? []).map((person) => person.id),
  ...rows.value.flatMap((item) => [item.salesOwner, item.engineerOwner]),
])].sort())
const usedOpportunityIds = computed(() => new Set(rows.value.map((item) => item.opportunity.id)))
const availableOpportunities = computed(() => opportunities.value.filter((item) => item.stage === '设备规格确认' && !usedOpportunityIds.value.has(item.id)))
const visibleRows = computed(() => rows.value)

function statusLabel(value: RfqStatus) {
  return ({
    'Engineer Review': ui('Engineer review', '工程师评审'), 'Manager Approval': ui('Manager approval', '经理审批'),
    'Sales Revision': ui('Sales revision', '销售修订'), Approved: ui('Approved', '已批准'),
  } satisfies Record<RfqStatus, string>)[value]
}
function opportunityStageLabel(value: string) {
  const keys: Record<string, string> = {
    '需求发现': 'opportunities.stage.discovery', 'Wafer Demo确认': 'opportunities.stage.waferDemo', '预算审批': 'opportunities.stage.budget',
    '设备规格确认': 'opportunities.stage.specification', '报价': 'opportunities.stage.quotation', '采购流程': 'opportunities.stage.procurement', Won: 'opportunities.stage.won', Lost: 'opportunities.stage.lost',
  }
  return keys[value] ? t(keys[value]) : value
}

function statusTone(value: RfqStatus): Tone {
  if (value === 'Approved') return 'positive'
  if (value === 'Sales Revision') return 'danger'
  if (value === 'Manager Approval') return 'warning'
  return 'info'
}

async function load() {
  const current = ++sequence
  loading.value = true
  error.value = ''
  denied.value = false
  try {
    const requestedOpportunityId = typeof route.query.opportunityId === 'string' ? route.query.opportunityId : ''
    const result = await props.apiClient.listRfqs({
      opportunityId: requestedOpportunityId,
      status: status.value,
      owner: owner.value,
      page: page.value,
      pageSize,
    })
    if (current !== sequence) return
    rows.value = result.data.items
    total.value = result.meta?.total ?? rows.value.length
  } catch (cause) {
    if (current !== sequence) return
    const mapped = mapRequestError(cause)
    error.value = mapped.localizedMessage ?? mapped.message
    requestId.value = mapped.requestId
    denied.value = mapped.denied
  } finally {
    if (current === sequence) loading.value = false
  }
}

async function loadOpportunities() {
  const result: StrategyOpportunityDto[] = []
  let nextPage = 1
  let expected = 0
  do {
    const response = await props.apiClient.listStrategyOpportunities({ page: nextPage, pageSize: 200 })
    result.push(...response.data.items)
    expected = response.meta?.total ?? result.length
    nextPage += 1
    if (!response.data.items.length) break
  } while (result.length < expected)
  opportunities.value = result
}

async function openCreate() {
  modalError.value = ''
  opportunityId.value = ''
  engineerId.value = engineers.value[0]?.id ?? ''
  note.value = ''
  file.value = null
  try {
    await loadOpportunities()
    modalOpen.value = true
  } catch (cause) {
    const mapped = mapRequestError(cause)
    error.value = mapped.localizedMessage ?? mapped.message
  }
}

function selectFile(event: Event) {
  const selected = (event.target as HTMLInputElement).files?.[0] ?? null
  if (selected && selected.size > MAX_FILE_BYTES) {
    file.value = null
    modalError.value = message('rfqs.fileTooLarge')
    return
  }
  modalError.value = ''
  file.value = selected
}

async function isTipRayProtected(selected: File) {
  const header = new Uint8Array(await selected.slice(0, TIPRAY_HEADER.length).arrayBuffer())
  return header.length === TIPRAY_HEADER.length && header.every((value, index) => value === TIPRAY_HEADER[index])
}

async function createRfq() {
  if (!opportunityId.value || !engineerId.value || !file.value) {
    modalError.value = message('rfqs.requiredFields')
    return
  }
  modalBusy.value = true
  modalError.value = ''
  try {
    const selected = file.value
    if (selected.size > MAX_FILE_BYTES) {
      modalError.value = message('rfqs.fileTooLarge')
      return
    }
    if (await isTipRayProtected(selected) && !window.confirm(tipRayUploadConfirm())) {
      return
    }
    const part: MultipartFilePart = { blob: selected, fileName: selected.name, mimeType: selected.type, size: selected.size }
    const result = await props.apiClient.createRfq({ opportunityId: opportunityId.value, engineerId: engineerId.value, note: note.value }, part)
    modalOpen.value = false
    await router.push({ name: 'rfq-detail', params: { rfqId: result.data.id } })
  } catch (cause) {
    const mapped = mapRequestError(cause)
    modalError.value = mapped.localizedMessage ?? mapped.message
  } finally {
    modalBusy.value = false
  }
}

function resetFilters() {
  status.value = 'All'
  owner.value = 'All'
}

function goPage(target: number) {
  page.value = target
  void load()
}

watch([status, owner], () => {
  page.value = 1
  void load()
}, { flush: 'sync' })

onMounted(async () => {
  await app.loadBootstrap(props.apiClient)
  await load()
})
</script>

<template>
  <div class="rfq-page">
    <PageHeader :eyebrow="ui('SPECIFICATION CONTROL', '规格管控')" :title="t('rfqs.title')" :description="t('rfqs.description')" />
    <section class="rfq-list" data-testid="rfq-list">
      <header class="list-heading">
        <span class="title-mark"><FileCheck2 :size="21" /></span>
        <div><small>{{ ui('RFQ PROJECTS', 'RFQ 项目') }}</small><h2>{{ ui('Request for Quotation', '报价请求') }}</h2><p>{{ ui('Each RFQ belongs to one Opportunity.', '每条 RFQ 对应一个 Opportunity。') }}</p></div>
        <button v-if="canCreate" class="primary-button" type="button" data-testid="new-rfq" @click="openCreate"><FilePlus2 :size="14" />{{ (locale === 'en-US' ? 'New RFQ' : '新建 RFQ') }}</button>
      </header>

      <div class="toolbar">
        <select v-model="status" :aria-label="(locale === 'en-US' ? 'RFQ status' : 'RFQ 状态')"><option value="All">{{ (locale === 'en-US' ? 'All statuses' : '全部状态') }}</option><option value="Engineer Review">{{ statusLabel('Engineer Review') }}</option><option value="Manager Approval">{{ statusLabel('Manager Approval') }}</option><option value="Sales Revision">{{ statusLabel('Sales Revision') }}</option><option value="Approved">{{ statusLabel('Approved') }}</option></select>
        <select v-model="owner" :aria-label="(locale === 'en-US' ? 'RFQ owner' : 'RFQ 负责人')"><option value="All">{{ (locale === 'en-US' ? 'All owners' : '全部负责人') }}</option><option v-for="item in owners" :key="item" :value="item">{{ personnelDisplayName(item) }}</option></select>
        <span>{{ visibleRows.length }} / {{ rows.length }}</span><button type="button" @click="resetFilters">{{ (locale === 'en-US' ? 'Reset filters' : '重置条件') }}</button>
      </div>

      <div class="table-card">
        <DataState v-if="loading && !rows.length" type="loading" />
        <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
        <DataState v-else-if="error" type="error" :message="error" :request-id="requestId" @retry="load" />
        <DataState v-else-if="!visibleRows.length" type="empty" :title="t('rfqs.emptyTitle')" :message="t('rfqs.emptyMessage')" />
        <div v-else class="table-scroll">
          <table class="crm-table rfq-table">
            <thead><tr><th>RFQ</th><th>{{ ui('Opportunity', '商机') }}</th><th>{{ ui('Account / Site', '客户 / 厂区') }}</th><th>{{ ui('Opportunity Stage', '商机阶段') }}</th><th>{{ ui('RFQ Status', 'RFQ 状态') }}</th><th>{{ ui('Sales', '销售') }}</th><th>{{ ui('Engineer', '工程师') }}</th><th>{{ ui('File / Version', '文件 / 版本') }}</th><th>{{ ui('Updated', '更新日期') }}</th></tr></thead>
            <tbody><tr v-for="item in visibleRows" :key="item.id" :data-rfq-id="item.id">
              <td><strong>{{ item.id }}</strong></td>
              <td><RouterLink class="record-link" :to="{ name: 'rfq-detail', params: { rfqId: item.id } }"><strong>{{ item.opportunity.title }}</strong><small>{{ item.opportunity.id }}</small></RouterLink></td>
              <td><strong>{{ item.opportunity.account }}</strong><small>{{ item.opportunity.site }}</small></td>
              <td>{{ opportunityStageLabel(item.opportunity.stage) }}</td>
              <td><StatusBadge :label="statusLabel(item.status)" :tone="statusTone(item.status)" /></td>
              <td>{{ item.salesOwnerName || personnelDisplayName(item.salesOwner) }}</td>
              <td>{{ item.engineerOwnerName || personnelDisplayName(item.engineerOwner) }}</td>
              <td><strong>{{ item.fileName }}</strong><small>{{ ui('Version', '版本') }} {{ item.latestVersion }}</small></td>
              <td>{{ formatDisplayDate(item.modified) }}</td>
            </tr></tbody>
          </table>
        </div>
        <PaginationControls v-if="total > pageSize" :page="page" :page-size="pageSize" :total="total" @change="goPage" />
      </div>
    </section>

    <ModalShell v-if="modalOpen" :title="t('rfqs.upload')" :eyebrow="ui('SALES UPLOAD', '销售上传')" :busy="modalBusy" :submit-label="t('rfqs.uploadSubmit')" @close="modalOpen = false" @submit="createRfq">
      <div class="create-form">
        <label><span>{{ ui('Opportunity', '商机') }}</span><select v-model="opportunityId" required><option value="">{{ t('rfqs.selectOpportunity') }}</option><option v-for="item in availableOpportunities" :key="item.id" :value="item.id">{{ item.id }} · {{ item.title }} · {{ item.account }}</option></select></label>
        <label><span>{{ ui('Engineer', '工程师') }}</span><select v-model="engineerId" required><option value="">{{ t('rfqs.selectEngineer') }}</option><option v-for="item in engineers" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
        <label><span>{{ (locale === 'en-US' ? 'RFQ file' : 'RFQ 文件') }}</span><input type="file" :aria-label="(locale === 'en-US' ? 'RFQ file' : 'RFQ 文件')" accept=".pdf,.png,.jpg,.jpeg,.docx,.xlsx,.pptx" required @change="selectFile" /><small>{{ (locale === 'en-US' ? 'PDF, PNG, JPG, DOCX, XLSX, PPTX, up to 100 MiB' : 'PDF、PNG、JPG、DOCX、XLSX、PPTX，最大 100 MiB') }}</small></label>
        <label><span>{{ (locale === 'en-US' ? 'Notes' : '备注') }}</span><textarea v-model="note" rows="3" :placeholder="(locale === 'en-US' ? 'Optional' : '可选')" /></label>
        <p v-if="modalError" class="form-error">{{ modalError }}</p>
      </div>
    </ModalShell>
  </div>
</template>

<style scoped>
.rfq-page,.rfq-list{display:grid;gap:12px}.list-heading{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:12px;padding:14px 16px;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.title-mark{display:grid;width:42px;height:42px;place-items:center;color:var(--crm-brand-ink);background:var(--crm-brand-soft);border-radius:10px}.list-heading small{color:var(--crm-text-muted);font-size:8px;font-weight:800}.list-heading h2{margin:3px 0;color:var(--crm-navy);font-size:19px}.list-heading p{margin:0;color:var(--crm-text-muted);font-size:9px}.list-heading .primary-button{display:flex;align-items:center;gap:6px}.toolbar{display:flex;align-items:center;gap:8px;padding:11px 13px;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.toolbar select{height:38px;padding:0 10px;background:#fff;border:1px solid var(--crm-line);border-radius:9px;font:inherit;font-size:9px}.toolbar>span{margin-left:auto;color:var(--crm-text-muted);font-size:9px}.toolbar>button{color:var(--crm-teal);background:transparent;border:0;font:inherit;font-size:9px;font-weight:800;cursor:pointer}.table-card{min-height:310px;overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.table-scroll{overflow:auto}.rfq-table{min-width:1260px}.rfq-table td strong,.rfq-table td small,.rfq-table td a{display:block}.rfq-table td small{margin-top:4px;color:var(--crm-text-muted);font-size:8px}.rfq-table td a{color:var(--crm-brand-strong);text-decoration:none}.create-form{display:grid;gap:15px}.create-form label{display:grid;gap:6px;color:var(--crm-text);font-size:9px;font-weight:800}.create-form select,.create-form input,.create-form textarea{width:100%;padding:10px;border:1px solid var(--crm-line);border-radius:8px;background:#fff;font:inherit;font-size:10px}.create-form small{color:var(--crm-text-muted);font-size:8px;font-weight:400}.form-error{margin:0;padding:9px;color:var(--crm-danger);background:#fff1f1;border-radius:7px;font-size:9px}@media(max-width:800px){.toolbar{align-items:stretch;flex-wrap:wrap}.toolbar .crm-search-control{flex:1 1 100%}.toolbar>span{margin-left:0}.list-heading{grid-template-columns:auto 1fr}.list-heading .primary-button{grid-column:1/-1;justify-content:center}}
</style>
