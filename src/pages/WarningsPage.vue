<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChevronLeft, ChevronRight, CircleCheck, SlidersHorizontal, TriangleAlert, X } from '@lucide/vue'
import { api as defaultApi, CrmApiError, type CrmApi } from '@/api'
import { requestErrorMessage } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import { localeMessage, useI18n, useLocaleMessage } from '@/i18n'
import { detailRoute, labels, metricText } from '@/features/cockpit/presentation'
import { cockpitRoute, dateWithin, EARLIEST_COCKPIT_DATE, endsBeforeEarliest, pickScope, shanghaiDate, showableAnchor, type CockpitContext } from '@/features/cockpit/scope'
import WarningNextStep from '@/features/cockpit/WarningNextStep.vue'
import RegionSelect from '@/features/cockpit/RegionSelect.vue'
import type { CockpitSettings, CockpitSettingsInput, Metric, PeriodKind, ReviewQuery, ReviewRow, WarningHandling, WarningsDto } from '@/features/cockpit/types'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const brandIconUrl = `${import.meta.env.BASE_URL}brand/planck-icon.png`
const app = useAppStore()
const router = useRouter()
const route = useRoute()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const label = (key: string) => labels[key]?.[locale.value === 'en-US' ? 1 : 0] ?? key
const fmt = (value: Metric) => metricText(value, locale.value)
const periods: PeriodKind[] = ['week', 'month', 'quarter', 'year']
// Opened from Review with its period and filters; the backend validates every value.
const initial = (key: string) => typeof route.query[key] === 'string' ? (route.query[key] as string).trim() : ''
// A date from a link is taken only if this page can show its period; otherwise the page opens on its default
// period.
const linkedPeriod: PeriodKind = periods.includes(initial('period') as PeriodKind) ? initial('period') as PeriodKind : 'week'
const linkedAnchor = showableAnchor(linkedPeriod, initial('anchor'), shanghaiDate())
const query = reactive<ReviewQuery>({
  period: linkedPeriod,
  ...(linkedAnchor ? { anchor: linkedAnchor } : {}),
  sales: initial('sales'), market: initial('market'), region: initial('region'), equipment: initial('equipment'),
})
const data = ref<WarningsDto | null>(null)
const filterOptions = ref<WarningsDto['filters']>({ sales: [], markets: [], regions: [], regionReady: false, equipment: [] })
const loading = ref(false)
const error = useLocaleMessage()
const manager = computed(() => app.bootstrap?.user.role === 'Manager')
// Back to Review with the period and filters Review handed to this page. The anchor always goes along:
// without one Review shows the last completed week while this page shows the current one. Until the period
// is known (an anchor asked for, or the data) there is nothing to hand over, so the tab is not a link yet.
// The anchor asked for wins over a loaded (possibly stale) response.
const shownAnchor = computed(() => query.anchor || data.value?.period.start || '')
const context = computed<CockpitContext>(() => ({ ...pickScope(query), period: query.period ?? 'week', reviewAnchor: shownAnchor.value }))
// After a failed load it is a link without an anchor, so Review opens on its own default period.
const reviewRoute = computed(() => cockpitRoute('review', context.value))
// Plan opens on the period after this one; Opportunities keeps this period for the way back. Without an anchor
// this page shows the period containing today on the Shanghai calendar (the backend default).
const planRoute = computed(() => cockpitRoute('plan', { ...context.value, reviewAnchor: shownAnchor.value || shanghaiDate() }))
const boardRoute = computed(() => cockpitRoute('board', { ...context.value, reviewAnchor: shownAnchor.value || shanghaiDate() }))
let revision = 0

const ownerName = (owner: string | null | undefined) => (owner && data.value?.names?.[owner]) || filterOptions.value.sales.find(r => r.id === owner)?.name || owner || copy('Owner unavailable', '归属数据不足')
const dateText = (value: string | null | undefined) => value ? new Date(value).toLocaleDateString(locale.value, { timeZone: 'Asia/Shanghai' }) : '—'
const dayText = (value: string | null | undefined) => value ? new Date(`${value.slice(0, 10)}T00:00:00Z`).toLocaleDateString(locale.value, { month: 'short', day: 'numeric', timeZone: 'UTC' }) : '—'
const millions = (value: number) => `¥${(value / 1000000).toLocaleString(locale.value, { maximumFractionDigits: 1 })}M`
const rowAmount = (row: ReviewRow) => row.amount == null || row.currency !== 'CNY' ? copy('Insufficient data', '数据不足') : millions(Number(row.amount))
// Sum the CNY estimates that exist; rows without one are reported beside the total, never counted as zero.
function amountSummary(rows: ReviewRow[]) {
  const known = rows.filter(row => row.amount != null && row.currency === 'CNY')
  const total = known.reduce((sum, row) => sum + Number(row.amount), 0)
  const missing = rows.length - known.length
  return { total, missing, text: known.length ? millions(total) : '—' }
}
// The as_of instant as a Shanghai calendar day, so a due date is late from the next Shanghai day.
const asOfDay = computed(() => data.value ? new Date(data.value.period.asOf).toLocaleDateString('en-CA', { timeZone: 'Asia/Shanghai' }) : '')
// Saving locks the filters and other editors, so a result is never dropped by a reload.
const busy = computed(() => planSaving.value || reviewSaving.value || stepSaving.value || settingsSaving.value)
const daysLate = (due: string | undefined) => due && asOfDay.value ? Math.max(0, Math.round((Date.parse(`${asOfDay.value}T00:00:00Z`) - Date.parse(`${due.slice(0, 10)}T00:00:00Z`)) / 86400000)) : null

const lostPending = computed(() => data.value?.lost.filter(row => row.reviewPending) ?? [])
const showBacklog = ref(false)
const lostRows = computed(() => data.value ? (showBacklog.value ? [...data.value.lost, ...data.value.lostBacklog] : data.value.lost) : [])
const lostSummary = computed(() => amountSummary(lostPending.value))
// The caption names the largest loss among the rows listed, so it follows the backlog toggle.
const largestLoss = computed(() => [...lostRows.value].filter(row => row.amount != null).sort((a, b) => Number(b.amount) - Number(a.amount))[0] ?? null)
const oldestOverdue = computed(() => Math.max(0, ...(data.value?.overdue ?? []).map(row => daysLate(row.due) ?? 0)))
const stalledOverdue = computed(() => (data.value?.overdue ?? []).some(row => row.stalled == null) ? null : (data.value?.overdue ?? []).filter(row => row.stalled).length)
const busiestOwner = computed(() => {
  const counts = new Map<string, number>()
  for (const row of data.value?.overdue ?? []) {
    const owner = row.actionOwner ?? row.owner
    if (owner) counts.set(owner, (counts.get(owner) ?? 0) + 1)
  }
  const [owner, count] = [...counts.entries()].sort((a, b) => b[1] - a[1])[0] ?? [null, 0]
  return owner && count > 1 ? { owner, count } : null
})
// One amount per deal: a deal downgraded twice in the period is counted and summed once.
const downgradeSummary = computed(() => amountSummary([...new Map((data.value?.downgrade ?? []).map(row => [row.id, row])).values()]))
const largestDowngrade = computed(() => [...(data.value?.downgrade ?? [])].filter(row => row.amount != null).sort((a, b) => Number(b.amount) - Number(a.amount))[0] ?? null)
// Quotes expiring plus stage 6 without PO, the two Review banner counts behind this zone.
// One insufficient count makes the total insufficient, never a partial sum.
const otherCount = computed(() => {
  const counts = ['quotation_expiry', 'stage6_no_po'].map(key => data.value?.warnings.find(w => w.key === key)?.count).filter((m): m is Metric => !!m)
  if (!data.value || !counts.length) return '—'
  const unknown = counts.find(m => m.state !== 'ready' || m.value == null)
  return fmt(unknown ? { ...unknown, state: unknown.state === 'ready' ? 'insufficient' : unknown.state } : { state: 'ready', value: counts.reduce((sum, m) => sum + Number(m.value), 0) })
})
const stage6Items = computed(() => data.value?.stage6NoPoItems ?? [])
// Stage 6 rows with an action recorded and the follow-up date ahead: listed apart, collapsed, never counted.
const stage6Handled = computed(() => data.value?.stage6NoPoHandledItems ?? [])
const showHandled = ref(false)
// Only a backend with warning handling sends the handled list: an older one gets no thresholds button
// (and, rows without handling, no next-step editors).
const handlingReady = computed(() => data.value?.stage6NoPoHandledItems !== undefined)
const overdueHandling = computed(() => (data.value?.overdue ?? []).some(row => row.handling))
// Older backends send no stage 6 count; an unknown count means an empty list proves nothing.
const stage6Known = computed(() => !!data.value?.warnings.some(w => w.key === 'stage6_no_po'))
const otherUnknown = computed(() => (data.value?.warnings ?? []).some(w => ['quotation_expiry', 'stage6_no_po'].includes(w.key) && (w.count.state !== 'ready' || w.count.value == null)))
const warningCount = (key: string) => { const metric = data.value?.warnings.find(w => w.key === key)?.count; return metric ? fmt(metric) : '—' }
// One line each on the card (the masthead keeps one height); the full text is the tooltip.
const summaryCards = computed(() => {
  const d = data.value
  const lostNote = !d ? '—' : [`${copy('pending post-mortem', '待复盘')} · ${lostSummary.value.text}`,
    lostSummary.value.missing ? `${lostSummary.value.missing} ${copy('without CNY estimate', '条缺人民币金额')}` : '',
    d.lostBacklog.length ? `${copy('older pending', '更早待复盘')} ${d.lostBacklog.length}` : ''].filter(Boolean).join(' · ')
  const overdueNote = !d ? '—' : !d.overdue.length ? copy('Nothing overdue', '没有逾期行动')
    : `${copy('Oldest', '最久')} ${oldestOverdue.value} ${copy('days late', '天')} · ${stalledOverdue.value === null ? copy('stall status unverified', '停滞状态待核验') : `${stalledOverdue.value} ${copy('on stalled deals', '条在停滞商机上')}`}`
  const downgradeNote = !d ? '—' : `${copy('awaiting action', '待负责人行动')} · ${downgradeSummary.value.text}`
  const otherNote = !d ? '—' : [`${label('quotation_expiry')} ${warningCount('quotation_expiry')}`,
    stage6Known.value ? `${label('stage6_no_po')} ${warningCount('stage6_no_po')}` : ''].filter(Boolean).join(' · ')
  return [
    { key: 'lost', label: copy('Lost · 4 wk · post-mortem pending', '近 4 周丢单待复盘'), value: warningCount('lost'), note: lostNote },
    { key: 'overdue', label: copy('Planned actions not executed', '未执行计划'), value: warningCount('overdue'), note: overdueNote },
    { key: 'downgrade', label: copy('Probability level reduced', '概率降档'), value: warningCount('downgrade'), note: downgradeNote },
    { key: 'other', label: label('other_alerts'), value: d ? otherCount.value : '—', note: otherNote },
  ]
})
const periodTitle = computed(() => data.value ? `${data.value.period.start} — ${data.value.period.end}` : '')
const levelText = (row: ReviewRow) => `${label(row.fromLevel ?? '')} → ${label(row.toLevel ?? '')}`
const periodHeading = computed(() => {
  if (!data.value) return ''
  const d = new Date(`${data.value.period.start}T00:00:00Z`), year = d.getUTCFullYear()
  if (data.value.period.kind === 'year') return String(year)
  if (data.value.period.kind === 'quarter') return `${year} · Q${Math.floor(d.getUTCMonth() / 3) + 1}`
  if (data.value.period.kind === 'month') return d.toLocaleDateString(locale.value, { year: 'numeric', month: 'long', timeZone: 'UTC' })
  d.setUTCDate(d.getUTCDate() + 3 - (d.getUTCDay() + 6) % 7)
  const week = Math.ceil(((d.getTime() - Date.UTC(d.getUTCFullYear(), 0, 1)) / 86400000 + 1) / 7)
  return `${copy('Week', '第')} ${week}${copy('', '周')}`
})

// In-meeting plan edit: one row at a time; saving never clears the warning (only the owner's recorded action does).
// The versions are taken when the editor opens: a later quiet refresh must not turn a draft started from an
// old plan into a save against the newer one (the backend then reports the conflict instead of overwriting).
const planEdit = ref<{ eventId: string; opportunityId: string; recoveryModified: string | null; opportunityModified: string } | null>(null)
const planDraft = ref('')
const planError = useLocaleMessage()
const planSaving = ref(false)
const planConflict = ref(false)
const refreshError = useLocaleMessage()
// Whether a failed quiet refresh followed a saved change (a vanished alert saves nothing).
const refreshSaved = ref(true)
const draftDropped = localeMessage('The row you were editing left the list after a refresh; your draft was not saved.', '正在编辑的行在刷新后已不在列表中，草稿未保存')

// quiet: refresh after a save without blanking the page; saved: whether that save changed anything.
// Resolves true once the new data is on the page.
async function load(quiet = false, saved = true) {
  const id = ++revision
  if (!quiet) {
    // A quiet refresh after a save keeps any other open editor and its draft.
    reviewDialog.value?.close(); settingsDialog.value?.close()
    planEdit.value = null; handlingEdit.value = null; handlingNotice.value = ''
    data.value = null
  }
  if (!manager.value) return false
  if (!quiet) { loading.value = true; error.value = '' }
  refreshError.value = ''
  try {
    const result = await props.apiClient.getWarnings({ ...query })
    if (id !== revision || !manager.value) return false
    data.value = result.data; filterOptions.value = result.data.filters
    // The row being edited is gone (e.g. the owner recorded the action): leave the editor and say the draft was dropped.
    if (planEdit.value && !result.data.downgrade.some(row => row.eventId === planEdit.value?.eventId)) { planEdit.value = null; handlingNotice.value = draftDropped }
    if (handlingEdit.value && !handlingKeys(result.data).has(handlingEdit.value.key)) { handlingEdit.value = null; handlingNotice.value = draftDropped }
    return true
  } catch (reason) {
    // A failed refresh after a save keeps the page; only a full load shows the error page.
    if (id === revision) { if (quiet && data.value) { refreshError.value = requestErrorMessage(reason); refreshSaved.value = saved } else error.value = requestErrorMessage(reason) }
    return false
  } finally {
    if (id === revision) loading.value = false
  }
}
function step(next: boolean) {
  if (data.value) query.anchor = next ? data.value.period.nextAnchor : data.value.period.previousAnchor
}
// The date asked for stays when the kind of period changes, unless the new kind cannot show it: the week that
// reaches into 2000 starts in 1999, and the month, quarter and year of that day end before 2000.
function changePeriod(period: PeriodKind) {
  if (query.anchor && endsBeforeEarliest(period, query.anchor)) query.anchor = EARLIEST_COCKPIT_DATE
  query.period = period
}
// What the date field holds while it is being edited. The field is bound to it from the moment it takes the
// focus until it is left, so a response that arrives in the middle of a date redraws the page without putting
// the date on show back into the field. That holds for an empty field too: typing a year into it changes
// nothing a script can see until the date is whole.
const dateDraft = ref<string | null>(null)
// The date field asks for a period only when it holds a whole date that this page can show: not before
// EARLIEST_COCKPIT_DATE and not after today. A year typed digit by digit passes through the years 2, 20 and
// 202, and a cleared field is empty; none of those is a request.
function pickAnchor(event: Event) {
  const picked = dateWithin((event.target as HTMLInputElement).value, EARLIEST_COCKPIT_DATE, shanghaiDate())
  if (picked) query.anchor = picked
}
// On leaving the field, a date that was not taken gives way to the one on show.
function showAnchor(event: Event) { dateDraft.value = null; (event.target as HTMLInputElement).value = shownAnchor.value }
// The period before the earliest one the cockpit shows (the one that reaches into 2000) cannot be asked for.
const atEarliestPeriod = computed(() => Boolean(data.value) && data.value!.period.start <= EARLIEST_COCKPIT_DATE)

// Focus follows the inline editors: into the text when one opens, back to the row's button once a save or cancel
// settles (buttons stay disabled while a save reloads), or to a fallback when the row moved.
const pageRoot = ref<HTMLElement | null>(null)
async function focusIn(attribute: string, value: string, selector: string, fallback?: string) {
  await nextTick()
  const block = [...(pageRoot.value?.querySelectorAll<HTMLElement>(`[${attribute}]`) ?? [])].find(element => element.getAttribute(attribute) === value)
  const target = block?.querySelector<HTMLElement>(selector) ?? (fallback ? pageRoot.value?.querySelector<HTMLElement>(fallback) : null)
  target?.focus()
}

// One inline editor per page (plan, next step or action): a second open draft could lose its save to the other's
// reload, and no save starts while another one runs.
function startPlanEdit(row: ReviewRow) {
  if (!row.eventId || !row.opportunityModified || handlingEdit.value) return
  planEdit.value = { eventId: row.eventId, opportunityId: row.id, recoveryModified: row.recovery?.modified ?? null, opportunityModified: row.opportunityModified }
  planDraft.value = row.recovery?.plan ?? ''
  planError.value = ''; planConflict.value = false
  void focusIn('data-downgrade-row', row.eventId, '[data-plan-draft]')
}
function cancelPlanEdit() {
  const edit = planEdit.value
  planEdit.value = null
  if (edit) void focusIn('data-downgrade-row', edit.eventId, '[data-plan-edit]')
}
async function savePlan() {
  const edit = planEdit.value
  if (!edit || busy.value || !planDraft.value.trim()) return
  const requestRevision = revision
  let saved = false
  planSaving.value = true; planError.value = ''; planConflict.value = false
  try {
    await props.apiClient.saveProbabilityRecovery(edit.opportunityId, edit.eventId, { plan: planDraft.value.trim(), recoveryModified: edit.recoveryModified }, edit.opportunityModified)
    if (requestRevision !== revision) return
    planEdit.value = null
    saved = true
    await load(true)
  } catch (reason) {
    if (requestRevision !== revision) return
    planConflict.value = errorCode(reason) === 'VERSION_CONFLICT'
    planError.value = requestErrorMessage(reason)
  } finally {
    planSaving.value = false
    if (saved) void focusIn('data-downgrade-row', edit.eventId, '[data-plan-edit]')
  }
}

// Next step (下一步) on overdue, quotation and stage 6 rows, versioned like the plan editor; saving it never clears the
// warning. Stage 6 rows can also record the action taken, which clears the row until its follow-up date (the backend
// moves it to the handled list, where the action and date can still be corrected).
const handlingKey = (handling: WarningHandling) => `${handling.warningType}:${handling.sourceId}:${handling.sourceEvent}`
const handlingEdit = ref<{ key: string; mode: 'plan' | 'action'; source: Pick<WarningHandling, 'warningType' | 'sourceId' | 'sourceEvent'>; modified: string | null; min: string; max: string } | null>(null)
const stepDraft = ref('')
const followUpDraft = ref('')
const stepError = useLocaleMessage()
const stepSaving = ref(false)
const stepConflict = ref(false)
const handlingNotice = useLocaleMessage()
const conflictMessage = localeMessage('Changed by someone else. Reload and try again.', '已被他人修改，请刷新后重试')
const errorCode = (reason: unknown) => typeof reason === 'object' && reason !== null ? (reason as { code?: string }).code : undefined
// Validation messages chosen by field, in the page language (the backend's field texts are English).
const fieldMessages = new Map<string, [string, string]>([
  ['nextStep', ['Enter the next step, up to 2,000 characters.', '请填写下一步，不超过 2000 字']],
  ['actionTaken', ['Enter the action taken, up to 2,000 characters.', '请填写已采取的行动，不超过 2000 字']],
  ['followUpOn', ['Pick a follow-up date from tomorrow to one year ahead.', '请选择明天至一年内的复核日期']],
  ['quoteExpiryDays', ['Quote expiry reminder: a whole number from 0 to 365.', '报价到期提醒天数须为 0–365 的整数']],
  ['stage6NoPoDays', ['Stage 6 without PO: a whole number from 1 to 365.', '第 6 阶段无 PO 天数须为 1–365 的整数']],
])
function failureMessage(reason: unknown) {
  const fields = reason instanceof CrmApiError ? Object.keys(reason.fieldErrors).map(key => fieldMessages.get(key)).filter((message): message is [string, string] => !!message) : []
  return fields.length ? localeMessage(fields.map(([english]) => english).join(' '), fields.map(([, chinese]) => chinese).join('；')) : requestErrorMessage(reason)
}
const handlingRows = (dto: WarningsDto) => [...dto.overdue, ...dto.quotationExpiryItems, ...(dto.stage6NoPoItems ?? []), ...(dto.stage6NoPoHandledItems ?? [])]
const handlingKeys = (dto: WarningsDto) => new Set(handlingRows(dto).flatMap(row => row.handling ? [handlingKey(row.handling)] : []))
// A follow-up date falls after the Shanghai today and at most 365 days ahead, as the backend checks.
function followUpBounds() {
  const today = Date.parse(`${new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Shanghai' })}T00:00:00Z`)
  const day = (offset: number) => new Date(today + offset * 86400000).toISOString().slice(0, 10)
  return { min: day(1), max: day(365) }
}
const followUpOk = computed(() => {
  const edit = handlingEdit.value
  return !!edit && /^\d{4}-\d{2}-\d{2}$/.test(followUpDraft.value) && followUpDraft.value >= edit.min && followUpDraft.value <= edit.max
})
const stepReady = computed(() => !!handlingEdit.value && !!stepDraft.value.trim() && (handlingEdit.value.mode === 'plan' || followUpOk.value))
// Back to the button that opened the editor; a stage 6 row that moved to the collapsed handled list falls back to its toggle.
const focusStepButton = (key: string, mode: 'plan' | 'action') => focusIn('data-handling-key', key, mode === 'plan' ? '[data-step-edit]' : '[data-action-open], [data-action-edit]', key.startsWith('stage6_no_po:') ? '[data-s6-handled-toggle]' : undefined)
function startStepEdit(handling: WarningHandling, mode: 'plan' | 'action') {
  if (planEdit.value) return
  const { warningType, sourceId, sourceEvent } = handling
  // A handled stage 6 row reopens its action to correct it (e.g. a follow-up date picked by mistake).
  const correcting = mode === 'action' && handling.state === 'handled'
  handlingEdit.value = { key: handlingKey(handling), mode, source: { warningType, sourceId, sourceEvent }, modified: handling.modified, ...followUpBounds() }
  stepDraft.value = mode === 'plan' ? handling.nextStep ?? '' : correcting ? handling.actionTaken ?? '' : ''
  followUpDraft.value = correcting ? handling.followUpOn ?? '' : ''
  stepError.value = ''; stepConflict.value = false; handlingNotice.value = ''
  void focusIn('data-handling-key', handlingKey(handling), '[data-step-draft]')
}
function cancelStepEdit() {
  const edit = handlingEdit.value
  handlingEdit.value = null
  if (edit) void focusStepButton(edit.key, edit.mode)
}
// The saved handling goes onto its row before the quiet reload, so a failed reload still leaves the new version.
function patchHandling(key: string, handling: WarningHandling) {
  const row = data.value ? handlingRows(data.value).find(item => item.handling && handlingKey(item.handling) === key) : undefined
  if (row) row.handling = handling
}
async function saveStep() {
  const edit = handlingEdit.value
  if (!edit || busy.value) return
  // The Shanghai day may have turned since the editor opened.
  if (edit.mode === 'action') Object.assign(edit, followUpBounds())
  if (!stepReady.value) return
  const requestRevision = revision
  let outcome: 'saved' | 'gone' | null = null
  stepSaving.value = true; stepError.value = ''; stepConflict.value = false
  try {
    const { sourceId, sourceEvent } = edit.source, text = stepDraft.value.trim()
    const result = edit.mode === 'plan'
      ? await props.apiClient.saveWarningPlan({ warningType: edit.source.warningType, sourceId, sourceEvent, nextStep: text }, edit.modified)
      : await props.apiClient.recordWarningAction({ warningType: 'stage6_no_po', sourceId, sourceEvent, actionTaken: text, followUpOn: followUpDraft.value }, edit.modified)
    if (requestRevision !== revision) return
    handlingEdit.value = null
    patchHandling(edit.key, result.data)
    outcome = 'saved'
    await load(true)
  } catch (reason) {
    if (requestRevision !== revision) return
    // The warning is gone (action done, quote replaced, deal left stage 6): nothing was saved; refresh quietly and say so.
    if (errorCode(reason) === 'INVALID_TRANSITION') {
      handlingEdit.value = null
      outcome = 'gone'
      handlingNotice.value = await load(true, false)
        ? localeMessage('That alert changed since the page loaded (it may have cleared); your draft was not saved and the page was refreshed.', '该提醒在页面加载后已变化（可能已解除），草稿未保存，页面已刷新')
        : localeMessage('That alert changed since the page loaded (it may have cleared); your draft was not saved.', '该提醒在页面加载后已变化（可能已解除），草稿未保存')
      return
    }
    stepConflict.value = errorCode(reason) === 'VERSION_CONFLICT'
    stepError.value = stepConflict.value ? conflictMessage : failureMessage(reason)
  } finally {
    stepSaving.value = false
    if (outcome === 'saved') void focusStepButton(edit.key, edit.mode)
    else if (outcome === 'gone') void nextTick(() => pageRoot.value?.querySelector<HTMLElement>('[data-handling-notice] button')?.focus())
  }
}
// What every row's next-step block binds; only the row being edited gets the drafts' bounds and errors.
function stepBind(handling: WarningHandling) {
  const key = handlingKey(handling)
  const edit = handlingEdit.value?.key === key ? handlingEdit.value : null
  return {
    'data-handling-key': key, handling, name: ownerName, editing: edit?.mode ?? null,
    locked: busy.value || !!handlingEdit.value || !!planEdit.value, saving: stepSaving.value, canSave: stepReady.value && !busy.value, dateHint: edit?.mode === 'action' && !followUpOk.value,
    error: edit ? stepError.value : '', conflict: stepConflict.value, allowAction: handling.warningType === 'stage6_no_po', followUpMin: edit?.min, followUpMax: edit?.max,
    draft: stepDraft.value, 'onUpdate:draft': (value: string) => { stepDraft.value = value },
    followUp: followUpDraft.value, 'onUpdate:followUp': (value: string) => { followUpDraft.value = value },
    onEdit: (mode: 'plan' | 'action') => startStepEdit(handling, mode), onCancel: cancelStepEdit, onSave: () => void saveStep(), onReload: () => void load(),
  }
}
// Post-mortem: the Manager records the conclusion against the loss review row; the Sales reason is read-only.
const reviewDialog = ref<HTMLDialogElement | null>(null)
const reviewRow = ref<ReviewRow | null>(null)
const reviewNote = ref('')
const reviewError = useLocaleMessage()
const reviewSaving = ref(false)
const reviewConflict = ref(false)
// Reverting asks for its own reason and never touches the conclusion.
const revertMode = ref(false)
const revertReason = ref('')
function openReview(row: ReviewRow) {
  reviewRow.value = row
  reviewNote.value = row.review?.note ?? ''
  revertMode.value = false; revertReason.value = ''
  reviewError.value = ''
  reviewConflict.value = false
  reviewDialog.value?.showModal()
}
async function submitReview(status: 'Reviewed' | 'Pending') {
  const row = reviewRow.value
  // A review row without a version cannot be saved against; the table shows such a row as pending backfill.
  if (!row?.review?.modified || reviewSaving.value) return
  const requestRevision = revision
  reviewSaving.value = true; reviewError.value = ''; reviewConflict.value = false
  try {
    const input = status === 'Pending'
      ? { status, reviewNote: row.review.note, revertReason: revertReason.value.trim() }
      : { status, reviewNote: reviewNote.value.trim() }
    await props.apiClient.reviewOpportunityLoss(row.id, row.review.id, input, row.review.modified)
    if (requestRevision !== revision) return
    reviewDialog.value?.close()
    await load(true)
  } catch (reason) {
    if (requestRevision !== revision) return
    reviewConflict.value = typeof reason === 'object' && reason !== null && (reason as { code?: string }).code === 'VERSION_CONFLICT'
    reviewError.value = requestErrorMessage(reason)
  } finally { reviewSaving.value = false }
}

// Other-alerts thresholds in a small dialog; after a save the quiet reload recounts with the new values.
const settingsDialog = ref<HTMLDialogElement | null>(null)
const settingsOpener = ref<HTMLButtonElement | null>(null)
const settings = ref<CockpitSettings | null>(null)
const settingsDraft = reactive<Record<keyof CockpitSettingsInput, number | string>>({ quoteExpiryDays: '', stage6NoPoDays: '' })
const settingsLoading = ref(false)
const settingsSaving = ref(false)
const settingsError = useLocaleMessage()
const settingsConflict = ref(false)
let settingsRequest = 0
// 0 quote days means only quotes expiring on the reference date; a stage 6 wait is at least one day.
const minDays: Record<keyof CockpitSettingsInput, number> = { quoteExpiryDays: 0, stage6NoPoDays: 1 }
const settingFields = computed(() => [
  { key: 'quoteExpiryDays' as const, label: copy('Quote expiry reminder (days)', '报价到期提醒天数') },
  { key: 'stage6NoPoDays' as const, label: copy('Stage 6 without PO (days)', '第 6 阶段无 PO 天数') },
])
const sourceText = (source: string) => source === 'settings' ? copy('Saved setting', '已保存设置') : source === 'site_config' ? copy('Site config', '站点配置') : copy('Default', '默认值')
// Whole days from the field's minimum to 365 (a number input gives a number, or '' when cleared).
const validDays = (key: keyof CockpitSettingsInput) => {
  const value = settingsDraft[key], days = typeof value === 'number' ? value : value.trim() ? Number(value) : NaN
  return Number.isInteger(days) && days >= minDays[key] && days <= 365 ? days : null
}
const settingsValid = computed(() => validDays('quoteExpiryDays') !== null && validDays('stage6NoPoDays') !== null)
// Back to the thresholds button once it is enabled again (it stays disabled while a save reloads the page).
function focusSettingsOpener() { if (!settingsSaving.value) void nextTick(() => settingsOpener.value?.focus()) }
function closeSettings() { settingsDialog.value?.close(); focusSettingsOpener() }
async function openSettings() {
  const id = ++settingsRequest
  settings.value = null; settingsError.value = ''; settingsConflict.value = false
  if (!settingsDialog.value?.open) settingsDialog.value?.showModal()
  settingsLoading.value = true
  try {
    const result = await props.apiClient.getCockpitSettings()
    if (id !== settingsRequest) return
    settings.value = result.data
    settingsDraft.quoteExpiryDays = result.data.quoteExpiryDays; settingsDraft.stage6NoPoDays = result.data.stage6NoPoDays
  } catch (reason) {
    if (id === settingsRequest) settingsError.value = requestErrorMessage(reason)
  } finally { if (id === settingsRequest) settingsLoading.value = false }
}
async function saveSettings() {
  const current = settings.value
  const quoteExpiryDays = validDays('quoteExpiryDays'), stage6NoPoDays = validDays('stage6NoPoDays')
  if (!current || busy.value || quoteExpiryDays === null || stage6NoPoDays === null) return
  const requestRevision = revision
  let saved = false
  settingsSaving.value = true; settingsError.value = ''; settingsConflict.value = false
  try {
    await props.apiClient.saveCockpitSettings({ quoteExpiryDays, stage6NoPoDays }, current.modified)
    if (requestRevision !== revision) return
    settingsDialog.value?.close()
    saved = true
    await load(true)
  } catch (reason) {
    if (requestRevision !== revision) return
    settingsConflict.value = errorCode(reason) === 'VERSION_CONFLICT'
    settingsError.value = settingsConflict.value ? conflictMessage : failureMessage(reason)
  } finally {
    settingsSaving.value = false
    if (saved) focusSettingsOpener()
  }
}
// Last in setup: the immediate watcher runs load() during setup when the shell has already loaded
// the Manager (navigating from Review), so every ref load() touches must be declared above.
watch(() => [app.bootstrap?.user.role, app.identityRevision, query.period, query.anchor, query.sales, query.market, query.region, query.equipment], () => {
  if (app.bootstrap && !manager.value) {
    revision++; data.value = null; filterOptions.value = { sales: [], markets: [], regions: [], regionReady: false, equipment: [] }
    reviewDialog.value?.close(); settingsDialog.value?.close()
    void router.replace('/calendar')
  } else if (manager.value) void load()
}, { immediate: true })
onMounted(() => app.loadBootstrap(props.apiClient))
onBeforeUnmount(() => { revision++ })
</script>

<template>
  <div v-if="manager" ref="pageRoot" class="warnings-page" data-testid="warnings-page" :aria-busy="loading">
    <div class="review-masthead">
      <div class="review-header-art" aria-hidden="true"><img :src="brandIconUrl" alt="" width="512" height="512" draggable="false" /></div>
      <header class="warnings-heading">
        <div class="identity"><h1>Warnings <span>· {{ copy('Risks', '风险预警') }}</span></h1><p>{{ periodHeading ? `${periodHeading} · ` : '' }}{{ periodTitle || '—' }}</p></div>
        <div class="summary-cards" role="group" :aria-label="copy('Warning summary', '预警摘要')">
          <article v-for="card in summaryCards" :key="card.key" class="summary-card" :class="card.key"><span :title="card.label">{{ card.label }}</span><strong :class="{ 'text-value': !/^[\d—]/.test(card.value) }" :title="card.value">{{ card.value }}</strong><small :title="card.note">{{ card.note }}</small></article>
        </div>
      </header>
      <nav class="review-controls" :aria-label="copy('Warnings filters', '预警筛选')">
        <RouterLink v-if="data || query.anchor || error" class="plan-tab" :to="reviewRoute">Review</RouterLink><span v-else class="plan-tab is-disabled" role="link" aria-disabled="true" :title="copy('Available once the page has loaded', '页面加载完成后可用')">Review</span><RouterLink class="plan-tab" :to="planRoute">Plan</RouterLink><strong class="review-tab" aria-current="page">Warnings</strong><RouterLink class="plan-tab" :to="boardRoute">Opportunities</RouterLink>
        <label><span class="filter-name">{{ copy('Region', '区域') }}</span><RegionSelect v-model="query.region" :regions="filterOptions.regions" :parents="filterOptions.regionParents" :disabled="loading || busy || !filterOptions.regionReady" :all-label="filterOptions.regionReady ? copy('All regions', '全部区域') : copy('Region migration pending', '区域待迁移')" /></label>
        <label><span class="filter-name">{{ copy('Sales', '销售') }}</span><select v-model="query.sales" :disabled="loading || busy" aria-label="Sales"><option value="">{{ copy('All sales', '全部销售') }}</option><option v-for="person in filterOptions.sales" :key="person.id" :value="person.id">{{ person.name }}</option></select></label>
        <label><span class="filter-name">{{ copy('Market', '市场') }}</span><select v-model="query.market" :disabled="loading || busy" aria-label="Market"><option value="">{{ copy('All markets', '全部市场') }}</option><option v-for="market in filterOptions.markets" :key="market" :value="market">{{ market }}</option></select></label>
        <label><span class="filter-name">{{ copy('Equipment', '设备') }}</span><select v-model="query.equipment" :disabled="loading || busy" aria-label="Equipment"><option value="">{{ copy('All equipment', '全部设备') }}</option><option v-for="equipment in filterOptions.equipment ?? []" :key="equipment" :value="equipment">{{ equipment }}</option></select></label>
        <div class="period-controls"><div class="segmented" :aria-label="copy('Period', '统计周期')"><button v-for="period in periods" :key="period" :aria-pressed="query.period === period" :class="{ active: query.period === period }" :disabled="loading || busy" @click="changePeriod(period)">{{ label(period) }}</button></div><button :disabled="loading || busy || !data || atEarliestPeriod" :aria-label="copy('Previous period', '上一期')" @click="step(false)"><ChevronLeft :size="16" /></button><input :value="dateDraft ?? shownAnchor" :min="EARLIEST_COCKPIT_DATE" :max="shanghaiDate()" type="date" :aria-label="copy('Reference date', '参考日期')" :disabled="busy" @focus="dateDraft = ($event.target as HTMLInputElement).value" @input="dateDraft = ($event.target as HTMLInputElement).value" @change="pickAnchor" @blur="showAnchor" /><button :disabled="loading || busy || !data?.period.hasNext" :aria-label="copy('Next period', '下一期')" @click="step(true)"><ChevronRight :size="16" /></button></div>
      </nav>
    </div>
    <div v-if="loading" class="review-state" role="status">{{ copy('Loading warnings…', '正在读取预警数据…') }}</div>
    <div v-else-if="error" class="review-state error" role="alert"><p>{{ error }}</p><button @click="load()">{{ copy('Retry', '重新加载') }}</button></div>
    <template v-else-if="data">
      <p v-if="refreshError" class="refresh-error" role="alert" data-refresh-error>{{ refreshSaved ? copy('Saved, but the page could not refresh:', '已保存，但页面刷新失败：') : copy('The page could not refresh:', '页面刷新失败：') }}{{ refreshError }} <button type="button" :disabled="busy" @click="load(true, refreshSaved)">{{ copy('Refresh', '刷新') }}</button></p>
      <p v-if="handlingNotice" class="refresh-error handling-notice" role="status" data-handling-notice>{{ handlingNotice }} <button type="button" @click="handlingNotice = ''">{{ copy('OK', '知道了') }}</button></p>
      <div class="warnings-grid">
        <section class="panel lost-panel" data-zone="lost"><div class="panel-heading"><div><h2>{{ copy('Opportunities lost', '丢单') }}</h2><p>{{ copy('Closed-lost in the last 4 weeks; older unreviewed losses are listed below the table', '近 4 周丢单；更早未复盘的丢单可在表格下方展开') }}</p></div><span class="zone-count">{{ warningCount('lost') }} {{ copy('pending', '待复盘') }}</span></div>
          <div class="table-scroll"><table><thead><tr><th>{{ copy('Customer', '客户') }}</th><th>{{ copy('Lost at stage', '丢失阶段') }}</th><th>{{ copy('Value', '金额') }}</th><th>{{ copy('Owner', '销售') }}</th><th>{{ copy('Loss reason', '丢单原因') }}</th><th>{{ copy('Date', '日期') }}</th><th>{{ copy('Post-mortem', '复盘') }}</th></tr></thead>
            <tbody><tr v-for="row in lostRows" :key="row.eventId ?? row.id" :data-lost-row="row.id" :class="{ backlog: row.reviewOverdue }"><td><RouterLink :to="detailRoute(row)"><strong>{{ row.customer }}</strong><small>{{ row.title }}</small></RouterLink></td><td>{{ label(row.stage ?? '') || '—' }}</td><td class="numeric">{{ rowAmount(row) }}</td><td>{{ ownerName(row.owner) }}</td><td class="reason-cell"><p>{{ row.reason || copy('Reason not recorded', '未记录原因') }}</p><small v-if="row.review?.status === 'reviewed' && row.review.note">{{ row.review.note }}</small></td><td>{{ dateText(row.at) }}</td>
              <td class="review-cell"><template v-if="row.reopenedAt"><span class="badge muted">{{ copy('Reopened', '已重开') }} {{ dateText(row.reopenedAt) }}</span></template><template v-else-if="!row.review || !row.review.modified"><span class="badge muted">{{ copy('Review record pending backfill', '复盘记录待回填') }}</span></template><template v-else-if="row.review.status === 'reviewed'"><span class="badge done"><CircleCheck :size="13" />{{ copy('Done', '已复盘') }} {{ dateText(row.review.reviewedAt) }} · {{ ownerName(row.review.reviewedBy) }}</span><button class="text-link" data-review-edit :disabled="busy" @click="openReview(row)">{{ copy('Edit', '修改') }}</button></template><template v-else><span v-if="row.reviewOverdue" class="badge danger">{{ copy('Post-mortem overdue', '复盘逾期') }}</span><span v-else class="badge warn">{{ copy('To do', '待分析') }}</span><button class="review-button" data-review-open :disabled="busy" @click="openReview(row)">{{ copy('Record post-mortem', '记录复盘') }}</button></template></td></tr></tbody></table></div>
          <button v-if="data.lostBacklog.length" type="button" class="backlog-toggle" data-lost-backlog :aria-expanded="showBacklog" @click="showBacklog = !showBacklog">{{ showBacklog ? copy('Hide older losses', '收起更早的丢单') : `${copy('Older losses awaiting a post-mortem', '更早未复盘的丢单')} · ${data.lostBacklog.length} ${copy('(not counted)', '条（不计入预警数）')}` }}</button>
          <p v-if="!data.lost.length && data.lostBacklog.length" class="backlog-only">{{ copy('No losses in the last 4 weeks', '近 4 周无丢单') }}</p>
          <p v-if="!data.lost.length && !data.lostBacklog.length" class="empty-list">{{ copy('No losses in the last 4 weeks and nothing awaiting a post-mortem', '近 4 周无丢单，也没有待复盘记录') }}</p>
          <footer v-if="largestLoss" class="zone-note">{{ largestLoss.customer }}（{{ rowAmount(largestLoss) }}）{{ copy('is the largest loss listed', '是本页金额最大的丢单') }} · {{ copy('Reasons are as entered by Sales; the Manager records the post-mortem conclusion', '原因为销售填写的原文，复盘结论由经理填写') }}</footer>
        </section>
        <section class="panel overdue-panel" data-zone="overdue"><div class="panel-heading"><div><h2>{{ copy('Planned actions not executed', '未执行计划') }}</h2><p>{{ copy('Open actions past their due date with no completion logged', '已过截止日期且没有记录完成的行动计划') }}</p></div><span class="zone-count">{{ warningCount('overdue') }} {{ copy('overdue', '条逾期') }}</span></div>
          <div class="table-scroll"><table><thead><tr><th>{{ copy('Action', '行动') }}</th><th>{{ copy('Opportunity', '商机') }}</th><th>{{ copy('Owner', '负责人') }}</th><th>{{ copy('Due', '到期') }}</th><th>{{ copy('Overdue', '逾期') }}</th><th>{{ copy('Status', '状态') }}</th><th v-if="overdueHandling">{{ copy('Next step', '下一步') }}</th></tr></thead>
            <tbody><tr v-for="row in data.overdue" :key="`${row.actionId}:${row.id}`" :data-overdue-row="row.actionId"><td><strong>{{ row.actionTitle }}</strong></td><td><RouterLink :to="detailRoute(row)"><strong>{{ row.customer }}</strong><small>{{ row.title }} · {{ rowAmount(row) }}</small></RouterLink></td><td>{{ ownerName(row.actionOwner ?? row.owner) }}</td><td>{{ dayText(row.due) }}</td><td class="negative idle">{{ daysLate(row.due) ?? '—' }} {{ copy('d', '天') }}</td><td><span v-if="row.stalled" class="badge danger">{{ copy('Stalled deal', '商机停滞') }}</span><span v-else class="badge warn">{{ copy('Open', '未完成') }}</span></td><td v-if="overdueHandling" class="step-cell"><WarningNextStep v-if="row.handling" v-bind="stepBind(row.handling)" /><span v-else class="muted">—</span></td></tr></tbody></table></div>
          <p v-if="!data.overdue.length" class="empty-list">{{ copy('No overdue actions', '没有逾期的行动计划') }}</p>
          <footer v-if="busiestOwner" class="zone-note">{{ ownerName(busiestOwner.owner) }} {{ copy('owns', '名下有') }} {{ busiestOwner.count }} / {{ data.overdue.length }} {{ copy('overdue actions — check workload before adding new commitments', '条逾期行动，安排新任务前先看负荷') }}</footer>
          <footer v-else class="zone-note">{{ copy('Completing the action on the opportunity page clears the row', '在商机页把行动标记完成后，该行自动清除') }}</footer>
        </section>
        <section class="panel downgrade-panel" data-zone="downgrade"><div class="panel-heading"><div><h2>{{ copy('Probability level reduced', '概率降档') }}</h2><p>{{ copy('Downgrades in the period still awaiting the owner action; edit the plan here in the meeting', '本期降档且负责人尚未记录行动；行动计划可在例会中直接修改') }}</p></div><span class="zone-count">{{ warningCount('downgrade') }} {{ copy('deals', '个商机') }}</span></div>
          <div class="table-scroll"><table><thead><tr><th>{{ copy('Customer', '客户') }}</th><th>{{ copy('Value', '金额') }}</th><th>{{ copy('Level', '档位') }}</th><th>{{ copy('Reason', '原因') }}</th><th>{{ copy('Action plan', '行动计划') }}</th><th>{{ copy('Owner', '负责人') }}</th></tr></thead>
            <tbody><tr v-for="row in data.downgrade" :key="row.eventId ?? row.id" :data-downgrade-row="row.eventId"><td><RouterLink :to="detailRoute(row)"><strong>{{ row.customer }}</strong><small>{{ row.title }}<template v-if="row.stage"> · {{ label(row.stage) }}</template></small></RouterLink></td><td class="numeric">{{ rowAmount(row) }}</td><td class="level-cell"><span class="badge muted">{{ label(row.fromLevel ?? '') }}</span><span class="arrow">→</span><span class="badge warn">{{ label(row.toLevel ?? '') }}</span></td><td class="reason-cell"><p>{{ row.reason || copy('Reason not recorded', '未记录原因') }}</p></td><td class="plan-cell"><div v-if="planEdit?.eventId === row.eventId" class="plan-editor" data-plan-editor><textarea v-model="planDraft" rows="3" maxlength="4000" :disabled="planSaving" :aria-label="copy('Action plan', '行动计划')" data-plan-draft></textarea><div class="plan-editor-foot"><small>{{ copy('Editing in the meeting · the warning stays until the owner records the action', '例会中编辑 · 负责人记录行动后预警才清除') }}</small><button type="button" :disabled="planSaving" @click="cancelPlanEdit()">{{ copy('Cancel', '取消') }}</button><button type="button" class="save-plan" :disabled="busy || !planDraft.trim()" data-plan-save @click="savePlan()">{{ copy('Save', '保存') }}</button></div><p v-if="planError" class="dialog-error" role="alert">{{ planError }}<button v-if="planConflict" type="button" data-plan-reload @click="load()">{{ copy('Reload', '重新加载') }}</button></p></div><template v-else><button type="button" class="plan-box" :disabled="!row.opportunityModified || busy || !!planEdit || !!handlingEdit" data-plan-edit :title="row.opportunityModified ? copy('Edit the plan in the meeting', '在例会中编辑计划') : copy('Reload the page to edit this plan', '请重新加载后再编辑')" @click="startPlanEdit(row)"><span v-if="row.recovery?.plan" class="recovery-text">{{ row.recovery.plan }}</span><span v-else class="muted">{{ copy('No plan recorded yet — add one', '尚未记录行动计划，点击补录') }}</span><small v-if="row.recovery?.editedAt">{{ copy('edited', '编辑于') }} {{ dateText(row.recovery.editedAt) }} · {{ ownerName(row.recovery.editedBy) }}</small></button><RouterLink class="text-link" :to="detailRoute(row)">{{ copy('Open the deal · the owner records the action', '打开商机 · 由负责人记录行动') }} →</RouterLink></template></td><td>{{ ownerName(row.currentOwner ?? row.owner) }}</td></tr></tbody></table></div>
          <p v-if="!data.downgrade.length" class="empty-list">{{ copy('No downgrades awaiting action', '没有待处理的降档') }}</p>
          <footer class="zone-note"><template v-if="data.downgrade.length">{{ copy('Estimated value awaiting action', '待处理商机金额') }} {{ downgradeSummary.text }}<template v-if="largestDowngrade"> · {{ largestDowngrade.customer }} {{ copy('is the largest exposure', '是最大的一笔') }}</template></template><template v-else>{{ copy('Recording the action taken on the opportunity page clears the warning; editing the plan alone does not', '负责人在商机页记录已采取的行动后预警清除，只修改计划不清除') }}</template></footer>
        </section>
        <section class="panel other-panel" data-zone="other"><div class="panel-heading"><div><h2>{{ label('other_alerts') }}</h2><p>{{ copy('Deadlines, resources and commitments at risk', '到期、资源与承诺风险') }}</p></div><div class="zone-tools"><button v-if="handlingReady" ref="settingsOpener" type="button" class="settings-button" data-settings-open :disabled="busy" @click="openSettings()"><SlidersHorizontal :size="12" />{{ copy('Thresholds', '阈值设置') }}</button><span class="zone-count">{{ otherCount }}</span></div></div>
          <ul class="alert-list">
            <li v-for="row in data.quotationExpiryItems" :key="`${row.id}:${row.quotationVersionId}`" class="alert-item" data-alert="quotation_expiry"><span class="alert-mark"><TriangleAlert :size="14" /></span><div><strong>{{ copy('Quote validity expires', '报价有效期截止') }} {{ dayText(row.validUntil) }}<small class="alert-owner">{{ ownerName(row.owner) }}</small></strong><p><RouterLink :to="detailRoute(row)">{{ row.customer }} · {{ row.title }}</RouterLink> · V{{ row.quotationVersionNo }} · {{ row.daysToExpiry === 0 ? copy('due on the reference date', '截止日当天到期') : `${row.daysToExpiry} ${copy('days after the reference date', '天后到期')}` }} — {{ copy('extend or re-price before expiry', '到期前续期或重新报价') }}</p><WarningNextStep v-if="row.handling" v-bind="stepBind(row.handling)" /></div></li>
            <li v-for="row in stage6Items" :key="`s6:${row.id}`" class="alert-item" data-alert="stage6_no_po"><span class="alert-mark"><TriangleAlert :size="14" /></span><div><strong>{{ copy('In stage 6 without a PO for', '第 6 阶段未收到 PO 已') }} {{ row.daysAtLeast ? '≥' : '' }}{{ row.daysInStage }} {{ copy('days', '天') }}<small class="alert-owner">{{ ownerName(row.owner) }}</small></strong><p><RouterLink :to="detailRoute(row)">{{ row.customer }} · {{ row.title }}</RouterLink> · {{ rowAmount(row) }} — {{ copy('chase the order, or move or close the deal', '跟进客户下单，或更新 / 关闭商机') }}</p><WarningNextStep v-if="row.handling" v-bind="stepBind(row.handling)" /></div></li>
            <li v-if="!data.quotationExpiryItems.length && !stage6Items.length" class="alert-empty" data-alert-empty>{{ otherUnknown ? copy('Alert data is insufficient: an empty list does not mean there are no alerts', '提醒数据不足，列表为空不代表没有提醒') : stage6Known && stage6Handled.length ? copy('No quotes expiring and no stage 6 deal waiting for action', '没有即将到期的报价，暂无待处理的第 6 阶段超期商机') : stage6Known ? copy('No quotes expiring and no stage 6 deal waiting too long for a PO', '没有即将到期的报价，也没有第 6 阶段超期未收到 PO 的商机') : copy('No quotes expiring in this window', '没有即将到期的报价') }}</li>
          </ul>
          <template v-if="stage6Known && stage6Handled.length"><button type="button" class="backlog-toggle" data-s6-handled-toggle :aria-expanded="showHandled" @click="showHandled = !showHandled">{{ copy('Handled', '已处理') }} ({{ stage6Handled.length }}) · {{ showHandled ? copy('hide', '收起') : copy('stage 6 deals with an action recorded, back on the follow-up date if still without a PO; not counted', '第 6 阶段已记录行动，到复核日期仍无 PO 会重新提醒；不计入预警数') }}</button>
            <ul v-if="showHandled" class="handled-list" data-s6-handled><li v-for="row in stage6Handled" :key="`s6h:${row.id}`" :data-s6-handled-row="row.id"><RouterLink :to="detailRoute(row)">{{ row.customer }} · {{ row.title }}</RouterLink><WarningNextStep v-if="row.handling" v-bind="stepBind(row.handling)" /></li></ul></template>
          <footer class="zone-note">{{ copy('Reference date', '参考日') }} {{ data.quotationExpiry.referenceDate }} · {{ copy('quotes', '报价') }} {{ data.quotationExpiry.thresholdDays }} {{ copy('days', '天') }}<template v-if="data.stage6NoPo"> · {{ copy('stage 6', '第 6 阶段') }} {{ data.stage6NoPo.thresholdDays }} {{ copy('days', '天') }}</template> · {{ copy('Alerts clear on their own: a quote once accepted, rejected, replaced or its deal closes', '提醒自动清除：报价在接受、拒绝、换版或商机结束后') }}<template v-if="stage6Known">{{ copy('; a stage 6 deal once it has its PO or leaves stage 6', '；第 6 阶段商机在收到 PO 或离开第 6 阶段（推进、退回或关闭）后') }}<template v-if="handlingReady">{{ copy(', or once the action taken is recorded, until its follow-up date', '，或记录已采取行动后至复核日期') }}</template></template><template v-if="handlingReady">{{ copy('. Saving a next step never clears an alert', '。保存下一步不清除提醒') }}</template></footer>
        </section>
      </div>
      <footer class="review-footer"><strong>QIHENG DEMO CONFIDENTIAL</strong><span>{{ copy('Shanghai timezone · Missing data is not zero · Same scope and period as Review', '上海时区 · 数据不足不计为零 · 与 Review 同一筛选与周期') }}</span></footer>
    </template>
    <dialog ref="reviewDialog" class="review-dialog loss-review-dialog" :aria-label="copy('Lost-deal post-mortem', '丢单复盘')" @cancel="reviewSaving && $event.preventDefault()">
      <header><div><p class="eyebrow">{{ copy('POST-MORTEM', '丢单复盘') }}</p><h2>{{ reviewRow?.customer }}</h2></div><button :disabled="reviewSaving" :aria-label="copy('Close', '关闭')" @click="reviewDialog?.close()"><X :size="20" /></button></header>
      <template v-if="reviewRow">
        <dl class="review-facts"><div><dt>{{ copy('Opportunity', '商机') }}</dt><dd>{{ reviewRow.title }} · {{ rowAmount(reviewRow) }}</dd></div><div><dt>{{ copy('Lost', '丢单') }}</dt><dd>{{ dateText(reviewRow.at) }} · {{ label(reviewRow.stage ?? '') }} · {{ ownerName(reviewRow.owner) }}</dd></div><div><dt>{{ copy('Reason entered by Sales', '销售填写的原因') }}</dt><dd>{{ reviewRow.reason || copy('Reason not recorded', '未记录原因') }}</dd></div></dl>
        <form @submit.prevent="submitReview('Reviewed')">
          <label>{{ copy('Post-mortem conclusion', '复盘结论') }}<textarea v-model="reviewNote" rows="4" maxlength="4000" :disabled="reviewSaving || revertMode" data-review-note :placeholder="copy('What was confirmed in the post-mortem, and what changes next time', '复盘确认了什么，下次怎么改')"></textarea></label>
          <p class="dialog-note">{{ copy('The Sales reason stays as entered. Marking the loss reviewed counts it in the Review loss statistics; every change is kept in the audit trail.', '销售原因原样保留。标记已复盘后计入 Review 的丢单统计；每次修改都有留痕。') }}</p>
          <label v-if="revertMode">{{ copy('Reason for reverting to pending', '撤回复盘的原因') }}<textarea v-model="revertReason" rows="3" maxlength="4000" :disabled="reviewSaving" data-revert-reason :placeholder="copy('Why the post-mortem needs another look', '为什么需要重新复盘')"></textarea></label>
          <p v-if="reviewError" class="dialog-error" role="alert">{{ reviewError }}<button v-if="reviewConflict" type="button" data-review-reload @click="load()">{{ copy('Reload', '重新加载') }}</button></p>
          <footer v-if="revertMode"><button type="button" :disabled="reviewSaving" @click="revertMode = false">{{ copy('Keep reviewed', '不撤回') }}</button><button type="button" class="save-review" :disabled="busy || !revertReason.trim()" data-review-revert-confirm @click="submitReview('Pending')">{{ copy('Revert to pending', '确认改回待分析') }}</button></footer>
          <footer v-else><button v-if="reviewRow.review?.status === 'reviewed'" type="button" :disabled="reviewSaving" data-review-revert @click="revertMode = true">{{ copy('Revert to pending…', '改回待分析…') }}</button><button type="button" :disabled="reviewSaving" @click="reviewDialog?.close()">{{ copy('Cancel', '取消') }}</button><button type="submit" class="save-review" :disabled="busy || !reviewNote.trim()" data-review-submit>{{ reviewRow.review?.status === 'reviewed' ? copy('Save changes', '保存修改') : copy('Mark post-mortem done', '标记已复盘') }}</button></footer>
        </form>
      </template>
    </dialog>
    <dialog ref="settingsDialog" class="review-dialog settings-dialog" :aria-label="copy('Alert thresholds', '阈值设置')" @cancel="settingsSaving && $event.preventDefault()" @close="focusSettingsOpener()">
      <header><div><p class="eyebrow">{{ label('other_alerts') }}</p><h2>{{ copy('Alert thresholds', '阈值设置') }}</h2></div><button :disabled="settingsSaving" :aria-label="copy('Close', '关闭')" @click="closeSettings()"><X :size="20" /></button></header>
      <p v-if="settingsLoading" class="dialog-note" role="status">{{ copy('Loading…', '加载中…') }}</p>
      <form v-else-if="settings" @submit.prevent="saveSettings()">
        <label v-for="field in settingFields" :key="field.key">{{ field.label }}<input v-model="settingsDraft[field.key]" type="number" :min="minDays[field.key]" max="365" step="1" required :disabled="settingsSaving" :data-setting="field.key" /><small :data-setting-source="field.key">{{ sourceText(settings.sources[field.key]) }}<span v-if="validDays(field.key) === null" class="field-error" data-setting-invalid> · {{ copy(`Enter a whole number from ${minDays[field.key]} to 365`, `请输入 ${minDays[field.key]}–365 的整数`) }}</span></small></label>
        <p class="dialog-note" data-settings-modified>{{ copy('Last modified: ', '最后修改：') }}{{ settings.modified ? `${settings.modifiedByName || ownerName(settings.modifiedBy)} · ${dateText(settings.modified)}` : copy('not saved yet', '尚未保存') }}{{ copy('. The counts use the new values as soon as they are saved.', '。保存后预警数立即按新阈值计算。') }}</p>
        <p v-if="settingsError" class="dialog-error" role="alert">{{ settingsError }}<button v-if="settingsConflict" type="button" data-settings-reload @click="openSettings()">{{ copy('Reload', '重新加载') }}</button></p>
        <footer><button type="button" :disabled="settingsSaving" @click="closeSettings()">{{ copy('Cancel', '取消') }}</button><button type="submit" class="save-review" :disabled="busy || !settingsValid" data-settings-save>{{ copy('Save', '保存') }}</button></footer>
      </form>
      <p v-else-if="settingsError" class="dialog-error" role="alert">{{ settingsError }}<button type="button" @click="openSettings()">{{ copy('Retry', '重试') }}</button></p>
    </dialog>
  </div>
</template>

<style scoped>
:global(.route-content:has(.warnings-page)){max-width:2000px;padding:20px 24px}
.warnings-page{font-variant-numeric:tabular-nums;color:var(--crm-text);container-type:inline-size;font-size:13px}.warnings-page *{box-sizing:border-box}.warnings-page button,.warnings-page select,.warnings-page input,.warnings-page textarea{font:inherit;color:inherit}.warnings-page button{cursor:pointer}.warnings-page button:disabled,.warnings-page select:disabled{opacity:.5;cursor:default}.warnings-page button:focus-visible,.warnings-page select:focus-visible,.warnings-page input:focus-visible,.warnings-page textarea:focus-visible{outline:2px solid var(--crm-brand);outline-offset:3px}
.review-masthead{position:relative;isolation:isolate;overflow:hidden;padding:20px;margin-bottom:16px;border:1px solid var(--crm-line);border-top:3px solid var(--crm-danger);border-radius:var(--crm-radius-md);background:linear-gradient(120deg,#fff1ec 0%,#fffaf3 48%,var(--crm-surface) 100%)}
.review-header-art{position:absolute;z-index:-1;inset:0 12px 0 auto;width:300px;pointer-events:none;opacity:.12;mask-image:linear-gradient(90deg,transparent,#000 65%);-webkit-mask-image:linear-gradient(90deg,transparent,#000 65%)}.review-header-art img{width:100%;height:100%;object-fit:contain;object-position:right center}
.warnings-heading{display:grid;grid-template-columns:minmax(220px,.8fr) 2.2fr;gap:24px;align-items:start;min-height:88px;margin-bottom:16px}.eyebrow{color:var(--crm-text-muted);font-size:11px;margin:0 0 8px}.identity .eyebrow{color:var(--crm-link);font-weight:650;line-height:1.5}.identity .eyebrow::before{content:"";display:inline-block;width:7px;height:7px;margin-right:8px;border-radius:1px;background:var(--crm-brand);box-shadow:5px -5px 0 -1px rgb(255 142 1 / 35%)}.identity h1{font-size:28px;letter-spacing:-.6px;margin:0;line-height:1.15}.identity>p:last-child{margin:5px 0 0;color:var(--crm-text-muted)}
.summary-cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.summary-card{display:grid;gap:2px;min-width:0;padding:9px 14px;background:white;border:1px solid var(--crm-line);border-top:3px solid var(--crm-line-strong);border-radius:var(--crm-radius-sm)}.summary-card span{font-size:12px;line-height:1.3;color:var(--crm-text-muted)}.warnings-page .summary-cards .summary-card strong{font-size:26px!important;line-height:1.1!important;font-weight:750;letter-spacing:-.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.warnings-page .summary-cards .summary-card strong.text-value{font-size:17px!important;line-height:28.6px!important;letter-spacing:0}.summary-card small{font-size:11px;color:var(--crm-text-muted);line-height:1.3}.summary-card span,.summary-card small{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.summary-card.lost{border-top-color:var(--crm-danger)}.summary-card.lost small{color:var(--crm-danger)}.summary-card.overdue{border-top-color:var(--crm-warning)}.summary-card.overdue small{color:#9a5b00}.summary-card.downgrade{border-top-color:#b8412f}.summary-card.downgrade small{color:#b8412f}.summary-card.other{border-top-color:var(--crm-link)}.summary-card.other small{color:var(--crm-link)}
.review-controls{position:relative;display:flex;flex-wrap:wrap;gap:8px;align-items:center}.plan-tab{padding:7px 16px;min-height:34px;border:1px solid var(--crm-line);border-radius:var(--crm-radius-sm);background:white;color:var(--crm-text);text-decoration:none}.plan-tab:hover{background:var(--crm-surface-muted)}.plan-tab.is-disabled{color:var(--crm-text-muted);background:var(--crm-surface-muted);cursor:default}.review-tab{background:var(--crm-navy);color:white;padding:7px 16px;min-height:34px;border-radius:var(--crm-radius-sm)}.review-controls label{display:flex;gap:6px;align-items:center;min-height:34px;background:white;border:1px solid var(--crm-line);border-radius:var(--crm-radius-sm);padding:5px 8px;white-space:nowrap;color:var(--crm-text-muted)}.review-controls select{border:0;background:transparent;max-width:135px;min-width:0;min-height:22px;font-weight:600}.warnings-page input{border:1px solid var(--crm-line);border-radius:var(--crm-radius-sm);background:white;padding:5px 7px;min-width:0}.period-controls{display:flex;gap:4px;align-items:center;margin-left:auto}.period-controls>button{display:inline-flex;align-items:center;justify-content:center;border:1px solid var(--crm-line);background:white;border-radius:var(--crm-radius-sm);min-height:34px}.period-controls input{width:125px}.segmented{display:flex;flex-shrink:0;border:1px solid var(--crm-line);border-radius:var(--crm-radius-sm);overflow:hidden}.segmented button{background:white;border:0;padding:6px 10px;font-weight:600}.segmented button.active{background:var(--crm-brand);color:var(--crm-brand-ink)}
.refresh-error{display:flex;align-items:center;gap:8px;margin:0 0 12px;padding:8px 12px;border:1px solid #e6b4ae;border-radius:var(--crm-radius-sm);background:var(--crm-danger-soft);color:var(--crm-danger);font-size:12px}.refresh-error button{border:1px solid var(--crm-line);background:white;border-radius:4px;padding:3px 8px;font-size:11px}.review-state{padding:40px;text-align:center;color:var(--crm-text-muted);background:white;border:1px solid var(--crm-line);border-radius:var(--crm-radius-md)}.review-state.error{color:var(--crm-danger)}.review-state button{margin-top:10px;border:1px solid var(--crm-line);background:white;border-radius:var(--crm-radius-sm);padding:6px 12px}
.warnings-grid{display:grid;grid-template-columns:1.15fr 1fr;gap:16px}.panel{display:flex;flex-direction:column;min-width:0;min-height:0;background:white;border:1px solid var(--crm-line);border-radius:var(--crm-radius-md);overflow:hidden}.panel-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:16px 18px 10px;flex-shrink:0}.panel h2{margin:0;line-height:1.25;letter-spacing:-.2px;font-size:16px}.panel-heading p{color:var(--crm-text-muted);margin:4px 0 0;font-size:12px;line-height:1.4}.zone-count{flex-shrink:0;padding:4px 10px;border-radius:999px;background:var(--crm-surface-muted);color:var(--crm-text-muted);font-size:12px;font-weight:650;white-space:nowrap}.lost-panel{border-top:3px solid var(--crm-danger)}.overdue-panel{border-top:3px solid var(--crm-warning)}.downgrade-panel{border-top:3px solid #b8412f}.other-panel{border-top:3px solid var(--crm-link)}
.table-scroll{overflow:auto;min-height:0;padding:0 18px;flex:1}table{border-collapse:collapse;width:100%;font-size:12px;text-align:left}th,td{padding:12px 7px;border-bottom:1px solid var(--crm-line);vertical-align:top;font-variant-numeric:tabular-nums}th:first-child,td:first-child{padding-left:0}th:last-child,td:last-child{padding-right:0}thead th{color:var(--crm-text-muted);font-size:11px;font-weight:650;white-space:nowrap;position:sticky;top:0;background:white}td strong{display:block}td small{display:block;color:var(--crm-text-muted);line-height:1.4;margin-top:3px}td a{color:inherit;text-decoration:none}td a:hover{text-decoration:underline}tr:last-child td{border-bottom:0}.numeric{white-space:nowrap}.idle{font-weight:750;white-space:nowrap}.negative{color:var(--crm-danger)}.muted{color:var(--crm-text-muted)}.reason-cell p,.plan-cell p{margin:0;line-height:1.5}.reason-cell small{margin-top:4px;color:var(--crm-positive-ink)}.recovery-text{white-space:pre-wrap;overflow-wrap:anywhere;max-width:320px}.plan-cell .text-link{display:inline-block;margin-top:4px}.plan-box{display:grid;gap:4px;width:100%;max-width:340px;padding:8px 10px;border:1px dashed var(--crm-line-strong);border-radius:var(--crm-radius-sm);background:white;text-align:left;line-height:1.5}.plan-box:hover:not(:disabled){border-color:var(--crm-link)}.plan-box small{color:var(--crm-text-muted);font-size:11px}.plan-editor{display:grid;gap:6px;max-width:360px;padding:8px;border:1px solid var(--crm-link);border-radius:var(--crm-radius-sm)}.plan-editor textarea{border:0;resize:vertical;min-height:60px;padding:0;line-height:1.5}.plan-editor textarea:focus-visible{outline:0}.plan-editor-foot{display:flex;align-items:center;gap:6px}.plan-editor-foot small{flex:1;color:var(--crm-link);font-size:11px}.plan-editor-foot button{border:1px solid var(--crm-line);background:white;border-radius:4px;padding:3px 8px;font-size:11px}.plan-editor-foot .save-plan{background:var(--crm-navy);border-color:var(--crm-navy);color:white;font-weight:650}.level-cell{white-space:nowrap}.level-cell .arrow{margin:0 6px;color:var(--crm-text-muted)}
.badge{display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:999px;font-size:11px;font-weight:650;white-space:nowrap;line-height:1.3}.badge.muted{background:var(--crm-surface-muted);color:var(--crm-text-muted)}.badge.warn{background:var(--crm-warning-soft);color:#9a5b00}.badge.danger{background:var(--crm-danger-soft);color:var(--crm-danger)}.badge.done{background:#e8f5ee;color:var(--crm-positive-ink);white-space:normal}.review-cell{min-width:150px}.review-cell .badge{margin-bottom:6px}.review-button{display:block;padding:5px 10px;border:1px solid var(--crm-brand);border-radius:var(--crm-radius-sm);background:var(--crm-brand);color:var(--crm-brand-ink);font-size:11px;font-weight:650}.text-link{padding:0;border:0;background:none;color:var(--crm-link);font-weight:650;text-decoration:none;font-size:11px}.text-link:hover{text-decoration:underline}
.backlog-only{margin:6px 18px 0;color:var(--crm-text-muted);font-size:12px}.backlog-toggle{margin:4px 18px 10px;padding:6px 10px;border:1px dashed var(--crm-line-strong);border-radius:var(--crm-radius-sm);background:var(--crm-surface-muted);color:var(--crm-text-muted);font-size:12px;text-align:left}tr.backlog td{background:#fffaf5}.empty-list{display:grid;place-items:center;margin:0;padding:28px 20px;min-height:80px;color:var(--crm-text-muted);text-align:center}.zone-note{padding:12px 18px 14px;border-top:1px solid var(--crm-line);font-size:12px;font-weight:650;color:#9a5b00;line-height:1.5}.lost-panel .zone-note{color:var(--crm-danger)}.downgrade-panel .zone-note{color:#b8412f}.other-panel .zone-note{color:var(--crm-text-muted);font-weight:500}
.alert-list{list-style:none;margin:0;padding:4px 18px 8px;flex:1}.alert-item{display:grid;grid-template-columns:auto minmax(0,1fr);gap:12px;padding:12px 0;border-bottom:1px solid var(--crm-line)}.alert-item:last-child{border-bottom:0}.alert-mark{display:grid;place-items:center;width:26px;height:26px;border-radius:50%;background:var(--crm-warning-soft);color:#9a5b00}.alert-mark.muted{background:var(--crm-surface-muted);color:var(--crm-text-muted)}.alert-item strong{display:flex;justify-content:space-between;gap:12px;font-size:13px}.alert-owner{font-weight:500;color:var(--crm-text-muted);font-size:11px;white-space:nowrap}.alert-item p{margin:4px 0 0;color:var(--crm-text-muted);font-size:12px;line-height:1.5}.alert-item a{color:var(--crm-link);text-decoration:none}.alert-empty{padding:20px 0;color:var(--crm-text-muted);text-align:center}
.review-footer{display:flex;justify-content:space-between;gap:12px;margin-top:16px;color:var(--crm-text-muted);font-size:11px}
.review-dialog{border:1px solid var(--crm-line);border-radius:9px;color:var(--crm-text);padding:22px;width:min(560px,90vw);max-height:85vh;overflow:auto}.review-dialog::backdrop{background:rgba(24,27,31,.42)}.review-dialog header{display:flex;justify-content:space-between;align-items:center;gap:20px}.review-dialog h2{margin:0;font-size:20px!important}.review-dialog header button{border:0;background:none}.review-dialog button{border:1px solid var(--crm-line);background:white;padding:6px 10px;border-radius:4px}.review-facts{display:grid;gap:8px;margin:16px 0 0;font-size:12px}.review-facts div{display:grid;grid-template-columns:110px minmax(0,1fr);gap:8px}.review-facts dt{color:var(--crm-text-muted)}.review-facts dd{margin:0;line-height:1.5}.loss-review-dialog form{display:grid;gap:12px;margin-top:16px}.loss-review-dialog label{display:grid;gap:6px;font-size:12px}.loss-review-dialog textarea{border:1px solid var(--crm-line);border-radius:var(--crm-radius-sm);padding:8px;resize:vertical;min-height:90px}.dialog-note{margin:0;font-size:12px;color:var(--crm-text-muted);line-height:1.6}.dialog-error{display:flex;gap:10px;align-items:center;margin:0;color:var(--crm-danger);font-size:12px}.loss-review-dialog footer{display:flex;justify-content:flex-end;gap:8px}.loss-review-dialog button.save-review{background:var(--crm-brand);border-color:var(--crm-brand);color:var(--crm-brand-ink);font-weight:650}
.zone-tools{display:flex;align-items:center;gap:8px;flex-shrink:0}.settings-button{display:inline-flex;align-items:center;gap:4px;padding:3px 9px;border:1px solid var(--crm-line);border-radius:999px;background:white;color:var(--crm-link);font-size:11px;font-weight:650;white-space:nowrap}.settings-button:hover:not(:disabled){border-color:var(--crm-link)}
.step-cell{min-width:200px}.step-cell .next-step{margin-top:0}.handling-notice{border-color:var(--crm-line);background:var(--crm-surface-muted);color:var(--crm-text)}
.handled-list{list-style:none;display:grid;gap:8px;margin:0 18px 10px;padding:0}.handled-list li{padding:8px 10px;border:1px solid var(--crm-line);border-radius:var(--crm-radius-sm);background:var(--crm-surface-muted);font-size:12px}.handled-list a{color:var(--crm-link);font-weight:650;text-decoration:none}.handled-list .next-step{margin-top:6px}
.settings-dialog{width:min(440px,90vw)}.settings-dialog form{display:grid;gap:14px;margin-top:16px}.settings-dialog label{display:grid;gap:6px;font-size:12px}.settings-dialog label input{width:120px}.settings-dialog label small{color:var(--crm-text-muted);font-size:11px}.field-error{color:var(--crm-danger)}.settings-dialog footer{display:flex;justify-content:flex-end;gap:8px}.settings-dialog button.save-review{background:var(--crm-brand);border-color:var(--crm-brand);color:var(--crm-brand-ink);font-weight:650}
@container(max-width:1350px){.warnings-heading{grid-template-columns:1fr 2fr;gap:16px}.identity h1{font-size:24px}.warnings-page .summary-cards .summary-card strong{font-size:22px!important}.warnings-page .summary-cards .summary-card strong.text-value{font-size:15px!important;line-height:24.2px!important}.warnings-grid{grid-template-columns:1fr}}
@container(max-width:900px){.warnings-heading{grid-template-columns:1fr}.summary-cards{grid-template-columns:1fr 1fr}.period-controls{margin-left:0;flex-wrap:wrap}.review-controls label{flex:1;justify-content:space-between}.table-scroll{padding:0 14px}.review-footer{flex-wrap:wrap}}
@media(forced-colors:active){.review-header-art{display:none}}
/* Cockpit mastheads wrap the same way below a 1860px page (above it the widest first row, English Review with its
   target button and four 135px-capped selects, about 1810px, still fits): the period (or scope) controls take their own
   second row on Review, Plan, Warnings and Opportunities, and the filters share the first row instead of
   wrapping, so the four top cards stay the same height. */
@container(max-width:1860px){.review-controls .period-controls{flex-basis:100%;margin-left:0}.review-controls label{flex:1 1 110px;max-width:max-content;min-width:0}}
/* Below a 1200px page the filter names give way so the four first-row selects stay readable; each select keeps its aria-label. */
@container(max-width:1200px){.review-controls .filter-name{display:none}}
</style>
