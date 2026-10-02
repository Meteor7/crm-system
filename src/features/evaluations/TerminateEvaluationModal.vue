<script setup lang="ts">
import { ref, watch } from 'vue'
import type { EvaluationDto } from '@/types/crm'
import ModalShell from '@/design-system/ModalShell.vue'
import { useI18n, useLocaleMessage } from '@/i18n'

// The server refuses a longer reason (terminate_evaluation).
const MAX_REASON_LENGTH = 1000

defineProps<{ evaluation: EvaluationDto; busy?: boolean; submitError?: string; requestId?: string }>()
const emit = defineEmits<{ close: []; submit: [input: { reason: string }] }>()
const reason = ref('')
const validationError = useLocaleMessage()
const { t, message } = useI18n()
// Editing answers the missing-reason prompt, which then gives way to any server refusal again.
watch(reason, () => { validationError.value = '' })
function submit() {
  const value = reason.value.trim()
  if (!value) {
    validationError.value = message('evaluations.terminateReasonRequired')
    return
  }
  validationError.value = ''
  emit('submit', { reason: value })
}
</script>

<template>
  <ModalShell
    :title="t('evaluations.terminateTitle')"
    eyebrow="DEMO TEST"
    :busy="busy"
    :submit-label="t('evaluations.terminateTitle')"
    @close="$emit('close')"
    @submit="submit"
  >
    <p class="terminate-target">{{ evaluation.id }} · {{ evaluation.title }}</p>
    <p class="terminate-hint">{{ t('evaluations.terminateHint') }}</p>
    <label class="terminate-field">
      {{ t('evaluations.terminateReason') }}
      <textarea v-model="reason" :aria-label="t('evaluations.terminateReason')" :maxlength="MAX_REASON_LENGTH" rows="4" />
    </label>
    <p v-if="validationError" class="validation-error" role="alert">{{ validationError }}</p>
    <div v-else-if="submitError" class="validation-error" role="alert">
      <span>{{ submitError }}</span>
      <small v-if="requestId">Request ID · {{ requestId }}</small>
    </div>
  </ModalShell>
</template>

<style scoped>
.terminate-target{margin:0 0 6px;color:var(--crm-navy);font-size:11px;font-weight:700;overflow-wrap:anywhere}.terminate-hint{margin:0 0 12px;color:var(--crm-text-muted);font-size:10px;line-height:1.6}.terminate-field{display:grid;gap:6px;color:var(--crm-text-muted);font-size:9px;font-weight:700}.terminate-field textarea{min-height:88px;padding:8px 10px;border:1px solid var(--crm-line);border-radius:8px;outline:0;font:inherit;font-size:11px;resize:vertical}.validation-error{display:grid;gap:4px;margin:10px 0 0;color:var(--crm-danger);font-size:10px}.validation-error small{opacity:.75}
</style>
