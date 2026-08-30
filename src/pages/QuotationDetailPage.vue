<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ArrowLeft, CheckCircle2, Download, FilePlus2, Link2, Send, ShieldCheck, ShieldX, Trash2 } from '@lucide/vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { api as defaultApi, type CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import type { ContactSummaryDto, SiteDto, Tone } from '@/types/crm'
import type { StrategyOpportunityDto } from '@/types/workspaces'
import type { QuotationApprovalDecisionInput, QuotationCatalogItemDto, QuotationDecisionInput, QuotationDetailDto, QuotationDraftInput, QuotationVersionDto } from '@/features/quotations/types'
import PageHeader from '@/design-system/PageHeader.vue'
import SectionCard from '@/design-system/SectionCard.vue'
import DataState from '@/design-system/DataState.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import ModalShell from '@/design-system/ModalShell.vue'
import QuotationEditor from '@/features/quotations/QuotationEditor.vue'
import QuotationPreview from '@/features/quotations/QuotationPreview.vue'
import QuotationHistory from '@/features/quotations/QuotationHistory.vue'
import { formatDisplayDate } from '@/domain/time'
import { downloadBlob } from '@/features/shared/download-blob'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const route = useRoute(); const router = useRouter(); const app = useAppStore()
const detail = ref<QuotationDetailDto>(); const draft = ref<QuotationDraftInput>(); const previewUrl = ref(''); const previewError = ref('')
const contacts = ref<ContactSummaryDto[]>([]); const sites = ref<SiteDto[]>([]); const contactError = ref(''); const catalog = ref<QuotationCatalogItemDto[]>([]); const catalogError = ref(''); const loading = ref(true); const denied = ref(false); const error = ref(''); const requestId = ref('')
const saveState = ref<'idle'|'saving'|'saved'|'error'>('idle'); const saveError = ref(''); const busy = ref(false); const decisionOpen = ref(false); const decision = ref<QuotationDecisionInput>({ decision:'Accepted', feedbackDate:'', feedbackNote:'' })
const approvalOpen = ref(false); const approvalDecision = ref<QuotationApprovalDecisionInput>({ decision:'Approved', comment:'' })
const linkOpen = ref(false); const linkBusy = ref(false); const linkError = ref(''); const linkOpportunityId = ref(''); const linkOpportunities = ref<StrategyOpportunityDto[]>([])
let ready = false; let previewSequence = 0; let saveTimer: ReturnType<typeof setTimeout>|undefined; let revision = 0; let savedRevision = 0; let savePromise: Promise<boolean>|undefined
const quotationId = computed(() => String(route.params.quotationId || ''))
const selectedIsLatest = computed(() => detail.value?.version.id === detail.value?.quotation.currentVersionId)
const canMutateQuotation = computed(() => Boolean(app.can('quotation:write') && !detail.value?.version.addressRestricted))
const editable = computed(() => Boolean(canMutateQuotation.value && selectedIsLatest.value && detail.value?.version.status === 'Draft' && detail.value?.version.approvalStatus !== 'Pending'))
const isSales = computed(() => app.bootstrap?.user.role === 'Sales')
const approvalPending = computed(() => selectedIsLatest.value && detail.value?.version.approvalStatus === 'Pending')
const selectedApprovals = computed(() => detail.value?.approvals.filter((item) => item.versionId === detail.value?.version.id) ?? [])
const latestApproval = computed(() => selectedApprovals.value[0])
const tone = computed<Tone>(() => detail.value?.version.status==='Accepted'?'positive':detail.value?.version.status==='Rejected'?'danger':detail.value?.version.status==='Published'?'info':detail.value?.version.status==='Expired'?'warning':'neutral')
const approvalTone = computed<Tone>(() => detail.value?.version.approvalStatus==='Approved'?'positive':detail.value?.version.approvalStatus==='Rejected'?'danger':detail.value?.version.approvalStatus==='Pending'?'warning':'neutral')
function jsonClone<T>(value: T): T { return JSON.parse(JSON.stringify(value)) as T }
function asDraft(version: QuotationVersionDto): QuotationDraftInput { return { primaryContactId:version.primaryContactId,addressId:version.addressId,quoteDate:version.quoteDate,validityMonths:version.validityMonths,items:jsonClone(version.items),discountType:version.discountType,discountValue:version.discountValue,paymentTerms:jsonClone(version.paymentTerms),deliveryMonths:version.deliveryMonths,warrantyMonths:version.warrantyMonths } }
function clearSaveTimer(){ if(saveTimer){clearTimeout(saveTimer);saveTimer=undefined} }
async function refreshPreview(versionId: string) {
  const current = ++previewSequence
  try {
    const file = await props.apiClient.getQuotationPreviewPdf(quotationId.value, versionId)
    const nextUrl = URL.createObjectURL(file.blob)
    if (current !== previewSequence) { URL.revokeObjectURL(nextUrl); return }
    const previousUrl = previewUrl.value
    previewUrl.value = nextUrl
    previewError.value = ''
    if (previousUrl) URL.revokeObjectURL(previousUrl)
  } catch (reason) {
    if (current === previewSequence) previewError.value = `PDF 预览生成失败：${mapRequestError(reason).message}`
  }
}
function applyDetail(value: QuotationDetailDto){ detail.value=value; void refreshPreview(value.version.id) }
async function loadAllContacts(accountId: string) {
  const items: ContactSummaryDto[] = []; let page = 1; let totalRows = 0
  do {
    const result = await props.apiClient.listContacts({ accountId, contactStatus:'Active', page, pageSize:200 })
    items.push(...result.data.items); totalRows = result.meta?.total ?? items.length; page += 1
    if (!result.data.items.length) break
  } while (items.length < totalRows)
  return items
}
async function loadReferences(accountId: string) {
  const referenceErrors: string[] = []
  sites.value = []
  contacts.value = []
  try {
    sites.value = (await props.apiClient.getAccount360(accountId)).data.sites
  } catch (reason) {
    const mapped = mapRequestError(reason)
    referenceErrors.push(`客户站点加载失败：${mapped.message}${mapped.requestId ? `（Request ID: ${mapped.requestId}）` : ''}`)
  }
  try {
    contacts.value = await loadAllContacts(accountId)
  } catch (reason) {
    const mapped = mapRequestError(reason)
    referenceErrors.push(`联系人加载失败：${mapped.message}${mapped.requestId ? `（Request ID: ${mapped.requestId}）` : ''}`)
  }
  contactError.value = referenceErrors.join('；')
}
async function loadCatalog() {
  catalogError.value = ''
  try { catalog.value = (await props.apiClient.listQuotationCatalog()).data }
  catch (reason) { catalog.value = []; catalogError.value = `设备目录加载失败：${mapRequestError(reason).message}` }
}async function load(versionId?: string) {
  clearSaveTimer(); loading.value = true; error.value = ''; requestId.value = ''; denied.value = false; contactError.value = ''; ready = false; revision = 0; savedRevision = 0
  try {
    const result = await props.apiClient.getQuotation(quotationId.value, versionId); applyDetail(result.data); draft.value = asDraft(result.data.version)
    if (result.data.version.quotationType === 'Device') await loadCatalog()
    else { catalog.value = []; catalogError.value = '' }
    if (!versionId || versionId === result.data.quotation.currentVersionId) {
      await loadReferences(result.data.quotation.accountId)
    } else {
      sites.value = []
      contacts.value = []
    }
    await nextTick(); ready = true
  } catch(reason) { const mapped=mapRequestError(reason); error.value=mapped.message; requestId.value=mapped.requestId; denied.value=mapped.denied }
  finally { loading.value=false }
}
async function persistDraft(): Promise<boolean> {
  if (!editable.value || !draft.value || !detail.value || savedRevision >= revision) return true
  if (savePromise) return savePromise
  savePromise = (async () => {
    while (editable.value && draft.value && detail.value && savedRevision < revision) {
      const sentRevision = revision; saveState.value='saving'; saveError.value=''
      try {
        const result=await props.apiClient.saveQuotationDraft(quotationId.value, jsonClone(draft.value), detail.value.version.modified)
        applyDetail(result.data); savedRevision=sentRevision
        if(revision===sentRevision) draft.value=asDraft(result.data.version)
      } catch(reason) {
        const mapped=mapRequestError(reason); saveState.value='error'; saveError.value=mapped.message; return false
      }
    }
    saveState.value='saved'; return true
  })().finally(() => { savePromise=undefined })
  return savePromise
}
function scheduleSave(){ if(!ready || !editable.value)return; revision+=1; saveState.value='idle'; clearSaveTimer(); saveTimer=setTimeout(()=>{saveTimer=undefined;void persistDraft()},1000) }
async function flushPendingSave(){ clearSaveTimer(); return persistDraft() }
async function publish(){ if(!detail.value)return; busy.value=true; saveError.value=''; try{ if(!await flushPendingSave())return; applyDetail((await props.apiClient.publishQuotation(quotationId.value,detail.value!.version.modified)).data); draft.value=asDraft(detail.value!.version); revision=savedRevision; await loadCatalog() }catch(reason){saveError.value=mapRequestError(reason).message}finally{busy.value=false} }
async function submitApproval(){ if(!detail.value)return; busy.value=true; saveError.value=''; try{ if(!await flushPendingSave())return; applyDetail((await props.apiClient.submitQuotationForApproval(quotationId.value,detail.value!.version.modified)).data);draft.value=asDraft(detail.value!.version);revision=savedRevision;await loadCatalog() }catch(reason){saveError.value=mapRequestError(reason).message}finally{busy.value=false} }
function openApproval(decisionValue: 'Approved'|'Rejected'){ approvalDecision.value={decision:decisionValue,comment:''};approvalOpen.value=true }
async function reviewApproval(){ if(!detail.value)return;busy.value=true;saveError.value='';try{applyDetail((await props.apiClient.reviewQuotationApproval(quotationId.value,{...approvalDecision.value,expectedModified:detail.value.version.modified})).data);draft.value=asDraft(detail.value!.version);approvalOpen.value=false}catch(reason){saveError.value=mapRequestError(reason).message}finally{busy.value=false} }
async function createVersion(){ busy.value=true; try{ applyDetail((await props.apiClient.createQuotationVersion(quotationId.value)).data); draft.value=asDraft(detail.value!.version); revision=0;savedRevision=0;await nextTick();ready=true }catch(reason){saveError.value=mapRequestError(reason).message}finally{busy.value=false} }
async function discard(){ busy.value=true; clearSaveTimer(); try{ if(savePromise)await savePromise;revision=savedRevision;const result=await props.apiClient.discardQuotationDraft(quotationId.value,detail.value!.version.modified);if('deleted' in result.data){ready=false;await router.push('/quotations')}else{applyDetail(result.data);draft.value=asDraft(result.data.version)} }catch(reason){saveError.value=mapRequestError(reason).message}finally{busy.value=false} }
async function selectVersion(versionId:string){ if(editable.value&&!await flushPendingSave())return;await load(versionId) }
async function submitDecision(){ busy.value=true; try{ applyDetail((await props.apiClient.recordQuotationDecision(quotationId.value,{...decision.value,expectedModified:detail.value!.version.modified})).data);decisionOpen.value=false }catch(reason){saveError.value=mapRequestError(reason).message}finally{busy.value=false} }
async function loadLinkOpportunities(){
  if(!detail.value)return
  const candidates: StrategyOpportunityDto[]=[]; const quoted=new Set<string>(); let opportunityPage=1; let opportunityTotal=0; let quotationPage=1; let quotationTotal=0
  do { const result=await props.apiClient.listStrategyOpportunities({accountId:detail.value.quotation.accountId,page:opportunityPage,pageSize:200}); candidates.push(...result.data.items); opportunityTotal=result.meta?.total??candidates.length; opportunityPage+=1; if(!result.data.items.length)break } while(candidates.length<opportunityTotal)
  do { const result=await props.apiClient.listQuotations({page:quotationPage,pageSize:200}); result.data.items.forEach((item)=>{if(item.opportunityId)quoted.add(item.opportunityId)}); quotationTotal=result.meta?.total??quoted.size; quotationPage+=1; if(!result.data.items.length)break } while((quotationPage-1)*200<quotationTotal)
  linkOpportunities.value=candidates.filter((item)=>item.accountId===detail.value?.quotation.accountId&&!quoted.has(item.id))
}
async function openOpportunityLink(){
  if(!detail.value||detail.value.quotation.opportunityId)return
  if(editable.value&&!await flushPendingSave())return
  linkBusy.value=true; linkError.value=''; linkOpportunityId.value=''
  try{await loadLinkOpportunities();linkOpen.value=true}catch(reason){const mapped=mapRequestError(reason);linkError.value=`${mapped.message}${mapped.requestId?`（Request ID: ${mapped.requestId}）`:''}`;linkOpen.value=true}finally{linkBusy.value=false}
}
async function linkOpportunity(){
  if(!detail.value||!linkOpportunityId.value)return
  linkBusy.value=true;linkError.value=''
  try{const result=await props.apiClient.linkQuotationOpportunity(quotationId.value,linkOpportunityId.value,detail.value.version.modified);applyDetail(result.data);draft.value=asDraft(result.data.version);linkOpen.value=false}catch(reason){const mapped=mapRequestError(reason);linkError.value=`${mapped.message}${mapped.requestId?`（Request ID: ${mapped.requestId}）`:''}`}finally{linkBusy.value=false}
}
async function download(versionId?:string){ try{ const file=await props.apiClient.getQuotationPdf(quotationId.value,versionId); downloadBlob(file.blob,file.fileName) }catch(reason){saveError.value=mapRequestError(reason).message} }
async function refreshCurrentIfClean(){
  if(!ready || !detail.value || revision>savedRevision || saveTimer || savePromise)return
  const requestedRevision=revision
  try {
    const result=await props.apiClient.getQuotation(quotationId.value,detail.value.version.id)
    if(!ready || revision!==requestedRevision || revision>savedRevision || saveTimer || savePromise)return
    applyDetail(result.data); draft.value=asDraft(result.data.version)
  }
  catch(reason){ saveError.value=mapRequestError(reason).message }
}
function handleVisibility(){ if(document.visibilityState==='visible')void refreshCurrentIfClean() }
onMounted(async()=>{window.addEventListener('focus',refreshCurrentIfClean);document.addEventListener('visibilitychange',handleVisibility);await app.loadBootstrap(props.apiClient);await load()})
onBeforeRouteLeave(async()=>{if(!ready||!editable.value)return true;return await flushPendingSave()})
onBeforeUnmount(()=>{ready=false;previewSequence+=1;window.removeEventListener('focus',refreshCurrentIfClean);document.removeEventListener('visibilitychange',handleVisibility);clearSaveTimer();if(previewUrl.value)URL.revokeObjectURL(previewUrl.value)})
</script>
<template>
  <div class="quotation-detail-page" :data-editable="editable">
    <PageHeader v-if="detail" eyebrow="QUOTATION DETAIL" :title="detail.quotation.refNo" :description="`${detail.quotation.accountName} · V${detail.version.version}`">
      <template #default>
        <button class="secondary-button" type="button" @click="router.push('/quotations')"><ArrowLeft :size="14" />返回列表</button>
        <button v-if="detail.version.pdfAvailable" class="secondary-button" data-testid="download-quotation-pdf" type="button" @click="download(detail.version.id)"><Download :size="14" />下载 PDF</button>
        <button v-if="selectedIsLatest && !detail.quotation.opportunityId && canMutateQuotation" class="secondary-button" data-testid="link-quotation-opportunity" type="button" :disabled="busy || linkBusy" @click="openOpportunityLink"><Link2 :size="14" />关联 Opportunity</button>
        <button v-if="editable" class="danger-button" type="button" :disabled="busy" @click="discard"><Trash2 :size="14" />放弃草稿</button>
        <button v-if="editable && isSales && app.can('quotation:submit')" class="primary-button" data-testid="submit-quotation-approval" type="button" :disabled="busy" @click="submitApproval"><Send :size="14" />提交 Manager 审批</button>
        <button v-if="editable && !isSales && app.can('quotation:publish')" class="primary-button" data-testid="publish-quotation" type="button" :disabled="busy" @click="publish"><Send :size="14" />直接发布正式版本</button>
        <button v-if="approvalPending && app.can('quotation:approve')" class="primary-button" data-testid="approve-quotation" type="button" :disabled="busy" @click="openApproval('Approved')"><ShieldCheck :size="14" />批准并发布</button>
        <button v-if="approvalPending && app.can('quotation:approve')" class="danger-button" data-testid="reject-quotation" type="button" :disabled="busy" @click="openApproval('Rejected')"><ShieldX :size="14" />驳回</button>
        <button v-if="selectedIsLatest && detail.version.status!=='Draft' && canMutateQuotation" class="primary-button" type="button" @click="createVersion"><FilePlus2 :size="14" />创建新版本</button>
        <button v-if="selectedIsLatest && ['Published','Expired'].includes(detail.version.status) && canMutateQuotation" class="secondary-button" type="button" @click="decisionOpen=true"><CheckCircle2 :size="14" />记录客户结果</button>
      </template>
    </PageHeader>
    <DataState v-if="loading" type="loading" />
    <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
    <DataState v-else-if="error||!detail||!draft" type="error" :message="error||'报价单加载失败'" :request-id="requestId" @retry="load()" />
    <template v-else>
      <section class="summary-strip">
        <div><small>Name</small><strong>{{ detail.quotation.refNo }}</strong><span>{{ detail.quotation.accountName }}</span></div>
        <div><small>Type</small><strong>{{ detail.version.quotationType }}</strong><span>{{ detail.version.quotationType === 'Service' ? '售后 / 维修 / 配件' : '设备报价' }}</span></div>
        <div><small>Source</small><strong>{{ detail.quotation.opportunityTitle || 'Others' }}</strong><span>{{ detail.quotation.opportunityId || detail.quotation.accountId }}</span></div>
        <div><small>上一次修改日期</small><strong>{{ formatDisplayDate(detail.version.modified) }}</strong><span>V{{ detail.version.version }}</span></div>
        <div><small>Status</small><StatusBadge :label="detail.version.status" :tone="tone" /><StatusBadge :label="detail.version.approvalStatus" :tone="approvalTone" /></div>
      </section>
      <div v-if="editable" class="save-line" :class="saveState">
        <span v-if="saveState==='saving'">正在保存并刷新预览…</span>
        <span v-else-if="saveState==='saved'">已保存，预览已同步</span>
        <span v-else-if="saveState==='error'">{{ saveError }}；预览保留上一次成功版本</span>
        <span v-else>编辑后约 1 秒自动保存</span>
      </div>
      <p v-else-if="!selectedIsLatest" class="history-notice">当前正在查看历史版本，仅可查看和下载。</p>
      <p v-else-if="approvalPending" class="approval-notice">当前版本正在等待 Manager 审批，审批完成前不可修改或发布。</p>
      <p v-else-if="detail.version.addressRestricted" class="history-notice" data-testid="quotation-address-restricted">客户地址仅 Account 负责人或 Manager 可见；当前报价为只读。</p>
      <p v-else-if="detail.version.approvalStatus==='Rejected'" class="rejection-notice">Manager 已驳回：{{ latestApproval?.comment || '未填写原因' }}。修改后可重新提交审批。</p>
      <p v-if="saveError && saveState!=='error'" class="form-error">{{ saveError }}</p>
      <div class="detail-grid">
        <p v-if="contactError" class="form-error">{{ contactError }}</p>
        <QuotationEditor v-model="draft" :contacts="contacts" :sites="sites" :quotation-type="detail.version.quotationType" :catalog="catalog" :catalog-error="catalogError" :readonly="!editable" @update:model-value="scheduleSave" />
        <aside>
          <SectionCard title="报价单预览" eyebrow="LIVE PDF"><QuotationPreview v-if="previewUrl" :src="previewUrl" /><p v-else class="form-error">{{ previewError || '正在生成 PDF 预览…' }}</p></SectionCard>
          <SectionCard title="历史版本" eyebrow="VERSION ARCHIVE"><QuotationHistory :versions="detail.versions" :selected-id="detail.version.id" @select="selectVersion" @download="download" /></SectionCard>
          <SectionCard v-if="selectedApprovals.length" title="审批记录" eyebrow="APPROVAL HISTORY">
            <div class="approval-history"><div v-for="item in selectedApprovals" :key="item.id"><strong>第 {{ item.attempt }} 次 · {{ item.status }}</strong><small>{{ item.decidedBy || item.submittedBy }} · {{ formatDisplayDate(item.decidedAt || item.submittedAt) }}</small><p v-if="item.comment">{{ item.comment }}</p></div></div>
          </SectionCard>
        </aside>
      </div>
    </template>
    <ModalShell v-if="decisionOpen" title="记录客户结果" eyebrow="CUSTOMER FEEDBACK" :busy="busy" :submit-disabled="!decision.feedbackDate||!decision.feedbackNote.trim()" @close="decisionOpen=false" @submit="submitDecision">
      <div class="decision-form">
        <label><span>结果</span><select v-model="decision.decision"><option>Accepted</option><option>Rejected</option></select></label>
        <label><span>反馈日期</span><input v-model="decision.feedbackDate" type="date" /></label>
        <label class="wide"><span>反馈说明</span><textarea v-model="decision.feedbackNote" /></label>
      </div>
    </ModalShell>
    <ModalShell v-if="approvalOpen" :title="approvalDecision.decision==='Approved'?'批准报价并发布':'驳回报价'" eyebrow="MANAGER APPROVAL" :busy="busy" :submit-disabled="approvalDecision.decision==='Rejected'&&!approvalDecision.comment.trim()" @close="approvalOpen=false" @submit="reviewApproval">
      <div class="decision-form"><label class="wide"><span>{{ approvalDecision.decision==='Rejected'?'驳回原因（必填）':'审批意见（选填）' }}</span><textarea v-model="approvalDecision.comment" maxlength="1000" /></label></div>
    </ModalShell>
    <ModalShell v-if="linkOpen" title="关联 Opportunity" eyebrow="QUOTATION SOURCE" :busy="linkBusy" :submit-disabled="!linkOpportunityId" @close="linkOpen=false" @submit="linkOpportunity">
      <p v-if="linkError" class="form-error">{{ linkError }}</p>
      <p v-if="!linkBusy && !linkError && !linkOpportunities.length" class="history-notice">当前 Account 没有可关联的 Opportunity。</p>
      <div class="decision-form"><label class="wide"><span>Opportunity</span><select v-model="linkOpportunityId" data-testid="link-opportunity-select"><option value="">请选择 Opportunity</option><option v-for="item in linkOpportunities" :key="item.id" :value="item.id">{{ item.title }} · {{ item.id }}</option></select></label></div>
    </ModalShell>
  </div>
</template>
<style scoped>
.quotation-detail-page{display:grid;gap:14px}.summary-strip{display:grid;grid-template-columns:1.1fr .8fr 1.7fr 1fr .9fr;gap:0;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.summary-strip>div{display:grid;align-content:center;min-height:80px;padding:13px 16px;border-right:1px solid var(--crm-line)}.summary-strip>div:last-child{border-right:0}.summary-strip small,.summary-strip span{color:var(--crm-muted);font-size:10px}.summary-strip strong{margin:4px 0;color:var(--crm-navy);font-size:13px}.summary-strip :deep(.status-badge + .status-badge){margin-left:5px}.detail-grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(380px,.75fr);align-items:start;gap:14px}.detail-grid aside{position:sticky;top:12px;display:grid;gap:12px;max-height:calc(100vh - 24px);overflow:auto}.save-line,.history-notice,.approval-notice,.rejection-notice,.form-error{margin:0;padding:9px 12px;font-size:11px;border-radius:8px}.save-line{color:#44676a;background:#eef6f5}.save-line.saving,.approval-notice{color:#7c641b;background:#fff7e5}.save-line.error,.rejection-notice,.form-error{color:#a63c3c;background:#fff0ef}.history-notice{color:#5b6575;background:#f0f2f5}.approval-history{display:grid;gap:8px}.approval-history>div{display:grid;gap:3px;padding:9px;border-bottom:1px solid var(--crm-line)}.approval-history small{color:var(--crm-muted)}.approval-history p{margin:2px 0 0;font-size:11px}.decision-form{display:grid;grid-template-columns:1fr 1fr;gap:12px}.decision-form label{display:grid;gap:5px}.decision-form .wide{grid-column:span 2}.decision-form input,.decision-form select,.decision-form textarea{min-height:38px;padding:8px;border:1px solid var(--crm-line);border-radius:7px}.decision-form textarea{min-height:90px}@media(max-width:1180px){.detail-grid{grid-template-columns:1fr}.detail-grid aside{position:static;max-height:none}.summary-strip{grid-template-columns:1fr 1fr}}@media(max-width:650px){.summary-strip{grid-template-columns:1fr}.summary-strip>div{border-right:0;border-bottom:1px solid var(--crm-line)}}
</style>
