<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import { shanghaiDate } from '@/domain/time'
import type { AddInstalledToolVersionRecordInput, InstalledToolDetailDto, InstalledToolVersionChangeType } from '@/types/workspaces'

const props = defineProps<{ tool: InstalledToolDetailDto; busy?: boolean; error?: string }>()
const emit = defineEmits<{ close: []; submit: [value: AddInstalledToolVersionRecordInput] }>()
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
  <ModalShell title="新增版本 / 配置记录" eyebrow="APPEND-ONLY VERSION AUDIT" submit-label="保存变更记录" :busy="busy" :submit-disabled="invalid" @close="emit('close')" @submit="submit">
    <p class="form-note">原值由服务器读取并写入审计记录，不能由前端指定。</p>
    <p v-if="error" class="form-error">{{ error }}</p>
    <div class="form-grid">
      <label><span>变更日期<RequiredMark /></span><input v-model="form.changeDate" type="date" required /></label>
      <label><span>变更类型<RequiredMark /></span><select v-model="form.changeType"><option v-for="item in types" :key="item" :value="item">{{ item }}</option></select></label>
      <label><span>当前值</span><input :value="currentValue || '—'" disabled /></label>
      <label><span>新值<RequiredMark /></span><input v-model="form.toValue" required /></label>
      <label class="wide"><span>变更原因<RequiredMark /></span><textarea v-model="form.reason" rows="3" required /></label>
      <label class="wide"><span>补充说明</span><textarea v-model="form.comment" rows="2" /></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.form-note,.form-error{margin:0 0 12px;padding:10px;border-radius:8px;font-size:9px}.form-note{color:var(--crm-teal);background:var(--crm-surface-muted)}.form-error{color:var(--crm-danger);background:var(--crm-danger-soft)}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.form-grid label{display:grid;gap:6px}.form-grid span{color:var(--crm-text-muted);font-size:9px;font-weight:700}.form-grid input,.form-grid select,.form-grid textarea{box-sizing:border-box;width:100%;padding:9px 10px;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.form-grid input,.form-grid select{height:38px}.form-grid input:disabled{background:var(--crm-surface-muted)}.wide{grid-column:1/-1}@media(max-width:620px){.form-grid{grid-template-columns:1fr}.wide{grid-column:auto}}
</style>