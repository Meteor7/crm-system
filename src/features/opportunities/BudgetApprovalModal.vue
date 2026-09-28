<script setup lang="ts">
import { computed, ref } from 'vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import { isIsoDate } from '@/domain/evaluations'
import { shanghaiDate } from '@/domain/time'
import { useI18n, useLocaleMessage } from '@/i18n'
import type { ConfirmBudgetApprovedInput } from '@/types/workspaces'

const props = defineProps<{
  busy?: boolean
  error?: string
  /** The owner has not set a success probability yet; the server refuses the step without one. */
  levelMissing?: boolean
  /** Latest selectable date, YYYY-MM-DD; defaults to today in Shanghai. */
  today?: string
}>()
const emit = defineEmits<{ close: []; submit: [input: ConfirmBudgetApprovedInput] }>()
const { t, message } = useI18n()
// The customer's approval can be dated earlier than today, never later.
const latestDate = computed(() => props.today || shanghaiDate())
const approvedOn = ref(latestDate.value)
const validationError = useLocaleMessage()

function submit() {
  const value = approvedOn.value.trim()
  if (!isIsoDate(value)) {
    validationError.value = message('budgetApproval.invalidDate')
    return
  }
  if (value > latestDate.value) {
    validationError.value = message('budgetApproval.futureDate')
    return
  }
  validationError.value = ''
  emit('submit', { approvedOn: value })
}
</script>

<template>
  <ModalShell :title="t('budgetApproval.title')" eyebrow="CUSTOMER BUDGET" :busy="busy" :submit-disabled="levelMissing" :submit-label="t('budgetApproval.submit')" @close="emit('close')" @submit="submit">
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <p class="modal-hint">{{ t('budgetApproval.hint') }}</p>
    <p v-if="levelMissing" class="modal-warning" data-testid="level-required-hint">{{ t('detail.levelRequiredHint') }}</p>
    <label class="date-field"><span>{{ t('budgetApproval.date') }}<RequiredMark /></span><input v-model="approvedOn" :aria-label="t('budgetApproval.date')" type="date" :max="latestDate" required /></label>
    <p v-if="validationError" class="validation-error" role="alert" data-field-error="approvedOn">{{ validationError }}</p>
  </ModalShell>
</template>

<style scoped>
.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:9px}
.modal-hint{margin:0 0 12px;color:var(--crm-text-muted);font-size:10px;line-height:1.6}
.modal-warning{margin:0 0 12px;padding:9px 10px;color:#8a651d;background:var(--crm-warning-soft);border-radius:8px;font-size:9px;line-height:1.5}
.date-field{display:grid;gap:6px;color:var(--crm-text-muted);font-size:9px;font-weight:700}
.date-field input{min-height:38px;padding:8px 10px;border:1px solid var(--crm-line);border-radius:8px;outline:0;font:inherit}
.validation-error{margin:10px 0 0;color:var(--crm-danger);font-size:10px}
</style>
