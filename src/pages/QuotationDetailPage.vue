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
import { useI18n, useLocaleMessage, localeMessage } from '@/i18n'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const route = useRoute(); const router = useRouter(); const app = useAppStore()
const { locale, message } = useI18n()
const ui = (english: string, chinese: string) => localeMessage(english, chinese)[locale.value]
const detail = ref<QuotationDetailDto>(); const draft = ref<QuotationDraftInput>(); const previewUrl = ref(''); const previewError = useLocaleMessage()
const contacts = ref<ContactSummaryDto[]>([]); const sites = ref<SiteDto[]>([]); const contactError = useLocaleMessage(); const catalog = ref<QuotationCatalogItemDto[]>([]); const catalogError = useLocaleMessage(); const loading = ref(true); const denied = ref(false); const error = useLocaleMessage(); const requestId = ref('')
const saveState = ref<'idle'|'saving'|'saved'|'error'>('idle'); const saveError = useLocaleMessage(); const busy = ref(false); const decisionOpen = ref(false); const decision = ref<QuotationDecisionInput>({ decision:'Accepted', feedbackDate:'', feedbackNote:'' })
const approvalOpen = ref(false); const approvalDecision = ref<QuotationApprovalDecisionInput>({ decision:'Approved', comment:'' })
const linkOpen = ref(false); const linkBusy = ref(false); const linkError = useLocaleMessage(); const linkOpportunityId = ref(''); const linkOpportunities = ref<StrategyOpportunityDto[]>([])
let ready = false; let previewSequence = 0; let saveTimer: ReturnType<typeof setTimeout>|undefined; let revision = 0; let savedRevision = 0; let savePromise: Promise<boolean>|undefined
const quotationId = computed(() => String(route.params.quotationId || ''))
const linkedVersion = computed(() => typeof route.query.version === 'string' ? route.query.version : undefined)
const selectedIsLatest = computed(() => detail.value?.version.id === detail.value?.quotation.currentVersionId)
const canMutateQuotation = computed(() => Boolean(app.can('quotation:write') && !detail.value?.version.addressRestricted))
const editable = computed(() => Boolean(canMutateQuotation.value && selectedIsLatest.value && detail.value?.version.status === 'Draft' && detail.value?.version.approvalStatus !== 'Pending'))
const isSales = computed(() => app.bootstrap?.user.role === 'Sales')
const approvalPending = computed(() => selectedIsLatest.value && detail.value?.version.approvalStatus === 'Pending')
const selectedApprovals = computed(() => detail.value?.approvals.filter((item) => item.versionId === detail.value?.version.id) ?? [])
// A draft that has been through approval keeps its approval record: it is revised and submitted again, not discarded.
const canDiscard = computed(() => editable.value && !selectedApprovals.value.length)
const latestApproval = computed(() => selectedApprovals.value[0])
const tone = computed<Tone>(() => detail.value?.version.status==='Accepted'?'positive':detail.value?.version.status==='Rejected'?'danger':detail.value?.version.status==='Published'?'info':detail.value?.version.status==='Expired'?'warning':'neutral')
const approvalTone = computed<Tone>(() => detail.value?.version.approvalStatus==='Approved'?'positive':detail.value?.version.approvalStatus==='Rejected'?'danger':detail.value?.version.approvalStatus==='Pending'?'warning':'neutral')
function quotationStatusLabel(value: QuotationVersionDto['status']) { return ({ Draft: ui('Draft', '草稿'), Published: ui('Published', '已发布'), Accepted: ui('Accepted', '已接受'), Rejected: ui('Rejected', '已驳回'), Expired: ui('Expired', '已过期'), Superseded: ui('Superseded', '已被替代') }[value]) }
function approvalStatusLabel(value: QuotationVersionDto['approvalStatus']) { return ({ 'Not Submitted': ui('Not submitted', '未提交'), Pending: ui('Pending', '待审批'), Approved: ui('Approved', '已批准'), Rejected: ui('Rejected', '已驳回'), 'Not Required': ui('Not required', '无需审批') }[value]) }
function quotationTypeLabel(value: QuotationVersionDto['quotationType']) { return value === 'Device' ? ui('Device', '设备') : ui('Service', '服务') }
function decisionLabel(value: 'Accepted' | 'Rejected') { return value === 'Accepted' ? ui('Accepted', '已接受') : ui('Rejected', '已驳回') }
function mappedMessage(mapped: ReturnType<typeof mapRequestError>) { return mapped.localizedMessage ?? mapped.message }
function messageWithError(key: string, mapped: ReturnType<typeof mapRequestError>): Record<'en-US' | 'zh-CN', string> {
  const detailMessage = mappedMessage(mapped)
  const formatted = typeof detailMessage === 'string'
    ? (() => {
      const translated = message(key, { error: detailMessage })
      return localeMessage(translated['en-US'], translated['zh-CN'])
    })()
    : localeMessage(
      message(key, { error: detailMessage['en-US'] })['en-US'],
      message(key, { error: detailMessage['zh-CN'] })['zh-CN'],
    )
  if (!mapped.requestId) return formatted
  return localeMessage(
    `${formatted['en-US']} (Request ID: ${mapped.requestId})`,
    `${formatted['zh-CN']}（Request ID: ${mapped.requestId}）`,
  )
}
function messageWithRequestId(mapped: ReturnType<typeof mapRequestError>) {
  const detailMessage = mappedMessage(mapped)
  if (!mapped.requestId) return detailMessage
  if (typeof detailMessage === 'string') return `${detailMessage} (Request ID: ${mapped.requestId})`
  return localeMessage(
    `${detailMessage['en-US']} (Request ID: ${mapped.requestId})`,
    `${detailMessage['zh-CN']}（Request ID: ${mapped.requestId}）`,
  )
}
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
    if (current === previewSequence) previewError.value = messageWithError('quotationDetail.previewFailed', mapRequestError(reason))
  }
}
// Counts every state the page has shown. A background refresh that was asked for under an older
// state must not replace a newer one (a discarded draft, a submitted or published version).
let detailEpoch = 0
function applyDetail(value: QuotationDetailDto){ detailEpoch+=1; detail.value=value; void refreshPreview(value.version.id) }
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
  const referenceErrors: ReturnType<typeof message>[] = []
  sites.value = []
  contacts.value = []
  try {
    sites.value = (await props.apiClient.getAccount360(accountId)).data.sites
  } catch (reason) {
    const mapped = mapRequestError(reason)
    referenceErrors.push(messageWithError('quotationDetail.sitesFailed', mapped))
  }
  try {
    contacts.value = await loadAllContacts(accountId)
  } catch (reason) {
    const mapped = mapRequestError(reason)
    referenceErrors.push(messageWithError('quotationDetail.contactsFailed', mapped))
  }
  contactError.value = localeMessage(referenceErrors.map((error) => error['en-US']).join('; '), referenceErrors.map((error) => error['zh-CN']).join('；'))
}
async function loadCatalog() {
  catalogError.value = ''
  try { catalog.value = (await props.apiClient.listQuotationCatalog()).data }
  catch (reason) { catalog.value = []; catalogError.value = messageWithError('quotationDetail.catalogFailed', mapRequestError(reason)) }
}
// `busy` is one lock for everything that replaces what the page shows: the loads and every command.
// It is taken only when it is free and released by whoever took it, so two of them never overlap and
// no answer arrives for a state that another one has already replaced. `load` is always called with
// the lock held, by loadHeld or selectVersion.
async function load(versionId?: string) {
  clearSaveTimer(); loading.value = true; error.value = ''; requestId.value = ''; denied.value = false; contactError.value = ''; ready = false; revision = 0; savedRevision = 0
  try {
    const result = await props.apiClient.getQuotation(quotationId.value, versionId)
    applyDetail(result.data); draft.value = asDraft(result.data.version)
    if (result.data.version.quotationType === 'Device') await loadCatalog()
    else { catalog.value = []; catalogError.value = '' }
    if (!versionId || versionId === result.data.quotation.currentVersionId) {
      await loadReferences(result.data.quotation.accountId)
    } else {
      sites.value = []
      contacts.value = []
    }
    await nextTick(); ready = true
  } catch(reason) { const mapped=mapRequestError(reason); error.value=mappedMessage(mapped); requestId.value=mapped.requestId; denied.value=mapped.denied }
  finally { loading.value=false }
}
// The first load and a retry after a failed one.
async function loadHeld(versionId?: string) { if(busy.value)return; busy.value=true; try{ await load(versionId) }finally{ busy.value=false } }
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
        const mapped=mapRequestError(reason); saveState.value='error'; saveError.value=mappedMessage(mapped); return false
      }
    }
    saveState.value='saved'; return true
  })().finally(() => { savePromise=undefined })
  return savePromise
}
function scheduleSave(){ if(!ready || !editable.value)return; revision+=1; saveState.value='idle'; clearSaveTimer(); saveTimer=setTimeout(()=>{saveTimer=undefined;void persistDraft()},1000) }
async function flushPendingSave(){ clearSaveTimer(); return persistDraft() }
async function publish(){ if(!detail.value||busy.value)return; busy.value=true; saveError.value=''; try{ if(!await flushPendingSave())return; applyDetail((await props.apiClient.publishQuotation(quotationId.value,detail.value!.version.modified)).data); draft.value=asDraft(detail.value!.version); revision=savedRevision; await loadCatalog() }catch(reason){saveError.value=mappedMessage(mapRequestError(reason))}finally{busy.value=false} }
async function submitApproval(){ if(!detail.value||busy.value)return; busy.value=true; saveError.value=''; try{ if(!await flushPendingSave())return; applyDetail((await props.apiClient.submitQuotationForApproval(quotationId.value,detail.value!.version.modified)).data);draft.value=asDraft(detail.value!.version);revision=savedRevision;await loadCatalog() }catch(reason){saveError.value=mappedMessage(mapRequestError(reason))}finally{busy.value=false} }
function openApproval(decisionValue: 'Approved'|'Rejected'){ approvalDecision.value={decision:decisionValue,comment:''};approvalOpen.value=true }
async function reviewApproval(){ if(!detail.value||busy.value)return;busy.value=true;saveError.value='';try{applyDetail((await props.apiClient.reviewQuotationApproval(quotationId.value,{...approvalDecision.value,expectedModified:detail.value.version.modified})).data);draft.value=asDraft(detail.value!.version);approvalOpen.value=false}catch(reason){saveError.value=mappedMessage(mapRequestError(reason))}finally{busy.value=false} }
async function createVersion(){ if(busy.value)return; busy.value=true; try{ applyDetail((await props.apiClient.createQuotationVersion(quotationId.value)).data); draft.value=asDraft(detail.value!.version); revision=0;savedRevision=0;await nextTick();ready=true }catch(reason){saveError.value=mappedMessage(mapRequestError(reason))}finally{busy.value=false} }
function discardConfirmation(){
  if(!detail.value)return ''
  const { refNo, currentPublishedVersionId } = detail.value.quotation
  // Without a published version the draft is all there is, and the quotation goes with it.
  return currentPublishedVersionId
    ? ui(`Discard the V${detail.value.version.version} draft of ${refNo} and return to the published version? The draft cannot be recovered.`, `放弃 ${refNo} 的 V${detail.value.version.version} 草稿，回到已发布的版本？草稿内容无法恢复。`)
    : ui(`Discard this draft? The whole quotation ${refNo} will be deleted and cannot be recovered.`, `放弃这份草稿？整张报价单 ${refNo} 将被删除，无法恢复。`)
}
async function discard(){ if(!detail.value||busy.value||!window.confirm(discardConfirmation()))return; busy.value=true; clearSaveTimer(); try{ if(savePromise)await savePromise;revision=savedRevision;const result=await props.apiClient.discardQuotationDraft(quotationId.value,detail.value!.version.modified);if('deleted' in result.data){ready=false;await router.push('/quotations')}else{applyDetail(result.data);draft.value=asDraft(result.data.version)} }catch(reason){saveError.value=mappedMessage(mapRequestError(reason))}finally{busy.value=false} }
// The lock is held from the click on: saving what is pending and loading the version are one step.
async function selectVersion(versionId:string){ if(busy.value)return; busy.value=true; try{ if(editable.value&&!await flushPendingSave())return; await load(versionId) }finally{ busy.value=false } }
async function submitDecision(){ if(busy.value)return; busy.value=true; try{ applyDetail((await props.apiClient.recordQuotationDecision(quotationId.value,{...decision.value,expectedModified:detail.value!.version.modified})).data);decisionOpen.value=false }catch(reason){saveError.value=mappedMessage(mapRequestError(reason))}finally{busy.value=false} }
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
  try{await loadLinkOpportunities();linkOpen.value=true}catch(reason){const mapped=mapRequestError(reason);linkError.value=messageWithRequestId(mapped);linkOpen.value=true}finally{linkBusy.value=false}
}
// Linking replaces what the page shows like any other command, so it holds the others while it runs:
// its answer must not arrive after a discard and put the draft back.
async function linkOpportunity(){
  if(!detail.value||!linkOpportunityId.value||busy.value)return
  linkBusy.value=true;busy.value=true;linkError.value=''
  try{const result=await props.apiClient.linkQuotationOpportunity(quotationId.value,linkOpportunityId.value,detail.value.version.modified);applyDetail(result.data);draft.value=asDraft(result.data.version);linkOpen.value=false}catch(reason){const mapped=mapRequestError(reason);linkError.value=messageWithRequestId(mapped)}finally{linkBusy.value=false;busy.value=false}
}
async function download(versionId?:string){ try{ const file=await props.apiClient.getQuotationPdf(quotationId.value,versionId); downloadBlob(file.blob,file.fileName) }catch(reason){saveError.value=mappedMessage(mapRequestError(reason))} }
async function refreshCurrentIfClean(){
  if(!ready || !detail.value || busy.value || revision>savedRevision || saveTimer || savePromise)return
  const requestedRevision=revision; const requestedEpoch=detailEpoch
  try {
    const result=await props.apiClient.getQuotation(quotationId.value,detail.value.version.id)
    if(!ready || busy.value || detailEpoch!==requestedEpoch || revision!==requestedRevision || revision>savedRevision || saveTimer || savePromise)return
    applyDetail(result.data); draft.value=asDraft(result.data.version)
  }
  catch(reason){ if(!ready || busy.value || detailEpoch!==requestedEpoch)return; saveError.value=mappedMessage(mapRequestError(reason)) }
}
function handleVisibility(){ if(document.visibilityState==='visible')void refreshCurrentIfClean() }
onMounted(async()=>{window.addEventListener('focus',refreshCurrentIfClean);document.addEventListener('visibilitychange',handleVisibility);await app.loadBootstrap(props.apiClient);await loadHeld(linkedVersion.value)})
onBeforeRouteLeave(async()=>{if(!ready||!editable.value)return true;return await flushPendingSave()})
onBeforeUnmount(()=>{ready=false;previewSequence+=1;window.removeEventListener('focus',refreshCurrentIfClean);document.removeEventListener('visibilitychange',handleVisibility);clearSaveTimer();if(previewUrl.value)URL.revokeObjectURL(previewUrl.value)})
</script>
<template>
  <div class="quotation-detail-page" :data-editable="editable">
    <PageHeader v-if="detail" :eyebrow="ui('QUOTATION DETAIL', '报价单详情')" :title="detail.quotation.refNo" :description="`${detail.quotation.accountName} · V${detail.version.version}`">
      <template #default>
        <button class="secondary-button" type="button" @click="router.push('/quotations')"><ArrowLeft :size="14" />{{ (locale === 'en-US' ? 'Back to list' : '返回列表') }}</button>
        <button v-if="detail.version.pdfAvailable" class="secondary-button" data-testid="download-quotation-pdf" type="button" @click="download(detail.version.id)"><Download :size="14" />{{ (locale === 'en-US' ? 'Download PDF' : '下载 PDF') }}</button>
        <button v-if="selectedIsLatest && !detail.quotation.opportunityId && canMutateQuotation" class="secondary-button" data-testid="link-quotation-opportunity" type="button" :disabled="busy || linkBusy" @click="openOpportunityLink"><Link2 :size="14" />{{ ui('Link opportunity', '关联商机') }}</button>
        <button v-if="canDiscard" class="danger-button" data-testid="discard-quotation-draft" type="button" :disabled="busy" @click="discard"><Trash2 :size="14" />{{ (locale === 'en-US' ? 'Discard draft' : '放弃草稿') }}</button>
        <button v-if="editable && isSales && app.can('quotation:submit')" class="primary-button" data-testid="submit-quotation-approval" type="button" :disabled="busy" @click="submitApproval"><Send :size="14" />{{ ui('Submit for Manager approval', '提交经理审批') }}</button>
        <button v-if="editable && !isSales && app.can('quotation:publish')" class="primary-button" data-testid="publish-quotation" type="button" :disabled="busy" @click="publish"><Send :size="14" />{{ (locale === 'en-US' ? 'Publish official version' : '直接发布正式版本') }}</button>
        <button v-if="approvalPending && app.can('quotation:approve')" class="primary-button" data-testid="approve-quotation" type="button" :disabled="busy" @click="openApproval('Approved')"><ShieldCheck :size="14" />{{ (locale === 'en-US' ? 'Approve and publish' : '批准并发布') }}</button>
        <button v-if="approvalPending && app.can('quotation:approve')" class="danger-button" data-testid="reject-quotation" type="button" :disabled="busy" @click="openApproval('Rejected')"><ShieldX :size="14" />{{ (locale === 'en-US' ? 'Reject' : '驳回') }}</button>
        <button v-if="selectedIsLatest && detail.version.status!=='Draft' && canMutateQuotation" class="primary-button" data-testid="create-quotation-version" type="button" :disabled="busy" @click="createVersion"><FilePlus2 :size="14" />{{ (locale === 'en-US' ? 'Create new version' : '创建新版本') }}</button>
        <button v-if="selectedIsLatest && ['Published','Expired'].includes(detail.version.status) && canMutateQuotation" class="secondary-button" type="button" :disabled="busy" @click="decisionOpen=true"><CheckCircle2 :size="14" />{{ (locale === 'en-US' ? 'Record customer result' : '记录客户结果') }}</button>
      </template>
    </PageHeader>
    <DataState v-if="loading" type="loading" />
    <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
    <DataState v-else-if="error||!detail||!draft" type="error" :message="error||(locale === 'en-US' ? 'Quotation failed to load' : '报价单加载失败')" :request-id="requestId" @retry="loadHeld(linkedVersion)" />
    <template v-else>
      <section class="summary-strip">
        <div><small>{{ ui('Name', '名称') }}</small><strong>{{ detail.quotation.refNo }}</strong><span>{{ detail.quotation.accountName }}</span></div>
        <div><small>{{ ui('Type', '类型') }}</small><strong>{{ quotationTypeLabel(detail.version.quotationType) }}</strong><span>{{ detail.version.quotationType === 'Service' ? (locale === 'en-US' ? 'After-sales / repair / accessories' : '售后 / 维修 / 配件') : (locale === 'en-US' ? 'Equipment quotation' : '设备报价') }}</span></div>
        <div><small>{{ ui('Source', '来源') }}</small><strong>{{ detail.quotation.opportunityTitle || ui('Others', '其他') }}</strong><span>{{ detail.quotation.opportunityId || detail.quotation.accountId }}</span></div>
        <div><small>{{ (locale === 'en-US' ? 'Last modified' : '上一次修改日期') }}</small><strong>{{ formatDisplayDate(detail.version.modified) }}</strong><span>V{{ detail.version.version }}</span></div>
        <div><small>{{ ui('Status', '状态') }}</small><StatusBadge :label="quotationStatusLabel(detail.version.status)" :tone="tone" /><StatusBadge :label="approvalStatusLabel(detail.version.approvalStatus)" :tone="approvalTone" /></div>
      </section>
      <div v-if="editable" class="save-line" :class="saveState">
        <span v-if="saveState==='saving'">{{ (locale === 'en-US' ? 'Saving and refreshing preview…' : '正在保存并刷新预览…') }}</span>
        <span v-else-if="saveState==='saved'">{{ (locale === 'en-US' ? 'Saved; preview synced' : '已保存，预览已同步') }}</span>
        <span v-else-if="saveState==='error'">{{ saveError }}{{ (locale === 'en-US' ? '; previous preview retained' : '；预览保留上一次成功版本') }}</span>
        <span v-else>{{ (locale === 'en-US' ? 'Auto-saves about 1 second after editing' : '编辑后约 1 秒自动保存') }}</span>
      </div>
      <p v-else-if="!selectedIsLatest" class="history-notice">{{ (locale === 'en-US' ? 'Viewing a historical version; view and download only.' : '当前正在查看历史版本，仅可查看和下载。') }}</p>
      <p v-else-if="approvalPending" class="approval-notice">{{ ui('This version is awaiting Manager approval and cannot be edited or published.', '当前版本正在等待经理审批，审批完成前不可修改或发布。') }}</p>
      <p v-else-if="detail.version.addressRestricted" class="history-notice" data-testid="quotation-address-restricted">{{ ui('Customer address is visible only to the Account owner or Manager; this quotation is read-only.', '客户地址仅客户负责人或经理可见；当前报价为只读。') }}</p>
      <p v-else-if="detail.version.approvalStatus==='Rejected'" class="rejection-notice">{{ ui('Manager rejected: ', '经理已驳回：') }}{{ latestApproval?.comment || (locale === 'en-US' ? 'No reason provided' : '未填写原因') }}{{ (locale === 'en-US' ? '. Edit and resubmit.' : '。修改后可重新提交审批。') }}</p>
      <p v-if="saveError && saveState!=='error'" class="form-error">{{ saveError }}</p>
      <div class="detail-grid">
        <p v-if="contactError" class="form-error">{{ contactError }}</p>
        <QuotationEditor v-model="draft" :contacts="contacts" :sites="sites" :quotation-type="detail.version.quotationType" :catalog="catalog" :catalog-error="catalogError" :readonly="!editable" @update:model-value="scheduleSave" />
        <aside>
          <SectionCard :title="(locale === 'en-US' ? 'Quotation preview' : '报价单预览')" :eyebrow="ui('LIVE PDF', '实时 PDF')"><QuotationPreview v-if="previewUrl" :src="previewUrl" /><p v-else class="form-error">{{ previewError || (locale === 'en-US' ? 'Generating PDF preview…' : '正在生成 PDF 预览…') }}</p></SectionCard>
          <SectionCard :title="(locale === 'en-US' ? 'Version history' : '历史版本')" :eyebrow="ui('VERSION ARCHIVE', '版本归档')"><QuotationHistory :versions="detail.versions" :selected-id="detail.version.id" @select="selectVersion" @download="download" /></SectionCard>
          <SectionCard v-if="selectedApprovals.length" :title="(locale === 'en-US' ? 'Approval history' : '审批记录')" :eyebrow="ui('APPROVAL HISTORY', '审批历史')">
            <div class="approval-history"><div v-for="item in selectedApprovals" :key="item.id"><strong>{{ (locale === 'en-US' ? `Round ${item.attempt}` : `第 ${item.attempt} 次`) }} · {{ approvalStatusLabel(item.status) }}</strong><small>{{ item.decidedBy || item.submittedBy }} · {{ formatDisplayDate(item.decidedAt || item.submittedAt) }}</small><p v-if="item.comment">{{ item.comment }}</p></div></div>
          </SectionCard>
        </aside>
      </div>
    </template>
    <ModalShell v-if="decisionOpen" :title="(locale === 'en-US' ? 'Record customer result' : '记录客户结果')" :eyebrow="ui('CUSTOMER FEEDBACK', '客户反馈')" :busy="busy" :submit-disabled="!decision.feedbackDate||!decision.feedbackNote.trim()" @close="decisionOpen=false" @submit="submitDecision">
      <div class="decision-form">
        <label><span>{{ (locale === 'en-US' ? 'Result' : '结果') }}</span><select v-model="decision.decision"><option value="Accepted">{{ decisionLabel('Accepted') }}</option><option value="Rejected">{{ decisionLabel('Rejected') }}</option></select></label>
        <label><span>{{ (locale === 'en-US' ? 'Feedback date' : '反馈日期') }}</span><input v-model="decision.feedbackDate" :aria-label="(locale === 'en-US' ? 'Feedback date' : '反馈日期')" type="date" /></label>
        <label class="wide"><span>{{ (locale === 'en-US' ? 'Feedback notes' : '反馈说明') }}</span><textarea v-model="decision.feedbackNote" :aria-label="(locale === 'en-US' ? 'Feedback notes' : '反馈说明')" /></label>
      </div>
    </ModalShell>
    <ModalShell v-if="approvalOpen" :title="approvalDecision.decision==='Approved' ? (locale === 'en-US' ? 'Approve and publish quotation' : '批准报价并发布') : (locale === 'en-US' ? 'Reject quotation' : '驳回报价')" :eyebrow="ui('MANAGER APPROVAL', '经理审批')" :busy="busy" :submit-disabled="approvalDecision.decision==='Rejected'&&!approvalDecision.comment.trim()" @close="approvalOpen=false" @submit="reviewApproval">
      <div class="decision-form"><label class="wide"><span>{{ approvalDecision.decision==='Rejected' ? (locale === 'en-US' ? 'Rejection reason (required)' : '驳回原因（必填）') : (locale === 'en-US' ? 'Approval note (optional)' : '审批意见（选填）') }}</span><textarea v-model="approvalDecision.comment" :aria-label="approvalDecision.decision==='Rejected' ? ui('Rejection reason', '驳回原因') : ui('Approval note', '审批意见')" maxlength="1000" /></label></div>
    </ModalShell>
    <ModalShell v-if="linkOpen" :title="ui('Link opportunity', '关联商机')" :eyebrow="ui('QUOTATION SOURCE', '报价来源')" :busy="linkBusy" :submit-disabled="!linkOpportunityId" @close="linkOpen=false" @submit="linkOpportunity">
      <p v-if="linkError" class="form-error">{{ linkError }}</p>
      <p v-if="!linkBusy && !linkError && !linkOpportunities.length" class="history-notice">{{ (locale === 'en-US' ? 'No opportunities available for this account.' : '当前 Account 没有可关联的 Opportunity。') }}</p>
      <div class="decision-form"><label class="wide"><span>{{ ui('Opportunity', '商机') }}</span><select v-model="linkOpportunityId" data-testid="link-opportunity-select" :aria-label="ui('Opportunity', '商机')"><option value="">{{ ui('Select opportunity', '请选择商机') }}</option><option v-for="item in linkOpportunities" :key="item.id" :value="item.id">{{ item.title }} · {{ item.id }}</option></select></label></div>
    </ModalShell>
  </div>
</template>
<style scoped>
.quotation-detail-page{display:grid;gap:14px}.summary-strip{display:grid;grid-template-columns:1.1fr .8fr 1.7fr 1fr .9fr;gap:0;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.summary-strip>div{display:grid;align-content:center;min-height:80px;padding:13px 16px;border-right:1px solid var(--crm-line)}.summary-strip>div:last-child{border-right:0}.summary-strip small,.summary-strip span{color:var(--crm-muted);font-size:10px}.summary-strip strong{margin:4px 0;color:var(--crm-navy);font-size:13px}.summary-strip :deep(.status-badge + .status-badge){margin-left:5px}.detail-grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(380px,.75fr);align-items:start;gap:14px}.detail-grid aside{position:sticky;top:12px;display:grid;gap:12px;max-height:calc(100vh - 24px);overflow:auto}.save-line,.history-notice,.approval-notice,.rejection-notice,.form-error{margin:0;padding:9px 12px;font-size:11px;border-radius:8px}.save-line{color:#44676a;background:#eef6f5}.save-line.saving,.approval-notice{color:#7c641b;background:#fff7e5}.save-line.error,.rejection-notice,.form-error{color:#a63c3c;background:#fff0ef}.history-notice{color:#5b6575;background:#f0f2f5}.approval-history{display:grid;gap:8px}.approval-history>div{display:grid;gap:3px;padding:9px;border-bottom:1px solid var(--crm-line)}.approval-history small{color:var(--crm-muted)}.approval-history p{margin:2px 0 0;font-size:11px}.decision-form{display:grid;grid-template-columns:1fr 1fr;gap:12px}.decision-form label{display:grid;gap:5px}.decision-form .wide{grid-column:span 2}.decision-form input,.decision-form select,.decision-form textarea{min-height:38px;padding:8px;border:1px solid var(--crm-line);border-radius:7px}.decision-form textarea{min-height:90px}@media(max-width:1180px){.detail-grid{grid-template-columns:1fr}.detail-grid aside{position:static;max-height:none}.summary-strip{grid-template-columns:1fr 1fr}}@media(max-width:650px){.summary-strip{grid-template-columns:1fr}.summary-strip>div{border-right:0;border-bottom:1px solid var(--crm-line)}}
</style>
