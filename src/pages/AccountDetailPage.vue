<script setup lang="ts">
import { systemValueLabel } from '@/features/shared/system-labels'
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft, Cpu, Edit3, ExternalLink, MapPin, Wrench } from '@lucide/vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api as defaultApi, CrmApiError, type CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import type { Account360Dto, CreateAccountInput, SiteDto } from '@/types/crm'
import type { InstalledToolDto } from '@/types/workspaces'
import { personnelDisplayName } from '@/demo/personnel'
import AccountProfile from '@/features/accounts/AccountProfile.vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import PersonnelSelect from '@/design-system/PersonnelSelect.vue'
import AccountSegmentSelect from '@/features/accounts/AccountSegmentSelect.vue'
import { REGION_PRESETS, regionLabel } from '@/domain/regions'
import SectionCard from '@/design-system/SectionCard.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import { useI18n, useLocaleMessage } from '@/i18n'
import { salesEnumLabel } from '@/features/shared/sales-i18n'
import { listReturnTarget } from '@/features/shared/list-return'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const route = useRoute()
const router = useRouter()
// Back to the list as it was (its search, filters and page) when the Account was opened from it.
const backTo = computed(() => listReturnTarget(router, route.query, 'accounts'))
const app = useAppStore()
const { locale, t } = useI18n()
const tools = ref<InstalledToolDto[]>([])
const loading = ref(false)
const warning = useLocaleMessage()
const warningRequestId = ref('')
const profileVersion = ref(0)
const accountDetail = ref<Account360Dto | null>(null)
const editOpen = ref(false)
const editBusy = ref(false)
const editError = useLocaleMessage()
// The Accounts named like the new name, which the server refused until the user says this is another company.
const duplicateAccounts = ref('')
const accountForm = ref<CreateAccountInput>({ name: '', shortName: '', segment: 'Frontend', tier: 'A', city: '', region: '', owner: '', visibility: 'Private', customerKind: '' })
// The name the last submission asked about: the refusal, and the offer to go on, are for that name alone,
// whatever the field says by the time the answer arrives.
const askedName = ref('')
const segments = ref<string[]>(['Frontend', 'Advanced Packaging'])
const regions = ref<string[]>([...REGION_PRESETS])
const siteDrafts = ref<Array<SiteDto & { isNew?: boolean }>>([])
const removedSiteIds = ref<string[]>([])
const accountId = computed(() => String(route.params.accountId || ''))
const relatedTools = computed(() => tools.value.filter((item) => item.accountId === accountId.value))
const canWrite = computed(() => {
  if (!app.can('account:write') || !accountDetail.value) return false
  return app.bootstrap?.user.role === 'Manager' || app.bootstrap?.user.id === accountDetail.value.account.owner
})
let equipmentSequence = 0
const regionOptionLabel = (value: string) => regionLabel(value, locale.value)

function captureAccount(detail: Account360Dto) { accountDetail.value = detail }
function openEdit() {
  if (!accountDetail.value) return
  const account = accountDetail.value.account
  accountForm.value = { name: account.name, shortName: account.shortName, segment: account.segment, tier: account.tier, city: account.city, region: account.region, owner: account.owner, visibility: account.visibility ?? 'Private', customerKind: account.customerKind ?? '' }
  siteDrafts.value = accountDetail.value.sites.map((site) => ({ ...site }))
  removedSiteIds.value = []
  editError.value = ''
  duplicateAccounts.value = ''
  editOpen.value = true
}
function submitEdit() { accountForm.value.confirmDuplicate = false; return saveAccount() }
function saveAnyway() { accountForm.value.confirmDuplicate = true; return saveAccount() }
async function saveAccount() {
  askedName.value = accountForm.value.name
  editBusy.value = true
  editError.value = ''
  duplicateAccounts.value = ''
  try {
    const accountResult = await props.apiClient.updateAccount(accountId.value, accountForm.value, accountDetail.value?.account.modified)
    if (!segments.value.includes(accountResult.data.segment)) segments.value = [...segments.value, accountResult.data.segment]
    if (accountResult.data.region && !regions.value.includes(accountResult.data.region)) regions.value = [...regions.value, accountResult.data.region]
    if (accountDetail.value) {
      accountDetail.value = { ...accountDetail.value, account: accountResult.data }
    }
    for (let index = 0; index < siteDrafts.value.length; index += 1) {
      const site = siteDrafts.value[index]!
      const input = { name: site.name, city: site.city, type: site.type, process: site.process, status: site.status }
      const result = site.isNew
        ? await props.apiClient.createAccountSite(accountId.value, input)
        : await props.apiClient.updateAccountSite(accountId.value, site.id, input)
      siteDrafts.value[index] = result.data
    }
    while (removedSiteIds.value.length) {
      const siteId = removedSiteIds.value[0]!
      await props.apiClient.deleteAccountSite(accountId.value, siteId)
      removedSiteIds.value.shift()
    }
    editOpen.value = false
    profileVersion.value += 1
    await loadEquipment()
  } catch (reason) {
    const mapped = mapRequestError(reason)
    editError.value = mapped.localizedMessage ?? mapped.message
    // Accounts named like the new name: the server names the ones the user may see and waits for their word.
    if (reason instanceof CrmApiError && reason.code === 'CONFLICT' && reason.fieldErrors.name) duplicateAccounts.value = reason.fieldErrors.name
  } finally {
    editBusy.value = false
  }
}

function addSiteDraft() {
  siteDrafts.value.push({
    id: `new-${Date.now()}-${siteDrafts.value.length}`,
    name: '',
    city: accountForm.value.city,
    type: '',
    process: '',
    status: '规划中',
    isNew: true,
  })
}

function removeSiteDraft(index: number) {
  const [site] = siteDrafts.value.splice(index, 1)
  if (site && !site.isNew) removedSiteIds.value.push(site.id)
}

async function loadEquipment() {
  const sequence = ++equipmentSequence
  const requestedAccountId = accountId.value
  loading.value = true
  warning.value = ''; warningRequestId.value = ''
  try {
    const items: InstalledToolDto[] = []
    let page = 1
    while (true) {
      const result = await props.apiClient.listInstalledTools({ accountId: requestedAccountId, page, pageSize: 200 })
      if (sequence !== equipmentSequence || requestedAccountId !== accountId.value) return
      items.push(...result.data.items)
      const total = result.meta?.total ?? items.length
      if (items.length >= total || result.data.items.length === 0) break
      page += 1
    }
    tools.value = items
  } catch (reason) {
    if (sequence !== equipmentSequence) return
    tools.value = []
    const mapped = mapRequestError(reason)
    warning.value = mapped.localizedMessage ?? mapped.message
    warningRequestId.value = mapped.requestId
  } finally {
    if (sequence === equipmentSequence) loading.value = false
  }
}

async function loadSegments() {
  try {
    segments.value = (await props.apiClient.listAccountSegments()).data
  } catch {
    segments.value = ['Frontend', 'Advanced Packaging']
  }
}

async function loadRegions() {
  try {
    regions.value = (await props.apiClient.listAccountRegions()).data
  } catch {
    regions.value = [...REGION_PRESETS]
  }
}

watch(accountId, loadEquipment)
onMounted(() => { void loadEquipment(); void loadSegments(); void loadRegions() })
</script>

<template>
  <div class="account-detail-page">
    <div class="detail-actions"><RouterLink class="detail-back-button" :to="backTo"><ArrowLeft :size="14" />{{ t('detail.backAccounts') }}</RouterLink><button v-if="canWrite" class="primary-button" type="button" data-testid="edit-account" :disabled="!accountDetail" @click="openEdit"><Edit3 :size="14" />{{ t('detail.editProfile') }}</button></div>
    <div class="account-detail-layout">
      <AccountProfile :key="profileVersion" :account-id="accountId" :api-client="props.apiClient" @loaded="captureAccount" @manage-sites="openEdit" />
      <aside class="equipment-column">
        <SectionCard :title="t('detail.equipmentRelation')" eyebrow="INSTALLED BASE">
           <div class="equipment-heading"><span><Cpu :size="18" /></span><div><strong>{{ relatedTools.length }} {{ locale === 'en-US' ? 'tools' : '台设备' }}</strong><small>{{ locale === 'en-US' ? 'Installed Tools for this account' : '当前客户 Installed Tools' }}</small></div></div>
          <p v-if="warning" class="equipment-warning">{{ warning }}<small v-if="warningRequestId">{{ locale === 'en-US' ? 'Request ID' : '请求编号' }}: {{ warningRequestId }}</small></p>
          <p v-else-if="loading" class="equipment-empty">{{ t('detail.loadingEquipment') }}</p>
          <div v-else-if="relatedTools.length" class="equipment-list">
            <article v-for="tool in relatedTools" :key="tool.id" :data-account-tool="tool.id">
               <header><strong>{{ tool.model }}</strong><StatusBadge :label="salesEnumLabel(tool.status, locale)" :tone="tool.status === 'Active' ? 'positive' : 'warning'" /></header>
              <b>{{ tool.serial }}</b>
              <p><MapPin :size="12" />{{ tool.site }} · {{ systemValueLabel(tool.location, locale) }}</p>
              <p><Wrench :size="12" />{{ tool.engineerOwner ? personnelDisplayName(tool.engineerOwner) : t('detail.engineerUnassigned') }}</p>
              <RouterLink v-if="tool.sourceBookingId" :to="{ name: 'booking-detail', params: { bookingId: tool.sourceBookingId } }">{{ t('detail.source') }} {{ tool.sourceBookingId }}<ExternalLink :size="12" /></RouterLink>
            </article>
          </div>
          <p v-else class="equipment-empty">{{ t('detail.noInstalledTools') }}</p>
          <RouterLink class="equipment-more" :to="{ name: 'installed-tools', query: { accountId } }">{{ t('detail.viewEquipment') }}<ExternalLink :size="13" /></RouterLink>
        </SectionCard>
      </aside>
    </div>
    <ModalShell v-if="editOpen" :title="t('detail.editAccount')" eyebrow="ACCOUNT MASTER" :busy="editBusy" @close="editOpen = false" @submit="submitEdit">
      <p v-if="editError" class="form-error">{{ editError }}</p>
      <p v-if="duplicateAccounts && accountForm.name === askedName" class="form-error duplicate-accounts" data-duplicate-accounts>{{ t('accounts.duplicateHint', { names: duplicateAccounts }) }} <button type="button" class="secondary-button" data-save-anyway :disabled="editBusy" @click="saveAnyway">{{ t('accounts.saveAnyway') }}</button></p>
      <div class="account-form-grid">
        <label><span>{{ t('detail.accountName') }}<RequiredMark /></span><input v-model="accountForm.name" :aria-label="t('detail.accountName')" required /></label>
        <label><span>{{ t('detail.accountShortName') }}<RequiredMark /></span><input v-model="accountForm.shortName" :aria-label="t('detail.accountShortName')" required /></label>
         <label><span>{{ t('detail.businessArea') }}<RequiredMark /></span><AccountSegmentSelect v-model="accountForm.segment" :segments="segments" :label="t('detail.businessArea')" required /></label>
        <label><span>{{ t('detail.accountTier') }}</span><select v-model="accountForm.tier" :aria-label="t('detail.accountTier')"><option>S</option><option>A</option><option>B</option></select></label>
        <label><span>{{ locale === 'en-US' ? 'Customer relationship' : '客户关系' }}</span><select v-model="accountForm.customerKind" :aria-label="locale === 'en-US' ? 'Customer relationship' : '客户关系'"><option value="">{{ locale === 'en-US' ? 'Unclassified' : '未分类' }}</option><option value="Prospect">{{ locale === 'en-US' ? 'Prospect' : '潜在客户' }}</option><option value="Existing">{{ locale === 'en-US' ? 'Existing customer' : '老客户' }}</option></select><small>{{ locale === 'en-US' ? 'Completed visits keep the relationship captured at completion.' : '已完成拜访保留完成时的客户关系，不随此处修改。' }}</small></label>
        <label><span>{{ t('detail.city') }}<RequiredMark /></span><input v-model="accountForm.city" :aria-label="t('detail.city')" required /></label>
        <label><span>{{ t('detail.region') }}<RequiredMark /></span><AccountSegmentSelect v-model="accountForm.region" :segments="regions" :label="t('detail.region')" :option-label="regionOptionLabel" :custom-option-label="t('region.customOption')" :custom-placeholder="t('region.customPlaceholder')" :empty-placeholder="t('region.choose')" :custom-on-empty="false" required /></label>
        <label class="wide"><span>{{ t('detail.owner') }}<RequiredMark /></span><PersonnelSelect owner v-model="accountForm.owner" :roles="['Sales']" :ariaLabel="t('detail.owner')" required /></label>
        <label class="wide"><span>{{ t('detail.access') }}<RequiredMark /></span><select v-model="accountForm.visibility" :aria-label="t('detail.access')" required><option value="Private">{{ t('detail.privateAccess') }}</option><option value="Public">{{ t('detail.publicAccess') }}</option></select></label>
      </div>
      <section class="site-editor" data-account-site-editor>
        <header>
          <div><strong>{{ t('detail.sites') }}</strong><small>{{ t('detail.sitesHint') }}</small></div>
          <button type="button" class="secondary-button" data-add-site @click="addSiteDraft">{{ t('detail.addSite') }}</button>
        </header>
        <p v-if="!siteDrafts.length" class="site-empty">{{ t('detail.noSites') }}</p>
        <article v-for="(site, index) in siteDrafts" :key="site.id" class="site-draft">
          <b>{{ t('detail.site') }} {{ index + 1 }}</b>
          <label><span>{{ t('detail.siteName') }}<RequiredMark /></span><input v-model="site.name" required /></label>
          <label><span>{{ t('detail.city') }}<RequiredMark /></span><input v-model="site.city" required /></label>
          <label><span>{{ t('detail.siteType') }}<RequiredMark /></span><input v-model="site.type" :placeholder="locale === 'en-US' ? 'e.g. Wafer fab' : '例如：晶圆制造'" required /></label>
          <label><span>{{ t('detail.process') }}<RequiredMark /></span><input v-model="site.process" :placeholder="locale === 'en-US' ? 'e.g. 16/28nm' : '例如：16/28nm'" required /></label>
          <label><span>{{ t('detail.status') }}<RequiredMark /></span><select v-model="site.status" required><option value="量产">{{ t('site.status.production') }}</option><option value="建设中">{{ t('site.status.construction') }}</option><option value="规划中">{{ t('site.status.planning') }}</option></select></label>
          <button type="button" class="site-remove" :data-remove-site="site.id" @click="removeSiteDraft(index)">{{ t('detail.removeSite') }}</button>
        </article>
      </section>
    </ModalShell>
  </div>
</template>

<style scoped>
.account-detail-page{display:grid;gap:14px}.detail-back-button{justify-self:start}.account-detail-layout{display:grid;grid-template-columns:minmax(0,1fr) 278px;gap:14px;align-items:start}.equipment-column{position:sticky;top:16px}.equipment-heading{display:flex;align-items:center;gap:9px;margin-bottom:12px;padding:11px;background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:10px}.equipment-heading>span{display:grid;width:34px;height:34px;place-items:center;color:var(--crm-brand-ink);background:var(--crm-teal-soft);border-radius:9px}.equipment-heading>div{display:grid;gap:3px}.equipment-heading strong{color:var(--crm-navy);font-size:12px}.equipment-heading small{color:var(--crm-text-muted);font-size:9px}.equipment-list{display:grid;gap:9px}.equipment-list article{display:grid;gap:6px;padding:11px;background:#fff;border:1px solid var(--crm-line);border-radius:10px}.equipment-list header{display:flex;align-items:center;justify-content:space-between;gap:7px}.equipment-list header strong{font-size:11px}.equipment-list b{color:var(--crm-teal);font-size:9px}.equipment-list p{display:flex;align-items:center;gap:5px;margin:0;color:var(--crm-text-muted);font-size:9px}.equipment-list a,.equipment-more{display:flex;align-items:center;justify-content:space-between;color:var(--crm-link);font-size:9px;font-weight:750}.equipment-more{margin-top:12px;padding-top:10px;border-top:1px solid var(--crm-line)}.equipment-empty,.equipment-warning{margin:0;padding:16px 8px;color:var(--crm-text-muted);font-size:10px;line-height:1.6;text-align:center}.equipment-warning{color:#7b5c15;background:var(--crm-warning-soft);border-radius:9px}@media(max-width:1100px){.account-detail-layout{grid-template-columns:1fr}.equipment-column{position:static}.equipment-list{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:620px){.equipment-list{grid-template-columns:1fr}}
.detail-actions{display:flex;align-items:center;justify-content:space-between;gap:12px}.detail-actions .primary-button{display:flex;align-items:center;gap:6px}.detail-actions .primary-button:disabled{opacity:.5;cursor:not-allowed}.account-form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.account-form-grid label{display:grid;gap:6px}.account-form-grid label.wide{grid-column:1/-1}.account-form-grid span{color:var(--crm-text-muted);font-size:9px;font-weight:700}.account-form-grid input,.account-form-grid select{height:38px;padding:0 10px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.account-form-grid input:focus,.account-form-grid select:focus{border-color:var(--crm-teal);outline:0}.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:9px}@media(max-width:560px){.account-form-grid{grid-template-columns:1fr}.account-form-grid label.wide{grid-column:auto}.detail-actions{align-items:stretch;flex-direction:column}.detail-actions>*{justify-content:center}}
.site-editor{display:grid;gap:12px;margin-top:18px;padding-top:16px;border-top:1px solid var(--crm-line)}.site-editor>header{display:flex;align-items:center;justify-content:space-between;gap:12px}.site-editor>header div{display:grid;gap:3px}.site-editor>header strong{color:var(--crm-navy);font-size:11px}.site-editor>header small,.site-empty{color:var(--crm-text-muted);font-size:8px}.site-empty{margin:0;padding:14px;background:var(--crm-surface);border-radius:8px;text-align:center}.site-draft{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;padding:12px;background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:10px}.site-draft>b{grid-column:1/-1;color:var(--crm-teal);font-size:9px}.site-draft label{display:grid;gap:5px}.site-draft label:last-child{grid-column:1/-1}.site-draft span{color:var(--crm-text-muted);font-size:8px;font-weight:700}.site-draft input,.site-draft select{height:36px;padding:0 9px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.site-remove{grid-column:1/-1;justify-self:start;margin-top:2px;padding:6px 12px;font-size:9px;font-weight:700;color:var(--crm-danger);background:var(--crm-danger-soft);border:1px solid transparent;border-radius:8px;cursor:pointer}@media(max-width:560px){.site-editor>header{align-items:stretch;flex-direction:column}.site-draft{grid-template-columns:1fr}.site-draft>b,.site-draft label:last-child{grid-column:auto}}
</style>
