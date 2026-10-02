<script setup lang="ts">
import { requestErrorMessage } from '@/api/request-state'
import { personnelDisplayName } from '@/demo/personnel'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter, type RouteLocationRaw } from 'vue-router'
import { CalendarDays, ChevronLeft, ChevronRight, Clock3, MapPin, UserRound, UsersRound } from '@lucide/vue'
import { api as defaultApi, type CrmApi } from '@/api'
import { useAppStore } from '@/stores/app'
import { formatDisplayDate } from '@/domain/time'
import { isTerminatedDemo, terminatedDemoRequestMatcher } from '@/domain/evaluations'
import type { ApiResponse, BookingDto, DemoRequestDto, EvaluationDto, PageData, VisitDto } from '@/types/crm'
import { useI18n, useLocaleMessage } from '@/i18n'

type CalendarEventType = 'visit' | 'demo-request' | 'demo-test' | 'booking'
interface CalendarEvent {
  id: string
  sourceId: string
  type: CalendarEventType
  date: string
  title: string
  account: string
  owner: string
  detail: string
}

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const app = useAppStore()
const router = useRouter()
const { locale, t, message } = useI18n()
const loading = ref(true)
const error = useLocaleMessage()
const sources = ref<{ visits: VisitDto[]; requests: DemoRequestDto[]; evaluations: EvaluationDto[]; linkedEvaluations: EvaluationDto[]; bookings: BookingDto[] }>({
  visits: [], requests: [], evaluations: [], linkedEvaluations: [], bookings: [],
})
const view = ref<'month' | 'week'>('month')
const cursor = ref(new Date())
const selectedId = ref('')
const selectedDate = ref('')
const isBoss = computed(() => app.bootstrap?.user.role === 'Manager')
const isEngineer = computed(() => app.bootstrap?.user.role === 'Engineer')
const scope = ref<'mine' | 'all'>(isBoss.value ? 'all' : 'mine')
const currentUser = computed(() => app.bootstrap?.user.id ?? '')
const accountFilter = ref('')
const ownerFilter = ref('')
let loadRevision = 0
let activeLoadKey = ''
let loadedBootstrapKey = ''

const typeMeta = computed<Record<CalendarEventType, { label: string; className: string }>>(() => ({
  visit: { label: t('calendar.event.visit'), className: 'visit' },
  'demo-request': { label: t('calendar.event.demoRequest'), className: 'request' },
  'demo-test': { label: t('calendar.event.demoTest'), className: 'test' },
  booking: { label: t('calendar.event.booking'), className: 'booking' },
}))

const weekdayLabels = computed(() => [
  t('calendar.weekday.sun'),
  t('calendar.weekday.mon'),
  t('calendar.weekday.tue'),
  t('calendar.weekday.wed'),
  t('calendar.weekday.thu'),
  t('calendar.weekday.fri'),
  t('calendar.weekday.sat'),
])
const monthWeekdayLabels = computed(() => [...weekdayLabels.value.slice(1), weekdayLabels.value[0]])

function iso(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
function addDays(date: Date, value: number) {
  const next = new Date(date)
  next.setDate(next.getDate() + value)
  return next
}
function startOfWeek(date: Date) {
  const next = new Date(date)
  const day = next.getDay() || 7
  next.setDate(next.getDate() - day + 1)
  next.setHours(0, 0, 0, 0)
  return next
}
function isMine(event: CalendarEvent) {
  return event.owner === currentUser.value
}
// A terminated Demo no longer has a Test DDL or a customer expected date to chase.
const isTerminatedRequest = computed(() => terminatedDemoRequestMatcher([...sources.value.evaluations, ...sources.value.linkedEvaluations]))
const events = computed(() => [
  ...sources.value.visits.map((item): CalendarEvent => ({
    id: `visit-${item.id}`, sourceId: item.id, type: 'visit', date: item.date, title: item.subject,
    account: item.accountName, owner: item.owner, detail: `${item.type} · ${item.objective}`,
  })),
  ...sources.value.requests.filter((item) => item.status !== 'Cancelled' && !isTerminatedRequest.value(item)).map((item): CalendarEvent => ({
    id: `request-${item.id}`, sourceId: item.id, type: 'demo-request', date: item.customerExpectedDate || item.targetDate,
    title: `${item.id} ${t('calendar.customerExpected')}`, account: item.accountName, owner: isEngineer.value ? item.engineerOwner : item.salesOwner,
    detail: `${item.title} · ${item.requestedEquipment}`,
  })),
  ...sources.value.evaluations.filter((item) => item.testRunDeadline && !isTerminatedDemo(item)).map((item): CalendarEvent => ({
    id: `test-${item.id}`, sourceId: item.id, type: 'demo-test', date: item.testRunDeadline,
    title: `${item.id} ${t('calendar.testRunDdl')}`, account: item.accountName, owner: item.owner,
    detail: item.title,
  })),
  ...sources.value.bookings.filter((item) => item.status !== 'Cancelled' && item.ddl).map((item): CalendarEvent => ({
    id: `booking-${item.id}`, sourceId: item.id, type: 'booking', date: item.ddl,
    title: `${item.id} ${t('calendar.customerDdl')}`, account: item.accountName, owner: item.owner,
    detail: `${item.equipment} · ${item.quantity} ${t('calendar.units')}`,
  })),
].filter((item) => item.date))
const scopedEvents = computed(() => isBoss.value && scope.value === 'mine' ? events.value.filter(isMine) : events.value)
const accountOptions = computed(() => [...new Set(scopedEvents.value.map((item) => item.account).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-CN')))
const ownerOptions = computed(() => [...new Set(scopedEvents.value.map((item) => item.owner).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-CN')))
const visibleEvents = computed(() => [...scopedEvents.value]
  .filter((item) => !accountFilter.value || item.account === accountFilter.value)
  .filter((item) => !ownerFilter.value || item.owner === ownerFilter.value)
  .sort((a, b) => a.date.localeCompare(b.date) || a.title.localeCompare(b.title)))
const dayEvents = computed(() => selectedDate.value
  ? visibleEvents.value.filter((item) => item.date === selectedDate.value)
  : [])
const monthDays = computed(() => {
  const first = new Date(cursor.value.getFullYear(), cursor.value.getMonth(), 1)
  const gridStart = startOfWeek(first)
  return Array.from({ length: 42 }, (_, index) => addDays(gridStart, index))
})
const weekDays = computed(() => {
  const first = startOfWeek(cursor.value)
  return Array.from({ length: 7 }, (_, index) => addDays(first, index))
})
const title = computed(() => {
  if (locale.value === 'zh-CN' && view.value === 'month') return `${cursor.value.getFullYear()}年 ${cursor.value.getMonth() + 1}月`
  const format = (date: Date) => new Intl.DateTimeFormat(locale.value, { year: 'numeric', month: 'short', day: 'numeric' }).format(date)
  return view.value === 'month' ? new Intl.DateTimeFormat(locale.value, { year: 'numeric', month: 'long' }).format(cursor.value) : `${format(weekDays.value[0])} — ${format(weekDays.value[6])}`
})
const selected = computed(() => visibleEvents.value.find((item) => item.id === selectedId.value) ?? visibleEvents.value[0])
const today = iso(new Date())

function eventsOn(date: Date) {
  const dateKey = iso(date)
  return visibleEvents.value.filter((item) => item.date === dateKey)
}
function move(direction: number) {
  const next = new Date(cursor.value)
  if (view.value === 'month') next.setMonth(next.getMonth() + direction, 1)
  else next.setDate(next.getDate() + direction * 7)
  cursor.value = next
}
function backToToday() {
  cursor.value = new Date()
}
function choose(event: CalendarEvent) {
  selectedDate.value = ''
  selectedId.value = event.id
}
function showDay(date: Date) {
  selectedDate.value = iso(date)
  selectedId.value = eventsOn(date)[0]?.id ?? ''
}
function chooseFromDay(event: CalendarEvent) {
  selectedId.value = event.id
}
function detailRoute(event: CalendarEvent): RouteLocationRaw {
  if (event.type === 'visit') return { name: 'visits', query: { focus: event.sourceId } }
  if (event.type === 'demo-request') return { name: 'demo-detail', params: { demoId: event.sourceId }, query: { from: 'demo-requests' } }
  if (event.type === 'demo-test') return { name: 'evaluations', query: { focus: event.sourceId } }
  return { name: 'booking-detail', params: { bookingId: event.sourceId } }
}
function openDetail(event: CalendarEvent) {
  void router.push(detailRoute(event))
}
function clearFilters() {
  accountFilter.value = ''
  ownerFilter.value = ''
  selectedId.value = ''
  selectedDate.value = ''
}

async function load() {
  const rangeDays = view.value === 'month' ? monthDays.value : weekDays.value
  const dateFrom = iso(rangeDays[0]!)
  const dateTo = iso(rangeDays.at(-1)!)
  const loadKey = `${view.value}|${dateFrom}|${dateTo}|${scope.value}|${currentUser.value}`
  if (activeLoadKey === loadKey) return
  activeLoadKey = loadKey
  const revision = ++loadRevision
  loading.value = events.value.length === 0
  error.value = ''
  try {
    async function readAll<T>(readPage: (page: number) => Promise<ApiResponse<PageData<T>>>) {
      const first = await readPage(1)
      const items = [...first.data.items]
      const total = first.meta?.total ?? items.length
      for (let page = 2; items.length < total; page += 1) items.push(...(await readPage(page)).data.items)
      return items
    }
    const visitsRequest = app.can('visit:view')
      ? readAll((page) => props.apiClient.listVisits({ page, pageSize: 200, dateFrom, dateTo }))
      : Promise.resolve([])
    const [visits, requests, evaluations, pipeline] = await Promise.all([
      visitsRequest,
      readAll((page) => props.apiClient.listDemoRequests({ page, pageSize: 200, dateFrom, dateTo })),
      readAll((page) => props.apiClient.listEvaluations({ page, pageSize: 200, dateFrom, dateTo })),
      props.apiClient.listPipeline({ dateFrom, dateTo }),
    ])
    // The Evaluation list only holds Test DDLs in this range. A shown request can link to an
    // Evaluation outside it (e.g. terminated before any DDL was set), so read those by id.
    const loadedEvaluationIds = new Set(evaluations.map((item) => item.id))
    const missingEvaluationIds = [...new Set(requests
      .filter((item) => item.status !== 'Cancelled' && item.evaluationId && !loadedEvaluationIds.has(item.evaluationId))
      .map((item) => item.evaluationId!))]
    const linkedEvaluations = (await Promise.all(missingEvaluationIds.map((id) =>
      // An unreadable link keeps its request event, as before.
      props.apiClient.getEvaluation(id).then((result) => result.data, () => null))))
      .filter((item): item is EvaluationDto => item !== null)
    if (revision !== loadRevision) return
    sources.value = { visits, requests, evaluations, linkedEvaluations, bookings: pipeline.data.bookings }
    if (!visibleEvents.value.some((item) => item.id === selectedId.value)) selectedId.value = visibleEvents.value[0]?.id ?? ''
  } catch (reason) {
    if (revision === loadRevision) error.value = requestErrorMessage(reason, message('calendar.loadFailed'))
  } finally {
    if (revision === loadRevision) {
      loading.value = false
      if (activeLoadKey === loadKey) activeLoadKey = ''
    }
  }
}

onMounted(async () => {
  await app.loadBootstrap(props.apiClient)
  if (!app.bootstrap && app.error) {
    error.value = app.errorSource
    loading.value = false
  }
})
watch(
  () => app.bootstrap,
  (bootstrap) => {
    if (!bootstrap) return
    const bootstrapKey = `${bootstrap.user.id}|${bootstrap.user.role}`
    if (bootstrapKey === loadedBootstrapKey) return
    loadedBootstrapKey = bootstrapKey
    scope.value = bootstrap.user.role === 'Manager' ? 'all' : 'mine'
    clearFilters()
    void load()
  },
  { immediate: true },
)
watch(scope, clearFilters)
watch([cursor, view], () => { void load() })
</script>

<template>
  <div class="workspace-page calendar-page" data-page="calendar">
    <header class="page-title-row">
      <div><span class="eyebrow">{{ t('calendar.eyebrow') }}</span><h1>{{ t('calendar.title') }}</h1><p>{{ t('calendar.description') }}</p></div>
      <span class="context-chip"><CalendarDays :size="15" />{{ t('calendar.items', { count: visibleEvents.length }) }}</span>
    </header>

    <section class="calendar-shell">
      <header class="calendar-toolbar">
        <div class="calendar-navigation">
          <button type="button" :aria-label="t('calendar.previousPeriod')" @click="move(-1)"><ChevronLeft :size="17" /></button>
          <button class="today-button" type="button" @click="backToToday">{{ t('calendar.today') }}</button>
          <button type="button" :aria-label="t('calendar.nextPeriod')" @click="move(1)"><ChevronRight :size="17" /></button>
          <h2>{{ title }}</h2>
        </div>
        <div class="calendar-controls">
          <div class="scope-switch">
            <button type="button" :class="{ active: scope === 'mine' }" @click="scope = 'mine'"><UserRound :size="13" />{{ t('calendar.mine') }}</button>
            <button v-if="isBoss" type="button" :class="{ active: scope === 'all' }" @click="scope = 'all'"><UsersRound :size="13" />{{ t('calendar.all') }}</button>
          </div>
          <div class="view-switch"><button type="button" :class="{ active: view === 'week' }" @click="view = 'week'">{{ t('calendar.week') }}</button><button type="button" :class="{ active: view === 'month' }" @click="view = 'month'">{{ t('calendar.month') }}</button></div>
        </div>
      </header>

      <div class="calendar-filters" :aria-label="t('calendar.filtersLabel')">
        <strong>{{ t('calendar.category') }}</strong>
        <label>
          <span>{{ t('calendar.account') }}</span>
          <select v-model="accountFilter" :aria-label="t('calendar.account')">
            <option value="">{{ t('calendar.allAccounts') }}</option>
            <option v-for="account in accountOptions" :key="account" :value="account">{{ account }}</option>
          </select>
        </label>
        <label>
          <span>{{ t('calendar.owner') }}</span>
          <select v-model="ownerFilter" :aria-label="t('calendar.owner')">
            <option value="">{{ t('calendar.allOwners') }}</option>
            <option v-for="owner in ownerOptions" :key="owner" :value="owner">{{ personnelDisplayName(owner) }}</option>
          </select>
        </label>
        <button v-if="accountFilter || ownerFilter" type="button" @click="clearFilters">{{ t('calendar.reset') }}</button>
      </div>

      <div class="calendar-legend">
        <span v-for="(meta, key) in typeMeta" :key="key"><i :class="meta.className" />{{ meta.label }}</span>
      </div>

      <div v-if="loading" class="calendar-state">{{ t('calendar.loading') }}</div>
      <div v-else-if="error" class="calendar-state error">{{ error }}</div>
      <div v-else class="calendar-layout">
        <div class="calendar-main">
          <div v-if="view === 'month'" class="month-view">
            <div v-for="label in monthWeekdayLabels" :key="label" class="weekday">{{ locale === 'zh-CN' ? `周${label}` : label }}</div>
            <div v-for="day in monthDays" :key="iso(day)" class="day-cell" :class="{ muted: day.getMonth() !== cursor.getMonth(), today: iso(day) === today }">
              <time>{{ day.getDate() }}</time>
              <button v-for="event in eventsOn(day).slice(0, 3)" :key="event.id" type="button" class="calendar-event" :class="[typeMeta[event.type].className, { selected: selected?.id === event.id }]" :title="`${event.title} · ${event.account}`" @click="choose(event)">
                <span>{{ event.title }}</span><small>{{ personnelDisplayName(event.owner) }}</small>
              </button>
              <button v-if="eventsOn(day).length > 3" type="button" class="more-events" @click="showDay(day)">{{ t('calendar.more', { count: eventsOn(day).length - 3 }) }}</button>
            </div>
          </div>
          <div v-else class="week-view">
            <article v-for="day in weekDays" :key="iso(day)" class="week-day" :class="{ today: iso(day) === today }">
              <header><span>{{ weekdayLabels[day.getDay()] }}</span><strong>{{ day.getDate() }}</strong></header>
              <div class="week-events">
                <button v-for="event in eventsOn(day)" :key="event.id" type="button" class="week-event" :class="[typeMeta[event.type].className, { selected: selected?.id === event.id }]" @click="choose(event)">
                  <small>{{ typeMeta[event.type].label }}</small><strong>{{ event.title }}</strong><span>{{ event.account }}</span><em>{{ personnelDisplayName(event.owner) }}</em>
                </button>
                <p v-if="!eventsOn(day).length">{{ t('calendar.noSchedule') }}</p>
              </div>
            </article>
          </div>
        </div>

        <aside class="event-detail">
          <template v-if="selectedDate">
            <header class="day-agenda-header">
              <div><small>{{ t('calendar.dayOverview') }}</small><strong>{{ selectedDate }}</strong><span>{{ t('calendar.dayMatches', { count: dayEvents.length }) }}</span></div>
              <button type="button" :aria-label="t('calendar.closeDay')" @click="selectedDate = ''">×</button>
            </header>
            <div v-if="dayEvents.length" class="day-agenda-list">
              <button
                v-for="event in dayEvents"
                :key="event.id"
                type="button"
                :class="{ active: selected?.id === event.id }"
                @click="chooseFromDay(event)"
              >
                <small :class="typeMeta[event.type].className">{{ typeMeta[event.type].label }}</small>
                <strong>{{ event.title }}</strong>
                <span>{{ event.account }} · {{ personnelDisplayName(event.owner) }}</span>
              </button>
            </div>
            <div v-else class="empty-detail"><Clock3 :size="23" /><span>{{ t('calendar.noDayMatches') }}</span></div>
            <section v-if="selected" class="day-agenda-detail">
              <strong>{{ selected.title }}</strong>
              <p><MapPin :size="13" />{{ selected.account }}</p>
              <p><UserRound :size="13" />{{ personnelDisplayName(selected.owner) }}</p>
              <span>{{ selected.detail }}</span>
              <button class="secondary-button" type="button" data-calendar-detail @click="openDetail(selected)">{{ t('calendar.details') }}</button>
            </section>
          </template>
          <template v-else-if="selected">
            <span class="event-type" :class="typeMeta[selected.type].className">{{ typeMeta[selected.type].label }}</span>
            <h3>{{ selected.title }}</h3>
            <p><CalendarDays :size="14" />{{ formatDisplayDate(selected.date) }}</p>
            <p><MapPin :size="14" />{{ selected.account }}</p>
            <p><UserRound :size="14" />{{ personnelDisplayName(selected.owner) }}</p>
            <div><strong>{{ t('calendar.scheduleDetails') }}</strong><span>{{ selected.detail }}</span></div>
            <small>{{ t('calendar.syncNote') }}</small>
            <button class="secondary-button" type="button" data-calendar-detail @click="openDetail(selected)">{{ t('calendar.details') }}</button>
          </template>
          <div v-else class="empty-detail"><Clock3 :size="23" /><span>{{ t('calendar.noCurrentSchedule') }}</span></div>
        </aside>
      </div>
    </section>
  </div>
</template>

<style scoped>
.calendar-shell{overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:15px;box-shadow:0 10px 28px rgba(31,35,41,.04)}.calendar-toolbar{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:14px 16px;border-bottom:1px solid var(--crm-line)}.calendar-navigation,.calendar-controls,.scope-switch,.view-switch{display:flex;align-items:center;gap:6px}.calendar-navigation button,.scope-switch button,.view-switch button{display:inline-flex;height:34px;align-items:center;justify-content:center;gap:5px;padding:0 10px;color:var(--crm-text-muted);background:#fff;border:1px solid var(--crm-line);border-radius:8px;font-size:9px;font-weight:700;cursor:pointer}.calendar-navigation button:not(.today-button){width:34px;padding:0}.calendar-navigation h2{min-width:190px;margin:0 0 0 8px;color:var(--crm-navy);font-size:14px}.scope-switch,.view-switch{padding:3px;background:#eef2f1;border-radius:9px}.scope-switch button,.view-switch button{height:29px;background:transparent;border:0}.scope-switch button.active,.view-switch button.active{color:var(--crm-navy);background:#fff;box-shadow:0 1px 4px rgba(31,35,41,.1)}.view-switch button{min-width:34px}.calendar-filters{display:flex;align-items:center;gap:10px;padding:10px 16px;background:#fbfcfc;border-bottom:1px solid var(--crm-line)}.calendar-filters>strong{color:var(--crm-navy);font-size:9px}.calendar-filters label{display:flex;align-items:center;gap:6px;color:var(--crm-text-muted);font-size:8px;font-weight:700}.calendar-filters select{min-width:150px;height:30px;padding:0 28px 0 9px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:7px;font-size:8px}.calendar-filters>button{margin-left:auto;padding:6px 9px;color:var(--crm-teal);background:transparent;border:0;cursor:pointer;font-size:8px;font-weight:700}.calendar-legend{display:flex;flex-wrap:wrap;gap:15px;padding:10px 16px;color:var(--crm-text-muted);border-bottom:1px solid var(--crm-line);font-size:8px}.calendar-legend span{display:flex;align-items:center;gap:6px}.calendar-legend i{width:8px;height:8px;border-radius:3px}.calendar-layout{display:grid;grid-template-columns:minmax(0,1fr) 250px;min-height:620px}.calendar-main{min-width:0;border-right:1px solid var(--crm-line)}.month-view{display:grid;grid-template-columns:repeat(7,minmax(0,1fr))}.weekday{padding:9px;color:var(--crm-text-muted);background:#FAF8F5;border-right:1px solid var(--crm-line);border-bottom:1px solid var(--crm-line);font-size:8px;font-weight:800;text-align:center}.day-cell{min-height:96px;padding:7px;border-right:1px solid var(--crm-line);border-bottom:1px solid var(--crm-line)}.day-cell:nth-child(7n+7){border-right:0}.day-cell>time{display:grid;width:23px;height:23px;place-items:center;margin-bottom:4px;color:var(--crm-text);border-radius:50%;font-size:9px;font-weight:800}.day-cell.muted>time{color:#b7c0c1}.day-cell.today>time,.week-day.today>header strong{color:var(--crm-brand-ink);background:var(--crm-teal)}.calendar-event{display:grid;width:100%;gap:1px;margin:3px 0;padding:4px 6px;overflow:hidden;border:0;border-left:3px solid;border-radius:5px;text-align:left;cursor:pointer}.calendar-event span,.calendar-event small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.calendar-event span{color:var(--crm-text);font-size:7px;font-weight:800}.calendar-event small{color:var(--crm-text-muted);font-size:6px}.calendar-event.selected,.week-event.selected{box-shadow:inset 0 0 0 1px currentColor}.visit{color:#247f75;background:#e8f5f2;border-color:#247f75}.request{color:#9c7218;background:#fff5db;border-color:#c69527}.test{color:#6d54a6;background:#f1edfa;border-color:#8266bd}.booking{color:#356e9c;background:#eaf3fa;border-color:#4d83ac}.more-events{display:block;width:100%;padding:3px 0;color:var(--crm-teal);background:transparent;border:0;text-align:left;cursor:pointer;font-size:7px;font-weight:800}.week-view{display:grid;grid-template-columns:repeat(7,minmax(120px,1fr));min-height:620px;overflow:auto}.week-day{border-right:1px solid var(--crm-line)}.week-day:last-child{border-right:0}.week-day>header{display:flex;height:58px;align-items:center;justify-content:center;gap:7px;color:var(--crm-text-muted);border-bottom:1px solid var(--crm-line);font-size:8px}.week-day>header strong{display:grid;width:28px;height:28px;place-items:center;color:var(--crm-navy);border-radius:50%;font-size:12px}.week-events{display:grid;align-content:start;gap:8px;padding:8px}.week-events>p{margin:18px 0;color:#a9b3b4;font-size:8px;text-align:center}.week-event{display:grid;gap:5px;min-height:104px;padding:10px;border:0;border-top:3px solid;border-radius:8px;text-align:left;cursor:pointer}.week-event small{font-size:7px;font-weight:800}.week-event strong{color:var(--crm-text);font-size:9px;line-height:1.4}.week-event span,.week-event em{color:var(--crm-text-muted);font-size:7px;font-style:normal}.event-detail{padding:18px;background:#fbfcfc}.event-type{display:inline-flex;padding:5px 8px;border-radius:6px;font-size:7px;font-weight:800}.event-detail h3{margin:13px 0 16px;color:var(--crm-navy);font-size:15px;line-height:1.45}.event-detail>p{display:flex;align-items:center;gap:8px;margin:9px 0;color:var(--crm-text-muted);font-size:8px}.event-detail>div:not(.empty-detail){display:grid;gap:7px;margin-top:18px;padding-top:15px;border-top:1px solid var(--crm-line)}.event-detail>div strong{color:var(--crm-navy);font-size:8px}.event-detail>div span,.event-detail>small{color:var(--crm-text-muted);font-size:8px;line-height:1.7}.event-detail>small{display:block;margin-top:22px}.day-agenda-header{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;padding-bottom:12px;border-bottom:1px solid var(--crm-line)}.day-agenda-header>div{display:grid;gap:4px}.day-agenda-header small{color:var(--crm-teal);font-size:7px;font-weight:800;letter-spacing:.08em}.day-agenda-header strong{color:var(--crm-navy);font-size:13px}.day-agenda-header span{color:var(--crm-text-muted);font-size:8px}.day-agenda-header>button{width:26px;height:26px;color:var(--crm-text-muted);background:#fff;border:1px solid var(--crm-line);border-radius:7px;cursor:pointer}.day-agenda-list{display:grid;max-height:330px;gap:7px;margin-top:12px;overflow:auto}.day-agenda-list>button{display:grid;gap:5px;padding:9px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;text-align:left;cursor:pointer}.day-agenda-list>button.active{border-color:var(--crm-teal);box-shadow:0 0 0 1px rgba(254,153,0,.12)}.day-agenda-list small{width:max-content;padding:3px 5px;border-radius:4px;font-size:6px;font-weight:800}.day-agenda-list strong{color:var(--crm-text);font-size:8px;line-height:1.4}.day-agenda-list span{color:var(--crm-text-muted);font-size:7px;line-height:1.4}.day-agenda-detail{display:grid;gap:7px;margin-top:13px;padding-top:12px;border-top:1px solid var(--crm-line)}.day-agenda-detail>strong{color:var(--crm-navy);font-size:9px}.day-agenda-detail p{display:flex;align-items:center;gap:6px;margin:0;color:var(--crm-text-muted);font-size:7px}.day-agenda-detail>span{color:var(--crm-text-muted);font-size:7px;line-height:1.5}.empty-detail{display:grid;height:100%;place-items:center;align-content:center;gap:10px;color:var(--crm-text-muted);font-size:9px}.calendar-state{display:grid;min-height:400px;place-items:center;color:var(--crm-text-muted);font-size:10px}.calendar-state.error{color:var(--crm-danger)}@media(max-width:1100px){.calendar-layout{grid-template-columns:1fr}.calendar-main{border-right:0}.event-detail{min-height:180px;border-top:1px solid var(--crm-line)}}@media(max-width:760px){.calendar-toolbar{align-items:flex-start;flex-direction:column}.calendar-controls{width:100%;justify-content:space-between}.calendar-filters{align-items:stretch;flex-direction:column}.calendar-filters label{justify-content:space-between}.calendar-filters select{width:75%}.calendar-filters>button{margin-left:0;text-align:left}.calendar-navigation{flex-wrap:wrap}.calendar-navigation h2{order:4;width:100%;margin:6px 0 0}.month-view{min-width:720px}.calendar-main{overflow:auto}.day-agenda-list{max-height:240px}.day-cell{min-height:86px}}
</style>
