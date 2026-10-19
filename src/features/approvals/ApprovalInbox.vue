<script setup lang="ts">
import { computed } from 'vue'
import { ArrowUpRight, Check, ClipboardCheck, FileText } from '@lucide/vue'
import { useI18n } from '@/i18n'
import { formatDisplayDateTime } from '@/domain/time'
import { approvalLabel, visibleApprovals, type ApprovalItem, type ApprovalViewer } from './approval-queue'

const props = withDefaults(defineProps<{ items: readonly ApprovalItem[]; viewer: ApprovalViewer; now?: string }>(), { now: () => new Date().toISOString() })
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const timestampLabel = (item: ApprovalItem) => item.submittedAtLabel ? copy('Materials completed at', '资料完成时间') : copy('Submitted at', '提交时间')
const emit = defineEmits<{ 'open-source': [item: ApprovalItem] }>()
const allowed = computed(() => visibleApprovals(props.items, props.viewer).sort((left, right) => Number(right.unread) - Number(left.unread)))
const isUnread = (item: ApprovalItem) => item.unread
const counts = computed(() => ({ all: allowed.value.length, unread: allowed.value.filter(isUnread).length }))
function open(item: ApprovalItem) {
  const current = allowed.value.find(candidate => candidate.id === item.id)
  if (current) emit('open-source', current)
}
function waiting(item: ApprovalItem) {
  const hours = Math.max(0, Math.floor((Date.parse(props.now) - Date.parse(item.submittedAt)) / 3_600_000))
  return hours >= 24 ? copy(`Waiting ${Math.floor(hours / 24)} days`, `等待 ${Math.floor(hours / 24)} 天`) : hours ? copy(`Waiting ${hours} hours`, `等待 ${hours} 小时`) : copy('Just submitted', '刚提交')
}
</script>

<template>
  <section class="approval-inbox" data-approval-inbox>
    <header class="inbox-heading">
      <div><div class="inbox-eyebrow"><ClipboardCheck :size="16" />{{ copy('My approval workspace', '我的审批工作台') }}</div><h2 class="inbox-title">{{ copy('Pending approvals', '待审批') }} <span>{{ counts.all }}</span></h2><p>{{ copy('View the items that need your attention and handle them in their business pages.', '集中查看需要你处理的事项，审批与确认仍在对应业务页面完成。') }}</p></div>
      <div class="inbox-identity"><span>{{ viewer.name.slice(0, 1) }}</span><div><strong>{{ viewer.name }}</strong><small>{{ copy('Current reviewer', '当前处理人') }}</small></div></div>
    </header>
    <div class="queue-summary" :aria-label="copy('Approval summary', '审批概况')"><span><strong>{{ counts.all }}</strong> {{ copy('Pending', '待处理') }}</span><span><strong>{{ counts.unread }}</strong> {{ copy('Unviewed', '未查看') }}</span></div>
    <div class="queue-panel">
      <div v-if="allowed.length" class="queue-table-scroll">
        <table class="approval-table"><thead><tr><th>{{ copy('Type', '业务类型') }}</th><th>{{ copy('Approval item', '审批事项') }}</th><th>{{ copy('Current step', '当前环节') }}</th><th>{{ copy('Submitted by', '提交人') }}</th><th>{{ copy('Submitted at', '提交时间') }}</th><th class="action-heading">{{ copy('Action', '操作') }}</th></tr></thead>
          <tbody><tr v-for="item in allowed" :key="item.id" :data-approval-id="item.id">
            <td class="kind-cell"><span class="kind-badge"><FileText :size="13" />{{ approvalLabel(item.kind, locale) }}</span></td>
            <td class="subject-cell"><div class="subject-title"><span v-if="isUnread(item)" class="unread-dot" :aria-label="copy('Unviewed', '未查看')" /><strong>{{ item.title }}</strong></div><p>{{ item.customer }}<span>·</span>{{ item.sourceId }}</p></td>
            <td class="stage-cell">{{ item.stage }}</td>
            <td class="requester-cell"><span class="requester-avatar">{{ item.requester.slice(0, 1) }}</span>{{ item.requester }}</td>
            <td class="date-cell"><time :datetime="item.submittedAt" :title="timestampLabel(item)" :aria-label="`${timestampLabel(item)} ${formatDisplayDateTime(item.submittedAt)}`">{{ formatDisplayDateTime(item.submittedAt).slice(5) }}</time><small>{{ waiting(item) }}</small></td>

            <td class="action-cell"><button class="view-item" type="button" :aria-label="`${copy('Go to approval', '前往审批')}：${item.title}`" data-open-approval @click="open(item)">{{ copy('Go to approval', '前往审批') }}<ArrowUpRight :size="14" /></button></td>
          </tr></tbody>
        </table>
      </div>
      <div v-else class="queue-empty"><div><Check :size="24" /></div><h3>{{ copy('No pending approvals', '当前没有待审批事项') }}</h3><p>{{ copy('New items that need your attention will appear here.', '需要你处理的新事项会出现在这里。') }}</p></div>
      <footer class="queue-footer"><span>{{ copy('Showing', '显示') }} {{ allowed.length }} {{ copy('items', '项') }}</span><span><span class="unread-dot" />{{ copy('Unviewed items', '未查看的事项') }}</span><small>{{ copy('Scoped to the current reviewer', '按当前处理人展示') }}</small></footer>
    </div>
  </section>
</template>

<style scoped>
.approval-inbox{min-width:0;container-type:inline-size;color:var(--crm-text);font-size:13px}.inbox-heading{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:8px 0 18px}.inbox-eyebrow{display:flex;align-items:center;gap:7px;color:var(--crm-text-muted);font-size:11px;font-weight:500}.approval-inbox .inbox-heading .inbox-title{display:flex;align-items:center;gap:10px;margin:8px 0 6px;font-size:26px!important;font-weight:650;letter-spacing:-.025em}.approval-inbox .inbox-heading .inbox-title>span{min-width:26px;padding:3px 7px;color:var(--crm-link);background:var(--crm-brand-soft);border-radius:7px;font-size:12px;font-weight:650;text-align:center}.inbox-heading p{margin:0;color:var(--crm-text-muted);font-size:12px!important;line-height:1.6}.inbox-identity{display:flex;align-items:center;gap:9px}.inbox-identity>span{display:grid;width:36px;height:36px;place-items:center;color:var(--crm-brand-ink);background:var(--crm-brand-soft);border-radius:11px;font-weight:650}.inbox-identity>div{display:grid;gap:3px}.inbox-identity strong{font-size:12px}.inbox-identity small{font-size:10px;color:var(--crm-text-muted)}
.queue-summary{display:flex;gap:24px;padding:0 0 20px;color:var(--crm-text-muted);font-size:12px}.queue-summary>span{display:flex;align-items:baseline;gap:6px}.queue-summary strong{color:var(--crm-text);font-size:20px;font-weight:600;font-variant-numeric:tabular-nums}.queue-panel{overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:14px}.queue-table-scroll{overflow:auto}.approval-table{width:100%;border-collapse:collapse;text-align:left}.approval-table th{padding:12px 14px;background:#fcfbf9;color:var(--crm-text-muted);font-size:10px;font-weight:500;white-space:nowrap;border-bottom:1px solid var(--crm-line)}.approval-table td{padding:17px 14px;border-bottom:1px solid #EDF1F7;vertical-align:middle;font-size:12px!important;line-height:1.45}.approval-table tbody tr:last-child td{border-bottom:0}.approval-table tbody tr:hover{background:#fdfbf7}.kind-badge{display:inline-flex;align-items:center;gap:5px;padding:5px 7px;border-radius:6px;background:var(--crm-surface);color:#5e6269;font-size:10px;font-weight:500;white-space:nowrap}.subject-cell{min-width:215px;max-width:360px}.subject-title{display:flex;gap:7px;align-items:center}.subject-title strong{font-size:12px!important;font-weight:600;line-height:1.5}.subject-cell p{display:flex;gap:6px;flex-wrap:wrap;margin:5px 0 0;color:var(--crm-text-muted);font-size:10px!important;line-height:1.5}.subject-cell p>span{color:#b6b3ad}.unread-dot{display:inline-block;width:5px;height:5px;flex:0 0 5px;border-radius:50%;background:var(--crm-brand)}.stage-cell{color:#686d75;min-width:100px}.requester-cell{white-space:nowrap}.requester-avatar{display:inline-grid;width:24px;height:24px;place-items:center;margin-right:6px;background:#f3f2ef;border-radius:50%;color:#7e827f;font-size:10px}.date-cell{white-space:nowrap;font-variant-numeric:tabular-nums}.date-cell small{display:block;margin-top:4px;color:var(--crm-text-muted);font-size:10px}.action-cell,.action-heading{text-align:right;white-space:nowrap}.view-item{display:inline-flex;align-items:center;justify-content:center;gap:5px;min-height:32px;padding:0 9px;color:var(--crm-link);border:1px solid var(--crm-line);border-radius:7px;background:white;font-size:11px!important;cursor:pointer}.view-item:hover{border-color:var(--crm-brand);background:var(--crm-brand-soft)}.queue-footer{display:flex;align-items:center;gap:16px;padding:12px 16px;border-top:1px solid var(--crm-line);color:var(--crm-text-muted);font-size:10px}.queue-footer>span:nth-child(2){display:flex;align-items:center;gap:6px}.queue-footer small{margin-left:auto;font-size:10px}.queue-empty{display:grid;justify-items:center;gap:8px;padding:60px 20px;color:var(--crm-text-muted);text-align:center}.queue-empty>div{display:grid;place-items:center;width:48px;height:48px;background:var(--crm-surface);border-radius:14px}.queue-empty h3{margin:6px 0 0;color:var(--crm-navy);font-size:15px}.queue-empty p{margin:0;font-size:12px!important}.approval-inbox button:focus-visible,.approval-inbox select:focus-visible{outline:2px solid var(--crm-brand);outline-offset:3px}
@container(max-width:900px){.approval-table thead{display:none}.approval-table,.approval-table tbody{display:block}.approval-table tr{display:grid;grid-template-columns:1fr auto;grid-template-areas:'kind action' 'subject subject' 'stage requester' 'date date';gap:9px 14px;padding:16px;border-bottom:1px solid var(--crm-line)}.approval-table td{padding:0;border:0;min-width:0}.kind-cell{grid-area:kind}.subject-cell{grid-area:subject;max-width:none}.stage-cell{grid-area:stage}.requester-cell{grid-area:requester}.date-cell{grid-area:date}.action-cell{grid-area:action}.queue-footer small{display:none}.inbox-heading{align-items:start}.inbox-identity{display:none}.queue-summary{gap:18px}}
</style>
