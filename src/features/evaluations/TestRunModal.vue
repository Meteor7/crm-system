<script setup lang="ts">
import { reactive, ref } from 'vue'
import type { CreateTestRunInput, EvaluationDto } from '@/types/crm'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import { shanghaiDate } from '@/domain/time'
import { useI18n, useLocaleMessage } from '@/i18n'

const props = defineProps<{ evaluation: EvaluationDto; busy?: boolean }>()
const emit = defineEmits<{ close: []; submit: [input: CreateTestRunInput] }>()
const form = reactive({ date: shanghaiDate(), lot: '', wafers: 1, capture: '' as number | '', falsePositive: '' as number | '', wph: '' as number | '', summary: '' })
const validationError = useLocaleMessage()
const { locale, t, message } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
function submit() {
  const metrics = [form.capture, form.falsePositive, form.wph]
  const metricCount = metrics.filter((value) => value !== '').length
  if (metricCount > 0 && metricCount < metrics.length) {
    validationError.value = message('testRun.metricsRequired')
    return
  }
  if (metricCount === metrics.length && !form.summary.trim()) {
    validationError.value = message('testRun.summaryRequired')
    return
  }
  validationError.value = ''
  emit('submit', { date: form.date, lot: form.lot.trim(), wafers: Number(form.wafers), capture: form.capture === '' ? null : Number(form.capture), falsePositive: form.falsePositive === '' ? null : Number(form.falsePositive), wph: form.wph === '' ? null : Number(form.wph), summary: form.summary.trim() })
}
</script>

<template>
  <ModalShell :title="t('testRun.newTitle')" :eyebrow="copy('WAFER TEST', '晶圆测试')" :busy="busy" @close="$emit('close')" @submit="submit"><div class="run-grid"><label><span>{{ t('testRun.date') }}<RequiredMark /></span><input v-model="form.date" type="date" required /></label><label><span>{{ copy('Wafer Lot', '晶圆批次') }}<RequiredMark /></span><input v-model="form.lot" :aria-label="copy('Wafer Lot', '晶圆批次')" required /></label><label><span>{{ t('testRun.wafers') }}<RequiredMark /></span><input v-model.number="form.wafers" :aria-label="t('testRun.wafers')" type="number" min="1" required /></label><label>{{ t('testRun.capture') }} %<input v-model.number="form.capture" :aria-label="t('testRun.capture')" type="number" min="0" max="100" step=".1" /></label><label>{{ t('testRun.falsePositive') }} %<input v-model.number="form.falsePositive" :aria-label="t('testRun.falsePositive')" type="number" min="0" max="100" step=".1" /></label><label>{{ copy('Throughput WPH', '吞吐量 WPH') }}<input v-model.number="form.wph" :aria-label="copy('Throughput WPH', '吞吐量 WPH')" type="number" min="0" step=".1" /></label><label class="full">{{ t('testRun.summary') }}<textarea v-model="form.summary" :aria-label="t('testRun.summary')" /></label><p v-if="validationError" class="validation-error full" role="alert">{{ validationError }}</p></div></ModalShell>
</template>

<style scoped>
.run-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.run-grid label{display:grid;gap:6px;color:var(--crm-text-muted);font-size:9px;font-weight:700}.run-grid .full{grid-column:1/-1}.run-grid input,.run-grid textarea{min-height:36px;padding:8px 10px;border:1px solid var(--crm-line);border-radius:8px;outline:0}.run-grid textarea{min-height:76px}.validation-error{margin:0;color:var(--crm-danger);font-size:10px}@media(max-width:540px){.run-grid{grid-template-columns:1fr}.run-grid .full{grid-column:auto}}
</style>
