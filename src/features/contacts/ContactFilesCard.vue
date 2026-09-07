<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { Download, FileText, LoaderCircle, Trash2, UploadCloud } from '@lucide/vue'
import { api as defaultApi, type CrmApi } from '@/api'
import type { MultipartFilePart } from '@/api/binary-transport'
import { mapRequestError } from '@/api/request-state'
import type { ContactFileMetaDto } from '@/types/crm'
import SectionCard from '@/design-system/SectionCard.vue'
import { downloadBlob } from '@/features/shared/download-blob'
import { readAllPages } from '@/features/shared/read-all-pages'
import { formatDisplayDate } from '@/domain/time'
import { useI18n, useLocaleMessage, localeMessage } from '@/i18n'

const MAX_FILE_SIZE = 100 * 1024 * 1024
const ACCEPTED_FILE_PATTERN = /\.(pdf|doc|docx|xls|xlsx|ppt|pptx|txt|csv|png|jpe?g)$/i
const ACCEPT = '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.png,.jpg,.jpeg'

const props = withDefaults(defineProps<{
  contactId: string
  canWrite?: boolean
  canDelete?: boolean
  apiClient?: CrmApi
}>(), {
  canWrite: false,
  canDelete: false,
  apiClient: () => defaultApi,
})
const { locale } = useI18n()

const files = ref<ContactFileMetaDto[]>([])
const input = ref<HTMLInputElement | null>(null)
const loading = ref(true)
const uploading = ref(false)
const activeFileId = ref('')
const dragging = ref(false)
const error = useLocaleMessage()
let loadSequence = 0

function getFileApi(): CrmApi | undefined {
  const supportsFiles = (client: Partial<CrmApi>) =>
    typeof client.listContactFiles === 'function' &&
    typeof client.uploadContactFiles === 'function' &&
    typeof client.getContactFile === 'function' &&
    typeof client.deleteContactFile === 'function'
  if (supportsFiles(props.apiClient)) return props.apiClient
  if (supportsFiles(defaultApi)) return defaultApi
  return undefined
}

function formatSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(size < 10 * 1024 ? 1 : 0)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

async function loadFiles() {
  const sequence = ++loadSequence
  loading.value = true
  error.value = ''
  const apiClient = getFileApi()
  if (!apiClient) {
    error.value = localeMessage('Contact file service is not ready. Refresh and try again.', '联系人文件接口尚未加载，请刷新页面后重试。')
    loading.value = false
    return
  }
  try {
    const allFiles = await readAllPages((page, pageSize) =>
      apiClient.listContactFiles(props.contactId, { page, pageSize }))
    if (sequence === loadSequence) files.value = allFiles
  } catch (reason) {
    if (sequence === loadSequence) { const mapped = mapRequestError(reason); error.value = mapped.localizedMessage ?? mapped.message }
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

function openPicker() {
  if (props.canWrite && !uploading.value) input.value?.click()
}

async function uploadFiles(fileList: FileList | null) {
  if (!props.canWrite || !fileList?.length) return
  error.value = ''
  const apiClient = getFileApi()
  if (!apiClient) {
    error.value = localeMessage('Contact file service is not ready. Refresh and try again.', '联系人文件接口尚未加载，请刷新页面后重试。')
    return
  }
  const selected = Array.from(fileList)
  const invalidType = selected.find((file) => !ACCEPTED_FILE_PATTERN.test(file.name))
  if (invalidType) {
    error.value = localeMessage(`File type is not supported: “${invalidType.name}”`, `不支持“${invalidType.name}”的文件类型`)
    return
  }
  const oversized = selected.find((file) => file.size > MAX_FILE_SIZE)
  if (oversized) {
    error.value = localeMessage(`“${oversized.name}” exceeds 100 MiB`, `“${oversized.name}”超过 100 MiB`)
    return
  }
  const empty = selected.find((file) => file.size === 0)
  if (empty) {
    error.value = localeMessage(`“${empty.name}” is empty`, `“${empty.name}”为空文件`)
    return
  }

  uploading.value = true
  try {
    const uploads: MultipartFilePart[] = selected.map((file) => ({
      fileName: file.name,
      mimeType: file.type,
      size: file.size,
      blob: file,
    }))
    await apiClient.uploadContactFiles(props.contactId, uploads)
    await loadFiles()
  } catch (reason) {
    { const mapped = mapRequestError(reason); error.value = mapped.localizedMessage ?? mapped.message }
  } finally {
    uploading.value = false
  }
}

function onInputChange(event: Event) {
  const target = event.target as HTMLInputElement
  void uploadFiles(target.files)
  target.value = ''
}

function onDrop(event: DragEvent) {
  dragging.value = false
  void uploadFiles(event.dataTransfer?.files ?? null)
}

async function downloadFile(file: ContactFileMetaDto) {
  activeFileId.value = file.id
  error.value = ''
  const apiClient = getFileApi()
  if (!apiClient) {
    error.value = localeMessage('Contact file service is not ready. Refresh and try again.', '联系人文件接口尚未加载，请刷新页面后重试。')
    activeFileId.value = ''
    return
  }
  try {
    const result = await apiClient.getContactFile(file.id)
    downloadBlob(result.blob, result.fileName)
  } catch (reason) {
    { const mapped = mapRequestError(reason); error.value = mapped.localizedMessage ?? mapped.message }
  } finally {
    activeFileId.value = ''
  }
}

async function deleteFile(file: ContactFileMetaDto) {
  if (!props.canWrite) return
  activeFileId.value = file.id
  error.value = ''
  const apiClient = getFileApi()
  if (!apiClient) {
    error.value = localeMessage('Contact file service is not ready. Refresh and try again.', '联系人文件接口尚未加载，请刷新页面后重试。')
    activeFileId.value = ''
    return
  }
  try {
    await apiClient.deleteContactFile(file.id)
    files.value = files.value.filter((item) => item.id !== file.id)
  } catch (reason) {
    { const mapped = mapRequestError(reason); error.value = mapped.localizedMessage ?? mapped.message }
  } finally {
    activeFileId.value = ''
  }
}

watch(() => props.contactId, loadFiles)
onMounted(loadFiles)
</script>

<template>
  <SectionCard :title="locale === 'en-US' ? `Files (${files.length})` : `文件 (${files.length})`" eyebrow="FILES">
    <input v-if="canWrite" ref="input" class="file-input" type="file" multiple :accept="ACCEPT" :aria-label="locale === 'en-US' ? 'Choose contact files' : '选择联系人文件'" @change="onInputChange">
    <div
      v-if="canWrite"
      class="upload-zone"
      :class="{ dragging }"
      tabindex="0"
      role="button"
      :aria-label="locale === 'en-US' ? 'Upload contact files' : '上传联系人文件'"
      data-testid="contact-file-dropzone"
      @click="openPicker"
      @keydown.enter.prevent="openPicker"
      @keydown.space.prevent="openPicker"
      @dragenter.prevent="canWrite && (dragging = true)"
      @dragover.prevent
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <span class="upload-icon"><UploadCloud :size="19" /></span>
      <button class="upload-button" type="button" :disabled="uploading" data-testid="upload-contact-files" @click.stop="openPicker">
        <LoaderCircle v-if="uploading" class="spin" :size="14" />
        <UploadCloud v-else :size="14" />
        {{ uploading ? (locale === 'en-US' ? 'Uploading…' : '正在上传…') : (locale === 'en-US' ? 'Upload files' : '上传文件') }}
      </button>
      <small>{{ locale === 'en-US' ? 'Or drop files here · 100 MiB per file' : '或拖放文件到此处 · 单个最大 100 MiB' }}</small>
    </div>

    <p v-if="error" class="file-error" role="alert">{{ error }}</p>
    <div v-if="loading" class="file-state"><LoaderCircle class="spin" :size="16" />{{ locale === 'en-US' ? 'Reading files…' : '正在读取文件…' }}</div>
    <div v-else-if="files.length" class="file-list" data-testid="contact-file-list">
      <article v-for="file in files" :key="file.id" class="file-row" :data-file-id="file.id">
        <span class="file-icon"><FileText :size="16" /></span>
        <div>
          <strong :title="file.fileName">{{ file.fileName }}</strong>
          <small>{{ formatSize(file.size) }} · {{ formatDisplayDate(file.uploadedAt) }}</small>
        </div>
        <nav>
          <button type="button" :aria-label="locale === 'en-US' ? `Download ${file.fileName}` : `下载 ${file.fileName}`" :disabled="activeFileId === file.id" @click="downloadFile(file)"><Download :size="14" /></button>
          <button v-if="canDelete" class="remove-file" type="button" :aria-label="locale === 'en-US' ? `Delete ${file.fileName}` : `删除 ${file.fileName}`" :disabled="activeFileId === file.id" @click="deleteFile(file)"><Trash2 :size="14" /></button>
        </nav>
      </article>
    </div>
    <p v-else-if="!error" class="file-empty">{{ locale === 'en-US' ? 'No contact files uploaded' : '尚未上传联系人文件' }}</p>
  </SectionCard>
</template>

<style scoped>
.file-input{display:none}.upload-zone{display:grid;justify-items:center;gap:8px;padding:17px 12px;background:#fbfcfc;border:1px dashed #aebfbe;border-radius:10px;outline:0;cursor:pointer;transition:.16s ease}.upload-zone:hover,.upload-zone.dragging,.upload-zone:focus-visible{background:#f0f8f7;border-color:var(--crm-teal);box-shadow:0 0 0 3px rgba(46,160,151,.12)}.upload-zone.disabled{cursor:default;opacity:.72}.upload-zone.disabled:hover{background:#fbfcfc;border-color:#aebfbe;box-shadow:none}.upload-icon{display:grid;width:34px;height:34px;place-items:center;color:var(--crm-teal);background:var(--crm-teal-soft);border-radius:10px}.upload-button{display:inline-flex;min-height:31px;align-items:center;gap:6px;padding:0 11px;color:var(--crm-navy);background:#fff;border:1px solid var(--crm-line-strong);border-radius:8px;font:inherit;font-size:9px;font-weight:800;cursor:pointer}.upload-button:not(:disabled):hover{color:var(--crm-teal);border-color:var(--crm-teal)}.upload-button:disabled{cursor:not-allowed;opacity:.6}.upload-zone small{color:var(--crm-text-muted);font-size:8px;text-align:center}.file-error{margin:10px 0 0;padding:9px 10px;color:var(--crm-danger);background:var(--crm-danger-soft);border:1px solid #ebc3c3;border-radius:8px;font-size:9px;line-height:1.45}.file-state,.file-empty{display:flex;align-items:center;justify-content:center;gap:6px;margin:10px 0 0;padding:9px;color:var(--crm-text-muted);font-size:8px}.file-list{display:grid;gap:7px;margin-top:11px}.file-row{display:grid;grid-template-columns:30px minmax(0,1fr) auto;align-items:center;gap:8px;padding:9px;background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:9px}.file-icon{display:grid;width:30px;height:30px;place-items:center;color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line);border-radius:8px}.file-row>div{display:grid;min-width:0;gap:3px}.file-row strong{overflow:hidden;color:var(--crm-navy);font-size:9px;text-overflow:ellipsis;white-space:nowrap}.file-row small{color:var(--crm-text-muted);font-size:7px}.file-row nav{display:flex;gap:3px}.file-row nav button{display:grid;width:28px;height:28px;place-items:center;color:var(--crm-teal);background:transparent;border:1px solid transparent;border-radius:7px;cursor:pointer}.file-row nav button:hover{background:#fff;border-color:var(--crm-line)}.file-row nav .remove-file{color:var(--crm-danger)}.file-row nav button:disabled{cursor:wait;opacity:.45}.spin{animation:spin .8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
</style>
