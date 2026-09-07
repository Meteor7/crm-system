<script setup lang="ts">
import { useI18n } from '@/i18n'
const { t } = useI18n()
defineProps<{ label: string; count: number; emptyCopy?: string }>()
</script>
<template><section class="column" :aria-label="label"><slot /><p v-if="!count">{{ emptyCopy || t('common.emptyStage') }}</p></section></template>
<style scoped>
.column{display:grid;min-height:var(--crm-board-column-min-height);max-height:var(--crm-board-column-max-height);align-content:start;gap:var(--crm-space-5);padding:var(--crm-space-6) var(--crm-space-5) var(--crm-space-10);overflow-y:auto;overscroll-behavior:contain;border:1px solid var(--crm-line);border-top:0}
.column p{margin:var(--crm-space-3) 0;padding:var(--crm-space-9) var(--crm-space-3);color:var(--crm-text-muted);border:1px dashed var(--crm-line);border-radius:var(--crm-radius-sm);font-size:var(--crm-font-md);text-align:center}
</style>
