<script setup lang="ts">
import { reactive, ref } from 'vue'
import type { CreateTestRunInput, EvaluationDto } from '@/types/crm'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import { shanghaiDate } from '@/domain/time'

const props = defineProps<{ evaluation: EvaluationDto; busy?: boolean }>()
const emit = defineEmits<{ close: []; submit: [input: CreateTestRunInput] }>()
const form = reactive({ date: shanghaiDate(), lot: '', wafers: 1, capture: '' as number | '', falsePositive: '' as number | '', wph: '' as number | '', summary: '' })
const validationError = ref('')
function submit() {
  const metrics = [form.capture, form.falsePositive, form.wph]
  const metricCount = metrics.filter((value) => value !== '').length
  if (metricCount > 0 && metricCount < metrics.length) {
    validationError.value = '填写测试指标时，缺陷捕获率、误报率和 Throughput WPH 必须完整填写'
    return
  }
  if (metricCount === metrics.length && !form.summary.trim()) {
    validationError.value = '完成 Test Run 时必须填写结果摘要'
    return
  }
  validationError.value = ''
  emit('submit', { date: form.date, lot: form.lot.trim(), wafers: Number(form.wafers), capture: form.capture === '' ? null : Number(form.capture), falsePositive: form.falsePositive === '' ? null : Number(form.falsePositive), wph: form.wph === '' ? null : Number(form.wph), summary: form.summary.trim() })
}
</script>

<template>
  <ModalShell title="新增 Wafer Test Run" eyebrow="WAFER TEST" :busy="busy" @close="$emit('close')" @submit="submit"><div class="run-grid"><label><span>测试日期<RequiredMark /></span><input v-model="form.date" type="date" required /></label><label><span>Wafer Lot<RequiredMark /></span><input v-model="form.lot" aria-label="Wafer Lot" required /></label><label><span>Wafer 数量<RequiredMark /></span><input v-model.number="form.wafers" aria-label="Wafer 数量" type="number" min="1" required /></label><label>缺陷捕获率 %<input v-model.number="form.capture" aria-label="缺陷捕获率" type="number" min="0" max="100" step=".1" /></label><label>误报率 %<input v-model.number="form.falsePositive" aria-label="误报率" type="number" min="0" max="100" step=".1" /></label><label>Throughput WPH<input v-model.number="form.wph" aria-label="Throughput WPH" type="number" min="0" step=".1" /></label><label class="full">结果摘要<textarea v-model="form.summary" aria-label="结果摘要" /></label><p v-if="validationError" class="validation-error full" role="alert">{{ validationError }}</p></div></ModalShell>
</template>

<style scoped>
.run-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.run-grid label{display:grid;gap:6px;color:var(--crm-text-muted);font-size:9px;font-weight:700}.run-grid .full{grid-column:1/-1}.run-grid input,.run-grid textarea{min-height:36px;padding:8px 10px;border:1px solid var(--crm-line);border-radius:8px;outline:0}.run-grid textarea{min-height:76px}.validation-error{margin:0;color:var(--crm-danger);font-size:10px}@media(max-width:540px){.run-grid{grid-template-columns:1fr}.run-grid .full{grid-column:auto}}
</style>
