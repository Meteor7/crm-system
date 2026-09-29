<script setup lang="ts">
import { CircleCheck } from '@lucide/vue'
import { useI18n } from '@/i18n'
import type { WarningHandling } from './types'

// One warning's next step (下一步) and, on stage 6 rows, the action taken (still correctable once handled).
// Presentational: the Warnings page owns the drafts, the version captured when an editor opens, the saving,
// the one-editor-per-page lock and the focus.
// dateHint: the action's follow-up date is missing or out of range, so Save stays disabled.
defineProps<{
  handling: WarningHandling; editing: 'plan' | 'action' | null; locked: boolean; saving: boolean; canSave: boolean
  error: string; conflict: boolean; dateHint?: boolean; allowAction?: boolean; followUpMin?: string; followUpMax?: string; name: (id: string | null | undefined) => string
}>()
const draft = defineModel<string>('draft', { required: true })
const followUp = defineModel<string>('followUp', { required: true })
const emit = defineEmits<{ edit: [mode: 'plan' | 'action']; cancel: []; save: []; reload: [] }>()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const dateText = (value: string | null | undefined) => value ? new Date(value).toLocaleDateString(locale.value, { timeZone: 'Asia/Shanghai' }) : '—'
const dayText = (value: string | null | undefined) => value ? new Date(`${value.slice(0, 10)}T00:00:00Z`).toLocaleDateString(locale.value, { month: 'short', day: 'numeric', timeZone: 'UTC' }) : '—'
</script>

<template>
  <div class="next-step" :data-handling="handling.warningType">
    <!-- A stage 6 row back after its follow-up date still shows what was done last time. -->
    <p v-if="handling.state === 'open' && handling.actionTaken" class="last-action" data-last-action><CircleCheck :size="12" /><span><b>{{ copy('Last action', '上次行动') }}</b> {{ handling.actionTaken }}<small>{{ name(handling.actedBy) }} · {{ dateText(handling.actedAt) }}<template v-if="handling.followUpOn"> · {{ copy('follow-up', '复核') }} {{ dayText(handling.followUpOn) }}</template></small></span></p>
    <div v-if="editing" class="step-editor" :class="editing" :data-step-editor="editing"><span class="step-label">{{ editing === 'plan' ? copy('Next step', '下一步') : copy('Action taken', '已采取行动') }}</span><textarea v-model="draft" rows="2" maxlength="2000" :disabled="saving" :aria-label="editing === 'plan' ? copy('Next step', '下一步') : copy('Action taken', '已采取行动')" :placeholder="editing === 'plan' ? copy('Who does what, by when', '谁、做什么、何时完成') : copy('What was done', '已经做了什么')" data-step-draft></textarea>
      <label v-if="editing === 'action'" class="follow-up">{{ copy('Follow-up date', '复核日期') }}<input v-model="followUp" type="date" required :min="followUpMin" :max="followUpMax" :disabled="saving" data-follow-up /></label>
      <div class="step-editor-foot"><small v-if="editing === 'action' && dateHint" class="date-hint" data-date-hint>{{ copy('Pick a date from tomorrow to one year ahead', '请选择明天至一年内的日期') }}</small><small v-else>{{ editing === 'plan' ? copy('Saving the next step keeps the warning', '保存下一步不清除预警') : copy('Clears the alert until the follow-up date; it returns if there is still no PO', '记录后提醒清除，到复核日期仍无 PO 会重新提醒') }}</small><button type="button" :disabled="saving" @click="emit('cancel')">{{ copy('Cancel', '取消') }}</button><button type="button" class="save-step" :disabled="saving || !canSave" data-step-save @click="emit('save')">{{ copy('Save', '保存') }}</button></div>
      <p v-if="error" class="step-error" role="alert">{{ error }}<button v-if="conflict" type="button" data-step-reload @click="emit('reload')">{{ copy('Reload', '重新加载') }}</button></p>
    </div>
    <div v-else-if="handling.state === 'handled'" class="step-view handled-view"><p class="last-action" data-handled-action><CircleCheck :size="12" /><span><b>{{ copy('Action taken', '已采取行动') }}</b> {{ handling.actionTaken }}<small>{{ name(handling.actedBy) }} · {{ dateText(handling.actedAt) }} · {{ copy('follow-up', '复核') }} {{ dayText(handling.followUpOn) }}</small></span></p><button type="button" class="correct-button" :disabled="locked" data-action-edit @click="emit('edit', 'action')">{{ copy('Edit action / follow-up date', '修改行动 / 复核日期') }}</button></div>
    <div v-else class="step-view"><button type="button" class="step-box" :disabled="locked" data-step-edit :title="copy('Edit the next step in the meeting', '在例会中编辑下一步')" @click="emit('edit', 'plan')"><span class="step-label">{{ copy('Next step', '下一步') }}</span><span v-if="handling.nextStep" class="step-text">{{ handling.nextStep }}</span><span v-else class="muted">{{ copy('No next step yet — add one', '尚未记录下一步，点击补录') }}</span><small v-if="handling.planAt">{{ name(handling.planBy) }} · {{ dateText(handling.planAt) }}</small></button><button v-if="allowAction" type="button" class="action-button" :disabled="locked" data-action-open @click="emit('edit', 'action')">{{ copy('Record action taken', '记录已采取行动') }}</button></div>
    <details v-if="handling.history.length" class="step-history" data-step-history><summary>{{ copy('History', '处理记录') }} · {{ handling.history.length }}</summary><p v-for="(entry, index) in handling.history" :key="`${entry.at}:${index}`" :data-kind="entry.kind"><span class="kind" :class="entry.kind === 'ActionRecorded' ? 'action' : 'plan'">{{ entry.kind === 'ActionRecorded' ? copy('Action taken', '已采取行动') : copy('Plan updated', '计划更新') }}</span>{{ entry.kind === 'ActionRecorded' ? entry.actionTaken : entry.nextStep }}<small>{{ name(entry.actor) }} · {{ dateText(entry.at) }}<template v-if="entry.followUpOn"> · {{ copy('follow-up', '复核') }} {{ dayText(entry.followUpOn) }}</template></small></p></details>
  </div>
</template>

<style scoped>
.next-step{display:grid;gap:6px;max-width:420px;margin-top:8px;font-size:12px}.next-step *{box-sizing:border-box}.next-step button,.next-step textarea,.next-step input{font:inherit;color:inherit}.next-step button{cursor:pointer}.next-step button:disabled{opacity:.5;cursor:default}
.next-step button:focus-visible,.next-step textarea:focus-visible,.next-step input:focus-visible{outline:2px solid var(--crm-brand);outline-offset:3px}
.step-view{display:flex;flex-wrap:wrap;align-items:flex-start;gap:6px}.step-box{display:grid;gap:3px;flex:1 1 220px;min-width:0;padding:6px 9px;border:1px dashed var(--crm-line-strong);border-radius:var(--crm-radius-sm);background:white;text-align:left;line-height:1.5}.step-box:hover:not(:disabled){border-color:var(--crm-link)}.step-box small{color:var(--crm-text-muted);font-size:11px}
.step-label{font-size:10px;font-weight:700;letter-spacing:.3px;color:var(--crm-link)}.step-text{white-space:pre-wrap;overflow-wrap:anywhere}.muted{color:var(--crm-text-muted)}
.action-button{padding:5px 10px;border:1px solid var(--crm-brand);border-radius:var(--crm-radius-sm);background:var(--crm-brand);color:var(--crm-brand-ink);font-size:11px;font-weight:650;white-space:nowrap}
.last-action{display:flex;gap:6px;align-items:flex-start;margin:0;padding:6px 9px;border-radius:var(--crm-radius-sm);background:#e8f5ee;color:var(--crm-positive-ink);line-height:1.5;overflow-wrap:anywhere}.last-action svg{flex-shrink:0;margin-top:4px}.last-action small{display:block;color:var(--crm-text-muted);font-size:11px}
.step-editor{display:grid;gap:6px;padding:8px;border:1px solid var(--crm-link);border-radius:var(--crm-radius-sm);background:white}.step-editor.action{border-color:var(--crm-positive-ink)}.step-editor.action .step-label{color:var(--crm-positive-ink)}.step-editor textarea{border:0;resize:vertical;min-height:48px;padding:0;line-height:1.5}.step-editor textarea:focus-visible{outline:0}
.follow-up{display:flex;align-items:center;gap:8px;color:var(--crm-text-muted);font-size:11px}.follow-up input{border:1px solid var(--crm-line);border-radius:var(--crm-radius-sm);background:white;padding:3px 6px}
.step-editor-foot{display:flex;align-items:center;gap:6px}.step-editor-foot small{flex:1;color:var(--crm-link);font-size:11px;line-height:1.4}.step-editor.action .step-editor-foot small{color:var(--crm-positive-ink)}.step-editor-foot button,.step-error button{border:1px solid var(--crm-line);background:white;border-radius:4px;padding:3px 8px;font-size:11px}.step-editor-foot .save-step{background:var(--crm-navy);border-color:var(--crm-navy);color:white;font-weight:650}
.step-editor.action .step-editor-foot .date-hint{color:var(--crm-danger)}.handled-view{flex-direction:column;align-items:stretch}.correct-button{align-self:flex-start;padding:0;border:0;background:none;color:var(--crm-link);font-size:11px;font-weight:650}.correct-button:hover:not(:disabled){text-decoration:underline}
.step-error{display:flex;gap:8px;align-items:center;margin:0;color:var(--crm-danger);font-size:11px}
.step-history summary{cursor:pointer;color:var(--crm-text-muted);font-size:11px}.step-history p{margin:4px 0 0;font-size:11px;line-height:1.5;overflow-wrap:anywhere}.step-history small{display:block;color:var(--crm-text-muted)}.kind{display:inline-block;margin-right:6px;padding:0 6px;border-radius:999px;font-size:10px;font-weight:650}.kind.plan{background:var(--crm-surface-muted);color:var(--crm-link)}.kind.action{background:#e8f5ee;color:var(--crm-positive-ink)}
</style>
