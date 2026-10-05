<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { MultipartFilePart } from '@/api/binary-transport'
import type { AccountSummaryDto, ContactSummaryDto, CreateVisitInput, UpdateVisitInput, VisitDto } from '@/types/crm'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import PersonnelSelect from '@/design-system/PersonnelSelect.vue'
import ContactPicker from '@/features/contacts/ContactPicker.vue'
import { addIsoDateDays, shanghaiDate } from '@/domain/time'
import { preferredPersonnelId } from '@/demo/personnel'
import { useOwnOwnerOnly } from '@/stores/signed-in-user'
import { useI18n } from '@/i18n'

const props = withDefaults(defineProps<{ mode: 'create' | 'review' | 'edit'; visit?: VisitDto | null; accounts: AccountSummaryDto[]; contacts?: ContactSummaryDto[]; initialAccountId?: string; initialPrimaryContactId?: string; initialOpportunityId?: string; busy?: boolean; error?: string; requestId?: string; conflict?: boolean }>(), { contacts: () => [], initialAccountId: '', initialPrimaryContactId: '', initialOpportunityId: '', error: '', requestId: '' })
const emit = defineEmits<{ close: []; submit: [payload: CreateVisitInput | UpdateVisitInput, file?: MultipartFilePart]; 'create-contact': [accountId: string]; reload: [] }>()
const { locale, t } = useI18n()
const ownOwnerOnly = useOwnOwnerOnly()
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
  form.owner = props.visit?.owner ?? (ownOwnerOnly.value || props.accounts.find((item) => item.id === form.accountId)?.owner || preferredPersonnelId('Sales', ''))
  form.objective = props.visit?.objective ?? t('visitModal.objectiveDefault')
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
  else if (props.mode === 'edit') {
    emit('submit', { subject: form.subject, date: form.date, type: form.visitType, owner: form.owner, objective: form.objective })
  }
  else emit('submit', {} as CreateVisitInput)
}

const title = computed(() => props.mode === 'create' ? t('visitModal.createTitle') : props.mode === 'edit' ? t('visitModal.editTitle') : t('visitModal.reviewTitle'))

function selectMeetingFile(event: Event) {
  meetingFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
}
</script>

<template>
  <ModalShell :title="title" eyebrow="VISIT WORKFLOW" :busy="busy" :cancel-label="t('common.cancel')" :close-label="t('common.close')" :submit-label="t('common.saveAndContinue')" :busy-label="t('common.processing')" @close="$emit('close')" @submit="submit">
    <p v-if="error" class="modal-error" role="alert">
      <span>{{ error }}<small v-if="requestId">{{ locale === 'en-US' ? 'Request ID' : '请求编号' }} {{ requestId }}</small></span>
      <button v-if="conflict" class="secondary-button" type="button" data-reload-visit :disabled="busy" @click="emit('reload')">{{ t('visitModal.reloadLatest') }}</button>
    </p>
    <div v-if="mode !== 'review'" class="form-grid">
      <label v-if="mode === 'create'"><span>{{ t('visitModal.account') }}<RequiredMark /></span><select v-model="form.accountId" :aria-label="t('visitModal.accountAria')" required><option v-for="account in accounts" :key="account.id" :value="account.id">{{ account.name }}</option></select></label>
      <label v-if="mode === 'create'">{{ t('visitModal.primaryContact') }}<ContactPicker v-model="form.primaryContactId" :contacts="contacts" :account-id="form.accountId" @create="emit('create-contact', form.accountId)" /></label>
      <label><span>{{ t('visitModal.visitType') }}<RequiredMark /></span><select v-model="form.visitType" :aria-label="t('visitModal.visitTypeAria')" required><option value="On-site">{{ t('visitModal.onSite') }}</option><option value="Video">{{ t('visitModal.video') }}</option><option value="Phone">{{ t('visitModal.phone') }}</option></select></label>
      <label class="full"><span>{{ t('visitModal.subject') }}<RequiredMark /></span><input v-model="form.subject" :aria-label="t('visitModal.subjectAria')" required /></label>
      <label><span>{{ t('visitModal.date') }}<RequiredMark /></span><input v-model="form.date" :aria-label="t('visitModal.dateAria')" type="date" required /></label>
      <label><span>{{ t('visitModal.owner') }}<RequiredMark /></span><PersonnelSelect owner v-model="form.owner" :roles="['Sales']" :ariaLabel="t('visitModal.ownerAria')" required /></label>
      <label class="full"><span>{{ t('visitModal.objective') }}<RequiredMark /></span><textarea v-model="form.objective" :aria-label="t('visitModal.objectiveAria')" required /></label>
      <label v-if="mode === 'create'" class="full"><span>{{ t('visitModal.recordFile') }}</span><input :aria-label="t('visitModal.recordFileAria')" type="file" @change="selectMeetingFile" /><small>{{ t('visitModal.recordHint') }}</small></label>
    </div>
    <div v-else class="review-copy"><strong>{{ visit?.subject }}</strong><p>{{ t('visitModal.reviewMessage') }}</p></div>
  </ModalShell>
</template>

<style scoped>
.modal-error{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:0 0 13px;padding:10px 12px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:10px;font-weight:700;line-height:1.6}.modal-error span{display:grid;gap:4px}.modal-error button{flex:0 0 auto}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.form-grid label{display:grid;gap:6px;color:var(--crm-text-muted);font-size:9px;font-weight:700}.form-grid .full{grid-column:1/-1}.form-grid input,.form-grid select,.form-grid textarea{width:100%;min-height:36px;padding:8px 10px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:8px;outline:0}.form-grid textarea{min-height:82px;resize:vertical}.form-grid small{font-weight:500}.review-copy{padding:10px;color:var(--crm-text)}.review-copy p{color:var(--crm-text-muted);font-size:11px}@media(max-width:560px){.form-grid{grid-template-columns:1fr}.form-grid .full{grid-column:auto}}
</style>
