<script setup lang="ts">
import { AlertTriangle, RefreshCw } from '@lucide/vue'

defineProps<{ message: string; requestId?: string }>()
defineEmits<{ refresh: [] }>()
</script>

<template>
  <div class="data-notice" role="status">
    <AlertTriangle :size="15" />
    <span><strong>PARTIAL / STALE</strong>{{ message }}</span>
    <small v-if="requestId">{{ requestId }}</small>
    <button type="button" @click="$emit('refresh')"><RefreshCw :size="13" />立即刷新</button>
  </div>
</template>

<style scoped>
.data-notice { display: flex; align-items: center; gap: 9px; margin-bottom: 12px; padding: 9px 12px; color: #7d611f; background: var(--crm-warning-soft); border: 1px solid #ecd99d; border-radius: 10px; font-size: 10px; }
.data-notice span { display: flex; min-width: 0; flex: 1; gap: 8px; }
.data-notice strong { letter-spacing: .06em; }
.data-notice small { color: #9a7b35; font-family: ui-monospace, monospace; font-size: 8px; }
.data-notice button { display: flex; align-items: center; gap: 5px; padding: 0; color: inherit; background: transparent; border: 0; font-size: 9px; font-weight: 700; cursor: pointer; }
@media (max-width: 620px) { .data-notice { align-items: flex-start; flex-wrap: wrap; } .data-notice span { width: calc(100% - 24px); flex-direction: column; gap: 2px; } .data-notice small { margin-left: 24px; } .data-notice button { margin-left: auto; } }
</style>
