<script setup lang="ts">
import { useLocalizedInput } from '@/i18n/localized-input'
import { systemValueLabel } from '@/features/shared/system-labels'
import { computed, ref } from 'vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import { shanghaiDate } from '@/domain/time'
import type { TransitionInstalledToolInput } from '@/types/workspaces'
import { useI18n } from '@/i18n'

export type InstalledToolTransitionSubmit = TransitionInstalledToolInput
defineProps<{ stage: string; busy?: boolean; error?: string }>()
const emit = defineEmits<{ close: []; submit: [value: InstalledToolTransitionSubmit] }>()
const { locale, t } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const stageLabel = (stage: string) => copy(stage, ({ FAT: 'FAT', Shipment: '发运', Installation: '安装', SAT: 'SAT', Warranty: '质保' } as Record<string, string>)[stage] || stage)
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
    openIssues: openIssuesInput.value.trim(),
    customerSignoff: form.value.customerSignoff.trim(),
    comment: form.value.comment.trim(),
    evidence: evidenceText.value.split(String.fromCharCode(10)).map((item) => item.trim()).filter(Boolean),
  })
}

const openIssuesInput = useLocalizedInput(() => form.value.openIssues, (value) => { form.value.openIssues = value }, (value) => systemValueLabel(value, locale.value))
</script>

<template>
  <ModalShell :title="t('installed.transitionTitle', { stage: stageLabel(stage) })" :eyebrow="copy('AUDITED LIFECYCLE TRANSITION', '已审计生命周期推进')" :submit-label="t('installed.confirmAdvance')" :busy="busy" :submit-disabled="invalid" @close="emit('close')" @submit="submit">
    <p class="form-note">{{ t('installed.transitionHint') }}</p>
    <p v-if="error" class="form-error">{{ error }}</p>
    <div class="form-grid">
      <label><span>{{ t('installed.completedAt') }}<RequiredMark /></span><input v-model="form.completedAt" type="date" required /></label>
      <label><span>{{ t('installed.customerSignoff') }}<RequiredMark /></span><input v-model="form.customerSignoff" :placeholder="t('installed.signerPlaceholder')" required /></label>
      <label class="wide"><span>{{ t('installed.result') }}<RequiredMark /></span><textarea v-model="form.result" rows="3" required /></label>
      <label class="wide"><span>{{ t('installed.openIssues') }}<RequiredMark /></span><textarea v-model="openIssuesInput" rows="2" required /></label>
      <label class="wide"><span>{{ t('installed.stageNote') }}<RequiredMark /></span><textarea v-model="form.comment" rows="2" required /></label>
      <label class="wide"><span>{{ t('installed.notes') }}</span><textarea v-model="evidenceText" rows="3" /></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.form-note,.form-error{margin:0 0 12px;padding:10px;border-radius:8px;font-size:9px}.form-note{color:var(--crm-teal);background:var(--crm-surface-muted)}.form-error{color:var(--crm-danger);background:var(--crm-danger-soft)}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.form-grid label{display:grid;gap:6px}.form-grid span{color:var(--crm-text-muted);font-size:9px;font-weight:700}.form-grid input,.form-grid textarea{box-sizing:border-box;width:100%;padding:9px 10px;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.form-grid input{height:38px}.form-grid textarea{resize:vertical}.wide{grid-column:1/-1}@media(max-width:620px){.form-grid{grid-template-columns:1fr}.wide{grid-column:auto}}
</style>
