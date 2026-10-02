<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Download, Plus, RefreshCw, Save, SlidersHorizontal, X } from '@lucide/vue'
import { api as defaultApi, type CrmApi } from '@/api'
import { CrmApiError } from '@/api/contracts'
import { requestErrorMessage } from '@/api/request-state'
import { useI18n, useLocaleMessage } from '@/i18n'
import { useAppStore } from '@/stores/app'
import PaginationControls from '@/features/shared/PaginationControls.vue'
import BoardMultiSelect from '@/features/opportunity-board/BoardMultiSelect.vue'
import BoardConditionRow from '@/features/opportunity-board/BoardConditionRow.vue'
import { allColumns, cellText, condition, defaultDefinition, fieldLabel, fieldOptions, groupFields, groupKey, money, optionLabel, presets, text, toQuery, validateDefinition } from '@/features/opportunity-board/model'
import { boardWorkbook, readBoardExport } from '@/features/opportunity-board/export'
import { downloadCustomerReport } from '@/features/accounts/xlsx-writer'
import { cockpitRoute, fromBoardScope, readCockpitQuery, toBoardScope } from '@/features/cockpit/scope'
import type { BoardColumn, BoardDefinition, BoardFilters, BoardResult, SavedBoardQuery } from '@/features/opportunity-board/types'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const app = useAppStore()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const brandIconUrl = `${import.meta.env.BASE_URL}brand/planck-icon.png`
const canView = computed(() => app.can('deal:view'))
const manager = computed(() => app.bootstrap?.user.role === 'Manager')
const route = useRoute()
// Opened from another cockpit tab with its single-value scope and Review period (see cockpit/scope.ts).
// The identity watch below resets the definition on mount and again once the account loads: every reset starts
// from the incoming scope, so the first query already carries it. Saved queries and exports are untouched.
function initialDefinition(): BoardDefinition {
  return { ...defaultDefinition(), scope: toBoardScope(readCockpitQuery(route.query).scope) }
}
const definition = ref<BoardDefinition>(initialDefinition())
// This board has no period of its own: the Review period it was opened with goes along to the other tabs.
const periodContext = computed(() => { const incoming = readCockpitQuery(route.query); return { period: incoming.period ?? 'week', reviewAnchor: incoming.reviewAnchor } })
// A dimension with several values selected cannot be shown on the single-value tabs: navigation waits for one value or all.
const outgoing = computed(() => fromBoardScope(definition.value.scope))
const tabRoute = (page: 'review' | 'plan' | 'warnings') => cockpitRoute(page, { ...outgoing.value.scope, ...periodContext.value })
const tabNames = { review: 'Review', plan: 'Plan', warnings: 'Warnings' } as const
const blockedScope = computed(() => outgoing.value.blocked.map(key => fieldLabel(key, locale.value)).join(copy(', ', '、')))
const filters = ref<BoardFilters | null>(null), data = ref<BoardResult | null>(null)
const saved = ref<SavedBoardQuery[]>([]), selectedId = ref('')
const page = ref(1), pageSize = ref(25), total = ref(0)
const loading = ref(false), initializing = ref(false), exporting = ref(false), busy = ref(false)
const error = useLocaleMessage(), savedError = useLocaleMessage(), mutationError = useLocaleMessage(), exportError = useLocaleMessage()
const fieldErrors = ref<Record<string, string>>({}), warnings = ref<string[]>([])
const requestId = ref('')
const saveDialog = ref<HTMLDialogElement | null>(null), deleteDialog = ref<HTMLDialogElement | null>(null)
const queryName = ref(''), editTarget = ref<SavedBoardQuery | null>(null)
let revision = 0, identity = 0, timer: ReturnType<typeof setTimeout> | undefined
const invalid = computed(() => filters.value ? validateDefinition(definition.value, filters.value, locale.value) : '')
const selected = computed(() => saved.value.find(q => q.id === selectedId.value))
const dirty = computed(() => selected.value && JSON.stringify(selected.value.definition) !== JSON.stringify(definition.value))
const scopeControls = [{ key: 'regions', field: 'region' }, { key: 'sales', field: 'sales' }, { key: 'equipment', field: 'equipment' }, { key: 'markets', field: 'market' }] as const
const visibleGroups = computed(() => {
  if (!data.value) return []
  if (!definition.value.groupBy) return [{ key: null, label: '', rows: data.value.items, totals: null }]
  const group = definition.value.groupBy
  return data.value.groups.map(g => ({
    key: g.key, label: g.key == null ? copy('Not set', '未填写') : optionLabel(group, g.key, g.label, locale.value),
    rows: data.value!.items.filter(row => groupKey(row, group) === g.key), totals: g,
  })).filter(g => g.rows.length)
})
function report(reason: unknown) {
  error.value = requestErrorMessage(reason)
  if (reason instanceof CrmApiError) { fieldErrors.value = reason.fieldErrors; requestId.value = reason.requestId }
}
async function load() {
  clearTimeout(timer)
  const id = ++revision, session = identity
  data.value = null; total.value = 0; error.value = ''; fieldErrors.value = {}; warnings.value = []; requestId.value = ''
  if (!filters.value || !canView.value || invalid.value) { loading.value = false; return }
  loading.value = true
  try {
    const response = await props.apiClient.queryOpportunities(toQuery(definition.value, page.value, pageSize.value))
    if (id !== revision || session !== identity) return
    data.value = response.data; total.value = response.meta?.total ?? response.data.summary.count
    page.value = response.meta?.page ?? page.value
    pageSize.value = response.meta?.pageSize ?? pageSize.value
    warnings.value = response.warnings ?? []
  } catch (reason) { if (id === revision && session === identity) report(reason) }
  finally { if (id === revision && session === identity) loading.value = false }
}
function schedule() {
  clearTimeout(timer); revision++; data.value = null; total.value = 0; error.value = ''; fieldErrors.value = {}; page.value = 1
  if (!filters.value || !canView.value || invalid.value) { loading.value = false; return }
  loading.value = true
  timer = setTimeout(() => void load(), 300)
}
watch(() => JSON.stringify(toQuery(definition.value)), schedule)
async function loadSaved(session = identity) {
  savedError.value = ''
  try { const result = await props.apiClient.listOpportunityQueries(); if (session === identity) saved.value = result.data.items }
  catch (reason) { if (session === identity) savedError.value = requestErrorMessage(reason) }
}
async function initialize() {
  const session = identity
  initializing.value = true; error.value = ''
  const savedRequest = loadSaved(session)
  try {
    const response = await props.apiClient.getOpportunityFilters()
    if (session !== identity) return
    filters.value = response.data
    await load()
  } catch (reason) { if (session === identity) report(reason) }
  finally { if (session === identity) initializing.value = false }
  await savedRequest
}
watch(() => [app.bootstrap?.user.id, app.identityRevision, canView.value], () => {
  identity++; revision++; clearTimeout(timer)
  filters.value = null; data.value = null; saved.value = []; selectedId.value = ''; total.value = 0
  definition.value = initialDefinition(); error.value = ''; savedError.value = ''; exportError.value = ''; fieldErrors.value = {}
  loading.value = false; initializing.value = false; busy.value = false; exporting.value = false
  saveDialog.value?.close(); deleteDialog.value?.close()
  if (canView.value) void initialize()
}, { immediate: true, flush: 'sync' })
onMounted(() => app.loadBootstrap(props.apiClient))
onBeforeUnmount(() => { identity++; revision++; clearTimeout(timer) })
function applySaved(id: string) {
  const item = saved.value.find(q => q.id === id)
  selectedId.value = id
  if (item) { definition.value = JSON.parse(JSON.stringify(item.definition)); page.value = 1 }
}
function applyPreset(index: number) {
  selectedId.value = ''
  definition.value = { ...defaultDefinition(), scope: JSON.parse(JSON.stringify(definition.value.scope)), conditions: JSON.parse(JSON.stringify(presets[index].conditions)) }
}
function clear() { selectedId.value = ''; definition.value = defaultDefinition() }
function sort(column: BoardColumn) {
  if (column === 'amount') return
  definition.value.sort = { field: column, direction: definition.value.sort.field === column && definition.value.sort.direction === 'asc' ? 'desc' : 'asc' }
}
function toggleColumn(column: BoardColumn, checked: boolean) {
  const columns = definition.value.columns
  if (checked) definition.value.columns = allColumns.filter(c => c === column || columns.includes(c))
  else if (columns.length > 1) definition.value.columns = columns.filter(c => c !== column)
}
async function openSave(update: boolean) {
  editTarget.value = update && selected.value ? JSON.parse(JSON.stringify(selected.value)) : null
  queryName.value = editTarget.value?.name ?? ''
  mutationError.value = ''
  await nextTick(); saveDialog.value?.showModal()
}
async function saveQuery() {
  if (!queryName.value.trim() || invalid.value || busy.value) return
  const session = identity
  const input = { name: queryName.value.trim(), definition: JSON.parse(JSON.stringify(definition.value)) as BoardDefinition }
  const target = editTarget.value
  busy.value = true; mutationError.value = ''
  try {
    const response = await props.apiClient.saveOpportunityQuery(input, target?.id, target?.modified)
    if (session !== identity) return
    saved.value = [response.data, ...saved.value.filter(q => q.id !== response.data.id)]
    selectedId.value = response.data.id
    definition.value = JSON.parse(JSON.stringify(response.data.definition))
    saveDialog.value?.close()
  } catch (reason) {
    if (session !== identity) return
    mutationError.value = reason instanceof CrmApiError && reason.code === 'VERSION_CONFLICT'
      ? copy('This query changed elsewhere. Close this dialog and reload your saved queries before updating.', '该查询已在其他位置更新。请关闭窗口并刷新个人查询后重新编辑。')
      : requestErrorMessage(reason)
  } finally { if (session === identity) busy.value = false }
}
async function openDelete() {
  if (!selected.value) return
  editTarget.value = JSON.parse(JSON.stringify(selected.value)); mutationError.value = ''
  await nextTick(); deleteDialog.value?.showModal()
}
async function deleteQuery() {
  const target = editTarget.value, session = identity
  if (!target || busy.value) return
  busy.value = true; mutationError.value = ''
  try {
    await props.apiClient.deleteOpportunityQuery(target.id, target.modified)
    if (session !== identity) return
    saved.value = saved.value.filter(q => q.id !== target.id); selectedId.value = ''; deleteDialog.value?.close()
  } catch (reason) { if (session === identity) mutationError.value = requestErrorMessage(reason) }
  finally { if (session === identity) busy.value = false }
}
async function exportRows() {
  if (!data.value || exporting.value) return
  const session = identity, language = locale.value
  const snapshot = JSON.parse(JSON.stringify(definition.value)) as BoardDefinition
  exporting.value = true; exportError.value = ''
  try {
    const rows = await readBoardExport(props.apiClient, toQuery(snapshot), () => session !== identity)
    if (session !== identity) return
    downloadCustomerReport(boardWorkbook(rows, snapshot.columns, snapshot.groupBy, language))
  } catch (reason) {
    if (session !== identity) return
    exportError.value = reason instanceof Error && reason.message === 'EXPORT_CHANGED'
      ? copy('The results changed during export. Refresh and try again.', '导出期间查询结果发生变化，请刷新后重试。')
      : requestErrorMessage(reason)
  } finally { if (session === identity) exporting.value = false }
}
</script>

<template>
  <div v-if="!app.bootstrap" class="board-state" role="status">{{ app.error || copy('Loading account…', '正在读取账号…') }}<button v-if="app.error" @click="app.loadBootstrap(apiClient)">{{ copy('Retry', '重试') }}</button></div>
  <div v-else-if="!canView" class="board-state" role="alert">{{ copy('You do not have access to opportunities.', '当前账号没有商机查看权限。') }}</div>
  <div v-else class="opportunity-board-page" data-testid="opportunity-board-page">
    <section class="board-hero">
      <img class="board-brand-art" :src="brandIconUrl" alt="" aria-hidden="true" />
      <header class="board-heading">
        <div><h1>Opportunities <span>· {{ copy('Opportunity analysis', '商机分析') }}</span></h1><p>{{ copy('Current opportunities · CNY estimates', '当前商机 · 人民币预计金额') }}</p></div>
        <RouterLink v-if="app.bootstrap.user.role !== 'Engineer'" class="board-list-link" to="/opportunities">{{ copy('Open opportunity list', '打开商机列表') }} ↗</RouterLink>
      </header>
      <div class="board-controls">
      <nav class="board-navigation" :aria-label="copy('Cockpit pages', '看板页面')"><template v-if="manager"><template v-for="tab in (['review', 'plan', 'warnings'] as const)" :key="tab"><RouterLink v-if="!outgoing.blocked.length" :to="tabRoute(tab)">{{ tabNames[tab] }}</RouterLink><span v-else class="is-disabled" role="link" aria-disabled="true" aria-describedby="board-scope-blocked">{{ tabNames[tab] }}</span></template></template><strong aria-current="page">Opportunities</strong></nav>
      <p v-if="manager && outgoing.blocked.length" id="board-scope-blocked" class="board-scope-blocked" role="status" data-scope-blocked>{{ copy(`Review, Plan and Warnings show one value or all per filter. Select one value or All for ${blockedScope} to open them with this scope.`, `Review、Plan 和 Warnings 每项筛选只支持单个值或全部。请将${blockedScope}改为单个值或全部后再切换。`) }}</p>
      <div v-if="filters" class="board-scope">
        <div v-for="control in scopeControls" :key="control.key" class="scope-item"><span>{{ fieldLabel(control.field, locale) }}</span><BoardMultiSelect v-model="definition.scope[control.key]" :label="fieldLabel(control.field, locale)" :options="fieldOptions(control.field, filters, locale)" :disabled="control.key === 'regions' && !filters.regionReady" :placeholder="control.key === 'regions' && !filters.regionReady ? copy('Not ready', '尚未就绪') : copy('All', '全部')" /></div>
      </div>
      </div>
    </section>

    <section v-if="filters" class="board-query-panel">
      <header class="board-panel-heading"><div><h2><SlidersHorizontal :size="17" />{{ copy('Query builder', '组合查询') }}</h2><p>{{ copy('Combine conditions. Results and totals update together.', '组合筛选条件，列表与汇总同步更新。') }}</p></div><div class="query-tools"><div class="board-segmented"><button :class="{ active: definition.match === 'all' }" :aria-pressed="definition.match === 'all'" @click="definition.match = 'all'">{{ copy('All (AND)', '全部满足 (AND)') }}</button><button :class="{ active: definition.match === 'any' }" :aria-pressed="definition.match === 'any'" @click="definition.match = 'any'">{{ copy('Any (OR)', '任一满足 (OR)') }}</button></div><button data-add-condition :disabled="definition.conditions.length >= 20" @click="definition.conditions.push(condition())"><Plus :size="14" />{{ copy('Add condition', '添加条件') }}</button><button @click="clear">{{ copy('Clear', '清空') }}</button></div></header>
      <div class="board-presets"><span>{{ copy('Quick queries', '快捷查询') }}</span><button v-for="(preset, index) in presets" :key="preset.id" :data-preset="preset.id" @click="applyPreset(index)">{{ text(preset.label, locale) }}</button></div>
      <div v-if="definition.conditions.length" class="board-conditions"><BoardConditionRow v-for="(_, index) in definition.conditions" :key="index" v-model="definition.conditions[index]" :filters="filters" :index="index" :match="definition.match" @remove="definition.conditions.splice(index, 1)" /></div>
      <p v-else class="board-query-empty">{{ copy('Showing all opportunities in your selected scope. Add a condition or choose a quick query.', '当前显示所选范围内的全部商机。添加条件或选择快捷查询开始筛选。') }}</p>
      <p v-if="invalid" class="board-validation" role="status">{{ invalid }}</p>
      <footer class="board-saved">
        <label>{{ copy('My queries', '我的查询') }}<select :value="selectedId" data-saved-select @change="applySaved(($event.target as HTMLSelectElement).value)"><option value="">{{ copy('Choose a saved query', '选择已保存查询') }}</option><option v-for="item in saved" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
        <span v-if="dirty" class="query-dirty">{{ copy('Unsaved changes', '有未保存修改') }}</span>
        <button :disabled="!!invalid" data-save-new @click="openSave(false)"><Save :size="14" />{{ copy('Save as new', '另存查询') }}</button>
        <button v-if="selected" :disabled="!!invalid" data-update-query @click="openSave(true)">{{ copy('Update / rename', '更新／重命名') }}</button>
        <button v-if="selected" data-delete-query @click="openDelete">{{ copy('Delete', '删除') }}</button>
        <button class="icon-button" :aria-label="copy('Reload saved queries', '刷新个人查询')" @click="loadSaved()"><RefreshCw :size="14" /></button>
        <p v-if="savedError" class="board-error" role="alert">{{ savedError }}</p>
      </footer>
    </section>

    <div v-if="initializing || loading" class="board-state" role="status">{{ copy('Loading matching opportunities…', '正在查询匹配的商机…') }}</div>
    <div v-else-if="error" class="board-state board-error" role="alert"><strong>{{ error }}</strong><p v-for="(message, field) in fieldErrors" :key="field">{{ field }}: {{ message }}</p><small v-if="requestId">{{ requestId }}</small><button @click="filters ? load() : initialize()">{{ copy('Retry', '重试') }}</button></div>
    <template v-else-if="data">
      <div v-for="warning in warnings" :key="warning" class="board-validation" role="status">{{ warning }}</div>
      <section class="board-results-summary" aria-live="polite">
        <div class="board-total"><strong>{{ data.summary.count }} <small>{{ copy('opportunities', '个商机') }}</small></strong><span>{{ money(data.summary.knownAmountCny, locale) }}<small v-if="data.summary.missingAmountCount"> · {{ copy('known amounts only', '仅已填写金额') }}</small></span></div>
        <div class="board-probabilities"><div v-for="bucket in [...data.summary.byProbability].reverse()" :key="bucket.level" class="probability-chip" :class="bucket.level"><span>{{ optionLabel('probabilityLevel', bucket.level, '', locale) }} <b>{{ bucket.count }}</b></span><small>{{ money(bucket.knownAmountCny, locale) }}<span v-if="bucket.missingAmountCount"> · {{ bucket.missingAmountCount }} {{ copy('missing', '条未填金额') }}</span></small></div></div>
        <div class="board-quality"><span v-if="data.summary.stageUnchangedOver21DaysCount" class="stage-warning">{{ data.summary.stageUnchangedOver21DaysCount }} {{ copy('open opportunities with no stage change > 21 days', '个开放商机超过 21 天无阶段变化') }}</span><span v-if="data.summary.missingAmountCount">{{ data.summary.missingAmountCount }} {{ copy('CNY amounts missing', '条人民币金额未填写') }}</span><span v-if="data.summary.unknownStageAgeCount">{{ data.summary.unknownStageAgeCount }} {{ copy('stage dates unknown', '条阶段日期未知') }}</span></div>
      </section>
      <section class="board-table-panel">
        <header class="board-table-tools"><div><h2>{{ copy('Matching opportunities', '匹配商机') }}</h2><p>{{ copy('As of', '数据时间') }} {{ new Date(data.asOf).toLocaleString(locale, { timeZone: 'Asia/Shanghai' }) }} · UTC+8</p></div>
          <div class="table-actions"><details class="board-columns"><summary>{{ copy('Columns', '显示列') }} ▾</summary><div><label v-for="column in allColumns" :key="column"><input type="checkbox" :checked="definition.columns.includes(column)" :disabled="definition.columns.length === 1 && definition.columns.includes(column)" @change="toggleColumn(column, ($event.target as HTMLInputElement).checked)" />{{ fieldLabel(column, locale) }}</label></div></details>
          <label>{{ copy('Group by', '分组') }}<select v-model="definition.groupBy" data-group-by><option :value="null">{{ copy('None', '不分组') }}</option><option v-for="group in groupFields" :key="group" :value="group" :disabled="group === 'region' && !filters?.regionReady">{{ fieldLabel(group, locale) }}</option></select></label>
          <button :disabled="exporting || !total" class="board-export" data-export @click="exportRows"><Download :size="15" />{{ exporting ? copy('Exporting…', '正在导出…') : copy('Export Excel', '导出 Excel') }}<span v-if="!exporting"> · {{ total }}</span></button></div>
        </header>
        <p v-if="exportError" class="board-error" role="alert">{{ exportError }}</p>
        <div class="board-table-scroll"><table class="board-table"><thead><tr><th v-for="column in definition.columns" :key="column" :aria-sort="definition.sort.field === column ? definition.sort.direction === 'asc' ? 'ascending' : 'descending' : 'none'"><span v-if="column === 'amount'">{{ fieldLabel(column, locale) }}</span><button v-else @click="sort(column)">{{ fieldLabel(column, locale) }}<span v-if="definition.sort.field === column">{{ definition.sort.direction === 'asc' ? ' ↑' : ' ↓' }}</span></button></th></tr></thead>
          <tbody v-for="group in visibleGroups" :key="group.key ?? '__ungrouped'">
            <tr v-if="group.totals" class="board-group-row"><th :colspan="definition.columns.length">{{ group.label }}<span>{{ group.totals.count }} {{ copy('opportunities', '个商机') }} · {{ money(group.totals.knownAmountCny, locale) }}<template v-if="group.totals.missingAmountCount"> · {{ group.totals.missingAmountCount }} {{ copy('amounts missing', '条未填金额') }}</template></span></th></tr>
            <tr v-for="row in group.rows" :key="row.id" :data-opportunity="row.id"><td v-for="column in definition.columns" :key="column" :class="['col-' + column, { 'stage-warning': column === 'stageChangedAt' && row.stageUnchangedOver21Days }]">
              <RouterLink v-if="(column === 'customerName' || column === 'title') && app.bootstrap.user.role !== 'Engineer'" :to="{ name: 'opportunity-detail', params: { opportunityId: row.id } }">{{ cellText(row, column, locale) }}<small v-if="column === 'customerName' && !definition.columns.includes('title')">{{ row.title }}</small></RouterLink>
              <span v-else-if="column === 'probabilityLevel'" class="probability-badge" :class="row.probabilityLevel ?? 'pending'">{{ cellText(row, column, locale) }}</span>
              <span v-else-if="column === 'stage'" class="stage-badge">{{ cellText(row, column, locale) }}</span>
              <span v-else>{{ cellText(row, column, locale) }}</span>
            </td></tr>
          </tbody>
        </table></div>
        <div v-if="!data.items.length" class="board-state">{{ total ? copy('No records on this page.', '当前页没有记录。') : copy('No opportunities match. Try changing or clearing your filters.', '没有匹配的商机，请调整或清空筛选条件。') }}<button v-if="total" @click="page = 1; load()">{{ copy('First page', '返回第一页') }}</button></div>
        <PaginationControls :page="page" :page-size="pageSize" :total="total" @change="page = $event; load()" @page-size-change="pageSize = $event; page = 1; load()" />
        <footer class="board-table-note">{{ copy('Amounts are unweighted opportunity estimates. Stage age does not measure customer follow-up activity.', '金额为未加权商机预计值；阶段停留时间不代表客户跟进间隔。') }}</footer>
      </section>
    </template>

    <dialog ref="saveDialog" class="board-dialog" :aria-label="copy('Save query', '保存查询')" @cancel="busy && $event.preventDefault()">
      <form @submit.prevent="saveQuery"><header><h2>{{ editTarget ? copy('Update query', '更新查询') : copy('Save query', '保存查询') }}</h2><button type="button" :disabled="busy" :aria-label="copy('Close', '关闭')" @click="saveDialog?.close()"><X :size="18" /></button></header><p>{{ copy('Save your filters, columns and grouping. Only you can access this query.', '保存筛选条件、显示列和分组，仅自己可见。') }}</p><label>{{ copy('Query name', '查询名称') }}<input v-model="queryName" data-query-name required maxlength="80" :disabled="busy" autofocus /></label><p v-if="mutationError" role="alert" class="board-error">{{ mutationError }}</p><footer><button type="button" :disabled="busy" @click="saveDialog?.close()">{{ copy('Cancel', '取消') }}</button><button class="board-primary" data-confirm-save :disabled="busy || !queryName.trim()">{{ busy ? copy('Saving…', '保存中…') : copy('Save', '保存') }}</button></footer></form>
    </dialog>
    <dialog ref="deleteDialog" class="board-dialog" :aria-label="copy('Delete query', '删除查询')" @cancel="busy && $event.preventDefault()">
      <form @submit.prevent="deleteQuery"><h2>{{ copy('Delete saved query?', '删除已保存查询？') }}</h2><p>{{ editTarget?.name }}</p><p>{{ copy('Opportunity records will remain available.', '删除查询不会删除商机记录。') }}</p><p v-if="mutationError" role="alert" class="board-error">{{ mutationError }}</p><footer><button type="button" :disabled="busy" @click="deleteDialog?.close()">{{ copy('Cancel', '取消') }}</button><button class="board-danger" data-confirm-delete :disabled="busy">{{ busy ? copy('Deleting…', '删除中…') : copy('Delete query', '删除查询') }}</button></footer></form>
    </dialog>
  </div>
</template>
<style src="@/features/opportunity-board/board.css"></style>

