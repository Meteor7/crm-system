<script setup lang="ts">
import { systemValueLabel } from '@/features/shared/system-labels'
import { computed } from 'vue'
import { CalendarClock, Check, Cpu, Wrench } from '@lucide/vue'
import { personnelDisplayName } from '@/demo/personnel'
import type { InstalledToolDto } from '@/types/workspaces'
import { useI18n } from '@/i18n'

const props = withDefaults(defineProps<{ items: InstalledToolDto[]; selectedId?: string }>(), { selectedId: '' })
const emit = defineEmits<{ select: [item: InstalledToolDto] }>()
const { locale, t } = useI18n()
const stageLabel = (stage: string) => locale.value === 'en-US' ? stage : ({ FAT: 'FAT', Shipment: '发运', Installation: '安装', SAT: 'SAT', Warranty: '质保', Completed: '已完成' } as Record<string, string>)[stage] || stage
const statusLabel = (status: string) => locale.value === 'en-US' ? status : ({ Production: '生产中', 'Upgrade Due': '待升级', Installation: '安装中', Active: '启用', Pending: '待确认', Completed: '已完成', Retired: '已退役', Decommissioned: '已停用' } as Record<string, string>)[status] || status

const stageOrder = ['FAT', 'Shipment', 'Installation', 'SAT', 'Warranty'] as const
const currentCount = computed(() => props.items.filter((item) => item.milestones.some((stage) => stage.state === 'Current')).length)
const warrantyCount = computed(() => props.items.filter((item) => {
  const current = item.milestones.find((stage) => stage.state === 'Current')
  return current?.label === 'Warranty' || item.milestones.every((stage) => stage.state === 'Done')
}).length)
const completedNodes = computed(() => props.items.reduce(
  (total, item) => total + item.milestones.filter((stage) => stage.state === 'Done').length,
  0,
))

function milestoneFor(item: InstalledToolDto, label: string) {
  return item.milestones.find((milestone) => milestone.label === label)
}

function milestoneState(item: InstalledToolDto, label: string) {
  return milestoneFor(item, label)?.state ?? 'Waiting'
}

function keyMilestone(item: InstalledToolDto) {
  return item.milestones.find((stage) => stage.state === 'Current')
    ?? item.milestones.find((stage) => stage.state === 'Waiting')
    ?? item.milestones.at(-1)
}
</script>

<template>
  <section class="project-cycle-board" data-installed-tool-project-board>
    <div class="board-summary">
      <article><Cpu :size="17" /><span>{{ t('installed.projectSummary.filtered') }}</span><strong>{{ items.length }}</strong></article>
      <article><Wrench :size="17" /><span>{{ t('installed.projectSummary.inProgress') }}</span><strong>{{ currentCount }}</strong></article>
      <article><CalendarClock :size="17" /><span>{{ t('installed.projectSummary.completed') }}</span><strong>{{ completedNodes }}/{{ items.length * stageOrder.length }}</strong></article>
      <article class="warranty"><Check :size="17" /><span>{{ t('installed.projectSummary.warranty') }}</span><strong>{{ warrantyCount }}</strong></article>
    </div>

    <div class="cycle-table-shell">
      <div class="cycle-table">
        <header class="cycle-table-header">
          <span>{{ t('installed.projectHeader.device') }}</span>
          <span>{{ t('installed.projectHeader.customerSite') }}</span>
          <span>{{ t('installed.projectHeader.stageOwner') }}</span>
          <span>{{ t('installed.projectHeader.keyDate') }}</span>
          <div class="timeline-header">
            <strong>{{ t('installed.projectHeader.cycle') }}</strong>
            <div>
               <span v-for="stage in stageOrder" :key="stage" data-installed-tool-stage-header>{{ stageLabel(stage) }}</span>
            </div>
          </div>
        </header>

        <div class="cycle-table-body">
          <button
            v-for="item in items"
            :key="item.id"
            type="button"
            class="cycle-row"
            :class="{ selected: item.id === selectedId }"
            data-installed-tool-project-row
            :data-installed-tool-project-id="item.id"
            @click="emit('select', item)"
          >
            <span class="tool-cell">
              <strong>{{ item.model }} · {{ item.serial }}</strong>
               <small>{{ item.id }} · {{ statusLabel(item.status) }}</small>
            </span>
            <span class="customer-cell">
              <strong>{{ item.account }}</strong>
              <small>{{ item.site }} · {{ systemValueLabel(item.location, locale) }}</small>
            </span>
            <span class="owner-cell">{{ personnelDisplayName(item.engineerOwner) || t('installed.confirmPending') }}</span>
            <span class="date-cell">
               <strong>{{ stageLabel(keyMilestone(item)?.label ?? 'Completed') }}</strong>
              <small>{{ systemValueLabel(keyMilestone(item)?.date, locale) || '—' }}</small>
            </span>
            <span class="timeline-cell">
              <span class="timeline-track">
                <span
                  v-for="(stage, index) in stageOrder"
                  :key="stage"
                  class="milestone"
                  :class="`is-${milestoneState(item, stage).toLowerCase()}`"
                  :data-state="milestoneState(item, stage)"
                  data-installed-tool-milestone
                >
                  <span class="node"><Check v-if="milestoneState(item, stage) === 'Done'" :size="12" /><template v-else>{{ index + 1 }}</template></span>
                  <time>{{ systemValueLabel(milestoneFor(item, stage)?.date, locale) || '—' }}</time>
                </span>
              </span>
            </span>
          </button>
          <p v-if="!items.length" class="empty-state">{{ t('installed.noDevices') }}</p>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.project-cycle-board{display:grid;gap:14px;min-width:0}.board-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.board-summary article{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:9px;padding:13px 15px;color:#6f747b;background:#fff;border:1px solid #DCE3EE;border-radius:7px}.board-summary article>span{font-size:11px}.board-summary article>strong{color:#25292f;font-size:20px}.board-summary .warranty{color:#267848;background:#f5fbf7;border-color:#c5e1d0}.board-summary .warranty>strong{color:#267848}.cycle-table-shell{min-width:0;overflow-x:auto;background:#fff;border:1px solid #d9d6d0;border-radius:8px;box-shadow:0 6px 20px rgba(44,48,54,.04)}.cycle-table{min-width:1160px}.cycle-table-header,.cycle-row{display:grid;grid-template-columns:230px 190px 130px 110px minmax(500px,1fr)}.cycle-table-header{min-height:76px;align-items:stretch;color:#666c72;background:#f5f4f1;border-bottom:1px solid #d8d5cf}.cycle-table-header>span{display:flex;align-items:center;padding:0 14px;border-right:1px solid #DCE3EE;font-size:10px;font-weight:800;letter-spacing:.04em}.timeline-header{display:grid;grid-template-rows:30px 1fr;min-width:0}.timeline-header>strong{display:flex;align-items:center;justify-content:center;border-bottom:1px solid #DCE3EE;font-size:10px;letter-spacing:.04em}.timeline-header>div{display:grid;grid-template-columns:repeat(5,minmax(100px,1fr));align-items:center}.timeline-header span{padding:0 4px;color:#73787e;font-size:9px;font-weight:750;text-align:center}.cycle-table-body{display:grid}.cycle-row{position:relative;width:100%;min-height:86px;align-items:stretch;padding:0;color:#555b61;background:#fff;border:0;border-top:1px solid #ebe8e3;font:inherit;text-align:left;cursor:pointer;transition:background-color .18s ease,box-shadow .18s ease}.cycle-row:first-child{border-top:0}.cycle-row:hover{z-index:1;background:#fffaf6;box-shadow:inset 0 0 0 1px #eab98f}.cycle-row.selected{background:#fff8f1;box-shadow:inset 3px 0 #ef7217}.cycle-row:focus-visible{z-index:2;outline:2px solid #d76313;outline-offset:-2px}.tool-cell,.customer-cell,.owner-cell,.date-cell{display:flex;min-width:0;justify-content:center;flex-direction:column;gap:4px;padding:12px 14px;border-right:1px solid #EDF1F7}.tool-cell strong,.customer-cell strong,.date-cell strong{overflow:hidden;color:#282d33;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.tool-cell small,.customer-cell small,.date-cell small{overflow:hidden;color:#7b8086;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.owner-cell{color:#444a50;font-size:10px;font-weight:700}.timeline-cell{display:flex;min-width:0;align-items:center;padding:12px 16px}.timeline-track{position:relative;display:grid;width:100%;grid-template-columns:repeat(5,minmax(96px,1fr))}.milestone{position:relative;display:grid;justify-items:center;gap:6px;color:#9b9fa4}.milestone::before,.milestone::after{position:absolute;top:14px;height:2px;background:#d9dddf;content:""}.milestone::before{right:50%;left:0}.milestone::after{right:0;left:50%}.milestone:first-child::before,.milestone:last-child::after{display:none}.node{z-index:1;display:grid;width:28px;height:28px;place-items:center;background:#f2f3f3;border:2px solid #cfd3d5;border-radius:50%;font-size:9px;font-weight:850}.milestone time{font-size:8px;white-space:nowrap}.milestone.is-done{color:#2b8b53}.milestone.is-done::before,.milestone.is-done::after{background:#79c39a}.milestone.is-done .node{color:#fff;background:#35a466;border-color:#35a466}.milestone.is-current{color:#b45713;font-weight:800}.milestone.is-current::before{background:#79c39a}.milestone.is-current .node{color:#fff;background:#ef7217;border-color:#ef7217;box-shadow:0 0 0 4px #fff0e5}.empty-state{margin:0;padding:46px 16px;color:#8b9095;font-size:11px;text-align:center}@media(max-width:900px){.board-summary{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:620px){.board-summary{grid-template-columns:1fr}.cycle-table{min-width:1050px}.cycle-table-header,.cycle-row{grid-template-columns:210px 170px 120px 100px minmax(450px,1fr)}}
</style>
