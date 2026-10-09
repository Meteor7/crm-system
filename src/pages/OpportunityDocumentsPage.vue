<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ArrowLeft, Target } from '@lucide/vue'
import { api as defaultApi, type CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import { useI18n, useLocaleMessage } from '@/i18n'
import { downloadBlob } from '@/features/shared/download-blob'
import { formatDisplayDate } from '@/domain/time'
import type { OpportunityDocuments, OpportunityDocumentKind, OpportunityDocumentItem, ScorecardKey } from '@/features/opportunities/document-types'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const route = useRoute(), app = useAppStore(), { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const id = computed(() => String(route.params.opportunityId || ''))
const data = ref<OpportunityDocuments | null>(null)
const loading = ref(false), busy = ref(false), editing = ref(false), downloading = ref('')
// Read in the reader's language where the service's message is a known one; as written otherwise.
const error = useLocaleMessage(), formError = useLocaleMessage()
const refusal = (reason: unknown) => { const mapped = mapRequestError(reason); return mapped.localizedMessage ?? mapped.message }
const draft = ref({ productScorecard: '', dealScorecard: '' })
const keys: ScorecardKey[] = ['productScorecard', 'dealScorecard']
let revision = 0
const label = (key: ScorecardKey) => key === 'productScorecard' ? copy('Product scorecard', '产品评分卡') : copy('Deal scorecard', '商机评分卡')
const groupLabel = (kind: OpportunityDocumentKind) => ({ status: copy('Status attachments', 'Status 附件'), demo: copy('Demo reports and forms', 'Demo 报告与表单'), rfq: 'RFQ', quotation: copy('Quotations', '报价'), visit: copy('Visit records', '拜访记录') })[kind]
async function load() {
  const current = ++revision
  loading.value = true; error.value = ''; editing.value = false; data.value = null
  try { const result = await props.apiClient.getOpportunityDocuments(id.value); if (current === revision) data.value = result.data }
  catch (reason) { if (current === revision) error.value = refusal(reason) }
  finally { if (current === revision) loading.value = false }
}
watch(id, load, { immediate: true })
function edit() {
  if (!data.value) return
  draft.value = { productScorecard: data.value.links.productScorecard.url, dealScorecard: data.value.links.dealScorecard.url }
  editing.value = true; formError.value = ''
}
async function save() {
  if (!data.value || busy.value) return
  const current = revision, opportunityId = id.value
  busy.value = true; formError.value = ''
  try {
    const result = await props.apiClient.saveOpportunityDocumentLinks(opportunityId, { ...draft.value }, data.value.modified)
    if (current === revision && data.value) { Object.assign(data.value, result.data); editing.value = false }
  } catch (reason) { if (current === revision) formError.value = refusal(reason) }
  finally { busy.value = false }
}
function destination(kind: OpportunityDocumentKind, item: OpportunityDocumentItem) {
  if (kind === 'demo') return { name: 'demo-detail', params: { demoId: item.sourceId }, query: { tab: 'information' } }
  if (kind === 'rfq') return { name: 'rfq-detail', params: { rfqId: item.sourceId } }
  if (kind === 'quotation') return { name: 'quotation-detail', params: { quotationId: item.sourceId } }
  if (kind === 'visit') return { name: 'visit-detail', params: { visitId: item.sourceId } }
  return { name: 'opportunity-detail', params: { opportunityId: id.value }, hash: '#blue-sheet' }
}
async function download(kind: OpportunityDocumentKind, item: OpportunityDocumentItem) {
  if (downloading.value || !item.fileId) return
  const current = revision, opportunityId = id.value
  downloading.value = item.id; error.value = ''
  try {
    const result = kind === 'demo' ? await props.apiClient.getDemoArtifact(item.fileId)
      : await props.apiClient.getOpportunityStatusFile(opportunityId, item.recordId!, item.fileId)
    if (current === revision) downloadBlob(result.blob, result.fileName)
  } catch (reason) { if (current === revision) error.value = refusal(reason) }
  finally { downloading.value = '' }
}
</script>

<template>
  <main class="document-library" data-testid="opportunity-documents">
    <!-- The ways back are buttons, as on the other detail pages: the back button and the Blue Sheet button. -->
    <nav><RouterLink class="detail-back-button" data-testid="documents-back-opportunity" :to="{ name: 'opportunity-detail', params: { opportunityId: id } }"><ArrowLeft :size="14" />{{ copy('Back to opportunity', '返回商机') }}</RouterLink><RouterLink class="secondary-button" data-testid="documents-blue-sheet" :to="{ name: 'opportunity-detail', params: { opportunityId: id }, hash: '#blue-sheet' }"><Target :size="14" />{{ copy('Blue Sheet', '战略分析') }}</RouterLink></nav>
    <header><div><h1>{{ copy('Documents', '商机资料') }}</h1><p v-if="data">{{ data.title }}</p></div><button :disabled="loading || busy || editing" @click="load">{{ copy('Refresh', '刷新') }}</button></header>
    <p v-if="error" role="alert">{{ error }} <button :disabled="editing" @click="load">{{ copy('Reload documents', '重新加载资料') }}</button></p>
    <p v-if="loading">{{ copy('Loading…', '正在加载…') }}</p>
    <template v-else-if="data">
      <section class="scorecards"><header><h2>{{ copy('Scorecards', '评分卡') }}</h2><button v-if="app.can('deal:write') && !data.archived && !editing" @click="edit">{{ copy('Edit links', '编辑链接') }}</button></header>
        <form v-if="editing" @submit.prevent="save">
          <label v-for="key in keys" :key="key">{{ label(key) }}<input v-model="draft[key]" type="url" maxlength="2048" :disabled="busy" :data-testid="key" placeholder="https://" /></label>
          <p>{{ copy('Leave a field blank to remove its link.', '清空字段可移除对应链接。') }}</p>
          <p v-if="formError" role="alert">{{ formError }}</p>
          <button type="submit" :disabled="busy">{{ copy('Save', '保存') }}</button><button type="button" :disabled="busy" @click="editing = false">{{ copy('Cancel', '取消') }}</button>
          <button v-if="formError" type="button" :disabled="busy" @click="load">{{ copy('Discard edits and reload', '放弃修改并重新加载') }}</button>
        </form>
        <ul v-else><li v-for="key in keys" :key="key"><strong>{{ label(key) }}</strong><a v-if="data.links[key].state === 'ready'" :href="data.links[key].url" target="_blank" rel="noopener noreferrer">{{ copy('Open scorecard', '打开评分卡') }} ↗</a><span v-else>{{ data.links[key].state === 'invalid' ? copy('Invalid link — update it.', '链接无效，请更新。') : copy('Link not set', '尚未设置链接') }}</span></li></ul>
      </section>
      <section v-for="group in data.groups" :key="group.kind" :data-testid="`documents-${group.kind}`">
        <h2>{{ groupLabel(group.kind) }} <small>{{ group.items.length }}</small></h2>
        <p v-if="!group.items.length">{{ copy('No linked documents visible in your scope.', '暂无你可访问的关联资料。') }}</p>
        <ul v-else><li v-for="item in group.items" :key="item.id"><div><RouterLink :to="destination(group.kind, item)">{{ item.title }}</RouterLink><small>{{ item.version ? `v${item.version} · ` : '' }}{{ formatDisplayDate(item.at) }}</small></div><button v-if="item.fileId" :disabled="Boolean(downloading)" @click="download(group.kind, item)">{{ downloading === item.id ? copy('Downloading…', '下载中…') : copy('Download', '下载') }}</button><RouterLink v-else :to="destination(group.kind, item)">{{ copy('Open record', '打开记录') }}</RouterLink></li></ul>
      </section>
    </template>
  </main>
</template>

<style scoped>
.document-library{max-width:1100px;margin:auto;padding:24px;color:var(--crm-text)}nav,header{display:flex;align-items:center;justify-content:space-between;gap:16px}nav{justify-content:flex-start;gap:8px;margin-bottom:20px}
nav a{text-decoration:none}nav .secondary-button{min-height:38px}h1{margin:0}h2{font-size:17px}section{background:white;border:1px solid var(--crm-line);border-radius:12px;padding:20px;margin:18px 0}ul{list-style:none;margin:0;padding:0}li{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px 0;border-top:1px solid var(--crm-line)}li>div{display:grid;gap:6px}a{color:var(--crm-link);overflow-wrap:anywhere}small,section>p{color:var(--crm-text-muted)}button{padding:8px 12px;border:1px solid var(--crm-line);border-radius:6px;background:white;cursor:pointer}button:disabled{opacity:.5;cursor:default}label{display:grid;gap:6px;margin:14px 0}input{padding:10px;border:1px solid var(--crm-line);border-radius:6px}form>button{margin-right:8px}[role=alert]{color:var(--crm-danger)}@media(max-width:600px){.document-library{padding:12px}section{padding:14px}li{align-items:flex-start;flex-wrap:wrap}}
</style>
