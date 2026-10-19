<script setup lang="ts">
import { ref, watch } from 'vue'
import { FileText, Paperclip, Pencil, Plus, Trash2 } from '@lucide/vue'
import type { CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import ModalShell from '@/design-system/ModalShell.vue'
import { personnelDisplayName } from '@/demo/personnel'
import { formatDisplayDate } from '@/domain/time'
import { downloadBlob } from '@/features/shared/download-blob'
import { useI18n } from '@/i18n'
import type { OpportunityStatusRecord, OpportunityStatusFile } from './status-types'

const props = defineProps<{ opportunityId: string; apiClient: CrmApi; canWrite: boolean }>()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const records = ref<OpportunityStatusRecord[]>([])
const loading = ref(false), busy = ref(false), error = ref(''), formError = ref('')
const open = ref(false), editing = ref<OpportunityStatusRecord | null>(null)
const text = ref(''), retained = ref<OpportunityStatusFile[]>([]), uploads = ref<File[]>([])
const downloading = ref('')
let sequence = 0
const maxBytes = 100 * 1024 * 1024
const accepted = '.pdf,.docx,.xlsx,.pptx,.txt,.csv,.png,.jpg,.jpeg'
const pattern = /\.(pdf|docx|xlsx|pptx|txt|csv|png|jpe?g)$/i

async function load() {
  const current = ++sequence
  loading.value = true
  error.value = ''
  try {
    const result = await props.apiClient.listOpportunityStatuses(props.opportunityId)
    if (current === sequence) records.value = result.data
  } catch (reason) {
    if (current === sequence) error.value = mapRequestError(reason).message
  } finally {
    if (current === sequence) loading.value = false
  }
}
watch(() => props.opportunityId, () => {
  records.value = []
  open.value = false
  void load()
}, { immediate: true })

function edit(record: OpportunityStatusRecord | null = null) {
  if (!props.canWrite || busy.value) return
  editing.value = record
  text.value = record?.text ?? ''
  retained.value = [...(record?.files ?? [])]
  uploads.value = []
  formError.value = ''
  open.value = true
}
function close() { if (!busy.value) open.value = false }
function selectFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const chosen = [...uploads.value, ...Array.from(input.files ?? [])]
  input.value = ''
  formError.value = ''
  if (chosen.some(file => /\.(doc|xls|ppt)$/i.test(file.name))) {
    formError.value = copy('Save legacy Office files as DOCX, XLSX or PPTX before uploading.', '请先将旧版 Office 文件另存为 DOCX、XLSX 或 PPTX 后上传。')
  } else if (chosen.length + retained.value.length > 10) {
    formError.value = copy('Each Status supports up to 10 attachments.', '每条 Status 最多添加 10 个附件。')
  } else if (chosen.some(file => Array.from(file.name).length > 140)) {
    formError.value = copy('File names including extensions must not exceed 140 characters. Shorten the file name and try again.', '文件名（含扩展名）最多 140 个字符，请缩短文件名后重试。')
  } else if (chosen.some(file => !pattern.test(file.name) || file.size === 0 || file.size > maxBytes) || chosen.reduce((sum, file) => sum + file.size, 0) > maxBytes) {
    formError.value = copy('Choose supported, non-empty files. Each file and the upload total must not exceed 100 MiB.', '请选择支持的非空文件，单个文件及本次上传总计不得超过 100 MiB。')
  } else {
    uploads.value = chosen
  }
}
async function save() {
  if (!props.canWrite || busy.value) return
  formError.value = ''
  if (!text.value.trim()) {
    formError.value = copy('Enter information.', '请填写记录信息。')
    return
  }
  busy.value = true
  const opportunityId = props.opportunityId
  try {
    const result = await props.apiClient.saveOpportunityStatus(opportunityId, {
      text: text.value.trim(), retainedFileIds: retained.value.map(file => file.id),
      ...(editing.value ? { recordId: editing.value.id, expectedModified: editing.value.modified } : {}),
    }, uploads.value.map(file => ({ blob: file, fileName: file.name, size: file.size, mimeType: /\.csv$/i.test(file.name) ? 'text/csv' : file.type })))
    if (opportunityId === props.opportunityId) {
      records.value = [result.data, ...records.value.filter(record => record.id !== result.data.id)]
      open.value = false
    }
  } catch (reason) {
    if (opportunityId === props.opportunityId) formError.value = mapRequestError(reason).message
  } finally {
    busy.value = false
  }
}
async function download(record: OpportunityStatusRecord, file: OpportunityStatusFile) {
  downloading.value = file.id
  error.value = ''
  try {
    const result = await props.apiClient.getOpportunityStatusFile(props.opportunityId, record.id, file.id)
    downloadBlob(result.blob, result.fileName)
  } catch (reason) {
    error.value = mapRequestError(reason).message
  } finally {
    downloading.value = ''
  }
}
function size(bytes: number) { return bytes < 1048576 ? `${Math.max(1, Math.ceil(bytes / 1024))} KB` : `${(bytes / 1048576).toFixed(1)} MB` }
</script>

<template>
  <section class="status-card" data-testid="opportunity-status">
    <header class="status-header"><h2><FileText :size="16" />Status</h2><button v-if="canWrite" type="button" class="new-status" data-testid="new-status" :disabled="loading || busy" @click="edit()"><Plus :size="13" />{{ copy('New', '新增') }}</button></header>
    <p v-if="error" class="status-error" role="alert">{{ error }} <button type="button" @click="load">{{ copy('Retry', '重试') }}</button></p>
    <p v-if="loading" class="status-empty">{{ copy('Loading…', '正在加载…') }}</p>
    <template v-else>
      <article v-for="record in records" :key="record.id" class="status-record">
        <div class="status-information"><p>{{ record.text }}</p><small>{{ personnelDisplayName(record.updatedBy) }} · {{ formatDisplayDate(record.updatedAt) }}</small></div>
        <div class="status-files"><small>{{ copy('Attachments', '附件') }} · {{ record.files.length }}</small><button v-for="file in record.files" :key="file.id" type="button" class="status-file" :disabled="Boolean(downloading)" @click="download(record, file)"><Paperclip :size="14" /><span>{{ file.fileName }}<small>{{ size(file.size) }} · {{ downloading === file.id ? copy('Downloading…', '下载中…') : copy('Download', '下载') }}</small></span></button><p v-if="!record.files.length" class="no-files">{{ copy('No attachments', '暂无附件') }}</p></div>
        <button v-if="canWrite" type="button" class="edit-status" :aria-label="copy('Edit Status record', '编辑 Status 记录')" @click="edit(record)"><Pencil :size="13" /></button>
      </article>
      <p v-if="!records.length && !error" class="status-empty">{{ copy('No Status records yet', '暂无 Status 记录') }}</p>
    </template>
  </section>
    <ModalShell class="status-modal" v-if="open" :title="editing ? copy('Edit Status', '编辑 Status') : copy('New Status', '新增 Status')" eyebrow="STATUS" :busy="busy" :submit-label="copy('Save and continue', '保存并继续')" :cancel-label="copy('Cancel', '取消')" :close-label="copy('Close', '关闭')" @close="close" @submit="save">
      <p v-if="formError" class="status-error" role="alert">{{ formError }}</p>
      <div class="status-form">
        <label>{{ copy('Information', '记录信息') }} <span aria-hidden="true">*</span><textarea v-model="text" :aria-label="copy('Information', '记录信息')" required maxlength="10000" rows="4" :disabled="busy" /></label>
        <label class="status-upload">{{ copy('Add attachments (optional)', '添加附件（可选）') }}<input type="file" multiple :accept="accepted" :disabled="busy" :aria-label="copy('Add attachments', '添加附件')" @change="selectFiles" /><small>{{ copy('PDF, DOCX, XLSX, PPTX, TXT, CSV and images; up to 10 attachments and 100 MiB per upload.', '支持 PDF、DOCX、XLSX、PPTX、TXT、CSV 和图片；最多 10 个附件，本次上传总计不超过 100 MiB。') }}</small></label>
        <div v-for="file in retained" :key="file.id" class="draft-file"><span>{{ file.fileName }}</span><button type="button" :disabled="busy" :aria-label="copy('Remove ', '移除 ') + file.fileName" @click="retained = retained.filter(item => item.id !== file.id)"><Trash2 :size="14" /></button></div>
        <div v-for="(file, index) in uploads" :key="index" class="draft-file"><span>{{ file.name }} · {{ size(file.size) }}</span><button type="button" :disabled="busy" :aria-label="copy('Remove ', '移除 ') + file.name" @click="uploads.splice(index, 1)"><Trash2 :size="14" /></button></div>
      </div>
    </ModalShell>
</template>

<style scoped>
.status-modal.modal-host{position:fixed;min-height:0}
.status-card{overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:14px;box-shadow:0 8px 20px rgba(20,30,40,.025)}.status-header{display:flex;align-items:center;justify-content:space-between;padding:13px 16px;background:#F6F8FB;border-bottom:1px solid var(--crm-line)}.status-header h2{display:flex;align-items:center;gap:9px;margin:0;font-size:12px;color:var(--crm-navy)}.new-status{display:flex;align-items:center;gap:5px;padding:7px 10px;border:1px solid var(--crm-line);border-radius:8px;background:white;color:var(--crm-teal);font:inherit;font-size:10px;font-weight:700;cursor:pointer}.status-record{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(120px,1fr) 28px;gap:14px;padding:17px 16px;border-bottom:1px solid var(--crm-line)}.status-record:last-child{border:0}.status-information p{margin:0 0 9px;font-size:11px;line-height:1.8;white-space:pre-wrap;overflow-wrap:anywhere}.status-record small{color:var(--crm-text-muted);font-size:8px}.status-files{padding-left:13px;border-left:1px solid var(--crm-line)}.status-file{display:flex;align-items:center;gap:7px;width:100%;margin-top:8px;padding:9px;text-align:left;color:var(--crm-navy);background:#fcfbf9;border:1px solid var(--crm-line);border-radius:7px;cursor:pointer;font:inherit;font-size:9px;overflow-wrap:anywhere}.status-file svg{flex-shrink:0;color:var(--crm-teal)}.status-file small{display:block;margin-top:4px}.edit-status{display:grid;place-items:center;width:28px;height:28px;color:var(--crm-teal);border:1px solid var(--crm-line);border-radius:7px;background:white;cursor:pointer}.status-empty{margin:0;padding:24px;text-align:center;color:var(--crm-text-muted);font-size:10px}.no-files{font-size:9px;color:var(--crm-text-muted)}.status-error{margin:12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);font-size:11px;border-radius:8px}.status-error button{font:inherit;cursor:pointer}.status-form{display:grid;gap:15px}.status-form label{display:block;color:var(--crm-text-muted);font-size:10px;font-weight:700}.status-form label>span{color:var(--crm-danger)}.status-form textarea{display:block;width:100%;margin-top:8px;resize:vertical;min-height:100px;padding:10px;font:inherit;font-size:12px;font-weight:400;color:var(--crm-text);line-height:1.7;border:1px solid var(--crm-line);border-radius:8px}.status-upload{padding:15px;border:1px dashed var(--crm-line);border-radius:9px;background:#fcfaf7}.status-upload input{display:block;max-width:100%;margin:12px 0}.status-upload small{display:block;font-size:9px;font-weight:400;line-height:1.6}.draft-file{display:flex;justify-content:space-between;align-items:center;gap:12px;font-size:11px}.draft-file span{overflow-wrap:anywhere}.draft-file button{padding:6px;color:var(--crm-danger);background:white;border:1px solid var(--crm-line);border-radius:6px;cursor:pointer}button:disabled{opacity:.55;cursor:wait}button:focus-visible,textarea:focus-visible,input:focus-visible{outline:2px solid var(--crm-teal);outline-offset:2px}@media(max-width:620px){.status-record{grid-template-columns:minmax(0,1fr) 28px}.status-files{grid-column:1;grid-row:2;padding-left:0;border:0}.edit-status{grid-column:2;grid-row:1}}
</style>
