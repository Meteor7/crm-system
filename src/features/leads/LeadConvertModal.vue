<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import type { AccountSummaryDto, ContactSummaryDto, LeadConversionInput, LeadDto, SiteDto } from '@/types/crm'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import PersonnelSelect from '@/design-system/PersonnelSelect.vue'
import AccountSegmentSelect from '@/features/accounts/AccountSegmentSelect.vue'
import { useAppStore } from '@/stores/app'

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
        process: form.siteProcess,
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
    opportunityTitle: form.opportunityTitle,
    opportunityAmount: String(form.opportunityAmount),
    opportunityCloseDate: form.opportunityCloseDate,
    opportunityOwner: form.opportunityOwner,
    toolType: form.toolType,
  })
}
</script>

<template>
  <ModalShell title="转换 Lead" eyebrow="QUALIFIED → BUSINESS RECORDS" :busy="busy" @close="emit('close')" @submit="submit">
    <p class="conversion-note">可复用现有 Account、Contact 与厂区；未选择时系统会根据 Lead 自动创建业务记录。转换只执行一次。</p>
    <p v-if="error" class="form-error">{{ error }}</p>
    <div class="convert-form">
      <label><span>复用 Account</span><select v-model="form.accountId" aria-label="复用 Account"><option value="">创建新 Account：{{ lead.company }}</option><option v-for="account in accounts" :key="account.id" :value="account.id">{{ account.name }}</option></select></label>
      <label><span>复用 Contact</span><select v-model="form.contactId" aria-label="复用 Contact" :disabled="!form.accountId"><option value="">创建新 Contact：{{ lead.name }}</option><option v-for="contact in accountContacts" :key="contact.id" :value="contact.id">{{ contact.name }} · {{ contact.title }}</option></select></label>
      <template v-if="!form.accountId">
        <label><span>客户全称<RequiredMark /></span><input v-model="form.accountName" aria-label="新客户全称" required /></label>
        <label><span>客户简称<RequiredMark /></span><input v-model="form.accountShortName" aria-label="新客户简称" required /></label>
        <label><span>业务领域<RequiredMark /></span><AccountSegmentSelect v-model="form.accountSegment" :segments="segments" label="新客户业务领域" required /></label>
        <label><span>客户等级</span><select v-model="form.accountTier" aria-label="新客户等级"><option>S</option><option>A</option><option>B</option></select></label>
        <label><span>城市<RequiredMark /></span><input v-model="form.accountCity" aria-label="新客户城市" required /></label>
        <label><span>区域<RequiredMark /></span><input v-model="form.accountRegion" aria-label="新客户区域" required /></label>
        <label><span>客户负责人<RequiredMark /></span><PersonnelSelect v-model="form.accountOwner" :roles="['Sales']" :ariaLabel="'\u65b0\u5ba2\u6237\u8d1f\u8d23\u4eba'" required /></label>
        <label><span>厂区名称<RequiredMark /></span><input v-model="form.siteName" aria-label="新厂区名称" required /></label>
        <label><span>厂区城市<RequiredMark /></span><input v-model="form.siteCity" aria-label="新厂区城市" required /></label>
        <label><span>厂区类型<RequiredMark /></span><input v-model="form.siteType" aria-label="新厂区类型" required /></label>
        <label><span>制程<RequiredMark /></span><input v-model="form.siteProcess" aria-label="新厂区制程" required /></label>
        <label><span>厂区状态</span><select v-model="form.siteStatus" aria-label="新厂区状态"><option>量产</option><option>建设中</option><option>规划中</option></select></label>
      </template>
      <label v-else><span>厂区<RequiredMark /></span><select v-model="form.siteId" aria-label="Opportunity 厂区" required><option v-for="site in accountSites" :key="site.id" :value="site.id">{{ site.name }}</option></select></label>
      <template v-if="!form.contactId">
        <label><span>联系人姓名<RequiredMark /></span><input v-model="form.contactName" aria-label="新联系人姓名" required /></label>
        <label><span>联系人职位<RequiredMark /></span><input v-model="form.contactTitle" aria-label="新联系人职位" required /></label>
        <label><span>联系人部门<RequiredMark /></span><input v-model="form.contactDepartment" aria-label="新联系人部门" required /></label>
        <label><span>联系人电话</span><input v-model="form.contactPhone" aria-label="新联系人电话" /></label>
        <label><span>联系人邮箱</span><input v-model="form.contactEmail" aria-label="新联系人邮箱" type="email" /></label>
        <label><span>联系人负责人<RequiredMark /></span><PersonnelSelect v-model="form.contactOwner" :roles="['Sales']" :ariaLabel="'\u65b0\u8054\u7cfb\u4eba\u8d1f\u8d23\u4eba'" required /></label>
      </template>
      <label><span>Opportunity 名称<RequiredMark /></span><input v-model="form.opportunityTitle" aria-label="Opportunity 名称" required /></label>
      <label><span>Opportunity 金额<RequiredMark /></span><input v-model="form.opportunityAmount" aria-label="Opportunity 金额" type="number" min="0.01" step="0.01" required /></label>
      <label><span>预计成交日期<RequiredMark /></span><input v-model="form.opportunityCloseDate" aria-label="Opportunity 预计成交日期" type="date" required /></label>
      <label><span>负责人<RequiredMark /></span><PersonnelSelect v-model="form.opportunityOwner" :roles="app.bootstrap?.user.role === 'Manager' ? ['Sales', 'Manager'] : ['Sales']" :ariaLabel="'Opportunity \u8d1f\u8d23\u4eba'" required /></label>
      <label><span>产品 / 设备<RequiredMark /></span><input v-model="form.toolType" aria-label="Opportunity 产品" required /></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.conversion-note{margin:0 0 12px;padding:10px 12px;color:var(--crm-text-muted);background:var(--crm-teal-soft);border-radius:9px;font-size:10px;line-height:1.6}.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:10px}.convert-form{display:grid;grid-template-columns:1fr 1fr;gap:13px}.convert-form label{display:grid;gap:6px;color:var(--crm-text-muted);font-size:10px;font-weight:700}.convert-form input,.convert-form select{width:100%;min-height:38px;padding:8px 10px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:8px;outline:0}.convert-form select:disabled{background:var(--crm-surface)}@media(max-width:560px){.convert-form{grid-template-columns:1fr}}
</style>
