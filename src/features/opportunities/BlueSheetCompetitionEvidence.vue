<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import type { CrmApi } from '@/api'
import { requestErrorMessage } from '@/api/request-state'
import { useI18n, useLocaleMessage } from '@/i18n'
import { useAppStore } from '@/stores/app'
import type { OpportunityCompetitor } from '@/types/workspaces'
const props = defineProps<{ opportunityId: string; apiClient: CrmApi; disabled?: boolean }>()
const emit = defineEmits<{ cite: [text: string] }>()
const app = useAppStore()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const rows = ref<OpportunityCompetitor[] | null>(null), busy = ref(false), modified = ref('')
const notes = ref('')
const error = useLocaleMessage()
let request = 0
watch([() => props.opportunityId, () => app.identityRevision], () => { request++; rows.value = null; notes.value = ''; modified.value = ''; busy.value = false; error.value = '' })
onBeforeUnmount(() => { request++ })
async function load() {
  if (busy.value || props.disabled) return
  const current = ++request
  busy.value = true; error.value = ''; rows.value = null; notes.value = ''
  try {
    const response = await props.apiClient.getStrategyOpportunity(props.opportunityId)
    if (current !== request) return
    rows.value = response.data.competitors ?? []; modified.value = response.data.modified ?? response.data.updated
    notes.value = response.data.competition ?? ''
  } catch (cause) { if (current === request) error.value = requestErrorMessage(cause) }
  finally { if (current === request) busy.value = false }
}
function citeText(lines: string[]) {
  if (props.disabled || busy.value) return
  emit('cite', [copy('Blue Sheet reference (not a confirmed loss cause)', 'Blue Sheet 参考（非已确认丢单原因）'), `${props.opportunityId} · ${modified.value}`, ...lines].join('\n'))
}
function cite(row: OpportunityCompetitor) {
  citeText([row.name, `${copy('Strengths', '竞争优势')}: ${row.strengths || '—'}`, `${copy('Response', '应对策略')}: ${row.response || '—'}`])
}
function citeNotes() {
  if (notes.value.trim()) citeText([copy('Competition notes', '竞争备注'), notes.value])
}
</script>
<template>
  <section class="competition-evidence" data-blue-competition>
    <h3>{{ copy('Competition evidence', '竞争信息参考') }}</h3>
    <p>{{ copy('Loads current Blue Sheet information. It is evidence to consider; the manager confirms the conclusion and category.', '读取当前 Blue Sheet 竞争信息供复盘参考，由经理确认结论与分类。') }}</p>
    <button type="button" :disabled="busy || disabled" data-blue-competition-load @click="load">{{ copy('Load current competition', '读取当前竞争信息') }}</button>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="rows && !rows.length && !notes.trim()">{{ copy('No competition information recorded.', '尚未记录竞争信息。') }}</p>
    <article v-if="notes.trim()" data-blue-competition-notes><strong>{{ copy('Competition notes', '竞争备注') }}</strong><p>{{ notes }}</p><button type="button" :disabled="busy || disabled" data-blue-competition-cite-notes @click="citeNotes">{{ copy('Cite in the draft conclusion', '引用到复盘草稿') }}</button></article>
    <article v-for="row in rows" :key="row.name"><strong>{{ row.name }}</strong><p>{{ row.strengths }}</p><p>{{ row.response }}</p><button type="button" :disabled="busy || disabled" data-blue-competition-cite @click="cite(row)">{{ copy('Cite in the draft conclusion', '引用到复盘草稿') }}</button></article>
  </section>
</template>
<style scoped>
.competition-evidence { border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px; margin: 14px 0; font-size: 12px; } h3 { margin: 0; } article { border-top: 1px solid #e2e8f0; padding-top: 8px; margin-top: 10px; } p { color: #64748b; white-space: pre-wrap; } [role=alert] { color: #b91c1c; }
</style>
