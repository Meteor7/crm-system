<script setup lang="ts">
import { ref, watch } from 'vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import ContactPicker from '@/features/contacts/ContactPicker.vue'
import type { ContactSummaryDto } from '@/types/crm'
import { OPPORTUNITY_STAKEHOLDER_INFLUENCES, OPPORTUNITY_STAKEHOLDER_ROLES, OPPORTUNITY_STAKEHOLDER_STANCES, type CreateOpportunityStakeholderInput, type OpportunityStakeholderDto } from '@/types/workspaces'

const props = defineProps<{
  stakeholder?: OpportunityStakeholderDto | null
  contacts: ContactSummaryDto[]
  accountId: string
  selectedContactId?: string
  busy?: boolean
  error?: string
}>()
const emit = defineEmits<{ close: []; submit: [value: CreateOpportunityStakeholderInput]; createContact: [] }>()
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
</script>

<template>
  <ModalShell :title="stakeholder ? '编辑机会关键人' : '新增机会关键人'" eyebrow="BUYING INFLUENCE" :busy="busy" @close="$emit('close')" @submit="$emit('submit', form)">
    <p v-if="error" class="form-error">{{ error }}</p>
    <div class="compact-form-grid">
      <label class="wide"><span>联系人<RequiredMark :show="!stakeholder" /></span><ContactPicker v-model="form.contactId" :contacts="contacts" :account-id="accountId" data-testid="opportunity-contact-picker" :disabled="busy" required @create="emit('createContact')" /></label>
      <label><span>Buying Role</span><select v-model="form.role" aria-label="关键人角色"><option v-for="item in OPPORTUNITY_STAKEHOLDER_ROLES" :key="item">{{ item }}</option></select></label>
      <label><span>Influence</span><select v-model="form.influence" aria-label="关键人影响力"><option v-for="item in OPPORTUNITY_STAKEHOLDER_INFLUENCES" :key="item">{{ item }}</option></select></label>
      <label><span>Attitude</span><select v-model="form.stance" aria-label="关键人态度"><option v-for="item in OPPORTUNITY_STAKEHOLDER_STANCES" :key="item">{{ item }}</option></select></label>
      <label><span>Coverage Evidence<RequiredMark :show="!stakeholder" /></span><input v-model="form.coverage" aria-label="关键人覆盖证据" required /></label>
      <label><span>Win Result</span><input v-model="form.winResult" aria-label="关键人赢单结果" /></label>
      <label><span>Opportunity Notes</span><input v-model="form.opportunityNotes" aria-label="关键人机会备注" /></label>
      <label class="coach"><input v-model="form.isCoach" aria-label="关键人是教练" type="checkbox" /><span>Coach</span></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:9px}.compact-form-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.compact-form-grid label{display:grid;gap:6px}.compact-form-grid label.wide{grid-column:1/-1}.compact-form-grid span{color:var(--crm-text-muted);font-size:9px;font-weight:700}.compact-form-grid input,.compact-form-grid select{height:38px;padding:0 10px;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.compact-form-grid label.coach{display:flex;align-items:center;gap:7px}.compact-form-grid label.coach input{height:auto}.compact-form-grid :focus{border-color:var(--crm-teal);outline:0}@media(max-width:560px){.compact-form-grid{grid-template-columns:1fr}.compact-form-grid label.wide{grid-column:auto}}
</style>
