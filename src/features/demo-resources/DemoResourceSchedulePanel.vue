<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import type { CrmApi } from '@/api'
import { CrmApiError } from '@/api/contracts'
import { requestErrorMessage } from '@/api/request-state'
import { resourceDateTime } from '@/features/demo-resources/types'
import { useI18n, useLocaleMessage } from '@/i18n'
import type { DemoResource, DemoResourceSchedule } from './types'
import { shanghaiInput, shanghaiTimestamp } from './types'

const props = defineProps<{ evaluationId: string; apiClient: CrmApi; refreshToken?: string }>()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const expanded = ref(false), loading = ref(false), saving = ref(false), stale = ref(false)
const data = ref<DemoResourceSchedule>(), resources = ref<DemoResource[]>([])
const error = useLocaleMessage()
const draft = reactive({ resourceId: '', start: '', end: '' })
const dirty = computed(() => !!data.value && (draft.resourceId !== data.value.resourceId || draft.start !== shanghaiInput(data.value.start) || draft.end !== shanghaiInput(data.value.end)))
let sequence = 0, refreshPending = false
watch(() => props.evaluationId, () => { sequence++; expanded.value = false; data.value = undefined; resources.value = []; error.value = ''; stale.value = false; loading.value = false; saving.value = false; refreshPending = false })
watch(() => props.refreshToken, () => {
  if (saving.value) { refreshPending = true; return }
  if (dirty.value) { stale.value = true; error.value = copy('Demo changed; your edits are retained. Reload before saving.', 'Demo 已更新，输入已保留。请重新加载后再保存。') }
  else if (expanded.value) void load()
  else data.value = undefined
})
onBeforeUnmount(() => { sequence++ })
async function load() {
  const current = ++sequence
  loading.value = true; error.value = ''
  try {
    const [schedule, catalogue] = await Promise.all([props.apiClient.getDemoResourceSchedule(props.evaluationId), props.apiClient.getDemoResources()])
    if (current !== sequence) return
    data.value = schedule.data; resources.value = catalogue.data.resources
    Object.assign(draft, { resourceId: data.value.resourceId, start: shanghaiInput(data.value.start), end: shanghaiInput(data.value.end) })
    stale.value = false
  } catch (reason) { if (current === sequence) { error.value = requestErrorMessage(reason); stale.value = true } }
  finally { if (current === sequence) loading.value = false }
}
async function toggle() {
  expanded.value = !expanded.value
  if (!expanded.value) return
  if (dirty.value) {
    stale.value = true
    error.value = copy('Availability may have changed; your edits are retained. Reload before saving.', '设备可用性可能已更新，输入已保留。请重新加载后再保存。')
  } else await load()
}
async function save() {
  if (!data.value?.canWrite || saving.value || loading.value || stale.value) return
  const current = sequence
  saving.value = true; error.value = ''
  try {
    const input = { resourceId: draft.resourceId, start: draft.resourceId ? shanghaiTimestamp(draft.start) : null, end: draft.resourceId ? shanghaiTimestamp(draft.end) : null }
    const response = await props.apiClient.saveDemoResourceSchedule(props.evaluationId, input, data.value.modified)
    if (current !== sequence) return
    data.value = response.data
    Object.assign(draft, { resourceId: data.value.resourceId, start: shanghaiInput(data.value.start), end: shanghaiInput(data.value.end) })
  } catch (reason) { if (current === sequence) { error.value = requestErrorMessage(reason); stale.value = !(reason instanceof CrmApiError && reason.code === 'VALIDATION_ERROR') } }
  finally {
    if (current === sequence) {
      saving.value = false
      if (refreshPending) { refreshPending = false; if (!error.value) await load() }
    }
  }
}
const stateLabel = computed(() => ({ unknown: copy('Resource or schedule incomplete', '设备或时间资料不完整'), blocked: copy('Resource unavailable during this schedule', '安排与设备不可用时间相交'), available: copy('No recorded unavailability overlaps this schedule', '当前安排未与已记录的不可用时段相交'), inactive: copy('Demo is outside the testing preparation stages', 'Demo 已不在测试准备／测试阶段'), elapsed: copy('This schedule has elapsed', '该安排已结束') })[data.value?.state ?? 'unknown'])
</script>

<template>
  <section class="resource-panel" data-demo-resource-schedule>
    <button type="button" :disabled="saving" :aria-expanded="expanded" @click="toggle">{{ copy('Demo resource and availability', 'Demo 设备与可用性') }}</button>
    <template v-if="expanded">
      <p v-if="loading">{{ copy('Loading…', '正在加载…') }}</p>
      <p v-if="error" role="alert">{{ error }} <button :disabled="saving" @click="load">{{ copy('Discard edits and reload', '放弃修改并重新加载') }}</button></p>
      <template v-if="data && !loading">
        <p v-if="!stale" :class="data.state" data-resource-state>{{ stateLabel }}</p>
        <form v-if="data.canWrite" @submit.prevent="save">
          <label>{{ copy('Concrete equipment', '具体设备') }}<select v-model="draft.resourceId" :disabled="saving"><option value="">{{ copy('Not assigned', '未安排') }}</option><option v-for="row in resources.filter(r => r.enabled || r.id === data?.resourceId)" :key="row.id" :value="row.id">{{ row.code }} · {{ row.title }}{{ row.enabled ? '' : copy(' (no new assignments)', '（停止新安排）') }}</option></select></label>
          <label>{{ copy('Start · Shanghai time', '开始 · 上海时间') }}<input v-model="draft.start" type="datetime-local" :required="!!draft.resourceId" :disabled="saving || !draft.resourceId" /></label>
          <label>{{ copy('End · Shanghai time', '结束 · 上海时间') }}<input v-model="draft.end" type="datetime-local" :required="!!draft.resourceId" :disabled="saving || !draft.resourceId" /></label>
          <button type="submit" :disabled="saving || stale">{{ copy('Save arrangement', '保存安排') }}</button>
        </form>
        <p v-else>{{ resources.find(r => r.id === data?.resourceId)?.title || '—' }} · {{ data.start ? resourceDateTime(data.start) : '—' }} — {{ data.end ? resourceDateTime(data.end) : '—' }}</p>
        <p class="help">{{ copy('End-to-start adjacent intervals do not conflict. Missing information is not proof of availability.', '首尾相接不算冲突；资料缺失不代表设备可用。') }} <RouterLink to="/demo-resources">{{ copy('Resource directory', '设备目录') }}</RouterLink></p>
        <ul v-if="data.impacts.length"><li v-for="row in data.impacts" :key="row.key">{{ row.reason }} · {{ resourceDateTime(row.unavailableStart) }} — {{ resourceDateTime(row.unavailableEnd) }}</li></ul>
        <details v-if="data.history.length"><summary>{{ copy('Observed impact history', '已观察到的影响历史') }} ({{ data.history.length }})</summary><ul><li v-for="row in data.history" :key="row.id">{{ resourceDateTime(row.detectedAt) }} · {{ row.current ? copy('Currently affected', '当前受影响') : copy('No longer affected by this instance', '当前已不受该实例影响') }} · {{ row.snapshot.reason }} · {{ resourceDateTime(row.snapshot.unavailableStart) }} — {{ resourceDateTime(row.snapshot.unavailableEnd) }}</li></ul></details>
      </template>
    </template>
  </section>
</template>

<style scoped>
.resource-panel{padding:16px;border:1px solid var(--crm-line);border-radius:10px;background:white;font-size:13px}form{display:flex;gap:12px;flex-wrap:wrap;align-items:end}label{display:grid;gap:6px}input,select,button{padding:8px;border:1px solid var(--crm-line);border-radius:6px;background:white}button{cursor:pointer}button:disabled{opacity:.5;cursor:default}.blocked,[role=alert]{color:var(--crm-danger)}.unknown,.help{color:var(--crm-text-muted)}li{margin:8px 0}
</style>
