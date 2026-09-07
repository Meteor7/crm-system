<script setup lang="ts">
import { reactive, watch } from 'vue'
import type { CreateLeadInput, LeadDto, LeadSource, LeadStatus } from '@/types/crm'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import PersonnelSelect from '@/design-system/PersonnelSelect.vue'
import { preferredPersonnelId } from '@/demo/personnel'
import { useI18n } from '@/i18n'
import { salesEnumLabel } from '@/features/shared/sales-i18n'

const props = defineProps<{ lead?: LeadDto | null; busy?: boolean; error?: string }>()
const emit = defineEmits<{ close: []; submit: [payload: CreateLeadInput] }>()
const { t, locale } = useI18n()

const form = reactive({
  name: '',
  company: '',
  title: '',
  phone: '',
  email: '',
  source: 'Website' as LeadSource,
  status: 'New' as LeadStatus,
  owner: '',
  interest: '',
  firstContactNote: '',
  nextAction: '',
  nextActionDue: '',
})

watch(() => props.lead, (lead) => {
  form.name = lead?.name ?? ''
  form.company = lead?.company ?? ''
  form.title = lead?.title ?? ''
  form.phone = lead?.phone ?? ''
  form.email = lead?.email ?? ''
  form.source = lead?.source ?? 'Website'
  form.status = lead?.status ?? 'New'
  form.owner = lead?.owner ?? preferredPersonnelId('Sales', '')
  form.interest = lead?.interest ?? ''
  form.firstContactNote = lead?.firstContactNote ?? ''
  form.nextAction = lead?.nextAction ?? ''
  form.nextActionDue = lead?.nextActionDue ?? ''
}, { immediate: true })

function submit() {
  emit('submit', {
    name: form.name,
    company: form.company,
    title: form.title,
    ...(form.phone ? { phone: form.phone } : {}),
    ...(form.email ? { email: form.email } : {}),
    source: form.source,
    status: form.status,
    owner: form.owner,
    interest: form.interest,
    firstContactNote: form.firstContactNote,
    nextAction: form.nextAction,
    nextActionDue: form.nextActionDue,
  })
}
</script>

<template>
  <ModalShell :title="lead ? t('leadEditor.edit') : t('leadEditor.new')" eyebrow="LEAD QUALIFICATION" :busy="busy" @close="emit('close')" @submit="submit">
    <p v-if="error" class="form-error">{{ error }}</p>
    <div class="lead-form">
      <label><span>{{ t('leadEditor.name') }}<RequiredMark :show="!lead" /></span><input v-model="form.name" :aria-label="t('leadEditor.name')" required /></label>
      <label><span>{{ t('leadEditor.company') }}<RequiredMark :show="!lead" /></span><input v-model="form.company" :aria-label="t('leadEditor.company')" required /></label>
      <label><span>{{ t('leadEditor.title') }}<RequiredMark :show="!lead" /></span><input v-model="form.title" :aria-label="t('leadEditor.title')" required /></label>
       <label><span>{{ t('leadEditor.owner') }}<RequiredMark :show="!lead" /></span><PersonnelSelect v-model="form.owner" :roles="['Sales']" :ariaLabel="t('leadEditor.owner')" required /></label>
      <label><span>{{ t('leadEditor.phone') }}</span><input v-model="form.phone" :aria-label="t('leadEditor.phone')" /></label>
      <label><span>{{ t('leadEditor.email') }}</span><input v-model="form.email" :aria-label="t('leadEditor.email')" type="email" /></label>
       <label><span>{{ t('leadEditor.source') }}</span><select v-model="form.source" :aria-label="t('leadEditor.source')"><option v-for="item in ['Website', 'Trade Show', 'Partner Referral', 'Outbound', 'Customer Referral', 'Other']" :key="item" :value="item">{{ salesEnumLabel(item, locale) }}</option></select></label>
       <label><span>{{ t('leadEditor.status') }}</span><select v-model="form.status" :aria-label="t('leadEditor.status')"><option v-for="item in ['New', 'Working', 'Qualified', 'Nurturing', 'Disqualified']" :key="item" :value="item">{{ salesEnumLabel(item, locale) }}</option></select></label>
      <label class="wide"><span>{{ t('leadEditor.interest') }}</span><input v-model="form.interest" :aria-label="t('leadEditor.interest')" /></label>
      <label class="wide"><span>{{ t('leadEditor.firstContact') }}</span><textarea v-model="form.firstContactNote" :aria-label="t('leadEditor.firstContact')" rows="3" /></label>
      <label><span>{{ t('leadEditor.nextAction') }}</span><input v-model="form.nextAction" :aria-label="t('leadEditor.nextAction')" /></label>
      <label><span>{{ t('leadEditor.dueDate') }}</span><input v-model="form.nextActionDue" :aria-label="t('leadEditor.dueDate')" type="date" /></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:10px}.lead-form{display:grid;grid-template-columns:1fr 1fr;gap:13px}.lead-form label{display:grid;gap:6px;color:var(--crm-text-muted);font-size:10px;font-weight:700}.lead-form label.wide{grid-column:1/-1}.lead-form input,.lead-form select,.lead-form textarea{width:100%;min-height:38px;padding:8px 10px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:8px;outline:0;font:inherit}.lead-form textarea{resize:vertical}.lead-form input:focus,.lead-form select:focus,.lead-form textarea:focus{border-color:var(--crm-teal)}@media(max-width:560px){.lead-form{grid-template-columns:1fr}.lead-form label.wide{grid-column:auto}}
</style>
