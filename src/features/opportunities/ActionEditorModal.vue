<script setup lang="ts">
import { ref } from 'vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import PersonnelSelect from '@/design-system/PersonnelSelect.vue'
import { preferredPersonnelId } from '@/demo/personnel'
import { OPPORTUNITY_ACTION_STATUSES, type CreateOpportunityActionInput, type OpportunityActionDto } from '@/types/workspaces'
import { useI18n } from '@/i18n'
import { salesEnumLabel } from '@/features/shared/sales-i18n'

const props = defineProps<{ action?: OpportunityActionDto | null; defaultOwner: string; busy?: boolean; error?: string }>()
const emit = defineEmits<{ close: []; submit: [value: CreateOpportunityActionInput] }>()
const { t, locale } = useI18n()
const form = ref<CreateOpportunityActionInput>({
  title: props.action?.title ?? '', owner: props.action?.owner ?? preferredPersonnelId('Sales', props.defaultOwner),
  remark: props.action?.remark ?? '',
  due: props.action?.due ?? '2026-07-31', status: props.action?.status ?? 'Open',
})
</script>

<template>
  <ModalShell :title="action ? t('actionEditor.edit') : t('actionEditor.new')" eyebrow="ACTION PLAN" :busy="busy" @close="$emit('close')" @submit="$emit('submit', form)">
    <p v-if="error" class="form-error">{{ error }}</p>
    <div class="action-form-grid">
      <label class="wide"><span>{{ t('actionEditor.title') }}<RequiredMark :show="!action" /></span><input v-model="form.title" :aria-label="t('actionEditor.title')" required /></label>
      <label><span>{{ t('actionEditor.owner') }}<RequiredMark :show="!action" /></span><PersonnelSelect v-model="form.owner" :roles="['Sales', 'Engineer']" :ariaLabel="t('actionEditor.owner')" required /></label>
      <label><span>{{ t('actionEditor.dueDate') }}<RequiredMark :show="!action" /></span><input v-model="form.due" :aria-label="t('actionEditor.dueDate')" type="date" required /></label>
      <label><span>{{ t('detail.status') }}<RequiredMark :show="!action" /></span><select v-model="form.status" :aria-label="t('detail.status')" required><option v-for="item in OPPORTUNITY_ACTION_STATUSES" :key="item" :value="item">{{ salesEnumLabel(item, locale) }}</option></select></label>
      <label><span>{{ t('actionEditor.remark') }}</span><textarea v-model="form.remark" :aria-label="t('actionEditor.remark')" rows="3" maxlength="10000" :placeholder="t('actionEditor.remarkPlaceholder')" /></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:9px}.action-form-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.action-form-grid label{display:grid;align-content:start;gap:6px}.action-form-grid label.wide{grid-column:1/-1}.action-form-grid span{color:var(--crm-text-muted);font-size:9px;font-weight:700}.action-form-grid input,.action-form-grid select{height:38px;padding:0 10px;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.action-form-grid textarea{min-height:80px;resize:vertical;padding:10px;border:1px solid var(--crm-line);border-radius:8px;font:inherit;line-height:1.6}.action-form-grid :focus{border-color:var(--crm-teal);outline:0}@media(max-width:560px){.action-form-grid{grid-template-columns:1fr}.action-form-grid label.wide{grid-column:auto}}
</style>
