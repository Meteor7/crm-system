<script setup lang="ts">
import { systemValueLabel } from '@/features/shared/system-labels'
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft, Cpu, Edit3, ExternalLink, MapPin, Wrench } from '@lucide/vue'
import { RouterLink, useRoute } from 'vue-router'
import { api as defaultApi, type CrmApi } from '@/api'
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
import SectionCard from '@/design-system/SectionCard.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import { useI18n, useLocaleMessage } from '@/i18n'
import { salesEnumLabel } from '@/features/shared/sales-i18n'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const route = useRoute()
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
const accountForm = ref<CreateAccountInput>({ name: '', shortName: '', segment: 'Frontend', tier: 'A', city: '', region: '', owner: '', visibility: 'Private' })
const segments = ref<string[]>(['Frontend', 'Advanced Packaging'])
const siteDrafts = ref<Array<SiteDto & { isNew?: boolean }>>([])
const removedSiteIds = ref<string[]>([])
const accountId = computed(() => String(route.params.accountId || ''))
const relatedTools = computed(() => tools.value.filter((item) => item.accountId === accountId.value))
const canWrite = computed(() => {
  if (!app.can('account:write') || !accountDetail.value) return false
  return app.bootstrap?.user.role === 'Manager' || app.bootstrap?.user.id === accountDetail.value.account.owner
})
let equipmentSequence = 0

function captureAccount(detail: Account360Dto) { accountDetail.value = detail }
function openEdit() {
  if (!accountDetail.value) return
  const account = accountDetail.value.account
  accountForm.value = { name: account.name, shortName: account.shortName, segment: account.segment, tier: account.tier, city: account.city, region: account.region, owner: account.owner, visibility: account.visibility ?? 'Private' }
  siteDrafts.value = accountDetail.value.sites.map((site) => ({ ...site }))
  removedSiteIds.value = []
  editError.value = ''
  editOpen.value = true
}
async function saveAccount() {
  editBusy.value = true
  editError.value = ''
  try {
    const accountResult = await props.apiClient.updateAccount(accountId.value, accountForm.value, accountDetail.value?.account.modified)
    if (!segments.value.includes(accountResult.data.segment)) segments.value = [...segments.value, accountResult.data.segment]
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

watch(accountId, loadEquipment)
onMounted(() => { void loadEquipment(); void loadSegments() })
</script>

<template>
  <div class="account-detail-page">
    <div class="detail-actions"><RouterLink class="detail-back-button" :to="{ name: 'accounts' }"><ArrowLeft :size="14" />{{ t('detail.backAccounts') }}</RouterLink><button v-if="canWrite" class="primary-button" type="button" data-testid="edit-account" :disabled="!accountDetail" @click="openEdit"><Edit3 :size="14" />{{ t('detail.editProfile') }}</button></div>
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
    <ModalShell v-if="editOpen" :title="t('detail.editAccount')" eyebrow="ACCOUNT MASTER" :busy="editBusy" @close="editOpen = false" @submit="saveAccount">
      <p v-if="editError" class="form-error">{{ editError }}</p>
      <div class="account-form-grid">
        <label><span>{{ t('detail.accountName') }}<RequiredMark /></span><input v-model="accountForm.name" :aria-label="t('detail.accountName')" required /></label>
        <label><span>{{ t('detail.accountShortName') }}<RequiredMark /></span><input v-model="accountForm.shortName" :aria-label="t('detail.accountShortName')" required /></label>
         <label><span>{{ t('detail.businessArea') }}<RequiredMark /></span><AccountSegmentSelect v-model="accountForm.segment" :segments="segments" :label="t('detail.businessArea')" required /></label>
        <label><span>{{ t('detail.accountTier') }}</span><select v-model="accountForm.tier" :aria-label="t('detail.accountTier')"><option>S</option><option>A</option><option>B</option></select></label>
        <label><span>{{ t('detail.city') }}<RequiredMark /></span><input v-model="accountForm.city" :aria-label="t('detail.city')" required /></label>
        <label><span>{{ t('detail.region') }}<RequiredMark /></span><input v-model="accountForm.region" :aria-label="t('detail.region')" required /></label>
        <label class="wide"><span>{{ t('detail.owner') }}<RequiredMark /></span><PersonnelSelect v-model="accountForm.owner" :roles="['Sales']" :ariaLabel="t('detail.owner')" required /></label>
        <label class="wide"><span>{{ t('detail.access') }}</span><select v-model="accountForm.visibility" :aria-label="t('detail.access')"><option value="Private">{{ t('detail.privateAccess') }}</option><option value="Public">{{ t('detail.publicAccess') }}</option></select></label>
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
.account-detail-page{display:grid;gap:14px}.detail-back-button{justify-self:start}.account-detail-layout{display:grid;grid-template-columns:minmax(0,1fr) 278px;gap:14px;align-items:start}.equipment-column{position:sticky;top:16px}.equipment-heading{display:flex;align-items:center;gap:9px;margin-bottom:12px;padding:11px;background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:10px}.equipment-heading>span{display:grid;width:34px;height:34px;place-items:center;color:var(--crm-brand-ink);background:var(--crm-teal-soft);border-radius:9px}.equipment-heading>div{display:grid;gap:3px}.equipment-heading strong{color:var(--crm-navy);font-size:12px}.equipment-heading small{color:var(--crm-text-muted);font-size:9px}.equipment-list{display:grid;gap:9px}.equipment-list article{display:grid;gap:6px;padding:11px;background:#fff;border:1px solid var(--crm-line);border-radius:10px}.equipment-list header{display:flex;align-items:center;justify-content:space-between;gap:7px}.equipment-list header strong{font-size:11px}.equipment-list b{color:var(--crm-teal);font-size:9px}.equipment-list p{display:flex;align-items:center;gap:5px;margin:0;color:var(--crm-text-muted);font-size:9px}.equipment-list a,.equipment-more{display:flex;align-items:center;justify-content:space-between;color:var(--crm-teal);font-size:9px;font-weight:750}.equipment-more{margin-top:12px;padding-top:10px;border-top:1px solid var(--crm-line)}.equipment-empty,.equipment-warning{margin:0;padding:16px 8px;color:var(--crm-text-muted);font-size:10px;line-height:1.6;text-align:center}.equipment-warning{color:#7b5c15;background:var(--crm-warning-soft);border-radius:9px}@media(max-width:1100px){.account-detail-layout{grid-template-columns:1fr}.equipment-column{position:static}.equipment-list{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:620px){.equipment-list{grid-template-columns:1fr}}
.detail-actions{display:flex;align-items:center;justify-content:space-between;gap:12px}.detail-actions .primary-button{display:flex;align-items:center;gap:6px}.detail-actions .primary-button:disabled{opacity:.5;cursor:not-allowed}.account-form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.account-form-grid label{display:grid;gap:6px}.account-form-grid label.wide{grid-column:1/-1}.account-form-grid span{color:var(--crm-text-muted);font-size:9px;font-weight:700}.account-form-grid input,.account-form-grid select{height:38px;padding:0 10px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.account-form-grid input:focus,.account-form-grid select:focus{border-color:var(--crm-teal);outline:0}.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:9px}@media(max-width:560px){.account-form-grid{grid-template-columns:1fr}.account-form-grid label.wide{grid-column:auto}.detail-actions{align-items:stretch;flex-direction:column}.detail-actions>*{justify-content:center}}
.site-editor{display:grid;gap:12px;margin-top:18px;padding-top:16px;border-top:1px solid var(--crm-line)}.site-editor>header{display:flex;align-items:center;justify-content:space-between;gap:12px}.site-editor>header div{display:grid;gap:3px}.site-editor>header strong{color:var(--crm-navy);font-size:11px}.site-editor>header small,.site-empty{color:var(--crm-text-muted);font-size:8px}.site-empty{margin:0;padding:14px;background:var(--crm-surface);border-radius:8px;text-align:center}.site-draft{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;padding:12px;background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:10px}.site-draft>b{grid-column:1/-1;color:var(--crm-teal);font-size:9px}.site-draft label{display:grid;gap:5px}.site-draft label:last-child{grid-column:1/-1}.site-draft span{color:var(--crm-text-muted);font-size:8px;font-weight:700}.site-draft input,.site-draft select{height:36px;padding:0 9px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.site-remove{grid-column:1/-1;justify-self:start;margin-top:2px;padding:6px 12px;font-size:9px;font-weight:700;color:var(--crm-danger);background:var(--crm-danger-soft);border:1px solid transparent;border-radius:8px;cursor:pointer}@media(max-width:560px){.site-editor>header{align-items:stretch;flex-direction:column}.site-draft{grid-template-columns:1fr}.site-draft>b,.site-draft label:last-child{grid-column:auto}}
</style>
