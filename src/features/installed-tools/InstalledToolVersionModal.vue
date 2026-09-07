<script setup lang="ts">
import { systemValueLabel } from '@/features/shared/system-labels'
import { computed, ref, watch } from 'vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import { shanghaiDate } from '@/domain/time'
import type { AddInstalledToolVersionRecordInput, InstalledToolDetailDto, InstalledToolVersionChangeType } from '@/types/workspaces'
import { useI18n } from '@/i18n'

const props = defineProps<{ tool: InstalledToolDetailDto; busy?: boolean; error?: string }>()
const emit = defineEmits<{ close: []; submit: [value: AddInstalledToolVersionRecordInput] }>()
const { locale, t } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const types: InstalledToolVersionChangeType[] = ['Software', 'Firmware', 'Operating System', 'Configuration']
const form = ref<AddInstalledToolVersionRecordInput>({ changeDate: shanghaiDate(), changeType: 'Software', toValue: '', reason: '', comment: '' })
const currentValue = computed(() => ({
  Software: props.tool.software,
  Firmware: props.tool.firmware,
  'Operating System': props.tool.operatingSystem,
  Configuration: props.tool.configuration,
}[form.value.changeType] ?? ''))
const invalid = computed(() => !form.value.changeDate || !form.value.toValue.trim() || form.value.toValue.trim() === currentValue.value || !form.value.reason.trim())
watch(() => props.tool.id, () => { form.value = { changeDate: shanghaiDate(), changeType: 'Software', toValue: '', reason: '', comment: '' } })
function submit() {
  emit('submit', { ...form.value, toValue: form.value.toValue.trim(), reason: form.value.reason.trim(), comment: form.value.comment?.trim() })
}
</script>

<template>
  <ModalShell :title="t('installed.versionTitle')" :eyebrow="copy('APPEND-ONLY VERSION AUDIT', '仅追加版本审计')" :submit-label="t('installed.saveVersion')" :busy="busy" :submit-disabled="invalid" @close="emit('close')" @submit="submit">
    <p class="form-note">{{ t('installed.versionAuditHint') }}</p>
    <p v-if="error" class="form-error">{{ error }}</p>
    <div class="form-grid">
      <label><span>{{ t('installed.changeDate') }}<RequiredMark /></span><input v-model="form.changeDate" type="date" required /></label>
      <label><span>{{ t('installed.changeType') }}<RequiredMark /></span><select v-model="form.changeType"><option v-for="item in types" :key="item" :value="item">{{ t('installed.change.' + item) }}</option></select></label>
      <label><span>{{ t('installed.currentValue') }}</span><input :value="systemValueLabel(currentValue, locale) || '—'" disabled /></label>
      <label><span>{{ t('installed.newValue') }}<RequiredMark /></span><input v-model="form.toValue" required /></label>
      <label class="wide"><span>{{ t('installed.changeReason') }}<RequiredMark /></span><textarea v-model="form.reason" rows="3" required /></label>
      <label class="wide"><span>{{ t('installed.additionalNotes') }}</span><textarea v-model="form.comment" rows="2" /></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.form-note,.form-error{margin:0 0 12px;padding:10px;border-radius:8px;font-size:9px}.form-note{color:var(--crm-teal);background:var(--crm-surface-muted)}.form-error{color:var(--crm-danger);background:var(--crm-danger-soft)}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.form-grid label{display:grid;gap:6px}.form-grid span{color:var(--crm-text-muted);font-size:9px;font-weight:700}.form-grid input,.form-grid select,.form-grid textarea{box-sizing:border-box;width:100%;padding:9px 10px;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.form-grid input,.form-grid select{height:38px}.form-grid input:disabled{background:var(--crm-surface-muted)}.wide{grid-column:1/-1}@media(max-width:620px){.form-grid{grid-template-columns:1fr}.wide{grid-column:auto}}
</style>
