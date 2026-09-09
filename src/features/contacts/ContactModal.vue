<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { Trash2 } from '@lucide/vue'
import type { AccountSummaryDto, ContactDto, ContactStatus, ContactSummaryDto, CreateContactInput, SiteDto } from '@/types/crm'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import PersonnelSelect from '@/design-system/PersonnelSelect.vue'
import { useI18n } from '@/i18n'
import { contactStatusLabel, salesEnumLabel } from '@/features/shared/sales-i18n'

const props = defineProps<{
  contact?: ContactDto | null
  accounts: AccountSummaryDto[]
  sites: Array<SiteDto & { accountId: string }>
  contacts: ContactSummaryDto[]
  fixedAccountId?: string
  busy?: boolean
  error?: string
  canDelete?: boolean
}>()
const emit = defineEmits<{ close: []; submit: [payload: CreateContactInput]; delete: [] }>()
const { locale, t } = useI18n()

const form = reactive({
  accountId: '',
  siteId: '',
  name: '',
  title: '',
  department: '',
  phone: '',
  email: '',
  reportsToContactId: '',
  relationship: 'Developing' as ContactDto['relationship'],
  owner: '',
  status: 'Active' as ContactStatus,
})

const selectedAccount = computed(() => props.accounts.find((item) => item.id === form.accountId))
const accountSites = computed(() => props.sites.filter((site) => site.accountId === form.accountId))
const reportingOptions = computed(() => props.contacts.filter((item) =>
  item.accountId === form.accountId && item.id !== props.contact?.id && item.status === 'Active',
))

function resetForm() {
  const accountId = props.fixedAccountId ?? props.contact?.accountId ?? props.accounts[0]?.id ?? ''
  form.accountId = accountId
  form.siteId = props.contact?.siteId ?? ''
  form.name = props.contact?.name ?? ''
  form.title = props.contact?.title ?? ''
  form.department = props.contact?.department ?? ''
  form.phone = props.contact?.phone ?? ''
  form.email = props.contact?.email ?? ''
  form.reportsToContactId = props.contact?.reportsToContactId ?? ''
  form.relationship = props.contact?.relationship ?? 'Developing'
  form.owner = props.contact?.owner ?? props.accounts.find((item) => item.id === accountId)?.owner ?? ''
  form.status = props.contact?.status ?? 'Active'
}

watch(() => [props.contact, props.fixedAccountId, props.accounts] as const, resetForm, { immediate: true })
watch(() => form.accountId, () => {
  if (!accountSites.value.some((item) => item.id === form.siteId)) form.siteId = ''
  if (!reportingOptions.value.some((item) => item.id === form.reportsToContactId)) form.reportsToContactId = ''
  if (!props.contact) form.owner = selectedAccount.value?.owner ?? form.owner
})

function submit() {
  emit('submit', {
    accountId: form.accountId,
    ...(form.siteId ? { siteId: form.siteId } : {}),
    name: form.name,
    title: form.title,
    department: form.department,
    ...(form.phone ? { phone: form.phone } : {}),
    ...(form.email ? { email: form.email } : {}),
    ...(form.reportsToContactId ? { reportsToContactId: form.reportsToContactId } : {}),
    relationship: form.relationship,
    owner: form.owner,
    status: form.status,
  })
}
</script>

<template>
  <ModalShell :title="contact ? (locale === 'en-US' ? 'Edit contact' : '编辑联系人') : (locale === 'en-US' ? 'New contact' : '新增联系人')" eyebrow="CONTACT MASTER" :busy="busy" @close="emit('close')" @submit="submit">
    <p v-if="error" class="form-error">{{ error }}</p>
    <div class="contact-form">
      <label><span>{{ locale === 'en-US' ? 'Name' : '姓名' }}<RequiredMark :show="!contact" /></span><input v-model="form.name" :aria-label="locale === 'en-US' ? 'Contact name' : '联系人姓名'" required /></label>
      <label><span>{{ locale === 'en-US' ? 'Account' : '所属客户' }}<RequiredMark :show="!contact" /></span><select v-model="form.accountId" :aria-label="locale === 'en-US' ? 'Account' : '所属客户'" :disabled="Boolean(fixedAccountId)" required><option v-for="account in accounts" :key="account.id" :value="account.id">{{ account.name }}</option></select></label>
      <label><span>{{ locale === 'en-US' ? 'Site' : '所属厂区' }}</span><select v-model="form.siteId" :aria-label="locale === 'en-US' ? 'Site' : '所属厂区'"><option value="">{{ t('detail.notSpecified') }}</option><option v-for="site in accountSites" :key="site.id" :value="site.id" :data-site-option="site.id">{{ site.name }}</option></select></label>
      <label><span>{{ locale === 'en-US' ? 'Title' : '职位' }}<RequiredMark :show="!contact" /></span><input v-model="form.title" :aria-label="locale === 'en-US' ? 'Contact title' : '联系人职位'" required /></label>
      <label><span>{{ locale === 'en-US' ? 'Department' : '部门' }}<RequiredMark :show="!contact" /></span><input v-model="form.department" :aria-label="locale === 'en-US' ? 'Contact department' : '联系人部门'" required /></label>
      <label><span>{{ t('detail.phone') }}</span><input v-model="form.phone" :aria-label="locale === 'en-US' ? 'Contact phone' : '联系人电话'" /></label>
      <label><span>{{ t('detail.email') }}</span><input v-model="form.email" :aria-label="locale === 'en-US' ? 'Contact email' : '联系人邮箱'" type="email" /></label>
      <label><span>{{ t('detail.manager') }}</span><select v-model="form.reportsToContactId" :aria-label="t('detail.manager')"><option value="">{{ t('detail.notSpecified') }}</option><option v-for="item in reportingOptions" :key="item.id" :value="item.id" :data-reports-to-option="item.id">{{ item.name }} · {{ item.title }}</option></select></label>
      <label><span>{{ t('detail.relationship') }}<RequiredMark :show="!contact" /></span><select v-model="form.relationship" :aria-label="t('detail.relationship')" required><option v-for="item in ['Strong', 'Developing', 'Weak']" :key="item" :value="item">{{ salesEnumLabel(item, locale) }}</option></select></label>
      <label><span>{{ t('detail.owner') }}<RequiredMark :show="!contact" /></span><PersonnelSelect v-model="form.owner" :roles="['Sales']" :ariaLabel="locale === 'en-US' ? 'Contact owner' : '联系人负责人'" required /></label>
      <label class="wide"><span>{{ t('detail.status') }}<RequiredMark :show="!contact" /></span><select v-model="form.status" :aria-label="t('detail.contactStatus')" required><option v-for="item in ['Active', 'Left Company', 'Archived']" :key="item" :value="item">{{ contactStatusLabel(item, locale) }}</option></select></label>
    </div>
    <button
      v-if="contact && canDelete"
      class="delete-contact-button"
      type="button"
      data-testid="delete-contact-from-edit"
      :disabled="busy"
      @click="emit('delete')"
    >
      <Trash2 :size="14" />{{ locale === 'en-US' ? 'Delete contact' : '删除联系人' }}
    </button>
  </ModalShell>
</template>

<style scoped>
.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:10px}.contact-form{display:grid;grid-template-columns:1fr 1fr;gap:13px}.contact-form label{display:grid;gap:6px;color:var(--crm-text-muted);font-size:10px;font-weight:700}.contact-form label.wide{grid-column:1/-1}.contact-form input,.contact-form select{width:100%;min-height:38px;padding:8px 10px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:8px;outline:0}.contact-form input:focus,.contact-form select:focus{border-color:var(--crm-teal)}.contact-form select:disabled{color:var(--crm-text-muted);background:var(--crm-surface)}.delete-contact-button{display:flex;align-items:center;gap:6px;margin-top:16px;padding:9px 11px;color:var(--crm-danger);background:var(--crm-danger-soft);border:1px solid rgba(174,59,59,.24);border-radius:8px;font-weight:700;cursor:pointer}.delete-contact-button:disabled{opacity:.55;cursor:not-allowed}@media(max-width:560px){.contact-form{grid-template-columns:1fr}.contact-form label.wide{grid-column:auto}}
</style>
