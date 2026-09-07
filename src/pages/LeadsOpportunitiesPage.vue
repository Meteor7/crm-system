<script setup lang="ts">
import { computed } from 'vue'
import { BriefcaseBusiness, Route, UserRoundSearch } from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import { api as defaultApi, type CrmApi } from '@/api'
import PageHeader from '@/design-system/PageHeader.vue'
import LeadListView from '@/features/leads/LeadListView.vue'
import OpportunityListView from '@/features/opportunities/OpportunityListView.vue'
import { useI18n } from '@/i18n'

const props = withDefaults(defineProps<{ apiClient?: CrmApi; fixedView?: 'leads' | 'opportunities' }>(), {
  apiClient: () => defaultApi,
  fixedView: undefined,
})
const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()
const view = computed<'leads' | 'opportunities'>(() => props.fixedView ?? (route.query.view === 'opportunities' ? 'opportunities' : 'leads'))
const title = computed(() => props.fixedView === 'leads' ? t('nav.leads') : props.fixedView === 'opportunities' ? t('nav.opportunities') : 'Leads&Opportunities')
const description = computed(() => props.fixedView === 'leads'
  ? t('leads.description')
  : props.fixedView === 'opportunities'
    ? t('opportunities.description')
    : t('sales.workspaceDescription'))

function switchView(next: 'leads' | 'opportunities') {
  void router.replace({ query: { ...route.query, view: next } })
}
</script>

<template>
      <div class="leads-opportunities-page">
    <PageHeader
      eyebrow="QUALIFY → CONVERT → WIN"
      :title="title"
      :description="description"
    />
    <div :class="['workspace-layout', { 'is-fixed-view': fixedView }]">
      <aside v-if="!fixedView" class="workspace-switch" :aria-label="locale === 'en-US' ? 'Leads and Opportunities view switch' : '线索与商机视图切换'">
        <button type="button" data-workspace-view="leads" :class="{ active: view === 'leads' }" @click="switchView('leads')">
          <span><UserRoundSearch :size="17" /></span>
          <strong>{{ t('nav.leads') }}</strong>
          <small>{{ locale === 'en-US' ? 'Identify people and sources' : '识别人和来源' }}</small>
        </button>
        <div class="flow-connector"><Route :size="14" /><span>{{ locale === 'en-US' ? 'Qualified → convert' : '合格 → 转换' }}</span></div>
        <button type="button" data-workspace-view="opportunities" :class="{ active: view === 'opportunities' }" @click="switchView('opportunities')">
          <span><BriefcaseBusiness :size="17" /></span>
          <strong>{{ t('nav.opportunities') }}</strong>
          <small>{{ locale === 'en-US' ? 'Move deals and revenue' : '推进交易与收入' }}</small>
        </button>
        <p>{{ locale === 'en-US' ? 'Converted leads become formal accounts, contacts, and opportunities. Bookings are managed separately in the main navigation.' : 'Lead 转换后才进入正式 Account、Contact 与 Opportunity。Booking 在左侧主导航中独立管理。' }}</p>
      </aside>
      <main class="workspace-content">
        <LeadListView v-if="view === 'leads'" :api-client="apiClient" />
        <OpportunityListView v-else :api-client="apiClient" />
      </main>
    </div>
  </div>
</template>

<style scoped>
.workspace-layout{display:grid;grid-template-columns:184px minmax(0,1fr);gap:14px;align-items:start}.workspace-layout.is-fixed-view{grid-template-columns:minmax(0,1fr)}.workspace-switch{position:sticky;top:78px;display:grid;gap:8px;padding:10px;background:#fff;border:1px solid var(--crm-line);border-radius:13px}.workspace-switch button{display:grid;grid-template-columns:34px 1fr;grid-template-rows:auto auto;gap:2px 8px;align-items:center;padding:11px;color:var(--crm-text-muted);text-align:left;background:transparent;border:1px solid transparent;border-radius:10px;cursor:pointer}.workspace-switch button>span{display:grid;grid-row:1/3;width:34px;height:34px;place-items:center;background:var(--crm-surface);border-radius:9px}.workspace-switch button strong{color:var(--crm-navy);font-size:11px}.workspace-switch button small{font-size:8px}.workspace-switch button.active{color:var(--crm-brand-ink);background:var(--crm-teal-soft);border-color:#c3e4de}.workspace-switch button.active>span{color:#fff;background:var(--crm-teal)}.flow-connector{display:flex;align-items:center;gap:5px;padding:2px 9px;color:var(--crm-text-muted);font-size:7px}.workspace-switch p{margin:5px 4px 2px;padding-top:10px;color:var(--crm-text-muted);border-top:1px solid var(--crm-line);font-size:8px;line-height:1.65}.workspace-content{min-width:0}@media(max-width:850px){.workspace-layout{grid-template-columns:1fr}.workspace-switch{position:static;grid-template-columns:1fr auto 1fr}.workspace-switch p{grid-column:1/-1}.flow-connector{justify-content:center}}@media(max-width:560px){.workspace-switch{grid-template-columns:1fr}.flow-connector{justify-content:flex-start}.workspace-switch p{grid-column:auto}}
</style>
