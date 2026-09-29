<script setup lang="ts">
import type { EvaluationDto, TestRunDto } from '@/types/crm'
import { useI18n } from '@/i18n'
import { canManageTestRun, type TestRunAction } from './test-run-actions'

defineProps<{ evaluation: EvaluationDto; canWrite: boolean; busy: boolean }>()
const emit = defineEmits<{ action: [run: TestRunDto, action: TestRunAction] }>()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const statusLabel = (status: TestRunDto['status']) => ({
  Planned: copy('Planned', '计划中'), Completed: copy('Completed', '已完成'), Cancelled: copy('Cancelled', '已取消'),
})[status]
</script>

<template>
  <section class="test-runs" data-test-runs>
    <h3>{{ copy('Test Runs', '测试记录') }} · {{ evaluation.id }}</h3>
    <p v-if="!evaluation.runs.length">{{ copy('No test runs recorded.', '暂无测试记录。') }}</p>
    <article v-for="run in evaluation.runs" :key="run.id" :data-test-run="run.id">
      <div class="run-heading"><strong>{{ run.lot }}</strong><span>{{ statusLabel(run.status) }}</span></div>
      <p>{{ copy(`Round ${run.round ?? 1}`, `第 ${run.round ?? 1} 轮`) }} · {{ run.date }} · {{ copy(`${run.wafers} wafers`, `${run.wafers} 片晶圆`) }}</p>
      <p v-if="run.status === 'Completed'">{{ copy('Capture', '检出率') }} {{ run.capture }}% · {{ copy('False positives', '误报率') }} {{ run.falsePositive }}% · WPH {{ run.wph }}</p>
      <p v-if="run.summary" class="run-summary">{{ run.summary }}</p>
      <div v-if="canWrite && canManageTestRun(evaluation, run)" class="run-actions">
        <button type="button" class="secondary-button" data-run-action="reschedule" :disabled="busy" @click="emit('action', run, 'reschedule')">{{ copy('Reschedule', '改期') }}</button>
        <button type="button" class="primary-button" data-run-action="complete" :disabled="busy" @click="emit('action', run, 'complete')">{{ copy('Complete', '完成') }}</button>
        <button type="button" class="secondary-button" data-run-action="cancel" :disabled="busy" @click="emit('action', run, 'cancel')">{{ copy('Cancel run', '取消测试') }}</button>
      </div>
    </article>
  </section>
</template>

<style scoped>
.test-runs{padding:16px;background:#fff;border:1px solid var(--crm-line);border-radius:12px;min-width:0}.test-runs h3{margin:0 0 12px;font-size:14px;color:var(--crm-navy)}.test-runs article{padding:12px 0;border-top:1px solid var(--crm-line);overflow-wrap:anywhere}.run-heading{display:flex;justify-content:space-between;gap:12px;font-size:12px}.run-heading span{color:var(--crm-text-muted)}.test-runs p{margin:7px 0;font-size:12px;color:var(--crm-text-muted)}.run-summary{white-space:pre-wrap}.run-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
</style>
