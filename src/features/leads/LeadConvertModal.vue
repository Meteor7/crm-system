<script setup lang="ts">
import { useLocalizedInput } from '@/i18n/localized-input'
import { systemValueLabel } from '@/features/shared/system-labels'
import { computed, reactive, watch } from 'vue'
import type { AccountSummaryDto, ContactSummaryDto, LeadConversionInput, LeadDto, SiteDto } from '@/types/crm'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import PersonnelSelect from '@/design-system/PersonnelSelect.vue'
import AccountSegmentSelect from '@/features/accounts/AccountSegmentSelect.vue'
import { useAppStore } from '@/stores/app'
import { useI18n } from '@/i18n'

const props = defineProps<{
  lead: LeadDto
  accounts: AccountSummaryDto[]
  contacts: ContactSummaryDto[]
  sites: Array<SiteDto & { accountId: string }>
  segments: string[]
  busy?: boolean
  error?: string
}>()
const emit = defineEmits<{ close: []; submit: [payload: LeadConversionInput] }>()
const app = useAppStore()
const { t, locale } = useI18n()
const form = reactive({
  accountId: '',
  contactId: '',
  siteId: '',
  opportunityTitle: '',
  opportunityAmount: '',
  opportunityCloseDate: '2026-12-31',
  opportunityOwner: '',
  toolType: '',
  accountName: '',
  accountShortName: '',
  accountSegment: 'Frontend' as AccountSummaryDto['segment'],
  accountTier: 'A' as AccountSummaryDto['tier'],
  accountCity: '',
  accountRegion: '',
  accountOwner: '',
  siteName: '',
  siteCity: '',
  siteType: 'Fab',
  siteProcess: '',
  siteStatus: '规划中' as SiteDto['status'],
  contactName: '',
  contactTitle: '',
  contactDepartment: '',
  contactPhone: '',
  contactEmail: '',
  contactOwner: '',
})
const accountContacts = computed(() => props.contacts.filter((contact) => contact.accountId === form.accountId && contact.status === 'Active'))
const accountSites = computed(() => props.sites.filter((site) => site.accountId === form.accountId))

watch(() => props.lead, (lead) => {
  form.accountId = ''
  form.contactId = ''
  form.siteId = ''
  form.opportunityTitle = `${lead.company} · ${lead.interest || '新项目'}`
  form.opportunityAmount = ''
  form.opportunityCloseDate = '2026-12-31'
  form.opportunityOwner = lead.owner
  form.toolType = '待确认'
  form.accountName = lead.company
  form.accountShortName = lead.company.replace(/[（(].*$/, '').slice(0, 12)
  form.accountCity = ''
  form.accountRegion = ''
  form.accountOwner = lead.owner
  form.siteName = `${form.accountShortName} Main Site`
  form.siteCity = ''
  form.siteProcess = '待确认'
  form.contactName = lead.name
  form.contactTitle = lead.title
  form.contactDepartment = ''
  form.contactPhone = lead.phone ?? ''
  form.contactEmail = lead.email ?? ''
  form.contactOwner = lead.owner
}, { immediate: true })
watch(() => form.accountId, () => {
  if (!accountContacts.value.some((item) => item.id === form.contactId)) form.contactId = ''
  if (!accountSites.value.some((item) => item.id === form.siteId)) form.siteId = accountSites.value[0]?.id ?? ''
})

function submit() {
  emit('submit', {
    ...(form.accountId ? { accountId: form.accountId } : {}),
    ...(form.contactId ? { contactId: form.contactId } : {}),
    ...(form.siteId ? { siteId: form.siteId } : {}),
    ...(!form.accountId ? {
      newAccount: {
        name: form.accountName,
        shortName: form.accountShortName,
        segment: form.accountSegment,
        tier: form.accountTier,
        city: form.accountCity,
        region: form.accountRegion,
        owner: form.accountOwner,
      },
      newSite: {
        name: form.siteName,
        city: form.siteCity,
        type: form.siteType,
        process: siteProcessInput.value,
        status: form.siteStatus,
      },
    } : {}),
    ...(!form.contactId ? {
      newContact: {
        name: form.contactName,
        title: form.contactTitle,
        department: form.contactDepartment,
        ...(form.contactPhone ? { phone: form.contactPhone } : {}),
        ...(form.contactEmail ? { email: form.contactEmail } : {}),
        relationship: 'Developing' as const,
        owner: form.contactOwner,
        status: 'Active' as const,
      },
    } : {}),
    opportunityTitle: opportunityTitleInput.value,
    opportunityAmount: String(form.opportunityAmount),
    opportunityCloseDate: form.opportunityCloseDate,
    opportunityOwner: form.opportunityOwner,
    toolType: toolTypeInput.value,
  })
}

const toolTypeInput = useLocalizedInput(() => form.toolType, (value) => { form.toolType = value }, (value) => systemValueLabel(value, locale.value), () => props.lead)
const siteProcessInput = useLocalizedInput(() => form.siteProcess, (value) => { form.siteProcess = value }, (value) => systemValueLabel(value, locale.value), () => props.lead)
const opportunityTitleInput = useLocalizedInput(() => form.opportunityTitle, (value) => { form.opportunityTitle = value }, (value) => !props.lead.interest && value === `${props.lead.company} · 新项目` && locale.value === 'en-US' ? `${props.lead.company} · New project` : value, () => props.lead)
</script>

<template>
  <ModalShell :title="t('leadConvert.title')" eyebrow="QUALIFIED → BUSINESS RECORDS" :busy="busy" @close="emit('close')" @submit="submit">
    <p class="conversion-note">{{ t('leadConvert.note') }}</p>
    <p v-if="error" class="form-error">{{ error }}</p>
    <div class="convert-form">
      <label><span>{{ t('leadConvert.reuseAccount') }}</span><select v-model="form.accountId" :aria-label="t('leadConvert.reuseAccount')"><option value="">{{ t('leadConvert.newAccount') }}: {{ lead.company }}</option><option v-for="account in accounts" :key="account.id" :value="account.id">{{ account.name }}</option></select></label>
      <label><span>{{ t('leadConvert.reuseContact') }}</span><select v-model="form.contactId" :aria-label="t('leadConvert.reuseContact')" :disabled="!form.accountId"><option value="">{{ t('leadConvert.newContact') }}: {{ lead.name }}</option><option v-for="contact in accountContacts" :key="contact.id" :value="contact.id">{{ contact.name }} · {{ contact.title }}</option></select></label>
      <template v-if="!form.accountId">
        <label><span>{{ t('detail.accountName') }}<RequiredMark /></span><input v-model="form.accountName" :aria-label="t('detail.accountName')" required /></label>
        <label><span>{{ t('detail.accountShortName') }}<RequiredMark /></span><input v-model="form.accountShortName" :aria-label="t('detail.accountShortName')" required /></label>
        <label><span>{{ t('detail.businessArea') }}<RequiredMark /></span><AccountSegmentSelect v-model="form.accountSegment" :segments="segments" :label="t('detail.businessArea')" required /></label>
        <label><span>{{ t('detail.accountTier') }}</span><select v-model="form.accountTier" :aria-label="t('detail.accountTier')"><option>S</option><option>A</option><option>B</option></select></label>
        <label><span>{{ t('detail.city') }}<RequiredMark /></span><input v-model="form.accountCity" :aria-label="t('detail.city')" required /></label>
        <label><span>{{ t('detail.region') }}<RequiredMark /></span><input v-model="form.accountRegion" :aria-label="t('detail.region')" required /></label>
        <label><span>{{ t('detail.owner') }}<RequiredMark /></span><PersonnelSelect v-model="form.accountOwner" :roles="['Sales']" :ariaLabel="t('detail.owner')" required /></label>
        <label><span>{{ t('detail.siteName') }}<RequiredMark /></span><input v-model="form.siteName" :aria-label="t('detail.siteName')" required /></label>
        <label><span>{{ t('detail.city') }}<RequiredMark /></span><input v-model="form.siteCity" :aria-label="t('detail.city')" required /></label>
        <label><span>{{ t('detail.siteType') }}<RequiredMark /></span><input v-model="form.siteType" :aria-label="t('detail.siteType')" required /></label>
        <label><span>{{ t('detail.process') }}<RequiredMark /></span><input v-model="siteProcessInput" :aria-label="t('detail.process')" required /></label>
        <label><span>{{ t('detail.status') }}</span><select v-model="form.siteStatus" :aria-label="t('detail.status')"><option value="量产">{{ t('site.status.production') }}</option><option value="建设中">{{ t('site.status.construction') }}</option><option value="规划中">{{ t('site.status.planning') }}</option></select></label>
      </template>
      <label v-else><span>{{ t('detail.site') }}<RequiredMark /></span><select v-model="form.siteId" :aria-label="t('detail.site')" required><option v-for="site in accountSites" :key="site.id" :value="site.id">{{ site.name }}</option></select></label>
      <template v-if="!form.contactId">
        <label><span>{{ t('detail.contact') }}{{ t('detail.nameSuffix') }}<RequiredMark /></span><input v-model="form.contactName" :aria-label="t('leadConvert.contactName')" required /></label>
        <label><span>{{ t('detail.contact') }}{{ t('detail.titleSuffix') }}<RequiredMark /></span><input v-model="form.contactTitle" :aria-label="t('leadConvert.contactTitle')" required /></label>
        <label><span>{{ t('detail.contact') }}{{ t('detail.departmentSuffix') }}<RequiredMark /></span><input v-model="form.contactDepartment" :aria-label="t('leadConvert.contactDepartment')" required /></label>
        <label><span>{{ t('detail.contact') }}{{ t('detail.phoneSuffix') }}</span><input v-model="form.contactPhone" :aria-label="t('detail.phone')" /></label>
        <label><span>{{ t('detail.contact') }}{{ t('detail.emailSuffix') }}</span><input v-model="form.contactEmail" :aria-label="t('detail.email')" type="email" /></label>
        <label><span>{{ t('detail.contact') }}{{ t('detail.ownerSuffix') }}<RequiredMark /></span><PersonnelSelect v-model="form.contactOwner" :roles="['Sales']" :ariaLabel="t('detail.owner')" required /></label>
      </template>
      <label><span>{{ t('oppEditor.name') }}<RequiredMark /></span><input v-model="opportunityTitleInput" :aria-label="t('oppEditor.name')" required /></label>
      <label><span>{{ t('oppEditor.amount') }}<RequiredMark /></span><input v-model="form.opportunityAmount" :aria-label="t('oppEditor.amount')" type="number" min="0.01" step="0.01" required /></label>
      <label><span>{{ t('oppEditor.poDate') }}<RequiredMark /></span><input v-model="form.opportunityCloseDate" :aria-label="t('oppEditor.poDate')" type="date" required /></label>
      <label><span>{{ t('detail.owner') }}<RequiredMark /></span><PersonnelSelect v-model="form.opportunityOwner" :roles="app.bootstrap?.user.role === 'Manager' ? ['Sales', 'Manager'] : ['Sales']" :ariaLabel="t('detail.owner')" required /></label>
      <label><span>{{ t('oppEditor.toolType') }}<RequiredMark /></span><input v-model="toolTypeInput" :aria-label="t('oppEditor.toolType')" required /></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.conversion-note{margin:0 0 12px;padding:10px 12px;color:var(--crm-text-muted);background:var(--crm-teal-soft);border-radius:9px;font-size:10px;line-height:1.6}.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:10px}.convert-form{display:grid;grid-template-columns:1fr 1fr;gap:13px}.convert-form label{display:grid;gap:6px;color:var(--crm-text-muted);font-size:10px;font-weight:700}.convert-form input,.convert-form select{width:100%;min-height:38px;padding:8px 10px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:8px;outline:0}.convert-form select:disabled{background:var(--crm-surface)}@media(max-width:560px){.convert-form{grid-template-columns:1fr}}
</style>
