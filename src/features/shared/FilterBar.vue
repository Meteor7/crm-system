<script setup lang="ts">
import { RotateCcw, SlidersHorizontal } from '@lucide/vue'

defineProps<{ resultLabel?: string }>()
defineEmits<{ reset: [] }>()
</script>

<template>
  <div class="filter-bar">
    <div class="filter-title"><SlidersHorizontal :size="15" /><span>筛选</span></div>
    <div class="filter-fields"><slot /></div>
    <span v-if="resultLabel" class="result-label">{{ resultLabel }}</span>
    <button class="reset-button" type="button" @click="$emit('reset')"><RotateCcw :size="13" />重置条件</button>
  </div>
</template>

<style scoped>
.filter-bar { display: flex; min-height: 58px; align-items: center; gap: 12px; margin-bottom: 14px; padding: 10px 13px; background: #fff; border: 1px solid var(--crm-line); border-radius: 12px; }
.filter-title { display: flex; align-items: center; gap: 6px; padding-right: 12px; color: var(--crm-text-muted); border-right: 1px solid var(--crm-line); font-size: 10px; font-weight: 700; }
.filter-fields { display: flex; min-width: 0; flex: 1; flex-wrap: wrap; gap: 8px; }
.result-label { color: var(--crm-text-muted); font-size: 9px; white-space: nowrap; }
.reset-button { display: flex; align-items: center; gap: 4px; padding: 7px 8px; color: var(--crm-teal); background: transparent; border: 0; border-radius: 7px; font-size: 10px; font-weight: 700; cursor: pointer; }
.reset-button:hover { background: var(--crm-teal-soft); }
@media (max-width: 700px) { .filter-bar { align-items: flex-start; flex-wrap: wrap; } .filter-title { width: 100%; border: 0; } .result-label { margin-left: auto; } }
</style>
