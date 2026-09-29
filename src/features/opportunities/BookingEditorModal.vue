<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import { preferredPersonnelId } from '@/demo/personnel'
import { shanghaiDate } from '@/domain/time'
import BookingFields from './BookingFields.vue'
import type { AccountSummaryDto, BookingDto, ContactSummaryDto, OpportunityDto, UpsertBookingInput } from '@/types/crm'
import type { BookingDraft } from '@/types/workspaces'
import { useI18n } from '@/i18n'
import { salesEnumLabel } from '@/features/shared/sales-i18n'

type BookingOpportunity = Pick<OpportunityDto, 'id' | 'title'>

const props = defineProps<{
  booking?: BookingDto | null
  accounts: AccountSummaryDto[]
  /** Used to show the source Opportunity title of an Opportunity Booking. */
  opportunities?: BookingOpportunity[]
  contacts: ContactSummaryDto[]
  selectedContactId?: string
  defaultOwner: string
  busy?: boolean
  error?: string
}>()
const emit = defineEmits<{ close: []; submit: [value: UpsertBookingInput]; 'create-contact': [accountId: string] }>()
const { t, locale } = useI18n()

// A new Booking is always an Upsell: Opportunity Bookings come from PO confirmation or an approved internal validation.
const opportunityBooking = computed(() => props.booking?.source === 'Opportunity')
const form = ref({
  accountId: props.booking?.accountId ?? props.accounts[0]?.id ?? '',
  source: props.booking?.source ?? 'Upsell',
  bookingType: props.booking?.bookingType ?? 'Equipment',
  sourceOpportunityId: props.booking?.sourceOpportunityId ?? '',
  status: props.booking?.status ?? 'Pending',
  actualPoDate: props.booking?.actualPoDate ?? '',
})
// Only an Upsell Booking without a date takes one here; any other change is a Manager's correction.
const actualPoDateLocked = computed(() => opportunityBooking.value || Boolean(props.booking?.actualPoDate))
// Mirrors bookings._assert_amount_cny_edit: only a Pending Booking, or an order without one, takes a CNY amount here.
const amountCnyLocked = computed(() => Boolean(props.booking && props.booking.status !== 'Pending' && props.booking.currency !== 'CNY' && props.booking.amountCny))
const latestPoDate = shanghaiDate()
const draft = ref<BookingDraft>({
  primaryContactId: props.booking?.primaryContactId ?? props.selectedContactId ?? '',
  equipment: props.booking?.equipment ?? '',
  quantity: props.booking?.quantity ?? 1,
  ddl: props.booking?.ddl ?? '2026-09-30',
  amount: props.booking?.amount ?? '0.00',
  currency: props.booking?.currency ?? 'CNY',
  amountCny: props.booking && props.booking.currency !== 'CNY' ? props.booking.amountCny ?? '' : '',
  owner: preferredPersonnelId('Sales', props.booking?.owner ?? props.defaultOwner),
  note: props.booking?.note ?? '',
})
// An Opportunity Booking can only be cancelled by hand, and a cancelled one cannot be restored.
const statusOptions = computed<BookingDto['status'][]>(() => {
  if (!opportunityBooking.value || !props.booking) return ['Pending', 'Confirmed', 'Cancelled']
  return props.booking.status === 'Cancelled' ? ['Cancelled'] : [props.booking.status, 'Cancelled']
})
const sourceOpportunityLabel = computed(() => {
  const opportunity = props.opportunities?.find((item) => item.id === form.value.sourceOpportunityId)
  return opportunity ? `${opportunity.id} · ${opportunity.title}` : form.value.sourceOpportunityId
})
watch(() => form.value.accountId, () => {
  if (!props.contacts.some((item) => item.id === draft.value.primaryContactId && item.accountId === form.value.accountId && item.status === 'Active')) {
    draft.value = { ...draft.value, primaryContactId: '' }
  }
})
watch(() => props.selectedContactId, (value) => {
  if (value) draft.value = { ...draft.value, primaryContactId: value }
})

function submit() {
  emit('submit', {
    accountId: form.value.accountId,
    primaryContactId: draft.value.primaryContactId,
    equipment: draft.value.equipment.trim(),
    quantity: draft.value.quantity,
    ddl: draft.value.ddl,
    amount: draft.value.amount,
    currency: draft.value.currency,
    status: form.value.status,
    owner: draft.value.owner.trim(),
    source: form.value.source,
    bookingType: form.value.bookingType,
    sourceOpportunityId: form.value.sourceOpportunityId,
    note: draft.value.note.trim(),
    actualPoDate: form.value.actualPoDate,
    ...(draft.value.currency !== 'CNY' ? { amountCny: String(draft.value.amountCny ?? '').trim() } : {}),
  })
}
</script>

<template>
  <ModalShell :title="booking ? t('bookingEditor.edit') : t('bookingEditor.new')" eyebrow="SALES BOOKING" :busy="busy" @close="$emit('close')" @submit="submit">
    <p v-if="error" class="form-error">{{ error }}</p>
    <p class="booking-note" :data-booking-editor-note="opportunityBooking ? 'opportunity' : 'upsell'">{{ opportunityBooking ? t('bookingEditor.opportunityLocked') : t('bookingEditor.upsellOnly') }}</p>
    <div class="booking-form-grid">
      <label><span>{{ t('bookingEditor.source') }}</span><select :value="form.source" :aria-label="t('bookingEditor.source')" disabled><option :value="form.source">{{ salesEnumLabel(form.source, locale) }}</option></select></label>
      <label><span>{{ t('bookingEditor.type') }}<RequiredMark :show="!booking" /></span><select v-model="form.bookingType" :aria-label="t('bookingEditor.type')" :disabled="opportunityBooking" required><option v-for="item in ['Equipment', 'Service']" :key="item" :value="item">{{ salesEnumLabel(item, locale) }}</option></select></label>
      <label v-if="opportunityBooking"><span>{{ t('bookingEditor.sourceOpportunity') }}</span><input :value="sourceOpportunityLabel" :aria-label="t('bookingEditor.sourceOpportunity')" disabled /></label>
      <label v-else><span>{{ t('bookingEditor.sourceNote') }}</span><input :value="salesEnumLabel('Existing Customer Upsell', locale)" :aria-label="t('bookingEditor.sourceNote')" disabled /></label>
      <label><span>{{ t('detail.account') }}<RequiredMark :show="!booking" /></span><select v-model="form.accountId" :aria-label="t('detail.account')" :disabled="opportunityBooking" required><option value="" disabled>{{ t('quotations.selectAccount') }}</option><option v-for="account in accounts" :key="account.id" :value="account.id">{{ account.shortName }} · {{ account.name }}</option></select></label>
      <label><span>{{ t('detail.status') }}<RequiredMark :show="!booking" /></span><select v-model="form.status" :aria-label="t('detail.status')" required><option v-for="item in statusOptions" :key="item" :value="item">{{ salesEnumLabel(item, locale) }}</option></select></label>
      <label class="wide"><span>{{ actualPoDateLocked ? t('actualPoDate.label') : t('actualPoDate.optionalLabel') }}</span><input v-model="form.actualPoDate" :aria-label="t('actualPoDate.label')" type="date" :max="latestPoDate" :disabled="actualPoDateLocked" /><small v-if="actualPoDateLocked" class="field-hint">{{ t('actualPoDate.managerOnly') }}</small></label>
    </div>
    <BookingFields v-model="draft" class="booking-draft-fields" :contacts="contacts" :account-id="form.accountId" :show-required-marks="!booking" :amount-cny-locked="amountCnyLocked" @create-contact="emit('create-contact', $event)" />
  </ModalShell>
</template>

<style scoped>
.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:9px}
.booking-note{margin:0 0 12px;padding:9px 10px;color:var(--crm-text-muted);background:var(--crm-surface-muted);border-radius:8px;font-size:9px;line-height:1.5}
.booking-form-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px;margin-bottom:13px}.booking-form-grid label{display:grid;gap:6px}
.booking-form-grid span{color:var(--crm-text-muted);font-size:9px;font-weight:700}.booking-form-grid input,.booking-form-grid select{box-sizing:border-box;width:100%;height:38px;padding:9px 10px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.booking-form-grid :focus{border-color:var(--crm-teal);outline:0}
.booking-form-grid input:disabled,.booking-form-grid select:disabled{color:var(--crm-text-muted);background:var(--crm-surface-muted);cursor:not-allowed}
.booking-form-grid .wide{grid-column:1/-1}.booking-form-grid .field-hint{color:var(--crm-text-muted);font-size:9px;font-weight:400}
@media(max-width:560px){.booking-form-grid{grid-template-columns:1fr}}
</style>
