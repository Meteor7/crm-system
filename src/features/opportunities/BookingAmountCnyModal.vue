<script setup lang="ts">
import { computed, ref } from 'vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import { normalizeMoney } from '@/domain/money'
import { useI18n, useLocaleMessage } from '@/i18n'
import type { SetBookingAmountCnyInput } from '@/types/crm'

const props = defineProps<{
  /** The CNY amount already on the Booking, or ''; changing it needs a reason. */
  currentAmount?: string
  busy?: boolean
  error?: string
}>()
const emit = defineEmits<{ close: []; submit: [input: SetBookingAmountCnyInput] }>()
const { t, message } = useI18n()
const correcting = computed(() => Boolean(props.currentAmount))
const amountCny = ref(props.currentAmount ?? '')
const reason = ref('')
const validationError = useLocaleMessage()

function normalized(value: string) {
  try { return normalizeMoney(value.trim()) } catch { return '' }
}

function submit() {
  const value = normalized(amountCny.value)
  const note = reason.value.trim()
  if (!value || Number(value) <= 0) validationError.value = message('amountCny.invalid')
  else if (props.currentAmount && value === normalized(props.currentAmount)) validationError.value = message('amountCny.unchanged')
  else if (correcting.value && !note) validationError.value = message('amountCny.reasonRequired')
  else {
    validationError.value = ''
    emit('submit', note ? { amountCny: value, reason: note } : { amountCny: value })
  }
}
</script>

<template>
  <ModalShell :title="t('amountCny.title')" eyebrow="CNY AMOUNT" :busy="busy" :submit-label="t('amountCny.save')" @close="emit('close')" @submit="submit">
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <p class="modal-hint">{{ t('amountCny.hint') }}</p>
    <div class="amount-fields">
      <label><span>{{ t('amountCny.label') }}<RequiredMark /></span><input v-model="amountCny" :aria-label="t('amountCny.label')" type="text" inputmode="decimal" pattern="\d+(?:\.\d{1,2})?" required /></label>
      <label><span>{{ t('amountCny.reason') }}<RequiredMark :show="correcting" /></span><textarea v-model="reason" :aria-label="t('amountCny.reason')" :required="correcting" rows="3" /></label>
    </div>
    <p v-if="validationError" class="validation-error" role="alert" data-field-error="amountCny">{{ validationError }}</p>
  </ModalShell>
</template>

<style scoped>
.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:9px}
.modal-hint{margin:0 0 12px;color:var(--crm-text-muted);font-size:10px;line-height:1.6}
.amount-fields{display:grid;gap:12px}
.amount-fields label{display:grid;gap:6px;color:var(--crm-text-muted);font-size:9px;font-weight:700}
.amount-fields input,.amount-fields textarea{box-sizing:border-box;width:100%;min-height:38px;padding:8px 10px;border:1px solid var(--crm-line);border-radius:8px;outline:0;font:inherit}
.validation-error{margin:10px 0 0;color:var(--crm-danger);font-size:10px}
</style>
