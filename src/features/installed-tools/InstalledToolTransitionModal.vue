<script setup lang="ts">
import { computed, ref } from 'vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import { shanghaiDate } from '@/domain/time'
import type { TransitionInstalledToolInput } from '@/types/workspaces'

export type InstalledToolTransitionSubmit = TransitionInstalledToolInput
defineProps<{ stage: string; busy?: boolean; error?: string }>()
const emit = defineEmits<{ close: []; submit: [value: InstalledToolTransitionSubmit] }>()
const evidenceText = ref('')
const form = ref<TransitionInstalledToolInput>({
  completedAt: shanghaiDate(),
  result: '',
  openIssues: '无',
  customerSignoff: '',
  comment: '',
  evidence: [],
})
const invalid = computed(() => !form.value.completedAt || !form.value.result.trim() || !form.value.openIssues.trim() || !form.value.customerSignoff.trim() || !form.value.comment.trim())
function submit() {
  emit('submit', {
    ...form.value,
    result: form.value.result.trim(),
    openIssues: form.value.openIssues.trim(),
    customerSignoff: form.value.customerSignoff.trim(),
    comment: form.value.comment.trim(),
    evidence: evidenceText.value.split(String.fromCharCode(10)).map((item) => item.trim()).filter(Boolean),
  })
}
</script>

<template>
  <ModalShell :title="`完成 ${stage} 节点`" eyebrow="AUDITED LIFECYCLE TRANSITION" submit-label="确认完成并推进" :busy="busy" :submit-disabled="invalid" @close="emit('close')" @submit="submit">
    <p class="form-note">提交后将生成不可覆盖的生命周期记录，并推进到下一个节点。</p>
    <p v-if="error" class="form-error">{{ error }}</p>
    <div class="form-grid">
      <label><span>完成日期<RequiredMark /></span><input v-model="form.completedAt" type="date" required /></label>
      <label><span>客户确认<RequiredMark /></span><input v-model="form.customerSignoff" placeholder="签字人或确认方式" required /></label>
      <label class="wide"><span>验收结果<RequiredMark /></span><textarea v-model="form.result" rows="3" required /></label>
      <label class="wide"><span>遗留问题<RequiredMark /></span><textarea v-model="form.openIssues" rows="2" required /></label>
      <label class="wide"><span>节点说明<RequiredMark /></span><textarea v-model="form.comment" rows="2" required /></label>
      <label class="wide"><span>备注</span><textarea v-model="evidenceText" rows="3" /></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.form-note,.form-error{margin:0 0 12px;padding:10px;border-radius:8px;font-size:9px}.form-note{color:var(--crm-teal);background:var(--crm-surface-muted)}.form-error{color:var(--crm-danger);background:var(--crm-danger-soft)}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.form-grid label{display:grid;gap:6px}.form-grid span{color:var(--crm-text-muted);font-size:9px;font-weight:700}.form-grid input,.form-grid textarea{box-sizing:border-box;width:100%;padding:9px 10px;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.form-grid input{height:38px}.form-grid textarea{resize:vertical}.wide{grid-column:1/-1}@media(max-width:620px){.form-grid{grid-template-columns:1fr}.wide{grid-column:auto}}
</style>
