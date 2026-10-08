<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { api as defaultApi, type CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import { resolveLocaleMessage, useI18n, type LocaleMessage } from '@/i18n'
import { useAppStore } from '@/stores/app'
import type { Territory, TerritoryAssignment, TerritoryAssignmentInput, TerritoryCatalogue, TerritoryInput } from '@/features/territories/types'
import PageHeader from '@/design-system/PageHeader.vue'
import DataState from '@/design-system/DataState.vue'
import { regionLabel } from '@/domain/regions'
import StatusBadge from '@/design-system/StatusBadge.vue'
import { Pencil, Plus, RotateCcw } from '@lucide/vue'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const app = useAppStore(), { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const manager = computed(() => app.bootstrap?.user.role === 'Manager')
const data = ref<TerritoryCatalogue | null>(null)
const loading = ref(true), busy = ref(false)
// The refusal as received; `error` shows it in the current language. Focus goes to a new refusal only:
// switching the language re-renders the same one and must leave focus on the language control.
const refusal = ref<LocaleMessage>('')
const error = computed({ get: () => resolveLocaleMessage(refusal.value), set: (next: LocaleMessage) => { refusal.value = next } })
const errorContext = ref<'page' | 'territory' | 'assignment'>('page')
const errorFeedback = ref<HTMLElement | null>(null)
watch(refusal, async value => {
  if (!value) return
  await nextTick()
  errorFeedback.value?.focus()
  errorFeedback.value?.scrollIntoView?.({ block: 'nearest' })
})
// The bootstrap could not be read (a transient failure at startup): the page says so and offers a retry, in
// place of telling a Manager that the page is for Managers only.
const bootstrapFailed = ref(false)
const editedTerritory = ref<Territory | null>(null), editedAssignment = ref<TerritoryAssignment | null>(null)
const territory = ref<TerritoryInput>({ name: '', parent: null, isGroup: false, enabled: true, sortOrder: 0 })
const assignment = ref<TerritoryAssignmentInput>({ territory: '', salesOwner: '', validFrom: '', validUntil: null, cancelled: false, note: '' })
const selectedRegion = ref('')
let loadRevision = 0
const regions = computed(() => data.value?.territories.filter(row => !row.isGroup) ?? [])
const assignments = computed(() => data.value?.assignments.filter(row => row.territory === selectedRegion.value) ?? [])
const tree = computed(() => {
  const result: { row: Territory; depth: number }[] = [], seen = new Set<string>()
  const rows = [...(data.value?.territories ?? [])].sort((a, b) => a.sortOrder - b.sortOrder || a.name.localeCompare(b.name))
  function visit(parent: string | null, depth: number) {
    for (const row of rows.filter(item => item.parent === parent)) {
      if (seen.has(row.name)) continue
      seen.add(row.name); result.push({ row, depth }); visit(row.name, depth + 1)
    }
  }
  visit(null, 0)
  for (const row of rows) if (!seen.has(row.name)) result.push({ row, depth: 0 })
  return result
})
const parentOptions = computed(() => data.value?.territories.filter(row => row.isGroup && row.enabled && row.name !== editedTerritory.value?.name) ?? [])
const salesName = (id: string) => data.value?.sales.find(row => row.id === id)?.name || id
function currentOwner(name: string) {
  const today = data.value?.today ?? ''
  const rows = data.value?.assignments.filter(row => row.territory === name && !row.cancelled && row.validFrom <= today && (!row.validUntil || row.validUntil >= today)) ?? []
  return rows.length === 1 ? salesName(rows[0]!.salesOwner) : copy('Unassigned', '未分配')
}
async function load() {
  const revision = ++loadRevision
  loading.value = true; error.value = ''; errorContext.value = 'page'
  try {
    const response = await props.apiClient.getTerritoryCatalogue()
    if (revision !== loadRevision) return
    data.value = response.data
    if (!selectedRegion.value) selectedRegion.value = regions.value[0]?.name ?? ''
  } catch (reason) { if (revision === loadRevision) { const mapped = mapRequestError(reason); error.value = mapped.localizedMessage ?? mapped.message } }
  finally { if (revision === loadRevision) loading.value = false }
}
function editTerritory(row?: Territory, unmapped = '') {
  editedTerritory.value = row ?? null
  territory.value = row ? { name: row.name, parent: row.parent, isGroup: row.isGroup, enabled: row.enabled, sortOrder: row.sortOrder } : { name: unmapped, parent: null, isGroup: false, enabled: true, sortOrder: 0 }
}
function editAssignment(row?: TerritoryAssignment) {
  editedAssignment.value = row ?? null
  assignment.value = row ? { territory: row.territory, salesOwner: row.salesOwner, validFrom: row.validFrom, validUntil: row.validUntil, cancelled: row.cancelled, note: row.note } : { territory: selectedRegion.value, salesOwner: '', validFrom: data.value?.today ?? '', validUntil: null, cancelled: false, note: '' }
}
function selectRegion() { editAssignment() }
async function saveTerritory() {
  busy.value = true; error.value = ''; errorContext.value = 'territory'
  try {
    await props.apiClient.saveTerritory({ ...territory.value }, editedTerritory.value?.name, editedTerritory.value?.modified)
    editTerritory(); await load()
  } catch (reason) { const mapped = mapRequestError(reason); error.value = mapped.localizedMessage ?? mapped.message }
  finally { busy.value = false }
}
async function saveAssignment() {
  busy.value = true; error.value = ''; errorContext.value = 'assignment'
  try {
    await props.apiClient.saveTerritoryAssignment({ ...assignment.value, validUntil: assignment.value.validUntil || null }, editedAssignment.value?.id, editedAssignment.value?.modified)
    await load(); editAssignment()
  } catch (reason) { const mapped = mapRequestError(reason); error.value = mapped.localizedMessage ?? mapped.message }
  finally { busy.value = false }
}
async function reload() { await load(); editTerritory(); editAssignment() }
async function start() {
  loading.value = true; bootstrapFailed.value = false; error.value = ''
  await app.loadBootstrap(props.apiClient)
  if (!app.bootstrap) {
    bootstrapFailed.value = true
    error.value = app.error || copy('The current user could not be read.', '无法读取当前用户信息。')
    loading.value = false
    return
  }
  if (manager.value) { await load(); editAssignment() } else loading.value = false
}
onMounted(start)
</script>

<template>
  <div class="territories-page">
    <PageHeader eyebrow="SALES TERRITORIES" :title="copy('Territories and sales responsibility', '地域与销售归属')" :description="copy('Maintain the territory tree and dated sales responsibility.', '维护地域层级和分时段的销售负责人。')">
      <button v-if="manager" class="secondary-button" type="button" :disabled="busy" @click="reload"><RotateCcw :size="14" />{{ copy('Reload and discard draft', '重新加载并放弃草稿') }}</button>
    </PageHeader>
    <DataState v-if="!manager && !loading && !bootstrapFailed" type="denied" :message="copy('Available to Managers only.', '仅经理可维护。')" />
    <div v-if="error && errorContext === 'page'" ref="errorFeedback" tabindex="-1" class="form-error" role="alert"><span>{{ error }}</span><button v-if="bootstrapFailed && !loading" class="secondary-button" type="button" data-testid="territories-retry" @click="start">{{ copy('Try again', '重试') }}</button></div>
    <DataState v-if="loading" type="loading" />
    <template v-else-if="manager && data">
      <p class="note">{{ copy('A sales user can cover several regions. Each region has one responsible sales user for any date. Existing access permissions continue to apply.', '一名销售可负责多个区域，同一区域在同一天只有一名负责人。业务资料仍按现有权限访问。') }}</p>
      <section v-if="data.unmappedRegions.length" class="card">
        <h2>{{ copy('Regions awaiting placement', '待挂接区域') }}</h2>
        <p class="note">{{ copy('Existing region names are preserved. Choose a name, then its parent in the form below.', '保留现有区域名称；选中后在下方设置所属层级。') }}</p>
        <div class="chip-row"><button v-for="name in data.unmappedRegions" :key="name" class="secondary-button" type="button" :disabled="busy" @click="editTerritory(undefined, name)">{{ regionLabel(name, locale) }}</button></div>
      </section>
      <div class="columns">
        <section class="card flush">
          <h2 class="card-title">{{ copy('Territory tree', '地域树') }}</h2>
          <div class="table-scroll"><table class="crm-table"><thead><tr><th>{{ copy('Territory', '地域') }}</th><th>{{ copy('Current owner', '当前负责人') }}</th><th>{{ copy('Status', '状态') }}</th><th /></tr></thead>
            <tbody><tr v-for="entry in tree" :key="entry.row.name"><td :style="{ paddingLeft: `${15 + entry.depth * 18}px` }"><strong :class="{ group: entry.row.isGroup }">{{ regionLabel(entry.row.name, locale) }}</strong></td><td>{{ entry.row.isGroup ? '—' : currentOwner(entry.row.name) }}</td><td><StatusBadge :label="entry.row.enabled ? copy('Active', '启用') : copy('Inactive', '停用')" :tone="entry.row.enabled ? 'positive' : 'neutral'" /></td><td class="row-action"><button class="secondary-button compact" type="button" :disabled="busy" @click="editTerritory(entry.row)"><Pencil :size="13" />{{ copy('Edit', '编辑') }}</button></td></tr></tbody>
          </table></div>
        </section>
        <form class="card editor" data-territory-form @submit.prevent="saveTerritory">
          <h2>{{ editedTerritory ? copy('Edit territory', '编辑地域') : copy('Add territory', '新增地域') }}</h2>
          <label><span>{{ copy('English name', '英文名称') }}</span><input v-model="territory.name" aria-label="Territory name" required maxlength="100" :disabled="!!editedTerritory || busy" /></label>
          <label><span>{{ copy('Parent', '上级地域') }}</span><select v-model="territory.parent" aria-label="Parent territory" :disabled="busy"><option :value="null">{{ copy('Top level', '顶层') }}</option><option v-for="row in parentOptions" :key="row.name" :value="row.name">{{ regionLabel(row.name, locale) }}</option></select></label>
          <label><span>{{ copy('Node type', '节点类型') }}</span><select v-model="territory.isGroup" aria-label="Territory type" :disabled="!!editedTerritory || busy"><option :value="false">{{ copy('Region: assign sales here', '区域：在此分配销售') }}</option><option :value="true">{{ copy('Group: contains territories', '分组：下设地域') }}</option></select></label>
          <label><span>{{ copy('Display order', '显示顺序') }}</span><input v-model.number="territory.sortOrder" type="number" min="-10000" max="10000" step="1" :disabled="busy" /></label>
          <label class="check"><input v-model="territory.enabled" type="checkbox" :disabled="busy" />{{ copy('Active for new assignments', '启用新的销售归属') }}</label>
          <p class="note">{{ copy('Names and node types stay fixed. Inactive regions keep their records and remain available in historical filters.', '名称和节点类型保存后固定。停用区域保留业务记录，历史筛选仍可选择。') }}</p>
          <p v-if="error && errorContext === 'territory'" ref="errorFeedback" tabindex="-1" class="form-error" role="alert">{{ error }}</p>
          <div class="form-actions"><button class="primary-button" type="submit" :disabled="busy">{{ copy('Save territory', '保存地域') }}</button><button type="button" class="secondary-button" :disabled="busy" @click="editTerritory()"><Plus :size="14" />{{ copy('New', '新增') }}</button></div>
        </form>
      </div>
      <section class="card">
        <div class="card-head"><h2>{{ copy('Sales assignment history', '销售归属记录') }}</h2><select v-model="selectedRegion" class="filter-control" aria-label="Assignment region" :disabled="busy" @change="selectRegion"><option v-for="row in regions" :key="row.name" :value="row.name">{{ regionLabel(row.name, locale) }}{{ row.enabled ? '' : copy(' (inactive)', '（停用）') }}</option></select></div>
        <div class="table-scroll"><table class="crm-table"><thead><tr><th>{{ copy('Sales', '销售') }}</th><th>{{ copy('From', '生效日') }}</th><th>{{ copy('Through', '截止日') }}</th><th>{{ copy('Status / note', '状态／备注') }}</th><th /></tr></thead><tbody><tr v-for="row in assignments" :key="row.id"><td><strong>{{ salesName(row.salesOwner) }}</strong></td><td>{{ row.validFrom }}</td><td>{{ row.validUntil || copy('Ongoing', '持续有效') }}</td><td><div class="status-note"><StatusBadge :label="row.cancelled ? copy('Cancelled', '已撤销') : copy('Recorded', '已登记')" :tone="row.cancelled ? 'neutral' : 'info'" /><span class="note-text">{{ row.note }}</span></div></td><td class="row-action"><button class="secondary-button compact" type="button" :disabled="busy" @click="editAssignment(row)"><Pencil :size="13" />{{ copy('Edit', '编辑') }}</button></td></tr></tbody></table></div>
        <p v-if="!assignments.length" class="empty">{{ copy('No assignment recorded.', '尚无归属记录。') }}</p>
        <form v-if="selectedRegion" class="assignment-editor editor" data-assignment-form @submit.prevent="saveAssignment">
          <div class="form-grid">
            <label><span>{{ copy('Sales owner', '销售负责人') }}</span><select v-model="assignment.salesOwner" aria-label="Sales owner" required :disabled="busy || !!editedAssignment"><option value="">{{ copy('Choose Sales', '选择销售') }}</option><option v-for="person in data.sales" :key="person.id" :value="person.id">{{ person.name }}</option><option v-if="assignment.salesOwner && !data.sales.some(row => row.id === assignment.salesOwner)" :value="assignment.salesOwner">{{ assignment.salesOwner }}</option></select></label>
            <label><span>{{ copy('Change note', '变更说明') }}</span><input v-model="assignment.note" aria-label="Assignment note" maxlength="2000" :disabled="busy" /></label>
            <label><span>{{ copy('Effective from', '生效日期') }}</span><input v-model="assignment.validFrom" aria-label="Effective from" type="date" required :disabled="busy" /></label>
            <label><span>{{ copy('Effective through (inclusive)', '截止日期（含当天）') }}</span><input v-model="assignment.validUntil" aria-label="Effective through" type="date" :min="assignment.validFrom" :disabled="busy" /></label>
            <label class="check wide"><input v-model="assignment.cancelled" type="checkbox" :disabled="busy" />{{ copy('Cancel this assignment', '撤销此归属记录') }}</label>
          </div>
          <p class="note">{{ copy('End the previous period before adding its successor. Dates include both endpoints; cancelled entries stay in history.', '先结束原归属期间，再增加下一任负责人；起止日期均含当天，撤销后保留记录。') }}</p>
          <p v-if="error && errorContext === 'assignment'" ref="errorFeedback" tabindex="-1" class="form-error" role="alert">{{ error }}</p>
          <div class="form-actions"><button class="primary-button" type="submit" :disabled="busy">{{ copy('Save assignment', '保存归属') }}</button><button type="button" class="secondary-button" :disabled="busy" @click="editAssignment()"><Plus :size="14" />{{ copy('New assignment', '新增归属') }}</button></div>
        </form>
      </section>
    </template>
  </div>
</template>

<style scoped>
.territories-page{display:grid;gap:16px}
.columns{display:grid;grid-template-columns:1.5fr 1fr;gap:16px;align-items:start}
.card{padding:20px;background:var(--crm-surface-raised);border:1px solid var(--crm-line);border-radius:var(--crm-radius-md);min-width:0}
.card.flush{padding:0;overflow:hidden}
.card h2{margin:0 0 12px;color:var(--crm-navy);font-size:15px}
.card-title{padding:19px 20px 0}
.card-head{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}
.card-head h2{margin:0;flex-shrink:0}
.card-head .filter-control{min-width:0;max-width:100%}
.note{margin:0;color:var(--crm-text-muted);font-size:12px;line-height:1.7}
.empty{margin:12px 0 0;color:var(--crm-text-muted);font-size:11px}
.chip-row{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.table-scroll{overflow:auto}
.crm-table td{height:52px}
.crm-table strong.group{color:var(--crm-navy)}
.row-action{text-align:right;white-space:nowrap}
.status-note{display:flex;align-items:center;gap:8px}
.status-note .note-text{color:var(--crm-text-muted)}
.secondary-button.compact{min-height:30px;padding:0 10px}
.form-error{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0;padding:10px 12px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:11px}
.editor{display:grid;gap:14px}
.editor label{display:grid;gap:6px}
.editor label>span{color:var(--crm-text-muted);font-size:9px;font-weight:700}
.editor input:not([type=checkbox]),.editor select{min-height:38px;max-width:100%;padding:0 10px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:8px;font:inherit}
.editor input:focus,.editor select:focus{border-color:var(--crm-teal);outline:0}
.editor .check{display:flex;align-items:center;gap:8px;font-size:11px}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.form-grid .wide{grid-column:1/-1}
.form-actions{display:flex;gap:8px}
.assignment-editor{margin-top:18px;padding:16px;max-width:760px;background:var(--crm-surface);border-radius:10px}
@media(max-width:960px){.columns,.form-grid{grid-template-columns:1fr}.form-grid .wide{grid-column:auto}}
@media(max-width:700px){.card-head{align-items:flex-start;flex-direction:column}.card-head .filter-control{width:100%}}
</style>
