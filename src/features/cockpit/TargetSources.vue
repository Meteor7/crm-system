<script setup lang="ts">
import { useI18n } from '@/i18n'
import { metricText } from './presentation'
import type { TargetMetric } from './types'

defineProps<{ target: TargetMetric; name: (id: string) => string; currency?: boolean }>()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
</script>

<template>
  <details v-if="target.sources?.length" class="target-sources" data-target-sources>
    <summary>{{ copy('Target sources', '目标来源') }} · {{ target.sources.filter(row => row.state === 'ready').length }} / {{ target.sources.length }}</summary>
    <p>{{ target.scope === 'territory' ? copy('Leaf territory targets, each counted once. Missing regions leave the total incomplete.', '末级地域目标只计一次；有地域缺目标时总目标不完整。') : copy('Sum of targets for the listed salespeople. A missing target leaves the total incomplete.', '按以下销售的个人目标求和；有人缺目标时团队目标不完整。') }}</p>
    <ul><li v-for="row in target.sources" :key="row.member"><span>{{ name(row.member) }}<small v-if="row.assignable === false">{{ copy('Outside the active sales team; actuals retained. New targets cannot be assigned.', '当前有效销售团队之外：保留实际活动，无法分配新目标。') }}</small><small v-if="row.record?.period === 'weekly_default'">{{ copy('Weekly default from', '默认周目标生效于') }} {{ row.record.anchor }}</small></span><strong>{{ metricText(row, locale, currency) }}</strong></li></ul>
  </details>
</template>

<style scoped>
.target-sources{margin:8px 0;font-size:11px;line-height:1.5;color:var(--crm-text-muted)}summary{cursor:pointer;font-weight:600}.target-sources p{margin:6px 0}.target-sources ul{padding:0;margin:6px 0;list-style:none}.target-sources li{display:flex;justify-content:space-between;gap:14px;padding:4px 0;border-top:1px solid var(--crm-line)}.target-sources small{display:block;font-size:10px}.target-sources strong{white-space:nowrap;color:var(--crm-text)}
</style>
