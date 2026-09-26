<script setup lang="ts">
import { ref } from 'vue'
import { Upload, X } from '@lucide/vue'
import type { CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import type { DemoTestReportUploadResult, EvaluationDto } from '@/types/crm'
import { useI18n, useLocaleMessage } from '@/i18n'
import { REPORT_UPLOAD_MIME_TYPES, REPORT_UPLOAD_ACCEPT, REPORT_UPLOAD_MAX_BYTES } from './report-upload-formats'

const props = defineProps<{ evaluation: EvaluationDto; apiClient: CrmApi }>()
const emit = defineEmits<{ close: []; uploaded: [result: DemoTestReportUploadResult] }>()
const internalFile = ref<File | null>(null)
const externalFile = ref<File | null>(null)
const busy = ref(false)
const error = useLocaleMessage()
const requestId = ref('')
const { locale, t, message } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese

function choose(kind: 'internal' | 'external', event: Event) {
  const selected = (event.target as HTMLInputElement).files?.[0] ?? null
  error.value = ''
  requestId.value = ''
  const target = kind === 'internal' ? internalFile : externalFile
  if (!selected) { target.value = null; return }
  if (!selected.size) { error.value = message('evaluationReport.emptyFile'); target.value = null; return }
  if (selected.size > REPORT_UPLOAD_MAX_BYTES) { error.value = message('evaluationReport.maxFile'); target.value = null; return }
  if (!REPORT_UPLOAD_MIME_TYPES.has(selected.type)) { error.value = message('evaluationReport.fileTypes'); target.value = null; return }
  target.value = selected
}

async function upload() {
  if (!internalFile.value || !externalFile.value) { error.value = message('evaluationReport.selectBoth'); return }
  busy.value = true; error.value = ''; requestId.value = ''
  try {
    const result = await props.apiClient.releaseDemoTestReport(props.evaluation.id, {
      internalFile: { fileName: internalFile.value.name, mimeType: internalFile.value.type, size: internalFile.value.size, blob: internalFile.value },
      externalFile: { fileName: externalFile.value.name, mimeType: externalFile.value.type, size: externalFile.value.size, blob: externalFile.value },
      expectedRound: props.evaluation.testRound,
    })
    emit('uploaded', result.data)
  } catch (reason) {
    const mapped = mapRequestError(reason)
    error.value = mapped.localizedMessage ?? mapped.message
    requestId.value = mapped.requestId
  }
  finally { busy.value = false }
}
</script>

<template>
  <div class="host" role="presentation" @mousedown.self="!busy && emit('close')">
    <section role="dialog" aria-modal="true" :aria-label="t('evaluationReport.uploadTitle')">
      <header><div><span>TEST REPORT</span><h2>{{ t('evaluationReport.uploadTitle') }}</h2></div><button type="button" :aria-label="t('detail.close')" :disabled="busy" @click="emit('close')"><X :size="18" /></button></header>
      <div class="body">
        <p>{{ evaluation.title }} · {{ evaluation.id }}</p>
        <label>{{ copy('Internal Report', '内部报告') }}<input data-internal-report type="file" :accept="REPORT_UPLOAD_ACCEPT" @change="choose('internal', $event)" /><small v-if="internalFile">{{ internalFile.name }}</small></label>
        <label>{{ copy('External Report', '外部报告') }}<input data-external-report type="file" :accept="REPORT_UPLOAD_ACCEPT" @change="choose('external', $event)" /><small v-if="externalFile">{{ externalFile.name }}</small></label>
        <small>{{ t('evaluationReport.hint') }}</small>
        <p v-if="error" class="error" role="alert">{{ error }}<small v-if="requestId">Request ID: {{ requestId }}</small></p>
      </div>
      <footer><button type="button" class="secondary-button" :disabled="busy" @click="emit('close')">{{ t('detail.cancel') }}</button><button type="button" class="primary-button" :disabled="busy || !internalFile || !externalFile" data-upload-test-report @click="upload"><Upload :size="15" />{{ busy ? t('evaluationReport.uploading') : t('evaluationReport.uploadBoth') }}</button></footer>
    </section>
  </div>
</template>

<style scoped>
.host{position:absolute;inset:0;z-index:2200;display:grid;place-items:center;padding:24px;background:rgba(7,29,37,.5)}section{width:min(560px,100%);overflow:hidden;background:#fff;border-radius:14px}header,footer{display:flex;align-items:center;justify-content:space-between;padding:16px 18px}header{color:#fff;background:var(--crm-navy)}header span{color:#98c9c4;font-size:8px;font-weight:800}h2{margin:3px 0 0;font-size:17px}header button{color:#fff;background:transparent;border:0}.body{display:grid;gap:12px;padding:20px}.body p{margin:0;color:var(--crm-text-muted)}label{display:grid;gap:8px;font-weight:700}.body small{color:var(--crm-text-muted)}.error{display:grid;gap:4px;padding:9px;color:var(--crm-danger);background:var(--crm-danger-soft)}.error small{color:inherit}footer{justify-content:flex-end;gap:8px;border-top:1px solid var(--crm-line)}footer button{display:flex;align-items:center;gap:6px}
</style>
