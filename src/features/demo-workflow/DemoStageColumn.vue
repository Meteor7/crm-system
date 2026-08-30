<script setup lang="ts">
import type { DemoLifecycleStage } from '@/types/crm'
import type { DemoWorkflowDto } from '@/types/workspaces'
import DemoPipelineCard from './DemoPipelineCard.vue'
import PipelineStageColumn from '@/design-system/PipelineStageColumn.vue'

defineProps<{ stage: DemoLifecycleStage; items: DemoWorkflowDto[] }>()
defineEmits<{ open: [item: DemoWorkflowDto] }>()
</script>

<template>
  <PipelineStageColumn class="stage-column" :label="stage" :count="items.length" empty-copy="当前阶段暂无 Demo" :data-demo-stage="stage" data-demo-stage-scroll>
    <DemoPipelineCard v-for="item in items" :key="item.id" :item="item" @open="$emit('open', $event)" />
  </PipelineStageColumn>
</template>
