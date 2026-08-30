<script setup lang="ts">
defineProps<{ stages: Array<{ label: string; state: 'Done' | 'Current' | 'Waiting' }> }>()
</script>

<template>
  <ol class="stage-rail" aria-label="流程阶段">
    <li v-for="stage in stages" :key="stage.label" :class="`is-${stage.state.toLowerCase()}`"><i /><span>{{ stage.label }}</span></li>
  </ol>
</template>
