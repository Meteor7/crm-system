<script setup lang="ts">
import { systemValueLabel } from '@/features/shared/system-labels'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowLeft, Check, Download, FileText, MessageSquareText, RotateCcw, ShieldCheck, Upload } from '@lucide/vue'
import { useRoute } from 'vue-router'
import { api as defaultApi, type CrmApi } from '@/api'
import type { MultipartFilePart } from '@/api/binary-transport'
import { mapRequestError } from '@/api/request-state'
import DataState from '@/design-system/DataState.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import { downloadBlob } from '@/features/shared/download-blob'
import { formatDisplayDate } from '@/domain/time'
import { useAppStore } from '@/stores/app'
import type { Tone } from '@/types/crm'
import type { RfqDetailDto, RfqStatus, RfqVersionDto } from '@/features/rfqs/types'
import { useI18n, useLocaleMessage, localeMessage } from '@/i18n'
import { opportunityStageLabel as stageLabel } from '@/domain/opportunity-stages'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const route = useRoute()
const app = useAppStore()
const { locale, t } = useI18n()
const ui = (english: string, chinese: string) => localeMessage(english, chinese)[locale.value]
const detail = ref<RfqDetailDto | null>(null)
const loading = ref(true)
const error = useLocaleMessage()
const denied = ref(false)
const requestId = ref('')
const busy = ref(false)
const actionError = useLocaleMessage()
const notice = useLocaleMessage()
const engineerComment = ref('')
const managerComment = ref('')
const revisionFile = ref<File | null>(null)
const selectedVersionId = ref('')
const previewUrl = ref('')
const previewMime = ref('')
const previewLoading = ref(false)
const previewError = useLocaleMessage()
let previewSequence = 0
const TIPRAY_HEADER = new TextEncoder().encode('%TSD-Header-###%')

const role = computed(() => app.bootstrap?.user.role)
const selectedVersion = computed(() => detail.value?.versions.find((item) => item.id === selectedVersionId.value) ?? detail.value?.currentVersion)
const canDownload = computed(() => role.value === 'Sales' || role.value === 'Manager')
const steps = computed(() => {
  const status = detail.value?.status
  return [
    { label: ui('Sales upload', '销售上传'), done: Boolean(detail.value), active: false },
    { label: ui('Engineer comment', '工程师意见'), done: ['Manager Approval', 'Approved'].includes(status ?? ''), active: status === 'Engineer Review' },
    { label: ui('Manager approval', '经理审批'), done: status === 'Approved', active: status === 'Manager Approval' },
  ]
})

function statusLabel(value: RfqStatus | RfqVersionDto['status']) {
  return ({
    'Engineer Review': ui('Engineer review', '工程师评审'), 'Manager Approval': ui('Manager approval', '经理审批'),
    'Sales Revision': ui('Sales revision', '销售修订'), Returned: ui('Returned', '已退回'), Approved: ui('Approved', '已批准'),
  } satisfies Record<RfqStatus | RfqVersionDto['status'], string>)[value]
}
function decisionLabel(value: 'Approved' | 'Returned') {
  return value === 'Approved' ? ui('Approved', '已批准') : ui('Returned', '已退回')
}
function opportunityStageLabel(value: string) {
  return stageLabel(value, locale.value)
}

function statusTone(value: RfqStatus): Tone {
  if (value === 'Approved') return 'positive'
  if (value === 'Sales Revision') return 'danger'
  if (value === 'Manager Approval') return 'warning'
  return 'info'
}

function releasePreview() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
}

async function loadPreview() {
  const current = ++previewSequence
  releasePreview()
  previewError.value = ''
  if (!detail.value || !selectedVersionId.value) return
  previewLoading.value = true
  try {
    const file = await props.apiClient.previewRfqFile(detail.value.id, selectedVersionId.value)
    if (current !== previewSequence) return
    previewMime.value = file.mimeType
    previewUrl.value = URL.createObjectURL(file.blob)
  } catch (cause) {
    if (current === previewSequence) {
      const mapped = mapRequestError(cause)
      previewError.value = mapped.localizedMessage ?? mapped.message
    }
  } finally {
    if (current === previewSequence) previewLoading.value = false
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const result = await props.apiClient.getRfq(String(route.params.rfqId))
    detail.value = result.data
    selectedVersionId.value = result.data.currentVersionId
  } catch (cause) {
    const mapped = mapRequestError(cause)
    error.value = mapped.localizedMessage ?? mapped.message
    denied.value = mapped.denied
    requestId.value = mapped.requestId
  } finally {
    loading.value = false
  }
}

function applyResult(result: RfqDetailDto) {
  detail.value = result
  selectedVersionId.value = result.currentVersionId
  engineerComment.value = ''
  managerComment.value = ''
  revisionFile.value = null
}

async function submitEngineerComment() {
  if (!detail.value || !engineerComment.value.trim()) {
    actionError.value = localeMessage('Engineer Comment is required.', 'Engineer Comment 不能为空。')
    return
  }
  busy.value = true
  actionError.value = ''
  try {
    const result = await props.apiClient.submitRfqEngineerComment(detail.value.id, engineerComment.value, detail.value.modified)
    applyResult(result.data)
    notice.value = localeMessage('Engineer Comment submitted. Waiting for Manager approval.', 'Engineer Comment 已提交，等待 Manager Approve。')
  } catch (cause) {
    const mapped = mapRequestError(cause)
    actionError.value = mapped.localizedMessage ?? mapped.message
  } finally {
    busy.value = false
  }
}

async function review(decision: 'Approved' | 'Returned') {
  if (!detail.value) return
  if (decision === 'Returned' && !managerComment.value.trim()) {
    actionError.value = localeMessage('A reason is required when returning.', '退回时必须填写原因。')
    return
  }
  busy.value = true
  actionError.value = ''
  try {
    const result = await props.apiClient.reviewRfq(detail.value.id, { decision, comment: managerComment.value }, detail.value.modified)
    applyResult(result.data)
    notice.value = decision === 'Approved' ? (localeMessage('RFQ approved.', 'RFQ 已批准。')) : (localeMessage('RFQ returned to Sales for revision.', 'RFQ 已退回 Sales 修改。'))
  } catch (cause) {
    const mapped = mapRequestError(cause)
    actionError.value = mapped.localizedMessage ?? mapped.message
  } finally {
    busy.value = false
  }
}

function selectRevision(event: Event) {
  revisionFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

async function isTipRayProtected(selected: File) {
  const header = new Uint8Array(await selected.slice(0, TIPRAY_HEADER.length).arrayBuffer())
  return header.length === TIPRAY_HEADER.length && header.every((value, index) => value === TIPRAY_HEADER[index])
}

async function revise() {
  if (!detail.value || !revisionFile.value) {
    actionError.value = localeMessage('Select a new RFQ file.', '请选择新的 RFQ 文件。')
    return
  }
  busy.value = true
  actionError.value = ''
  try {
    const file = revisionFile.value
    if (await isTipRayProtected(file) && !window.confirm(t('rfqs.tipRayConfirm'))) return
    const part: MultipartFilePart = { blob: file, fileName: file.name, mimeType: file.type, size: file.size }
    const result = await props.apiClient.reviseRfq(detail.value.id, part, detail.value.modified)
    applyResult(result.data)
    notice.value = localeMessage('New version uploaded. Waiting for Engineer Comment again.', '新版本已上传，重新等待 Engineer Comment。')
  } catch (cause) {
    const mapped = mapRequestError(cause)
    actionError.value = mapped.localizedMessage ?? mapped.message
  } finally {
    busy.value = false
  }
}

async function downloadOriginal() {
  if (!detail.value || !selectedVersion.value) return
  try {
    const file = await props.apiClient.downloadRfqFile(detail.value.id, selectedVersion.value.id)
    downloadBlob(file.blob, file.fileName)
  } catch (cause) {
    const mapped = mapRequestError(cause)
    actionError.value = mapped.localizedMessage ?? mapped.message
  }
}

watch(selectedVersionId, () => { void loadPreview() })
onMounted(async () => {
  await app.loadBootstrap(props.apiClient)
  await load()
})
onBeforeUnmount(() => {
  previewSequence += 1
  releasePreview()
})
</script>

<template>
  <div class="rfq-detail-page">
    <RouterLink class="back-link" :to="{ name: 'rfqs' }"><ArrowLeft :size="14" />{{ (locale === 'en-US' ? 'Back to RFQ Center' : '返回 RFQ Center') }}</RouterLink>
    <DataState v-if="loading" type="loading" />
    <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
    <DataState v-else-if="error || !detail" type="error" :message="error || (locale === 'en-US' ? 'RFQ not found' : 'RFQ 不存在')" :request-id="requestId" @retry="load" />
    <template v-else>
      <header class="detail-header">
        <div><span>{{ ui('REQUEST FOR QUOTATION', '报价请求') }}</span><h1>{{ detail.id }}</h1><p>{{ detail.opportunity.title }} · {{ detail.opportunity.id }}</p></div>
        <StatusBadge :label="statusLabel(detail.status)" :tone="statusTone(detail.status)" />
      </header>

      <div class="detail-layout">
        <aside class="project-sidebar">
          <section>
            <span class="eyebrow">{{ ui('OPPORTUNITY', '商机') }}</span>
            <RouterLink v-if="role !== 'Engineer'" class="record-link" :to="{ name: 'opportunity-detail', params: { opportunityId: detail.opportunity.id } }"><strong>{{ detail.opportunity.title }}</strong></RouterLink>
            <strong v-else>{{ detail.opportunity.title }}</strong>
            <dl>
              <div><dt>{{ ui('Account', '客户') }}</dt><dd>{{ detail.opportunity.account }}</dd></div>
              <div><dt>{{ ui('Site', '厂区') }}</dt><dd>{{ detail.opportunity.site }}</dd></div>
              <div><dt>{{ ui('Stage', '阶段') }}</dt><dd>{{ opportunityStageLabel(detail.opportunity.stage) }}</dd></div>
              <div><dt>{{ ui('Tool Type', '设备类型') }}</dt><dd>{{ systemValueLabel(detail.opportunity.toolType, locale) }}</dd></div>
              <div><dt>{{ ui('Sales', '销售') }}</dt><dd>{{ detail.salesOwnerName }}</dd></div>
              <div><dt>{{ ui('Engineer', '工程师') }}</dt><dd>{{ detail.engineerOwnerName }}</dd></div>
            </dl>
          </section>
          <section>
            <span class="eyebrow">{{ ui('WORKFLOW', '工作流') }}</span>
            <ol class="workflow-steps">
              <li v-for="step in steps" :key="step.label" :class="{ done: step.done, active: step.active }">
                <span><Check v-if="step.done" :size="13" /><i v-else /></span><div><strong>{{ step.label }}</strong><small>{{ step.done ? ui('Completed', '已完成') : step.active ? ui('Current', '当前') : ui('Waiting', '等待中') }}</small></div>
              </li>
            </ol>
          </section>
          <section v-if="detail.note"><span class="eyebrow">{{ ui('NOTE', '备注') }}</span><p>{{ detail.note }}</p></section>
        </aside>

        <main class="preview-workspace">
          <header><div><span class="eyebrow">{{ ui('FILE PREVIEW', '文件预览') }}</span><h2>{{ selectedVersion?.fileName }}</h2></div><button v-if="canDownload" class="secondary-button" type="button" @click="downloadOriginal"><Download :size="14" />{{ (locale === 'en-US' ? 'Download original' : '下载原件') }}</button></header>
          <div class="preview-surface">
            <DataState v-if="previewLoading" type="loading" />
            <DataState v-else-if="previewError" type="error" :message="previewError" @retry="loadPreview" />
            <iframe v-else-if="previewUrl && previewMime === 'application/pdf'" :src="previewUrl" :title="(locale === 'en-US' ? 'RFQ PDF preview' : 'RFQ PDF 预览')" />
            <img v-else-if="previewUrl && previewMime.startsWith('image/')" :src="previewUrl" :alt="(locale === 'en-US' ? 'RFQ file preview' : 'RFQ 文件预览')" />
            <DataState v-else type="empty" :title="(locale === 'en-US' ? 'No preview' : '暂无预览')" :message="(locale === 'en-US' ? 'No preview is available for this version.' : '当前版本没有可用预览。')" />
          </div>
        </main>

        <aside class="action-sidebar">
          <section v-if="role === 'Engineer' && detail.status === 'Engineer Review'" class="action-panel">
            <MessageSquareText :size="18" /><h2>{{ ui('Engineer comment', '工程师意见') }}</h2><textarea v-model="engineerComment" rows="7" :placeholder="(locale === 'en-US' ? 'Enter specifications and technical comments' : '填写规格与技术意见')" /><button class="primary-button" type="button" :disabled="busy" @click="submitEngineerComment">{{ ui('Submit comment', '提交意见') }}</button>
          </section>
          <section v-else-if="role === 'Manager' && detail.status === 'Manager Approval'" class="action-panel">
            <ShieldCheck :size="18" /><h2>{{ ui('Manager approval', '经理审批') }}</h2><textarea v-model="managerComment" rows="6" :placeholder="(locale === 'en-US' ? 'Approval note optional; return reason required' : '批准意见可选；退回原因必填')" /><div class="decision-buttons"><button class="secondary-button danger" type="button" :disabled="busy" @click="review('Returned')"><RotateCcw :size="13" />{{ (locale === 'en-US' ? 'Return' : '退回') }}</button><button class="primary-button" type="button" :disabled="busy" @click="review('Approved')"><Check :size="13" />{{ (locale === 'en-US' ? 'Approve' : '批准') }}</button></div>
          </section>
          <section v-else-if="(role === 'Sales' || role === 'Manager') && detail.status === 'Sales Revision'" class="action-panel">
            <Upload :size="18" /><h2>{{ ui('Sales revision', '销售修订') }}</h2><p>{{ ui('This RFQ needs revision. Replacing the file will return it to Engineer review.', '当前 RFQ 需要修订。替换文件后将重新进入工程师评审。') }}</p><input type="file" :aria-label="ui('New RFQ file', '新的 RFQ 文件')" accept=".pdf,.png,.jpg,.jpeg,.docx,.xlsx,.pptx" @change="selectRevision" /><button class="primary-button" type="button" :disabled="busy" @click="revise">{{ (locale === 'en-US' ? 'Upload new version' : '上传新版本') }}</button>
          </section>
           <section v-else class="action-panel readonly"><FileText :size="18" /><h2>{{ ui('Current status', '当前状态') }}</h2><StatusBadge :label="statusLabel(detail.status)" :tone="statusTone(detail.status)" /><p v-if="detail.status === 'Approved'">{{ (locale === 'en-US' ? 'This RFQ is locked and satisfies the Opportunity quotation gate.' : '当前 RFQ 已锁定并满足 Opportunity 报价阶段门禁。') }}</p><p v-else>{{ (locale === 'en-US' ? 'Waiting for the current owner to complete the next step.' : '等待当前责任人完成下一步。') }}</p></section>
          <p v-if="actionError" class="action-error">{{ actionError }}</p><p v-if="notice" class="action-notice">{{ notice }}</p>

          <section class="history-panel">
             <header><span class="eyebrow">{{ ui('VERSION HISTORY', '版本历史') }}</span><strong>{{ detail.versions.length }}</strong></header>
            <button v-for="version in detail.versions" :key="version.id" type="button" :class="{ selected: selectedVersionId === version.id }" @click="selectedVersionId = version.id">
               <span>V{{ version.version }}</span><div><strong>{{ version.fileName }}</strong><small>{{ statusLabel(version.status) }} · {{ formatDisplayDate(version.uploadedAt) }}</small></div>
            </button>
             <article v-if="selectedVersion?.engineerComment"><strong>{{ ui('Engineer comment', '工程师意见') }}</strong><p>{{ selectedVersion.engineerComment }}</p><small>{{ selectedVersion.engineerCommentedByName }} · {{ formatDisplayDate(selectedVersion.engineerCommentedAt) }}</small></article>
             <article v-if="selectedVersion?.managerDecision"><strong>{{ ui('Manager', '经理') }} {{ decisionLabel(selectedVersion.managerDecision) }}</strong><p>{{ selectedVersion.managerComment || ui('No comment', '无意见') }}</p><small>{{ selectedVersion.managerDecidedByName }} · {{ formatDisplayDate(selectedVersion.managerDecidedAt) }}</small></article>
          </section>
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
.rfq-detail-page{display:grid;gap:12px}.back-link{display:flex;width:max-content;align-items:center;gap:5px;color:var(--crm-teal);font-size:9px;font-weight:800}.detail-header{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:16px 18px;background:#fff;border:1px solid var(--crm-line);border-radius:10px}.detail-header span,.eyebrow{color:var(--crm-text-muted);font-size:8px;font-weight:800;letter-spacing:.1em}.detail-header h1{margin:4px 0;color:var(--crm-navy);font-size:23px}.detail-header p{margin:0;color:var(--crm-text-muted);font-size:10px}.detail-layout{display:grid;grid-template-columns:230px minmax(430px,1fr) 290px;min-height:650px;border:1px solid var(--crm-line);background:#fff}.project-sidebar,.action-sidebar{display:grid;align-content:start;gap:0;background:#f8faf9}.project-sidebar{border-right:1px solid var(--crm-line)}.action-sidebar{border-left:1px solid var(--crm-line)}.project-sidebar section,.action-sidebar>section{padding:16px;border-bottom:1px solid var(--crm-line)}.project-sidebar section>a,.project-sidebar section>strong{display:block;margin-top:8px;color:var(--crm-navy);font-size:12px;line-height:1.45}.project-sidebar dl{display:grid;gap:10px;margin:16px 0 0}.project-sidebar dl div{display:grid;gap:3px}.project-sidebar dt{color:var(--crm-text-muted);font-size:8px}.project-sidebar dd{margin:0;color:var(--crm-text);font-size:9px;font-weight:700}.project-sidebar p{color:var(--crm-text-muted);font-size:9px;line-height:1.6}.workflow-steps{display:grid;gap:0;margin:12px 0 0;padding:0;list-style:none}.workflow-steps li{display:grid;grid-template-columns:24px 1fr;gap:8px;min-height:50px}.workflow-steps li>span{position:relative;z-index:1;display:grid;width:22px;height:22px;place-items:center;color:var(--crm-text-muted);background:#fff;border:1px solid var(--crm-line);border-radius:50%}.workflow-steps li:not(:last-child)>span:after{position:absolute;top:21px;left:10px;width:1px;height:29px;background:var(--crm-line);content:""}.workflow-steps li.done>span{color:#fff;background:var(--crm-teal);border-color:var(--crm-teal)}.workflow-steps li.active>span{border:5px solid var(--crm-brand-soft)}.workflow-steps i{width:5px;height:5px;background:var(--crm-text-muted);border-radius:50%}.workflow-steps div{display:grid;align-content:start;gap:3px}.workflow-steps strong{font-size:9px}.workflow-steps small{color:var(--crm-text-muted);font-size:8px}.preview-workspace{display:grid;min-width:0;grid-template-rows:auto 1fr;background:#eef1f1}.preview-workspace>header{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 14px;background:#fff;border-bottom:1px solid var(--crm-line)}.preview-workspace h2{max-width:430px;overflow:hidden;margin:4px 0 0;color:var(--crm-navy);font-size:11px;text-overflow:ellipsis;white-space:nowrap}.preview-workspace button{display:flex;align-items:center;gap:5px}.preview-surface{display:grid;min-height:590px;padding:14px;place-items:stretch}.preview-surface iframe,.preview-surface img{width:100%;height:100%;min-height:560px;background:#fff;border:0;object-fit:contain}.action-panel{display:grid;gap:10px}.action-panel>svg{color:var(--crm-teal)}.action-panel h2{margin:0;color:var(--crm-navy);font-size:12px}.action-panel p{margin:0;color:var(--crm-text-muted);font-size:9px;line-height:1.55}.action-panel textarea,.action-panel input{width:100%;padding:9px;background:#fff;border:1px solid var(--crm-line);border-radius:7px;font:inherit;font-size:9px}.decision-buttons{display:grid;grid-template-columns:1fr 1fr;gap:7px}.decision-buttons button,.action-panel>button{display:flex;align-items:center;justify-content:center;gap:4px}.secondary-button.danger{color:var(--crm-danger);border-color:#edc6c6}.action-error,.action-notice{margin:10px 14px 0;padding:9px;border-radius:7px;font-size:8px}.action-error{color:var(--crm-danger);background:#fff1f1}.action-notice{color:var(--crm-teal);background:var(--crm-teal-soft)}.history-panel{padding:14px!important}.history-panel>header{display:flex;align-items:center;justify-content:space-between;margin-bottom:9px}.history-panel>button{display:grid;width:100%;grid-template-columns:28px 1fr;gap:7px;padding:9px;text-align:left;background:transparent;border:1px solid transparent;border-radius:7px;cursor:pointer}.history-panel>button.selected{background:#fff;border-color:var(--crm-line)}.history-panel>button>span{color:var(--crm-teal);font-size:9px;font-weight:800}.history-panel>button div{min-width:0}.history-panel>button strong,.history-panel>button small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.history-panel>button strong{font-size:8px}.history-panel>button small{margin-top:3px;color:var(--crm-text-muted);font-size:7px}.history-panel article{margin-top:10px;padding-top:10px;border-top:1px solid var(--crm-line)}.history-panel article strong{font-size:9px}.history-panel article p{margin:5px 0;color:var(--crm-text);font-size:8px;line-height:1.5}.history-panel article small{color:var(--crm-text-muted);font-size:7px}@media(max-width:1180px){.detail-layout{grid-template-columns:220px minmax(420px,1fr)}.action-sidebar{grid-column:1/-1;grid-template-columns:repeat(2,minmax(0,1fr));border-top:1px solid var(--crm-line);border-left:0}.action-sidebar>section{border-right:1px solid var(--crm-line)}}@media(max-width:760px){.detail-layout{grid-template-columns:1fr}.project-sidebar,.action-sidebar{grid-column:auto;grid-template-columns:1fr;border:0}.project-sidebar{border-bottom:1px solid var(--crm-line)}.preview-surface{min-height:440px}.preview-surface iframe,.preview-surface img{min-height:410px}}
</style>
