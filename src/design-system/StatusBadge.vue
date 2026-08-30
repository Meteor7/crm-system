<script setup lang="ts">
import { computed } from 'vue'
import type { Tone } from '@/types/crm'

const props = withDefaults(defineProps<{ label: string; tone?: Tone; dot?: boolean }>(), { tone: 'neutral', dot: true })
const toneClass = computed(() => `tone-${props.tone}`)
</script>

<template><span class="status-badge" :class="toneClass"><i v-if="dot" />{{ label }}</span></template>

<style scoped>
.status-badge { display: inline-flex; align-items: center; gap: 5px; width: fit-content; padding: 4px 8px; color: var(--ink); background: var(--fill); border: 1px solid var(--border); border-radius: 999px; font-size: 10px; font-weight: 700; line-height: 1; white-space: nowrap; }
.status-badge i { width: 5px; height: 5px; background: currentColor; border-radius: 50%; }
.tone-neutral { --ink: #627276; --fill: #f3f5f5; --border: #e2e7e6; }
.tone-info { --ink: #176d75; --fill: #e8f5f4; --border: #cce8e5; }
.tone-positive { --ink: #5b6b16; --fill: #f1f6d8; --border: #dfe9a6; }
.tone-warning { --ink: #946817; --fill: #fff5df; --border: #f0dda9; }
.tone-danger { --ink: #a63c3c; --fill: #fff0ef; --border: #f2cfcc; }
</style>
