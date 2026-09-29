<script setup lang="ts">
import { computed, ref } from 'vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import { isIsoDate } from '@/domain/evaluations'
import { shanghaiDate } from '@/domain/time'
import { useI18n, useLocaleMessage } from '@/i18n'
import type { SetActualPoDateInput } from '@/types/crm'

const props = defineProps<{
  /** The date already on the Booking; changing it needs a reason. */
  currentDate?: string
  busy?: boolean
  error?: string
  /** Latest selectable date, YYYY-MM-DD; defaults to today in Shanghai. */
  today?: string
}>()
const emit = defineEmits<{ close: []; submit: [input: SetActualPoDateInput] }>()
const { t, message } = useI18n()
const latestDate = computed(() => props.today || shanghaiDate())
const correcting = computed(() => Boolean(props.currentDate))
const actualPoDate = ref(props.currentDate ?? '')
const reason = ref('')
const validationError = useLocaleMessage()

function submit() {
  const value = actualPoDate.value.trim()
  const note = reason.value.trim()
  if (!isIsoDate(value)) validationError.value = message('actualPoDate.invalidDate')
  else if (value > latestDate.value) validationError.value = message('actualPoDate.futureDate')
  else if (value === (props.currentDate ?? '')) validationError.value = message('actualPoDate.unchanged')
  else if (correcting.value && !note) validationError.value = message('actualPoDate.reasonRequired')
  else {
    validationError.value = ''
    emit('submit', note ? { actualPoDate: value, reason: note } : { actualPoDate: value })
  }
}
</script>

<template>
  <ModalShell :title="t('actualPoDate.title')" eyebrow="ACTUAL PO DATE" :busy="busy" :submit-label="t('actualPoDate.save')" @close="emit('close')" @submit="submit">
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <p class="modal-hint">{{ t('actualPoDate.hint') }}</p>
    <div class="po-date-fields">
      <label><span>{{ t('actualPoDate.label') }}<RequiredMark /></span><input v-model="actualPoDate" :aria-label="t('actualPoDate.label')" type="date" :max="latestDate" required /></label>
      <label><span>{{ t('actualPoDate.reason') }}<RequiredMark :show="correcting" /></span><textarea v-model="reason" :aria-label="t('actualPoDate.reason')" :required="correcting" rows="3" /></label>
    </div>
    <p v-if="validationError" class="validation-error" role="alert" data-field-error="actualPoDate">{{ validationError }}</p>
  </ModalShell>
</template>

<style scoped>
.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:9px}
.modal-hint{margin:0 0 12px;color:var(--crm-text-muted);font-size:10px;line-height:1.6}
.po-date-fields{display:grid;gap:12px}
.po-date-fields label{display:grid;gap:6px;color:var(--crm-text-muted);font-size:9px;font-weight:700}
.po-date-fields input,.po-date-fields textarea{box-sizing:border-box;width:100%;min-height:38px;padding:8px 10px;border:1px solid var(--crm-line);border-radius:8px;outline:0;font:inherit}
.validation-error{margin:10px 0 0;color:var(--crm-danger);font-size:10px}
</style>
