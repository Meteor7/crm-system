<script setup lang="ts">
import { requestErrorMessage } from '@/api/request-state'
import { personnelDisplayName } from '@/demo/personnel'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import RequiredMark from '@/design-system/RequiredMark.vue'
import {
  Building2,
  Check,
  ClipboardList,
  Download,
  Eye,
  File,
  FileLock2,
  FileText,
  Folder,
  History,
  Info,
  LockKeyhole,
  MessageSquareMore,
  Plus,
  ShieldCheck,
  UserRound,
  X,
} from '@lucide/vue'
import { api as defaultApi, usingMock } from '@/api'
import type { CrmApi } from '@/api'
import { useI18n, useLocaleMessage, localeMessage } from '@/i18n'
import type { UserRole } from '@/types/crm'
import type { ControlledDocumentAccessRequestDto, ControlledDocumentDto, DocumentUploadInput, DocumentUploadRequestDto } from '@/types/workspaces'
import type { MultipartFilePart } from '@/api/binary-transport'
import { downloadBlob } from '@/features/shared/download-blob'
import { readAllPages } from '@/features/shared/read-all-pages'
import { formatDisplayDate } from '@/domain/time'

type LibraryFilter = 'All' | 'Technical' | 'Commercial'
type DetailTab = 'details' | 'versions' | 'audit'
type ApprovalDecision = 'approve-watermarked' | 'approve-original' | 'reject' | 'more-info'

interface ApprovalRequest {
  kind: 'access' | 'upload'
  id: string
  requester: string
  initials: string
  role: string
  team: string
  documentId: string
  documentTitle: string
  version: string
  revision: string
  submittedAt: string
  reason: string
  status: 'Manager Review' | 'Document Manager Review' | 'Approved' | 'More Info Required' | 'Rejected'
  upload?: DocumentUploadRequestDto
}

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), {
  apiClient: () => defaultApi,
})
const route = useRoute()
const { t, locale } = useI18n()
const documentLabels: Record<string, [string, string]> = {
  Internal: ['内部', 'Internal'], Confidential: ['机密', 'Confidential'], Restricted: ['受限', 'Restricted'],
  Released: ['已发布', 'Released'], Published: ['已发布', 'Published'], Superseded: ['已替代', 'Superseded'], Obsolete: ['已废弃', 'Obsolete'],
  Manager: ['经理', 'Manager'], Sales: ['销售', 'Sales'], Engineer: ['工程师', 'Engineer'],
  Engineering: ['工程团队', 'Engineering'], Management: ['管理团队', 'Management'],
}
function documentLabel(value: string) { return documentLabels[value]?.[locale.value === 'en-US' ? 1 : 0] ?? value }
const invalidPreview = new Error('Invalid controlled PDF')
const invalidDownload = new Error('Invalid controlled file type')


const libraryItems: Array<{ value: LibraryFilter; label: string; icon: typeof Folder }> = [
  { value: 'All', label: '全部文档', icon: Folder },
  { value: 'Technical', label: '技术文档', icon: FileText },
  { value: 'Commercial', label: '商务文档', icon: ClipboardList },
]
function libraryLabel(value: LibraryFilter) {
  if (locale.value === 'en-US') return value === 'All' ? 'All documents' : value === 'Technical' ? 'Technical documents' : 'Commercial documents'
  return libraryItems.find((item) => item.value === value)?.label ?? value
}

const approvalRequests = ref<ApprovalRequest[]>([])
const workspaceMode = ref<'library' | 'approvals'>('library')
const uploadOpen = ref(false)
const uploadSubmitting = ref(false)
const uploadError = useLocaleMessage()
const uploadDecisionReason = ref('')
const uploadForm = ref<DocumentUploadInput>({ title: '', category: 'Technical', documentType: '', accessMode: 'Request', confidentiality: 'Confidential', product: '', version: '1.0', revision: 'R1', reviewDate: '', applicableTool: '' })
const uploadFile = ref<File | null>(null)

const controlledDocuments = ref<ControlledDocumentDto[]>([])
const selectedId = ref('')
const selectedRequestId = ref(approvalRequests.value[0]?.id ?? '')
const role = ref<UserRole>('Sales')
const currentUserName = ref('')
const currentUserTeam = ref('')
const libraryFilter = ref<LibraryFilter>('All')
const activeDetailTab = ref<DetailTab>('details')
const requestReason = ref('')
const requestError = useLocaleMessage()
const requestedIds = ref(new Set<string>())
const loading = ref(true)
const approvalLoading = ref(false)
const submitting = ref(false)
const error = useLocaleMessage()
const accessApprovalError = useLocaleMessage()
const uploadApprovalError = useLocaleMessage()
const notice = useLocaleMessage()
const previewUrl = ref('')
const previewLoading = ref(false)
const previewError = useLocaleMessage()
const downloading = ref(false)
const decidingRequestId = ref('')
let previewRequest = 0

function applyWorkspaceQuery() {
  workspaceMode.value = role.value === 'Manager' && route?.query?.workspace === 'approvals'
    ? 'approvals'
    : 'library'
}

const isApprovalWorkspace = computed(() => role.value === 'Manager' && workspaceMode.value === 'approvals')
const isManagementReadonly = computed(() => false)
const selected = computed(() =>
  controlledDocuments.value.find((document) => document.id === selectedId.value)
  ?? filteredDocuments.value[0]
  ?? controlledDocuments.value[0],
)
const selectedRequest = computed(() =>
  approvalRequests.value.find((request) => request.id === selectedRequestId.value)
  ?? approvalRequests.value[0],
)
const approvalDocument = computed(() =>
  controlledDocuments.value.find((document) => document.id === selectedRequest.value?.documentId)
  ?? controlledDocuments.value.find((document) => document.id === 'DOC-PRICE-26')
  ?? controlledDocuments.value[0],
)
const filteredDocuments = computed(() => {
  return controlledDocuments.value.filter((document) => libraryFilter.value === 'All' || document.category === libraryFilter.value)
})
const categoryCounts = computed(() => ({
  All: controlledDocuments.value.length,
  Technical: controlledDocuments.value.filter((document) => document.category === 'Technical').length,
  Commercial: controlledDocuments.value.filter((document) => document.category === 'Commercial').length,
}))
const requestSubmitted = computed(() => Boolean(
  selected.value
  && (requestedIds.value.has(selected.value.id) || selected.value.accessRequest?.status === 'Pending'),
))

function loadAllControlledDocuments() {
  return readAllPages((page, pageSize) => props.apiClient.listControlledDocuments({ page, pageSize }))
}

function loadAllAccessRequests() {
  return readAllPages((page, pageSize) => props.apiClient.listControlledDocumentRequests({ page, pageSize }))
}

function loadAllUploadRequests() {
  return readAllPages((page, pageSize) => props.apiClient.listControlledDocumentUploadRequests({ page, pageSize }))
}

function mapApprovalRequest(item: ControlledDocumentAccessRequestDto): ApprovalRequest {
  const document = controlledDocuments.value.find((candidate) => candidate.id === item.documentId)
  const words = item.requesterName.trim().split(/\s+/)
  return {
    kind: 'access',
    id: item.id,
    requester: item.requesterName,
    initials: words.map((word) => word[0]).join('').slice(0, 2).toUpperCase(),
    role: item.requesterRole,
    team: item.requesterRole === 'Engineer' ? 'Engineering' : item.requesterRole === 'Sales' ? 'Sales' : 'Management',
    documentId: item.documentId,
    documentTitle: item.documentTitle,
    version: document?.version ?? item.versionId,
    revision: document?.revision ?? '',
    submittedAt: item.submittedAt,
    reason: item.reason,
    status: item.status === 'Pending' ? 'Manager Review' : item.status,
  }
}

function mapUploadRequest(item: DocumentUploadRequestDto): ApprovalRequest {
  const words = item.submittedByName.trim().split(/\s+/)
  return {
    kind: 'upload', id: item.id, requester: item.submittedByName,
    initials: words.map((word) => word[0]).join('').slice(0, 2).toUpperCase(),
    role: item.submittedByRole, team: item.submittedByRole === 'Engineer' ? 'Engineering' : 'Sales',
    documentId: item.id, documentTitle: item.title, version: item.version || '1.0', revision: item.revision || 'R1',
    submittedAt: item.submittedAt, reason: `${item.category} · ${item.documentType} · ${item.fileName}`,
    status: 'Manager Review', upload: item,
  }
}

function selectUploadFile(event: Event) {
  uploadFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

async function submitDocumentUpload() {
  const file = uploadFile.value
  if (!uploadForm.value.title.trim() || !uploadForm.value.documentType.trim() || !file) {
    uploadError.value = localeMessage('Enter a title and document type, then select a file.', '请填写标题、文档类型并选择文件。')
    return
  }
  uploadSubmitting.value = true
  uploadError.value = ''
  try {
    const part: MultipartFilePart = { blob: file, fileName: file.name, mimeType: file.type, size: file.size }
    const result = await props.apiClient.submitControlledDocumentUpload(uploadForm.value, part)
    uploadOpen.value = false
    notice.value = result.data.status === 'Published' ? (localeMessage('Document published and archived.', '文档已直接发布并归档。')) : (localeMessage('Document submitted and waiting for Manager review.', '文档已提交，等待经理审核。'))
    if (result.data.status === 'Published') {
      controlledDocuments.value = await loadAllControlledDocuments()
    }
  } catch (reason) {
    uploadError.value = requestErrorMessage(reason, (localeMessage('Document upload failed.', '文档上传失败')))
  } finally {
    uploadSubmitting.value = false
  }
}

function chooseLibrary(value: LibraryFilter) {
  libraryFilter.value = value
  const first = controlledDocuments.value.find((document) => value === 'All' || document.category === value)
  selectedId.value = first?.id ?? ''
  activeDetailTab.value = 'details'
  requestError.value = ''
}

function chooseDocument(documentId: string) {
  selectedId.value = documentId
  activeDetailTab.value = 'details'
  requestReason.value = ''
  requestError.value = ''
  notice.value = ''
}

async function submitAccessRequest() {
  const document = selected.value
  const reason = requestReason.value.trim()
  if (!document?.versionId) return
  if (!reason) {
    requestError.value = localeMessage('Enter a business purpose before submitting.', '请填写访问用途后再提交')
    return
  }

  submitting.value = true
  requestError.value = ''
  try {
    const result = await props.apiClient.requestControlledDocumentAccess(document.versionId, reason)
    document.accessRequest = result.data
    requestedIds.value = new Set([...requestedIds.value, document.id])
    notice.value = localeMessage('Access request submitted. Current status: Manager Review.', '访问申请已提交，当前状态为经理审核')
  } catch (reasonError) {
    requestError.value = requestErrorMessage(reasonError, (localeMessage('Access request failed.', '访问申请提交失败')))
  } finally {
    submitting.value = false
  }
}

function showControlledDownloadNotice() {
  if (!selected.value || selected.value.access !== 'Direct') return
  notice.value = localeMessage(`Demo: controlled download logged for ${selected.value.id} ${selected.value.version}/${selected.value.revision} by ${currentUserName.value}.`, `Demo：已为 ${currentUserName.value} 生成 ${selected.value.id} ${selected.value.version}/${selected.value.revision} 的受控下载记录`)
}

function releasePreviewUrl() {
  if (!previewUrl.value) return
  URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
}

async function loadControlledPreview() {
  const request = ++previewRequest
  releasePreviewUrl()
  previewError.value = ''
  if (usingMock || !selected.value?.canPreview) return
  previewLoading.value = true
  try {
    const file = await props.apiClient.previewControlledDocument(selected.value.id)
    if (request !== previewRequest) return
    if (file.mimeType !== 'application/pdf' || file.blob.size === 0) throw invalidPreview
    previewUrl.value = URL.createObjectURL(file.blob)
  } catch (reason) {
    if (request === previewRequest) previewError.value = reason === invalidPreview ? localeMessage('The server did not return a valid controlled PDF.', '服务端未返回有效的受控 PDF') : requestErrorMessage(reason, (localeMessage('Controlled preview generation failed.', '受控预览生成失败')))
  } finally {
    if (request === previewRequest) previewLoading.value = false
  }
}

async function downloadControlledDocument() {
  if (!selected.value?.canDownload || downloading.value) return
  const document = selected.value
  downloading.value = true
  notice.value = ''
  try {
    const file = await props.apiClient.downloadControlledDocument(document.id)
    const expectedMime = document.deliveryMode === 'Original'
      ? document.mimeType
      : 'application/pdf'
    if (file.mimeType !== expectedMime || file.blob.size === 0) throw invalidDownload
    downloadBlob(file.blob, file.fileName)
    notice.value = role.value === 'Manager' ? (localeMessage(`Clean original for ${document.id} downloaded; action logged.`, `已下载 ${document.id} 的无水印原件，下载行为已记录`)) : document.deliveryMode === 'Original' ? (localeMessage(`Approved original for ${document.id} downloaded; action logged.`, `已下载 ${document.id} 的批准原件，下载行为已记录`)) : (localeMessage(`Personal watermarked PDF for ${document.id} generated; action logged.`, `已生成 ${document.id} 的个人水印 PDF，下载行为已记录`))
  } catch (reason) {
    notice.value = reason === invalidDownload ? localeMessage('The server returned an invalid controlled file type.', '服务端返回的受控文件类型不正确') : requestErrorMessage(reason, (localeMessage('Controlled download failed.', '受控下载生成失败')))
  } finally {
    downloading.value = false
  }
}

async function decideRequest(decision: ApprovalDecision) {
  if (isManagementReadonly.value || !selectedRequest.value || decidingRequestId.value) return
  const request = selectedRequest.value
  decidingRequestId.value = request.id
  if (request.kind === 'upload' && request.upload) {
    try {
      const input = decision === 'reject'
        ? { decision: 'reject' as const, reason: uploadDecisionReason.value.trim() }
        : { decision: 'approve' as const, category: request.upload.category, confidentiality: request.upload.confidentiality, accessMode: request.upload.accessMode }
      if (input.decision === 'reject' && !input.reason) {
        notice.value = localeMessage('A reason is required when rejecting an upload.', '拒绝上传时必须填写原因。')
        return
      }
      const result = await props.apiClient.decideControlledDocumentUploadRequest(request.id, input)
      request.status = result.data.status === 'Published' ? 'Approved' : 'Rejected'
      notice.value = result.data.status === 'Published' ? (localeMessage('Uploaded document approved and archived.', '上传文档已批准归档。')) : (localeMessage('Uploaded document rejected.', '上传文档已拒绝。'))
      approvalRequests.value = approvalRequests.value.filter((item) => item.id !== request.id)
      selectedRequestId.value = approvalRequests.value[0]?.id ?? ''
    } catch (decisionError) {
      notice.value = requestErrorMessage(decisionError, (localeMessage('Approval action failed.', '审批操作失败')))
    } finally {
      decidingRequestId.value = ''
    }
    return
  }
  if (!usingMock) {
    try {
      const result = await props.apiClient.decideControlledDocumentRequest(request.id, decision)
      const mapped = mapApprovalRequest(result.data)
      Object.assign(request, mapped)
    } catch (decisionError) {
      notice.value = requestErrorMessage(decisionError, (localeMessage('Approval action failed.', '审批操作失败')))
      decidingRequestId.value = ''
      return
    }
  }
  const nextStatus: ApprovalRequest['status'] = decision.startsWith('approve-')
    ? 'Approved'
    : decision === 'reject'
      ? 'Rejected'
      : 'More Info Required'
  selectedRequest.value.status = nextStatus
  notice.value = decision === 'approve-watermarked' ? (localeMessage('Watermarked PDF preview and download approved.', '已批准水印 PDF 预览与下载')) : decision === 'approve-original' ? (localeMessage('Original PPTX download approved; preview still uses a personal watermarked PDF.', '已批准原始 PPTX 下载；预览仍使用个人水印 PDF')) : decision === 'reject' ? (localeMessage('Access request rejected.', '已拒绝该访问申请')) : (localeMessage('Applicant asked to provide more information.', '已要求申请人补充信息'))
  approvalRequests.value = approvalRequests.value.filter((item) => item.id !== request.id)
  selectedRequestId.value = approvalRequests.value[0]?.id ?? ''
  decidingRequestId.value = ''
}

function requestStatusLabel(status: ApprovalRequest['status']) {
  const labels: Record<ApprovalRequest['status'], string> = {
    'Manager Review': locale.value === 'en-US' ? 'Manager review' : '经理审核',
    'Document Manager Review': locale.value === 'en-US' ? 'Document manager review' : '文档管理员审核',
    Approved: locale.value === 'en-US' ? 'Approved' : '已批准',
    'More Info Required': locale.value === 'en-US' ? 'More information required' : '待补充信息',
    Rejected: locale.value === 'en-US' ? 'Rejected' : '已拒绝',
  }
  return labels[status]
}

function statusTone(status: ApprovalRequest['status']) {
  if (status === 'Approved') return 'positive'
  if (status === 'Rejected') return 'danger'
  return 'warning'
}

function confidentialityClass(value: string) {
  if (value === 'Restricted') return 'danger'
  if (value === 'Confidential') return 'warning'
  return 'info'
}

async function loadDocumentLibrary() {
  try {
    controlledDocuments.value = await loadAllControlledDocuments()
    selectedId.value = controlledDocuments.value[0]?.id ?? ''
  } catch (loadError) {
    error.value = requestErrorMessage(loadError, localeMessage('Document Center failed to load.', 'Document Center 加载失败'))
  } finally {
    loading.value = false
  }
}

async function loadApprovalQueues() {
  approvalLoading.value = true
  accessApprovalError.value = ''
  uploadApprovalError.value = ''
  const [accessResult, uploadResult] = await Promise.allSettled([
    loadAllAccessRequests(),
    loadAllUploadRequests(),
  ])
  const requests = accessResult.status === 'fulfilled'
    ? accessResult.value.map(mapApprovalRequest)
    : []
  const uploads = uploadResult.status === 'fulfilled'
    ? uploadResult.value.map(mapUploadRequest)
    : []
  if (accessResult.status === 'rejected') {
    accessApprovalError.value = requestErrorMessage(accessResult.reason, localeMessage('Access approval queue failed to load.', '访问审批队列加载失败'))
  }
  if (uploadResult.status === 'rejected') {
    uploadApprovalError.value = requestErrorMessage(uploadResult.reason, localeMessage('Upload approval queue failed to load.', '上传审批队列加载失败'))
  }
  approvalRequests.value = [...requests, ...uploads].sort((left, right) => right.submittedAt.localeCompare(left.submittedAt))
  selectedRequestId.value = approvalRequests.value[0]?.id ?? ''
  approvalLoading.value = false
}

onMounted(async () => {
  try {
  const bootstrapResult = await props.apiClient.getBootstrap()
  role.value = bootstrapResult.data.user.role
  currentUserName.value = bootstrapResult.data.user.name
  currentUserTeam.value = bootstrapResult.data.user.team
  applyWorkspaceQuery()
  } catch (loadError) {
    error.value = requestErrorMessage(loadError, localeMessage('Document Center failed to load.', 'Document Center 加载失败'))
    loading.value = false
    return
  }
  void loadDocumentLibrary()
  if (role.value === 'Manager') void loadApprovalQueues()
})

watch(() => route?.query?.workspace, applyWorkspaceQuery)

watch(() => selected.value?.id, () => {
  void loadControlledPreview()
})

onBeforeUnmount(() => {
  previewRequest += 1
  releasePreviewUrl()
})
</script>

<template>
  <div class="workspace-page" data-page="document-center">
    <header class="page-title-row">
      <div>
        <span class="eyebrow">DOCUMENT GOVERNANCE · CONTROLLED ACCESS</span>
        <h1>{{ t('documents.title') }}</h1>
        <p>
          {{ isApprovalWorkspace
            ? t('documents.approvalDescription')
            : t('documents.libraryDescription') }}
        </p>
      </div>
      <div class="document-header-actions">
        <button type="button" class="primary-button upload-document-button" data-upload-document @click="uploadOpen = true">
          <Plus :size="15" />{{ t('documents.upload') }}
        </button>
        <span class="context-chip">
          <Eye v-if="isManagementReadonly" :size="15" />
          <ShieldCheck v-else :size="15" />
          {{ documentLabel(role) }} · {{ isManagementReadonly ? t('documents.readonly') : currentUserName }}
        </span>
      </div>
    </header>

    <nav v-if="role === 'Manager'" class="workspace-filter-row document-workspace-tabs" aria-label="Document Center workspace">
      <button type="button" data-workspace-tab="library" :class="{ active: workspaceMode === 'library' }" :aria-pressed="workspaceMode === 'library'" @click="workspaceMode = 'library'">{{ t('documents.library') }}</button>
      <button type="button" data-workspace-tab="approvals" :class="{ active: workspaceMode === 'approvals' }" :aria-pressed="workspaceMode === 'approvals'" @click="workspaceMode = 'approvals'">{{ t('documents.approvals') }} <b>{{ approvalRequests.length }}</b></button>
    </nav>

    <p v-if="notice" class="document-notice" role="status">
      <Check :size="15" />
      {{ notice }}
    </p>
    <p v-if="isApprovalWorkspace && accessApprovalError" class="document-notice approval-load-error" data-approval-load-error="access" role="alert">
      {{ accessApprovalError }}
    </p>
    <p v-if="isApprovalWorkspace && uploadApprovalError" class="document-notice approval-load-error" data-approval-load-error="upload" role="alert">
      {{ uploadApprovalError }}
    </p>

    <section v-if="loading" class="workspace-panel document-state">
      <span /><span /><span />
    </section>
    <section v-else-if="error" class="workspace-panel document-state is-error">{{ error }}</section>

    <template v-else>
      <section
        v-if="isApprovalWorkspace && selectedRequest"
        class="approval-grid"
        data-approval-workspace
      >
        <aside class="workspace-panel approval-queue">
          <header class="queue-header">
            <div>
              <span class="queue-heading-icon"><ClipboardList :size="17" /></span>
              <span class="queue-heading-copy">
                <h2>{{ locale === 'en-US' ? 'Approval queue' : '审批队列' }}</h2>
                <small>ACCESS &amp; UPLOAD REQUESTS</small>
              </span>
            </div>
            <span class="queue-count"><b>{{ approvalRequests.length }}</b> {{ locale === 'en-US' ? 'pending' : '待处理' }}</span>
          </header>
          <div class="workspace-panel-body">
            <div class="queue-context">
              <span><i />{{ locale === 'en-US' ? 'Awaiting my approval' : '待我审批' }}</span>
              <small>{{ locale === 'en-US' ? 'Sorted by submission time' : '按提交时间排序' }}</small>
            </div>
            <div class="workspace-list request-list">
              <button
                v-for="request in approvalRequests"
                :key="request.id"
                type="button"
                class="workspace-select-card request-card"
                :class="{ active: request.id === selectedRequest.id }"
                :aria-pressed="request.id === selectedRequest.id"
                @click="selectedRequestId = request.id; notice = ''"
              >
                <span class="request-avatar">{{ request.initials }}</span>
                <span class="request-copy">
                  <strong>{{ request.requester }}</strong>
                  <small>{{ request.kind === 'upload' ? (locale === 'en-US' ? 'Upload archive' : '上传归档') : (locale === 'en-US' ? 'Access request' : '访问申请') }} · {{ documentLabel(request.role) }} · {{ documentLabel(request.team) }}</small>
                </span>
                <span class="workspace-badge" :class="statusTone(request.status)">
                  {{ requestStatusLabel(request.status) }}
                </span>
                <span class="request-document">
                  <FileLock2 :size="14" />
                  <span><b>{{ request.documentTitle }}</b><small>{{ request.documentId }}</small></span>
                </span>
                <span class="request-card-footer">
                  <time>{{ formatDisplayDate(request.submittedAt) }}</time>
                  <small>{{ request.id }}</small>
                </span>
              </button>
            </div>
          </div>
        </aside>

        <article class="workspace-panel approval-detail">
          <header>
            <div>
              <h2>{{ selectedRequest.documentTitle }}</h2>
              <span>{{ selectedRequest.documentId }} · {{ selectedRequest.version }} / {{ selectedRequest.revision }}</span>
            </div>
            <span class="workspace-badge danger">{{ documentLabel('Restricted') }}</span>
          </header>

          <div class="workspace-panel-body approval-body">
            <p v-if="isManagementReadonly" class="readonly-notice" data-management-readonly>
              <Eye :size="17" />
              <span><strong>Manager · {{ locale === 'en-US' ? 'Read-only' : '只读' }}</strong>{{ locale === 'en-US' ? 'Can view approvals and audits but cannot approve, reject, or request more information.' : '可查看审批与审计，无法批准、拒绝或要求补充信息。' }}</span>
            </p>

            <section class="request-summary">
              <div><UserRound :size="15" /><span><small>{{ locale === 'en-US' ? 'Requester' : '申请人' }}</small><strong>{{ selectedRequest.requester }}</strong></span></div>
              <div><ShieldCheck :size="15" /><span><small>{{ locale === 'en-US' ? 'User role' : '用户角色' }}</small><strong>{{ documentLabel(selectedRequest.role) }}</strong></span></div>
              <div><Building2 :size="15" /><span><small>{{ locale === 'en-US' ? 'Team' : '业务组' }}</small><strong>{{ documentLabel(selectedRequest.team) }}</strong></span></div>
              <div><History :size="15" /><span><small>{{ locale === 'en-US' ? 'Submitted' : '提交时间' }}</small><strong>{{ formatDisplayDate(selectedRequest.submittedAt) }}</strong></span></div>
              <div class="request-reason"><ClipboardList :size="15" /><span><small>{{ locale === 'en-US' ? 'Reason' : '申请原因' }}</small><strong>{{ selectedRequest.reason }}</strong></span></div>
            </section>

            <section class="approval-flow" data-approval-timeline>
              <header><h3>{{ locale === 'en-US' ? 'Approval flow' : '审批流程' }}</h3><span class="workspace-badge warning">{{ locale === 'en-US' ? 'Current: manager review' : '当前：经理审核' }}</span></header>
              <ol class="stage-rail">
                <li class="is-done"><i /><span>{{ locale === 'en-US' ? 'Submitted' : '已提交' }}</span></li>
                <li class="is-current"><i /><span>{{ locale === 'en-US' ? 'Manager review' : '经理审核' }}</span></li>
                <li><i /><span>{{ locale === 'en-US' ? 'Document manager review' : '文档管理员审核' }}</span></li>
              </ol>
            </section>

            <section v-if="selectedRequest.kind === 'upload' && selectedRequest.upload" class="upload-approval-fields" data-upload-approval-fields>
              <label>{{ locale === 'en-US' ? 'Archive section' : '归档板块' }}<select v-model="selectedRequest.upload.category"><option value="Technical">{{ locale === 'en-US' ? 'Technical documents' : '技术文档' }}</option><option value="Commercial">{{ locale === 'en-US' ? 'Commercial documents' : '商务文档' }}</option></select></label>
              <label>{{ locale === 'en-US' ? 'Confidentiality' : '密级' }}<select v-model="selectedRequest.upload.confidentiality"><option v-for="level in ['Internal', 'Confidential', 'Restricted']" :key="level" :value="level">{{ documentLabel(level) }}</option></select></label>
              <label>{{ locale === 'en-US' ? 'Access mode' : '访问方式' }}<select v-model="selectedRequest.upload.accessMode"><option value="Direct">{{ locale === 'en-US' ? 'Direct access' : '直接访问' }}</option><option value="Request">{{ locale === 'en-US' ? 'Request access' : '申请后访问' }}</option></select></label>
              <label class="wide">{{ locale === 'en-US' ? 'Rejection reason' : '拒绝原因' }}<textarea v-model="uploadDecisionReason" :placeholder="locale === 'en-US' ? 'Required when rejecting' : '拒绝时必填'"></textarea></label>
            </section>

            <section class="decision-bar">
              <div>
                <small>{{ locale === 'en-US' ? 'Authorization policy' : '授权策略' }}</small>
                <strong>{{ locale === 'en-US' ? 'Choose watermarked PDF or original PPTX during approval' : '审批时明确选择水印 PDF 或原始 PPTX' }}</strong>
              </div>
              <div class="approval-actions">
                <button
                  v-if="selectedRequest.kind === 'upload'"
                  type="button"
                  class="primary-button"
                  data-approval-action="approve-upload"
                  :disabled="selectedRequest.status !== 'Manager Review' || decidingRequestId === selectedRequest.id"
                  @click="decideRequest('approve-original')"
                >
                  <Check :size="15" />{{ locale === 'en-US' ? 'Approve archive' : '批准归档' }}
                </button>
                <button
                  v-if="selectedRequest.kind === 'upload'"
                  type="button"
                  class="secondary-button danger-action"
                  data-approval-action="reject-upload"
                  :disabled="selectedRequest.status !== 'Manager Review' || decidingRequestId === selectedRequest.id"
                  @click="decideRequest('reject')"
                >
                  <X :size="15" />{{ locale === 'en-US' ? 'Reject' : '拒绝' }}
                </button>
                <button
                  v-if="selectedRequest.kind === 'access'"
                  type="button"
                  class="primary-button"
                  data-approval-action="approve-watermarked"
                  :disabled="isManagementReadonly || selectedRequest.status !== 'Manager Review' || decidingRequestId === selectedRequest.id"
                  @click="decideRequest('approve-watermarked')"
                >
                  <Check :size="15" />{{ locale === 'en-US' ? 'Approve watermarked PDF' : '批准水印 PDF' }}
                </button>
                <button
                  v-if="selectedRequest.kind === 'access'"
                  type="button"
                  class="primary-button"
                  data-approval-action="approve-original"
                  :disabled="isManagementReadonly || selectedRequest.status !== 'Manager Review' || decidingRequestId === selectedRequest.id"
                  @click="decideRequest('approve-original')"
                >
                  <Download :size="15" />{{ locale === 'en-US' ? 'Approve original PPTX' : '批准原始 PPTX' }}
                </button>
                <button
                  v-if="selectedRequest.kind === 'access'"
                  type="button"
                  class="secondary-button danger-action"
                  data-approval-action="reject"
                  :disabled="isManagementReadonly || selectedRequest.status !== 'Manager Review' || decidingRequestId === selectedRequest.id"
                  @click="decideRequest('reject')"
                >
                  <X :size="15" />{{ locale === 'en-US' ? 'Reject' : '拒绝' }}
                </button>
                <button
                  v-if="selectedRequest.kind === 'access'"
                  type="button"
                  class="secondary-button"
                  data-approval-action="more-info"
                  :disabled="isManagementReadonly || selectedRequest.status !== 'Manager Review' || decidingRequestId === selectedRequest.id"
                  @click="decideRequest('more-info')"
                >
                  <MessageSquareMore :size="15" />{{ locale === 'en-US' ? 'Request more info' : '补充信息' }}
                </button>
              </div>
              <p class="approval-status" data-approval-status>
                {{ locale === 'en-US' ? 'Current status: ' : '当前状态：' }}<strong>{{ requestStatusLabel(selectedRequest.status) }}</strong>
              </p>
            </section>

            <section class="evidence-grid">
              <article class="evidence-card" data-version-history>
                <header><h3>{{ locale === 'en-US' ? 'Version history' : '版本历史' }}</h3><span>{{ approvalDocument?.versions.length ?? 0 }} {{ locale === 'en-US' ? 'items' : '条' }}</span></header>
                <div class="table-scroll">
                  <table class="crm-table evidence-table">
                    <thead><tr><th>{{ locale === 'en-US' ? 'Version' : '版本' }}</th><th>{{ locale === 'en-US' ? 'Status' : '状态' }}</th><th>{{ locale === 'en-US' ? 'Published' : '发布日期' }}</th></tr></thead>
                    <tbody>
                      <tr v-for="version in approvalDocument?.versions ?? []" :key="`${version.version}-${version.revision}`">
                        <td><strong>{{ version.version }} / {{ version.revision }}</strong></td>
                        <td><span class="workspace-badge" :class="version.status === 'Released' ? 'positive' : ''">{{ documentLabel(version.status) }}</span></td>
                        <td>{{ formatDisplayDate(version.releasedAt) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </article>

              <article class="evidence-card" data-download-audit>
                <header><h3>{{ locale === 'en-US' ? 'Download audit' : '下载审计' }}</h3><span>{{ locale === 'en-US' ? 'Authorized access log' : '授权访问记录' }}</span></header>
                <p class="audit-note"><Info :size="14" />{{ locale === 'en-US' ? 'No download record is created before approval.' : '批准前不会生成本次下载记录。' }}</p>
                <div class="audit-list">
                  <div><strong>Irene Li</strong><span>Manager</span><time>2026-06-20</time><small>{{ locale === 'en-US' ? 'Controlled download' : '受控下载' }}</small></div>
                  <div><strong>Michael Zhang</strong><span>Sales Director</span><time>2026-05-18</time><small>{{ locale === 'en-US' ? 'Controlled download' : '受控下载' }}</small></div>
                </div>
              </article>
            </section>
          </div>
        </article>
      </section>

      <section v-else-if="isApprovalWorkspace" class="workspace-panel document-state approval-empty" data-approval-empty>
        <ClipboardList :size="28" />
        <h2>{{ approvalLoading ? (locale === 'en-US' ? 'Loading approval queue' : '正在加载审批队列') : (locale === 'en-US' ? 'No pending requests' : '暂无待审批申请') }}</h2>
        <p>{{ approvalLoading ? (locale === 'en-US' ? 'The document library remains available.' : '文档库仍可独立浏览。') : (locale === 'en-US' ? 'No document access requests require this Manager in Frappe.' : '当前 Frappe 数据库没有需要该 Manager 处理的文档访问申请。') }}</p>
      </section>

      <template v-else>
        <nav class="workspace-filter-row document-filters" :aria-label="locale === 'en-US' ? 'Document type' : '文档类型'" data-document-library>
          <button
            v-for="item in libraryItems"
            :key="item.value"
            type="button"
            :class="{ active: libraryFilter === item.value }"
            :data-library-filter="item.value"
            @click="chooseLibrary(item.value)"
          >
            <component :is="item.icon" :size="14" />
            {{ libraryLabel(item.value) }}
            <b>{{ categoryCounts[item.value] }}</b>
          </button>
        </nav>

        <section v-if="selected" class="document-grid" data-document-workspace>
          <aside class="workspace-panel document-list-panel">
            <header>
              <h2>{{ libraryLabel(libraryFilter) }}</h2>
              <span>{{ filteredDocuments.length }} {{ locale === 'en-US' ? 'visible documents' : '份可见文档' }}</span>
            </header>
            <div class="workspace-panel-body document-list-body">
              <div v-if="filteredDocuments.length" class="workspace-list document-list">
                <button
                  v-for="document in filteredDocuments"
                  :key="document.id"
                  type="button"
                  class="workspace-select-card document-row"
                  :class="{ active: document.id === selected.id }"
                  :data-document-id="document.id"
                  data-document-row
                  @click="chooseDocument(document.id)"
                >
                  <span class="document-type-icon">
                    <File v-if="document.type.includes('Template')" :size="18" />
                    <FileText v-else :size="18" />
                    <LockKeyhole v-if="document.access === 'Request'" :size="10" class="row-lock" />
                  </span>
                  <span class="document-row-copy">
                    <strong>{{ document.title }}</strong>
                    <small>{{ document.id }} · {{ document.product }}</small>
                  </span>
                  <span class="workspace-badge" :class="confidentialityClass(document.confidentiality)">
                    {{ document.access === 'Direct' ? (locale === 'en-US' ? 'Direct access' : '直接访问') : documentLabel(document.confidentiality) }}
                  </span>
                  <span class="document-row-meta">
                    <small>{{ document.version }} / {{ document.revision }}</small>
                    <b>{{ personnelDisplayName(document.owner) }}</b>
                  </span>
                </button>
              </div>
              <p v-else class="workspace-empty-note">{{ locale === 'en-US' ? 'No documents match the current filters.' : '没有符合当前筛选条件的文档。' }}</p>
            </div>
          </aside>

          <article class="workspace-panel document-detail-panel">
            <header>
              <div>
                <h2>{{ selected.title }}</h2>
                <span>{{ selected.id }} · {{ selected.version }} / {{ selected.revision }}</span>
              </div>
              <span class="workspace-badge" :class="confidentialityClass(selected.confidentiality)">
                {{ documentLabel(selected.confidentiality) }}
              </span>
            </header>

            <div class="document-tabs">
              <button type="button" :class="{ active: activeDetailTab === 'details' }" @click="activeDetailTab = 'details'">
                {{ selected.access === 'Request' ? (locale === 'en-US' ? 'Access request' : '访问申请') : (locale === 'en-US' ? 'Document details' : '文档详情') }}
              </button>
              <button type="button" :class="{ active: activeDetailTab === 'versions' }" @click="activeDetailTab = 'versions'">{{ locale === 'en-US' ? 'Version history' : '版本历史' }}</button>
              <button type="button" :class="{ active: activeDetailTab === 'audit' }" @click="activeDetailTab = 'audit'">{{ locale === 'en-US' ? 'Download audit' : '下载审计' }}</button>
            </div>

            <div v-if="activeDetailTab === 'details'" class="workspace-panel-body preview-layout">
              <section
                v-if="selected.canPreview"
                class="document-preview"
                data-document-preview="direct"
              >
                <template v-if="usingMock">
                  <div class="preview-toolbar">
                    <span>{{ locale === 'en-US' ? 'Preview · Demo' : '预览 · Demo' }}</span>
                    <b>100%</b>
                  </div>
                  <div class="pdf-stage">
                  <article class="pdf-sheet">
                    <div class="pdf-brand">PLANCK <small>SEMICONDUCTOR</small></div>
                    <span>{{ selected.type.toUpperCase() }}</span>
                    <h3>{{ selected.title }}</h3>
                    <p>{{ selected.product }} · Version {{ selected.version }} / {{ selected.revision }}</p>
                    <div class="pdf-figure"><i /><i /><i /></div>
                    <dl>
                      <div><dt>Document ID</dt><dd>{{ selected.id }}</dd></div>
                      <div><dt>Status</dt><dd>{{ selected.status }}</dd></div>
                      <div><dt>Owner</dt><dd>{{ personnelDisplayName(selected.owner) }}</dd></div>
                    </dl>
                    <div v-if="role !== 'Manager'" class="pdf-watermark">{{ currentUserName }} · {{ selected.id }} · CONTROLLED COPY</div>
                  </article>
                  </div>
                </template>
                <div v-else-if="previewLoading" class="real-preview-state" data-preview-loading>
                  <span class="preview-spinner" />
                  <strong>{{ role === 'Manager' ? (locale === 'en-US' ? 'Loading clean preview' : '正在加载无水印预览') : (locale === 'en-US' ? 'Generating your watermarked preview' : '正在生成个人水印预览') }}</strong>
                  <small>{{ role === 'Manager' ? (locale === 'en-US' ? 'Manager view uses the integrity-checked version' : 'Manager 查看经过完整性校验的清晰版本') : (locale === 'en-US' ? 'Each page includes the current account and unique access ID' : '每一页将写入当前账号和唯一访问编号') }}</small>
                </div>
                <div v-else-if="previewError" class="real-preview-state is-error" data-preview-error>
                  <strong>{{ locale === 'en-US' ? 'Preview failed' : '预览生成失败' }}</strong>
                  <small>{{ previewError }}</small>
                  <button type="button" class="secondary-button" @click="loadControlledPreview">{{ locale === 'en-US' ? 'Generate again' : '重新生成' }}</button>
                </div>
                <object
                  v-else-if="previewUrl"
                  class="controlled-pdf-object"
                  data-controlled-pdf-preview
                  :data="previewUrl"
                  type="application/pdf"
                  :aria-label="`${selected.title} ${role === 'Manager' ? (locale === 'en-US' ? 'Preview without watermark' : '无水印预览') : (locale === 'en-US' ? 'Watermarked preview' : '水印预览')}`"
                >
                  <p>{{ locale === 'en-US' ? 'This browser cannot embed the PDF. Use the controlled download on the right.' : '当前浏览器无法内嵌 PDF，请使用右侧受控下载。' }}</p>
                </object>
              </section>

              <section
                v-else-if="selected.canDownload"
                class="document-preview original-only-preview"
                data-document-preview="original-only"
              >
                <FileText :size="38" />
                <h3>{{ locale === 'en-US' ? 'Original available' : '原件可用' }}</h3>
                <p>{{ locale === 'en-US' ? 'This document has no browser preview.' : '此文档没有浏览器预览版本' }}</p>
                <small>{{ role === 'Manager' ? (locale === 'en-US' ? 'Manager can download the integrity-checked original' : 'Manager 可直接下载经过完整性校验的原始文件') : (locale === 'en-US' ? 'Download the original using the approved authorization' : '可按已批准的授权方式下载原件') }}</small>
              </section>
              <section v-else class="document-preview locked-preview" data-document-preview="locked">
                <LockKeyhole :size="38" />
                <h3>{{ locale === 'en-US' ? 'Content restricted' : '内容受限' }}</h3>
                <p>{{ locale === 'en-US' ? 'Access permission required' : '需要访问权限' }}</p>
                <small>{{ locale === 'en-US' ? 'Preview and download are unavailable before approval' : '审批通过前不可预览或下载' }}</small>
              </section>

              <aside class="document-action-card">
                <template v-if="selected.canDownload">
                  <span class="workspace-badge positive"><ShieldCheck :size="13" />{{ locale === 'en-US' ? 'Approved access' : '已批准访问' }}</span>
                  <h3>{{ role === 'Manager' ? (locale === 'en-US' ? 'Download clean original' : '无水印原件下载') : selected.deliveryMode === 'Original' ? (locale === 'en-US' ? 'Download approved original' : '已批准原件下载') : (locale === 'en-US' ? 'Download approved watermarked PDF' : '已批准水印 PDF 下载') }}</h3>
                  <p>{{ role === 'Manager' ? (locale === 'en-US' ? 'Manager can view the clean preview and download the integrity-checked original.' : 'Manager 可直接查看无水印预览，并下载经过完整性校验的原始文件。') : (locale === 'en-US' ? 'Preview uses a personal watermarked PDF; the original is available only after explicit Manager approval.' : '预览使用当前账号的个人水印 PDF；原始文件仅在 Manager 明确批准后提供。') }}</p>
                  <dl class="document-facts">
                    <div><dt>{{ locale === 'en-US' ? 'Status' : '状态' }}</dt><dd>{{ documentLabel(selected.status) }}</dd></div>
                    <div><dt>{{ locale === 'en-US' ? 'Review date' : '复核日期' }}</dt><dd>{{ selected.reviewDate }}</dd></div>
                    <div><dt>{{ locale === 'en-US' ? 'Applicable product' : '适用产品' }}</dt><dd>{{ selected.product }}</dd></div>
                  </dl>
                  <a
                    v-if="usingMock && selected.fileUrl"
                    class="primary-button full-button"
                    data-controlled-download
                    :href="selected.fileUrl"
                    :download="selected.fileName"
                    @click="showControlledDownloadNotice"
                  >
                    <Download :size="15" />{{ role === 'Manager' ? (locale === 'en-US' ? 'Download clean original' : '下载无水印原件') : selected.deliveryMode === 'Original' ? (locale === 'en-US' ? 'Download original' : '下载原件') : (locale === 'en-US' ? 'Download watermarked PDF' : '下载水印 PDF') }}
                  </a>
                  <button
                    v-else
                    type="button"
                    class="primary-button full-button"
                    data-controlled-download
                    :disabled="downloading"
                    @click="usingMock ? showControlledDownloadNotice() : downloadControlledDocument()"
                  >
                    <Download :size="15" />{{ downloading ? (locale === 'en-US' ? 'Preparing controlled file…' : '正在准备受控文件…') : role === 'Manager' ? (locale === 'en-US' ? 'Download clean original' : '下载无水印原件') : selected.deliveryMode === 'Original' ? (locale === 'en-US' ? 'Download original' : '下载原件') : (locale === 'en-US' ? 'Download watermarked PDF' : '下载水印 PDF') }}
                  </button>
                  <small class="action-help">{{ usingMock ? (selected.fileUrl ? (locale === 'en-US' ? 'Download the current Demo file.' : '下载当前 Demo 文件。') : (locale === 'en-US' ? 'Demo records the action only; no official file is generated.' : 'Demo 仅记录动作，不生成正式文件。')) : role === 'Manager' ? (locale === 'en-US' ? 'The integrity-checked original is logged in the audit.' : '下载经过完整性校验的原始文件；行为会写入审计。') : selected.deliveryMode === 'Original' ? (locale === 'en-US' ? 'This authorized original is logged in the audit.' : '该授权下载经过完整性校验的原始文件；行为会写入审计。') : (locale === 'en-US' ? 'The server generates a watermarked PDF for the current account.' : '服务端将为当前账号逐页生成水印 PDF。') }}</small>
                </template>

                <template v-else-if="requestSubmitted">
                  <span class="workspace-badge warning" data-access-request-status>{{ requestStatusLabel('Manager Review') }}</span>
                  <h3>{{ locale === 'en-US' ? 'Access request submitted' : '访问申请已提交' }}</h3>
                  <ol class="stage-rail request-stage">
                    <li class="is-done"><i /><span>{{ locale === 'en-US' ? 'Submitted' : '已提交' }}</span></li>
                    <li class="is-current"><i /><span>{{ locale === 'en-US' ? 'Manager review' : '经理审核' }}</span></li>
                    <li><i /><span>{{ locale === 'en-US' ? 'Document admin' : '文档管理员' }}</span></li>
                  </ol>
                  <dl class="document-facts">
                    <div><dt>{{ locale === 'en-US' ? 'Requester' : '申请人' }}</dt><dd>{{ currentUserName }}</dd></div>
                    <div><dt>{{ locale === 'en-US' ? 'Reason' : '申请原因' }}</dt><dd>{{ requestReason }}</dd></div>
                  </dl>
                  <button type="button" class="secondary-button full-button" disabled>{{ locale === 'en-US' ? 'Waiting for approval' : '等待审批' }}</button>
                </template>

                <form v-else data-access-request-form @submit.prevent="submitAccessRequest">
                  <span class="workspace-badge warning"><FileLock2 :size="13" />{{ locale === 'en-US' ? 'Request required' : '需要申请' }}</span>
                  <h3>{{ locale === 'en-US' ? 'Request access to Restricted document' : '申请访问受限文档' }}</h3>
                  <p>{{ locale === 'en-US' ? 'Provide a specific business purpose. Content and download links remain hidden until approval.' : '填写具体业务用途。批准前不会显示正文或生成下载链接。' }}</p>
                  <label class="reason-field">
                    <span>{{ locale === 'en-US' ? 'Business purpose' : '访问用途' }}<RequiredMark /></span>
                    <textarea
                      v-model="requestReason"
                      data-access-reason
                      rows="5"
                      :placeholder="locale === 'en-US' ? 'e.g. Customer pricing review; verify the authorized version' : '例如：客户价格评审会议，需要核对授权版本'"
                      @input="requestError = ''"
                    />
                  </label>
                  <p v-if="requestError" class="inline-error">{{ requestError }}</p>
                  <button type="submit" class="primary-button full-button" :disabled="submitting">
                    <FileLock2 :size="15" />{{ submitting ? (locale === 'en-US' ? 'Submitting…' : '正在提交…') : (locale === 'en-US' ? 'Submit access request' : '提交访问申请') }}
                  </button>
                </form>
              </aside>
            </div>

            <div v-else-if="activeDetailTab === 'versions'" class="workspace-panel-body tab-evidence" data-version-history>
              <header><h3>{{ locale === 'en-US' ? 'Version history' : '版本历史' }}</h3><span>{{ selected.applicableTool }}</span></header>
              <div class="table-scroll">
                <table class="crm-table">
                  <thead><tr><th>{{ locale === 'en-US' ? 'Version' : '版本' }}</th><th>{{ locale === 'en-US' ? 'Status' : '状态' }}</th><th>{{ locale === 'en-US' ? 'Checksum' : '校验值' }}</th><th>{{ locale === 'en-US' ? 'Release date' : '发布日期' }}</th></tr></thead>
                  <tbody>
                    <tr v-for="version in selected.versions" :key="`${version.version}-${version.revision}`">
                      <td><strong>{{ version.version }} / {{ version.revision }}</strong></td>
                      <td><span class="workspace-badge" :class="version.status === 'Released' ? 'positive' : ''">{{ documentLabel(version.status) }}</span></td>
                      <td>{{ version.checksum }}</td>
                      <td>{{ formatDisplayDate(version.releasedAt) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div v-else class="workspace-panel-body tab-evidence" data-download-audit>
              <header><h3>{{ locale === 'en-US' ? 'Download audit' : '下载审计' }}</h3><span>{{ locale === 'en-US' ? 'Employee · time · purpose · version' : '员工 · 时间 · 用途 · 版本' }}</span></header>
              <div v-if="selected.audit.length" class="audit-list document-audit">
                <div v-for="entry in selected.audit" :key="entry.id">
                  <strong>{{ entry.employee }}</strong><span>{{ entry.reason }}</span><time>{{ formatDisplayDate(entry.at) }}</time><small>{{ entry.version }}</small>
                </div>
              </div>
              <p v-else class="workspace-empty-note">{{ locale === 'en-US' ? 'No download records for this version.' : '当前版本暂无下载记录。' }}</p>
            </div>
          </article>
        </section>
        <section v-else class="workspace-panel document-state" data-document-library-empty>
          <File :size="28" />
          <h2>{{ locale === 'en-US' ? 'No published documents' : '暂无已发布文档' }}</h2>
          <p>{{ locale === 'en-US' ? 'Upload the first document. A Manager can publish it directly or archive it after approval.' : '上传第一份文档后，Manager 可直接发布或在审批通过后归档到文档库。' }}</p>
        </section>
      </template>
    </template>

    <div v-if="uploadOpen" class="document-upload-backdrop" data-upload-modal @click.self="uploadOpen = false">
      <form class="workspace-panel document-upload-modal" @submit.prevent="submitDocumentUpload">
        <header><div><h2>{{ locale === 'en-US' ? 'Upload document' : '上传文档' }}</h2><p>{{ locale === 'en-US' ? 'Regular-user submissions require Manager review; Manager uploads are published directly.' : '普通用户提交后由 Manager 审核；Manager 上传将直接发布。' }}</p></div><button type="button" :aria-label="t('common.close')" @click="uploadOpen = false">×</button></header>
        <div class="upload-form-grid">
          <label class="wide">{{ locale === 'en-US' ? 'Title' : '标题' }}<input v-model="uploadForm.title" required></label>
          <label>{{ locale === 'en-US' ? 'Archive section' : '归档板块' }}<select v-model="uploadForm.category"><option value="Technical">{{ locale === 'en-US' ? 'Technical documents' : '技术文档' }}</option><option value="Commercial">{{ locale === 'en-US' ? 'Commercial documents' : '商务文档' }}</option></select></label>
          <label>{{ locale === 'en-US' ? 'Document type' : '文档类型' }}<input v-model="uploadForm.documentType" :placeholder="locale === 'en-US' ? 'Contract / equipment manual' : '合同 / 设备说明书'" required></label>
          <label>{{ locale === 'en-US' ? 'Access mode' : '访问方式' }}<select v-model="uploadForm.accessMode"><option value="Direct">{{ locale === 'en-US' ? 'Direct access' : '直接访问' }}</option><option value="Request">{{ locale === 'en-US' ? 'Request access' : '申请后访问' }}</option></select></label>
          <label>{{ locale === 'en-US' ? 'Confidentiality' : '密级' }}<select v-model="uploadForm.confidentiality"><option v-for="level in ['Internal', 'Confidential', 'Restricted']" :key="level" :value="level">{{ documentLabel(level) }}</option></select></label>
          <label>{{ locale === 'en-US' ? 'Product / equipment' : '产品 / 设备' }}<input v-model="uploadForm.product" :placeholder="locale === 'en-US' ? 'General' : '通用'"></label>
          <label>{{ locale === 'en-US' ? 'Applicable equipment' : '适用设备' }}<input v-model="uploadForm.applicableTool"></label>
          <label>{{ locale === 'en-US' ? 'Version' : '版本' }}<input v-model="uploadForm.version"></label><label>{{ locale === 'en-US' ? 'Revision' : '修订' }}<input v-model="uploadForm.revision"></label>
          <label>{{ locale === 'en-US' ? 'Review date' : '复审日期' }}<input v-model="uploadForm.reviewDate" type="date"></label>
          <label class="wide"><span>{{ locale === 'en-US' ? 'File' : '文件' }}<RequiredMark /></span><input type="file" accept=".pdf,.docx,.xlsx,.pptx" required @change="selectUploadFile"></label>
        </div>
        <p v-if="uploadError" class="upload-error">{{ uploadError }}</p>
        <footer><button type="button" class="secondary-button" @click="uploadOpen = false">{{ locale === 'en-US' ? 'Cancel' : '取消' }}</button><button type="submit" class="primary-button" :disabled="uploadSubmitting">{{ uploadSubmitting ? (locale === 'en-US' ? 'Uploading…' : '上传中…') : (locale === 'en-US' ? 'Submit upload' : '提交上传') }}</button></footer>
      </form>
    </div>
  </div>
</template>

<style scoped>
.document-workspace-tabs{margin-bottom:12px}.document-workspace-tabs b{display:inline-grid;min-width:20px;height:20px;place-items:center;margin-left:5px;border-radius:10px;background:#f28a24;color:#fff}.document-header-actions{display:flex;align-items:center;gap:10px}.upload-document-button{display:inline-flex;align-items:center;gap:7px;white-space:nowrap}.document-upload-backdrop{position:fixed;inset:0;z-index:80;display:grid;place-items:center;padding:24px;background:#08192eb8}.document-upload-modal{width:min(720px,100%);padding:0;background:#fff}.document-upload-modal>header{display:flex;justify-content:space-between;padding:20px;border-bottom:1px solid #ddd}.document-upload-modal h2,.document-upload-modal p{margin:0}.document-upload-modal p{margin-top:5px;color:#6f747a;font-size:12px}.document-upload-modal>header button{border:0;background:none;font-size:24px}.upload-form-grid,.upload-approval-fields{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding:20px}.upload-form-grid label,.upload-approval-fields label{display:grid;gap:6px;font-size:11px;font-weight:700}.upload-form-grid .wide,.upload-approval-fields .wide{grid-column:1/-1}.upload-form-grid input,.upload-form-grid select,.upload-approval-fields select,.upload-approval-fields textarea{min-height:38px;padding:8px;border:1px solid #d6d3ce;border-radius:5px;background:#fff}.document-upload-modal footer{display:flex;justify-content:flex-end;gap:10px;padding:16px 20px;border-top:1px solid #ddd}.upload-error{padding:0 20px;color:#a83232}@media(max-width:760px){.document-header-actions{width:100%;align-items:stretch;flex-direction:column}.upload-document-button{justify-content:center}.upload-form-grid,.upload-approval-fields{grid-template-columns:1fr}.upload-form-grid .wide,.upload-approval-fields .wide{grid-column:auto}}
.document-notice {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 11px 13px;
  color: var(--crm-positive-ink);
  background: #f1f8f4;
  border: 1px solid #cfe4d8;
  border-radius: 10px;
  font-size: 9px;
}

.document-state {
  display: grid;
  gap: 10px;
  min-height: 180px;
  align-content: center;
  padding: 24px;
  color: var(--crm-text-muted);
  text-align: center;
}

.document-state > span {
  width: min(100%, 620px);
  height: 12px;
  margin: 0 auto;
  background: var(--crm-surface-muted);
  border-radius: 6px;
}

.document-state > span:nth-child(2) { width: min(82%, 510px); }
.document-state > span:nth-child(3) { width: min(66%, 410px); }
.document-state.is-error { color: var(--crm-danger); }
.approval-empty { justify-items: center; }
.approval-empty h2 { margin: 0; color: var(--crm-navy); font-size: 14px; }
.approval-empty p { max-width: 520px; margin: 0; font-size: 9px; line-height: 1.6; }

.document-filters {
  padding: 4px;
  background: var(--crm-surface-muted);
  border-radius: 10px;
}

.document-filters button {
  gap: 7px;
  background: transparent;
  border-color: transparent;
}

.document-filters button b {
  min-width: 19px;
  padding: 2px 5px;
  color: inherit;
  background: rgba(255, 255, 255, .7);
  border-radius: 5px;
  font-size: 7px;
}

.document-grid {
  display: grid;
  grid-template-columns: minmax(320px, .82fr) minmax(0, 1.55fr);
  gap: 14px;
  align-items: start;
}

.approval-grid {
  display: grid;
  grid-template-columns: minmax(350px, .88fr) minmax(0, 1.62fr);
  gap: 14px;
  align-items: start;
}

.document-list-panel,
.approval-queue {
  position: sticky;
  top: 18px;
}

.approval-queue {
  border-color: var(--crm-line-strong);
  box-shadow: 0 12px 32px rgba(31, 35, 41, .07);
}

.approval-queue .queue-header {
  min-height: 68px;
  padding: 0 15px;
}

.queue-header > div {
  display: flex;
  align-items: center;
  gap: 10px;
}

.queue-heading-icon {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  color: var(--crm-brand-ink);
  background: var(--crm-brand-soft);
  border-radius: 9px;
}

.queue-heading-copy {
  display: grid;
  gap: 3px;
}

.queue-heading-copy h2 { font-size: 13px !important; }

.queue-heading-copy small {
  color: var(--crm-text-muted);
  font-size: 6px;
  font-weight: 800;
  letter-spacing: .14em;
}

.queue-count {
  display: inline-flex;
  min-height: 27px;
  align-items: center;
  gap: 5px;
  padding: 0 8px;
  color: var(--crm-text-muted) !important;
  background: var(--crm-surface);
  border: 1px solid var(--crm-line);
  border-radius: 8px;
  font-size: 7px !important;
}

.queue-count b {
  color: var(--crm-navy);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.document-list-body,
.approval-queue .workspace-panel-body {
  display: grid;
  gap: 13px;
}

.approval-queue .workspace-panel-body {
  padding: 14px;
  background: #faf9f7;
}

.document-list-body .crm-search-control,
.queue-search {
  width: 100%;
  min-width: 0;
}

.queue-context {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 2px;
}

.queue-context span {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--crm-navy);
  font-size: 8px;
  font-weight: 700;
}

.queue-context i {
  width: 6px;
  height: 6px;
  background: var(--crm-teal);
  border-radius: 50%;
  box-shadow: 0 0 0 3px var(--crm-teal-soft);
}

.queue-context small {
  color: var(--crm-text-muted);
  font-size: 7px;
}

.document-list,
.request-list {
  max-height: 690px;
  overflow: auto;
  padding-right: 3px;
}

.request-list { gap: 10px; }

.document-row {
  grid-template-columns: 34px minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px 10px;
}

.document-type-icon {
  position: relative;
  display: grid;
  width: 34px;
  height: 38px;
  grid-row: 1 / 3;
  place-items: center;
  color: var(--crm-teal);
  background: var(--crm-teal-soft);
  border-radius: 8px;
}

.row-lock {
  position: absolute;
  right: -2px;
  bottom: -2px;
  padding: 2px;
  color: #fff;
  background: var(--crm-warning);
  border-radius: 50%;
}

.document-row-copy {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.document-row-copy strong,
.request-document b {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.document-row-meta {
  display: flex;
  grid-column: 2 / 4;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--crm-text-muted);
  font-size: 8px;
}

.document-row-meta b { color: var(--crm-text); font-weight: 600; }

.document-detail-panel > header,
.approval-detail > header {
  min-height: 64px;
}

.document-detail-panel > header > div,
.approval-detail > header > div {
  display: grid;
  gap: 4px;
}

.document-detail-panel > header h2,
.approval-detail > header h2 {
  font-size: 13px;
}

.document-tabs {
  display: flex;
  gap: 4px;
  padding: 9px 16px 0;
  border-bottom: 1px solid var(--crm-line);
}

.document-tabs button {
  min-height: 36px;
  padding: 0 12px;
  color: var(--crm-text-muted);
  background: transparent;
  border: 0;
  border-bottom: 2px solid transparent;
  font-size: 9px;
  font-weight: 700;
  cursor: pointer;
}

.document-tabs button.active {
  color: var(--crm-teal);
  border-bottom-color: var(--crm-teal);
}

.preview-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(240px, .65fr);
  gap: 14px;
}

.document-preview,
.document-action-card {
  overflow: hidden;
  background: var(--crm-surface);
  border: 1px solid var(--crm-line);
  border-radius: 11px;
}

.preview-toolbar {
  display: flex;
  height: 38px;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  color: var(--crm-text-muted);
  background: #fff;
  border-bottom: 1px solid var(--crm-line);
  font-size: 8px;
}

.pdf-stage {
  display: grid;
  min-height: 480px;
  padding: 26px;
  place-items: center;
}

.pdf-sheet {
  position: relative;
  display: grid;
  width: min(100%, 360px);
  min-height: 430px;
  align-content: start;
  gap: 13px;
  padding: 28px;
  overflow: hidden;
  background: #fff;
  border: 1px solid var(--crm-line);
  box-shadow: 0 10px 28px rgba(31, 35, 41, .09);
}

.pdf-brand {
  color: var(--crm-navy);
  font-size: 12px;
  font-weight: 900;
  letter-spacing: .08em;
}

.pdf-brand small {
  color: var(--crm-teal);
  font-size: 6px;
}

.pdf-sheet > span {
  margin-top: 18px;
  color: var(--crm-teal);
  font-size: 7px;
  font-weight: 800;
  letter-spacing: .16em;
}

.pdf-sheet h3 {
  margin: 0;
  color: var(--crm-navy);
  font-size: 25px;
  line-height: 1.05;
  letter-spacing: -.04em;
}

.pdf-sheet p {
  margin: 0;
  color: var(--crm-text-muted);
  font-size: 8px;
}

.pdf-figure {
  display: grid;
  height: 120px;
  grid-template-columns: 1.4fr .8fr .55fr;
  align-items: end;
  gap: 9px;
  padding: 16px;
  background: #f5f3ef;
  border-radius: 8px;
}

.pdf-figure i {
  display: block;
  height: 84%;
  background: var(--crm-navy);
  border-radius: 4px 4px 0 0;
}

.pdf-figure i:nth-child(2) { height: 56%; background: var(--crm-teal); }
.pdf-figure i:nth-child(3) { height: 35%; background: var(--crm-line-strong); }

.pdf-sheet dl {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1px;
  margin: 0;
  background: var(--crm-line);
}

.pdf-sheet dl div { padding: 9px; background: #fff; }
.pdf-sheet dt { color: var(--crm-text-muted); font-size: 6px; }
.pdf-sheet dd { margin: 4px 0 0; color: var(--crm-navy); font-size: 7px; font-weight: 700; }

.pdf-watermark {
  position: absolute;
  right: -55px;
  bottom: 44px;
  color: rgba(200, 78, 78, .18);
  font-size: 8px;
  font-weight: 800;
  letter-spacing: .08em;
  transform: rotate(-24deg);
}

.controlled-pdf-object {
  display: block;
  width: 100%;
  min-height: 680px;
  background: #edf2f1;
  border: 0;
}

.real-preview-state {
  display: grid;
  min-height: 560px;
  padding: 32px;
  place-content: center;
  justify-items: center;
  gap: 10px;
  color: var(--crm-text-muted);
  text-align: center;
}

.real-preview-state strong { color: var(--crm-navy); font-size: 13px; }
.real-preview-state small { max-width: 360px; font-size: 9px; line-height: 1.6; }
.real-preview-state.is-error strong { color: var(--crm-danger); }
.preview-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid var(--crm-line);
  border-top-color: var(--crm-teal);
  border-radius: 999px;
  animation: document-preview-spin .8s linear infinite;
}
@keyframes document-preview-spin { to { transform: rotate(360deg); } }

.locked-preview,
.original-only-preview {
  display: grid;
  min-height: 520px;
  place-content: center;
  justify-items: center;
  padding: 28px;
  color: var(--crm-text-muted);
  text-align: center;
}

.locked-preview svg { color: var(--crm-warning); }
.original-only-preview svg { color: var(--crm-teal); }
.locked-preview h3,
.original-only-preview h3 { margin: 12px 0 2px; color: var(--crm-navy); font-size: 15px; }
.locked-preview p,
.original-only-preview p { margin: 0 0 6px; font-size: 10px; }
.locked-preview small,
.original-only-preview small { font-size: 8px; }

.document-action-card {
  display: grid;
  align-content: start;
  gap: 12px;
  padding: 18px;
  background: #fff;
}

.document-action-card form {
  display: grid;
  gap: 12px;
}

.document-action-card h3 {
  margin: 2px 0 0;
  color: var(--crm-navy);
  font-size: 13px;
}

.document-action-card p {
  margin: 0;
  color: var(--crm-text-muted);
  font-size: 9px;
  line-height: 1.65;
}

.document-facts {
  display: grid;
  margin: 0;
  border-top: 1px solid var(--crm-line);
}

.document-facts div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 0;
  border-bottom: 1px solid var(--crm-line);
}

.document-facts dt { color: var(--crm-text-muted); font-size: 8px; }
.document-facts dd { margin: 0; color: var(--crm-navy); font-size: 8px; font-weight: 700; text-align: right; }
.full-button { width: 100%; }
.action-help { color: var(--crm-text-muted); font-size: 7px; text-align: center; }

.reason-field {
  display: grid;
  gap: 7px;
  color: var(--crm-text);
  font-size: 8px;
  font-weight: 700;
}

.reason-field textarea {
  width: 100%;
  resize: vertical;
  padding: 10px;
  color: var(--crm-text);
  background: var(--crm-surface);
  border: 1px solid var(--crm-line);
  border-radius: 8px;
  outline: 0;
  font-size: 9px;
  line-height: 1.55;
}

.reason-field textarea:focus {
  border-color: var(--crm-teal);
  box-shadow: 0 0 0 3px rgba(254, 153, 0, .12);
}

.inline-error { color: var(--crm-danger) !important; }

.tab-evidence {
  display: grid;
  gap: 12px;
}

.tab-evidence > header,
.evidence-card > header,
.approval-flow > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.tab-evidence h3,
.evidence-card h3,
.approval-flow h3 {
  margin: 0;
  color: var(--crm-navy);
  font-size: 11px;
}

.table-scroll { overflow: auto; }
.tab-evidence .crm-table { min-width: 620px; }

.request-card {
  position: relative;
  grid-template-columns: 40px minmax(0, 1fr) auto;
  align-items: start;
  gap: 8px 10px;
  padding: 13px;
  overflow: hidden;
  background: #fff;
  border-color: var(--crm-line);
  box-shadow: 0 4px 14px rgba(31, 35, 41, .03);
  transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease, background-color .18s ease;
}

.request-card:hover {
  border-color: #e9b760;
  box-shadow: 0 8px 20px rgba(31, 35, 41, .07);
  transform: translateY(-1px);
}

.request-card.active {
  background: #fffaf2;
  border-color: var(--crm-teal);
  box-shadow: inset 3px 0 0 var(--crm-teal), 0 8px 20px rgba(217, 119, 6, .08);
}

.request-avatar {
  display: grid;
  width: 40px;
  height: 40px;
  grid-row: 1;
  place-items: center;
  color: var(--crm-brand-ink);
  background: var(--crm-brand-soft);
  border: 1px solid #f3d49f;
  border-radius: 10px;
  font-size: 9px;
  font-weight: 800;
}

.request-copy,
.request-document > span {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.request-copy { align-self: center; }
.request-copy strong { color: var(--crm-navy); font-size: 10px; }
.request-copy small { color: var(--crm-text-muted); font-size: 7px; }
.request-card > .workspace-badge { align-self: center; }

.request-document {
  display: grid;
  min-width: 0;
  grid-column: 1 / 4;
  grid-template-columns: 16px 1fr;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  color: var(--crm-teal);
  background: var(--crm-surface);
  border: 1px solid var(--crm-line);
  border-radius: 8px;
}

.request-document b { color: var(--crm-navy); font-size: 8px; }
.request-document small { color: var(--crm-text-muted); font-size: 7px; }

.request-card-footer {
  display: flex;
  grid-column: 1 / 4;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 2px;
}

.request-card-footer time,
.request-card-footer small {
  color: var(--crm-text-muted);
  font-size: 7px;
  font-variant-numeric: tabular-nums;
}

.request-card-footer small {
  color: #8a651d;
  font-weight: 700;
}

.approval-body {
  display: grid;
  gap: 16px;
}

.readonly-notice {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  padding: 11px 12px;
  color: var(--crm-text-muted);
  background: var(--crm-surface);
  border: 1px solid var(--crm-line);
  border-radius: 9px;
  font-size: 8px;
  line-height: 1.5;
}

.readonly-notice svg { color: var(--crm-teal); }
.readonly-notice span { display: grid; gap: 2px; }
.readonly-notice strong { color: var(--crm-navy); }

.request-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  overflow: hidden;
  background: var(--crm-line);
  border: 1px solid var(--crm-line);
  border-radius: 10px;
}

.request-summary > div {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 12px;
  color: var(--crm-teal);
  background: #fff;
}

.request-summary span { display: grid; gap: 4px; }
.request-summary small { color: var(--crm-text-muted); font-size: 7px; }
.request-summary strong { color: var(--crm-navy); font-size: 8px; line-height: 1.5; }
.request-summary .request-reason { grid-column: 1 / -1; }

.approval-flow,
.decision-bar,
.evidence-card {
  display: grid;
  gap: 14px;
  padding: 14px;
  background: var(--crm-surface);
  border: 1px solid var(--crm-line);
  border-radius: 10px;
}

.approval-flow .stage-rail { padding: 8px 0 2px; }

.decision-bar {
  grid-template-columns: minmax(150px, 1fr) auto;
  align-items: center;
  background: #fff;
}

.decision-bar > div:first-child { display: grid; gap: 4px; }
.decision-bar small { color: var(--crm-text-muted); font-size: 7px; }
.decision-bar strong { color: var(--crm-navy); font-size: 9px; }

.approval-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 7px;
}

.danger-action:not(:disabled) { color: var(--crm-danger); }

.approval-status {
  grid-column: 1 / -1;
  margin: 0;
  color: var(--crm-text-muted);
  font-size: 8px;
}

.evidence-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.evidence-card {
  min-width: 0;
  align-content: start;
  background: #fff;
}

.evidence-table { min-width: 440px; }
.audit-note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  padding: 9px;
  color: var(--crm-text-muted);
  background: var(--crm-surface);
  border-radius: 8px;
  font-size: 8px;
}

.audit-list {
  display: grid;
  border-top: 1px solid var(--crm-line);
}

.audit-list > div {
  display: grid;
  grid-template-columns: minmax(90px, 1fr) minmax(100px, 1.2fr) auto;
  align-items: center;
  gap: 5px 9px;
  padding: 10px 0;
  border-bottom: 1px solid var(--crm-line);
  font-size: 8px;
}

.audit-list strong { color: var(--crm-navy); }
.audit-list span,
.audit-list time,
.audit-list small { color: var(--crm-text-muted); }
.audit-list small { grid-column: 1 / -1; }

.document-audit > div {
  grid-template-columns: minmax(100px, .7fr) minmax(180px, 1.3fr) auto;
}

.request-stage { margin: 12px 0 4px; padding: 0; }

@media (max-width: 1199px) {
  .document-grid,
  .approval-grid { grid-template-columns: 1fr; }
  .document-list-panel,
  .approval-queue { position: static; }
  .document-list,
  .request-list { max-height: none; }
  .preview-layout { grid-template-columns: minmax(0, 1.25fr) minmax(250px, .75fr); }
}

@media (max-width: 820px) {
  .preview-layout,
  .evidence-grid { grid-template-columns: 1fr; }
  .request-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .decision-bar { grid-template-columns: 1fr; }
  .approval-actions { justify-content: flex-start; }
  .pdf-stage { min-height: 420px; padding: 18px; }
}

@media (max-width: 540px) {
  .document-filters { overflow: auto; flex-wrap: nowrap; }
  .document-filters button { flex: 0 0 auto; }
  .document-row { grid-template-columns: 34px minmax(0, 1fr); }
  .document-row > .workspace-badge { grid-column: 2; }
  .document-row-meta { grid-column: 2; align-items: flex-start; flex-direction: column; }
  .request-summary { grid-template-columns: 1fr; }
  .request-summary .request-reason { grid-column: auto; }
  .approval-actions { display: grid; }
  .approval-actions button { width: 100%; }
  .pdf-sheet { min-height: 390px; padding: 22px; }
  .audit-list > div,
  .document-audit > div { grid-template-columns: 1fr; }
  .audit-list small { grid-column: auto; }
}
</style>
