<script setup lang="ts">
import { computed, ref } from 'vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import { shanghaiDate } from '@/domain/time'
import type { AddInstalledToolServiceRecordInput, InstalledToolDetailDto, InstalledToolServiceType } from '@/types/workspaces'

const props = withDefaults(defineProps<{
  tool: InstalledToolDetailDto
  actionOwners: Array<{ id: string; name: string; role: string }>
  busy?: boolean
  error?: string
}>(), { actionOwners: () => [] })
const emit = defineEmits<{ close: []; submit: [value: AddInstalledToolServiceRecordInput] }>()
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
    openIssues: form.value.openIssues.trim(),
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
</script>

<template>
  <ModalShell title="新增质保 / 服务记录" eyebrow="APPEND-ONLY SERVICE AUDIT" submit-label="保存服务记录" :busy="busy" :submit-disabled="invalid" @close="emit('close')" @submit="submit">
    <p v-if="error" class="form-error">{{ error }}</p>
    <div class="form-grid">
      <label><span>服务日期<RequiredMark /></span><input v-model="form.serviceDate" type="date" required /></label>
      <label><span>服务类型<RequiredMark /></span><select v-model="form.serviceType"><option v-for="item in types" :key="item" :value="item">{{ item }}</option></select></label>
      <label class="wide"><span>处理结果<RequiredMark /></span><textarea v-model="form.result" rows="3" required /></label>
      <label class="wide"><span>遗留问题<RequiredMark /></span><textarea v-model="form.openIssues" rows="2" required /></label>
      <label class="wide"><span>下一步行动</span><input v-model="form.nextAction" aria-label="下一步行动" /></label>
      <label><span>行动负责人<RequiredMark v-if="form.nextAction?.trim()" /></span><select v-model="form.actionOwner" aria-label="行动负责人"><option value="">请选择有效人员</option><option v-for="owner in actionOwners" :key="owner.id" :value="owner.id">{{ owner.name }} · {{ owner.role }}</option></select></label>
      <label><span>截止日期<RequiredMark v-if="form.nextAction?.trim()" /></span><input v-model="form.due" type="date" aria-label="截止日期" /></label>
      <label><span>质保开始</span><input v-model="form.warrantyStart" type="date" /></label>
      <label><span>质保结束</span><input v-model="form.warrantyEnd" type="date" /></label>
      <label><span>服务合同</span><input v-model="form.serviceContract" /></label>
      <label><span>PM 周期</span><input v-model="form.pmCycle" /></label>
      <label class="wide"><span>补充说明</span><textarea v-model="form.comment" rows="2" /></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:9px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.form-grid label{display:grid;gap:6px}.form-grid span{color:var(--crm-text-muted);font-size:9px;font-weight:700}.form-grid input,.form-grid select,.form-grid textarea{box-sizing:border-box;width:100%;padding:9px 10px;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.form-grid input,.form-grid select{height:38px}.wide{grid-column:1/-1}@media(max-width:620px){.form-grid{grid-template-columns:1fr}.wide{grid-column:auto}}
</style>