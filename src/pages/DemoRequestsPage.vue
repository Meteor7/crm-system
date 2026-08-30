<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ClipboardCheck, Plus } from '@lucide/vue'
import { api as defaultApi, CrmApiError, type CrmApi } from '@/api'
import type { AccountSummaryDto, ContactSummaryDto, CreateContactInput, CreateDemoRequestInput, DemoRequestCommand, DemoRequestDto } from '@/types/crm'
import { mapRequestError, readRequestMeta, type RequestMetaState } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import PageHeader from '@/design-system/PageHeader.vue'
import DataState from '@/design-system/DataState.vue'
import DataNotice from '@/design-system/DataNotice.vue'
import DemoRequestModal from '@/features/demo-requests/DemoRequestModal.vue'
import DemoRequestWorkspaceNav, { type DemoRequestView } from '@/features/demo-requests/DemoRequestWorkspaceNav.vue'
import DemoRequestWorkspace from '@/features/demo-requests/DemoRequestWorkspace.vue'
import PaginationControls from '@/features/shared/PaginationControls.vue'
import { readAllPages } from '@/features/shared/read-all-pages'
import ContactModal from '@/features/contacts/ContactModal.vue'
import { generateDemoRequestDocxArtifact } from '@/features/demo-requests/demo-request-docx'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const app = useAppStore()
const route = useRoute()
const router = useRouter()
const rows = ref<DemoRequestDto[]>([]), accounts = ref<AccountSummaryDto[]>([]), loading = ref(false), error = ref(''), requestId = ref(''), denied = ref(false), meta = ref<RequestMetaState | null>(null)
const total = ref(0), page = ref(1)
const pageSize = ref(10)
const actionError = ref(''), actionRequestId = ref('')
const processing = ref(''), modalMode = ref<'create'|'edit'|'engineer'|'manager'|''>(''), selected = ref<DemoRequestDto | null>(null)
const activeView = ref<DemoRequestView>('overview')
const selectedRequestId = ref('')
const downloadingId = ref(''), downloadError = ref('')
const preparedDownload = ref<{ requestId: string; url: string; fileName: string; notice: string } | null>(null)
const demoTestHandoff = ref<{ requestId: string; evaluationId: string } | null>(null)
const contacts = ref<ContactSummaryDto[]>([])
const contactModal = ref(false)
const modalContactId = ref('')
const contactAccountId = ref('')
let sequence = 0
const activeRows = computed(() => rows.value.filter((item) => !['Converted', 'Cancelled'].includes(item.status)))
const canCreate = computed(() => app.can('demo_request:create'))
const canEngineer = computed(() => app.can('demo_request:engineering_review'))
const canManager = computed(() => app.can('demo_request:manager_approve'))
const viewCopy: Record<DemoRequestView, { eyebrow: string; title: string; description: string }> = {
  overview: { eyebrow: 'DEMO REQUEST CENTER', title: 'Demo Request 总览', description: '查看和管理全部 Demo Request，跟踪申请状态与处理进度。' },
  sales: { eyebrow: 'DEMO REQUEST CENTER', title: 'Sales Preparation', description: '完善客户需求、设备与样品信息，提交工程评估。' },
  engineer: { eyebrow: 'DEMO REQUEST CENTER', title: 'Engineer Review', description: '依据 Sales 填写的 DRF 信息形成工程评估结论。' },
  manager: { eyebrow: 'DEMO REQUEST CENTER', title: 'Manager Approval', description: '基于工程评估与风险检查完成最终审批。' },
}
const currentViewCopy = computed(() => viewCopy[activeView.value])

async function load() {
  const current = ++sequence; loading.value = true; error.value = ''; denied.value = false; meta.value = null
  try {
    const contactId = typeof route.query.contactId === 'string' ? route.query.contactId : ''
    const [requests, accountRows, contactRows] = await Promise.all([
      props.apiClient.listDemoRequests({ accountId: 'All', owner: 'All', status: 'All', contactId, page: page.value, pageSize: pageSize.value }),
      readAllPages((referencePage, referencePageSize) => props.apiClient.listAccounts({ page: referencePage, pageSize: referencePageSize })),
      app.can('contact:view') ? readAllPages((referencePage, referencePageSize) => props.apiClient.listContacts({ page: referencePage, pageSize: referencePageSize })) : Promise.resolve(null),
    ])
    if (current !== sequence) return
    rows.value = requests.data.items; total.value = requests.meta?.total ?? rows.value.length; accounts.value = accountRows; contacts.value = contactRows ?? []; meta.value = readRequestMeta(requests)
  } catch (reason) { if (current !== sequence) return; const mapped = mapRequestError(reason); error.value = mapped.message; requestId.value = mapped.requestId; denied.value = mapped.denied; if (mapped.denied) rows.value = [] }
  finally { if (current === sequence) loading.value = false }
}
function goPage(target: number) { page.value = target; void load() }
function changePageSize(value: number) { pageSize.value = value; page.value = 1; void load() }
function open(mode: 'create'|'edit'|'engineer'|'manager', request: DemoRequestDto | null = null) { modalMode.value = mode; selected.value = request }
function openDetail(request: DemoRequestDto) {
  router.push({ name: 'demo-detail', params: { demoId: request.id }, query: { from: 'demo-requests' } })
}
function openContact(accountId: string) { contactAccountId.value = accountId; contactModal.value = true }
async function saveContact(input: CreateContactInput) {
  try {
    const created = await props.apiClient.createContact(input)
    modalContactId.value = created.data.id
    contacts.value = await readAllPages((referencePage, referencePageSize) => props.apiClient.listContacts({ page: referencePage, pageSize: referencePageSize }))
    contactModal.value = false
  } catch (reason) { handleWriteError(reason) }
}
function clearActionError() { actionError.value = ''; actionRequestId.value = '' }
async function handleWriteError(reason: unknown) {
  const mapped = mapRequestError(reason)
  if (mapped.denied) {
    error.value = mapped.message; requestId.value = mapped.requestId; denied.value = true; rows.value = []; modalMode.value = ''; selected.value = null
    clearActionError()
    return
  }
  actionError.value = reason instanceof CrmApiError && reason.code === 'VERSION_CONFLICT'
    ? '记录已被其他用户更新，已刷新最新数据，请重新确认后操作。'
    : mapped.message
  actionRequestId.value = mapped.requestId
  if (reason instanceof CrmApiError && reason.code === 'VERSION_CONFLICT') await load()
}
async function submitRequest(id: string) { processing.value = id; clearActionError(); try { const request = rows.value.find((item) => item.id === id); await props.apiClient.transitionDemoRequest(id, { type: 'submit' }, request?.modified); await load() } catch (reason) { await handleWriteError(reason) } finally { processing.value = '' } }
async function cancelRequest(id: string) { processing.value = id; clearActionError(); try { const request = rows.value.find((item) => item.id === id); await props.apiClient.transitionDemoRequest(id, { type: 'cancel', comment: 'Sales 取消申请' }, request?.modified); await load() } catch (reason) { await handleWriteError(reason) } finally { processing.value = '' } }
async function submitModal(payload: CreateDemoRequestInput | DemoRequestCommand) {
  processing.value = selected.value?.id || 'create'
  clearActionError()
  try {
    if (modalMode.value === 'create') {
      await props.apiClient.createDemoRequest(payload as CreateDemoRequestInput)
    } else if (modalMode.value === 'edit') {
      await props.apiClient.updateDemoRequest(selected.value!.id, payload as CreateDemoRequestInput, selected.value!.modified)
    } else {
      const result = await props.apiClient.transitionDemoRequest(selected.value!.id, payload as DemoRequestCommand, selected.value!.modified)
      if (result.data.evaluation) {
        demoTestHandoff.value = {
          requestId: result.data.request.id,
          evaluationId: result.data.evaluation.id,
        }
      }
    }
    modalMode.value = ''
    selected.value = null
    await load()
  }
  catch (reason) { await handleWriteError(reason) }
  finally { processing.value = '' }
}
async function downloadRequest(request: DemoRequestDto) {
  downloadingId.value = request.id
  downloadError.value = ''
  clearPreparedDownload()
  try {
    const artifact = await generateDemoRequestDocxArtifact(request)
    let archiveWarning = ''
    try {
      await props.apiClient.saveDemoArtifact({
        demoRequestId: request.id,
        type: 'Demo Request DOCX',
        visibility: 'Internal',
        file: {
          fileName: artifact.fileName,
          mimeType: artifact.blob.type,
          size: artifact.blob.size,
          blob: artifact.blob,
        },
      })
    } catch (reason) {
      const mapped = mapRequestError(reason)
      archiveWarning = mapped.denied
        ? '当前角色没有 Artifact 写入权限，本次文件不会保存到归档。'
        : `归档保存失败：${mapped.message}`
    }
    preparedDownload.value = {
      requestId: request.id,
      url: URL.createObjectURL(artifact.blob),
      fileName: artifact.fileName,
      notice: archiveWarning || 'Word 已生成，请点击“保存 Word 文件”完成下载。',
    }
  }
  catch (reason) {
    downloadError.value = reason instanceof Error && reason.message === 'Word 模板加载失败，请重试'
      ? 'Word 模板加载失败，请重试'
      : 'Word 文档生成失败，请检查申请内容后重试'
  }
  finally { downloadingId.value = '' }
}
function clearPreparedDownload() {
  if (preparedDownload.value) URL.revokeObjectURL(preparedDownload.value.url)
  preparedDownload.value = null
}
onMounted(async () => {
  await app.loadBootstrap(props.apiClient)
  await load()
})
onBeforeUnmount(clearPreparedDownload)
</script>

<template>
  <div>
    <PageHeader :eyebrow="currentViewCopy.eyebrow" :title="currentViewCopy.title" :description="currentViewCopy.description"><button v-if="canCreate" class="primary-button" type="button" @click="open('create')"><Plus :size="15" />新建 Demo Request</button></PageHeader>
    <DataNotice v-if="meta?.stale" :message="meta.message" :request-id="meta.requestId" @refresh="load" />
    <div v-if="actionError" class="api-error" data-api-error role="alert"><span>{{ actionError }}</span><small v-if="actionRequestId">Request ID · {{ actionRequestId }}</small></div>
    <DemoRequestWorkspaceNav v-if="!denied" v-model="activeView" />
    <div v-if="demoTestHandoff" class="demo-test-handoff" data-demo-test-handoff role="status">
      <span><strong>{{ demoTestHandoff.requestId }}</strong> 已批准，并已创建 Demo Test <strong>{{ demoTestHandoff.evaluationId }}</strong>。</span>
      <RouterLink :to="{ name: 'evaluations', query: { focus: demoTestHandoff.evaluationId } }">前往 Demo Test</RouterLink>
    </div>
    <div v-if="downloadError" class="download-error" role="alert">{{ downloadError }}</div>
    <div v-if="preparedDownload" class="download-ready" role="status">
      <span>{{ preparedDownload.notice }}</span>
      <a :data-demo-save="preparedDownload.requestId" :href="preparedDownload.url" :download="preparedDownload.fileName">保存 Word 文件</a>
    </div>
    <DataState v-if="loading && !activeRows.length" type="loading" /><DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" /><DataState v-else-if="error" type="error" :message="error" :request-id="requestId" @retry="load" /><DataState v-else-if="!activeRows.length" type="empty" title="没有匹配的 Demo Request" message="调整筛选条件，或新建第一条 Demo Request。" />
    <DemoRequestWorkspace
      v-else
      :view="activeView"
      :requests="activeRows"
      :selected-id="selectedRequestId"
      :can-create="canCreate"
      :can-engineer="canEngineer"
      :can-manager="canManager"
      :processing="processing"
      :downloading="downloadingId"
      @select="selectedRequestId = $event"
      @open-detail="openDetail"
      @submit="submitRequest"
      @edit="open('edit', $event)"
      @cancel="cancelRequest"
      @engineer="open('engineer', $event)"
      @manager="open('manager', $event)"
      @download="downloadRequest"
    />
    <PaginationControls v-if="!denied && !error && total > pageSize" :page="page" :page-size="pageSize" :total="total" @change="goPage" @page-size-change="changePageSize" />
    <DemoRequestModal v-if="modalMode" :mode="modalMode" :request="selected" :accounts="accounts" :contacts="contacts" :selected-contact-id="modalContactId" :current-sales-contact="app.bootstrap?.user.id || ''" :busy="Boolean(processing)" :api-client="props.apiClient" @close="modalMode = ''" @create-contact="openContact" @submit="submitModal" />
    <ContactModal v-if="contactModal" :accounts="accounts" :sites="[]" :contacts="contacts" :fixed-account-id="contactAccountId" @close="contactModal = false" @submit="saveContact" />
  </div>
</template>

<style scoped>
.demo-test-handoff,.download-error,.download-ready,.api-error{margin-bottom:12px;padding:10px 12px;border-radius:9px;font-size:11px;font-weight:700}.demo-test-handoff,.download-ready{display:flex;align-items:center;justify-content:space-between;gap:12px;color:#315f4b;background:#eaf5ef;border:1px solid #bddccb}.demo-test-handoff a,.download-ready a{flex:none;padding:7px 10px;color:var(--crm-brand-ink);background:var(--crm-teal);border-radius:7px;text-decoration:none}.download-error,.api-error{color:#9a3a31;background:#fbe9e5;border:1px solid #edc7be}.api-error{display:grid;gap:4px}.api-error small{opacity:.75}@media(max-width:470px){.demo-test-handoff,.download-ready{align-items:flex-start;flex-direction:column}}
</style>
