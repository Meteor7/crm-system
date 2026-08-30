<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import type { MultipartFilePart } from '@/api/binary-transport'
import type { AccountSummaryDto, ContactSummaryDto, CreateVisitInput, VisitDto } from '@/types/crm'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import PersonnelSelect from '@/design-system/PersonnelSelect.vue'
import ContactPicker from '@/features/contacts/ContactPicker.vue'
import { addIsoDateDays, shanghaiDate } from '@/domain/time'
import { preferredPersonnelId } from '@/demo/personnel'

const props = withDefaults(defineProps<{ mode: 'create' | 'review'; visit?: VisitDto | null; accounts: AccountSummaryDto[]; contacts?: ContactSummaryDto[]; initialAccountId?: string; initialPrimaryContactId?: string; initialOpportunityId?: string; busy?: boolean }>(), { contacts: () => [], initialAccountId: '', initialPrimaryContactId: '', initialOpportunityId: '' })
const emit = defineEmits<{ close: []; submit: [payload: CreateVisitInput, file?: MultipartFilePart]; 'create-contact': [accountId: string] }>()
const defaultDate = shanghaiDate()
const defaultDue = addIsoDateDays(defaultDate, 1)
const form = reactive({ accountId: '', primaryContactId: '', subject: '', date: defaultDate, visitType: 'On-site' as VisitDto['type'], owner: '', objective: '', outcome: '', nextAction: '', actionOwner: '', due: defaultDue })
const meetingFile = ref<File | null>(null)

watch(() => [props.mode, props.visit, props.accounts, props.initialAccountId, props.initialPrimaryContactId] as const, () => {
  form.accountId = props.visit?.accountId || props.initialAccountId || props.accounts[0]?.id || ''
  form.primaryContactId = props.visit?.primaryContactId || props.initialPrimaryContactId || ''
  form.subject = props.visit?.subject ?? ''
  form.date = props.visit?.date ?? defaultDate
  form.visitType = props.visit?.type ?? 'On-site'
  form.owner = props.visit?.owner ?? props.accounts.find((item) => item.id === form.accountId)?.owner ?? preferredPersonnelId('Sales', '')
  form.objective = props.visit?.objective ?? '确认客户需求和下一步计划'
  form.outcome = props.visit?.outcome ?? ''
  form.nextAction = props.visit?.nextAction ?? ''
  form.actionOwner = props.visit?.actionOwner || form.owner
  form.due = props.visit?.due ?? defaultDue
}, { immediate: true })

watch(() => form.accountId, () => {
  if (!props.contacts.some((contact) => contact.id === form.primaryContactId && contact.accountId === form.accountId && contact.status === 'Active')) {
    form.primaryContactId = ''
  }
})

function submit() {
  if (props.mode === 'create') {
    const file = meetingFile.value
    emit('submit', { accountId: form.accountId, ...(form.primaryContactId ? { primaryContactId: form.primaryContactId } : {}), ...(props.initialOpportunityId ? { opportunityId: props.initialOpportunityId } : {}), subject: form.subject, date: form.date, type: form.visitType, owner: form.owner, objective: form.objective }, file ? { blob: file, fileName: file.name, mimeType: file.type || 'application/octet-stream', size: file.size } : undefined)
  }
  else emit('submit', {} as CreateVisitInput)
}

function selectMeetingFile(event: Event) {
  meetingFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
}
</script>

<template>
  <ModalShell :title="mode === 'create' ? '&#x65B0;&#x5EFA;&#x5BA2;&#x6237;&#x62DC;&#x8BBF;' : '&#x7ECF;&#x7406;&#x5BA1;&#x6838;&#x62DC;&#x8BBF;'" eyebrow="VISIT WORKFLOW" :busy="busy" @close="$emit('close')" @submit="submit">
    <div v-if="mode === 'create'" class="form-grid">
      <label><span>&#x5BA2;&#x6237;<RequiredMark /></span><select v-model="form.accountId" aria-label="&#x62DC;&#x8BBF;&#x5BA2;&#x6237;" required><option v-for="account in accounts" :key="account.id" :value="account.id">{{ account.name }}</option></select></label>
      <label>&#x4E3B;&#x8981;&#x8054;&#x7CFB;&#x4EBA;<ContactPicker v-model="form.primaryContactId" :contacts="contacts" :account-id="form.accountId" @create="emit('create-contact', form.accountId)" /></label>
      <label>&#x62DC;&#x8BBF;&#x65B9;&#x5F0F;<select v-model="form.visitType" aria-label="&#x62DC;&#x8BBF;&#x65B9;&#x5F0F;"><option>On-site</option><option>Video</option><option>Phone</option></select></label>
      <label class="full"><span>&#x62DC;&#x8BBF;&#x4E3B;&#x9898;<RequiredMark /></span><input v-model="form.subject" aria-label="&#x62DC;&#x8BBF;&#x4E3B;&#x9898;" required /></label>
      <label><span>&#x65E5;&#x671F;<RequiredMark /></span><input v-model="form.date" aria-label="&#x62DC;&#x8BBF;&#x65E5;&#x671F;" type="date" required /></label>
      <label><span>&#x8D1F;&#x8D23;&#x4EBA;<RequiredMark /></span><PersonnelSelect v-model="form.owner" :roles="['Sales']" :ariaLabel="'\u62dc\u8bbf\u8d1f\u8d23\u4eba'" required /></label>
      <label class="full"><span>&#x62DC;&#x8BBF;&#x76EE;&#x6807;<RequiredMark /></span><textarea v-model="form.objective" aria-label="&#x62DC;&#x8BBF;&#x76EE;&#x6807;" required /></label>
      <label class="full"><span>&#x62DC;&#x8BBF;&#x8BB0;&#x5F55;&#x6587;&#x4EF6;&#xFF08;&#x53EF;&#x9009;&#xFF09;</span><input aria-label="&#x62DC;&#x8BBF;&#x8BB0;&#x5F55;&#x6587;&#x4EF6;" type="file" @change="selectMeetingFile" /><small>&#x63D0;&#x4EA4;&#x6587;&#x4EF6;&#x540E;&#x81EA;&#x52A8;&#x89C6;&#x4E3A;&#x5B8C;&#x6210;&#x62DC;&#x8BBF;&#xFF1B;&#x539F;&#x6587;&#x4EF6;&#x4F1A;&#x5F52;&#x6863;&#x5E76;&#x5C3D;&#x529B;&#x89E3;&#x6790;&#x3002;</small></label>
    </div>
    <div v-else class="review-copy"><strong>{{ visit?.subject }}</strong><p>&#x5BA1;&#x6838;&#x540E;&#x72B6;&#x6001;&#x5C06;&#x53D8;&#x4E3A;&#x201C;&#x7BA1;&#x7406;&#x8005;&#x5DF2;&#x5BA1;&#x6838;&#x201D;&#xFF0C;&#x62DC;&#x8BBF;&#x8BB0;&#x5F55;&#x4ECD;&#x53EF;&#x8FFD;&#x6EAF;&#x3002;</p></div>
  </ModalShell>
</template>

<style scoped>
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.form-grid label{display:grid;gap:6px;color:var(--crm-text-muted);font-size:9px;font-weight:700}.form-grid .full{grid-column:1/-1}.form-grid input,.form-grid select,.form-grid textarea{width:100%;min-height:36px;padding:8px 10px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:8px;outline:0}.form-grid textarea{min-height:82px;resize:vertical}.form-grid small{font-weight:500}.review-copy{padding:10px;color:var(--crm-text)}.review-copy p{color:var(--crm-text-muted);font-size:11px}@media(max-width:560px){.form-grid{grid-template-columns:1fr}.form-grid .full{grid-column:auto}}
</style>
