<script setup lang="ts">
import { CalendarClock } from '@lucide/vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import { personnelDisplayName } from '@/demo/personnel'
import {
  opportunityReachedAtBasisLabel,
  opportunityStageHistoryEventLabel,
  opportunityStageHistoryEventTone,
  opportunityStageLabel,
  showsSeparateReachedAt,
} from '@/domain/opportunity-stages'
import { formatDisplayDate, formatDisplayDateTime } from '@/domain/time'
import { useI18n } from '@/i18n'
import type { OpportunityStageHistoryDto } from '@/types/workspaces'

defineProps<{ history: OpportunityStageHistoryDto[] }>()
const { t, locale } = useI18n()

// A declared date is a calendar day, so it is shown without a time of day.
function reachedAtText(row: OpportunityStageHistoryDto) {
  return row.reachedAtBasis === 'declared' ? formatDisplayDate(row.reachedAt) : formatDisplayDateTime(row.reachedAt)
}

function reachedAtSummary(row: OpportunityStageHistoryDto) {
  const label = t('detail.reachedAt')
  const basis = opportunityReachedAtBasisLabel(row.reachedAtBasis, locale.value)
  return row.reachedAt ? `${label} ${reachedAtText(row)} · ${basis}` : `${label} · ${basis}`
}

function moveText(row: OpportunityStageHistoryDto) {
  const to = opportunityStageLabel(row.to, locale.value)
  return row.from ? `${opportunityStageLabel(row.from, locale.value)} → ${to}` : to
}
</script>

<template>
  <section class="stage-history-card" data-testid="opportunity-stage-timeline">
    <header><CalendarClock :size="16" /><h2>{{ t('detail.stageHistory') }}</h2><span>{{ history.length }}</span></header>
    <ol v-if="history.length" class="stage-history-list">
      <li v-for="row in history" :key="row.id" :data-stage-history-id="row.id" :data-stage-history-event="row.event">
        <div class="stage-history-move"><strong>{{ moveText(row) }}</strong><StatusBadge :label="opportunityStageHistoryEventLabel(row.event, locale)" :tone="opportunityStageHistoryEventTone(row.event)" /></div>
        <p v-if="row.reason" class="stage-history-reason">{{ row.reason }}</p>
        <span>{{ personnelDisplayName(row.actor) }} · <time :datetime="row.recordedAt">{{ formatDisplayDateTime(row.recordedAt) }}</time></span>
        <small v-if="showsSeparateReachedAt(row)" data-stage-history-reached>{{ reachedAtSummary(row) }}</small>
      </li>
    </ol>
    <p v-else class="empty-copy">{{ t('detail.noStageHistory') }}</p>
  </section>
</template>

<style scoped>
.stage-history-card{overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:12px;box-shadow:0 8px 24px rgba(31,35,41,.035)}
.stage-history-card>header{display:flex;min-height:50px;align-items:center;gap:8px;padding:0 14px;color:var(--crm-teal);background:#faf9f7;border-bottom:1px solid var(--crm-line)}
.stage-history-card>header h2{margin:0;color:var(--crm-navy);font-size:12px}.stage-history-card>header>span{margin-left:auto;color:var(--crm-text-muted);font-size:9px}
.stage-history-list{display:grid;margin:0;padding:2px 14px 10px;list-style:none}
.stage-history-list li{display:grid;gap:4px;padding:10px 0;border-bottom:1px solid var(--crm-line)}.stage-history-list li:last-child{border-bottom:0}
.stage-history-move{display:flex;align-items:center;justify-content:space-between;gap:8px}.stage-history-move strong{color:var(--crm-text);font-size:10px}
.stage-history-reason{margin:0;color:var(--crm-text);font-size:9px;line-height:1.5}
.stage-history-list li>span,.stage-history-list small{color:var(--crm-text-muted);font-size:8px}
.empty-copy{margin:0;padding:22px;color:var(--crm-text-muted);font-size:9px;text-align:center}
</style>
