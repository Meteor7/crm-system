<script setup lang="ts">
import { personnelDisplayName } from '@/demo/personnel'
import { formatDisplayDate } from '@/domain/time'
import { ArrowRight, Ban, CheckCircle2, Clock3, Download, Pencil, RotateCcw } from '@lucide/vue'
import type { DemoRequestDto, Tone } from '@/types/crm'
import StatusBadge from '@/design-system/StatusBadge.vue'

defineProps<{
  request: DemoRequestDto
  processing?: boolean
  canCreate?: boolean
  canEngineer?: boolean
  canManager?: boolean
  downloading?: boolean
}>()
defineEmits<{ submit: [id: string]; edit: [request: DemoRequestDto]; cancel: [id: string]; engineer: [request: DemoRequestDto]; manager: [request: DemoRequestDto]; download: [request: DemoRequestDto] }>()
const statusLabel: Record<DemoRequestDto['status'], string> = { Draft: '草稿', 'Engineer Review': '待工程评估', 'Engineer Returned': '工程退回', 'Manager Approval': '待经理审批', 'Manager Rejected': '经理驳回', Converted: '已转 Demo', Cancelled: '已取消' }
const tone = (status: DemoRequestDto['status']): Tone => status === 'Converted' ? 'positive' : ['Engineer Returned','Manager Rejected'].includes(status) ? 'warning' : status === 'Cancelled' ? 'danger' : 'info'
</script>

<template>
  <article class="request-card" :class="{ returned: ['Engineer Returned','Manager Rejected'].includes(request.status), converted: request.status === 'Converted' }" :data-demo-request="request.id">
    <header><StatusBadge :label="statusLabel[request.status]" :tone="tone(request.status)" /><small>{{ request.id }} · 客户期望时间 {{ request.customerExpectedDate }}</small></header>
    <h3>{{ request.title }}</h3>
    <p><strong>{{ request.accountName }}</strong> · Sales {{ personnelDisplayName(request.salesOwner) }}<br>{{ request.objective }}</p>
    <div class="request-meta"><span v-if="request.requestMode === 'Self Test'">自测</span><span>{{ request.requestedEquipment }}</span><span>{{ request.sampleQuantity }} Samples</span><span>{{ request.priority }}</span><span>目标 {{ request.targetDate }}</span></div>
    <div class="review-note"><p><b>FAE Review</b>{{ request.engineerComment || '待评估' }}</p><p><b>Boss</b>{{ request.managerComment || '待审批' }}</p><p v-if="request.evaluationId"><b>来源</b>{{ request.id }} → {{ request.evaluationId }}</p></div>
    <div v-if="request.history[0]" class="timeline"><Clock3 :size="12" /><span>最近记录 · {{ formatDisplayDate(request.history[0].at) }} · {{ personnelDisplayName(request.history[0].actor) }}<br>{{ request.history[0].comment }}</span></div>
    <footer>
      <button class="subtle" :data-demo-download="request.id" type="button" :disabled="downloading" @click="$emit('download', request)"><Download :size="13" />{{ downloading ? '生成中' : '下载 Word' }}</button>
      <button v-if="canCreate && ['Draft','Engineer Returned','Manager Rejected'].includes(request.status)" :data-demo-action="`${request.id}-submit`" type="button" :disabled="processing" @click="$emit('submit', request.id)"><ArrowRight :size="13" />提交工程评估</button>
      <button v-if="canCreate && ['Draft','Engineer Returned','Manager Rejected'].includes(request.status)" :data-demo-action="`${request.id}-edit`" class="subtle" type="button" :disabled="processing" @click="$emit('edit', request)"><Pencil :size="13" />修改</button>
      <button v-if="canCreate && ['Draft','Engineer Returned','Manager Rejected'].includes(request.status)" :data-demo-action="`${request.id}-cancel`" class="danger" type="button" :disabled="processing" @click="$emit('cancel', request.id)"><Ban :size="13" />取消</button>
      <button v-if="canEngineer && request.status === 'Engineer Review'" :data-demo-action="`${request.id}-review`" type="button" :disabled="processing" @click="$emit('engineer', request)"><RotateCcw :size="13" />工程处理</button>
      <button v-if="canManager && request.status === 'Manager Approval'" :data-demo-action="`${request.id}-review`" type="button" :disabled="processing" @click="$emit('manager', request)"><CheckCircle2 :size="13" />经理审批</button>
    </footer>
  </article>
</template>

<style scoped>
.request-card{display:grid;gap:9px;padding:15px;background:#fff;border:1px solid var(--crm-line);border-radius:12px;box-shadow:0 5px 15px rgba(31,35,41,.03)}.request-card.returned{border-left:3px solid var(--crm-warning)}.request-card.converted{border-left:3px solid var(--crm-positive)}
header{display:flex;align-items:center;justify-content:space-between}header small{color:var(--crm-text-muted);font-family:ui-monospace,monospace;font-size:8px}h3{margin:0;color:var(--crm-navy);font-size:12px;line-height:1.4}p{margin:0;color:var(--crm-text-muted);font-size:9px;line-height:1.55}p strong{color:var(--crm-text)}
.request-meta{display:flex;flex-wrap:wrap;gap:5px}.request-meta span{padding:4px 6px;color:var(--crm-teal);background:var(--crm-teal-soft);border-radius:6px;font-size:8px;font-weight:700}.review-note{display:grid;gap:3px;padding:8px;background:var(--crm-surface);border-radius:8px}.review-note b{display:inline-block;width:58px;color:var(--crm-text);font-size:8px}.timeline{display:flex;gap:6px;padding-top:7px;color:var(--crm-text-muted);border-top:1px dashed var(--crm-line);font-size:8px;line-height:1.5}.timeline svg{flex:0 0 auto;margin-top:1px}
footer{display:flex;flex-wrap:wrap;gap:6px}footer button{display:flex;align-items:center;gap:5px;padding:7px 9px;color:var(--crm-brand-ink);background:var(--crm-teal);border:0;border-radius:7px;font-size:8px;font-weight:700;cursor:pointer}footer button.subtle{color:var(--crm-teal);background:var(--crm-teal-soft)}footer button.danger{color:#9a3a31;background:#fbe9e5}footer button:disabled{opacity:.55;cursor:not-allowed}
</style>
