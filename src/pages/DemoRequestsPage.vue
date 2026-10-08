<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ClipboardCheck, Plus } from '@lucide/vue'
import { api as defaultApi, CrmApiError, type CrmApi } from '@/api'
import type { AccountSummaryDto, ContactSummaryDto, CreateContactInput, CreateDemoRequestInput, DemoRequestCommand, DemoRequestDto } from '@/types/crm'
import { mapRequestError, requestErrorMessage, readRequestMeta, type RequestMetaState } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import PageHeader from '@/design-system/PageHeader.vue'
import DataState from '@/design-system/DataState.vue'
import DataNotice from '@/design-system/DataNotice.vue'
import DemoRequestModal from '@/features/demo-requests/DemoRequestModal.vue'
import DemoRequestWorkspaceNav, { type DemoRequestView } from '@/features/demo-requests/DemoRequestWorkspaceNav.vue'
import DemoRequestWorkspace from '@/features/demo-requests/DemoRequestWorkspace.vue'
import { readAllPages, readAllPagesWithFirst } from '@/features/shared/read-all-pages'
import ContactModal from '@/features/contacts/ContactModal.vue'
import { generateDemoRequestDocxArtifact } from '@/features/demo-requests/demo-request-docx'
import { useI18n, useLocaleMessage, localeMessage, type LocaleMessage } from '@/i18n'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const app = useAppStore()
const route = useRoute()
const router = useRouter()
const { t, locale, message } = useI18n()
const rows = ref<DemoRequestDto[]>([]), accounts = ref<AccountSummaryDto[]>([]), loading = ref(false), error = useLocaleMessage(), requestId = ref(''), denied = ref(false), meta = ref<RequestMetaState | null>(null)
const actionError = useLocaleMessage(), actionRequestId = ref('')
// The dialog's own refusal (a save the server refused), apart from the page's actions, and bound to the dialog it was
// answered to: each opening is a session, and a refusal that comes back after the dialog was closed goes to the page's
// banner instead of the next dialog.
const modalError = useLocaleMessage(), modalRequestId = ref(''), modalFieldErrors = ref<Record<string, string>>({})
let modalSession = 0
const processing = ref(''), modalMode = ref<'create'|'edit'|'engineer'|'manager'|''>(''), selected = ref<DemoRequestDto | null>(null)
// A save refused for the record's version: the dialog keeps its draft and offers the latest version (`reloadLatest`);
// while that version is being read, the dialog is held (nothing typed meanwhile could survive the form starting over).
const modalConflict = ref(false), modalReloading = ref(false)
// The dialog's own save, out or not: the page's other actions (`processing`) do not stand for it.
const modalSaving = ref(false)
const activeView = ref<DemoRequestView>('overview')
const selectedRequestId = ref('')
const downloadingId = ref(''), downloadError = useLocaleMessage()
const downloadNotice = useLocaleMessage()
const preparedDownload = ref<{ requestId: string; url: string; fileName: string } | null>(null)
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
const currentViewCopy = computed(() => {
  const copy: Record<DemoRequestView, { eyebrow: string; title: string; description: string }> = {
    overview: { eyebrow: 'DEMO REQUEST CENTER', title: t('demoRequests.overviewTitle'), description: t('demoRequests.overviewDescription') },
    sales: { eyebrow: 'DEMO REQUEST CENTER', title: t('demoRequests.salesTitle'), description: t('demoRequests.salesDescription') },
    engineer: { eyebrow: 'DEMO REQUEST CENTER', title: t('demoRequests.engineerTitle'), description: t('demoRequests.engineerDescription') },
    manager: { eyebrow: 'DEMO REQUEST CENTER', title: t('demoRequests.managerTitle'), description: t('demoRequests.managerDescription') },
  }
  return copy[activeView.value]
})

// Resolves true when this read's rows are the ones shown (false when it failed or a later read took over).
// The last read's refusal, as a message in both languages, for a dialog that asked for the read (`reloadLatest`).
let lastLoadError: LocaleMessage = ''
async function load(): Promise<boolean> {
  const current = ++sequence; loading.value = true; error.value = ''; denied.value = false; meta.value = null; lastLoadError = ''
  try {
    const contactId = typeof route.query.contactId === 'string' ? route.query.contactId : ''
    // Everything still in progress, in one read: the workspace sorts it into its views and pages each of them.
    const [requests, accountRows, contactRows] = await Promise.all([
      readAllPagesWithFirst((requestPage, requestPageSize) => props.apiClient.listDemoRequests({ accountId: 'All', owner: 'All', status: 'All', inProgress: '1', contactId, page: requestPage, pageSize: requestPageSize })),
      readAllPages((referencePage, referencePageSize) => props.apiClient.listAccounts({ page: referencePage, pageSize: referencePageSize })),
      app.can('contact:view') ? readAllPages((referencePage, referencePageSize) => props.apiClient.listContacts({ page: referencePage, pageSize: referencePageSize })) : Promise.resolve(null),
    ])
    if (current !== sequence) return false
    rows.value = requests.items; accounts.value = accountRows; contacts.value = contactRows ?? []; meta.value = readRequestMeta(requests.first)
    return true
  } catch (reason) { if (current !== sequence) return false; const mapped = mapRequestError(reason); lastLoadError = mapped.localizedMessage ?? mapped.message; error.value = lastLoadError; requestId.value = mapped.requestId; denied.value = mapped.denied; if (mapped.denied) rows.value = []; return false }
  finally { if (current === sequence) loading.value = false }
}
// A dialog opened or closed starts its own state: a read or a save still out for the one before ends with that session.
function open(mode: 'create'|'edit'|'engineer'|'manager', request: DemoRequestDto | null = null) { modalSession += 1; clearModalError(); modalSaving.value = false; modalReloading.value = false; modalMode.value = mode; selected.value = request }
function closeModal() { modalSession += 1; clearModalError(); modalSaving.value = false; modalReloading.value = false; modalMode.value = '' }
function clearModalError() { modalError.value = ''; modalRequestId.value = ''; modalFieldErrors.value = {}; modalConflict.value = false }
// The states a dialog acts on (as `DemoRequestCard` offers them): a record read anew in another state has moved on.
const DIALOG_STATES: Record<'edit' | 'engineer' | 'manager', Array<DemoRequestDto['status']>> = {
  edit: ['Draft', 'Engineer Returned', 'Manager Rejected'], engineer: ['Engineer Review'], manager: ['Manager Approval'],
}
// Discards the draft on purpose, at the user's request: it is the way out of a version the server refused.
async function reloadLatest() {
  const session = modalSession
  const id = selected.value?.id
  const mode = modalMode.value
  if (!id || mode === '' || mode === 'create' || modalSaving.value) return
  // The dialog waits for the read: a save sent meanwhile would name the version being replaced, and anything typed
  // meanwhile would be lost when the form starts over.
  modalSaving.value = true
  modalReloading.value = true
  let loaded = false
  try { loaded = await load() } finally { if (session === modalSession) { modalSaving.value = false; modalReloading.value = false } }
  if (session !== modalSession) return
  if (!loaded) {
    // Refused for who asks: the page says so, the dialog has nothing to show. Failed: the dialog says so and keeps its
    // draft and the button. Overtaken by a later read: that read's outcome stands and the dialog is left as it is.
    if (denied.value) { modalMode.value = ''; selected.value = null; clearModalError() }
    else if (lastLoadError) { modalError.value = lastLoadError; modalRequestId.value = requestId.value }
    return
  }
  const refreshed = rows.value.find((item) => item.id === id)
  if (refreshed && DIALOG_STATES[mode].includes(refreshed.status)) { selected.value = refreshed; clearModalError(); return }
  // Read anew, the request is not one this dialog can act on any more: it left the in-progress ones, this page's
  // contact or the user's reach, or moved on to another step. The list shows it as it is now.
  closeModal()
  selected.value = null
  actionError.value = localeMessage('This Demo Request has moved on since the dialog opened: it is no longer in progress, no longer in this list, or no longer at the step this dialog handles. The list shows the latest records.', '该 Demo 申请在对话框打开后已有变化：已不在进行中、不在这个列表里，或已不在这一步；列表已显示最新记录。')
  actionRequestId.value = ''
}
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
    error.value = mapped.localizedMessage ?? mapped.message; requestId.value = mapped.requestId; denied.value = true; rows.value = []; modalMode.value = ''; selected.value = null
    clearActionError()
    return
  }
  actionError.value = reason instanceof CrmApiError && reason.code === 'VERSION_CONFLICT'
    ? message('demoRequests.versionConflict')
    : mapped.localizedMessage ?? mapped.message
  actionRequestId.value = mapped.requestId
  if (reason instanceof CrmApiError && reason.code === 'VERSION_CONFLICT') await load()
}
async function submitRequest(id: string) { processing.value = id; clearActionError(); try { const request = rows.value.find((item) => item.id === id); await props.apiClient.transitionDemoRequest(id, { type: 'submit' }, request?.modified); await load() } catch (reason) { await handleWriteError(reason) } finally { processing.value = '' } }
async function cancelRequest(id: string) { processing.value = id; clearActionError(); try { const request = rows.value.find((item) => item.id === id); await props.apiClient.transitionDemoRequest(id, { type: 'cancel', comment: 'Sales 取消申请' }, request?.modified); await load() } catch (reason) { await handleWriteError(reason) } finally { processing.value = '' } }
async function submitModal(payload: CreateDemoRequestInput | DemoRequestCommand) {
  processing.value = selected.value?.id || 'create'
  const session = modalSession
  modalSaving.value = true
  // A known conflict outlives a save refused for another reason: the version is still the one refused.
  const wasConflict = modalConflict.value
  clearModalError()
  let handoff: { requestId: string; evaluationId: string } | null = null
  try {
    if (modalMode.value === 'create') {
      // The new request becomes the selected one, so the workspace shows the page it is on.
      selectedRequestId.value = (await props.apiClient.createDemoRequest(payload as CreateDemoRequestInput)).data.id
    } else if (modalMode.value === 'edit') {
      await props.apiClient.updateDemoRequest(selected.value!.id, payload as CreateDemoRequestInput, selected.value!.modified)
    } else {
      const result = await props.apiClient.transitionDemoRequest(selected.value!.id, payload as DemoRequestCommand, selected.value!.modified)
      if (result.data.evaluation) handoff = { requestId: result.data.request.id, evaluationId: result.data.evaluation.id }
    }
    // Answered to a dialog since closed (another may be open, saving): the list is read anew, that dialog left alone.
    if (session !== modalSession) { await load(); return }
    if (handoff) demoTestHandoff.value = handoff
    closeModal()
    selected.value = null
    await load()
  }
  catch (reason) {
    const mapped = mapRequestError(reason)
    // Denied for who asks, or answered to a dialog since closed: the page's business. Otherwise the dialog's.
    if (mapped.denied || !(reason instanceof CrmApiError) || session !== modalSession) { await handleWriteError(reason); return }
    // A version conflict of a record (a new request has no version): the dialog keeps its draft and still names the
    // version it opened with, so a save without the latest version is refused again; the way on is `reloadLatest`,
    // asked for by the user. The list is read again so that the page behind the dialog is current.
    const conflict = reason.code === 'VERSION_CONFLICT' && selected.value !== null
    modalError.value = conflict ? message('demoRequests.dialogVersionConflict') : mapped.localizedMessage ?? mapped.message
    modalRequestId.value = mapped.requestId
    modalFieldErrors.value = reason.fieldErrors
    modalConflict.value = conflict || (wasConflict && selected.value !== null)
    if (reason.code === 'VERSION_CONFLICT') {
      await load()
      // Refused for who asks meanwhile: the page says so, the dialog has nothing to show (as `reloadLatest`).
      if (denied.value && session === modalSession) { modalMode.value = ''; selected.value = null; clearModalError() }
    }
  }
  finally { processing.value = ''; if (session === modalSession) modalSaving.value = false }
}
async function downloadRequest(request: DemoRequestDto) {
  downloadingId.value = request.id
  downloadError.value = ''
  clearPreparedDownload()
  try {
    const artifact = await generateDemoRequestDocxArtifact(request)
    let archiveWarning: LocaleMessage | '' = ''
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
        ? localeMessage('Your role cannot write Artifacts; this file will not be saved to the archive.', '当前角色没有 Artifact 写入权限，本次文件不会保存到归档。')
        : requestErrorMessage(reason, localeMessage('Archive save failed. Please retry.', '归档保存失败，请重试。'))
    }
    downloadNotice.value = archiveWarning || localeMessage('Word is ready. Click “Save Word file” to download.', 'Word 已生成，请点击“保存 Word 文件”完成下载。')
    preparedDownload.value = {
      requestId: request.id,
      url: URL.createObjectURL(artifact.blob),
      fileName: artifact.fileName,
    }
  }
  catch (reason) {
    downloadError.value = reason instanceof Error && reason.message === 'Word 模板加载失败，请重试'
      ? localeMessage('Word template failed to load. Please retry.', 'Word 模板加载失败，请重试')
      : requestErrorMessage(reason, localeMessage('Word generation failed. Check the request content and try again.', 'Word 文档生成失败，请检查申请内容后重试'))
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
    <PageHeader :eyebrow="currentViewCopy.eyebrow" :title="currentViewCopy.title" :description="currentViewCopy.description"><button v-if="canCreate" class="primary-button" type="button" data-testid="new-demo-request" @click="open('create')"><Plus :size="15" />{{ t('demoRequests.new') }}</button></PageHeader>
    <DataNotice v-if="meta?.stale" :message="meta.localizedMessage ?? meta.message" :request-id="meta.requestId" @refresh="load" />
    <div v-if="actionError" class="api-error" data-api-error role="alert"><span>{{ actionError }}</span><small v-if="actionRequestId">Request ID · {{ actionRequestId }}</small></div>
    <DemoRequestWorkspaceNav v-if="!denied" v-model="activeView" />
    <div v-if="demoTestHandoff" class="demo-test-handoff" data-demo-test-handoff role="status">
      <span><strong>{{ demoTestHandoff.requestId }}</strong> {{ locale === 'en-US' ? 'was approved and created Demo Test' : '已批准，并已创建 Demo Test' }} <strong>{{ demoTestHandoff.evaluationId }}</strong>{{ locale === 'en-US' ? '.' : '。' }}</span>
      <RouterLink :to="{ name: 'evaluations', query: { focus: demoTestHandoff.evaluationId } }">{{ locale === 'en-US' ? 'Go to Demo Test' : '前往 Demo Test' }}</RouterLink>
    </div>
    <div v-if="downloadError" class="download-error" role="alert">{{ downloadError }}</div>
    <div v-if="preparedDownload" class="download-ready" role="status">
      <span>{{ downloadNotice }}</span>
      <a :data-demo-save="preparedDownload.requestId" :href="preparedDownload.url" :download="preparedDownload.fileName">{{ locale === 'en-US' ? 'Save Word file' : '保存 Word 文件' }}</a>
    </div>
    <DataState v-if="loading && !activeRows.length" type="loading" /><DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" /><DataState v-else-if="error" type="error" :message="error" :request-id="requestId" @retry="load" /><DataState v-else-if="!activeRows.length" type="empty" :title="t('demoRequests.emptyTitle')" :message="t('demoRequests.emptyMessage')" />
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
    <DemoRequestModal v-if="modalMode" :mode="modalMode" :request="selected" :accounts="accounts" :contacts="contacts" :selected-contact-id="modalContactId" :current-sales-contact="app.bootstrap?.user.id || ''" :busy="modalSaving" :api-client="props.apiClient" :error="modalError" :request-id="modalRequestId" :field-errors="modalFieldErrors" :conflict="modalConflict" :reloading="modalReloading" @close="closeModal" @create-contact="openContact" @submit="submitModal" @reload="reloadLatest" />
    <ContactModal v-if="contactModal" :accounts="accounts" :sites="[]" :contacts="contacts" :fixed-account-id="contactAccountId" @close="contactModal = false" @submit="saveContact" />
  </div>
</template>

<style scoped>
.demo-test-handoff,.download-error,.download-ready,.api-error{margin-bottom:12px;padding:10px 12px;border-radius:9px;font-size:11px;font-weight:700}.demo-test-handoff,.download-ready{display:flex;align-items:center;justify-content:space-between;gap:12px;color:#315f4b;background:#eaf5ef;border:1px solid #bddccb}.demo-test-handoff a,.download-ready a{flex:none;padding:7px 10px;color:var(--crm-brand-ink);background:var(--crm-teal);border-radius:7px;text-decoration:none}.download-error,.api-error{color:#9a3a31;background:#fbe9e5;border:1px solid #edc7be}.api-error{display:grid;gap:4px}.api-error small{opacity:.75}@media(max-width:470px){.demo-test-handoff,.download-ready{align-items:flex-start;flex-direction:column}}
</style>
