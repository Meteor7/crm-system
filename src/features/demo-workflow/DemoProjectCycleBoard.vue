<script setup lang="ts">
import { demoHealthReason } from './demo-health-label'
import { computed } from 'vue'
import { CalendarClock, CheckCircle2, TriangleAlert } from '@lucide/vue'
import {
  buildDemoProjectTimeline,
  demoProjectCycleGroup,
  isCustomerExpectedRisk,
  recentCompletedProjects,
  recentTerminatedProjects,
} from '@/domain/demo-project-cycle'
import type { DemoHealthLevel } from '@/types/crm'
import type { DemoWorkflowDto } from '@/types/workspaces'
import DemoProjectTimeline from './DemoProjectTimeline.vue'
import { personnelDisplayName } from '@/demo/personnel'
import { useI18n } from '@/i18n'

const props = defineProps<{
  items: DemoWorkflowDto[]
  health: 'all' | DemoHealthLevel
  customer: string
  salesOwner: string
  engineerOwner: string
}>()
const emit = defineEmits<{
  'update:health': [value: 'all' | DemoHealthLevel]
  'update:customer': [value: string]
  'update:salesOwner': [value: string]
  'update:engineerOwner': [value: string]
  open: [item: DemoWorkflowDto]
}>()
const { locale, t } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const stageLabel = (value: string) => copy(value, ({
  'Sales Preparation': 'Sales 准备', 'Engineer Review': '工程评估', 'Manager Approval': '经理审批',
  'Wafer & Test Preparation': 'Wafer 与测试准备', 'Test Execution': '测试执行',
  'Internal Review': '内部评审', 'Customer Review': '客户评审',
} as Record<string, string>)[value] || value)

const timelineLabels = [
  'Sales Preparation',
  'Engineer Review',
  'Manager Approval',
  'Wafer & Test Preparation',
  'Test Execution',
  'Internal Review',
  'Customer Review',
]

// Terminated Demos are archived too: they follow the completed ones, marked and never counted.
const recentItems = computed(() => [
  ...props.items.filter((item) => item.archiveCategory !== 'Completed'),
  ...recentCompletedProjects(props.items),
  ...recentTerminatedProjects(props.items),
])
const filtered = computed(() => {
  return recentItems.value.filter((item) =>
    (props.health === 'all' || item.health?.level === props.health)
    && (props.customer === 'all' || item.account === props.customer)
    && (props.salesOwner === 'all' || item.salesOwner === props.salesOwner)
    && (props.engineerOwner === 'all' || item.engineerOwner === props.engineerOwner),
  )
})
const customers = computed(() => [...new Set(props.items.map((item) => item.account))].sort())
const salesOwners = computed(() => [...new Set(props.items.map((item) => item.salesOwner))].sort())
const engineerOwners = computed(() => [...new Set(props.items.map((item) => item.engineerOwner))].sort())
const activeCount = computed(() => props.items.filter((item) => item.archiveCategory === 'In Progress').length)
const riskCount = computed(() => props.items.filter(isCustomerExpectedRisk).length)
const completedCount = computed(() => recentItems.value.filter((item) => demoProjectCycleGroup(item) === 'completed').length)
const orderedItems = computed(() => {
  const activeItems = filtered.value.filter((item) => item.archiveCategory !== 'Completed')
  return [
    ...activeItems.filter(isCustomerExpectedRisk),
    ...activeItems.filter((item) => !isCustomerExpectedRisk(item)),
    ...filtered.value.filter((item) => item.archiveCategory === 'Completed'),
  ]
})

function currentStageOwner(item: DemoWorkflowDto): string {
  // A terminated Demo's stop node is not an active stage, so it has no current actor.
  const current = demoProjectCycleGroup(item) === 'terminated'
    ? undefined
    : buildDemoProjectTimeline(item).find((step) => step.state === 'Current')
  return current?.actor
    || item.engineerOwner
    || (locale.value === 'en-US' ? 'To be confirmed' : '待确认')
}

function formatCustomerExpectedDate(value?: string): string {
  return /^(\d{4}-\d{2}-\d{2})/.exec(value ?? '')?.[1] ?? (locale.value === 'en-US' ? 'To be confirmed' : '待确认')
}

function startsCompletedBlock(item: DemoWorkflowDto, index: number): boolean {
  return item.archiveCategory === 'Completed'
    && index > 0
    && orderedItems.value[index - 1]?.archiveCategory !== 'Completed'
}
</script>

<template>
  <section class="project-cycle-board" data-project-cycle-board>
    <div class="board-summary">
      <article><CalendarClock :size="17" /><span>{{ copy('Active projects', '进行中项目') }}</span><strong>{{ activeCount }}</strong></article>
      <article class="risk"><TriangleAlert :size="17" /><span>{{ copy('Customer expected ≤ 7 days', '客户预期 ≤ 7 天') }}</span><strong>{{ riskCount }}</strong></article>
      <article><CheckCircle2 :size="17" /><span>{{ copy('Completed in last 100 days', '过去 100 天已完成') }}</span><strong>{{ completedCount }}</strong></article>
    </div>

    <div class="board-toolbar">
      <label class="toolbar-filter">
        <span>{{ copy('Health', '健康状态') }}</span>
        <select
          :value="health"
          :aria-label="copy('Project health', '项目健康状态')"
          @change="emit('update:health', ($event.target as HTMLSelectElement).value as 'all' | DemoHealthLevel)"
        >
          <option value="all">{{ copy('All', '全部') }}</option>
          <option value="critical">{{ copy('Red · Critical', '红色 · 紧迫') }}</option>
          <option value="stalled">{{ copy('Orange · Stalled', '橙色 · 停滞') }}</option>
          <option value="healthy">{{ copy('Green · Healthy', '绿色 · 正常') }}</option>
        </select>
      </label>
      <label class="toolbar-filter">
        <span>{{ copy('Account', '客户') }}</span>
        <select
          :value="customer"
          :aria-label="copy('Project account', '项目客户')"
          @change="emit('update:customer', ($event.target as HTMLSelectElement).value)"
        >
          <option value="all">{{ copy('All accounts', '全部客户') }}</option>
          <option v-for="account in customers" :key="account" :value="account">{{ account }}</option>
        </select>
      </label>
      <label class="toolbar-filter">
        <span>{{ copy('Sales', '销售') }}</span>
        <select
          :value="salesOwner"
          :aria-label="copy('Project Sales owner', '项目 Sales 负责人')"
          @change="emit('update:salesOwner', ($event.target as HTMLSelectElement).value)"
        >
          <option value="all">{{ copy('All', '全部') }}</option>
          <option v-for="owner in salesOwners" :key="owner" :value="owner">{{ personnelDisplayName(owner) }}</option>
        </select>
      </label>
      <label class="toolbar-filter">
        <span>{{ copy('Engineer', '工程师') }}</span>
        <select
          :value="engineerOwner"
          :aria-label="copy('Project Engineer owner', '项目工程师负责人')"
          @change="emit('update:engineerOwner', ($event.target as HTMLSelectElement).value)"
        >
          <option value="all">{{ copy('All', '全部') }}</option>
          <option v-for="owner in engineerOwners" :key="owner" :value="owner">{{ personnelDisplayName(owner) }}</option>
        </select>
      </label>
    </div>

    <div class="project-cycle-table-shell">
      <div class="project-cycle-table" data-project-cycle-table>
        <header class="project-table-header">
          <span>{{ copy('Project', '项目名称') }}</span>
          <span>{{ copy('Current stage owner', '当前阶段负责人') }}</span>
          <span>DDL</span>
          <div class="timeline-column-header">
            <strong>{{ copy('Project milestones', '项目周期节点') }}</strong>
            <div>
              <span v-for="label in timelineLabels" :key="label">{{ stageLabel(label) }}</span>
            </div>
          </div>
        </header>

        <div class="project-table-body">
          <button
            v-for="(item, index) in orderedItems"
            :key="item.id"
            type="button"
            class="project-cycle-row"
            :class="{
              'is-customer-risk': isCustomerExpectedRisk(item),
              'is-request-project': demoProjectCycleGroup(item) === 'request' && !isCustomerExpectedRisk(item),
              'is-test-project': demoProjectCycleGroup(item) === 'test' && !isCustomerExpectedRisk(item),
              'is-completed-project': demoProjectCycleGroup(item) === 'completed',
              'is-terminated-project': demoProjectCycleGroup(item) === 'terminated',
              'starts-completed-block': startsCompletedBlock(item, index),
            }"
            :data-project-id="item.id"
            :data-customer-risk="isCustomerExpectedRisk(item)"
            data-project-cycle-row
            @click="emit('open', item)"
          >
            <span class="project-name-cell">
              <strong>{{ item.title }}</strong>
               <small v-if="isCustomerExpectedRisk(item)">{{ copy('Urgent · ', '加急 · ') }}{{ demoHealthReason(item.health, locale) }}</small>
              <small
                v-if="demoProjectCycleGroup(item) === 'terminated'"
                class="terminated-marker"
                :title="item.terminationReason"
                data-terminated-marker
              >{{ t('evaluations.terminated') }} · {{ item.terminationReason }}</small>
            </span>
            <span class="project-owner-cell" data-current-stage-owner>
              {{ personnelDisplayName(currentStageOwner(item)) }}
            </span>
            <span class="project-ddl" data-customer-expected-ddl>
               {{ copy('DDL: ', 'DDL：') }}{{ formatCustomerExpectedDate(item.customerExpectedDate) }}
            </span>
            <span class="timeline-panel">
              <DemoProjectTimeline
                :item="item"
                compact
                hide-context
                row-mode
                scope="full"
                :tone="demoProjectCycleGroup(item) === 'terminated' ? 'terminated' : item.archiveCategory === 'Completed'
                  ? 'complete'
                  : isCustomerExpectedRisk(item)
                    ? 'critical'
                    : demoProjectCycleGroup(item) === 'request'
                      ? 'request'
                      : 'test'"
              />
            </span>
          </button>
           <p v-if="!orderedItems.length" class="empty-list">{{ copy('No projects match the current filters', '当前筛选下暂无项目') }}</p>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.project-cycle-board{display:grid;gap:14px;min-width:0}.board-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.board-summary article{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:9px;padding:13px 15px;color:#6f747b;background:#fff;border:1px solid #DCE3EE;border-radius:7px}.board-summary article>span{font-size:11px}.board-summary article>strong{color:#25292f;font-size:20px}.board-summary .risk{color:#b7292e;background:#fff8f8;border-color:#edc3c5}.board-summary .risk>strong{color:#c52228}.board-toolbar{display:flex;justify-content:flex-end;gap:9px}.search-field,.toolbar-filter{display:flex;height:42px;align-items:center;gap:8px;padding:0 12px;background:#fff;border:1px solid #d7d3cc;border-radius:5px}.search-field{width:min(330px,30vw);color:#656a70}.search-field input{min-width:0;flex:1;background:transparent;border:0;outline:0;font-size:12px}.toolbar-filter>span{font-size:10px;font-weight:750}.toolbar-filter select{min-width:78px;background:transparent;border:0;outline:0;font-size:10px}.cycle-sections{display:grid;gap:13px}.cycle-section{min-width:0;overflow:hidden;background:#fff;border:1px solid #d9d6d0;border-radius:8px}.cycle-section.is-active{border-color:#efb17f;box-shadow:inset 4px 0 #ef7217}.is-active .section-header{background:#fff8f1;border-bottom-color:#f1d1b7}.is-active .section-header button{color:#9f4508;background:#fff7f0;border-color:#efb184}.cycle-section.is-critical{border-color:#df777b;box-shadow:inset 4px 0 #d6373d}.is-critical .section-header{background:#fff2f3;border-bottom-color:#efc1c3}.is-critical .section-header span{color:#bd2c32}.is-critical .section-header button{color:#ae252b;background:#fff3f3;border-color:#df777b}.cycle-section.is-completed{border-color:#8dcaa8;box-shadow:inset 4px 0 #35a466}.is-completed .section-header{background:#f3faf5;border-bottom-color:#cbe6d5}.is-completed .section-header span{color:#2b8b53}.is-completed .section-header button{color:#267848;background:#f3faf5;border-color:#75bd94}.section-header{display:flex;min-height:74px;align-items:center;justify-content:space-between;gap:16px;padding:12px 16px;border-bottom:1px solid #e4e1dc}.section-header>div{display:grid;grid-template-columns:auto 1fr;gap:2px 9px;align-items:baseline}.section-header span{color:#df6812;font-size:9px;font-weight:800;letter-spacing:.08em;text-transform:uppercase}.section-header h2{margin:0;color:#22262c;font-size:17px}.section-header p{grid-column:1/-1;margin:0;color:#82868b;font-size:10px}.section-header button{display:flex;align-items:center;gap:6px;padding:8px 11px;color:#9f4508;background:#fff7f0;border:1px solid #efb184;border-radius:5px;font-size:10px;font-weight:800;cursor:pointer}.section-header button:disabled{opacity:.45;cursor:not-allowed}.section-body{display:grid;min-height:210px;grid-template-columns:300px minmax(0,1fr)}.project-list{max-height:230px;overflow-y:auto;padding:8px;background:#f5f3ef;border-right:1px solid #e2dfd9;scrollbar-width:thin}.project-list-item{display:grid;width:100%;grid-template-columns:auto 1fr;gap:4px 8px;margin-bottom:6px;padding:10px 11px;color:#6c7177;background:#fff;border:1px solid transparent;border-radius:5px;text-align:left;cursor:pointer}.project-list-item:hover{border-color:#d7d3cc}.project-list-item.selected{border-color:#e97a2a;box-shadow:inset 3px 0 #e96c12}.project-list-item.is-normal-project{background:#fff7ee;border-color:#f1cfb2}.project-list-item.is-customer-risk{background:#fff0f1;border-color:#e8afb2}.project-list-item.is-customer-risk.selected{border-color:#ce3137;box-shadow:inset 3px 0 #c92228}.project-list-item.is-completed-project{background:#edf8f1;border-color:#b8ddc7}.project-list-item.is-completed-project.selected{border-color:#43a970;box-shadow:inset 3px 0 #35a466}.is-completed-project .project-code{color:#277b4a}.project-code{color:#9b4b13;font-size:9px;font-weight:800}.project-list-item>strong{overflow:hidden;color:#2b2f35;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.project-list-item>small,.project-meta,.risk-copy{grid-column:1/-1;overflow:hidden;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.project-list-item>small{color:#62676d}.project-meta{color:#8b8f94}.risk-copy{color:#c3272d;font-weight:800}.timeline-panel{display:grid;min-width:0;align-items:center;padding:16px 18px}.timeline-panel>p{color:#91959a;font-size:11px;text-align:center}.empty-list{margin:28px 10px;color:#93969a;font-size:10px;text-align:center}@media(max-width:1080px){.board-toolbar{flex-wrap:wrap}.search-field{width:100%}.section-body{grid-template-columns:260px minmax(620px,1fr);overflow-x:auto}}@media(max-width:720px){.board-summary{grid-template-columns:1fr}.board-toolbar{display:grid;grid-template-columns:1fr 1fr}.search-field{grid-column:1/-1}.section-body{grid-template-columns:1fr}.project-list{max-height:220px;border-right:0;border-bottom:1px solid #e2dfd9}.timeline-panel{overflow-x:auto}.section-header{align-items:flex-start;flex-direction:column}.section-header button{align-self:flex-end}}
.cycle-section-cluster{display:grid;gap:13px;min-width:0}.active-demo-frame{padding:10px;background:#F3F5FA;border:1px solid #d8d4cd;border-radius:11px;box-shadow:0 6px 20px rgba(44,48,54,.05)}.cycle-section.is-request{border-color:#89c8a4;box-shadow:inset 4px 0 #35a466}.is-request .section-header{background:#f3faf5;border-bottom-color:#cbe6d5}.is-request .section-header span{color:#2b8b53}.is-request .section-header button{color:#267848;background:#f3faf5;border-color:#75bd94}.cycle-section.is-test{border-color:#efb17f;box-shadow:inset 4px 0 #ef7217}.is-test .section-header{background:#fff8f1;border-bottom-color:#f1d1b7}.is-test .section-header button{color:#9f4508;background:#fff7f0;border-color:#efb184}.cycle-section.is-completed{border-color:#bfc2c5;box-shadow:inset 4px 0 #8c9197}.is-completed .section-header{background:#f4f5f6;border-bottom-color:#d9dcdf}.is-completed .section-header span{color:#747a80}.is-completed .section-header button{color:#656b71;background:#f6f7f8;border-color:#bfc3c7}.cycle-section.is-critical{border-color:#df777b;box-shadow:inset 4px 0 #d6373d}.is-critical .section-header{background:#fff2f3;border-bottom-color:#efc1c3}.is-critical .section-header span{color:#bd2c32}.is-critical .section-header button{color:#ae252b;background:#fff3f3;border-color:#df777b}.project-list-item.is-request-project{background:#eef8f2;border-color:#b9dec8}.project-list-item.is-request-project.selected{border-color:#43a970;box-shadow:inset 3px 0 #35a466}.is-request-project .project-code{color:#277b4a}.project-list-item.is-test-project{background:#fff7ee;border-color:#f1cfb2}.project-list-item.is-test-project.selected{border-color:#e97a2a;box-shadow:inset 3px 0 #e96c12}.project-list-item.is-completed-project{background:#f0f1f2;border-color:#d1d4d7}.project-list-item.is-completed-project.selected{border-color:#92979c;box-shadow:inset 3px 0 #858b91}.is-completed-project .project-code{color:#666c72}.project-ddl{grid-column:1/-1;overflow:hidden;color:#555b61;font-size:9px;font-weight:750;text-overflow:ellipsis;white-space:nowrap}.project-list-item.is-customer-risk .project-ddl{color:#a52b30}.risk-copy{white-space:normal}.active-demo-frame .cycle-section:first-child{margin-top:0}@media(max-width:720px){.active-demo-frame{padding:7px}}
.project-cycle-table-shell{min-width:0;overflow-x:auto;background:#fff;border:1px solid #d9d6d0;border-radius:8px;box-shadow:0 6px 20px rgba(44,48,54,.04)}.project-cycle-table{min-width:1238px}.project-table-header,.project-cycle-row{display:grid;grid-template-columns:250px 140px 128px minmax(720px,1fr)}.project-table-header{min-height:76px;align-items:stretch;color:#666c72;background:#f5f4f1;border-bottom:1px solid #d8d5cf}.project-table-header>span{display:flex;align-items:center;padding:0 16px;background:#f5f4f1;border-right:1px solid #DCE3EE;font-size:10px;font-weight:800;letter-spacing:.04em}.project-table-header>span:nth-child(1),.project-name-cell{position:sticky;left:0;z-index:3}.project-table-header>span:nth-child(2),.project-owner-cell{position:sticky;left:250px;z-index:3}.project-table-header>span:nth-child(3),.project-cycle-row>.project-ddl{position:sticky;left:390px;z-index:3;box-shadow:8px 0 12px -12px rgba(44,48,54,.8)}.timeline-column-header{display:grid;grid-template-rows:30px 1fr;min-width:0}.timeline-column-header>strong{display:flex;align-items:center;justify-content:center;color:#555b61;border-bottom:1px solid #DCE3EE;font-size:10px;letter-spacing:.04em}.timeline-column-header>div{display:grid;grid-template-columns:repeat(6,minmax(112px,1fr));align-items:center}.timeline-column-header span{padding:0 4px;color:#73787e;font-size:9px;font-weight:750;text-align:center}.project-table-body{display:grid}.project-cycle-row{position:relative;width:100%;min-height:68px;align-items:stretch;padding:0;color:#555b61;background:#fff;border:0;border-top:1px solid #ebe8e3;font:inherit;text-align:left;cursor:pointer;transition:background-color .2s ease,box-shadow .2s ease}.project-cycle-row:first-child{border-top:0}.project-cycle-row:hover{z-index:1;background:#fffaf6;box-shadow:inset 0 0 0 1px #eab98f}.project-cycle-row:active{transform:translateY(1px)}.project-cycle-row:focus-visible{z-index:2;outline:2px solid #d76313;outline-offset:-2px}.project-name-cell,.project-owner-cell,.project-cycle-row>.project-ddl{display:flex;min-width:0;align-items:center;padding:12px 16px;background:inherit;border-right:1px solid #EDF1F7}.project-name-cell{align-items:flex-start;justify-content:center;flex-direction:column;gap:4px}.project-name-cell::before{position:absolute;top:0;bottom:0;left:0;width:3px;background:#35a466;content:""}.project-name-cell strong{max-width:100%;overflow:hidden;color:#282d33;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.project-name-cell small{color:#bd2c32;font-size:9px;font-weight:800}.project-owner-cell{color:#444a50;font-size:10px;font-weight:700}.project-cycle-row>.project-ddl{grid-column:auto;overflow:visible;color:#565c62;font-size:9px;font-weight:750;text-overflow:clip;white-space:nowrap}.project-cycle-row>.timeline-panel{display:block;min-width:0;align-self:center;padding:10px 14px}.project-cycle-row.is-test-project .project-name-cell::before{background:#ef7217}.project-cycle-row.is-customer-risk{background:#fff5f5}.project-cycle-row.is-customer-risk:hover{background:#ffeded;box-shadow:inset 0 0 0 1px #df777b}.project-cycle-row.is-customer-risk .project-name-cell::before{background:#d6373d}.project-cycle-row.is-customer-risk>.project-ddl{color:#a52b30}.project-cycle-row.is-completed-project{color:#777d83;background:#f7f8f8}.project-cycle-row.is-completed-project .project-name-cell::before{background:#989da2}.project-cycle-row.is-completed-project .project-name-cell strong,.project-cycle-row.is-completed-project .project-owner-cell,.project-cycle-row.is-completed-project>.project-ddl{color:#6e747a}.project-cycle-row.starts-completed-block{border-top:8px solid #e8e9e9}.project-cycle-table .empty-list{margin:0;padding:42px 16px;border-top:1px solid #ebe8e3}.project-cycle-table :deep(.timeline-row .timeline-label),.project-cycle-table :deep(.timeline-row .timeline-track small){display:none}.project-cycle-table :deep(.timeline-row .timeline-track){min-width:672px;grid-template-columns:repeat(6,minmax(112px,1fr))}.project-cycle-table :deep(.timeline-row .timeline-track li){gap:5px}.project-cycle-table :deep(.timeline-row .timeline-track li::before),.project-cycle-table :deep(.timeline-row .timeline-track li::after){top:7px}.project-cycle-table :deep(.timeline-row .timeline-track time){margin-top:2px;font-size:9px}.project-cycle-table :deep(.timeline-row .timeline-scroll){overflow:visible;padding:0 4px}@media(max-width:1080px){.project-cycle-table-shell{width:100%}}@media(max-width:720px){.project-cycle-table{min-width:1058px}.project-table-header,.project-cycle-row{grid-template-columns:220px 130px 118px minmax(590px,1fr)}.project-table-header>span:nth-child(2),.project-owner-cell{left:220px}.project-table-header>span:nth-child(3),.project-cycle-row>.project-ddl{left:350px}.project-name-cell,.project-owner-cell,.project-cycle-row>.project-ddl{padding-right:12px;padding-left:12px}.project-cycle-row>.timeline-panel{padding-right:10px;padding-left:10px}}
.project-cycle-table{min-width:1190px}.project-table-header,.project-cycle-row{grid-template-columns:250px 112px 108px minmax(720px,1fr)}.project-table-header>span:nth-child(2),.project-owner-cell{left:250px}.project-table-header>span:nth-child(3),.project-cycle-row>.project-ddl{left:362px}.project-table-header>span:nth-child(2),.project-table-header>span:nth-child(3),.project-owner-cell,.project-cycle-row>.project-ddl{padding-right:12px;padding-left:12px}@media(max-width:720px){.project-cycle-table{min-width:1026px}.project-table-header,.project-cycle-row{grid-template-columns:220px 110px 106px minmax(590px,1fr)}.project-table-header>span:nth-child(2),.project-owner-cell{left:220px}.project-table-header>span:nth-child(3),.project-cycle-row>.project-ddl{left:330px}}
.project-cycle-row{min-height:88px}.project-cycle-table :deep(.timeline-row .timeline-track li::before),.project-cycle-table :deep(.timeline-row .timeline-track li::after){top:20px}
.timeline-column-header>div{grid-template-columns:repeat(7,minmax(102px,1fr))}
.project-cycle-table :deep(.timeline-row .timeline-track){min-width:714px;grid-template-columns:repeat(7,minmax(102px,1fr))}
.project-cycle-row.is-terminated-project{color:#7d6f70;background:#fbf7f7}.project-cycle-row.is-terminated-project .project-name-cell::before{background:#b86b6f}.project-name-cell .terminated-marker{max-width:100%;overflow:hidden;color:#9a4a4e;text-overflow:ellipsis;white-space:nowrap}
</style>
