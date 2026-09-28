<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ModalShell from '@/design-system/ModalShell.vue'
import BookingFields from './BookingFields.vue'
import { opportunityBookingDraft, trimmedBookingDraft, validateBookingDraft, type BookingDraftErrors } from './booking-draft'
import { resolveLocaleMessage, useI18n } from '@/i18n'
import type { ContactSummaryDto } from '@/types/crm'
import type { BookingDraft, ConfirmPoInput, StrategyOpportunityDto } from '@/types/workspaces'

const props = defineProps<{
  opportunity: StrategyOpportunityDto
  contacts: ContactSummaryDto[]
  selectedContactId?: string
  defaultOwner: string
  /** Set for a Sales user, who can only assign the Booking to themselves. */
  lockedOwner?: string
  /** At PO received, a Booking cancelled by hand is replaced without a new stage arrival. */
  replacing?: boolean
  busy?: boolean
  error?: string
}>()
const emit = defineEmits<{ close: []; submit: [input: ConfirmPoInput]; 'create-contact': [accountId: string] }>()
const { t } = useI18n()
// Prefilled from the Pending Booking of an approved internal validation, or else from the request draft.
const draft = ref<BookingDraft>(opportunityBookingDraft(props.opportunity, props.contacts, props.defaultOwner, props.lockedOwner))
const draftErrors = ref<BookingDraftErrors>({})
const fieldErrors = computed(() => Object.fromEntries(
  Object.entries(draftErrors.value).map(([field, value]) => [field, resolveLocaleMessage(value)]),
))
const confirmsPendingBooking = computed(() => props.opportunity.stage === 'internal_validation' && props.opportunity.liveBooking?.status === 'Pending')
const cancelsPendingRequest = computed(() => props.opportunity.stage === 'quotation_sent' && props.opportunity.internalValidation?.status === 'pending')
// A replacement Booking does not need the probability level; confirming the PO does.
const levelMissing = computed(() => !props.replacing && !props.opportunity.probabilityLevel)
const hint = computed(() => {
  if (props.replacing) return t('poConfirmation.replaceHint')
  return confirmsPendingBooking.value ? t('poConfirmation.pendingBookingHint') : t('poConfirmation.hint')
})

watch(() => props.selectedContactId, (value) => {
  if (value) draft.value = { ...draft.value, primaryContactId: value }
})

function submit() {
  draftErrors.value = validateBookingDraft(draft.value)
  if (Object.keys(draftErrors.value).length) return
  const input: ConfirmPoInput = { booking: trimmedBookingDraft(draft.value) }
  // The server confirms the Pending Booking only if it is still the version this form was prefilled from.
  if (confirmsPendingBooking.value && props.opportunity.liveBooking?.modified) input.expectedBookingModified = props.opportunity.liveBooking.modified
  emit('submit', input)
}
</script>

<template>
  <ModalShell :title="replacing ? t('poConfirmation.replaceTitle') : t('poConfirmation.title')" :eyebrow="replacing ? 'REPLACEMENT BOOKING' : 'PO RECEIVED'" :busy="busy" :submit-disabled="levelMissing" :submit-label="replacing ? t('poConfirmation.replaceSubmit') : t('poConfirmation.submit')" @close="emit('close')" @submit="submit">
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <p class="modal-hint" data-testid="po-confirmation-hint">{{ hint }}</p>
    <p v-if="cancelsPendingRequest" class="modal-warning" data-testid="po-cancels-pending-request">{{ t('poConfirmation.cancelPendingHint') }}</p>
    <p v-if="levelMissing" class="modal-warning" data-testid="level-required-hint">{{ t('detail.levelRequiredHint') }}</p>
    <BookingFields v-model="draft" :contacts="contacts" :account-id="opportunity.accountId" :owner-disabled="Boolean(lockedOwner)" :errors="fieldErrors" @create-contact="emit('create-contact', $event)" />
  </ModalShell>
</template>

<style scoped>
.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:9px}
.modal-hint{margin:0 0 12px;color:var(--crm-text-muted);font-size:10px;line-height:1.6}
.modal-warning{margin:0 0 12px;padding:9px 10px;color:#8a651d;background:var(--crm-warning-soft);border-radius:8px;font-size:9px;line-height:1.5}
</style>
