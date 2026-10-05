<script setup lang="ts">
import { personnelDisplayName } from '@/demo/personnel'
import { formatDisplayDate } from '@/domain/time'
import { computed, ref } from 'vue'
import { Ban, CheckCircle2, Download, ExternalLink, Pencil } from '@lucide/vue'
import type { DemoRequestDto, Tone } from '@/types/crm'
import StatusBadge from '@/design-system/StatusBadge.vue'
import PaginationControls from '@/features/shared/PaginationControls.vue'
import { usePagedSelection } from '@/features/shared/paged-selection'
import type { DemoRequestView } from './DemoRequestWorkspaceNav.vue'
import { useI18n } from '@/i18n'

const props = defineProps<{
  view: DemoRequestView
  requests: DemoRequestDto[]
  selectedId?: string
  canCreate?: boolean
  canEngineer?: boolean
  canManager?: boolean
  processing?: string
  downloading?: string
}>()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese

const emit = defineEmits<{
  select: [id: string]
  submit: [id: string]
  edit: [request: DemoRequestDto]
  cancel: [id: string]
  engineer: [request: DemoRequestDto]
  manager: [request: DemoRequestDto]
  download: [request: DemoRequestDto]
  'open-detail': [request: DemoRequestDto]
}>()

const sales = ref('All')
const salesOptions = computed(() => [...new Set(props.requests.map((item) => item.salesOwner))])
const stageRows = computed(() => props.view === 'sales'
  ? props.requests.filter((item) => ['Draft', 'Engineer Returned', 'Manager Rejected'].includes(item.status))
  : props.view === 'engineer'
    ? props.requests.filter((item) => item.status === 'Engineer Review')
    : props.view === 'manager'
      ? props.requests.filter((item) => item.status === 'Manager Approval')
      : props.requests)
const scopedRows = computed(() => {
  return stageRows.value.filter((item) => sales.value === 'All' || item.salesOwner === sales.value)
})
// `requests` is everything in progress. A view is paged here, after it is filtered, so every page is full and
// the count is the view's own.
const { page, pageSize, openingPageSize, pagedRows, selected, paged, turnTo } = usePagedSelection({
  rows: scopedRows,
  selectedId: () => props.selectedId,
  narrowedBy: () => `${props.view}\n${sales.value}`,
  pageSize: 10,
  select: (id) => emit('select', id),
})

const statusLabel: Record<DemoRequestDto['status'], string> = {
  Draft: '草稿',
  'Engineer Review': '待工程评估',
  'Engineer Returned': '工程退回',
  'Manager Approval': '待经理审批',
  'Manager Rejected': '经理驳回',
  Converted: '已转 Demo',
  Cancelled: '已取消',
}
function statusText(status: DemoRequestDto['status']) {
  if (locale.value !== 'en-US') return statusLabel[status]
  return ({ Draft: 'Draft', 'Engineer Review': 'Engineer review', 'Engineer Returned': 'Returned by engineering', 'Manager Approval': 'Manager approval', 'Manager Rejected': 'Rejected by manager', Converted: 'Converted to Demo', Cancelled: 'Cancelled' } as Record<DemoRequestDto['status'], string>)[status]
}
const statusTone = (status: DemoRequestDto['status']): Tone => status === 'Converted'
  ? 'positive'
  : ['Engineer Returned', 'Manager Rejected'].includes(status)
    ? 'warning'
    : status === 'Cancelled'
      ? 'danger'
      : 'info'
const editable = computed(() => Boolean(selected.value && ['Draft', 'Engineer Returned', 'Manager Rejected'].includes(selected.value.status)))
</script>

<template>
  <section class="request-workspace" :data-demo-workspace="view">
    <div class="workspace-main">
      <div class="toolbar">
        <label>
          {{ copy('Sales', '销售') }}
          <select v-model="sales" :aria-label="copy('Workspace Sales', '工作区 Sales')">
            <option value="All">{{ copy('All Sales', '全部 Sales') }}</option>
            <option v-for="item in salesOptions" :key="item">{{ item }}</option>
          </select>
        </label>
        <span class="row-count">Demo Request · {{ scopedRows.length }}</span>
      </div>

      <div class="request-table-wrap" data-demo-request-table>
        <table class="request-table">
          <thead>
            <tr>
              <th>{{ locale === 'en-US' ? 'Request / Project' : 'Request / 项目' }}</th>
              <th>{{ locale === 'en-US' ? 'Account' : '客户' }}</th>
              <th>{{ copy('Sales', '销售') }}</th>
              <th>{{ copy('Engineer', '工程师') }}</th>
              <th>{{ locale === 'en-US' ? 'Status' : '状态' }}</th>
              <th>{{ locale === 'en-US' ? 'Target date' : '目标日期' }}</th>
              <th>{{ locale === 'en-US' ? 'Updated' : '更新日期' }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in pagedRows"
              :key="item.id"
              :class="{ selected: selected?.id === item.id }"
              :data-demo-request="item.id"
              @click="emit('select', item.id)"
            >
              <td>
                <button
                  class="request-link record-name-link"
                  type="button"
                  :data-open-demo-detail="item.id"
                  @click.stop="emit('open-detail', item)"
                >
                  <b>{{ item.id }}</b>
                  <strong>{{ item.title }}</strong>
                </button>
              </td>
              <td>{{ item.accountName }}</td>
              <td>{{ personnelDisplayName(item.salesOwner) }}</td>
              <td>{{ item.engineerOwner ? personnelDisplayName(item.engineerOwner) : (locale === 'en-US' ? 'Unassigned' : '待分配') }}</td>
              <td><StatusBadge :label="statusText(item.status)" :tone="statusTone(item.status)" /></td>
              <td>{{ item.customerExpectedDate || item.targetDate }}</td>
              <td>{{ formatDisplayDate(item.updatedAt) }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="!scopedRows.length" class="workspace-empty">{{ locale === 'en-US' ? 'No Demo Requests in this view' : '当前分类暂无 Demo Request' }}</p>
        <PaginationControls v-if="paged" :page="page" :page-size="pageSize" :opening-page-size="openingPageSize" :total="scopedRows.length" @change="turnTo" @page-size-change="pageSize = $event" />
      </div>
    </div>

      <aside v-if="selected" class="request-actions action-panel" data-demo-request-actions>
        <header>
          <span>{{ locale === 'en-US' ? 'Owner actions' : '相关人员操作' }}</span>
          <StatusBadge :label="statusText(selected.status)" :tone="statusTone(selected.status)" />
        </header>
        <b>{{ selected.id }}</b>
        <h2>{{ selected.title }}</h2>
        <p>{{ selected.accountName }}</p>
        <dl>
          <div><dt>{{ copy('Sales', '销售') }}</dt><dd>{{ personnelDisplayName(selected.salesOwner) }}</dd></div>
          <div><dt>{{ copy('Engineer', '工程师') }}</dt><dd>{{ selected.engineerOwner ? personnelDisplayName(selected.engineerOwner) : (locale === 'en-US' ? 'Unassigned' : '待分配') }}</dd></div>
          <div><dt>{{ locale === 'en-US' ? 'Target date' : '目标日期' }}</dt><dd>{{ selected.customerExpectedDate || selected.targetDate }}</dd></div>
        </dl>

        <button type="button" class="secondary-button" @click="emit('open-detail', selected)">
          <ExternalLink :size="14" />{{ locale === 'en-US' ? 'View details' : '查看详细信息' }}
        </button>
        <button
          type="button"
          class="secondary-button"
          :data-demo-download="selected.id"
          :disabled="downloading === selected.id"
          @click="emit('download', selected)"
        >
          <Download :size="14" />{{ downloading === selected.id ? (locale === 'en-US' ? 'Generating…' : '生成中…') : (locale === 'en-US' ? 'Download Word' : '下载 Word') }}
        </button>
        <template v-if="canCreate && editable">
          <button type="button" class="primary-button" :data-demo-action="`${selected.id}-submit`" :disabled="processing === selected.id" @click="emit('submit', selected.id)">
            <CheckCircle2 :size="14" />{{ locale === 'en-US' ? 'Submit for engineering review' : '提交工程评估' }}
          </button>
          <button type="button" class="secondary-button" :data-demo-action="`${selected.id}-edit`" :disabled="processing === selected.id" @click="emit('edit', selected)">
            <Pencil :size="14" />{{ locale === 'en-US' ? 'Edit Request' : '编辑 Request' }}
          </button>
          <button type="button" class="danger-button" :data-demo-action="`${selected.id}-cancel`" :disabled="processing === selected.id" @click="emit('cancel', selected.id)">
            <Ban :size="14" />{{ locale === 'en-US' ? 'Cancel' : '取消' }}
          </button>
        </template>
        <button
          v-if="canEngineer && selected.status === 'Engineer Review'"
          type="button"
          class="primary-button"
          :data-demo-action="`${selected.id}-review`"
          :disabled="processing === selected.id"
          @click="emit('engineer', selected)"
        >
          <CheckCircle2 :size="14" />{{ locale === 'en-US' ? 'Engineering review' : '工程评估' }}
        </button>
        <button
          v-if="canManager && selected.status === 'Manager Approval'"
          type="button"
          class="primary-button"
          :data-demo-action="`${selected.id}-review`"
          :disabled="processing === selected.id"
          @click="emit('manager', selected)"
        >
          <CheckCircle2 :size="14" />{{ locale === 'en-US' ? 'Manager approval' : '经理审批' }}
        </button>
      </aside>
  </section>
</template>

<style scoped>
.request-workspace{display:grid;gap:12px}.request-filters{display:flex;align-items:center;gap:9px;padding:10px;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.search-control{display:flex;min-width:280px;height:36px;align-items:center;gap:7px;padding:0 10px;color:var(--crm-text-muted);background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:8px}.search-control input{min-width:0;flex:1;background:transparent;border:0;outline:0;font-size:11px}.request-filters select{height:36px;padding:0 10px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;font:inherit;font-size:10px}.request-filters>span{margin-left:auto;color:var(--crm-text-muted);font-size:10px;font-weight:700}.request-layout{display:grid;grid-template-columns:minmax(0,1fr) 250px;gap:12px;align-items:start}.request-table-wrap{overflow:auto;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.request-table{width:100%;min-width:920px;border-collapse:collapse}.request-table th,.request-table td{padding:12px 13px;border-bottom:1px solid var(--crm-line);font-size:10px;text-align:left}.request-table th{color:var(--crm-text-muted);background:#faf9f7;font-size:9px;letter-spacing:.02em}.request-table tbody tr{cursor:pointer;transition:background-color .16s ease}.request-table tbody tr:hover,.request-table tbody tr.selected{background:#fff8ed}.request-table tbody tr.selected{box-shadow:inset 3px 0 0 #ed760f}.request-link{display:grid;gap:3px;min-width:190px;padding:0;color:inherit;background:transparent;border:0;text-align:left;cursor:pointer}.request-link span{color:var(--crm-link);font-size:9px;font-weight:800}.request-link strong{color:var(--crm-link);font-size:11px}.request-actions{display:grid;align-content:start;gap:10px;padding:15px;background:#fff;border:1px solid var(--crm-line);border-radius:12px;box-shadow:0 8px 22px rgba(31,35,41,.035)}.request-actions header{display:flex;align-items:center;justify-content:space-between;gap:8px;padding-bottom:10px;border-bottom:1px solid var(--crm-line)}.request-actions header>span{color:var(--crm-navy);font-size:11px;font-weight:850}.request-actions>b{color:#c65b08;font-size:10px}.request-actions h2{margin:0;color:var(--crm-navy);font-size:14px;line-height:1.4}.request-actions>p{margin:0;color:var(--crm-text-muted);font-size:10px}.request-actions dl{display:grid;margin:2px 0 4px}.request-actions dl div{display:flex;justify-content:space-between;gap:8px;padding:8px 0;border-bottom:1px solid var(--crm-line);font-size:9px}.request-actions dt{color:var(--crm-text-muted)}.request-actions dd{margin:0;color:var(--crm-navy);font-weight:750;text-align:right}.request-actions button{display:flex;min-height:35px;align-items:center;justify-content:center;gap:6px;padding:0 9px;border-radius:8px;font:inherit;font-size:9px;font-weight:800;cursor:pointer}.danger-button{color:var(--crm-danger);background:#fffafa;border:1px solid #e7c1c1}.workspace-empty{margin:0;padding:48px;color:var(--crm-text-muted);font-size:11px;text-align:center}@media(max-width:920px){.request-layout{grid-template-columns:1fr}.request-actions{grid-template-columns:repeat(2,1fr)}.request-actions header,.request-actions h2,.request-actions>p,.request-actions dl{grid-column:1/-1}}@media(max-width:620px){.request-filters{align-items:stretch;flex-direction:column}.search-control{width:100%;min-width:0}.request-filters>span{margin-left:0}.request-actions{grid-template-columns:1fr}.request-actions header,.request-actions h2,.request-actions>p,.request-actions dl{grid-column:auto}}
.request-workspace{grid-template-columns:minmax(0,1fr) 248px;gap:14px;align-items:start}.workspace-main{display:grid;min-width:0;gap:12px}.toolbar{display:flex;align-items:center;gap:10px;padding:11px;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.toolbar-search{display:flex;min-width:240px;height:36px;flex:1;align-items:center;gap:7px;padding:0 11px;color:var(--crm-text-muted);background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:8px}.toolbar-search input{min-width:0;flex:1;background:transparent;border:0;outline:0;font:inherit;font-size:12px}.toolbar>label:not(.toolbar-search){display:flex;align-items:center;gap:7px;color:var(--crm-text-muted);font-size:11px;font-weight:700}.toolbar select{height:36px;padding:0 9px;background:#fff;border:1px solid var(--crm-line-strong);border-radius:8px;font:inherit;font-size:11px}.row-count{flex:none;color:var(--crm-text-muted);font-size:11px;font-weight:700}.request-table th,.request-table td{padding:13px 12px;font-size:11px}.request-table th{background:#faf8f5;font-size:10px}.request-table tbody tr{transition:background .15s ease}.request-table tbody tr.selected{box-shadow:inset 3px 0 0 var(--crm-teal)}.request-link{gap:4px;font:inherit}.request-link b{margin-bottom:4px;color:var(--crm-teal);font-size:11px}.request-link strong{font-size:12px}.request-link:hover strong{color:var(--crm-link-hover);text-decoration:none}.request-actions.action-panel{position:sticky;top:16px;padding:16px;box-shadow:none}.request-actions header{padding-bottom:0;border-bottom:0}.request-actions header>span{color:var(--crm-teal);font-size:11px;font-weight:800}.request-actions>b{color:var(--crm-teal);font-size:12px}.request-actions h2{font-size:15px}.request-actions>p{font-size:11px;line-height:1.5}.request-actions dl{margin:2px 0}.request-actions dl div{font-size:10px}.request-actions dd{font-weight:700}.request-actions button{min-height:36px;padding:0 10px;font-size:11px}.workspace-empty{padding:42px}@media(max-width:1000px){.request-workspace{grid-template-columns:1fr}.request-actions.action-panel{position:static}.toolbar{align-items:stretch;flex-wrap:wrap}.toolbar-search{min-width:100%}}@media(max-width:620px){.toolbar>label:not(.toolbar-search){justify-content:space-between}.row-count{width:100%}}
</style>
