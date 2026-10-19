<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { api as defaultApi, type CrmApi } from '@/api'
import { CrmApiError } from '@/api/contracts'
import { requestErrorMessage } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import { useI18n, useLocaleMessage } from '@/i18n'
import { Pencil, Plus } from '@lucide/vue'
import PageHeader from '@/design-system/PageHeader.vue'
import DataState from '@/design-system/DataState.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
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
    <PageHeader eyebrow="DEMO RESOURCES" :title="copy('Demo resources', 'Demo 设备资源')" :description="copy('Concrete internal equipment and its recorded unavailable intervals.', '内部具体设备及已记录的不可用时段。')">
      <button v-if="manager" class="primary-button" type="button" :disabled="busy || !!editing" data-new-resource @click="editResource()"><Plus :size="14" />{{ copy('Add equipment', '添加设备') }}</button>
    </PageHeader>
    <p class="note">{{ copy('Enter real equipment IDs and maintainers. This directory starts empty. Turning off new assignments does not mark equipment unavailable; record an interval below.', '请录入真实设备编号与维护负责人，目录初始为空。停止新安排不代表设备不可用；请在下方登记不可用时段。') }}</p>
    <DataState v-if="loading && !catalogue.resources.length" type="loading" />
    <div v-if="error" class="form-error" role="alert"><span>{{ error }}</span><button class="secondary-button" type="button" :disabled="saving" @click="load">{{ copy('Discard edits and reload', '放弃修改并重新加载') }}</button></div>
    <form v-if="editing === 'resource'" class="card editor" data-resource-form @submit.prevent="save">
      <h2>{{ resourceVersion ? copy('Edit equipment', '修改设备') : copy('New equipment', '添加设备') }}</h2>
      <div class="form-grid">
        <label><span>{{ copy('Equipment ID', '设备编号') }}</span><input v-model="resourceDraft.code" maxlength="140" required :disabled="saving || !!resourceVersion" /></label>
        <label><span>{{ copy('Name', '名称') }}</span><input v-model="resourceDraft.title" maxlength="140" required :disabled="saving" /></label>
        <label><span>{{ copy('Platform / model', '平台／型号') }}</span><input v-model="resourceDraft.platform" maxlength="140" required :disabled="saving" /></label>
        <label><span>{{ copy('Maintainer', '维护负责人') }}</span><select v-model="resourceDraft.maintainer" required :disabled="saving"><option value="">{{ copy('Choose', '请选择') }}</option><option v-if="resourceVersion && !catalogue.maintainers.some(row => row.id === resourceVersion?.maintainer)" :value="resourceVersion.maintainer">{{ resourceVersion.maintainer }} ({{ copy('inactive', '已停用') }})</option><option v-for="row in catalogue.maintainers" :key="row.id" :value="row.id">{{ row.name }}</option></select></label>
        <label class="check wide"><input v-model="resourceDraft.enabled" type="checkbox" :disabled="saving" />{{ copy('Allow new assignments', '允许新安排') }}</label>
      </div>
      <div class="form-actions"><button class="primary-button" type="submit" :disabled="busy || stale">{{ copy('Save', '保存') }}</button><button class="secondary-button" type="button" :disabled="saving" @click="editing = null">{{ copy('Cancel', '取消') }}</button></div>
    </form>
    <div class="resource-grid">
      <aside class="card resource-list">
        <h2>{{ copy('Resource directory', '设备目录') }}</h2>
        <button v-for="row in catalogue.resources" :key="row.id" type="button" class="resource-row" :class="{ selected: row.id === selected }" :disabled="busy || !!editing" @click="select(row.id)"><strong>{{ row.code }} · {{ row.title }}</strong><span class="resource-platform">{{ row.platform }}</span><StatusBadge :label="row.enabled ? copy('Accepting assignments', '允许新安排') : copy('No new assignments', '停止新安排')" :tone="row.enabled ? 'positive' : 'neutral'" /></button>
        <p v-if="!loading && !catalogue.resources.length" class="empty">{{ copy('No equipment registered.', '尚未登记设备。') }}</p>
      </aside>
      <section v-if="resource" class="card resource-detail">
        <header class="card-header"><div><h2>{{ resource.code }} · {{ resource.title }}</h2><p>{{ copy('Maintainer', '维护负责人') }}: {{ catalogue.maintainers.find(row => row.id === resource?.maintainer)?.name || resource.maintainer }}</p></div><button v-if="manager" class="secondary-button" type="button" :disabled="busy || !!editing" data-edit-resource @click="editResource(resource)"><Pencil :size="14" />{{ copy('Edit equipment', '修改设备') }}</button></header>
        <div class="card-header interval-header"><h3>{{ copy('Unavailable intervals', '不可用时段') }}</h3><button v-if="resource.canMaintain" class="secondary-button" type="button" :disabled="busy || !!editing" data-new-interval @click="editInterval()"><Plus :size="14" />{{ copy('Record unavailable interval', '登记不可用时段') }}</button></div>
        <p class="note">{{ copy('All input times use Shanghai time. Adjacent intervals do not conflict. Resolving an interval clears its current warning and keeps observed impact history.', '所有输入时间均为上海时间，首尾相接不算冲突。恢复可用会解除该时段的当前预警，已记录的影响历史保留。') }}</p>
        <div v-if="intervalError" class="form-error" role="alert"><span>{{ intervalError }}</span><button class="secondary-button" type="button" @click="loadIntervals">{{ copy('Retry', '重试') }}</button></div>
        <form v-if="editing === 'interval'" class="editor interval-editor" data-interval-form @submit.prevent="save">
          <div class="form-grid">
            <label><span>{{ copy('Start · Shanghai', '开始 · 上海时间') }}</span><input v-model="intervalDraft.start" type="datetime-local" required :disabled="saving" /></label>
            <label><span>{{ copy('End · Shanghai', '结束 · 上海时间') }}</span><input v-model="intervalDraft.end" type="datetime-local" required :disabled="saving" /></label>
            <label class="wide"><span>{{ copy('Reason', '原因') }}</span><textarea v-model="intervalDraft.reason" maxlength="1000" required :disabled="saving" /></label>
            <label><span>{{ copy('Status', '状态') }}</span><select v-model="intervalDraft.status" :disabled="saving"><option value="Active">{{ copy('Unavailable', '不可用') }}</option><option value="Resolved">{{ copy('Resolved', '已恢复') }}</option></select></label>
          </div>
          <div class="form-actions"><button class="primary-button" type="submit" :disabled="busy || stale">{{ copy('Save', '保存') }}</button><button class="secondary-button" type="button" :disabled="saving" @click="editing = null">{{ copy('Cancel', '取消') }}</button></div>
        </form>
        <ul class="interval-list"><li v-for="row in intervals" :key="row.id" :data-unavailable="row.id"><div><StatusBadge :label="row.status === 'Active' ? copy('Unavailable', '不可用') : copy('Resolved', '已恢复')" :tone="row.status === 'Active' ? 'danger' : 'positive'" /><strong>{{ resourceDateTime(row.start) }} — {{ resourceDateTime(row.end) }}</strong><p>{{ row.reason }}</p></div><button v-if="resource.canMaintain" class="secondary-button" type="button" :disabled="busy || !!editing" @click="editInterval(row)">{{ copy('Edit / resolve', '修改／恢复可用') }}</button></li></ul>
        <p v-if="!intervalError && !intervals.length" class="empty">{{ copy('No unavailable intervals recorded.', '未记录不可用时段。') }}</p>
      </section>
    </div>
  </div>
  <DataState v-else type="denied" :message="copy('Demo access is required.', '需要 Demo 查看权限。')" />
</template>

<style scoped>
.resources-page{display:grid;gap:16px;max-width:1400px;margin:auto}
.note{margin:0;color:var(--crm-text-muted);font-size:12px;line-height:1.7}
.card{padding:20px;background:var(--crm-surface-raised);border:1px solid var(--crm-line);border-radius:var(--crm-radius-md)}
.card h2{margin:0;color:var(--crm-navy);font-size:15px}
.card h3{margin:0;color:var(--crm-navy);font-size:13px}
.card-header{display:flex;align-items:center;justify-content:space-between;gap:12px}
.card-header p{margin:4px 0 0;color:var(--crm-text-muted);font-size:11px}
.form-error{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0;padding:10px 12px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:11px}
.editor{display:grid;gap:14px}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.form-grid label{display:grid;gap:6px}
.form-grid label.wide{grid-column:1/-1}
.form-grid span{color:var(--crm-text-muted);font-size:9px;font-weight:700}
.form-grid input:not([type=checkbox]),.form-grid select,.form-grid textarea{min-height:38px;padding:0 10px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:8px;font:inherit}
.form-grid textarea{min-height:76px;padding:8px 10px;resize:vertical}
.form-grid input:focus,.form-grid select:focus,.form-grid textarea:focus{border-color:var(--crm-teal);outline:0}
.form-grid .check{display:flex;align-items:center;gap:8px;font-size:11px}
.form-actions{display:flex;gap:8px}
.resource-grid{display:grid;grid-template-columns:320px 1fr;gap:16px;align-items:start}
.resource-list{display:grid;gap:10px}
.resource-row{display:grid;justify-items:start;gap:6px;width:100%;padding:12px;text-align:left;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:10px;cursor:pointer;transition:border-color .18s ease,background-color .18s ease}
.resource-row .resource-platform{color:var(--crm-text-muted);font-size:11px}
.resource-row:not(:disabled):hover{background:#F5F7FF;border-color:#A8BAEF}
.resource-row.selected{background:#F5F7FF;border-color:var(--crm-brand)}
.resource-row:disabled{cursor:default;opacity:.7}
.resource-detail{display:grid;gap:14px}
.interval-header{padding-top:14px;border-top:1px solid var(--crm-line)}
.interval-editor{padding:14px;background:var(--crm-surface);border-radius:10px}
.interval-list{display:grid;margin:0;padding:0;list-style:none}
.interval-list li{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:14px 0;border-bottom:1px solid var(--crm-line)}
.interval-list li:last-child{border-bottom:0}
.interval-list li>div{display:grid;gap:6px}
.interval-list strong{font-size:12px}
.interval-list p{margin:0;color:var(--crm-text-muted);font-size:11px;line-height:1.6}
.empty{margin:0;color:var(--crm-text-muted);font-size:11px}
@media(max-width:850px){.resource-grid,.form-grid{grid-template-columns:1fr}.form-grid label.wide{grid-column:auto}}
</style>
