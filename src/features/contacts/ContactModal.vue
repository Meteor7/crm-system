<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { Trash2 } from '@lucide/vue'
import type { AccountSummaryDto, ContactDto, ContactStatus, ContactSummaryDto, CreateContactInput, SiteDto } from '@/types/crm'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import PersonnelSelect from '@/design-system/PersonnelSelect.vue'

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
  <ModalShell :title="contact ? '编辑联系人' : '新增联系人'" eyebrow="CONTACT MASTER" :busy="busy" @close="emit('close')" @submit="submit">
    <p v-if="error" class="form-error">{{ error }}</p>
    <div class="contact-form">
      <label><span>姓名<RequiredMark :show="!contact" /></span><input v-model="form.name" aria-label="联系人姓名" required /></label>
      <label><span>所属客户<RequiredMark :show="!contact" /></span><select v-model="form.accountId" aria-label="所属客户" :disabled="Boolean(fixedAccountId)" required><option v-for="account in accounts" :key="account.id" :value="account.id">{{ account.name }}</option></select></label>
      <label><span>所属厂区</span><select v-model="form.siteId" aria-label="所属厂区"><option value="">未指定</option><option v-for="site in accountSites" :key="site.id" :value="site.id" :data-site-option="site.id">{{ site.name }}</option></select></label>
      <label><span>职位<RequiredMark :show="!contact" /></span><input v-model="form.title" aria-label="联系人职位" required /></label>
      <label><span>部门<RequiredMark :show="!contact" /></span><input v-model="form.department" aria-label="联系人部门" required /></label>
      <label><span>电话</span><input v-model="form.phone" aria-label="联系人电话" /></label>
      <label><span>邮箱</span><input v-model="form.email" aria-label="联系人邮箱" type="email" /></label>
      <label><span>直属上司</span><select v-model="form.reportsToContactId" aria-label="直属上司"><option value="">未指定</option><option v-for="item in reportingOptions" :key="item.id" :value="item.id" :data-reports-to-option="item.id">{{ item.name }} · {{ item.title }}</option></select></label>
      <label><span>关系强度</span><select v-model="form.relationship" aria-label="关系强度"><option>Strong</option><option>Developing</option><option>Weak</option></select></label>
      <label><span>负责人<RequiredMark :show="!contact" /></span><PersonnelSelect v-model="form.owner" :roles="['Sales']" :ariaLabel="'\u8054\u7cfb\u4eba\u8d1f\u8d23\u4eba'" required /></label>
      <label class="wide"><span>状态</span><select v-model="form.status" aria-label="联系人状态"><option>Active</option><option>Left Company</option><option>Archived</option></select></label>
    </div>
    <button
      v-if="contact && canDelete"
      class="delete-contact-button"
      type="button"
      data-testid="delete-contact-from-edit"
      :disabled="busy"
      @click="emit('delete')"
    >
      <Trash2 :size="14" />删除联系人
    </button>
  </ModalShell>
</template>

<style scoped>
.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:10px}.contact-form{display:grid;grid-template-columns:1fr 1fr;gap:13px}.contact-form label{display:grid;gap:6px;color:var(--crm-text-muted);font-size:10px;font-weight:700}.contact-form label.wide{grid-column:1/-1}.contact-form input,.contact-form select{width:100%;min-height:38px;padding:8px 10px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:8px;outline:0}.contact-form input:focus,.contact-form select:focus{border-color:var(--crm-teal)}.contact-form select:disabled{color:var(--crm-text-muted);background:var(--crm-surface)}.delete-contact-button{display:flex;align-items:center;gap:6px;margin-top:16px;padding:9px 11px;color:var(--crm-danger);background:var(--crm-danger-soft);border:1px solid rgba(174,59,59,.24);border-radius:8px;font-weight:700;cursor:pointer}.delete-contact-button:disabled{opacity:.55;cursor:not-allowed}@media(max-width:560px){.contact-form{grid-template-columns:1fr}.contact-form label.wide{grid-column:auto}}
</style>
