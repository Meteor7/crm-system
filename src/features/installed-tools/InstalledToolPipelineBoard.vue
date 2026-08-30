<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import PipelineBoard from '@/design-system/PipelineBoard.vue'
import PipelineStageColumn from '@/design-system/PipelineStageColumn.vue'
import PipelineCard from '@/design-system/PipelineCard.vue'
import type { InstalledToolDto } from '@/types/workspaces'
import { personnelDisplayName } from '@/demo/personnel'
const props=withDefaults(defineProps<{items:InstalledToolDto[];selectedId?:string}>(),{selectedId:''});const emit=defineEmits<{select:[item:InstalledToolDto]}>()
const order=['FAT','Shipment','Installation','SAT','Warranty'] as const
function current(item:InstalledToolDto){return item.milestones.find(m=>m.state==='Current')?.label??item.milestones.find(m=>m.state==='Waiting')?.label??order.at(-1)!}
function itemsFor(label:string){return props.items.filter(item=>current(item)===label)} const limits=ref(Object.fromEntries(order.map(label=>[label,4])) as Record<(typeof order)[number],number>);function visibleItems(label:(typeof order)[number]){return itemsFor(label).slice(0,limits.value[label])}function loadMore(label:(typeof order)[number]){limits.value[label]+=4}watch(()=>props.items,()=>{order.forEach(label=>{limits.value[label]=4})})
const stages=computed(()=>order.map(label=>({key:label,label,count:itemsFor(label).length})))
function progress(item:InstalledToolDto){return `${item.milestones.filter(m=>m.state==='Done').length}/${order.length} 已完成`}
</script>
<template><section class="installed-board" data-installed-tool-pipeline><PipelineBoard :stages="stages" :columns="5"><template #stage="{stage}"><PipelineStageColumn :label="stage.label" :count="stage.count" empty-copy="当前阶段暂无设备"><PipelineCard v-for="item in visibleItems(stage.key)" :key="item.id" :selected="item.id===selectedId" :tone="item.milestones.find(m=>m.label===stage.key)?.state==='Current'?'current':'healthy'" :title="item.account" :summary="`${item.model} · ${item.serial}`" :meta="`Engineer ${personnelDisplayName(item.engineerOwner)||'待确认'}`" :reason="progress(item)" :data-installed-tool-id="item.id" @open="emit('select',item)" /><button v-if="visibleItems(stage.key).length < itemsFor(stage.key).length" type="button" class="load-more" :data-load-more-stage="stage.key" @click="loadMore(stage.key)">加载更多</button></PipelineStageColumn></template></PipelineBoard></section></template>
<style scoped>.installed-board{min-width:0;overflow:hidden;padding:var(--crm-space-6);background:var(--crm-surface-raised);border:1px solid var(--crm-line);border-radius:var(--crm-radius-md)}.load-more{width:100%;min-height:32px;color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line);border-radius:6px;font-size:10px;font-weight:750;cursor:pointer}</style>
