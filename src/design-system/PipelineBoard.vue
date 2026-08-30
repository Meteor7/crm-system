<script setup lang="ts" generic="T extends { key: string; label: string; count: number }">
defineProps<{ stages: T[]; columns?: number }>()
</script>

<template>
  <div class="pipeline-board" data-pipeline-board>
    <div class="track" :style="{ '--columns': columns || stages.length }">
      <div v-for="stage in stages" :key="stage.key" class="segment"><strong>{{ stage.label }}</strong><span>{{ stage.count }}</span></div>
    </div>
    <div class="columns" :style="{ '--columns': columns || stages.length }">
      <slot v-for="stage in stages" name="stage" :stage="stage" />
    </div>
  </div>
</template>

<style scoped>
.pipeline-board{min-width:100%;overflow-x:auto;padding-bottom:var(--crm-space-3)}
.track,.columns{display:grid;grid-template-columns:repeat(var(--columns),minmax(var(--crm-board-column-width),1fr));min-width:calc(var(--columns) * var(--crm-board-column-width))}
.track{height:var(--crm-board-track-height)}
.segment{display:flex;align-items:center;justify-content:center;gap:var(--crm-space-5);margin-left:calc(-1 * var(--crm-space-1) / 4);background:var(--crm-surface-raised);border:1px solid var(--crm-pipeline-accent);font-size:var(--crm-font-lg)}
.segment span{color:var(--crm-pipeline-accent);font-weight:800}
</style>
