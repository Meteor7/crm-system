<script setup lang="ts">
import { computed, ref } from 'vue'
import { CheckCircle2, ShieldCheck, X } from '@lucide/vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import { personnelDisplayName } from '@/demo/personnel'
import { formatMoney } from '@/domain/money'
import { internalValidationCancelReasonLabel, internalValidationStatusLabel, internalValidationStatusTone } from '@/domain/opportunity-stages'
import { formatDisplayDate, formatDisplayDateTime } from '@/domain/time'
import { useI18n, useLocaleMessage } from '@/i18n'
import type { OpportunityInternalValidationDto } from '@/types/workspaces'

const props = defineProps<{
  validation: OpportunityInternalValidationDto
  stage: string
  currentUserId: string
  /** deal:internal_validation_approve, granted to Managers. */
  canReview: boolean
  busy?: boolean
  error?: string
}>()
const emit = defineEmits<{ review: [input: { decision: 'approved' | 'rejected'; comment: string }] }>()
const { t, locale, message } = useI18n()
const comment = ref('')
const commentError = useLocaleMessage()
// A pending request is reviewed while the Opportunity is at quotation sent, and never by the Manager who requested it.
const reviewable = computed(() => props.canReview && props.validation.status === 'pending' && props.stage === 'quotation_sent')
const ownRequest = computed(() => props.validation.requestedBy === props.currentUserId)
const draft = computed(() => props.validation.booking)

function review(decision: 'approved' | 'rejected') {
  if (decision === 'rejected' && !comment.value.trim()) {
    commentError.value = message('internalValidation.commentRequired')
    return
  }
  commentError.value = ''
  emit('review', { decision, comment: comment.value.trim() })
}
</script>

<template>
  <section class="validation-card" data-testid="internal-validation-panel" :data-validation-status="validation.status">
    <header><ShieldCheck :size="16" /><h2>{{ t('internalValidation.panelTitle') }}</h2><StatusBadge :label="internalValidationStatusLabel(validation.status, locale)" :tone="internalValidationStatusTone(validation.status)" /></header>
    <dl class="validation-fields">
      <div><dt>{{ t('internalValidation.attempt', { attempt: validation.attemptNo }) }}</dt><dd>{{ validation.reason }}</dd></div>
      <div><dt>{{ t('internalValidation.expectedPoDate') }}</dt><dd>{{ formatDisplayDate(validation.expectedPoDate) }}</dd></div>
      <div v-if="draft?.equipment"><dt>{{ t('internalValidation.bookingDraft') }}</dt><dd>{{ draft.equipment }} × {{ draft.quantity }} · {{ formatMoney(draft.amount, draft.currency) }} · {{ formatDisplayDate(draft.ddl) }}</dd></div>
      <div><dt>{{ t('internalValidation.requestedBy') }}</dt><dd>{{ personnelDisplayName(validation.requestedBy) }} · {{ formatDisplayDateTime(validation.requestedAt) }}</dd></div>
      <div v-if="validation.decidedBy"><dt>{{ t('internalValidation.decidedBy') }}</dt><dd>{{ personnelDisplayName(validation.decidedBy) }} · {{ formatDisplayDateTime(validation.decidedAt) }}</dd></div>
      <div v-if="validation.decisionComment"><dt>{{ t('internalValidation.decisionComment') }}</dt><dd>{{ validation.decisionComment }}</dd></div>
      <div v-if="validation.bookingId"><dt>{{ t('internalValidation.createdBooking') }}</dt><dd><RouterLink :to="{ name: 'booking-detail', params: { bookingId: validation.bookingId } }" data-testid="internal-validation-booking-link">{{ validation.bookingId }}</RouterLink></dd></div>
      <div v-if="validation.status === 'cancelled'"><dt>{{ t('internalValidation.cancelReason') }}</dt><dd>{{ internalValidationCancelReasonLabel(validation.cancelReason, locale) }}<small v-if="validation.cancelledBy">{{ personnelDisplayName(validation.cancelledBy) }} · {{ formatDisplayDateTime(validation.cancelledAt) }}</small></dd></div>
    </dl>
    <div v-if="reviewable" class="review-form">
      <p v-if="ownRequest" class="own-request" data-testid="internal-validation-own-request">{{ t('internalValidation.ownRequest') }}</p>
      <template v-else>
        <label><span>{{ t('internalValidation.decisionComment') }}</span><textarea v-model="comment" :aria-label="t('internalValidation.decisionComment')" rows="3" :placeholder="t('internalValidation.commentPlaceholder')" /></label>
        <small v-if="commentError" data-field-error="comment">{{ commentError }}</small>
        <p v-if="error" class="review-error" role="alert">{{ error }}</p>
        <div class="review-actions">
          <button class="secondary-button reject-button" type="button" data-testid="reject-internal-validation" :disabled="busy" @click="review('rejected')"><X :size="13" />{{ t('internalValidation.reject') }}</button>
          <button class="primary-button" type="button" data-testid="approve-internal-validation" :disabled="busy" @click="review('approved')"><CheckCircle2 :size="13" />{{ t('internalValidation.approve') }}</button>
        </div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.validation-card{overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:12px;box-shadow:0 8px 24px rgba(31,35,41,.035)}
.validation-card>header{display:flex;min-height:50px;align-items:center;gap:8px;padding:0 14px;color:var(--crm-teal);background:#faf9f7;border-bottom:1px solid var(--crm-line)}
.validation-card>header h2{flex:1;margin:0;color:var(--crm-navy);font-size:12px}
.validation-fields{display:grid;margin:0;padding:2px 14px 10px}.validation-fields>div{display:grid;gap:4px;padding:9px 0;border-bottom:1px solid var(--crm-line)}.validation-fields>div:last-child{border-bottom:0}
.validation-fields dt{color:var(--crm-text-muted);font-size:8px;font-weight:700}.validation-fields dd{display:grid;gap:3px;margin:0;color:var(--crm-text);font-size:10px;line-height:1.45}.validation-fields dd a{color:var(--crm-link)}.validation-fields small{color:var(--crm-text-muted);font-size:8px}
.review-form{display:grid;gap:8px;padding:12px 14px 14px;background:var(--crm-surface);border-top:1px solid var(--crm-line)}
.review-form label{display:grid;gap:6px}.review-form span{color:var(--crm-text-muted);font-size:9px;font-weight:700}
.review-form textarea{box-sizing:border-box;width:100%;padding:9px 10px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;font:inherit;resize:vertical}
.review-form>small,.review-error{margin:0;color:var(--crm-danger);font-size:9px}
.own-request{margin:0;color:var(--crm-text-muted);font-size:9px;line-height:1.5}
.review-actions{display:grid;grid-template-columns:1fr 1fr;gap:7px}.review-actions button{display:flex;align-items:center;justify-content:center;gap:4px}
.reject-button{color:var(--crm-danger)!important;border-color:rgba(200,78,78,.35)!important}
</style>
