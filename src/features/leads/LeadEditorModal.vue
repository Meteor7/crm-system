<script setup lang="ts">
import { reactive, watch } from 'vue'
import type { CreateLeadInput, LeadDto, LeadSource, LeadStatus } from '@/types/crm'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import PersonnelSelect from '@/design-system/PersonnelSelect.vue'
import { preferredPersonnelId } from '@/demo/personnel'

const props = defineProps<{ lead?: LeadDto | null; busy?: boolean; error?: string }>()
const emit = defineEmits<{ close: []; submit: [payload: CreateLeadInput] }>()

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
  <ModalShell :title="lead ? '编辑 Lead' : '新增 Lead'" eyebrow="LEAD QUALIFICATION" :busy="busy" @close="emit('close')" @submit="submit">
    <p v-if="error" class="form-error">{{ error }}</p>
    <div class="lead-form">
      <label><span>姓名<RequiredMark :show="!lead" /></span><input v-model="form.name" aria-label="Lead 姓名" required /></label>
      <label><span>公司<RequiredMark :show="!lead" /></span><input v-model="form.company" aria-label="Lead 公司" required /></label>
      <label><span>职位<RequiredMark :show="!lead" /></span><input v-model="form.title" aria-label="Lead 职位" required /></label>
      <label><span>负责人<RequiredMark :show="!lead" /></span><PersonnelSelect v-model="form.owner" :roles="['Sales']" :ariaLabel="'Lead \u8d1f\u8d23\u4eba'" required /></label>
      <label><span>电话</span><input v-model="form.phone" aria-label="Lead 电话" /></label>
      <label><span>邮箱</span><input v-model="form.email" aria-label="Lead 邮箱" type="email" /></label>
      <label><span>来源</span><select v-model="form.source" aria-label="Lead 来源"><option>Website</option><option>Trade Show</option><option>Partner Referral</option><option>Outbound</option><option>Customer Referral</option><option>Other</option></select></label>
      <label><span>状态</span><select v-model="form.status" aria-label="Lead 状态"><option>New</option><option>Working</option><option>Qualified</option><option>Nurturing</option><option>Disqualified</option></select></label>
      <label class="wide"><span>初步兴趣</span><input v-model="form.interest" aria-label="Lead 初步兴趣" /></label>
      <label class="wide"><span>首次联系备注</span><textarea v-model="form.firstContactNote" aria-label="Lead 首次联系备注" rows="3" /></label>
      <label><span>下一步</span><input v-model="form.nextAction" aria-label="Lead 下一步" /></label>
      <label><span>到期日</span><input v-model="form.nextActionDue" aria-label="Lead 到期日" type="date" /></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:10px}.lead-form{display:grid;grid-template-columns:1fr 1fr;gap:13px}.lead-form label{display:grid;gap:6px;color:var(--crm-text-muted);font-size:10px;font-weight:700}.lead-form label.wide{grid-column:1/-1}.lead-form input,.lead-form select,.lead-form textarea{width:100%;min-height:38px;padding:8px 10px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:8px;outline:0;font:inherit}.lead-form textarea{resize:vertical}.lead-form input:focus,.lead-form select:focus,.lead-form textarea:focus{border-color:var(--crm-teal)}@media(max-width:560px){.lead-form{grid-template-columns:1fr}.lead-form label.wide{grid-column:auto}}
</style>
