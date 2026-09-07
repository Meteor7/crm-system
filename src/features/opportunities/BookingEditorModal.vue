<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import PersonnelSelect from '@/design-system/PersonnelSelect.vue'
import { preferredPersonnelId } from '@/demo/personnel'
import ContactPicker from '@/features/contacts/ContactPicker.vue'
import type { AccountSummaryDto, BookingDto, ContactSummaryDto, OpportunityDto, UpsertBookingInput } from '@/types/crm'
import { useI18n } from '@/i18n'
import { salesEnumLabel } from '@/features/shared/sales-i18n'

type BookingOpportunity = Pick<OpportunityDto, 'id' | 'accountId' | 'title' | 'amount' | 'currency' | 'owner' | 'saleType'> & { stage: string; toolType?: string; poDate?: string }

const props = defineProps<{
  booking?: BookingDto | null
  accounts: AccountSummaryDto[]
  opportunities: BookingOpportunity[]
  contacts: ContactSummaryDto[]
  selectedContactId?: string
  sourceOpportunityId?: string
  defaultOwner: string
  busy?: boolean
  error?: string
}>()
const emit = defineEmits<{ close: []; submit: [value: UpsertBookingInput]; 'create-contact': [accountId: string] }>()
const { t, locale } = useI18n()

const firstAccount = props.accounts[0]
const initialSourceOpportunityId = props.booking?.sourceOpportunityId ?? props.sourceOpportunityId ?? ''
const initialOpportunity = props.opportunities.find((item) => item.id === initialSourceOpportunityId)
const form = ref({
  accountId: props.booking?.accountId ?? initialOpportunity?.accountId ?? firstAccount?.id ?? '',
  primaryContactId: props.booking?.primaryContactId ?? props.selectedContactId ?? '',
  customerContact: '',
  equipment: props.booking?.equipment ?? initialOpportunity?.toolType ?? initialOpportunity?.title ?? '',
  quantity: props.booking?.quantity ?? 1,
  ddl: props.booking?.ddl ?? initialOpportunity?.poDate ?? '2026-09-30',
  amount: props.booking?.amount ?? initialOpportunity?.amount ?? '0.00',
  currency: props.booking?.currency ?? initialOpportunity?.currency ?? 'CNY',
  status: props.booking?.status ?? 'Pending',
  owner: preferredPersonnelId('Sales', props.booking?.owner ?? initialOpportunity?.owner ?? props.defaultOwner),
  source: props.booking?.source ?? (initialSourceOpportunityId ? 'Opportunity' : 'Upsell'),
  bookingType: props.booking?.bookingType ?? (initialOpportunity?.saleType === 'Service' ? 'Service' : 'Equipment'),
  sourceOpportunityId: initialSourceOpportunityId,
  note: props.booking?.note ?? '',
})
const sourceOpportunities = computed(() => props.opportunities.filter((item) =>
  item.stage === 'Won' || item.id === props.booking?.sourceOpportunityId,
))
watch(() => form.value.accountId, () => {
  if (!props.contacts.some((item) => item.id === form.value.primaryContactId && item.accountId === form.value.accountId && item.status === 'Active')) {
    form.value.primaryContactId = ''
  }
})
watch(() => props.selectedContactId, (value) => {
  if (value) form.value.primaryContactId = value
})
watch(() => form.value.sourceOpportunityId, (value) => {
  const opportunity = props.opportunities.find((item) => item.id === value)
  if (!opportunity) return
  form.value.accountId = opportunity.accountId
  form.value.equipment = opportunity.toolType || opportunity.title
  form.value.amount = opportunity.amount
  form.value.currency = opportunity.currency
  form.value.owner = opportunity.owner
  form.value.bookingType = opportunity.saleType === 'Service' ? 'Service' : 'Equipment'
})
watch(() => form.value.source, (value) => {
  if (value === 'Upsell') form.value.sourceOpportunityId = ''
})

function submit() {
  const { customerContact: _legacyText, ...input } = form.value
  emit('submit', {
    ...input,
    equipment: form.value.equipment.trim(),
    owner: form.value.owner.trim(),
    note: form.value.note.trim(),
  })
}
</script>

<template>
  <ModalShell :title="booking ? t('bookingEditor.edit') : t('bookingEditor.new')" eyebrow="SALES BOOKING" :busy="busy" @close="$emit('close')" @submit="submit">
    <p v-if="error" class="form-error">{{ error }}</p>
    <div class="booking-form-grid">
      <label><span>{{ t('bookingEditor.source') }}</span><select v-model="form.source" :aria-label="t('bookingEditor.source')"><option v-for="item in ['Opportunity', 'Upsell']" :key="item" :value="item">{{ salesEnumLabel(item, locale) }}</option></select></label>
      <label><span>{{ t('bookingEditor.type') }}<RequiredMark :show="!booking" /></span><select v-model="form.bookingType" :aria-label="t('bookingEditor.type')" :disabled="form.source === 'Opportunity'" required><option v-for="item in ['Equipment', 'Service']" :key="item" :value="item">{{ salesEnumLabel(item, locale) }}</option></select></label>
      <label v-if="form.source === 'Opportunity'"><span>{{ t('bookingEditor.sourceOpportunity') }}<RequiredMark :show="!booking" /></span><select v-model="form.sourceOpportunityId" :aria-label="t('bookingEditor.sourceOpportunity')" required><option value="">{{ t('bookingEditor.selectWon') }}</option><option v-for="item in sourceOpportunities" :key="item.id" :value="item.id">{{ item.id }} · {{ item.title }}</option></select></label>
      <label v-else><span>{{ t('bookingEditor.sourceNote') }}</span><input :value="salesEnumLabel('Existing Customer Upsell', locale)" :aria-label="t('bookingEditor.sourceNote')" disabled /></label>
      <label><span>{{ t('detail.account') }}</span><select v-model="form.accountId" :aria-label="t('detail.account')" :disabled="Boolean(form.sourceOpportunityId)"><option v-for="account in accounts" :key="account.id" :value="account.id">{{ account.shortName }} · {{ account.name }}</option></select></label>
      <div class="contact-field"><span>{{ t('detail.primaryContact') }}<RequiredMark :show="!booking" /></span><ContactPicker v-model="form.primaryContactId" :contacts="contacts" :account-id="form.accountId" required @create="emit('create-contact', form.accountId)" /></div>
      <label class="wide"><span>{{ t('detail.equipmentNeed') }}<RequiredMark :show="!booking" /></span><input v-model="form.equipment" :aria-label="t('detail.equipmentNeed')" required placeholder="FastScan 1200" /></label>
      <label><span>{{ t('detail.quantity') }}<RequiredMark :show="!booking" /></span><input v-model.number="form.quantity" :aria-label="t('detail.quantity')" type="number" min="1" required :placeholder="t('detail.quantity')" /></label>
      <label><span>{{ t('detail.customerDdl') }}<RequiredMark :show="!booking" /></span><input v-model="form.ddl" :aria-label="t('detail.customerDdl')" type="date" required /></label>
      <label><span>{{ t('detail.bookingAmount') }}<RequiredMark :show="!booking" /></span><input v-model="form.amount" :aria-label="t('detail.bookingAmount')" type="text" inputmode="decimal" pattern="\d+(?:\.\d{1,2})?" required placeholder="0.00" /></label>
      <label><span>{{ t('bookingEditor.currency') }}<RequiredMark :show="!booking" /></span><select v-model="form.currency" :aria-label="t('bookingEditor.currency')" required><option>CNY</option><option>USD</option><option>EUR</option></select></label>
      <label><span>{{ t('detail.status') }}</span><select v-model="form.status" :aria-label="t('detail.status')"><option v-for="item in ['Pending', 'Confirmed', 'Cancelled']" :key="item" :value="item">{{ salesEnumLabel(item, locale) }}</option></select></label>
      <label><span>{{ t('bookingEditor.owner') }}<RequiredMark :show="!booking" /></span><PersonnelSelect v-model="form.owner" :roles="['Sales']" :ariaLabel="t('bookingEditor.owner')" required /></label>
      <label class="wide"><span>{{ t('detail.notes') }}</span><textarea v-model="form.note" :aria-label="t('detail.notes')" rows="3" :placeholder="t('bookingEditor.notePlaceholder')" /></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:9px}
.booking-form-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.booking-form-grid label,.contact-field{display:grid;gap:6px}.booking-form-grid label.wide{grid-column:1/-1}
.booking-form-grid span{color:var(--crm-text-muted);font-size:9px;font-weight:700}.booking-form-grid input,.booking-form-grid select,.booking-form-grid textarea{box-sizing:border-box;width:100%;padding:9px 10px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.booking-form-grid input,.booking-form-grid select{height:38px}.booking-form-grid textarea{resize:vertical}.booking-form-grid :focus{border-color:var(--crm-teal);outline:0}.booking-form-grid input::placeholder,.booking-form-grid textarea::placeholder{color:#aab5b7}
@media(max-width:560px){.booking-form-grid{grid-template-columns:1fr}.booking-form-grid label.wide{grid-column:auto}}
</style>
