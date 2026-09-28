<script setup lang="ts">
import { computed } from 'vue'
import { Check } from '@lucide/vue'
import { opportunityMilestoneSegments, opportunityStageLabel } from '@/domain/opportunity-stages'
import { useI18n } from '@/i18n'
import type { StrategyOpportunityDto } from '@/types/workspaces'

const props = defineProps<{ opportunity: Pick<StrategyOpportunityDto, 'stage' | 'lostAtStage' | 'stageHistory'> }>()
const { t, locale } = useI18n()
const segments = computed(() => opportunityMilestoneSegments(props.opportunity))
</script>

<template>
  <ol class="milestone-bar" :aria-label="t('detail.stagePath')">
    <li
      v-for="(segment, index) in segments"
      :key="segment.stage"
      :data-stage-path="segment.stage"
      :data-stage-state="segment.state"
      :class="[`is-${segment.state}`, { 'is-optional': segment.optional }]"
      :aria-current="segment.state === 'current' ? 'step' : undefined"
    >
      <span class="milestone-index"><Check v-if="segment.state === 'complete'" :size="12" /><template v-else>{{ index + 1 }}</template></span>
      <span class="milestone-copy">
        <strong>{{ opportunityStageLabel(segment.stage, locale) }}</strong>
        <span class="milestone-markers">
          <small v-if="segment.optional" data-stage-marker="optional">{{ t('detail.optionalStage') }}</small>
          <small v-if="segment.state === 'skipped'" data-stage-marker="skipped">{{ t('detail.skippedStage') }}</small>
          <small v-if="segment.state === 'lost'" data-stage-marker="lost">{{ t('detail.lostHere') }}</small>
        </span>
      </span>
    </li>
  </ol>
</template>

<style scoped>
.milestone-bar{display:grid;min-width:720px;grid-template-columns:repeat(7,minmax(94px,1fr));gap:6px;margin:0;padding:0;list-style:none}
.milestone-bar li{display:flex;min-height:44px;box-sizing:border-box;align-items:center;gap:7px;padding:6px 9px;color:var(--crm-text-muted);background:#eeeae4;border:1px solid transparent;border-radius:9px;font-size:9px;font-weight:800}
.milestone-index{display:grid;width:20px;height:20px;flex:0 0 auto;place-items:center;color:inherit;background:rgba(255,255,255,.75);border-radius:50%;font-size:8px}
.milestone-copy{display:grid;min-width:0;gap:2px}.milestone-copy strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.milestone-markers{display:flex;flex-wrap:wrap;gap:4px}.milestone-markers small{font-size:7px;font-weight:700}
.milestone-bar li.is-complete{color:#24633f;background:#dff3e8}
.milestone-bar li.is-current{color:var(--crm-brand-ink);background:var(--crm-brand)}
.milestone-bar li.is-optional{background:#f7f5f1;border:1px dashed #b9b2a8}
.milestone-bar li.is-optional.is-complete{background:#eef8f2;border-color:#8cc5a4}
.milestone-bar li.is-optional.is-current{background:var(--crm-brand);border-color:var(--crm-brand-ink)}
.milestone-bar li.is-skipped{color:#9a9489;background:repeating-linear-gradient(135deg,#f7f5f1 0 6px,#efebe4 6px 12px)}
.milestone-bar li.is-skipped strong{text-decoration:line-through}
.milestone-bar li.is-lost{color:var(--crm-danger);background:var(--crm-danger-soft);border:1px solid rgba(200,78,78,.4)}
</style>
