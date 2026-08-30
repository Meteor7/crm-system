<script setup lang="ts">
import { reactive, watch } from 'vue'
import type { BuyingRole, ContactDto, CreateStakeholderInput } from '@/types/crm'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'

const props = defineProps<{ accountId: string; contact?: ContactDto | null; contacts: ContactDto[]; busy?: boolean }>()
const emit = defineEmits<{ close: []; submit: [payload: CreateStakeholderInput] }>()
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
  <ModalShell :title="contact ? '编辑关键人' : '新增关键人'" eyebrow="STAKEHOLDER MAP" :busy="busy" @close="$emit('close')" @submit="submit">
    <div class="form-grid">
      <label><span>姓名<RequiredMark :show="!contact" /></span><input v-model="form.name" aria-label="关键人姓名" required /></label><label><span>职位<RequiredMark :show="!contact" /></span><input v-model="form.title" aria-label="关键人职位" required /></label>
      <label><span>部门<RequiredMark :show="!contact" /></span><input v-model="form.department" aria-label="关键人部门" required /></label><label>购买角色<select v-model="form.role" aria-label="购买角色"><option v-for="role in roles" :key="role">{{ role }}</option></select></label>
      <label>影响力<select v-model="form.influence" aria-label="影响力"><option>High</option><option>Medium</option><option>Low</option></select></label><label>关系强度<select v-model="form.relationship" aria-label="关系强度"><option>Strong</option><option>Developing</option><option>Weak</option></select></label>
      <label>汇报对象<select v-model="form.reportsTo" aria-label="汇报对象"><option value="">无 / 未知</option><option v-for="item in contacts.filter((item) => item.id !== contact?.id)" :key="item.id" :value="item.id">{{ item.name }} · {{ item.title }}</option></select></label>
      <label>邮箱<input v-model="form.email" aria-label="关键人邮箱" type="email" placeholder="未知可留空" /></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.form-grid label{display:grid;gap:6px;color:var(--crm-text-muted);font-size:9px;font-weight:700}.form-grid input,.form-grid select{width:100%;min-height:36px;padding:8px 10px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:8px;outline:0}@media(max-width:560px){.form-grid{grid-template-columns:1fr}}
</style>
