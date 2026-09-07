<script setup lang="ts">
import type { DemoWorkflowDto } from '@/types/workspaces'
import { personnelDisplayName } from '@/demo/personnel'
import PipelineCard from '@/design-system/PipelineCard.vue'
import { useI18n } from '@/i18n'
import { demoHealthReason } from './demo-health-label'

defineProps<{ item: DemoWorkflowDto }>()
defineEmits<{ open: [item: DemoWorkflowDto] }>()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
</script>

<template>
  <PipelineCard
    class="pipeline-card"
    :tone="item.health?.level || 'healthy'" :title="item.account" :summary="`${item.id} · ${item.title}`" :meta="`${copy('Sales', '销售')} ${personnelDisplayName(item.salesOwner)} · ${copy('Engineer', '工程师')} ${personnelDisplayName(item.engineerOwner)}`" :reason="demoHealthReason(item.health, locale)"
    :data-demo-id="item.id"
    @click="$emit('open', item)"
  />
</template>
