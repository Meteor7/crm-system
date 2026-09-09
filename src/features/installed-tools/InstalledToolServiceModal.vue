<script setup lang="ts">
import { useLocalizedInput } from '@/i18n/localized-input'
import { systemValueLabel } from '@/features/shared/system-labels'
import { computed, ref } from 'vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import { shanghaiDate } from '@/domain/time'
import type { AddInstalledToolServiceRecordInput, InstalledToolDetailDto, InstalledToolServiceType } from '@/types/workspaces'
import { useI18n } from '@/i18n'

const props = withDefaults(defineProps<{
  tool: InstalledToolDetailDto
  actionOwners: Array<{ id: string; name: string; role: string }>
  busy?: boolean
  error?: string
}>(), { actionOwners: () => [] })
const emit = defineEmits<{ close: []; submit: [value: AddInstalledToolServiceRecordInput] }>()
const { locale, t } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const types: InstalledToolServiceType[] = ['Warranty Activation', 'Preventive Maintenance', 'Corrective Service', 'Remote Support', 'Installation Support', 'Contract Change']
const form = ref<AddInstalledToolServiceRecordInput>({
  serviceDate: shanghaiDate(),
  serviceType: 'Preventive Maintenance',
  result: '',
  openIssues: '无',
  nextAction: '',
  actionOwner: '',
  due: '',
  comment: '',
  warrantyStart: props.tool.warrantyStart,
  warrantyEnd: props.tool.warrantyEnd,
  serviceContract: props.tool.serviceContract,
  pmCycle: props.tool.pmCycle,
})
const validActionOwner = computed(() => props.actionOwners.some((item) => item.id === form.value.actionOwner))
const invalid = computed(() =>
  !form.value.serviceDate || !form.value.result.trim() || !form.value.openIssues.trim()
  || Boolean(form.value.nextAction?.trim()) && (!validActionOwner.value || !form.value.due),
)
function optional(value?: string) { return value?.trim() || undefined }
function submit() {
  emit('submit', {
    ...form.value,
    result: form.value.result.trim(),
    openIssues: openIssuesInput.value.trim(),
    nextAction: optional(form.value.nextAction),
    actionOwner: form.value.nextAction?.trim() ? optional(form.value.actionOwner) : undefined,
    due: form.value.nextAction?.trim() ? optional(form.value.due) : undefined,
    comment: optional(form.value.comment),
    warrantyStart: optional(form.value.warrantyStart),
    warrantyEnd: optional(form.value.warrantyEnd),
    serviceContract: optional(form.value.serviceContract),
    pmCycle: optional(form.value.pmCycle),
  })
}

const openIssuesInput = useLocalizedInput(() => form.value.openIssues, (value) => { form.value.openIssues = value }, (value) => systemValueLabel(value, locale.value))
const serviceContractInput = useLocalizedInput(() => form.value.serviceContract, (value) => { form.value.serviceContract = value }, (value) => systemValueLabel(value, locale.value))
const pmCycleInput = useLocalizedInput(() => form.value.pmCycle, (value) => { form.value.pmCycle = value }, (value) => systemValueLabel(value, locale.value))
</script>

<template>
  <ModalShell :title="t('installed.serviceTitle')" :eyebrow="copy('APPEND-ONLY SERVICE AUDIT', '仅追加服务审计')" :submit-label="t('installed.saveService')" :busy="busy" :submit-disabled="invalid" @close="emit('close')" @submit="submit">
    <p v-if="error" class="form-error">{{ error }}</p>
    <div class="form-grid">
      <label><span>{{ t('installed.serviceDate') }}<RequiredMark /></span><input v-model="form.serviceDate" type="date" required /></label>
      <label><span>{{ t('installed.serviceType') }}<RequiredMark /></span><select v-model="form.serviceType" required><option v-for="item in types" :key="item" :value="item">{{ t('installed.type.' + item) }}</option></select></label>
      <label class="wide"><span>{{ t('installed.handlingResult') }}<RequiredMark /></span><textarea v-model="form.result" rows="3" required /></label>
      <label class="wide"><span>{{ t('installed.openIssues') }}<RequiredMark /></span><textarea v-model="openIssuesInput" rows="2" required /></label>
      <label class="wide"><span>{{ t('installed.nextAction') }}</span><input v-model="form.nextAction" :aria-label="t('installed.nextAction')" /></label>
      <label><span>{{ t('installed.actionOwner') }}<RequiredMark v-if="form.nextAction?.trim()" /></span><select v-model="form.actionOwner" :aria-label="t('installed.actionOwner')"><option value="">{{ t('installed.selectValidPerson') }}</option><option v-for="owner in actionOwners" :key="owner.id" :value="owner.id">{{ owner.name }} · {{ owner.role }}</option></select></label>
      <label><span>{{ t('installed.dueDate') }}<RequiredMark v-if="form.nextAction?.trim()" /></span><input v-model="form.due" type="date" :aria-label="t('installed.dueDate')" /></label>
      <label><span>{{ t('installed.warrantyStart') }}</span><input v-model="form.warrantyStart" type="date" /></label>
      <label><span>{{ t('installed.warrantyEnd') }}</span><input v-model="form.warrantyEnd" type="date" /></label>
      <label><span>{{ t('installed.serviceContract') }}</span><input v-model="serviceContractInput" /></label>
      <label><span>{{ t('installed.pmCycle') }}</span><input v-model="pmCycleInput" /></label>
      <label class="wide"><span>{{ t('installed.optionalNotes') }}</span><textarea v-model="form.comment" rows="2" /></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:9px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.form-grid label{display:grid;gap:6px}.form-grid span{color:var(--crm-text-muted);font-size:9px;font-weight:700}.form-grid input,.form-grid select,.form-grid textarea{box-sizing:border-box;width:100%;padding:9px 10px;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.form-grid input,.form-grid select{height:38px}.wide{grid-column:1/-1}@media(max-width:620px){.form-grid{grid-template-columns:1fr}.wide{grid-column:auto}}
</style>
