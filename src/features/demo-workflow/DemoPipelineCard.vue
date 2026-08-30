<script setup lang="ts">
import type { DemoWorkflowDto } from '@/types/workspaces'
import { personnelDisplayName } from '@/demo/personnel'
import PipelineCard from '@/design-system/PipelineCard.vue'

defineProps<{ item: DemoWorkflowDto }>()
defineEmits<{ open: [item: DemoWorkflowDto] }>()
</script>

<template>
  <PipelineCard
    class="pipeline-card"
    :tone="item.health?.level || 'healthy'" :title="item.account" :summary="`${item.id} · ${item.title}`" :meta="`Sales ${personnelDisplayName(item.salesOwner)} · Engineer ${personnelDisplayName(item.engineerOwner)}`" :reason="item.health?.reason || '正常推进'"
    :data-demo-id="item.id"
    @click="$emit('open', item)"
  />
</template>
