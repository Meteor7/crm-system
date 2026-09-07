<script setup lang="ts">
import { reactive, watch } from 'vue'
import type { BuyingRole, ContactDto, CreateStakeholderInput } from '@/types/crm'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import { useI18n } from '@/i18n'

const props = defineProps<{ accountId: string; contact?: ContactDto | null; contacts: ContactDto[]; busy?: boolean }>()
const emit = defineEmits<{ close: []; submit: [payload: CreateStakeholderInput] }>()
const { t } = useI18n()
const roles: BuyingRole[] = ['Decision Maker', 'Economic Buyer', 'Champion', 'Technical Champion', 'Technical Evaluator', 'Procurement', 'Influencer', 'Blocker', 'User']
const form = reactive({ name: '', title: '', department: '', role: 'User' as BuyingRole, influence: 'Medium' as 'High' | 'Medium' | 'Low', relationship: 'Developing' as ContactDto['relationship'], reportsTo: '', email: '' })

watch(() => props.contact, (contact) => {
  form.name = contact?.name ?? ''; form.title = contact?.title ?? ''; form.department = contact?.department ?? ''
  form.role = contact?.role ?? 'User'; form.influence = contact?.influence ?? 'Medium'; form.relationship = contact?.relationship ?? 'Developing'
  form.reportsTo = contact?.reportsTo ?? ''; form.email = contact?.email ?? ''
}, { immediate: true })

function submit() {
  emit('submit', { accountId: props.accountId, name: form.name, title: form.title, department: form.department, role: form.role, influence: form.influence, relationship: form.relationship, ...(form.reportsTo ? { reportsTo: form.reportsTo } : {}), ...(form.email ? { email: form.email } : {}) })
}
</script>

<template>
  <ModalShell :title="contact ? t('stakeholder.edit') : t('stakeholder.new')" eyebrow="STAKEHOLDER MAP" :busy="busy" @close="$emit('close')" @submit="submit">
    <div class="form-grid">
      <label><span>{{ t('stakeholder.name') }}<RequiredMark :show="!contact" /></span><input v-model="form.name" :aria-label="t('stakeholder.name')" required /></label><label><span>{{ t('stakeholder.title') }}<RequiredMark :show="!contact" /></span><input v-model="form.title" :aria-label="t('stakeholder.title')" required /></label>
      <label><span>{{ t('stakeholder.department') }}<RequiredMark :show="!contact" /></span><input v-model="form.department" :aria-label="t('stakeholder.department')" required /></label><label>{{ t('stakeholder.role') }}<select v-model="form.role" :aria-label="t('stakeholder.role')"><option v-for="role in roles" :key="role">{{ role }}</option></select></label>
      <label>{{ t('stakeholder.influence') }}<select v-model="form.influence" :aria-label="t('stakeholder.influence')"><option>High</option><option>Medium</option><option>Low</option></select></label><label>{{ t('stakeholder.relationship') }}<select v-model="form.relationship" :aria-label="t('stakeholder.relationship')"><option>Strong</option><option>Developing</option><option>Weak</option></select></label>
      <label>{{ t('stakeholder.reportsTo') }}<select v-model="form.reportsTo" :aria-label="t('stakeholder.reportsTo')"><option value="">{{ t('detail.notSpecified') }}</option><option v-for="item in contacts.filter((item) => item.id !== contact?.id)" :key="item.id" :value="item.id">{{ item.name }} · {{ item.title }}</option></select></label>
      <label>{{ t('detail.email') }}<input v-model="form.email" :aria-label="t('detail.email')" type="email" :placeholder="t('stakeholder.emailPlaceholder')" /></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.form-grid label{display:grid;gap:6px;color:var(--crm-text-muted);font-size:9px;font-weight:700}.form-grid input,.form-grid select{width:100%;min-height:36px;padding:8px 10px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:8px;outline:0}@media(max-width:560px){.form-grid{grid-template-columns:1fr}}
</style>
