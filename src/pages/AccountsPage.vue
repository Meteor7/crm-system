<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Building2, Plus } from '@lucide/vue'
import { api as defaultApi, type CrmApi } from '@/api'
import type { AccountSummaryDto, CreateAccountInput, SiteDto, Tone } from '@/types/crm'
import { useAppStore } from '@/stores/app'
import PageHeader from '@/design-system/PageHeader.vue'
import DataState from '@/design-system/DataState.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import FilterBar from '@/features/shared/FilterBar.vue'
import DataNotice from '@/design-system/DataNotice.vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import PersonnelSelect from '@/design-system/PersonnelSelect.vue'
import PaginationControls from '@/features/shared/PaginationControls.vue'
import AccountSegmentSelect from '@/features/accounts/AccountSegmentSelect.vue'
import { personnelDisplayName, preferredPersonnelId } from '@/demo/personnel'
import { mapRequestError, readRequestMeta, type RequestMetaState } from '@/api/request-state'
import { formatDisplayDate } from '@/domain/time'
import { useI18n, useLocaleMessage, localeMessage } from '@/i18n'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const route = useRoute()
const router = useRouter()
const app = useAppStore()
const { locale, t, message: translatedMessage } = useI18n()
const rows = ref<AccountSummaryDto[]>([]), total = ref(0), loading = ref(false), error = useLocaleMessage(), denied = ref(false), requestId = ref(''), meta = ref<RequestMetaState | null>(null)
const deletingId = ref(''), deleteError = useLocaleMessage(), deleteRequestId = ref('')
const page = ref(typeof route.query.page === 'string' && Number(route.query.page) > 0 ? Number(route.query.page) : 1)
const pageSize = ref(typeof route.query.pageSize === 'string' && [10, 25, 50].includes(Number(route.query.pageSize)) ? Number(route.query.pageSize) : 10)
const segment = ref(typeof route.query.segment === 'string' ? route.query.segment : 'All'), city = ref(typeof route.query.city === 'string' ? route.query.city : 'All')
const segments = ref<string[]>(['Frontend', 'Advanced Packaging'])
const cities = ref<string[]>([])
const accountModal = ref(false), busy = ref(false), modalError = useLocaleMessage()
const canWrite = computed(() => app.can('account:write'))
const canDelete = computed(() => app.bootstrap?.user.role === 'Manager')
const accountForm = ref<CreateAccountInput>({ name: '', shortName: '', segment: 'Frontend', tier: 'A', city: '上海', region: '华东', owner: preferredPersonnelId('Sales', app.bootstrap?.user.id), visibility: 'Private' })
type NewSiteDraft = Omit<SiteDto, 'id'> & { clientId: string }
const newSiteDrafts = ref<NewSiteDraft[]>([])
const createdAccountId = ref('')
const persistedSiteCount = ref(0)
let loadSequence = 0
const riskTone = (risk: AccountSummaryDto['risk']): Tone => risk === '高风险' ? 'danger' : risk === '关注' ? 'warning' : 'positive'

async function load() {
  const sequence = ++loadSequence; loading.value = true; error.value = ''; denied.value = false; meta.value = null
  try {
    const result = await props.apiClient.listAccounts({ segment: segment.value, city: city.value, page: page.value, pageSize: pageSize.value })
    if (sequence !== loadSequence) return
    rows.value = result.data.items; total.value = result.meta?.total ?? rows.value.length; meta.value = readRequestMeta(result)
    rows.value.forEach((account) => includeCity(account.city))
  } catch (reason) {
    if (sequence !== loadSequence) return
    const mapped = mapRequestError(reason); error.value = mapped.localizedMessage ?? mapped.message; requestId.value = mapped.requestId; denied.value = mapped.denied
    if (mapped.denied) { rows.value = []; total.value = 0 }
  } finally { if (sequence === loadSequence) loading.value = false }
}
async function loadSegments() {
  try {
    const result = await props.apiClient.listAccountSegments()
    segments.value = result.data
  } catch {
    segments.value = ['Frontend', 'Advanced Packaging']
  }
}
async function loadCities() {
  try {
    const result = await props.apiClient.listAccountCities()
    cities.value = result.data
  } catch {
    rows.value.forEach((account) => includeCity(account.city))
  }
}
function includeSegment(value: string) {
  const normalized = value.trim()
  if (normalized && !segments.value.includes(normalized)) segments.value = [...segments.value, normalized]
}
function includeCity(value: string) {
  const normalized = value.trim()
  if (normalized && !cities.value.includes(normalized)) cities.value = [...cities.value, normalized].sort((left, right) => left.localeCompare(right, 'zh-CN'))
}
function reset() { page.value = 1; segment.value = 'All'; city.value = 'All' }
let restoringRoute = false
function syncUrl() { if (!restoringRoute) void router.replace({ query: { ...route.query, page: String(page.value), pageSize: String(pageSize.value), segment: segment.value === 'All' ? undefined : segment.value, city: city.value === 'All' ? undefined : city.value } }) }
function changeFilters() { if (restoringRoute) return; page.value = 1; syncUrl(); void load() }
function goPage(target: number) { page.value = target; syncUrl(); void load() }
function changePageSize(value: number) { pageSize.value = value; page.value = 1; syncUrl(); void load() }
function openAccountModal() {
  accountForm.value = { name: '', shortName: '', segment: 'Frontend', tier: 'A', city: '上海', region: '华东', owner: preferredPersonnelId('Sales', app.bootstrap?.user.id), visibility: 'Private' }
  newSiteDrafts.value = []
  createdAccountId.value = ''
  persistedSiteCount.value = 0
  modalError.value = ''
  accountModal.value = true
}
function addNewSiteDraft() {
  newSiteDrafts.value.push({
    clientId: `new-${Date.now()}-${newSiteDrafts.value.length}`,
    name: '',
    city: accountForm.value.city,
    type: '',
    process: '',
    status: '规划中',
  })
}
function removeNewSiteDraft(index: number) {
  if (index < persistedSiteCount.value) return
  newSiteDrafts.value.splice(index, 1)
}
async function createAccount() {
  busy.value = true; modalError.value = ''
  try {
    let accountId = createdAccountId.value
    try {
      if (!accountId) {
        const result = await props.apiClient.createAccount(accountForm.value)
        accountId = result.data.id
        includeSegment(result.data.segment)
        includeCity(result.data.city)
        createdAccountId.value = accountId
      }
      for (let index = persistedSiteCount.value; index < newSiteDrafts.value.length; index += 1) {
        const { clientId: _clientId, ...input } = newSiteDrafts.value[index]!
        await props.apiClient.createAccountSite(accountId, input)
        persistedSiteCount.value = index + 1
      }
    } catch (reason) {
      const mapped = mapRequestError(reason)
      const localized = mapped.localizedMessage ?? mapped.message
      if (createdAccountId.value) {
        const english = typeof localized === 'string' ? localized : localized['en-US']
        const chinese = typeof localized === 'string' ? localized : localized['zh-CN']
        modalError.value = localeMessage(translatedMessage('accounts.siteSaveFailed', { message: english })['en-US'], translatedMessage('accounts.siteSaveFailed', { message: chinese })['zh-CN'])
      } else modalError.value = localized
      return
    }
    segment.value = 'All'; city.value = 'All'
    accountModal.value = false
    const targetAccountId = accountId
    newSiteDrafts.value = []
    createdAccountId.value = ''
    persistedSiteCount.value = 0
    await load()
    await router.push({ name: 'account-detail', params: { accountId: targetAccountId } })
  } catch (reason) { const mapped = mapRequestError(reason); modalError.value = mapped.localizedMessage ?? mapped.message }
  finally { busy.value = false }
}
watch([segment, city], changeFilters, { flush: 'sync' })
watch(() => [route.query.page, route.query.pageSize, route.query.segment, route.query.city], ([nextPage, nextSize, nextSegment, nextCity]) => {
  const restoredPage = typeof nextPage === 'string' && Number(nextPage) > 0 ? Number(nextPage) : 1
  const restoredSize = typeof nextSize === 'string' && [10, 25, 50].includes(Number(nextSize)) ? Number(nextSize) : 10
  const restoredSegment = typeof nextSegment === 'string' ? nextSegment : 'All'
  const restoredCity = typeof nextCity === 'string' ? nextCity : 'All'
  if (restoredPage === page.value && restoredSize === pageSize.value && restoredSegment === segment.value && restoredCity === city.value) return
  restoringRoute = true; page.value = restoredPage; pageSize.value = restoredSize; segment.value = restoredSegment; city.value = restoredCity; restoringRoute = false; void load()
})
onMounted(() => { void load(); void loadSegments(); void loadCities() })
function openDetail(account: AccountSummaryDto) { void router.push({ name: 'account-detail', params: { accountId: account.id } }) }
async function deleteAccount(account: AccountSummaryDto) {
  if (deletingId.value || !window.confirm(`${t('accounts.delete')} ${t('accounts.account').toLowerCase()} ${account.name}?`)) return
  deletingId.value = account.id
  deleteError.value = ''
  deleteRequestId.value = ''
  try {
    await props.apiClient.deleteAccount(account.id)
    if (rows.value.length === 1 && page.value > 1) page.value -= 1
    await load()
  } catch (reason) {
    const mapped = mapRequestError(reason)
    deleteError.value = mapped.localizedMessage ?? mapped.message
    deleteRequestId.value = mapped.requestId
  } finally {
    deletingId.value = ''
  }
}
</script>

<template>
  <div class="accounts-page">
    <PageHeader eyebrow="ACCOUNT PORTFOLIO" :title="t('accounts.title')" :description="t('accounts.description')">
      <button v-if="canWrite" class="primary-button" type="button" data-testid="new-account" @click="openAccountModal"><Plus :size="15" />{{ t('accounts.new') }}</button>
    </PageHeader>
    <section v-if="!denied" class="account-stats"><div><span>{{ t('accounts.total') }}</span><strong>{{ total }}</strong><small>{{ t('accounts.scope') }}</small></div><div><span>{{ t('accounts.completeness') }}</span><strong>{{ rows.length ? Math.round(rows.reduce((sum, item) => sum + item.completeness, 0) / rows.length) : 0 }}%</strong><small>{{ t('accounts.completenessHint') }}</small></div></section>
    <FilterBar :result-label="t('accounts.result', { count: total })" @reset="reset"><select v-model="segment" class="filter-control" :aria-label="locale === 'en-US' ? 'Business area' : '业务领域'"><option value="All">{{ t('accounts.allSegments') }}</option><option v-for="item in segments" :key="item" :value="item">{{ item }}</option></select><select v-model="city" class="filter-control" :aria-label="locale === 'en-US' ? 'City' : '城市'"><option value="All">{{ t('accounts.allCities') }}</option><option v-for="item in cities" :key="item" :value="item">{{ item }}</option></select></FilterBar>
    <DataNotice v-if="meta?.stale" :message="meta.localizedMessage ?? meta.message" :request-id="meta.requestId" @refresh="load" />
    <p v-if="deleteError" class="form-error" data-delete-error>{{ deleteError }}<small v-if="deleteRequestId">{{ locale === 'en-US' ? 'Request ID' : '请求编号' }} {{ deleteRequestId }}</small></p>

    <section class="accounts-card">
      <DataState v-if="loading && !rows.length" type="loading" />
      <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
      <DataState v-else-if="error" type="error" :message="error" :request-id="requestId" @retry="load" />
      <DataState v-else-if="!rows.length" type="empty" :title="t('accounts.emptyTitle')" :message="t('accounts.emptyMessage')" />
      <div v-else class="table-scroll">
        <table class="crm-table accounts-table">
          <thead><tr><th>{{ t('accounts.account') }}</th><th>{{ t('accounts.businessRegion') }}</th><th>{{ t('accounts.owner') }}</th><th>{{ t('accounts.contactsSites') }}</th><th>{{ t('accounts.pipelineIntent') }}</th><th>{{ t('accounts.nextStep') }}</th><th>{{ t('accounts.risk') }}</th><th>{{ t('accounts.completeness') }}</th><th>{{ t('accounts.updated') }}</th><th v-if="canDelete">{{ t('accounts.actions') }}</th></tr></thead>
          <tbody>
            <tr v-for="account in rows" :key="account.id" :data-account-id="account.id">
              <td><button class="account-link record-name-link" type="button" :data-open-account-detail="account.id" @click="openDetail(account)"><span><Building2 :size="14" /></span><div><strong>{{ account.shortName }}</strong><small>{{ account.name }}</small></div></button></td>
              <td><strong>{{ account.segment }}</strong><small>{{ account.city }} · {{ account.region }}</small></td>
              <td>{{ personnelDisplayName(account.owner) }}</td><td><strong>{{ t('accounts.contactsCount', { count: account.stakeholderCount }) }}</strong><small>{{ t('accounts.sitesCount', { count: account.siteCount }) }}</small></td><td><strong>¥{{ account.pipelineAmount.toLocaleString(locale) }}</strong><small>{{ locale === 'en-US' ? 'Intent score' : '意愿评分' }} {{ account.intentScore }}</small></td><td><strong>{{ account.nextAction || t('accounts.none') }}</strong><small>{{ account.nextActionDue ? formatDisplayDate(account.nextActionDue) : t('accounts.unscheduled') }}</small></td>
              <td><StatusBadge :label="account.risk === '高风险' ? t('accounts.riskHigh') : account.risk === '关注' ? t('accounts.riskWatch') : t('accounts.riskStable')" :tone="riskTone(account.risk)" /></td><td>{{ account.completeness }}%</td><td>{{ formatDisplayDate(account.updatedAt) }}</td>
              <td v-if="canDelete"><button type="button" class="site-remove" :data-delete-account="account.id" :disabled="Boolean(deletingId)" @click="deleteAccount(account)">{{ t('accounts.delete') }}</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <PaginationControls v-if="!denied && !error && total > pageSize" :page="page" :page-size="pageSize" :total="total" @change="goPage" @page-size-change="changePageSize" />
    </section>
    <ModalShell v-if="accountModal" :title="locale === 'en-US' ? 'New account' : '新增客户'" eyebrow="ACCOUNT MASTER" :busy="busy" @close="accountModal = false" @submit="createAccount">
      <p v-if="modalError" class="form-error">{{ modalError }}</p>
      <div class="account-form-grid">
        <label><span>{{ locale === 'en-US' ? 'Account name' : '客户全称' }}<RequiredMark /></span><input v-model="accountForm.name" :aria-label="locale === 'en-US' ? 'Account name' : '客户全称'" required /></label>
        <label><span>{{ locale === 'en-US' ? 'Short name' : '客户简称' }}<RequiredMark /></span><input v-model="accountForm.shortName" :aria-label="locale === 'en-US' ? 'Short name' : '客户简称'" required /></label>
        <label><span>{{ locale === 'en-US' ? 'Business area' : '业务领域' }}<RequiredMark /></span><AccountSegmentSelect v-model="accountForm.segment" :segments="segments" :label="locale === 'en-US' ? 'Account business area' : '客户业务领域'" required /></label>
        <label><span>{{ locale === 'en-US' ? 'Account tier' : '客户等级' }}</span><select v-model="accountForm.tier" :aria-label="locale === 'en-US' ? 'Account tier' : '客户等级'"><option>S</option><option>A</option><option>B</option></select></label>
        <label><span>{{ locale === 'en-US' ? 'City' : '城市' }}<RequiredMark /></span><input v-model="accountForm.city" :aria-label="locale === 'en-US' ? 'City' : '客户城市'" required /></label>
        <label><span>{{ locale === 'en-US' ? 'Region' : '区域' }}<RequiredMark /></span><input v-model="accountForm.region" :aria-label="locale === 'en-US' ? 'Region' : '客户区域'" required /></label>
        <label class="wide"><span>{{ locale === 'en-US' ? 'Owner' : '负责人' }}<RequiredMark /></span><PersonnelSelect v-model="accountForm.owner" :roles="['Sales']" :ariaLabel="locale === 'en-US' ? 'Account owner' : '客户负责人'" required /></label>
        <label class="wide"><span>{{ locale === 'en-US' ? 'Visibility' : '访问权限' }}</span><select v-model="accountForm.visibility" :aria-label="locale === 'en-US' ? 'Account visibility' : '客户访问权限'"><option value="Private">{{ locale === 'en-US' ? 'Private: owner and Manager only' : '私有：仅负责人和 Manager 可见' }}</option><option value="Public">{{ locale === 'en-US' ? 'Public: all Sales can view; other Sales read-only' : '公开：所有 Sales 可见，其他 Sales 只读' }}</option></select></label>
      </div>
      <section class="site-editor" data-account-site-editor>
        <header>
          <div><strong>{{ locale === 'en-US' ? 'Site information' : '厂区信息' }}</strong><small>{{ locale === 'en-US' ? 'Optional; a site profile is created after account creation' : '可选；客户创建后会同步建立厂区档案' }}</small></div>
          <button type="button" class="secondary-button" data-add-site @click="addNewSiteDraft">{{ locale === 'en-US' ? 'Add site' : '增加厂区' }}</button>
        </header>
        <p v-if="!newSiteDrafts.length" class="site-empty">{{ locale === 'en-US' ? 'You can add sites later from account details.' : '可稍后在客户详情中增加厂区。' }}</p>
        <article v-for="(site, index) in newSiteDrafts" :key="site.clientId" class="site-draft">
          <b>{{ locale === 'en-US' ? 'Site' : '厂区' }} {{ index + 1 }}<small v-if="index < persistedSiteCount">{{ locale === 'en-US' ? 'Saved' : '已保存' }}</small></b>
          <label><span>{{ locale === 'en-US' ? 'Site name' : '厂区名称' }}<RequiredMark /></span><input v-model="site.name" :aria-label="locale === 'en-US' ? `New site ${index + 1} name` : `新厂区 ${index + 1} 名称`" :disabled="index < persistedSiteCount" required /></label>
          <label><span>{{ locale === 'en-US' ? 'City' : '城市' }}<RequiredMark /></span><input v-model="site.city" :aria-label="locale === 'en-US' ? `New site ${index + 1} city` : `新厂区 ${index + 1} 城市`" :disabled="index < persistedSiteCount" required /></label>
          <label><span>{{ locale === 'en-US' ? 'Site type' : '厂区类型' }}<RequiredMark /></span><input v-model="site.type" :aria-label="locale === 'en-US' ? `New site ${index + 1} type` : `新厂区 ${index + 1} 类型`" :disabled="index < persistedSiteCount" :placeholder="locale === 'en-US' ? 'e.g. Wafer fab' : '例如：晶圆制造'" required /></label>
          <label><span>{{ locale === 'en-US' ? 'Process / use' : '制程/用途' }}<RequiredMark /></span><input v-model="site.process" :aria-label="locale === 'en-US' ? `New site ${index + 1} process or use` : `新厂区 ${index + 1} 制程或用途`" :disabled="index < persistedSiteCount" :placeholder="locale === 'en-US' ? 'e.g. 16/28nm' : '例如：16/28nm'" required /></label>
          <label><span>{{ locale === 'en-US' ? 'Status' : '状态' }}<RequiredMark /></span><select v-model="site.status" :aria-label="locale === 'en-US' ? `New site ${index + 1} status` : `新厂区 ${index + 1} 状态`" :disabled="index < persistedSiteCount" required><option value="量产">{{ locale === 'en-US' ? 'Production' : '量产' }}</option><option value="建设中">{{ locale === 'en-US' ? 'Under construction' : '建设中' }}</option><option value="规划中">{{ locale === 'en-US' ? 'Planned' : '规划中' }}</option></select></label>
          <button type="button" class="site-remove" :disabled="index < persistedSiteCount" :data-remove-site="site.clientId" @click="removeNewSiteDraft(index)">{{ locale === 'en-US' ? 'Remove site' : '删除此厂区' }}</button>
        </article>
      </section>
    </ModalShell>
  </div>
</template>

<style scoped>
.account-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}.account-stats div{display:grid;gap:4px;padding:14px 16px;background:#fff;border:1px solid var(--crm-line);border-radius:11px}.account-stats span{color:var(--crm-text-muted);font-size:8px;font-weight:700}.account-stats strong{color:var(--crm-navy);font-size:20px;font-variant-numeric:tabular-nums}.account-stats small{color:#91a0a3;font-size:8px}.search-control{display:flex;min-width:220px;height:34px;align-items:center;gap:7px;padding:0 10px;color:var(--crm-text-muted);background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:8px}.search-control input{min-width:0;flex:1;background:transparent;border:0;outline:0;font-size:10px}.account-workspace{display:grid;grid-template-columns:270px minmax(0,1fr);gap:14px;align-items:start}.account-list{display:grid;max-height:760px;overflow:auto;padding:8px;background:#FAF8F5;border:1px solid var(--crm-line);border-radius:13px}.account-list>button{display:grid;grid-template-columns:36px minmax(0,1fr);gap:10px;padding:12px;text-align:left;background:transparent;border:1px solid transparent;border-radius:10px;cursor:pointer}.account-list>button.active{background:#fff;border-color:#F3C173;box-shadow:0 3px 12px rgba(31,35,41,.06)}.account-mark{display:grid;width:36px;height:36px;place-items:center;color:var(--crm-teal);background:var(--crm-teal-soft);border-radius:10px;font-size:9px;font-weight:800}.account-copy{display:grid;min-width:0;gap:4px}.account-copy header{display:flex;align-items:center;justify-content:space-between;gap:6px}.account-copy strong{font-size:11px}.account-copy p{overflow:hidden;margin:0;color:var(--crm-text);font-size:9px;text-overflow:ellipsis;white-space:nowrap}.account-copy small{color:var(--crm-text-muted);font-size:8px}.account-copy footer{display:flex;align-items:center;gap:7px;margin-top:4px}.account-copy footer b{margin-right:auto;color:var(--crm-navy);font-size:10px}.account-copy footer span{display:flex;align-items:center;gap:3px;color:var(--crm-text-muted);font-size:8px}@media(max-width:1100px){.account-workspace{grid-template-columns:220px minmax(0,1fr)}.account-stats{grid-template-columns:repeat(2,1fr)}}@media(max-width:760px){.account-workspace{grid-template-columns:1fr}.account-list{display:flex;max-height:none;overflow:auto}.account-list>button{min-width:230px}.account-stats{grid-template-columns:1fr 1fr}}@media(max-width:480px){.account-stats{grid-template-columns:1fr}}
.primary-button{display:flex;align-items:center;gap:6px}.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:9px}.account-form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.account-form-grid label{display:grid;gap:6px}.account-form-grid label.wide{grid-column:1/-1}.account-form-grid span{color:var(--crm-text-muted);font-size:9px;font-weight:700}.account-form-grid input,.account-form-grid select{height:38px;padding:0 10px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.account-form-grid input:focus,.account-form-grid select:focus{border-color:var(--crm-teal);outline:0}@media(max-width:560px){.account-form-grid{grid-template-columns:1fr}.account-form-grid label.wide{grid-column:auto}}
.accounts-card{overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:14px}.table-scroll{overflow:auto}.accounts-table{min-width:1080px}.accounts-table td strong,.accounts-table td small{display:block}.accounts-table td small{margin-top:4px;color:var(--crm-text-muted);font-size:10px}.account-link{display:flex;min-width:250px;align-items:center;gap:8px;padding:0;color:var(--crm-navy);background:transparent;border:0;font:inherit;text-align:left;cursor:pointer}.account-link>span{display:grid;width:30px;height:30px;flex:0 0 auto;place-items:center;color:var(--crm-brand-ink);background:var(--crm-teal-soft);border-radius:9px}.account-link>div{display:grid;min-width:0;flex:1}.account-link strong{color:var(--crm-link);font-size:12px}.account-link:hover strong{color:var(--crm-link-hover);text-decoration:none}
.account-stats{grid-template-columns:repeat(2,1fr)}
.site-editor{display:grid;gap:12px;margin-top:18px;padding-top:16px;border-top:1px solid var(--crm-line)}.site-editor>header{display:flex;align-items:center;justify-content:space-between;gap:12px}.site-editor>header div{display:grid;gap:3px}.site-editor>header strong{color:var(--crm-navy);font-size:11px}.site-editor>header small,.site-empty{color:var(--crm-text-muted);font-size:8px}.site-empty{margin:0;padding:14px;background:var(--crm-surface);border-radius:8px;text-align:center}.site-draft{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;padding:12px;background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:10px}.site-draft>b{display:flex;grid-column:1/-1;align-items:center;gap:7px;color:var(--crm-teal);font-size:9px}.site-draft>b small{color:var(--crm-text-muted);font-size:8px}.site-draft label{display:grid;gap:5px}.site-draft label:last-of-type{grid-column:1/-1}.site-draft span{color:var(--crm-text-muted);font-size:8px;font-weight:700}.site-draft input,.site-draft select{height:36px;padding:0 9px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.site-draft input:disabled,.site-draft select:disabled{color:var(--crm-text-muted);background:#f4f4f2}.site-remove{grid-column:1/-1;justify-self:start;margin-top:2px;padding:6px 12px;font-size:9px;font-weight:700;color:var(--crm-danger);background:var(--crm-danger-soft);border:1px solid transparent;border-radius:8px;cursor:pointer}.site-remove:disabled{opacity:.45;cursor:not-allowed}@media(max-width:560px){.site-editor>header{align-items:stretch;flex-direction:column}.site-draft{grid-template-columns:1fr}.site-draft>b,.site-draft label:last-of-type{grid-column:auto}}
</style>
