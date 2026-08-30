<script setup lang="ts">
import { personnelDisplayName } from '@/demo/personnel'
import { CheckCircle2, Clock3 } from '@lucide/vue'
import type { ActionDto } from '@/types/crm'
import { formatDisplayDate, shanghaiDate } from '@/domain/time'

defineProps<{ actions: ActionDto[] }>()
const today = shanghaiDate()
const overdue = (due: string) => due < today
</script>

<template>
  <div class="action-list">
    <article v-for="action in actions" :key="action.id">
      <span class="action-check"><CheckCircle2 :size="16" /></span>
      <div><strong>{{ action.title }}</strong><small>{{ personnelDisplayName(action.owner) }} · 来源 {{ action.sourceType }}</small></div>
      <span class="due" :class="{ overdue: overdue(action.due) }"><Clock3 :size="11" />{{ formatDisplayDate(action.due) }}</span>
    </article>
  </div>
</template>

<style scoped>
.action-list { display: grid; }
article { display: grid; grid-template-columns: 29px minmax(0,1fr) auto; align-items: center; gap: 9px; min-height: 57px; border-bottom: 1px solid var(--crm-line); }
article:last-child { border-bottom: 0; }
.action-check { display: grid; width: 29px; height: 29px; place-items: center; color: var(--crm-teal); background: var(--crm-teal-soft); border-radius: 8px; }
article div { display: grid; min-width: 0; gap: 4px; }
strong { overflow: hidden; color: var(--crm-text); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
small { color: var(--crm-text-muted); font-size: 9px; }
.due { display: flex; align-items: center; gap: 3px; color: var(--crm-text-muted); font-size: 9px; }
.due.overdue { color: var(--crm-danger); font-weight: 700; }
</style>
