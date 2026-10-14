<script setup lang="ts">
import { DEMO_REQUEST_STAGES, canCreateDemoRequestAt, opportunityStageLabel } from '@/domain/opportunity-stages'
import { computed, reactive, ref, watch } from 'vue'
import { api as defaultApi, type CrmApi } from '@/api'
import type { AccountSummaryDto, ContactSummaryDto, CreateDemoRequestInput, DemoRequestCommand, DemoRequestDto, DemoRequestFormData } from '@/types/crm'
import type { StrategyOpportunityDto } from '@/types/workspaces'
import { activeDemoWaferIndexes, activeDemoWafers, applyDemoRequestImport, cloneDemoRequestFormData, createEmptyDemoRequestFormData, getDemoRequestFormData, validateDemoRequestFormData } from '@/domain/demo-request-form'
import { requestErrorMessage } from '@/api/request-state'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import PersonnelSelect from '@/design-system/PersonnelSelect.vue'
import DemoRequestForm from './DemoRequestForm.vue'
import { useOwnOwnerOnly } from '@/stores/signed-in-user'
import { useI18n, useLocaleMessage, localeMessage } from '@/i18n'

const props = defineProps<{
  mode: 'create' | 'edit' | 'engineer' | 'manager'
  request?: DemoRequestDto | null
  accounts?: AccountSummaryDto[]
  contacts?: ContactSummaryDto[]
  opportunities?: Array<Pick<StrategyOpportunityDto, 'id' | 'accountId' | 'title' | 'stage'>>
  selectedContactId?: string
  currentSalesContact?: string
  busy?: boolean
  apiClient?: CrmApi
  /** The server's refusal of the last save, shown in the dialog; the fields it names are flagged inline. */
  error?: string
  requestId?: string
  fieldErrors?: Record<string, string>
  /** The refusal is for the record's version: the draft is kept, and the latest version can be loaded in its place. */
  conflict?: boolean
  /** The latest version is being read: every field waits, since the form starts over when it arrives. */
  reloading?: boolean
}>()
const emit = defineEmits<{ close: []; submit: [payload: CreateDemoRequestInput | DemoRequestCommand]; 'create-contact': [accountId: string]; reload: [] }>()
const { locale } = useI18n()
const ownOwnerOnly = useOwnOwnerOnly()

const accountId = ref('')
const opportunityId = ref('')
const SELF_TEST_OPTION = '__SELF_TEST__'
const opportunitySearch = ref('')
const loadedOpportunities = ref<StrategyOpportunityDto[]>([])
const opportunityLoading = ref(false)
const opportunityLoadError = useLocaleMessage()
const primaryContactId = ref('')
const formData = ref<DemoRequestFormData>(createEmptyDemoRequestFormData())
const errors = ref<Record<string, string>>({})
type ValidationSnapshot = Record<'en-US' | 'zh-CN', Record<string, string>>
const validationSnapshot = ref<ValidationSnapshot | null>(null)
const submitImmediately = ref(true)
const customerExpectedDate = ref('')
// The visible row each wafer row sent came from: the server names the rows it got (`wafers.0`), the form shows them all.
const sentWaferRows = ref<number[]>([])
const importBusy = ref(false)
// Whether the errors shown include the server's (they are replaced by the editor's own at the next submit or import).
let serverErrorsShown = false
const importError = useLocaleMessage()
const importNotice = useLocaleMessage()
const isSelfTest = computed(() => opportunityId.value === SELF_TEST_OPTION)
const review = reactive({ decision: 'approve', engineerOwner: '', testPlan: '', assignedEquipment: '', resourceWindow: '', estimatedCompletionDate: '2026-08-15', technicalRisk: '', comment: '' })

const opportunityOptions = computed(() => {
  const source = props.opportunities ?? loadedOpportunities.value
  const search = opportunitySearch.value.trim().toLocaleLowerCase()
  return source.filter((item) => item.accountId === accountId.value
    && (item.id === props.request?.opportunityId || canCreateDemoRequestAt(item.stage))
    && (!search || `${item.id} ${item.title}`.toLocaleLowerCase().includes(search)))
})
const opportunityGuidance = computed(() => locale.value === 'en-US'
  ? 'Select a customer company below to filter Opportunities or self-test'
  : '请先选择下方客户公司名筛选 Opportunities 或自测')

let opportunityRequest = 0
async function loadOpportunities() {
  if (props.opportunities || !accountId.value || (props.mode !== 'create' && props.mode !== 'edit')) return
  const request = ++opportunityRequest
  opportunityLoading.value = true
  opportunityLoadError.value = ''
  try {
    const query = { accountId: accountId.value, search: opportunitySearch.value.trim(), page: 1, pageSize: 20 }
    const results = await Promise.all(DEMO_REQUEST_STAGES.map((status) =>
      (props.apiClient || defaultApi).listStrategyOpportunities({ ...query, status }),
    ))
    if (request !== opportunityRequest) return
    const eligible = results.flatMap((result) => result.data.items)
    if (props.request?.opportunityId && !eligible.some((item) => item.id === props.request?.opportunityId)) {
      const linked = await (props.apiClient || defaultApi).getStrategyOpportunity(props.request.opportunityId)
      if (request !== opportunityRequest) return
      eligible.unshift(linked.data)
    }
    loadedOpportunities.value = Array.from(new Map(eligible.map((item) => [item.id, item])).values())
    opportunityLoadError.value = ''
  } catch (reason) {
    if (request === opportunityRequest) opportunityLoadError.value = requestErrorMessage(reason, localeMessage('Unable to load eligible opportunities.', '暂时无法读取可关联的 Opportunity。'))
  } finally {
    if (request === opportunityRequest) opportunityLoading.value = false
  }
}

// The Accounts are not watched: they are reference data, read again by the page after each of its actions, and
// their refresh must not start the form over under the user.
// The record the form was last started from: the same record read anew (the latest version loaded) starts the
// record's fields over, not what the user chose to do with it (the submit choice, the review decision and comment).
let startedFrom = ''
watch(() => [props.mode, props.request, props.currentSalesContact] as const, () => {
  const key = `${props.mode}:${props.request?.id ?? ''}`
  const sameRecord = key === startedFrom
  startedFrom = key
  accountId.value = props.request?.accountId || ''
  opportunityId.value = props.request?.requestMode === 'Self Test' ? SELF_TEST_OPTION : props.request?.opportunityId || ''
  primaryContactId.value = props.request?.primaryContactId || props.selectedContactId || ''
  formData.value = props.request
    ? getDemoRequestFormData(props.request)
    : createEmptyDemoRequestFormData(props.currentSalesContact || '')
  errors.value = {}
  serverErrorsShown = false
  opportunityLoadError.value = ''
  // A form started over (the latest version loaded) holds nothing of an import done before.
  importError.value = ''
  importNotice.value = ''
  validationSnapshot.value = null
  if (!sameRecord) submitImmediately.value = true
  customerExpectedDate.value = props.request?.customerExpectedDate || ''
  if (!sameRecord) review.decision = 'approve'
  review.engineerOwner = props.request?.engineerOwner || ''
  review.testPlan = props.request?.testPlan || ''
  review.assignedEquipment = props.request?.assignedEquipment || props.request?.requestedEquipment || ''
  review.resourceWindow = props.request?.resourceWindow || ''
  review.estimatedCompletionDate = props.request?.estimatedCompletionDate || props.request?.targetDate || '2026-08-15'
  review.technicalRisk = props.request?.technicalRisk || ''
  if (!sameRecord) review.comment = ''
  void loadOpportunities()
}, { immediate: true })
watch(() => props.selectedContactId, (value) => {
  if (value) primaryContactId.value = value
})
watch(accountId, () => {
  if (!(props.contacts || []).some((item) => item.id === primaryContactId.value && item.accountId === accountId.value && item.status === 'Active')) {
    primaryContactId.value = ''
  }
  const selectedOpportunity = (props.opportunities ?? loadedOpportunities.value).find((item) => item.id === opportunityId.value)
  if (selectedOpportunity && selectedOpportunity.accountId !== accountId.value) opportunityId.value = ''
  void loadOpportunities()
})
watch(opportunitySearch, () => { void loadOpportunities() })
watch(locale, () => {
  if (!validationSnapshot.value) return
  const validationKeys = new Set([...Object.keys(validationSnapshot.value['en-US']), ...Object.keys(validationSnapshot.value['zh-CN'])])
  const refreshed = { ...errors.value }
  validationKeys.forEach((key) => { delete refreshed[key] })
  Object.assign(refreshed, validationSnapshot.value[locale.value])
  errors.value = refreshed
})

async function importCompletedForm(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  importError.value = ''
  importNotice.value = ''
  if (!/\.(pdf|docx)$/i.test(file.name)) {
    importError.value = localeMessage('Only PDF or Word (.docx) files are supported', '仅支持 PDF 或 Word（.docx）文件')
    input.value = ''
    return
  }
  if (!file.size || file.size > 100 * 1024 * 1024) {
    importError.value = localeMessage('File cannot be empty and must not exceed 100 MiB', '文件不能为空且不能超过 100 MiB')
    input.value = ''
    return
  }
  importBusy.value = true
  try {
    const response = await (props.apiClient || defaultApi).importDemoRequestForm({
      blob: file,
      fileName: file.name,
      mimeType: file.type || (file.name.toLocaleLowerCase().endsWith('.pdf')
        ? 'application/pdf'
        : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
      size: file.size,
    })
    // A save that went out while the form was being read counted the rows as they were: the form read is not applied.
    if (props.busy) {
      importError.value = localeMessage('The form was not applied: a save is in progress. Import it again once the save is answered.', '识别结果未应用：保存进行中，等保存返回后再导入。')
      return
    }
    const applied = applyDemoRequestImport(
      formData.value,
      response.data,
      props.accounts || [],
      props.contacts || [],
      // A form that names a colleague leaves a Sales user's own name in place: the field offers nobody else.
      ownOwnerOnly.value ? [ownOwnerOnly.value] : undefined,
    )
    formData.value = applied.formData
    if (applied.accountId) accountId.value = applied.accountId
    if (applied.primaryContactId) primaryContactId.value = applied.primaryContactId
    if (applied.customerExpectedDate) customerExpectedDate.value = applied.customerExpectedDate
    errors.value = {}
    serverErrorsShown = false
    validationSnapshot.value = null
    importNotice.value = localeMessage(`Detected ${response.data.detectedFields.length} fields from ${response.data.fileName}; review before saving.`, `已从 ${response.data.fileName} 识别并回填 ${response.data.detectedFields.length} 个字段，请检查后再保存。`)
  } catch (reason) {
    importError.value = requestErrorMessage(reason, localeMessage('Demo Request form import failed. Please retry.', 'Demo Request 表单导入失败，请重试。'))
  } finally {
    importBusy.value = false
    input.value = ''
  }
}

function submit() {
  if (props.mode === 'create' || props.mode === 'edit') {
    const validationSnapshotValue: ValidationSnapshot = {
      'en-US': validateDemoRequestFormData(formData.value, { requireCustomerInformation: !isSelfTest.value, locale: 'en-US' }),
      'zh-CN': validateDemoRequestFormData(formData.value, { requireCustomerInformation: !isSelfTest.value, locale: 'zh-CN' }),
    }
    const addModalValidation = (messages: Record<string, string>, language: 'en-US' | 'zh-CN') => {
      if (!isSelfTest.value && !primaryContactId.value) messages.primaryContactId = language === 'en-US' ? 'Select a primary contact' : '请选择主要联系人'
      if (!opportunityId.value) messages.opportunityId = language === 'en-US' ? 'Select an opportunity or self-test' : '请选择关联 Opportunity 或自测'
      if (!customerExpectedDate.value) messages.customerExpectedDate = language === 'en-US' ? 'Enter the customer expected date' : '请填写客户期望时间'
    }
    addModalValidation(validationSnapshotValue['en-US'], 'en-US')
    addModalValidation(validationSnapshotValue['zh-CN'], 'zh-CN')
    validationSnapshot.value = validationSnapshotValue
    errors.value = { ...validationSnapshotValue[locale.value] }
    serverErrorsShown = false
    if (Object.keys(errors.value).length) return
    sentWaferRows.value = activeDemoWaferIndexes(formData.value)
    emit('submit', {
      accountId: isSelfTest.value ? '' : accountId.value,
      opportunityId: opportunityId.value === SELF_TEST_OPTION ? undefined : opportunityId.value,
      requestMode: opportunityId.value === SELF_TEST_OPTION ? 'Self Test' : 'Opportunity',
      primaryContactId: primaryContactId.value,
      // The rows that hold data, as counted: a row left empty is not sent (the server asks for every cell of a row it gets).
      formData: { ...cloneDemoRequestFormData(formData.value), wafers: activeDemoWafers(formData.value) },
      customerExpectedDate: customerExpectedDate.value,
      submit: submitImmediately.value,
    })
  } else if (props.mode === 'engineer') {
    emit('submit', review.decision === 'return'
      ? { type: 'engineer_return', comment: review.comment }
      : { type: 'engineer_approve', engineerOwner: review.engineerOwner, testPlan: review.testPlan, assignedEquipment: review.assignedEquipment, resourceWindow: review.resourceWindow, estimatedCompletionDate: review.estimatedCompletionDate, technicalRisk: review.technicalRisk, comment: review.comment })
  } else {
    emit('submit', review.decision === 'reject'
      ? { type: 'manager_reject', comment: review.comment }
      : { type: 'manager_approve', comment: review.comment })
  }
}

// The fields the server named in its refusal are flagged as the editor's own checks flag them (the next submit
// checks the draft anew and replaces them), in the language of the moment, and translated again with the language
// only while they are still the errors shown. Declared last: the form's own set-up above clears the errors first.
function flagServerErrors() {
  const fieldErrors = props.fieldErrors
  if (!fieldErrors || !Object.keys(fieldErrors).length) return
  const flagged: Record<string, string> = {}
  for (const [key, text] of Object.entries(fieldErrors)) {
    // `wafers.<n>` counts the rows sent; the row shown is the one it came from (the rows keep their places while
    // the save is out: the form's row buttons are disabled then), as moved by the rows removed since; a row removed
    // takes its hint with it.
    const sent = /^wafers\.(\d+)(\..*)?$/.exec(key)
    const row = sent ? (sentWaferRows.value[Number(sent[1])] ?? Number(sent[1])) : null
    if (row === -1) continue
    const visibleKey = sent ? `wafers.${row}${sent[2] ?? ''}` : key
    flagged[visibleKey] = text === 'Required' ? (locale.value === 'en-US' ? 'Enter this field' : '请填写此项') : text
  }
  errors.value = { ...errors.value, ...flagged }
  serverErrorsShown = true
}

// A wafer row removed after a refusal: the hints of the rows below it move up with them, the removed row's go, and
// the rows the server counted are remembered as they stand now (a language change re-reads its hints from there).
function rowsMovedUp(messages: Record<string, string>, removed: number): Record<string, string> {
  const moved: Record<string, string> = {}
  for (const [key, text] of Object.entries(messages)) {
    const keyed = /^wafers\.(\d+)(\..*)?$/.exec(key)
    if (!keyed) { moved[key] = text; continue }
    const row = Number(keyed[1])
    if (row === removed) continue
    moved[row > removed ? `wafers.${row - 1}${keyed[2] ?? ''}` : key] = text
  }
  return moved
}
function waferRowRemoved(removed: number) {
  sentWaferRows.value = sentWaferRows.value.map((row) => row === removed ? -1 : row > removed ? row - 1 : row)
  errors.value = rowsMovedUp(errors.value, removed)
  if (validationSnapshot.value) {
    validationSnapshot.value = { 'en-US': rowsMovedUp(validationSnapshot.value['en-US'], removed), 'zh-CN': rowsMovedUp(validationSnapshot.value['zh-CN'], removed) }
  }
}
watch(() => props.fieldErrors, flagServerErrors, { immediate: true })
watch(locale, () => { if (serverErrorsShown) flagServerErrors() })
</script>

<template>
  <ModalShell
    :title="mode === 'create' ? (locale === 'en-US' ? 'New Demo Request' : '新建 Demo Request') : mode === 'edit' ? (locale === 'en-US' ? 'Edit Demo Request' : '修改 Demo Request') : mode === 'engineer' ? (locale === 'en-US' ? 'FAE Review' : '工程评估') : (locale === 'en-US' ? 'Boss Approval' : '经理审批')"
    :eyebrow="mode === 'create' || mode === 'edit' ? (locale === 'en-US' ? 'DEMO REQUEST FORM' : 'DEMO REQUEST 表单') : mode === 'engineer' ? (locale === 'en-US' ? 'FAE REVIEW' : '工程评估') : (locale === 'en-US' ? 'BOSS APPROVAL' : '经理审批')"
    :busy="busy"
    :submit-disabled="importBusy"
    :wide="mode === 'create' || mode === 'edit'"
    @close="$emit('close')"
    @submit="submit"
  >
    <template #feedback>
    <p v-if="error" class="save-error" data-modal-error role="alert"><span>{{ error }}</span><small v-if="requestId">Request ID · {{ requestId }}</small><button v-if="conflict" class="secondary-button" type="button" data-reload-demo-request :disabled="busy || importBusy" @click="emit('reload')">{{ locale === 'en-US' ? 'Load the latest version' : '载入最新版本' }}</button></p>
    </template>
    <fieldset class="dialog-fields" :disabled="reloading">
    <template v-if="mode === 'create' || mode === 'edit'">
      <section class="drf-import-panel" data-demo-request-import>
        <div>
          <strong>{{ locale === 'en-US' ? 'Import completed DRF' : '导入已填写的 DRF' }}</strong>
          <span>{{ locale === 'en-US' ? 'PDF and Word (.docx) are supported. Fields are filled into this form for review; nothing is submitted automatically.' : '支持 PDF 和 Word（.docx），自动识别后回填当前表单，不会自动提交。' }}</span>
        </div>
        <label class="drf-import-button" :class="{ disabled: importBusy || busy }">
          {{ importBusy ? (locale === 'en-US' ? 'Recognizing…' : '正在识别…') : (locale === 'en-US' ? 'Choose file and recognize' : '选择文件并识别') }}
          <input
            data-import-demo-request-input
            type="file"
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            :disabled="importBusy || busy"
            @change="importCompletedForm"
          />
        </label>
        <p v-if="importNotice" data-demo-request-import-success>{{ importNotice }}</p>
        <p v-if="importError" class="import-error" data-demo-request-import-error>{{ importError }}</p>
      </section>
      <div class="request-meta-grid">
        <label><span class="field-label">{{ locale === 'en-US' ? 'Opportunity / self-test' : '关联 Opportunity / 自测' }}<RequiredMark :show="mode === 'create'" /></span>
          <input v-model="opportunitySearch" :aria-label="locale === 'en-US' ? 'Search opportunity' : '搜索 Opportunity'" type="search" :placeholder="accountId ? (locale === 'en-US' ? 'Search by number or name' : '按编号或名称搜索') : opportunityGuidance" />
          <select v-model="opportunityId" :aria-label="locale === 'en-US' ? 'Linked opportunity' : '关联 Opportunity'" required :disabled="mode === 'edit' || opportunityLoading">
            <option value="">{{ opportunityLoading ? (locale === 'en-US' ? 'Loading…' : '正在读取…') : accountId ? (locale === 'en-US' ? 'Select an opportunity or self-test' : '请选择 Opportunity 或自测') : opportunityGuidance }}</option>
            <option :value="SELF_TEST_OPTION">{{ locale === 'en-US' ? 'Self-test (no opportunity link)' : '自测（无需关联 Opportunity）' }}</option>
            <option v-for="opportunity in opportunityOptions" :key="opportunity.id" :value="opportunity.id">
              {{ opportunity.id }} · {{ opportunity.title }} · {{ opportunityStageLabel(opportunity.stage, locale) }}
            </option>
          </select>
          <small v-if="errors.opportunityId || opportunityLoadError" data-field-error="opportunityId">{{ errors.opportunityId || opportunityLoadError }}</small>
        </label>
        <label><span class="field-label">{{ locale === 'en-US' ? 'Customer expected date' : '客户期望时间' }}<RequiredMark :show="mode === 'create'" /></span>
          <input v-model="customerExpectedDate" :aria-label="locale === 'en-US' ? 'Customer expected date' : '客户期望时间'" type="date" required />
          <small>{{ locale === 'en-US' ? 'Used for scheduling and communication only; not written to the Demo Request Word file.' : '仅用于系统排期与沟通，不写入 Demo Request Word' }}</small>
          <small v-if="errors.customerExpectedDate" data-field-error="customerExpectedDate">{{ errors.customerExpectedDate }}</small>
        </label>
      </div>
      <DemoRequestForm
        v-model="formData"
        @remove-wafer="waferRowRemoved"
        v-model:account-id="accountId"
        :accounts="accounts || []"
        :contacts="contacts || []"
        v-model:primary-contact-id="primaryContactId"
        :errors="errors"
        :busy="busy"
        :disable-account="mode === 'edit'"
        :show-required-marks="mode === 'create'"
        :hide-customer-information="isSelfTest"
        @create-contact="emit('create-contact', accountId)"
      />
      <label class="submit-choice"><input v-model="submitImmediately" type="checkbox" />{{ mode === 'edit' ? (locale === 'en-US' ? 'Resubmit for FAE Review after saving' : '保存后重新提交 FAE Review') : (locale === 'en-US' ? 'Submit for FAE Review after creating' : '创建后直接提交 FAE Review') }}</label>
    </template>
    <div v-else-if="mode === 'engineer'" class="form-grid">
      <label>{{ locale === 'en-US' ? 'Assessment decision' : '评估结论' }}<select v-model="review.decision"><option value="approve">{{ locale === 'en-US' ? 'Confirm feasible' : '确认可做' }}</option><option value="return">{{ locale === 'en-US' ? 'Return to Sales' : '退回 Sales' }}</option></select></label>
      <label><span>{{ locale === 'en-US' ? 'Engineer owner' : '工程负责人' }}</span><PersonnelSelect v-model="review.engineerOwner" :roles="['Engineer']" :ariaLabel="locale === 'en-US' ? 'Engineer owner' : '工程负责人'" disabled /></label>
      <label class="full"><span>{{ locale === 'en-US' ? 'Test plan' : '测试方案' }}<RequiredMark :show="review.decision === 'approve'" /></span><textarea v-model="review.testPlan" :required="review.decision === 'approve'" /></label>
      <label><span>{{ locale === 'en-US' ? 'Assigned equipment' : '分配设备' }}<RequiredMark :show="review.decision === 'approve'" /></span><input v-model="review.assignedEquipment" :required="review.decision === 'approve'" /></label>
      <label><span>{{ locale === 'en-US' ? 'Resource window' : '资源窗口' }}<RequiredMark :show="review.decision === 'approve'" /></span><input v-model="review.resourceWindow" placeholder="2026-08-01 ~ 2026-08-10" :required="review.decision === 'approve'" /></label>
      <label><span>{{ locale === 'en-US' ? 'Estimated completion' : '预计完成' }}<RequiredMark :show="review.decision === 'approve'" /></span><input v-model="review.estimatedCompletionDate" type="date" :required="review.decision === 'approve'" /></label>
      <label><span>{{ locale === 'en-US' ? 'Technical risk' : '技术风险' }}<RequiredMark :show="review.decision === 'approve'" /></span><input v-model="review.technicalRisk" :required="review.decision === 'approve'" /></label>
      <label class="full"><span>{{ locale === 'en-US' ? 'Engineer comment / return reason' : '工程意见 / 退回原因' }}<RequiredMark /></span><textarea v-model="review.comment" :aria-label="locale === 'en-US' ? 'Engineer assessment comment' : '工程评估意见'" required /></label>
    </div>
    <div v-else class="form-grid">
      <label>{{ locale === 'en-US' ? 'Approval decision' : '审批决定' }}<select v-model="review.decision"><option value="approve">{{ locale === 'en-US' ? 'Approve and convert to Demo' : '批准并转 Demo' }}</option><option value="reject">{{ locale === 'en-US' ? 'Reject Sales' : '驳回 Sales' }}</option></select></label>
      <label class="full"><span>{{ locale === 'en-US' ? 'Boss approval comment' : 'Boss 审批意见' }}<RequiredMark :show="review.decision === 'reject'" /></span><textarea v-model="review.comment" :aria-label="locale === 'en-US' ? 'Boss approval comment' : 'Boss 审批意见'" :required="review.decision === 'reject'" /></label>
    </div>
    </fieldset>
  </ModalShell>
</template>

<style scoped>
.drf-import-panel{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px 16px;padding:14px 16px;margin-bottom:14px;background:#f3f8f7;border:1px solid #cfe1dd;border-radius:10px}.drf-import-panel>div{display:grid;gap:4px}.drf-import-panel strong{color:var(--crm-navy);font-size:var(--crm-font-md)}.drf-import-panel span{color:var(--crm-text-muted);font-size:var(--crm-font-sm);line-height:1.5}.drf-import-button{display:inline-flex;align-items:center;justify-content:center;min-height:34px;padding:8px 12px;color:#fff;background:var(--crm-teal);border-radius:8px;font-size:var(--crm-font-md);font-weight:600;cursor:pointer}.drf-import-button.disabled{opacity:.55;cursor:not-allowed}.drf-import-button input{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}.drf-import-panel p{grid-column:1/-1;margin:0;color:#27794a;font-size:9px}.drf-import-panel .import-error{color:#b64545}
.form-grid,.request-meta-grid{display:grid;gap:13px}.form-grid{grid-template-columns:repeat(2,minmax(0,1fr));align-items:start}.request-meta-grid{grid-template-columns:minmax(0,1fr)}.form-grid label,.request-meta-grid label{display:grid;min-width:0;gap:6px;align-content:start;color:var(--crm-text-muted);font-size:var(--crm-font-sm);font-weight:600}.form-grid label>span,.request-meta-grid .field-label{min-height:20px;line-height:18px}.form-grid .full{grid-column:1/-1}.form-grid input,.form-grid select,.form-grid textarea,.request-meta-grid input,.request-meta-grid select{width:100%;min-width:0;min-height:38px;padding:8px 12px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:8px;outline:0;font-size:var(--crm-font-md);font-weight:400;transition:border-color .15s,box-shadow .15s}.form-grid input,.form-grid select,.request-meta-grid input,.request-meta-grid select{height:38px}.form-grid textarea{min-height:76px;resize:vertical}.form-grid input:focus,.form-grid select:focus,.form-grid textarea:focus,.request-meta-grid input:focus,.request-meta-grid select:focus{border-color:var(--crm-teal);box-shadow:0 0 0 3px color-mix(in srgb,var(--crm-teal) 12%,transparent)}.request-meta-grid small{color:var(--crm-text-muted);font-size:var(--crm-font-xs);font-weight:400}.request-meta-grid [data-field-error]{color:#b64545;font-weight:600}.submit-choice{display:flex;align-items:center;gap:8px;margin-top:14px;color:var(--crm-text-muted);font-size:9px;font-weight:700}.submit-choice input{width:16px;height:16px}@media(max-width:560px){.form-grid{grid-template-columns:1fr}.form-grid .full{grid-column:auto}}
.save-error{display:grid;gap:4px;margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:9px}.save-error small{color:var(--crm-text-muted);font-size:8px}.save-error button{justify-self:start;margin-top:4px}
.dialog-fields{display:contents;border:0;margin:0;padding:0;min-width:0}
</style>
