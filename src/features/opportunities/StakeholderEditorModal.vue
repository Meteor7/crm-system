<script setup lang="ts">
import { useLocalizedInput } from '@/i18n/localized-input'
import { systemValueLabel } from '@/features/shared/system-labels'
import { ref, watch } from 'vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import ContactPicker from '@/features/contacts/ContactPicker.vue'
import type { ContactSummaryDto } from '@/types/crm'
import { OPPORTUNITY_STAKEHOLDER_INFLUENCES, OPPORTUNITY_STAKEHOLDER_ROLES, OPPORTUNITY_STAKEHOLDER_STANCES, type CreateOpportunityStakeholderInput, type OpportunityStakeholderDto } from '@/types/workspaces'
import { useI18n } from '@/i18n'
import { salesEnumLabel } from '@/features/shared/sales-i18n'

const props = defineProps<{
  stakeholder?: OpportunityStakeholderDto | null
  contacts: ContactSummaryDto[]
  accountId: string
  selectedContactId?: string
  busy?: boolean
  error?: string
}>()
const emit = defineEmits<{ close: []; submit: [value: CreateOpportunityStakeholderInput]; createContact: [] }>()
const { t, locale } = useI18n()
const form = ref<CreateOpportunityStakeholderInput>({
  contactId: props.stakeholder?.contactId ?? '',
  role: props.stakeholder?.role ?? 'Influencer', influence: props.stakeholder?.influence ?? 'Medium',
  stance: props.stakeholder?.stance ?? 'Neutral', coverage: props.stakeholder?.coverage ?? '待建立覆盖',
  isCoach: props.stakeholder?.isCoach ?? false,
  winResult: props.stakeholder?.winResult ?? '',
  opportunityNotes: props.stakeholder?.opportunityNotes ?? '',
})

watch(() => props.selectedContactId, (contactId) => {
  if (contactId) form.value.contactId = contactId
})
watch(() => props.accountId, () => {
  if (!props.contacts.some((contact) => contact.id === form.value.contactId && contact.accountId === props.accountId && contact.status === 'Active')) {
    form.value.contactId = ''
  }
})

const coverageInput = useLocalizedInput(() => form.value.coverage, (value) => { form.value.coverage = value }, (value) => systemValueLabel(value, locale.value))
</script>

<template>
  <ModalShell :title="stakeholder ? t('stakeholderEditor.edit') : t('stakeholderEditor.new')" eyebrow="BUYING INFLUENCE" :busy="busy" @close="$emit('close')" @submit="$emit('submit', { ...form, coverage: stakeholder ? form.coverage : coverageInput })">
    <p v-if="error" class="form-error">{{ error }}</p>
    <div class="compact-form-grid">
      <label class="wide"><span>{{ t('detail.contact') }}<RequiredMark :show="!stakeholder" /></span><ContactPicker v-model="form.contactId" :contacts="contacts" :account-id="accountId" data-testid="opportunity-contact-picker" :disabled="busy" required @create="emit('createContact')" /></label>
      <label><span>{{ t('stakeholderEditor.role') }}<RequiredMark :show="!stakeholder" /></span><select v-model="form.role" :aria-label="t('stakeholderEditor.role')" required><option v-for="item in OPPORTUNITY_STAKEHOLDER_ROLES" :key="item" :value="item">{{ salesEnumLabel(item, locale) }}</option></select></label>
      <label><span>{{ t('stakeholderEditor.influence') }}<RequiredMark :show="!stakeholder" /></span><select v-model="form.influence" :aria-label="t('stakeholderEditor.influence')" required><option v-for="item in OPPORTUNITY_STAKEHOLDER_INFLUENCES" :key="item" :value="item">{{ salesEnumLabel(item, locale) }}</option></select></label>
      <label><span>{{ t('stakeholderEditor.attitude') }}<RequiredMark :show="!stakeholder" /></span><select v-model="form.stance" :aria-label="t('stakeholderEditor.attitude')" required><option v-for="item in OPPORTUNITY_STAKEHOLDER_STANCES" :key="item" :value="item">{{ salesEnumLabel(item, locale) }}</option></select></label>
      <label><span>{{ t('stakeholderEditor.coverage') }}<RequiredMark :show="!stakeholder" /></span><input v-model="coverageInput" :aria-label="t('stakeholderEditor.coverage')" required /></label>
      <label><span>{{ t('stakeholderEditor.winResult') }}</span><input v-model="form.winResult" :aria-label="t('stakeholderEditor.winResult')" /></label>
      <label><span>{{ t('stakeholderEditor.notes') }}</span><input v-model="form.opportunityNotes" :aria-label="t('stakeholderEditor.notes')" /></label>
      <label class="coach"><input v-model="form.isCoach" :aria-label="t('stakeholderEditor.coach')" type="checkbox" /><span>{{ t('stakeholderEditor.coach') }}</span></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:9px}.compact-form-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.compact-form-grid label{display:grid;gap:6px}.compact-form-grid label.wide{grid-column:1/-1}.compact-form-grid span{color:var(--crm-text-muted);font-size:9px;font-weight:700}.compact-form-grid input,.compact-form-grid select{height:38px;padding:0 10px;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.compact-form-grid label.coach{display:flex;align-items:center;gap:7px}.compact-form-grid label.coach input{height:auto}.compact-form-grid :focus{border-color:var(--crm-teal);outline:0}@media(max-width:560px){.compact-form-grid{grid-template-columns:1fr}.compact-form-grid label.wide{grid-column:auto}}
</style>
