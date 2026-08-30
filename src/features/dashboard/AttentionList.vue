<script setup lang="ts">
import { CalendarClock, ChevronRight } from '@lucide/vue'
import type { AccountSummaryDto } from '@/types/crm'
import StatusBadge from '@/design-system/StatusBadge.vue'

defineProps<{ accounts: AccountSummaryDto[] }>()
const emit = defineEmits<{ select: [id: string] }>()
const money = (value: number) => `¥${(value / 10000).toFixed(0)}万`
</script>

<template>
  <div class="attention-list">
    <button v-for="account in accounts" :key="account.id" type="button" @click="emit('select', account.id)">
      <span class="account-monogram">{{ account.shortName.slice(0, 2) }}</span>
      <span class="account-copy"><strong>{{ account.name }}</strong><small><CalendarClock :size="12" />{{ account.nextAction }} · {{ account.nextActionDue.slice(5) }}</small></span>
      <span class="account-metrics"><b class="tabular">{{ money(account.pipelineAmount) }}</b><StatusBadge :label="account.risk" :tone="account.risk === '高风险' ? 'danger' : 'warning'" /></span>
      <ChevronRight :size="16" />
    </button>
  </div>
</template>

<style scoped>
.attention-list { display: grid; }
button { display: grid; grid-template-columns: 36px minmax(0,1fr) auto 18px; align-items: center; gap: 11px; min-height: 66px; padding: 10px 0; color: inherit; background: transparent; border: 0; border-bottom: 1px solid var(--crm-line); cursor: pointer; text-align: left; }
button:last-child { border-bottom: 0; }
button:hover strong { color: var(--crm-teal); }
.account-monogram { display: grid; width: 36px; height: 36px; place-items: center; color: var(--crm-navy); background: var(--crm-surface-muted); border: 1px solid var(--crm-line); border-radius: 10px; font-size: 9px; font-weight: 800; }
.account-copy { display: grid; min-width: 0; gap: 5px; }
.account-copy strong { overflow: hidden; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.account-copy small { display: flex; align-items: center; gap: 4px; overflow: hidden; color: var(--crm-text-muted); font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.account-metrics { display: grid; justify-items: end; gap: 5px; }
.account-metrics b { color: var(--crm-navy); font-size: 11px; }
button > svg { color: #a3b0b2; }
</style>
