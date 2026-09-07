<script setup lang="ts">
import { salesEnumLabel } from '@/features/shared/sales-i18n'
import type { DemoWorkflowDto } from '@/types/workspaces'
import DemoProjectTimeline from './DemoProjectTimeline.vue'
import DemoArticleCard from './DemoArticleCard.vue'
import { personnelDisplayName } from '@/demo/personnel'
import { formatDisplayDate } from '@/domain/time'
import { useI18n } from '@/i18n'

withDefaults(defineProps<{
  item: DemoWorkflowDto
  showOverview?: boolean
  showTimeline?: boolean
}>(), {
  showOverview: true,
  showTimeline: true,
})
defineEmits<{ download: [id: string]; preview: [id: string] }>()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const statusLabel = (status: string) => copy(status, ({ Requested: '已申请', 'Scope Confirmed': '范围已确认', 'Sample Received': '样品已收到', Scheduled: '已排期', Testing: '测试中', Analysis: '分析中', 'Internal Review': '内部评审', 'Customer Review': '客户评审', Accepted: '已接受', Rejected: '已拒绝', Pending: '待确认' } as Record<string, string>)[status] || status)
</script>

<template>
  <div class="demo-main" data-testid="selected-demo">
    <section v-if="showOverview" class="workspace-panel archive-overview">
      <header>
        <div><span class="eyebrow">{{ item.id }}</span><h2>{{ item.title }}</h2></div>
         <span class="workspace-badge info">{{ statusLabel(item.status) }}</span>
      </header>
      <div class="archive-overview-body">
        <span>{{ item.account }}</span>
         <strong>{{ copy('Sales', '销售') }} {{ personnelDisplayName(item.salesOwner) }}</strong>
         <strong>{{ copy('Engineer', '工程师') }} {{ personnelDisplayName(item.engineerOwner) }}</strong>
      </div>
    </section>

    <section v-if="showTimeline" class="workspace-panel project-timeline-dashboard" data-project-timeline-dashboard>
       <header><h2>{{ copy('Project timeline', '项目时间链') }}</h2><span>{{ copy('Request → Test → Internal Review → Customer Review', '申请 → 测试 → 内部评审 → 客户评审') }}</span></header>
      <div class="workspace-panel-body">
        <DemoProjectTimeline :item="item" />
      </div>
    </section>

    <section v-if="item.request" class="workspace-panel request-snapshot">
       <header><h2>{{ copy('Demo Request', 'Demo Request') }}</h2><span>{{ copy('Submitted snapshot', '正式提交快照') }}</span></header>
      <div class="detail-grid">
         <div><small>{{ copy('Objective', '目标') }}</small><strong>{{ item.request.objective }}</strong></div>
         <div><small>{{ copy('Primary Tool', '主要设备') }}</small><strong>{{ item.request.assignedEquipment || item.request.requestedEquipment }}</strong></div>
         <div><small>{{ copy('Specific Request', '具体需求') }}</small><strong>{{ item.request.specificRequest }}</strong></div>
         <div><small>{{ copy('Expected Results', '预期结果') }}</small><strong>{{ item.request.expectedResults }}</strong></div>
         <div><small>{{ copy('Priority', '优先级') }}</small><strong>{{ salesEnumLabel(item.request.priority, locale) }}</strong></div>
         <div><small>{{ copy('Sales Owner', '销售负责人') }}</small><strong>{{ personnelDisplayName(item.request.salesOwner) }}</strong></div>
         <div><small>{{ copy('Engineer Owner', '工程师负责人') }}</small><strong>{{ personnelDisplayName(item.engineerOwner) }}</strong></div>
         <div><small>{{ copy('Detect / Measure', '检测 / 测量') }}</small><strong>{{ item.request.detectMeasure }}</strong></div>
         <div><small>{{ copy('Complementary Tool', '辅助设备') }}</small><strong>{{ item.request.complementaryTool || '—' }}</strong></div>
         <div><small>{{ copy('Sample', '样品') }}</small><strong>{{ item.request.sampleType }} · {{ item.request.sampleQuantity }}</strong></div>
         <div><small>{{ copy('Acceptance Criteria', '验收标准') }}</small><strong>{{ item.request.acceptanceCriteria }}</strong></div>
         <div v-if="item.request.internalQuestions?.length" data-demo-sensitive="internal-questions"><small>{{ copy('Internal Questions', '内部问题') }}</small><strong>{{ item.request.internalQuestions.join(locale === 'en-US' ? '; ' : '；') }}</strong></div>
         <div v-if="item.request.contactPerson" data-demo-sensitive="contact"><small>{{ copy('Customer Contact', '客户联系人') }}</small><strong>{{ item.request.contactPerson }}</strong></div>
         <div v-if="item.request.competition"><small>{{ copy('Competition', '竞品情况') }}</small><strong>{{ item.request.competition }}</strong></div>
         <div v-if="item.request.testPlan"><small>{{ copy('Test Plan', '测试方案') }}</small><strong>{{ item.request.testPlan }}</strong></div>
         <div v-if="item.request.resourceWindow"><small>{{ copy('Resource Window', '资源窗口') }}</small><strong>{{ item.request.resourceWindow }}</strong></div>
         <div v-if="item.request.estimatedCompletionDate"><small>{{ copy('Estimated Completion', '预计完成') }}</small><strong>{{ item.request.estimatedCompletionDate }}</strong></div>
         <div v-if="item.request.technicalRisk"><small>{{ copy('Technical Risk', '技术风险') }}</small><strong>{{ item.request.technicalRisk }}</strong></div>
         <div v-if="item.request.engineerComment"><small>{{ copy('Engineer Comment', '工程师意见') }}</small><strong>{{ item.request.engineerComment }}</strong></div>
         <div v-if="item.request.managerDecision"><small>{{ copy('Manager Decision', '经理决定') }}</small><strong>{{ item.request.managerDecision }}</strong></div>
         <div v-if="item.request.managerComment"><small>{{ copy('Manager Comment', '经理意见') }}</small><strong>{{ item.request.managerComment }}</strong></div>
      </div>
      <div v-if="item.request.wafers?.length" class="request-wafers" data-demo-sensitive="wafer-samples">
         <strong>{{ copy('Wafer Samples', '晶圆样品') }}</strong>
        <span v-for="wafer in item.request.wafers" :key="wafer.id">{{ wafer.id }} · {{ wafer.specificity }} · {{ wafer.detail }}</span>
      </div>
    </section>

    <section v-if="item.evaluation" class="workspace-panel test-summary" data-demo-sensitive="test-runs">
       <header><h2>{{ copy('Demo Test', 'Demo 测试') }}</h2><span>{{ statusLabel(item.evaluation.status) }}</span></header>
      <div class="table-wrap">
        <table class="crm-table demo-table">
           <thead><tr><th>{{ copy('Run', '运行') }}</th><th>{{ copy('Date', '日期') }}</th><th>{{ copy('Lot', '批次') }}</th><th>{{ copy('Wafers', '晶圆数') }}</th><th>{{ copy('Capture', '捕获率') }}</th><th>{{ copy('False Positive', '误报率') }}</th><th>WPH</th><th>{{ copy('Status', '状态') }}</th><th>{{ copy('Summary', '摘要') }}</th></tr></thead>
          <tbody>
            <tr v-for="run in item.evaluation.runs" :key="run.id">
              <td><strong>{{ run.id }}</strong></td><td>{{ formatDisplayDate(run.date) }}</td><td>{{ run.lot }}</td><td>{{ run.wafers }}</td>
              <td>{{ run.capture ?? '—' }}</td><td>{{ run.falsePositive ?? '—' }}</td><td>{{ run.wph ?? '—' }}</td>
               <td>{{ statusLabel(run.status) }}</td><td>{{ run.summary || (locale === 'en-US' ? 'Pending analysis' : '待分析') }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <DemoArticleCard :artifacts="item.artifacts || []" @preview="$emit('preview', $event)" @download="$emit('download', $event)" />

    <section class="workspace-panel conclusion-panel">
       <header><h2>{{ copy('Demo Conclusion', 'Demo 结论') }}</h2><span class="workspace-badge info">{{ statusLabel(item.conclusion.status) }}</span></header>
      <div class="workspace-panel-body"><strong>{{ item.conclusion.summary || (locale === 'en-US' ? 'No formal conclusion' : '暂无正式结论') }}</strong></div>
    </section>
  </div>
</template>

<style scoped>
.demo-main{display:grid;gap:14px;min-width:0}.archive-overview h2{margin-top:4px;font-size:20px}.archive-overview-body{display:flex;flex-wrap:wrap;gap:10px 22px;padding:14px 16px;color:var(--crm-text-muted);font-size:12px}.archive-overview-body strong{color:var(--crm-navy)}.detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;background:var(--crm-line)}.detail-grid>div{display:grid;gap:6px;padding:14px;background:#fff}.detail-grid small{color:var(--crm-text-muted);font-size:10px}.detail-grid strong{color:var(--crm-navy);font-size:11px;line-height:1.5}.request-wafers{display:grid;gap:7px;padding:14px 16px;border-top:1px solid var(--crm-line);font-size:11px}.request-wafers span{color:var(--crm-text-muted)}.archive-list{display:grid;gap:1px;background:var(--crm-line)}.archive-list button,.archive-list p{display:grid;gap:5px;margin:0;padding:13px 16px;border:0;background:#fff;text-align:left}.archive-list button{grid-template-columns:auto 1fr auto;align-items:center;color:var(--crm-teal);cursor:pointer}.archive-list button strong{color:var(--crm-navy);font-size:11px}.archive-list button span{color:var(--crm-text-muted);font-size:10px}.table-wrap{overflow:auto}.demo-table{min-width:650px}@media(max-width:720px){.detail-grid{grid-template-columns:1fr}.archive-list button{grid-template-columns:auto 1fr}.archive-list button span{grid-column:2}}
</style>
