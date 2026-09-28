<script setup lang="ts">
import PersonnelSelect from '@/design-system/PersonnelSelect.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import ContactPicker from '@/features/contacts/ContactPicker.vue'
import { useI18n } from '@/i18n'
import type { ContactSummaryDto } from '@/types/crm'
import type { BookingDraft } from '@/types/workspaces'

const props = withDefaults(defineProps<{
  modelValue: BookingDraft
  contacts: ContactSummaryDto[]
  accountId: string
  showRequiredMarks?: boolean
  /** A Sales user can only assign a Booking to themselves. */
  ownerDisabled?: boolean
  errors?: Partial<Record<keyof BookingDraft, string>>
}>(), { showRequiredMarks: true, ownerDisabled: false, errors: () => ({}) })
const emit = defineEmits<{ 'update:modelValue': [value: BookingDraft]; 'create-contact': [accountId: string] }>()
const { t } = useI18n()

function update<K extends keyof BookingDraft>(field: K, value: BookingDraft[K]) {
  emit('update:modelValue', { ...props.modelValue, [field]: value })
}

function valueOf(event: Event) {
  return (event.target as HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement).value
}
</script>

<template>
  <div class="booking-fields" data-booking-fields>
    <div class="field contact-field">
      <span>{{ t('detail.primaryContact') }}<RequiredMark :show="showRequiredMarks" /></span>
      <ContactPicker :model-value="modelValue.primaryContactId" :contacts="contacts" :account-id="accountId" required @update:model-value="update('primaryContactId', $event)" @create="emit('create-contact', accountId)" />
      <small v-if="errors.primaryContactId" data-field-error="primaryContactId">{{ errors.primaryContactId }}</small>
    </div>
    <label class="field">
      <span>{{ t('bookingEditor.owner') }}<RequiredMark :show="showRequiredMarks" /></span>
      <PersonnelSelect :model-value="modelValue.owner" :roles="['Sales']" :ariaLabel="t('bookingEditor.owner')" :disabled="ownerDisabled" required @update:model-value="update('owner', $event)" />
      <small v-if="errors.owner" data-field-error="owner">{{ errors.owner }}</small>
    </label>
    <label class="field wide">
      <span>{{ t('detail.equipmentNeed') }}<RequiredMark :show="showRequiredMarks" /></span>
      <input :value="modelValue.equipment" :aria-label="t('detail.equipmentNeed')" required placeholder="FastScan 1200" @input="update('equipment', valueOf($event))" />
      <small v-if="errors.equipment" data-field-error="equipment">{{ errors.equipment }}</small>
    </label>
    <label class="field">
      <span>{{ t('detail.quantity') }}<RequiredMark :show="showRequiredMarks" /></span>
      <input :value="modelValue.quantity" :aria-label="t('detail.quantity')" type="number" min="1" step="1" required :placeholder="t('detail.quantity')" @input="update('quantity', Number(valueOf($event)))" />
      <small v-if="errors.quantity" data-field-error="quantity">{{ errors.quantity }}</small>
    </label>
    <label class="field">
      <span>{{ t('detail.customerDdl') }}<RequiredMark :show="showRequiredMarks" /></span>
      <input :value="modelValue.ddl" :aria-label="t('detail.customerDdl')" type="date" required @input="update('ddl', valueOf($event))" />
      <small v-if="errors.ddl" data-field-error="ddl">{{ errors.ddl }}</small>
    </label>
    <label class="field">
      <span>{{ t('detail.bookingAmount') }}<RequiredMark :show="showRequiredMarks" /></span>
      <input :value="modelValue.amount" :aria-label="t('detail.bookingAmount')" type="text" inputmode="decimal" pattern="\d+(?:\.\d{1,2})?" required placeholder="0.00" @input="update('amount', valueOf($event))" />
      <small v-if="errors.amount" data-field-error="amount">{{ errors.amount }}</small>
    </label>
    <label class="field">
      <span>{{ t('bookingEditor.currency') }}<RequiredMark :show="showRequiredMarks" /></span>
      <select :value="modelValue.currency" :aria-label="t('bookingEditor.currency')" required @change="update('currency', valueOf($event))"><option>CNY</option><option>USD</option><option>EUR</option></select>
      <small v-if="errors.currency" data-field-error="currency">{{ errors.currency }}</small>
    </label>
    <label class="field wide">
      <span>{{ t('detail.notes') }}</span>
      <textarea :value="modelValue.note" :aria-label="t('detail.notes')" rows="3" :placeholder="t('bookingEditor.notePlaceholder')" @input="update('note', valueOf($event))" />
    </label>
  </div>
</template>

<style scoped>
.booking-fields{display:grid;grid-template-columns:1fr 1fr;gap:13px}
.booking-fields .field{display:grid;align-content:start;gap:6px}.booking-fields .wide{grid-column:1/-1}
.booking-fields span{color:var(--crm-text-muted);font-size:9px;font-weight:700}
.booking-fields input,.booking-fields select,.booking-fields textarea{box-sizing:border-box;width:100%;padding:9px 10px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;font:inherit}
.booking-fields input,.booking-fields select{height:38px}.booking-fields textarea{resize:vertical}.booking-fields :focus{border-color:var(--crm-teal);outline:0}
.booking-fields select:disabled{color:var(--crm-text-muted);background:var(--crm-surface-muted);cursor:not-allowed}
.booking-fields input::placeholder,.booking-fields textarea::placeholder{color:#aab5b7}
.booking-fields small{color:var(--crm-danger);font-size:8px}
@media(max-width:560px){.booking-fields{grid-template-columns:1fr}.booking-fields .wide{grid-column:auto}}
</style>
