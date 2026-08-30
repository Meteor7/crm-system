<script setup lang="ts">
import type { DemoWorkflowDto } from '@/types/workspaces'
import DemoProjectTimeline from './DemoProjectTimeline.vue'
import DemoArticleCard from './DemoArticleCard.vue'
import { personnelDisplayName } from '@/demo/personnel'
import { formatDisplayDate } from '@/domain/time'

withDefaults(defineProps<{
  item: DemoWorkflowDto
  showOverview?: boolean
  showTimeline?: boolean
}>(), {
  showOverview: true,
  showTimeline: true,
})
defineEmits<{ download: [id: string]; preview: [id: string] }>()
</script>

<template>
  <div class="demo-main" data-testid="selected-demo">
    <section v-if="showOverview" class="workspace-panel archive-overview">
      <header>
        <div><span class="eyebrow">{{ item.id }}</span><h2>{{ item.title }}</h2></div>
        <span class="workspace-badge info">{{ item.status }}</span>
      </header>
      <div class="archive-overview-body">
        <span>{{ item.account }}</span>
        <strong>Sales {{ personnelDisplayName(item.salesOwner) }}</strong>
        <strong>Engineer {{ personnelDisplayName(item.engineerOwner) }}</strong>
      </div>
    </section>

    <section v-if="showTimeline" class="workspace-panel project-timeline-dashboard" data-project-timeline-dashboard>
      <header><h2>项目时间链</h2><span>Request → Test → Internal Review → Customer Review</span></header>
      <div class="workspace-panel-body">
        <DemoProjectTimeline :item="item" />
      </div>
    </section>

    <section v-if="item.request" class="workspace-panel request-snapshot">
      <header><h2>Demo Request</h2><span>正式提交快照</span></header>
      <div class="detail-grid">
        <div><small>Objective</small><strong>{{ item.request.objective }}</strong></div>
        <div><small>Primary Tool</small><strong>{{ item.request.assignedEquipment || item.request.requestedEquipment }}</strong></div>
        <div><small>Specific Request</small><strong>{{ item.request.specificRequest }}</strong></div>
        <div><small>Expected Results</small><strong>{{ item.request.expectedResults }}</strong></div>
        <div><small>Priority</small><strong>{{ item.request.priority }}</strong></div>
        <div><small>Sales Owner</small><strong>{{ personnelDisplayName(item.request.salesOwner) }}</strong></div>
        <div><small>Engineer Owner</small><strong>{{ personnelDisplayName(item.engineerOwner) }}</strong></div>
        <div><small>Detect / Measure</small><strong>{{ item.request.detectMeasure }}</strong></div>
        <div><small>Complementary Tool</small><strong>{{ item.request.complementaryTool || '—' }}</strong></div>
        <div><small>Sample</small><strong>{{ item.request.sampleType }} · {{ item.request.sampleQuantity }}</strong></div>
        <div><small>Acceptance Criteria</small><strong>{{ item.request.acceptanceCriteria }}</strong></div>
        <div v-if="item.request.internalQuestions?.length" data-demo-sensitive="internal-questions"><small>Internal Questions</small><strong>{{ item.request.internalQuestions.join('；') }}</strong></div>
        <div v-if="item.request.contactPerson" data-demo-sensitive="contact"><small>Customer Contact</small><strong>{{ item.request.contactPerson }}</strong></div>
        <div v-if="item.request.competition"><small>Competition</small><strong>{{ item.request.competition }}</strong></div>
        <div v-if="item.request.testPlan"><small>Test Plan</small><strong>{{ item.request.testPlan }}</strong></div>
        <div v-if="item.request.resourceWindow"><small>Resource Window</small><strong>{{ item.request.resourceWindow }}</strong></div>
        <div v-if="item.request.estimatedCompletionDate"><small>Estimated Completion</small><strong>{{ item.request.estimatedCompletionDate }}</strong></div>
        <div v-if="item.request.technicalRisk"><small>Technical Risk</small><strong>{{ item.request.technicalRisk }}</strong></div>
        <div v-if="item.request.engineerComment"><small>Engineer Comment</small><strong>{{ item.request.engineerComment }}</strong></div>
        <div v-if="item.request.managerDecision"><small>Manager Decision</small><strong>{{ item.request.managerDecision }}</strong></div>
        <div v-if="item.request.managerComment"><small>Manager Comment</small><strong>{{ item.request.managerComment }}</strong></div>
      </div>
      <div v-if="item.request.wafers?.length" class="request-wafers" data-demo-sensitive="wafer-samples">
        <strong>Wafer Samples</strong>
        <span v-for="wafer in item.request.wafers" :key="wafer.id">{{ wafer.id }} · {{ wafer.specificity }} · {{ wafer.detail }}</span>
      </div>
    </section>

    <section v-if="item.evaluation" class="workspace-panel test-summary" data-demo-sensitive="test-runs">
      <header><h2>Demo Test</h2><span>{{ item.evaluation.status }}</span></header>
      <div class="table-wrap">
        <table class="crm-table demo-table">
          <thead><tr><th>Run</th><th>Date</th><th>Lot</th><th>Wafers</th><th>Capture</th><th>False Positive</th><th>WPH</th><th>Status</th><th>Summary</th></tr></thead>
          <tbody>
            <tr v-for="run in item.evaluation.runs" :key="run.id">
              <td><strong>{{ run.id }}</strong></td><td>{{ formatDisplayDate(run.date) }}</td><td>{{ run.lot }}</td><td>{{ run.wafers }}</td>
              <td>{{ run.capture ?? '—' }}</td><td>{{ run.falsePositive ?? '—' }}</td><td>{{ run.wph ?? '—' }}</td>
              <td>{{ run.status }}</td><td>{{ run.summary || '待分析' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <DemoArticleCard :artifacts="item.artifacts || []" @preview="$emit('preview', $event)" @download="$emit('download', $event)" />

    <section class="workspace-panel conclusion-panel">
      <header><h2>Demo Conclusion</h2><span class="workspace-badge info">{{ item.conclusion.status }}</span></header>
      <div class="workspace-panel-body"><strong>{{ item.conclusion.summary || '暂无正式结论' }}</strong></div>
    </section>
  </div>
</template>

<style scoped>
.demo-main{display:grid;gap:14px;min-width:0}.archive-overview h2{margin-top:4px;font-size:20px}.archive-overview-body{display:flex;flex-wrap:wrap;gap:10px 22px;padding:14px 16px;color:var(--crm-text-muted);font-size:12px}.archive-overview-body strong{color:var(--crm-navy)}.detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;background:var(--crm-line)}.detail-grid>div{display:grid;gap:6px;padding:14px;background:#fff}.detail-grid small{color:var(--crm-text-muted);font-size:10px}.detail-grid strong{color:var(--crm-navy);font-size:11px;line-height:1.5}.request-wafers{display:grid;gap:7px;padding:14px 16px;border-top:1px solid var(--crm-line);font-size:11px}.request-wafers span{color:var(--crm-text-muted)}.archive-list{display:grid;gap:1px;background:var(--crm-line)}.archive-list button,.archive-list p{display:grid;gap:5px;margin:0;padding:13px 16px;border:0;background:#fff;text-align:left}.archive-list button{grid-template-columns:auto 1fr auto;align-items:center;color:var(--crm-teal);cursor:pointer}.archive-list button strong{color:var(--crm-navy);font-size:11px}.archive-list button span{color:var(--crm-text-muted);font-size:10px}.table-wrap{overflow:auto}.demo-table{min-width:650px}@media(max-width:720px){.detail-grid{grid-template-columns:1fr}.archive-list button{grid-template-columns:auto 1fr}.archive-list button span{grid-column:2}}
</style>
