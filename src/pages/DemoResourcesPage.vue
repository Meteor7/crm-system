<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { api as defaultApi, type CrmApi } from '@/api'
import { CrmApiError } from '@/api/contracts'
import { requestErrorMessage } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import { useI18n, useLocaleMessage } from '@/i18n'
import { resourceDateTime } from '@/features/demo-resources/types'
import type { DemoResource, DemoResourceCatalogue, DemoUnavailability } from '@/features/demo-resources/types'
import { shanghaiInput, shanghaiTimestamp } from '@/features/demo-resources/types'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const app = useAppStore(), { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const manager = computed(() => app.bootstrap?.user.role === 'Manager')
const catalogue = ref<DemoResourceCatalogue>({ resources: [], maintainers: [] })
const selected = ref(''), intervals = ref<DemoUnavailability[]>([])
const resource = computed(() => catalogue.value.resources.find(row => row.id === selected.value))
const loading = ref(false), saving = ref(false), editing = ref<'resource' | 'interval' | null>(null), stale = ref(false)
const error = useLocaleMessage(), intervalError = useLocaleMessage()
const resourceVersion = ref<DemoResource>(), intervalVersion = ref<DemoUnavailability>()
const resourceDraft = reactive({ code: '', title: '', platform: '', maintainer: '', enabled: true })
const intervalDraft = reactive({ start: '', end: '', reason: '', status: 'Active' as 'Active' | 'Resolved' })
const busy = computed(() => loading.value || saving.value)
let revision = 0, intervalRevision = 0

async function load() {
  if (!app.can('evaluation:view')) return
  const current = ++revision
  loading.value = true; error.value = ''; editing.value = null; stale.value = false
  try {
    const response = await props.apiClient.getDemoResources()
    if (current !== revision) return
    catalogue.value = response.data
    if (!catalogue.value.resources.some(row => row.id === selected.value)) selected.value = catalogue.value.resources[0]?.id ?? ''
    await loadIntervals()
  } catch (reason) { if (current === revision) error.value = requestErrorMessage(reason) }
  finally { if (current === revision) loading.value = false }
}
async function loadIntervals() {
  const current = ++intervalRevision, id = selected.value
  intervals.value = []; intervalError.value = ''
  if (!id) return
  try {
    const response = await props.apiClient.getDemoUnavailability(id)
    if (current === intervalRevision) intervals.value = response.data
  } catch (reason) { if (current === intervalRevision) intervalError.value = requestErrorMessage(reason) }
}
async function select(id: string) { if (busy.value || editing.value) return; selected.value = id; await loadIntervals() }
function editResource(row?: DemoResource) {
  if (!manager.value || busy.value) return
  resourceVersion.value = row
  Object.assign(resourceDraft, row ?? { code: '', title: '', platform: '', maintainer: '', enabled: true })
  editing.value = 'resource'; stale.value = false; error.value = ''
}
function editInterval(row?: DemoUnavailability) {
  if (!resource.value?.canMaintain || busy.value) return
  intervalVersion.value = row
  Object.assign(intervalDraft, { start: shanghaiInput(row?.start ?? null), end: shanghaiInput(row?.end ?? null), reason: row?.reason ?? '', status: row?.status ?? 'Active' })
  editing.value = 'interval'; stale.value = false; error.value = ''
}
async function save() {
  if (busy.value || stale.value || !editing.value) return
  const current = revision
  saving.value = true; error.value = ''
  try {
    if (editing.value === 'resource' && manager.value) {
      const { code, title, platform, maintainer, enabled } = resourceDraft
      const response = await props.apiClient.saveDemoResource({ code, title, platform, maintainer, enabled }, resourceVersion.value?.id, resourceVersion.value?.modified)
      if (current !== revision) return
      selected.value = response.data.id
    } else if (editing.value === 'interval' && resource.value?.canMaintain) {
      await props.apiClient.saveDemoUnavailability(selected.value, { ...intervalDraft, start: shanghaiTimestamp(intervalDraft.start), end: shanghaiTimestamp(intervalDraft.end) }, intervalVersion.value?.id, intervalVersion.value?.modified)
      if (current !== revision) return
    } else return
    editing.value = null
    await load()
  } catch (reason) { if (current === revision) { error.value = requestErrorMessage(reason); stale.value = !(reason instanceof CrmApiError && reason.code === 'VALIDATION_ERROR') } }
  finally { if (current <= revision) saving.value = false }
}
watch(() => [app.bootstrap?.user.id, app.bootstrap?.user.role], () => {
  revision++; intervalRevision++; catalogue.value = { resources: [], maintainers: [] }; intervals.value = []; selected.value = ''; editing.value = null
  loading.value = false; saving.value = false; error.value = ''; intervalError.value = ''
  void load()
})
onMounted(async () => { await app.loadBootstrap(props.apiClient); if (app.bootstrap && !loading.value) await load() })
onBeforeUnmount(() => { revision++; intervalRevision++ })
</script>

<template>
  <div v-if="app.can('evaluation:view')" class="resources-page" data-demo-resources>
    <header><div><h1>{{ copy('Demo resources', 'Demo 设备资源') }}</h1><p>{{ copy('Concrete internal equipment and its recorded unavailable intervals.', '内部具体设备及已记录的不可用时段。') }}</p></div><button v-if="manager" :disabled="busy || !!editing" data-new-resource @click="editResource()">{{ copy('Add equipment', '添加设备') }}</button></header>
    <p class="help">{{ copy('Enter real equipment IDs and maintainers. This directory starts empty. Turning off new assignments does not mark equipment unavailable; record an interval below.', '请录入真实设备编号与维护负责人，目录初始为空。停止新安排不代表设备不可用；请在下方登记不可用时段。') }}</p>
    <p v-if="loading" role="status">{{ copy('Loading…', '正在加载…') }}</p>
    <p v-if="error" role="alert">{{ error }} <button :disabled="saving" @click="load">{{ copy('Discard edits and reload', '放弃修改并重新加载') }}</button></p>
    <form v-if="editing === 'resource'" data-resource-form @submit.prevent="save">
      <h2>{{ resourceVersion ? copy('Edit equipment', '修改设备') : copy('New equipment', '添加设备') }}</h2>
      <label>{{ copy('Equipment ID', '设备编号') }}<input v-model="resourceDraft.code" maxlength="140" required :disabled="saving || !!resourceVersion" /></label>
      <label>{{ copy('Name', '名称') }}<input v-model="resourceDraft.title" maxlength="140" required :disabled="saving" /></label>
      <label>{{ copy('Platform / model', '平台／型号') }}<input v-model="resourceDraft.platform" maxlength="140" required :disabled="saving" /></label>
      <label>{{ copy('Maintainer', '维护负责人') }}<select v-model="resourceDraft.maintainer" required :disabled="saving"><option value="">{{ copy('Choose', '请选择') }}</option><option v-if="resourceVersion && !catalogue.maintainers.some(row => row.id === resourceVersion?.maintainer)" :value="resourceVersion.maintainer">{{ resourceVersion.maintainer }} ({{ copy('inactive', '已停用') }})</option><option v-for="row in catalogue.maintainers" :key="row.id" :value="row.id">{{ row.name }}</option></select></label>
      <label class="check"><input v-model="resourceDraft.enabled" type="checkbox" :disabled="saving" />{{ copy('Allow new assignments', '允许新安排') }}</label>
      <div class="actions"><button type="submit" :disabled="busy || stale">{{ copy('Save', '保存') }}</button><button type="button" :disabled="saving" @click="editing = null">{{ copy('Cancel', '取消') }}</button></div>
    </form>
    <div class="resource-grid">
      <aside><button v-for="row in catalogue.resources" :key="row.id" class="resource-row" :class="{ selected: row.id === selected }" :disabled="busy || !!editing" @click="select(row.id)"><strong>{{ row.code }} · {{ row.title }}</strong><span>{{ row.platform }} · {{ row.enabled ? copy('Accepting assignments', '允许新安排') : copy('No new assignments', '停止新安排') }}</span></button><p v-if="!loading && !catalogue.resources.length">{{ copy('No equipment registered.', '尚未登记设备。') }}</p></aside>
      <section v-if="resource">
        <header><div><h2>{{ resource.code }} · {{ resource.title }}</h2><p>{{ copy('Maintainer', '维护负责人') }}: {{ catalogue.maintainers.find(row => row.id === resource?.maintainer)?.name || resource.maintainer }}</p></div><button v-if="manager" :disabled="busy || !!editing" data-edit-resource @click="editResource(resource)">{{ copy('Edit equipment', '修改设备') }}</button></header>
        <h3>{{ copy('Unavailable intervals', '不可用时段') }}</h3>
        <p class="help">{{ copy('All input times use Shanghai time. Adjacent intervals do not conflict. Resolving an interval clears its current warning and keeps observed impact history.', '所有输入时间均为上海时间，首尾相接不算冲突。恢复可用会解除该时段的当前预警，已记录的影响历史保留。') }}</p>
        <button v-if="resource.canMaintain" :disabled="busy || !!editing" data-new-interval @click="editInterval()">{{ copy('Record unavailable interval', '登记不可用时段') }}</button>
        <p v-if="intervalError" role="alert">{{ intervalError }} <button @click="loadIntervals">{{ copy('Retry', '重试') }}</button></p>
        <form v-if="editing === 'interval'" data-interval-form @submit.prevent="save">
          <label>{{ copy('Start · Shanghai', '开始 · 上海时间') }}<input v-model="intervalDraft.start" type="datetime-local" required :disabled="saving" /></label>
          <label>{{ copy('End · Shanghai', '结束 · 上海时间') }}<input v-model="intervalDraft.end" type="datetime-local" required :disabled="saving" /></label>
          <label>{{ copy('Reason', '原因') }}<textarea v-model="intervalDraft.reason" maxlength="1000" required :disabled="saving" /></label>
          <label>{{ copy('Status', '状态') }}<select v-model="intervalDraft.status" :disabled="saving"><option value="Active">{{ copy('Unavailable', '不可用') }}</option><option value="Resolved">{{ copy('Resolved', '已恢复') }}</option></select></label>
          <div class="actions"><button type="submit" :disabled="busy || stale">{{ copy('Save', '保存') }}</button><button type="button" :disabled="saving" @click="editing = null">{{ copy('Cancel', '取消') }}</button></div>
        </form>
        <ul><li v-for="row in intervals" :key="row.id" :data-unavailable="row.id"><strong>{{ row.status === 'Active' ? copy('Unavailable', '不可用') : copy('Resolved', '已恢复') }}</strong><p>{{ resourceDateTime(row.start) }} — {{ resourceDateTime(row.end) }}</p><p>{{ row.reason }}</p><button v-if="resource.canMaintain" :disabled="busy || !!editing" @click="editInterval(row)">{{ copy('Edit / resolve', '修改／恢复可用') }}</button></li></ul>
        <p v-if="!intervalError && !intervals.length">{{ copy('No unavailable intervals recorded.', '未记录不可用时段。') }}</p>
      </section>
    </div>
  </div>
  <p v-else>{{ copy('Demo access is required.', '需要 Demo 查看权限。') }}</p>
</template>

<style scoped>
.resources-page{max-width:1400px;margin:auto;color:var(--crm-text)}header{display:flex;gap:16px;justify-content:space-between;align-items:center}h1{font-size:26px}h2{font-size:18px}h3{font-size:16px}.help,header p{color:var(--crm-text-muted);line-height:1.6}.resource-grid{display:grid;grid-template-columns:320px 1fr;gap:20px;margin-top:20px}section,form,aside{background:white;border:1px solid var(--crm-line);border-radius:10px;padding:18px}form{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}form h2{width:100%;margin:0}label{display:grid;gap:6px;flex:1;min-width:180px}.check{display:flex;align-items:center}.actions{display:flex;gap:8px;align-items:end}input,select,textarea,button{font:inherit;padding:8px;border:1px solid var(--crm-line);border-radius:6px;background:white}button{cursor:pointer}button:disabled{opacity:.55;cursor:default}.resource-row{display:grid;gap:8px;width:100%;text-align:left;margin-bottom:10px}.selected{border-color:var(--crm-brand)}ul{padding:0;list-style:none}li{padding:14px 0;border-bottom:1px solid var(--crm-line)}[role=alert]{color:var(--crm-danger)}@media(max-width:850px){.resource-grid{grid-template-columns:1fr}header{align-items:start}}
</style>
