<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import BookingFields from './BookingFields.vue'
import { opportunityBookingDraft, trimmedBookingDraft, validateBookingDraft, type BookingDraftErrors } from './booking-draft'
import { isIsoDate } from '@/domain/evaluations'
import { resolveLocaleMessage, useI18n, useLocaleMessage } from '@/i18n'
import type { ContactSummaryDto } from '@/types/crm'
import type { BookingDraft, RequestInternalValidationInput, StrategyOpportunityDto } from '@/types/workspaces'

const props = defineProps<{
  opportunity: StrategyOpportunityDto
  contacts: ContactSummaryDto[]
  selectedContactId?: string
  defaultOwner: string
  /** Set for a Sales user, who can only assign the Booking to themselves. */
  lockedOwner?: string
  busy?: boolean
  error?: string
}>()
const emit = defineEmits<{ close: []; submit: [input: RequestInternalValidationInput]; 'create-contact': [accountId: string] }>()
const { t, message } = useI18n()
const reason = ref('')
const expectedPoDate = ref(props.opportunity.poDate)
const draft = ref<BookingDraft>(opportunityBookingDraft(props.opportunity, props.contacts, props.defaultOwner, props.lockedOwner))
const reasonError = useLocaleMessage()
const dateError = useLocaleMessage()
const draftErrors = ref<BookingDraftErrors>({})
const fieldErrors = computed(() => Object.fromEntries(
  Object.entries(draftErrors.value).map(([field, value]) => [field, resolveLocaleMessage(value)]),
))
const levelMissing = computed(() => !props.opportunity.probabilityLevel)

watch(() => props.selectedContactId, (value) => {
  if (value) draft.value = { ...draft.value, primaryContactId: value }
})

function submit() {
  reasonError.value = reason.value.trim() ? '' : message('internalValidation.reasonRequired')
  dateError.value = isIsoDate(expectedPoDate.value) ? '' : message('internalValidation.expectedPoDateRequired')
  draftErrors.value = validateBookingDraft(draft.value)
  if (reasonError.value || dateError.value || Object.keys(draftErrors.value).length) return
  emit('submit', { reason: reason.value.trim(), expectedPoDate: expectedPoDate.value, booking: trimmedBookingDraft(draft.value) })
}
</script>

<template>
  <ModalShell :title="t('internalValidation.requestTitle')" eyebrow="INTERNAL VALIDATION" :busy="busy" :submit-disabled="levelMissing" :submit-label="t('internalValidation.submit')" @close="emit('close')" @submit="submit">
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <p class="modal-hint">{{ t('internalValidation.requestHint') }}</p>
    <p v-if="levelMissing" class="modal-warning" data-testid="level-required-hint">{{ t('detail.levelRequiredHint') }}</p>
    <div class="request-grid">
      <label class="wide"><span>{{ t('internalValidation.reason') }}<RequiredMark /></span><textarea v-model="reason" :aria-label="t('internalValidation.reason')" rows="3" required /><small v-if="reasonError" data-field-error="reason">{{ reasonError }}</small></label>
      <label><span>{{ t('internalValidation.expectedPoDate') }}<RequiredMark /></span><input v-model="expectedPoDate" :aria-label="t('internalValidation.expectedPoDate')" type="date" required /><small v-if="dateError" data-field-error="expectedPoDate">{{ dateError }}</small></label>
    </div>
    <h3 class="section-title">{{ t('internalValidation.bookingDraft') }}</h3>
    <BookingFields v-model="draft" :contacts="contacts" :account-id="opportunity.accountId" :owner-disabled="Boolean(lockedOwner)" :errors="fieldErrors" @create-contact="emit('create-contact', $event)" />
  </ModalShell>
</template>

<style scoped>
.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:9px}
.modal-hint{margin:0 0 12px;color:var(--crm-text-muted);font-size:10px;line-height:1.6}
.modal-warning{margin:0 0 12px;padding:9px 10px;color:#8a651d;background:var(--crm-warning-soft);border-radius:8px;font-size:9px;line-height:1.5}
.request-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.request-grid label{display:grid;gap:6px}.request-grid .wide{grid-column:1/-1}
.request-grid span{color:var(--crm-text-muted);font-size:9px;font-weight:700}
.request-grid input,.request-grid textarea{box-sizing:border-box;width:100%;padding:9px 10px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.request-grid input{height:38px}.request-grid textarea{resize:vertical}
.request-grid small{color:var(--crm-danger);font-size:8px}
.section-title{margin:18px 0 10px;padding-top:14px;color:var(--crm-navy);border-top:1px solid var(--crm-line);font-size:11px}
@media(max-width:560px){.request-grid{grid-template-columns:1fr}.request-grid .wide{grid-column:auto}}
</style>
