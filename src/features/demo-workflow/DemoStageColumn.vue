<script setup lang="ts">
import type { DemoLifecycleStage } from '@/types/crm'
import type { DemoWorkflowDto } from '@/types/workspaces'
import DemoPipelineCard from './DemoPipelineCard.vue'
import PipelineStageColumn from '@/design-system/PipelineStageColumn.vue'
import { useI18n } from '@/i18n'

defineProps<{ stage: DemoLifecycleStage; items: DemoWorkflowDto[] }>()
defineEmits<{ open: [item: DemoWorkflowDto] }>()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
</script>

<template>
  <PipelineStageColumn class="stage-column" :label="copy(stage, ({ 'Sales Preparation': 'Sales 准备', 'Engineer Review': '工程评估', 'Manager Approval': '经理审批', 'Wafer Preparation': 'Wafer 准备', 'Test Preparation': '测试准备', 'Test Execution': '测试执行', 'Internal Review': '内部评审', 'Customer Review': '客户评审' } as Record<string, string>)[stage] || stage)" :count="items.length" :empty-copy="copy('No Demo records in this stage', '当前阶段暂无 Demo')" :data-demo-stage="stage" data-demo-stage-scroll>
    <DemoPipelineCard v-for="item in items" :key="item.id" :item="item" @open="$emit('open', $event)" />
  </PipelineStageColumn>
</template>
