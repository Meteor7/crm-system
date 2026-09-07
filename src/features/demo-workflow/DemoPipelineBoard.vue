<script setup lang="ts">
import { computed } from 'vue'
import type { DemoHealthLevel, DemoLifecycleStage } from '@/types/crm'
import type { DemoWorkflowDto } from '@/types/workspaces'
import DemoStageColumn from './DemoStageColumn.vue'
import PipelineBoard from '@/design-system/PipelineBoard.vue'
import { personnelDisplayName } from '@/demo/personnel'
import { useI18n } from '@/i18n'

const props = defineProps<{
  items: DemoWorkflowDto[]
  health: 'all' | DemoHealthLevel
  salesOwner: string
  engineerOwner: string
}>()
const emit = defineEmits<{
  'update:health': [value: 'all' | DemoHealthLevel]
  'update:salesOwner': [value: string]
  'update:engineerOwner': [value: string]
  open: [item: DemoWorkflowDto]
}>()
const { locale } = useI18n()
const stageLabel = (stage: string) => locale.value === 'en-US' ? stage : ({ 'Engineer Review': '工程评估', 'Manager Approval': '经理审批', 'Test Preparation': '测试准备', 'Test Execution': '测试执行', 'Internal Review': '内部评审', 'Customer Review': '客户评审' } as Record<string, string>)[stage] || stage

const stages: DemoLifecycleStage[] = [
  'Engineer Review',
  'Manager Approval',
  'Test Preparation',
  'Test Execution',
  'Internal Review',
  'Customer Review',
]

const filtered = computed(() => {
  return props.items.filter((item) =>
    (props.health === 'all' || item.health?.level === props.health)
    && (props.salesOwner === 'all' || item.salesOwner === props.salesOwner)
    && (props.engineerOwner === 'all' || item.engineerOwner === props.engineerOwner),
  )
})

const salesOwners = computed(() => [...new Set(props.items.map((item) => item.salesOwner))].sort())
const engineerOwners = computed(() => [...new Set(props.items.map((item) => item.engineerOwner))].sort())
const boardStages = computed(() => stages.map((stage) => ({ key: stage, label: stageLabel(stage), count: stageItems(stage).length })))

function stageItems(stage: DemoLifecycleStage) {
  return filtered.value.filter((item) => item.stage === stage)
}
</script>

<template>
  <section class="demo-board" data-demo-board>
    <div class="board-toolbar">
      <label class="health-filter">
        <span>{{ locale === 'en-US' ? 'Health' : '健康状态' }}</span>
        <select
          :value="health"
          :aria-label="locale === 'en-US' ? 'Health' : '健康状态'"
          @change="emit('update:health', ($event.target as HTMLSelectElement).value as 'all' | DemoHealthLevel)"
        >
          <option value="all">{{ locale === 'en-US' ? 'All' : '全部' }}</option>
          <option value="critical">{{ locale === 'en-US' ? 'Red · Critical' : '红色 · 紧迫' }}</option>
          <option value="stalled">{{ locale === 'en-US' ? 'Orange · Stalled' : '橙色 · 停滞' }}</option>
          <option value="healthy">{{ locale === 'en-US' ? 'Green · Healthy' : '绿色 · 正常' }}</option>
        </select>
      </label>
      <label class="owner-filter">
        <span>Sales</span>
        <select
          :value="salesOwner"
          :aria-label="locale === 'en-US' ? 'Sales owner' : 'Sales Owner'"
          @change="emit('update:salesOwner', ($event.target as HTMLSelectElement).value)"
        >
          <option value="all">{{ locale === 'en-US' ? 'All' : '全部' }}</option>
          <option v-for="owner in salesOwners" :key="owner" :value="owner">{{ personnelDisplayName(owner) }}</option>
        </select>
      </label>
      <label class="owner-filter">
        <span>Engineer</span>
        <select
          :value="engineerOwner"
          :aria-label="locale === 'en-US' ? 'Engineer owner' : 'Engineer Owner'"
          @change="emit('update:engineerOwner', ($event.target as HTMLSelectElement).value)"
        >
          <option value="all">{{ locale === 'en-US' ? 'All' : '全部' }}</option>
          <option v-for="owner in engineerOwners" :key="owner" :value="owner">{{ personnelDisplayName(owner) }}</option>
        </select>
      </label>
    </div>

    <div class="health-legend" :aria-label="locale === 'en-US' ? 'Health rules' : '健康状态规则'">
      <span class="critical"><i></i>{{ locale === 'en-US' ? 'Red: customer expected ≤ 7 days' : '红：客户预期 ≤ 7 天' }}</span>
      <span class="stalled"><i></i>{{ locale === 'en-US' ? 'Orange: no effective progress for 5 days' : '橙：5 天无有效进展' }}</span>
      <span class="healthy"><i></i>{{ locale === 'en-US' ? 'Green: progressing normally' : '绿：正常推进' }}</span>
    </div>

    <PipelineBoard :stages="boardStages" :columns="6" :aria-label="locale === 'en-US' ? 'Demo lifecycle' : 'Demo 全生命周期'">
      <template #stage="{ stage }">
        <DemoStageColumn :stage="stage.key" :items="stageItems(stage.key)" @open="emit('open', $event)" />
      </template>
    </PipelineBoard>
  </section>
</template>

<style scoped>
.demo-board{width:100%;max-width:100%;min-width:0;overflow:hidden}.board-toolbar{display:flex;align-items:center;justify-content:flex-end;gap:9px;margin-bottom:18px}
.search-field{display:flex;width:min(300px,28vw);height:44px;align-items:center;gap:10px;padding:0 14px;color:#5c626b;background:#fff;border:1px solid #d4d1cc;border-radius:5px}
.search-field input{min-width:0;flex:1;color:#24282e;background:transparent;border:0;outline:0;font-size:13px}
.search-field input::placeholder{color:#9a9da3}
.health-filter,.owner-filter{display:flex;height:44px;align-items:center;gap:7px;padding:0 10px;background:#fff;border:1px solid #d4d1cc;border-radius:5px}
.health-filter span,.owner-filter span{color:#2b3036;font-size:11px;font-weight:700}
.health-filter select,.owner-filter select{min-width:86px;color:#2b3036;background:transparent;border:0;outline:0;font-size:11px}
.health-legend{display:flex;justify-content:flex-end;gap:18px;margin:0 8px 14px;color:#474c53;font-size:12px}
.health-legend span{display:flex;align-items:center;gap:7px;white-space:nowrap}.health-legend i{width:10px;height:10px;border-radius:50%}
.health-legend .critical i{background:#ef2b2d}.health-legend .stalled i{background:#ff860a}.health-legend .healthy i{background:#54a22d}
@media(max-width:1280px){.board-toolbar{flex-wrap:wrap}.search-field{width:min(420px,100%)}}
@media(max-width:680px){.board-toolbar{display:grid;grid-template-columns:1fr 1fr;align-items:stretch;gap:9px}.search-field{grid-column:1/-1;width:100%}.health-filter,.owner-filter{width:100%}.health-legend{justify-content:flex-start;gap:8px 16px;flex-wrap:wrap}}
</style>
