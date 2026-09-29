<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import type { CreateTestRunInput, TestRunDto } from '@/types/crm'
import { isIsoDate } from '@/domain/evaluations'
import ModalShell from '@/design-system/ModalShell.vue'
import { useI18n, useLocaleMessage, localeMessage } from '@/i18n'
import type { TestRunAction } from './test-run-actions'

const props = defineProps<{ run: TestRunDto; action: TestRunAction; busy: boolean; submitError: string; requestId: string; conflict: boolean }>()
const emit = defineEmits<{ close: []; save: [input: CreateTestRunInput]; 'cancel-run': [reason: string]; reload: [] }>()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const title = computed(() => ({ reschedule: copy('Reschedule test run', '测试改期'), complete: copy('Complete test run', '完成测试'), cancel: copy('Cancel test run', '取消测试') })[props.action])
// Frappe persists blank Float fields as zero. Planned runs have no confirmed
// results, so require an explicit entry even when the API returns those defaults.
const form = reactive({ date: props.run.date, capture: '' as number | '', falsePositive: '' as number | '', wph: '' as number | '', summary: props.run.summary })
const reason = ref('')
const validationError = useLocaleMessage()
function close() { if (!props.busy) emit('close') }
function submit() {
  if (props.busy || props.conflict) return
  validationError.value = ''
  if (props.action === 'cancel') {
    if (!reason.value.trim() || reason.value.trim().length > 500) {
      validationError.value = localeMessage('Enter a cancellation reason (1–500 characters).', '请填写取消原因（1–500 字）。')
      return
    }
    emit('cancel-run', reason.value.trim())
    return
  }
  if (!isIsoDate(form.date)) {
    validationError.value = localeMessage('Enter a valid test date.', '请填写有效测试日期。')
    return
  }
  if (props.action === 'complete') {
    const metrics = [form.capture, form.falsePositive, form.wph]
    if (metrics.some(value => value === '' || !Number.isFinite(Number(value)) || Number(value) < 0)
      || Number(form.capture) > 100 || Number(form.falsePositive) > 100 || !form.summary.trim()) {
      validationError.value = localeMessage('Enter all three results and a summary. Percentages must be 0–100; WPH cannot be negative.', '请填写三项结果和摘要。百分比为 0–100，WPH 不能为负数。')
      return
    }
  }
  // The existing API accepts the complete record. Rescheduling must not complete it.
  emit('save', {
    date: form.date, lot: props.run.lot, wafers: props.run.wafers,
    capture: props.action === 'complete' ? Number(form.capture) : null,
    falsePositive: props.action === 'complete' ? Number(form.falsePositive) : null,
    wph: props.action === 'complete' ? Number(form.wph) : null,
    summary: props.action === 'complete' ? form.summary.trim() : props.run.summary,
  })
}
</script>

<template>
  <ModalShell :title="title" :eyebrow="run.lot" :busy="busy" :submit-disabled="conflict" :submit-label="title" @close="close" @submit="submit">
    <fieldset class="run-form" :disabled="busy">
      <p>{{ copy(`Round ${run.round ?? 1}`, `第 ${run.round ?? 1} 轮`) }} · {{ run.id }}</p>
      <label v-if="action === 'cancel'">{{ copy('Cancellation reason', '取消原因') }}<textarea v-model="reason" data-run-reason required maxlength="500" /></label>
      <template v-else>
        <label>{{ copy('Test date', '测试日期') }}<input v-model="form.date" data-run-date type="date" required /></label>
        <template v-if="action === 'complete'">
          <label>{{ copy('Capture (%)', '检出率（%）') }}<input v-model.number="form.capture" data-run-capture type="number" min="0" max="100" step="any" required /></label>
          <label>{{ copy('False positives (%)', '误报率（%）') }}<input v-model.number="form.falsePositive" data-run-false-positive type="number" min="0" max="100" step="any" required /></label>
          <label>WPH<input v-model.number="form.wph" data-run-wph type="number" min="0" step="any" required /></label>
          <label>{{ copy('Results summary', '结果摘要') }}<textarea v-model="form.summary" data-run-summary required /></label>
        </template>
      </template>
      <p v-if="validationError" role="alert" class="run-error">{{ validationError }}</p>
      <div v-if="submitError" role="alert" class="run-error"><p>{{ submitError }}</p><small v-if="requestId">Request ID · {{ requestId }}</small></div>
      <div v-if="conflict" class="conflict-recovery">
        <p>{{ copy('This record changed. Your draft is kept. Reload the latest version to discard this draft and try again.', '记录已被修改，当前输入已保留。重新载入最新版本会放弃本次输入，然后可以重试。') }}</p>
        <button type="button" class="secondary-button" data-run-reload @click="emit('reload')">{{ copy('Reload and discard draft', '重新载入并放弃本次输入') }}</button>
      </div>
    </fieldset>
  </ModalShell>
</template>

<style scoped>
.run-form{display:grid;gap:12px;min-width:0;margin:0;padding:0;border:0}.run-form label{display:grid;gap:6px;font-size:12px;color:var(--crm-text-muted)}.run-form input,.run-form textarea{min-width:0;padding:9px;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.run-form textarea{min-height:80px}.run-form p{margin:0;font-size:12px;overflow-wrap:anywhere}.run-error{color:var(--crm-danger)}.run-error p{margin-bottom:6px}.conflict-recovery{display:grid;gap:10px}
</style>
