<script setup lang="ts">
import { useI18n } from '@/i18n'
import { metricText } from './presentation'
import type { ReviewDto, Metric } from './types'
defineProps<{ item: ReviewDto['activities'][number] }>()
defineEmits<{ details: [key: string] }>()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const money = (value: string) => `¥${(Number(value) / 1000000).toLocaleString(locale.value, { maximumFractionDigits: 2 })}M`
const amount = (metric: Metric) => metric.state === 'ready' && metric.value !== null ? money(String(metric.value)) : metricText(metric, locale.value)
</script>
<template>
  <div v-if="item.customerKinds" class="breakdown" data-visit-classification>
    <button v-for="row in item.customerKinds" :key="row.key" type="button" @click="$emit('details', `visits_${row.key}`)">
      <span>{{ { existing: copy('Existing', '老客户'), prospect: copy('Prospects', '潜在客户'), unclassified: copy('Unclassified', '未分类') }[row.key] }}</span><strong>{{ metricText(row.actual, locale) }}</strong>
      <small>{{ copy('Prior', '上期') }} {{ metricText(row.previous, locale) }} · Δ {{ row.delta === null ? '—' : `${row.delta > 0 ? '+' : ''}${row.delta}` }}</small>
    </button>
    <small>{{ copy('Classification saved when the visit was completed.', '按拜访完成时保存的客户分类。') }}</small>
  </div>
  <div v-if="item.quoteAmount" class="breakdown" data-quote-amount>
    <strong>{{ copy('First published value', '首次发布金额') }} {{ amount(item.quoteAmount.actual) }}</strong>
    <small>{{ copy('Prior', '上期') }} {{ amount(item.quoteAmount.previous) }} · Δ {{ item.quoteAmount.delta === null ? '—' : money(item.quoteAmount.delta) }}</small>
    <small v-if="item.quoteAmount.actual.state !== 'ready'" data-quote-period="current">{{ copy('Current recorded subtotal', '本期已记录金额小计') }} {{ money(item.quoteAmount.known) }} · {{ item.quoteAmount.missing }} {{ copy('quotes without a CNY snapshot; total may be incomplete', '份报价缺少人民币快照；总额可能不完整') }}</small>
    <small v-if="item.quoteAmount.previous.state !== 'ready'" data-quote-period="previous">{{ copy('Prior recorded subtotal', '上期已记录金额小计') }} {{ money(item.quoteAmount.previousKnown) }} · {{ item.quoteAmount.previousMissing }} {{ copy('quotes without a CNY snapshot; total may be incomplete', '份报价缺少人民币快照；总额可能不完整') }}</small>
  </div>
</template>
<style scoped>
.breakdown{display:grid;gap:5px;margin-top:12px;font-size:12px}.breakdown button{display:flex;flex-wrap:wrap;gap:7px;text-align:left;border:0;border-top:1px solid var(--crm-line);background:none;padding:6px 0;cursor:pointer}.breakdown button small{width:100%}.breakdown small{color:var(--crm-text-muted);font-size:11px;line-height:1.4}
</style>
