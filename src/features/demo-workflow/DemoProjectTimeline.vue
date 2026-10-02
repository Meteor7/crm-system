<script setup lang="ts">
import { computed } from 'vue'
import {
  buildDemoProjectTimeline,
  preparationGateState,
} from '@/domain/demo-project-cycle'
import type {
  DemoProjectTimelineStepDto,
  DemoWorkflowDto,
} from '@/types/workspaces'
import { personnelDisplayName } from '@/demo/personnel'
import { isTerminatedDemo } from '@/domain/evaluations'
import { formatDisplayDate } from '@/domain/time'
import { useI18n } from '@/i18n'

const props = withDefaults(defineProps<{
  item: DemoWorkflowDto
  compact?: boolean
  hideContext?: boolean
  rowMode?: boolean
  scope?: 'full' | 'request' | 'test'
  tone?: 'default' | 'request' | 'test' | 'critical' | 'complete' | 'terminated'
}>(), { scope: 'full', tone: 'default' })
const { locale, t } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
// The server keeps a terminated Demo's stop node Current and later nodes Waiting; neither is
// still going on or to be scheduled, so they read as where it stopped and as never reached.
const terminated = computed(() => isTerminatedDemo(props.item))
const stateClass = (state: DemoProjectTimelineStepDto['state']) =>
  terminated.value && state === 'Current' ? 'stopped' : state.toLocaleLowerCase()
const stageCopy: Record<string, string> = {
  'Sales Preparation': 'Sales 准备', 'Engineer Review': '工程评估', 'Manager Approval': '经理审批',
  'Wafer Preparation': 'Wafer 准备', 'Test Preparation': '测试准备', 'Test Execution': '测试执行',
  'Internal Review': '内部评审', 'Customer Review': '客户评审',
}
const steps = computed(() => {
  const timeline = buildDemoProjectTimeline(props.item)
  if (props.scope === 'request') return timeline.slice(0, 3)
  if (props.scope === 'test') return timeline.slice(3)
  return timeline
})
const timelineGroups = computed(() => {
  const hasParallelPreparation = steps.value.some((step) => step.key === 'wafer-preparation')
    && steps.value.some((step) => step.key === 'test-preparation')
  return steps.value.flatMap((step) => {
    if (hasParallelPreparation && step.key === 'test-preparation') return []
    if (hasParallelPreparation && step.key === 'wafer-preparation') {
      const preparationSteps = steps.value.filter((candidate) =>
        candidate.key === 'wafer-preparation' || candidate.key === 'test-preparation')
      return [{
        key: 'wafer-test-preparation',
        label: copy('Wafer & Test Preparation', 'Wafer 与测试准备'),
        state: preparationGateState(preparationSteps),
        steps: preparationSteps,
        parallel: true,
      }]
    }
    return [{
      key: step.key,
      label: copy(step.label, stageCopy[step.label] || step.label),
      state: step.state,
      steps: [step],
      parallel: false,
    }]
  })
})

function preparationValue(
  steps: DemoProjectTimelineStepDto[],
  key: 'date' | 'actor',
  fallback: string,
): string {
  const values = [...new Set(steps.map((step) => {
    const value = step[key]
    if (!value) return value
    return key === 'actor' ? personnelDisplayName(value) : formatDisplayDate(value)
  }).filter(Boolean))]
  if (values.length) return values.join(' / ')
  if (key === 'date') {
    if (steps.every((step) => step.state === 'Done')) return locale.value === 'en-US' ? 'Completed (date not recorded)' : '已完成（时间未记录）'
    if (steps.some((step) => step.state === 'Current')) return locale.value === 'en-US' ? 'In progress' : '进行中'
  }
  return fallback
}

function preparationDate(state: DemoProjectTimelineStepDto['state'], steps: DemoProjectTimelineStepDto[]): string {
  if (terminated.value && state === 'Current') return t('demo.timelineStoppedHere')
  return preparationValue(steps, 'date', terminated.value
    ? t('demo.timelineNotReached')
    : locale.value === 'en-US' ? 'To be scheduled' : '待排期')
}

function timelineDate(step: DemoProjectTimelineStepDto): string {
  if (terminated.value && step.state === 'Current') return t('demo.timelineStoppedHere')
  if (step.date) return formatDisplayDate(step.date)
  if (step.state === 'Done') return locale.value === 'en-US' ? 'Completed (date not recorded)' : '已完成（时间未记录）'
  if (step.state === 'Current') return locale.value === 'en-US' ? 'In progress' : '进行中'
  if (terminated.value) return t('demo.timelineNotReached')
  return locale.value === 'en-US' ? 'To be scheduled' : '待排期'
}
</script>

<template>
  <div
    class="project-timeline"
    :class="{
      compact,
      'tone-request': tone === 'request',
      'tone-test': tone === 'test',
      'tone-critical': tone === 'critical',
      'tone-complete': tone === 'complete',
      'tone-terminated': tone === 'terminated',
      'timeline-row': rowMode,
    }"
    :style="{ '--timeline-columns': timelineGroups.length }"
    data-project-timeline
    :aria-label="locale === 'en-US' ? `${item.id} project timeline` : `${item.id} 项目时间链`"
  >
    <div v-if="!hideContext" class="timeline-context">
      <span>{{ item.id }}</span>
      <strong>{{ item.title }}</strong>
      <small>{{ item.account }} · {{ item.equipment }}</small>
    </div>
    <div class="timeline-scroll">
      <ol class="timeline-track">
        <li
          v-for="group in timelineGroups"
          :key="group.key"
          :class="[stateClass(group.state), { 'parallel-preparation': group.parallel }]"
          :data-parallel-preparation="group.parallel ? '' : undefined"
        >
          <template v-if="group.parallel">
            <span class="timeline-label">{{ group.label }}</span>
            <span class="parallel-branch" :aria-label="locale === 'en-US' ? 'Wafer and Test preparation in parallel' : 'Wafer 与 Test 并行准备'">
              <span
                v-for="step in group.steps"
                :key="step.key"
                class="parallel-stage"
                :class="stateClass(step.state)"
                data-parallel-lane
                :data-parallel-stage="step.key"
                :data-tooltip="copy(step.label, stageCopy[step.label] || step.label)"
                :title="copy(step.label, stageCopy[step.label] || step.label)"
              >
                <span class="parallel-wire" aria-hidden="true"></span>
                <i aria-hidden="true"></i>
              </span>
            </span>
            <time>{{ preparationDate(group.state, group.steps) }}</time>
            <small>{{ preparationValue(group.steps, 'actor', locale === 'en-US' ? 'To be confirmed' : '待确认') }}</small>
          </template>
          <template v-else>
            <span class="timeline-label">{{ group.label }}</span>
            <span class="single-node"><i aria-hidden="true"></i></span>
            <time>{{ timelineDate(group.steps[0]) }}</time>
            <small>{{ group.steps[0].actor ? personnelDisplayName(group.steps[0].actor) : (group.state === 'Waiting' ? (locale === 'en-US' ? 'To be confirmed' : '待确认') : (locale === 'en-US' ? 'Customer milestone' : '客户节点')) }}</small>
          </template>
        </li>
      </ol>
    </div>
  </div>
</template>

<style scoped>
.project-timeline{display:grid;gap:18px;min-width:0}.timeline-context{display:grid;grid-template-columns:auto 1fr;gap:4px 10px;align-items:center}.timeline-context>span{padding:4px 7px;color:#a44500;background:#fff0e4;border-radius:4px;font-size:10px;font-weight:800}.timeline-context>strong{overflow:hidden;color:#20242a;font-size:15px;text-overflow:ellipsis;white-space:nowrap}.timeline-context>small{grid-column:1/-1;color:#777d84;font-size:11px}.timeline-scroll{min-width:0;overflow-x:auto;padding:6px 4px 4px}.timeline-track{display:grid;min-width:calc(var(--timeline-columns) * 126px);grid-template-columns:repeat(var(--timeline-columns),minmax(112px,1fr));margin:0;padding:0;list-style:none}.timeline-track li{position:relative;display:grid;justify-items:center;gap:7px;color:#969a9f;text-align:center}.timeline-track li::before,.timeline-track li::after{position:absolute;top:34px;width:50%;height:2px;background:#ddd9d2;content:""}.timeline-track li::before{left:0}.timeline-track li::after{right:0}.timeline-track li:first-child::before,.timeline-track li:last-child::after{display:none}.timeline-label{min-height:18px;color:#6f747a;font-size:11px;font-weight:750}.timeline-track i{z-index:1;width:15px;height:15px;background:#fff;border:3px solid #c8c5bf;border-radius:50%}.timeline-track time{color:#3a3e44;font-size:10px;font-weight:700}.timeline-track small{max-width:108px;overflow:hidden;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.timeline-track li.done::before,.timeline-track li.done::after,.timeline-track li.current::before{background:#ef7217}.timeline-track li.done i{background:#ef7217;border-color:#ef7217}.timeline-track li.current i{background:#fff;border-color:#ef7217;box-shadow:0 0 0 4px #fff0e4}.timeline-track li.current .timeline-label,.timeline-track li.current time{color:#d95e08}.tone-critical .timeline-context>span{color:#ad252b;background:#fff0f1}.tone-critical .timeline-track li.done::before,.tone-critical .timeline-track li.done::after,.tone-critical .timeline-track li.current::before{background:#d6373d}.tone-critical .timeline-track li.done i{background:#d6373d;border-color:#d6373d}.tone-critical .timeline-track li.current i{border-color:#d6373d;box-shadow:0 0 0 4px #ffe8e9}.tone-critical .timeline-track li.done .timeline-label,.tone-critical .timeline-track li.current .timeline-label,.tone-critical .timeline-track li.done time,.tone-critical .timeline-track li.current time{color:#b52b31}.tone-complete .timeline-context>span{color:#247747;background:#e8f6ed}.tone-complete .timeline-track li.done::before,.tone-complete .timeline-track li.done::after{background:#35a466}.tone-complete .timeline-track li.done i{background:#35a466;border-color:#35a466}.tone-complete .timeline-track li.done .timeline-label,.tone-complete .timeline-track li.done time{color:#27794a}.project-timeline.compact{gap:14px}.compact .timeline-context{display:none}.compact .timeline-track li::before,.compact .timeline-track li::after{top:31px}@media(max-width:760px){.timeline-context{grid-template-columns:1fr}.timeline-context>span{width:max-content}.timeline-context>small{grid-column:auto}}
.tone-request .timeline-context>span{color:#247747;background:#e8f6ed}.tone-request .timeline-track li.done::before,.tone-request .timeline-track li.done::after,.tone-request .timeline-track li.current::before{background:#35a466}.tone-request .timeline-track li.done i{background:#35a466;border-color:#35a466}.tone-request .timeline-track li.current i{border-color:#35a466;box-shadow:0 0 0 4px #e8f6ed}.tone-request .timeline-track li.done .timeline-label,.tone-request .timeline-track li.current .timeline-label,.tone-request .timeline-track li.done time,.tone-request .timeline-track li.current time{color:#27794a}.tone-complete .timeline-context>span{color:#666c72;background:#eef0f1}.tone-complete .timeline-track li.done::before,.tone-complete .timeline-track li.done::after{background:#8c9197}.tone-complete .timeline-track li.done i{background:#8c9197;border-color:#8c9197}.tone-complete .timeline-track li.done .timeline-label,.tone-complete .timeline-track li.done time{color:#666c72}
.project-timeline{--timeline-accent:#ef7217;--timeline-halo:#fff0e4;--timeline-tooltip:#2d3238}.tone-request{--timeline-accent:#35a466;--timeline-halo:#e8f6ed}.tone-critical{--timeline-accent:#d6373d;--timeline-halo:#ffe8e9}.tone-complete{--timeline-accent:#8c9197;--timeline-halo:#eef0f1}.parallel-branch{position:relative;display:block;width:44px;height:28px;justify-self:center;margin-top:-5px}.parallel-branch::before{position:absolute;top:3px;bottom:3px;left:50%;width:2px;background:#ddd9d2;content:"";transform:translateX(-50%)}.parallel-preparation.done .parallel-branch::before,.parallel-preparation.current .parallel-branch::before{background:var(--timeline-accent)}.parallel-stage{position:absolute;left:50%;z-index:2;width:15px;height:15px;transform:translateX(-50%)}.parallel-stage:first-child{top:0}.parallel-stage:last-child{bottom:0}.parallel-stage i{display:block;width:15px;height:15px;background:#fff;border:3px solid #c8c5bf;border-radius:50%}.parallel-preparation .parallel-stage.waiting i{background:#fff;border-color:#c8c5bf;box-shadow:none}.parallel-preparation .parallel-stage.done i{background:var(--timeline-accent);border-color:var(--timeline-accent);box-shadow:none}.parallel-preparation .parallel-stage.current i{background:#fff;border-color:var(--timeline-accent);box-shadow:0 0 0 4px var(--timeline-halo)}.parallel-stage::after{position:absolute;bottom:calc(100% + 7px);left:50%;z-index:8;padding:5px 7px;color:#fff;background:var(--timeline-tooltip);border-radius:4px;box-shadow:0 4px 12px rgba(28,32,36,.18);content:attr(data-tooltip);font-size:9px;font-style:normal;font-weight:750;line-height:1;opacity:0;pointer-events:none;transform:translate(-50%,3px);transition:opacity .16s ease,transform .16s ease;white-space:nowrap}.parallel-stage::before{position:absolute;bottom:calc(100% + 3px);left:50%;z-index:8;width:0;height:0;border-top:4px solid var(--timeline-tooltip);border-right:4px solid transparent;border-left:4px solid transparent;content:"";opacity:0;pointer-events:none;transform:translateX(-50%);transition:opacity .16s ease}.parallel-stage:hover::after,.parallel-stage:hover::before{opacity:1}.parallel-stage:hover::after{transform:translate(-50%,0)}.timeline-row .parallel-branch{margin-top:-7px}.timeline-row .parallel-preparation time{margin-top:0}
.timeline-track li::before,.timeline-track li::after{top:44px}.single-node{display:grid;width:76px;height:40px;place-items:center}.single-node i{display:block}.parallel-preparation::before,.parallel-preparation::after{width:calc(50% - 38px)!important}.parallel-branch{width:76px;height:40px;margin-top:0}.parallel-branch::before,.parallel-branch::after{position:absolute;top:7px;bottom:7px;width:2px;background:#ddd9d2;content:"";transform:none}.parallel-branch::before{left:0}.parallel-branch::after{right:0}.parallel-preparation.current .parallel-branch::before,.parallel-preparation.done .parallel-branch::before,.parallel-preparation.done .parallel-branch::after{background:var(--timeline-accent)}.parallel-stage{right:0;left:0;width:100%;height:15px;transform:none}.parallel-stage:first-child{top:0}.parallel-stage:last-child{bottom:0}.parallel-wire{position:absolute;top:50%;right:0;left:0;height:2px;background:#ddd9d2;transform:translateY(-50%)}.parallel-stage.done .parallel-wire{background:var(--timeline-accent)}.parallel-stage.current .parallel-wire{background:linear-gradient(to right,var(--timeline-accent) 0 50%,#ddd9d2 50% 100%)}.parallel-stage i{position:absolute;top:50%;left:50%;z-index:2;transform:translate(-50%,-50%)}.parallel-stage:last-child::after{bottom:calc(100% + 32px)}.parallel-stage:last-child::before{bottom:calc(100% + 28px)}.timeline-row .parallel-branch{margin-top:0}.timeline-row .timeline-track li::before,.timeline-row .timeline-track li::after{top:20px}.timeline-row .parallel-preparation time{margin-top:0}
.tone-terminated{--timeline-accent:#b86b6f;--timeline-halo:#f7eaea}.tone-terminated .timeline-track li.done::before,.tone-terminated .timeline-track li.done::after,.tone-terminated .timeline-track li.current::before{background:#b86b6f}.tone-terminated .timeline-track li.done i{background:#b86b6f;border-color:#b86b6f}.tone-terminated .timeline-track li.current i{border-color:#b86b6f;box-shadow:0 0 0 4px #f7eaea}.tone-terminated .timeline-track li.done .timeline-label,.tone-terminated .timeline-track li.done time,.tone-terminated .timeline-track li.current .timeline-label,.tone-terminated .timeline-track li.current time{color:#9a4a4e}
.timeline-track li.stopped::before,.parallel-preparation.stopped .parallel-branch::before{background:var(--timeline-accent)}.timeline-track li.stopped i,.parallel-preparation .parallel-stage.stopped i{border-color:var(--timeline-accent);box-shadow:none}.parallel-stage.stopped .parallel-wire{background:linear-gradient(to right,var(--timeline-accent) 0 50%,#ddd9d2 50% 100%)}
</style>
