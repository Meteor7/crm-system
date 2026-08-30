<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { api as defaultApi, type CrmApi } from '@/api'
import type { AccountSummaryDto, ContactSummaryDto, CreateDemoRequestInput, DemoRequestCommand, DemoRequestDto, DemoRequestFormData } from '@/types/crm'
import type { StrategyOpportunityDto } from '@/types/workspaces'
import { applyDemoRequestImport, cloneDemoRequestFormData, createEmptyDemoRequestFormData, getDemoRequestFormData, validateDemoRequestFormData } from '@/domain/demo-request-form'
import { mapRequestError } from '@/api/request-state'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import DemoRequestForm from './DemoRequestForm.vue'

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
}>()
const emit = defineEmits<{ close: []; submit: [payload: CreateDemoRequestInput | DemoRequestCommand]; 'create-contact': [accountId: string] }>()

const accountId = ref('')
const opportunityId = ref('')
const SELF_TEST_OPTION = '__SELF_TEST__'
const opportunitySearch = ref('')
const loadedOpportunities = ref<StrategyOpportunityDto[]>([])
const opportunityLoading = ref(false)
const primaryContactId = ref('')
const formData = ref<DemoRequestFormData>(createEmptyDemoRequestFormData())
const errors = ref<Record<string, string>>({})
const submitImmediately = ref(true)
const customerExpectedDate = ref('')
const importBusy = ref(false)
const importError = ref('')
const importNotice = ref('')
const isSelfTest = computed(() => opportunityId.value === SELF_TEST_OPTION)
const review = reactive({ decision: 'approve', engineerOwner: '', testPlan: '', assignedEquipment: '', resourceWindow: '', estimatedCompletionDate: '2026-08-15', technicalRisk: '', comment: '' })

const opportunityOptions = computed(() => {
  const source = props.opportunities ?? loadedOpportunities.value
  const search = opportunitySearch.value.trim().toLocaleLowerCase()
  return source.filter((item) => item.accountId === accountId.value
    && (item.id === props.request?.opportunityId || item.stage === '需求发现' || item.stage === 'Wafer Demo确认')
    && (!search || `${item.id} ${item.title}`.toLocaleLowerCase().includes(search)))
})

let opportunityRequest = 0
async function loadOpportunities() {
  if (props.opportunities || !accountId.value || (props.mode !== 'create' && props.mode !== 'edit')) return
  const request = ++opportunityRequest
  opportunityLoading.value = true
  try {
    const query = { accountId: accountId.value, search: opportunitySearch.value.trim(), page: 1, pageSize: 20 }
    const results = await Promise.all([
      (props.apiClient || defaultApi).listStrategyOpportunities({ ...query, status: '需求发现' }),
      (props.apiClient || defaultApi).listStrategyOpportunities({ ...query, status: 'Wafer Demo确认' }),
    ])
    if (request !== opportunityRequest) return
    const eligible = results.flatMap((result) => result.data.items)
    if (props.request?.opportunityId && !eligible.some((item) => item.id === props.request?.opportunityId)) {
      const linked = await (props.apiClient || defaultApi).getStrategyOpportunity(props.request.opportunityId)
      if (request !== opportunityRequest) return
      eligible.unshift(linked.data)
    }
    loadedOpportunities.value = Array.from(new Map(eligible.map((item) => [item.id, item])).values())
  } catch (reason) {
    if (request === opportunityRequest) errors.value.opportunityId = mapRequestError(reason).message
  } finally {
    if (request === opportunityRequest) opportunityLoading.value = false
  }
}

watch(() => [props.mode, props.request, props.accounts, props.currentSalesContact] as const, () => {
  accountId.value = props.request?.accountId || props.accounts?.[0]?.id || ''
  opportunityId.value = props.request?.requestMode === 'Self Test' ? SELF_TEST_OPTION : props.request?.opportunityId || ''
  primaryContactId.value = props.request?.primaryContactId || props.selectedContactId || ''
  formData.value = props.request
    ? getDemoRequestFormData(props.request)
    : createEmptyDemoRequestFormData(props.currentSalesContact || '')
  errors.value = {}
  submitImmediately.value = true
  customerExpectedDate.value = props.request?.customerExpectedDate || ''
  review.decision = 'approve'
  review.engineerOwner = props.request?.engineerOwner || ''
  review.testPlan = props.request?.testPlan || ''
  review.assignedEquipment = props.request?.assignedEquipment || props.request?.requestedEquipment || ''
  review.resourceWindow = props.request?.resourceWindow || ''
  review.estimatedCompletionDate = props.request?.estimatedCompletionDate || props.request?.targetDate || '2026-08-15'
  review.technicalRisk = props.request?.technicalRisk || ''
  review.comment = ''
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

async function importCompletedForm(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  importError.value = ''
  importNotice.value = ''
  if (!/\.(pdf|docx)$/i.test(file.name)) {
    importError.value = '仅支持 PDF 或 Word（.docx）文件'
    input.value = ''
    return
  }
  if (!file.size || file.size > 100 * 1024 * 1024) {
    importError.value = '文件不能为空且不能超过 100 MiB'
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
    const applied = applyDemoRequestImport(
      formData.value,
      response.data,
      props.accounts || [],
      props.contacts || [],
    )
    formData.value = applied.formData
    if (applied.accountId) accountId.value = applied.accountId
    if (applied.primaryContactId) primaryContactId.value = applied.primaryContactId
    if (applied.customerExpectedDate) customerExpectedDate.value = applied.customerExpectedDate
    errors.value = {}
    importNotice.value = `已从 ${response.data.fileName} 识别并回填 ${response.data.detectedFields.length} 个字段，请检查后再保存。`
  } catch (reason) {
    importError.value = mapRequestError(reason).message
  } finally {
    importBusy.value = false
    input.value = ''
  }
}

function submit() {
  if (props.mode === 'create' || props.mode === 'edit') {
    errors.value = validateDemoRequestFormData(formData.value, { requireCustomerInformation: !isSelfTest.value })
    if (!isSelfTest.value && !primaryContactId.value) errors.value.primaryContactId = '请选择主要联系人'
    if (!opportunityId.value) errors.value.opportunityId = '请选择关联 Opportunity 或自测'
    if (!customerExpectedDate.value) errors.value.customerExpectedDate = '请填写客户期望时间'
    if (Object.keys(errors.value).length) return
    emit('submit', {
      accountId: isSelfTest.value ? '' : accountId.value,
      opportunityId: opportunityId.value === SELF_TEST_OPTION ? undefined : opportunityId.value,
      requestMode: opportunityId.value === SELF_TEST_OPTION ? 'Self Test' : 'Opportunity',
      primaryContactId: primaryContactId.value,
      formData: cloneDemoRequestFormData(formData.value),
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
</script>

<template>
  <ModalShell
    :title="mode === 'create' ? '新建 Demo Request' : mode === 'edit' ? '修改 Demo Request' : mode === 'engineer' ? 'FAE Review' : 'Boss Approval'"
    :eyebrow="mode === 'create' || mode === 'edit' ? 'DEMO REQUEST FORM' : mode === 'engineer' ? 'FAE REVIEW' : 'BOSS APPROVAL'"
    :busy="busy"
    :wide="mode === 'create' || mode === 'edit'"
    @close="$emit('close')"
    @submit="submit"
  >
    <template v-if="mode === 'create' || mode === 'edit'">
      <section class="drf-import-panel" data-demo-request-import>
        <div>
          <strong>导入已填写的 DRF</strong>
          <span>支持 PDF 和 Word（.docx），自动识别后回填当前表单，不会自动提交。</span>
        </div>
        <label class="drf-import-button" :class="{ disabled: importBusy || busy }">
          {{ importBusy ? '正在识别…' : '选择文件并识别' }}
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
        <label>关联 Opportunity / 自测<RequiredMark :show="mode === 'create'" />
          <input v-model="opportunitySearch" aria-label="搜索 Opportunity" type="search" placeholder="按编号或名称搜索" />
          <select v-model="opportunityId" aria-label="关联 Opportunity" required :disabled="mode === 'edit' || opportunityLoading">
            <option value="">{{ opportunityLoading ? '正在读取…' : '请选择 Opportunity 或自测' }}</option>
            <option :value="SELF_TEST_OPTION">自测（无需关联 Opportunity）</option>
            <option v-for="opportunity in opportunityOptions" :key="opportunity.id" :value="opportunity.id">
              {{ opportunity.id }} · {{ opportunity.title }} · {{ opportunity.stage }}
            </option>
          </select>
          <small v-if="errors.opportunityId" data-field-error="opportunityId">{{ errors.opportunityId }}</small>
        </label>
        <label>客户期望时间<RequiredMark :show="mode === 'create'" />
          <input v-model="customerExpectedDate" aria-label="客户期望时间" type="date" required />
          <small>仅用于系统排期与沟通，不写入 Demo Request Word</small>
          <small v-if="errors.customerExpectedDate" data-field-error="customerExpectedDate">{{ errors.customerExpectedDate }}</small>
        </label>
      </div>
      <DemoRequestForm
        v-model="formData"
        v-model:account-id="accountId"
        :accounts="accounts || []"
        :contacts="contacts || []"
        v-model:primary-contact-id="primaryContactId"
        :errors="errors"
        :disable-account="mode === 'edit'"
        :show-required-marks="mode === 'create'"
        :hide-customer-information="isSelfTest"
        @create-contact="emit('create-contact', accountId)"
      />
      <label class="submit-choice"><input v-model="submitImmediately" type="checkbox" />{{ mode === 'edit' ? '保存后重新提交 FAE Review' : '创建后直接提交 FAE Review' }}</label>
    </template>
    <div v-else-if="mode === 'engineer'" class="form-grid">
      <label>评估结论<select v-model="review.decision"><option value="approve">确认可做</option><option value="return">退回 Sales</option></select></label>
      <label class="full">测试方案<textarea v-model="review.testPlan" /></label>
      <label>分配设备<input v-model="review.assignedEquipment" /></label>
      <label>资源窗口<input v-model="review.resourceWindow" placeholder="2026-08-01 ~ 2026-08-10" /></label>
      <label>预计完成<input v-model="review.estimatedCompletionDate" type="date" /></label>
      <label>技术风险<input v-model="review.technicalRisk" /></label>
      <label class="full">工程意见 / 退回原因<textarea v-model="review.comment" aria-label="工程评估意见" /></label>
    </div>
    <div v-else class="form-grid">
      <label>审批决定<select v-model="review.decision"><option value="approve">批准并转 Demo</option><option value="reject">驳回 Sales</option></select></label>
      <label class="full">Boss 审批意见<textarea v-model="review.comment" aria-label="Boss 审批意见" /></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.drf-import-panel{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px 16px;padding:14px 16px;margin-bottom:14px;background:#f3f8f7;border:1px solid #cfe1dd;border-radius:10px}.drf-import-panel>div{display:grid;gap:4px}.drf-import-panel strong{color:var(--crm-navy);font-size:11px}.drf-import-panel span{color:var(--crm-text-muted);font-size:9px;line-height:1.5}.drf-import-button{display:inline-flex;align-items:center;justify-content:center;min-height:34px;padding:8px 12px;color:#fff;background:var(--crm-teal);border-radius:8px;font-size:9px;font-weight:800;cursor:pointer}.drf-import-button.disabled{opacity:.55;cursor:not-allowed}.drf-import-button input{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}.drf-import-panel p{grid-column:1/-1;margin:0;color:#27794a;font-size:9px}.drf-import-panel .import-error{color:#b64545}
.form-grid,.request-meta-grid{display:grid;gap:13px}.form-grid{grid-template-columns:1fr 1fr}.request-meta-grid{grid-template-columns:1fr}.form-grid label,.request-meta-grid label{display:grid;gap:6px;color:var(--crm-text-muted);font-size:9px;font-weight:700}.form-grid .full{grid-column:1/-1}.form-grid input,.form-grid select,.form-grid textarea,.request-meta-grid input,.request-meta-grid select{width:100%;min-height:36px;padding:8px 10px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:8px;outline:0}.form-grid textarea{min-height:76px;resize:vertical}.form-grid input:focus,.form-grid select:focus,.form-grid textarea:focus,.request-meta-grid input:focus,.request-meta-grid select:focus{border-color:var(--crm-teal)}.request-meta-grid small{color:#9aa6a8;font-size:8px;font-weight:400}.request-meta-grid [data-field-error]{color:#b64545;font-weight:600}.submit-choice{display:flex;align-items:center;gap:8px;margin-top:14px;color:var(--crm-text-muted);font-size:9px;font-weight:700}.submit-choice input{width:16px;height:16px}@media(max-width:560px){.form-grid{grid-template-columns:1fr}.form-grid .full{grid-column:auto}}
</style>
