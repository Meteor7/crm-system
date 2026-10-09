<script setup lang="ts">
import { personnelDisplayName } from '@/demo/personnel'
import { formatDisplayDate } from '@/domain/time'
import { computed, onMounted, ref, watch } from 'vue'
import { BriefcaseBusiness, Kanban, List, Plus } from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import { api as defaultApi, type CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import {
  OPPORTUNITY_PROBABILITY_LEVELS,
  PENDING_PROBABILITY_LEVEL_FILTER,
  matchesOpportunityProbabilityLevelFilter,
  normalizeOpportunityProbabilityLevelFilter,
  opportunityProbabilityLevelLabel,
  opportunityProbabilityLevelTone,
} from '@/domain/opportunity-probability'
import { OPPORTUNITY_STAGES, OPTIONAL_OPPORTUNITY_STAGE, isOpportunityStage, opportunityStageLabel } from '@/domain/opportunity-stages'
import DataState from '@/design-system/DataState.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import PaginationControls from '@/features/shared/PaginationControls.vue'
import { readAllPages } from '@/features/shared/read-all-pages'
import { ownerFilterOptions } from '@/features/shared/owner-filter'
import { sitesByAccountId } from '@/features/accounts/account-sites'
import OpportunityEditorModal from './OpportunityEditorModal.vue'
import { useAppStore } from '@/stores/app'
import type { AccountSummaryDto, ArchiveState, SiteDto } from '@/types/crm'
import type { CreateStrategyOpportunityInput, OpportunityProbabilityLevelFilter, OpportunityStageSummaryDto, StrategyOpportunityDto, StrategyOpportunityListQuery } from '@/types/workspaces'
import { formatKnownTotals, formatMoney, formatSummedTotals } from '@/domain/money'
import { EQUIPMENT_PRESETS } from '@/domain/equipment'
import { loadEquipmentTypes } from '@/features/opportunities/equipment-types'
import { useI18n, useLocaleMessage } from '@/i18n'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const app = useAppStore()
const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()
const rows = ref<StrategyOpportunityDto[]>([])
// What rows holds: the page the list shows, or every matching Opportunity, which the board shows as cards.
const rowsScope = ref<'page' | 'all'>('page')
// Count and totals per stage of everything the filters match, as the server added them up in one request.
// The board shows these. Adding up the cards instead would mix pages fetched at different moments.
const stageSummary = ref<Map<string, OpportunityStageSummaryDto> | null>(null)
const total = ref(0)
const page = ref(typeof route.query.page === 'string' && Number(route.query.page) > 0 ? Number(route.query.page) : 1)
const pageSize = ref(typeof route.query.pageSize === 'string' && [10, 12, 25, 50].includes(Number(route.query.pageSize)) ? Number(route.query.pageSize) : 12)
const accounts = ref<AccountSummaryDto[]>([])
const sitesByAccount = ref<Record<string, SiteDto[]>>({})
// The Accounts come with the rows, the Sites after them; the editor, opened meanwhile, says so until they are here.
const referencesLoading = ref(true)
const loading = ref(true)
const denied = ref(false)
const error = useLocaleMessage()
const requestId = ref('')
const busy = ref(false)
const modalError = useLocaleMessage()
const editorOpen = ref(false)
const equipmentTypes = ref<string[]>([...EQUIPMENT_PRESETS])
watch(editorOpen, (open) => { if (open) void loadEquipmentTypes(props.apiClient).then((types) => { equipmentTypes.value = types }) })
// The layout is kept in the address like the filters: the shell mounts the page anew whenever the address changes.
const layout = ref<'list' | 'board'>(normalizeLayout(route.query.layout))
const wantedScope = computed(() => layout.value === 'board' ? 'all' : 'page')
const stage = ref(normalizeStageFilter(route.query.status))
const probabilityLevel = ref<OpportunityProbabilityLevelFilter>(normalizeOpportunityProbabilityLevelFilter(route.query.probabilityLevel))
const owner = ref(typeof route.query.owner === 'string' ? route.query.owner : 'All')
// Archived Opportunities (a Manager's archive, in place of a delete) are shown only when asked for.
const normalizeArchive = (value: unknown): ArchiveState => value === 'archived' || value === 'all' ? value : 'active'
const archiveState = ref<ArchiveState>(normalizeArchive(route.query.archive))
let sequence = 0
const canWrite = computed(() => app.can('deal:write'))
const owners = computed(() => ownerFilterOptions(app.bootstrap?.user, rows.value.map((item) => item.owner), owner.value))
const requestedAccountId = computed(() => typeof route.query.accountId === 'string' ? route.query.accountId : '')
const requestedOpportunityId = computed(() => typeof route.query.opportunityId === 'string' ? route.query.opportunityId : '')
const opportunityAccounts = computed(() => {
  const requested = accounts.value.find((account) => account.id === requestedAccountId.value)
  return requested ? [requested, ...accounts.value.filter((account) => account.id !== requested.id)] : accounts.value
})
const visibleRows = computed(() => {
  return rows.value.filter((item) =>
    (stage.value === 'All' || item.stage === stage.value) &&
    matchesOpportunityProbabilityLevelFilter(item.probabilityLevel, probabilityLevel.value) &&
    (owner.value === 'All' || item.owner === owner.value),
  )
})
const boardRows = computed(() => Object.fromEntries(
  OPPORTUNITY_STAGES.map((item) => [item, visibleRows.value.filter((opportunity) => opportunity.stage === item)]),
) as Record<(typeof OPPORTUNITY_STAGES)[number], StrategyOpportunityDto[]>)
const boardLimits = ref(Object.fromEntries(OPPORTUNITY_STAGES.map((item) => [item, 5])) as Record<(typeof OPPORTUNITY_STAGES)[number], number>)
const visibleBoardRows = computed(() => Object.fromEntries(
  OPPORTUNITY_STAGES.map((item) => [item, boardRows.value[item].slice(0, boardLimits.value[item])]),
) as Record<(typeof OPPORTUNITY_STAGES)[number], StrategyOpportunityDto[]>)
function loadMoreStage(stageName: (typeof OPPORTUNITY_STAGES)[number]) { boardLimits.value[stageName] += 5 }
function resetBoardLimits() { OPPORTUNITY_STAGES.forEach((item) => { boardLimits.value[item] = 5 }) }

function normalizeLayout(value: unknown): 'list' | 'board' {
  return value === 'board' ? 'board' : 'list'
}
// A bookmarked link may still carry a retired stage name; it falls back to all stages.
function normalizeStageFilter(value: unknown): string {
  return isOpportunityStage(value) ? value : 'All'
}
function stageLabel(value: string) {
  return opportunityStageLabel(value, locale.value)
}
// A server without the summary leaves the board to count the cards it has read.
function stageCount(stageName: (typeof OPPORTUNITY_STAGES)[number]) {
  return stageSummary.value ? stageSummary.value.get(stageName)?.count ?? 0 : boardRows.value[stageName].length
}
// Known amounts only, with how many are not entered yet, so a partial total never reads as complete.
function stageMoney(stageName: (typeof OPPORTUNITY_STAGES)[number]) {
  const unknownLabel = (count: number) => t('opportunities.unknownAmountCount', { count })
  if (!stageSummary.value) return formatKnownTotals(boardRows.value[stageName], unknownLabel)
  const summary = stageSummary.value.get(stageName)
  return summary ? formatSummedTotals(summary.totals, summary.unknownAmountCount, unknownLabel) : ''
}
// Everything the board shows: the stage summary and the first cards come in one request, which is one
// moment. Further pages only add cards; a row that moved between two of them is shown once.
async function readBoard(filters: StrategyOpportunityListQuery) {
  const first = await props.apiClient.listStrategyOpportunities({ ...filters, page: 1, pageSize: 200, stageSummary: true })
  const cards = new Map(first.data.items.map((item) => [item.id, item]))
  const matching = first.meta?.total ?? first.data.items.length
  let received = first.data.items.length
  for (let nextPage = 2; received < matching; nextPage += 1) {
    const next = await props.apiClient.listStrategyOpportunities({ ...filters, page: nextPage, pageSize: 200 })
    if (!next.data.items.length) break
    next.data.items.forEach((item) => cards.set(item.id, item))
    received += next.data.items.length
  }
  return { items: [...cards.values()], total: matching, stageSummary: first.data.stageSummary ?? null }
}
function amountText(value: StrategyOpportunityDto['amount'], currency: string) {
  return value ? formatMoney(value, currency) : t('oppEditor.amountPending')
}
let restoringRoute = false
// One reload for the three filters together, not one for each of them.
function resetFilters() {
  restoringRoute = true
  stage.value = 'All'
  probabilityLevel.value = 'All'
  owner.value = 'All'
  archiveState.value = 'active'
  restoringRoute = false
  reloadFromFirstPage()
}
// `create` opened the editor once, when the page was reached; kept in the address it would open it again on every remount.
function syncUrl() { if (!restoringRoute) void router.replace({ query: { ...route.query, create: undefined, page: String(page.value), pageSize: String(pageSize.value), status: stage.value === 'All' ? undefined : stage.value, probabilityLevel: probabilityLevel.value === 'All' ? undefined : probabilityLevel.value, owner: owner.value === 'All' ? undefined : owner.value, archive: archiveState.value === 'active' ? undefined : archiveState.value, layout: layout.value === 'board' ? 'board' : undefined } }) }
function goPage(target: number) { page.value = target; syncUrl(); void load() }
function changePageSize(value: number) { pageSize.value = value; page.value = 1; syncUrl(); void load() }
function reloadFromFirstPage() { if (restoringRoute) return; page.value = 1; resetBoardLimits(); syncUrl(); void load() }
function changeLayout() { if (restoringRoute) return; resetBoardLimits(); syncUrl(); void load() }
async function load() {
  const current = ++sequence
  loading.value = true
  referencesLoading.value = true
  denied.value = false
  error.value = ''
  const scope = wantedScope.value
  const contactId = typeof route.query.contactId === 'string' ? route.query.contactId : ''
  const filters = { status: stage.value, probabilityLevel: probabilityLevel.value, owner: owner.value, archiveState: archiveState.value, accountId: requestedAccountId.value, contactId, opportunityId: requestedOpportunityId.value }
  try {
    const [opportunityResult, accountRows] = await Promise.all([
      scope === 'all'
        ? readBoard(filters)
        : props.apiClient.listStrategyOpportunities({ ...filters, page: page.value, pageSize: pageSize.value }).then((result) => ({ items: result.data.items, total: result.meta?.total, stageSummary: null })),
      readAllPages((currentPage, currentPageSize) => props.apiClient.listAccounts({ page: currentPage, pageSize: currentPageSize })),
    ])
    if (current !== sequence) return
    rows.value = requestedOpportunityId.value
      ? opportunityResult.items.filter((item) => item.id === requestedOpportunityId.value)
      : contactId
        ? opportunityResult.items.filter((item) => item.stakeholders.some((person) => person.contactId === contactId))
        : opportunityResult.items
    rowsScope.value = scope
    stageSummary.value = opportunityResult.stageSummary && new Map(opportunityResult.stageSummary.map((item) => [item.stage, item]))
    total.value = opportunityResult.total ?? rows.value.length
    accounts.value = accountRows
    if (app.can('contact:view')) {
      const sites = await props.apiClient.listAccountSites()
      if (current !== sequence) return
      sitesByAccount.value = sitesByAccountId(accounts.value, sites.data)
    } else {
      sitesByAccount.value = {}
    }
  } catch (reason) {
    if (current !== sequence) return
    const mapped = mapRequestError(reason)
    error.value = mapped.localizedMessage ?? mapped.message
    requestId.value = mapped.requestId
    denied.value = mapped.denied
  } finally {
    if (current === sequence) {
      loading.value = false
      referencesLoading.value = false
    }
  }
}
async function saveOpportunity(input: CreateStrategyOpportunityInput) {
  busy.value = true
  modalError.value = ''
  try {
    const result = await props.apiClient.createStrategyOpportunity(input)
    editorOpen.value = false
    await router.push({ name: 'opportunity-detail', params: { opportunityId: result.data.id } })
  } catch (reason) {
    const mapped = mapRequestError(reason); modalError.value = mapped.localizedMessage ?? mapped.message
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  await app.loadBootstrap(props.apiClient)
  await load()
  if (route.query.create === '1' && canWrite.value) editorOpen.value = true
})
watch([stage, probabilityLevel, owner, archiveState], reloadFromFirstPage, { flush: 'sync' })
watch(layout, changeLayout, { flush: 'sync' })
watch(() => [route.query.page, route.query.pageSize, route.query.status, route.query.probabilityLevel, route.query.owner, route.query.layout, route.query.archive], ([nextPage, nextSize, nextStage, nextLevel, nextOwner, nextLayout, nextArchive]) => {
  const restoredPage = typeof nextPage === 'string' && Number(nextPage) > 0 ? Number(nextPage) : 1
  const restoredSize = typeof nextSize === 'string' && [10, 12, 25, 50].includes(Number(nextSize)) ? Number(nextSize) : 12
  const values = [normalizeStageFilter(nextStage), typeof nextOwner === 'string' ? nextOwner : 'All']
  const restoredLevel = normalizeOpportunityProbabilityLevelFilter(nextLevel)
  const restoredLayout = normalizeLayout(nextLayout)
  const restoredArchive = normalizeArchive(nextArchive)
  if (restoredPage === page.value && restoredSize === pageSize.value && values[0] === stage.value && restoredLevel === probabilityLevel.value && values[1] === owner.value && restoredLayout === layout.value && restoredArchive === archiveState.value) return
  restoringRoute = true; page.value = restoredPage; pageSize.value = restoredSize; stage.value = values[0]!; probabilityLevel.value = restoredLevel; owner.value = values[1]!; layout.value = restoredLayout; archiveState.value = restoredArchive; restoringRoute = false; resetBoardLimits(); void load()
})
</script>

<template>
  <section class="opportunity-list-view" data-testid="opportunity-list">
    <header class="opportunity-list-heading">
      <div class="opportunity-title-mark"><BriefcaseBusiness :size="21" /></div>
      <div>
        <span>OPPORTUNITIES</span>
        <h2>{{ t('opportunities.recentlyViewed') }}</h2>
        <p>{{ t('opportunities.countHint', { count: total }) }}</p>
      </div>
      <button v-if="canWrite" class="primary-button" type="button" data-testid="new-opportunity" @click="editorOpen = true"><Plus :size="14" />{{ t('opportunities.new') }}</button>
    </header>

    <div class="opportunity-list-toolbar">
      <RouterLink class="secondary-button" to="/opportunity-board">{{ t("nav.opportunities") }} · {{ t("opportunities.board") }}</RouterLink>
      <select v-model="stage" :aria-label="t('opportunities.allStages')"><option value="All">{{ t('opportunities.allStages') }}</option><option v-for="item in OPPORTUNITY_STAGES" :key="item" :value="item">{{ stageLabel(item) }}</option></select>
      <select v-model="probabilityLevel" :aria-label="t('opportunities.allProbabilityLevels')"><option value="All">{{ t('opportunities.allProbabilityLevels') }}</option><option v-for="level in OPPORTUNITY_PROBABILITY_LEVELS" :key="level" :value="level">{{ opportunityProbabilityLevelLabel(level, locale) }}</option><option :value="PENDING_PROBABILITY_LEVEL_FILTER">{{ opportunityProbabilityLevelLabel('', locale) }}</option></select>
      <select v-model="owner" :aria-label="t('opportunities.allOwners')"><option value="All">{{ t('opportunities.allOwners') }}</option><option v-for="item in owners" :key="item" :value="item">{{ personnelDisplayName(item) }}</option></select>
      <select v-model="archiveState" :aria-label="t('opportunities.archiveState')"><option value="active">{{ t('opportunities.archiveActive') }}</option><option value="archived">{{ t('opportunities.archiveArchived') }}</option><option value="all">{{ t('opportunities.archiveAll') }}</option></select>
      <div class="opportunity-layout-switch" :aria-label="t('opportunities.viewMode')">
        <button type="button" data-opportunity-layout="list" :class="{ active: layout === 'list' }" :aria-label="t('opportunities.listView')" @click="layout = 'list'"><List :size="14" />{{ t('opportunities.list') }}</button>
        <button type="button" data-opportunity-layout="board" :class="{ active: layout === 'board' }" :aria-label="t('opportunities.boardView')" @click="layout = 'board'"><Kanban :size="14" />{{ t('opportunities.board') }}</button>
      </div>
      <span data-testid="opportunity-shown-count">{{ visibleRows.length }} / {{ total }}</span>
      <button type="button" @click="resetFilters">{{ t('opportunities.reset') }}</button>
    </div>

    <div class="opportunity-table-card">
      <DataState v-if="loading && (!rows.length || layout === 'board' || rowsScope !== wantedScope)" type="loading" />
      <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
      <DataState v-else-if="error" type="error" :message="error" :request-id="requestId" @retry="load" />
      <DataState v-else-if="!visibleRows.length" type="empty" :title="t('opportunities.emptyTitle')" :message="t('opportunities.emptyMessage')" />
      <div v-else-if="layout === 'list'" class="table-scroll">
        <table class="crm-table opportunity-table">
          <thead><tr><th data-testid="opportunity-number-header">{{ t('opportunities.number') }}</th><th>{{ t('oppEditor.name') }}</th><th>{{ t('detail.account') }} / {{ t('detail.site') }}</th><th>{{ t('oppEditor.stage') }}</th><th>{{ t('detail.closeDate') }}</th><th>{{ t('detail.amount') }}</th><th>{{ t('oppEditor.probabilityLevel') }}</th><th>{{ t('opportunities.purchaseIntent') }}</th><th>{{ t('detail.owner') }}</th><th>{{ t('detail.updated') }}</th></tr></thead>
          <tbody>
            <tr v-for="item in visibleRows" :key="item.id" :data-opportunity-id="item.id">
              <td class="opportunity-number" :data-opportunity-number="item.id">{{ item.id }}<StatusBadge v-if="item.archived" :label="t('opportunities.archiveArchived')" tone="neutral" :data-opportunity-archived="item.id" /></td>
              <td><RouterLink class="record-link" :to="{ name: 'opportunity-detail', params: { opportunityId: item.id } }" :data-opportunity-link="item.id"><strong>{{ item.title }}</strong></RouterLink></td>
              <td><strong>{{ item.account }}</strong><small>{{ item.site }}</small></td>
              <td><strong>{{ stageLabel(item.stage) }}</strong><small v-if="item.pendingStageAdvance === 'demo_done' && item.stage === 'qualified_opportunity'" class="pending-stage-marker" :data-testid="`opportunity-pending-badge-${item.id}`" :title="t(item.currency === 'CNY' ? 'oppEditor.pendingDemoDone' : 'oppEditor.pendingDemoDoneForeign')">{{ t('oppEditor.pendingDemoDoneShort') }}</small></td>
              <td>{{ formatDisplayDate(item.poDate) }}</td>
              <td><strong :data-opportunity-amount="item.id">{{ amountText(item.amount, item.currency) }}</strong><small>{{ locale === 'en-US' ? 'Original' : '原始金额' }} {{ amountText(item.originalAmount, item.currency) }}</small><small :data-opportunity-amount-cny="item.id">{{ t('oppEditor.amountCny') }} {{ item.amountCny ? formatMoney(item.amountCny, 'CNY') : t('oppEditor.amountCnyPending') }}</small></td>
              <td data-opportunity-probability-level><StatusBadge :label="opportunityProbabilityLevelLabel(item.probabilityLevel, locale)" :tone="opportunityProbabilityLevelTone(item.probabilityLevel)" /></td>
              <td data-opportunity-intent><strong class="purchase-intent">{{ item.score }}/100</strong><small>{{ item.score >= 70 ? t('opportunities.highIntent') : item.score >= 50 ? t('opportunities.mediumIntent') : t('opportunities.lowIntent') }}</small></td>
              <td>{{ personnelDisplayName(item.owner) }}</td>
              <td>{{ formatDisplayDate(item.updated) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="opportunity-board-scroll" data-testid="opportunity-board">
        <div class="opportunity-board">
          <section v-for="stageName in OPPORTUNITY_STAGES" :key="stageName" class="opportunity-board-column" :data-opportunity-stage="stageName">
            <header>
              <div><strong>{{ stageLabel(stageName) }}<small v-if="stageName === OPTIONAL_OPPORTUNITY_STAGE" class="optional-stage-marker" data-stage-marker="optional">{{ t('detail.optionalStage') }}</small></strong><span>{{ t('opportunities.count', { count: stageCount(stageName) }) }}</span></div>
              <em>{{ stageMoney(stageName) }}</em>
            </header>
            <div class="opportunity-board-cards">
              <article v-for="item in visibleBoardRows[stageName]" :key="item.id" class="opportunity-board-card" :data-opportunity-id="item.id">
                <div class="board-card-topline"><span>{{ item.id }}</span><StatusBadge v-if="item.archived" :label="t('opportunities.archiveArchived')" tone="neutral" :data-opportunity-archived="item.id" /><StatusBadge :label="opportunityProbabilityLevelLabel(item.probabilityLevel, locale)" :tone="opportunityProbabilityLevelTone(item.probabilityLevel)" data-opportunity-board-probability-level /></div>
                <RouterLink class="record-link" :to="{ name: 'opportunity-detail', params: { opportunityId: item.id } }" :data-opportunity-board-link="item.id">{{ item.title }}</RouterLink>
                <small v-if="item.pendingStageAdvance === 'demo_done' && item.stage === 'qualified_opportunity'" class="pending-stage-marker board-pending-marker" :data-testid="`opportunity-board-pending-badge-${item.id}`" :title="t(item.currency === 'CNY' ? 'oppEditor.pendingDemoDone' : 'oppEditor.pendingDemoDoneForeign')">{{ t('oppEditor.pendingDemoDoneShort') }}</small>
                <p>{{ item.account }}<small>{{ item.site }}</small></p>
                <dl>
                  <div><dt>{{ t('detail.amount') }}</dt><dd>{{ amountText(item.amount, item.currency) }}</dd></div>
                  <div><dt>{{ t('opportunities.purchaseIntent') }}</dt><dd>{{ item.score }}/100</dd></div>
                </dl>
                <footer><span>{{ personnelDisplayName(item.owner) }}</span><time>{{ formatDisplayDate(item.poDate) }}</time></footer>
              </article>
              <p v-if="!boardRows[stageName].length" class="opportunity-board-empty">{{ t('opportunities.noItems') }}</p><button v-else-if="visibleBoardRows[stageName].length < boardRows[stageName].length" type="button" class="secondary-button board-load-more" :data-load-more-stage="stageName" @click="loadMoreStage(stageName)">{{ t('opportunities.loadMore') }}</button>
            </div>
          </section>
        </div>
      </div>
      <PaginationControls v-if="layout === 'list' && !denied && !error && total > pageSize" :page="page" :page-size="pageSize" :total="total" @change="goPage" @page-size-change="changePageSize" />
    </div>

    <OpportunityEditorModal v-if="editorOpen" :accounts="opportunityAccounts" :sites-by-account="sitesByAccount" :equipment-types="equipmentTypes" :default-owner="app.bootstrap?.user.id ?? ''" :current-user-id="app.bootstrap?.user.id ?? ''" :references-loading="referencesLoading" :busy="busy" :error="modalError" @close="editorOpen = false" @submit="saveOpportunity" />
  </section>
</template>

<style scoped>
.opportunity-list-view{display:grid;gap:12px}.opportunity-list-heading{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:12px;padding:14px 16px;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.opportunity-title-mark{display:grid;width:42px;height:42px;place-items:center;color:var(--crm-brand-ink);background:var(--crm-brand-soft);border-radius:12px}.opportunity-list-heading>div:nth-child(2){display:grid;gap:3px}.opportunity-list-heading span{color:var(--crm-text-muted);font-size:8px;font-weight:800;letter-spacing:.12em}.opportunity-list-heading h2{margin:0;color:var(--crm-navy);font-size:19px;letter-spacing:-.02em}.opportunity-list-heading p{margin:0;color:var(--crm-text-muted);font-size:9px}.opportunity-list-heading .primary-button{display:flex;align-items:center;gap:6px}.opportunity-list-toolbar{display:flex;align-items:center;gap:8px;padding:11px 13px;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.opportunity-list-toolbar select{height:38px;padding:0 10px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:10px;outline:0;font:inherit;font-size:9px}.opportunity-list-toolbar select:focus{border-color:rgba(254,153,0,.74);box-shadow:0 0 0 3px rgba(254,153,0,.1)}.opportunity-list-toolbar>span{margin-left:auto;color:var(--crm-text-muted);font-size:9px;white-space:nowrap}.opportunity-list-toolbar>button{padding:8px;color:var(--crm-teal);background:transparent;border:0;border-radius:8px;font:inherit;font-size:9px;font-weight:800;cursor:pointer}.opportunity-list-toolbar>button:hover{background:var(--crm-teal-soft)}.opportunity-table-card{min-height:310px;overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.opportunity-table{min-width:1260px}.opportunity-table th:first-child,.opportunity-table td:first-child{width:70px;text-align:center}.opportunity-table td>a,.opportunity-table td>strong,.opportunity-table td>small{display:block}.opportunity-table td>a{color:var(--crm-link)}.opportunity-table td>a strong{font-size:10px}.opportunity-table td small,.opportunity-table td>a small{margin-top:4px;color:var(--crm-text-muted);font-size:8px}.opportunity-number{color:var(--crm-text-muted);font-size:9px;font-weight:800;white-space:nowrap}.purchase-intent{color:var(--crm-teal);font-size:12px;font-variant-numeric:tabular-nums}@media(max-width:980px){.opportunity-list-toolbar{align-items:stretch;flex-wrap:wrap}.opportunity-list-toolbar>span{margin-left:0}.opportunity-list-toolbar .crm-search-control{flex:1 1 100%}}@media(max-width:700px){.opportunity-list-heading{grid-template-columns:auto 1fr}.opportunity-list-heading .primary-button{grid-column:1/-1;justify-content:center}.opportunity-list-toolbar{display:grid}.opportunity-list-toolbar>span{margin:0}}
</style>

<style scoped>
.opportunity-layout-switch{display:flex;flex:0 0 auto;padding:3px;background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:9px}
.opportunity-layout-switch button{display:flex;height:30px;align-items:center;gap:5px;padding:0 9px;color:var(--crm-text-muted);background:transparent;border:0;border-radius:6px;font:inherit;font-size:9px;font-weight:800;white-space:nowrap;cursor:pointer}
.opportunity-layout-switch button.active{color:var(--crm-brand-ink);background:#fff;box-shadow:0 1px 4px rgba(15,35,55,.1)}
.opportunity-board-scroll{min-height:480px;overflow-x:auto;background:var(--crm-surface)}
.opportunity-board{display:grid;min-width:1690px;min-height:480px;grid-template-columns:repeat(8,minmax(210px,1fr));gap:1px;background:var(--crm-line)}
.opportunity-board-column{display:grid;grid-template-rows:auto 1fr;min-width:0;background:#f8faf9}
.opportunity-board-column>header{display:grid;gap:7px;padding:12px 13px;background:#fff;border-top:3px solid var(--crm-teal)}
.opportunity-board-column>header div{display:flex;align-items:center;justify-content:space-between;gap:8px}
.opportunity-board-column>header strong{color:var(--crm-navy);font-size:10px}
.optional-stage-marker{margin-left:6px;padding:1px 5px;color:var(--crm-text-muted);border:1px dashed #b9b2a8;border-radius:999px;font-size:7px;font-weight:700}
.pending-stage-marker,.opportunity-table td small.pending-stage-marker{display:block;width:fit-content;padding:1px 5px;color:#8a651d;background:var(--crm-warning-soft);border:1px solid currentColor;border-radius:999px;font-size:7px;font-weight:700;white-space:nowrap}
.board-pending-marker{justify-self:start}
.opportunity-board-column>header span{color:var(--crm-text-muted);font-size:8px}
.opportunity-board-column>header em{color:var(--crm-teal);font-size:13px;font-style:normal;font-weight:800}
.opportunity-board-cards{display:grid;align-content:start;gap:9px;padding:10px}
.opportunity-board-card{display:grid;gap:9px;padding:12px;background:#fff;border:1px solid var(--crm-line);border-radius:10px;box-shadow:0 2px 7px rgba(15,35,55,.05)}
.board-card-topline,.opportunity-board-card footer{display:flex;align-items:center;justify-content:space-between;gap:8px}
.board-card-topline>span{color:var(--crm-text-muted);font-size:8px;font-weight:800}
.opportunity-board-card>a{color:var(--crm-navy);font-size:10px;font-weight:800;line-height:1.4}
.opportunity-board-card>a:hover{color:var(--crm-link-hover)}
.opportunity-board-card>p{display:grid;gap:3px;margin:0;color:var(--crm-text);font-size:9px}
.opportunity-board-card>p small{color:var(--crm-text-muted);font-size:8px}
.opportunity-board-card dl{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:0;padding:8px 0;border-top:1px solid var(--crm-line);border-bottom:1px solid var(--crm-line)}
.opportunity-board-card dl div{display:grid;gap:3px}
.opportunity-board-card dt{color:var(--crm-text-muted);font-size:7px}
.opportunity-board-card dd{margin:0;color:var(--crm-teal);font-size:10px;font-weight:800}
.opportunity-board-card footer{color:var(--crm-text-muted);font-size:8px}
.opportunity-board-empty{margin:0;padding:28px 10px;color:var(--crm-text-muted);border:1px dashed var(--crm-line);border-radius:9px;font-size:8px;text-align:center}
@media(max-width:700px){.opportunity-layout-switch{justify-self:start}}
</style>
