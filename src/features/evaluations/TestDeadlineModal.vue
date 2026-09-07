<script setup lang="ts">
import { ref } from 'vue'
import type { EvaluationDto } from '@/types/crm'
import { isIsoDate } from '@/domain/evaluations'
import ModalShell from '@/design-system/ModalShell.vue'
import { useI18n, useLocaleMessage } from '@/i18n'

const props = defineProps<{ evaluation: EvaluationDto; busy?: boolean }>()
const emit = defineEmits<{ close: []; submit: [input: { testRunDeadline: string }] }>()
const testRunDeadline = ref(props.evaluation.testRunDeadline)
const validationError = useLocaleMessage()
const { t, message } = useI18n()
function submit() {
  const value = testRunDeadline.value.trim()
  if (!isIsoDate(value)) {
    validationError.value = message('testRun.invalidDate')
    return
  }
  validationError.value = ''
  emit('submit', { testRunDeadline: value })
}
</script>

<template>
  <ModalShell :title="t('testRun.setDdl')" eyebrow="TEST PREPARATION" :busy="busy" @close="$emit('close')" @submit="submit">
    <label class="deadline-field">Test Run DDL<input v-model="testRunDeadline" aria-label="Test Run DDL" type="date" required /></label>
    <p v-if="validationError" class="validation-error" role="alert">{{ validationError }}</p>
  </ModalShell>
</template>

<style scoped>
.deadline-field{display:grid;gap:6px;color:var(--crm-text-muted);font-size:9px;font-weight:700}.deadline-field input{min-height:38px;padding:8px 10px;border:1px solid var(--crm-line);border-radius:8px;outline:0}.validation-error{margin:10px 0 0;color:var(--crm-danger);font-size:10px}
</style>
