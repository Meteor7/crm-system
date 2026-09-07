<script setup lang="ts">
import { personnelDisplayName } from '@/demo/personnel'
import { computed, ref, watch } from 'vue'
import { ElDrawer, ElTabPane, ElTabs } from 'element-plus'
import { Building2, CalendarClock, ClipboardCheck, Factory, FileSignature, FlaskConical, MapPin, Users } from '@lucide/vue'
import type { CrmApi } from '@/api'
import type { Account360Dto } from '@/types/crm'
import DataState from '@/design-system/DataState.vue'
import DataNotice from '@/design-system/DataNotice.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import { mapRequestError, readRequestMeta, type RequestMetaState } from '@/api/request-state'
import { formatDisplayDate, shanghaiDate } from '@/domain/time'
import { formatMoney, moneyByCurrency } from '@/domain/money'
import { useI18n } from '@/i18n'

const props = defineProps<{ modelValue: boolean; accountId: string; apiClient: CrmApi }>()
const { locale } = useI18n()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const detail = ref<Account360Dto | null>(null)
const loading = ref(false)
const error = ref('')
const denied = ref(false)
const requestId = ref('')
const meta = ref<RequestMetaState | null>(null)
const visible = computed({ get: () => props.modelValue, set: (value) => emit('update:modelValue', value) })
const opportunityTotals = computed(() => detail.value ? moneyByCurrency(detail.value.opportunities.filter((item) => !['Won', 'Lost'].includes(item.stage))) : [])
const money = (value: number) => `¥${(value / 10000).toFixed(0)}万`
const today = shanghaiDate()
let loadSequence = 0

async function load() {
  if (!props.accountId) return
  const sequence = ++loadSequence
  const accountId = props.accountId
  detail.value = null
  loading.value = true
  error.value = ''
  denied.value = false
  requestId.value = ''
  meta.value = null
  try {
    const result = await props.apiClient.getAccount360(accountId)
    if (sequence === loadSequence && accountId === props.accountId) {
      detail.value = result.data
      meta.value = readRequestMeta(result)
    }
  } catch (reason) {
    if (sequence === loadSequence && accountId === props.accountId) {
      const mapped = mapRequestError(reason)
      error.value = mapped.message
      requestId.value = mapped.requestId
      denied.value = mapped.denied
    }
  } finally {
    if (sequence === loadSequence && accountId === props.accountId) loading.value = false
  }
}

watch([() => props.modelValue, () => props.accountId], ([open]) => {
  if (open) void load()
  else {
    loadSequence += 1
    detail.value = null
    error.value = ''
    meta.value = null
  }
}, { immediate: true })
</script>

<template>
  <div class="account-drawer-host">
  <ElDrawer v-model="visible" size="min(760px, 94vw)" :with-header="false" :append-to-body="false" :lock-scroll="false" destroy-on-close class="account-drawer">
    <DataState v-if="loading" type="loading" />
    <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
    <DataState v-else-if="error" type="error" :message="error" :request-id="requestId" @retry="load" />
    <template v-else-if="detail">
      <DataNotice v-if="meta?.stale" :message="meta.message" :request-id="meta.requestId" @refresh="load" />
      <div class="account-360" data-testid="account-360">
      <header class="drawer-hero">
        <span class="hero-mark">{{ detail.account.shortName.slice(0, 2) }}</span>
        <div><span class="eyebrow">ACCOUNT 360</span><h2>{{ detail.account.name }}</h2><p><MapPin :size="13" />{{ detail.account.city }} · {{ detail.account.segment }} · Owner {{ personnelDisplayName(detail.account.owner) }}</p></div>
        <StatusBadge :label="locale === 'en-US' ? `Tier ${detail.account.tier} account` : `${detail.account.tier} 级客户`" tone="positive" />
      </header>

      <section class="drawer-kpis">
        <div><span>OPEN PIPELINE</span><strong v-for="total in opportunityTotals" :key="total.currency">{{ formatMoney(total.amount, total.currency) }}</strong></div>
        <div><span>{{ locale === 'en-US' ? 'Intent score' : '意愿评分' }}</span><strong>{{ detail.account.intentScore }}</strong></div>
        <div><span>{{ locale === 'en-US' ? 'Active demos' : '活跃 DEMO' }}</span><strong>{{ detail.summary.activeDemos }}</strong></div>
        <div><span>{{ locale === 'en-US' ? 'Profile completeness' : '数据完整度' }}</span><strong>{{ detail.account.completeness }}%</strong></div>
      </section>

      <ElTabs class="drawer-tabs">
        <ElTabPane :label="locale === 'en-US' ? '360 overview' : '经营全貌'">
          <div class="drawer-grid">
            <section class="drawer-section sites-section">
              <header><Factory :size="16" /><strong>{{ locale === 'en-US' ? 'Sites' : 'Site / 厂区' }}</strong><span>{{ detail.sites.length }}</span></header>
              <article v-for="site in detail.sites" :key="site.id"><div><strong>{{ site.name }}</strong><small>{{ site.city }} · {{ site.type }} · {{ site.process }}</small></div><StatusBadge :label="site.status" tone="positive" /></article>
            </section>
            <section class="drawer-section contacts-section">
              <header><Users :size="16" /><strong>{{ locale === 'en-US' ? 'Stakeholders & reporting lines' : '关键人与组织关系' }}</strong><span>{{ detail.contacts.length }}</span></header>
              <article v-for="contact in detail.contacts" :key="contact.id"><span class="contact-avatar">{{ contact.name.slice(-2) }}</span><div><strong>{{ contact.name }} · {{ contact.title }}</strong><small>{{ contact.department }} · {{ contact.role }}</small></div><StatusBadge :label="contact.relationship" :tone="contact.relationship === 'Strong' ? 'positive' : 'info'" /></article>
              <div v-if="!detail.contacts.length" class="mini-empty">{{ locale === 'en-US' ? 'Stakeholder details pending' : '关键人关系待补充' }}</div>
            </section>
          </div>
          <section class="drawer-section full-section">
            <header><CalendarClock :size="16" /><strong>{{ locale === 'en-US' ? 'Next actions & risks' : '下一步行动与风险' }}</strong><span>{{ detail.actions.length }}</span></header>
            <article v-for="action in detail.actions" :key="action.id"><div><strong>{{ action.title }}</strong><small>{{ personnelDisplayName(action.owner) }} · {{ formatDisplayDate(action.due) }} · {{ locale === 'en-US' ? 'Source' : '来源' }} {{ action.sourceType }}</small></div><StatusBadge :label="action.status" :tone="action.due && action.due < today ? 'danger' : 'info'" /></article>
          </section>
        </ElTabPane>
        <ElTabPane :label="locale === 'en-US' ? `Requirements ${detail.requirements.length}` : `需求 ${detail.requirements.length}`">
          <section class="drawer-section full-section"><article v-for="item in detail.requirements" :key="item.id"><Building2 :size="16" /><div><strong>{{ item.title }}</strong><small>{{ item.equipment }} · {{ money(item.budgetAmount) }} · {{ item.nextAction }}</small></div><StatusBadge :label="item.status" tone="info" /></article></section>
        </ElTabPane>
        <ElTabPane :label="locale === 'en-US' ? `Demo / evaluations ${detail.demoRequests.length + detail.evaluations.length}` : `Demo / 验证 ${detail.demoRequests.length + detail.evaluations.length}`">
          <section class="drawer-section full-section"><header><ClipboardCheck :size="16" /><strong>Demo Request</strong><span>{{ detail.demoRequests.length }}</span></header><article v-for="item in detail.demoRequests" :key="item.id"><ClipboardCheck :size="16" /><div><strong>{{ item.title }}</strong><small>{{ item.id }} · {{ item.requestedEquipment }} · {{ locale === 'en-US' ? 'Target' : '目标' }} {{ item.targetDate }}</small></div><StatusBadge :label="item.status" :tone="item.status === 'Converted' ? 'positive' : 'info'" /></article><div v-if="!detail.demoRequests.length" class="mini-empty">{{ locale === 'en-US' ? 'No Demo Requests' : '暂无 Demo Request' }}</div></section>
          <section class="drawer-section full-section"><header><FlaskConical :size="16" /><strong>Evaluation / Wafer Test</strong><span>{{ detail.evaluations.length }}</span></header><article v-for="item in detail.evaluations" :key="item.id"><FlaskConical :size="16" /><div><strong>{{ item.title }}</strong><small>{{ item.id }} · {{ item.wafers }} Wafers · {{ personnelDisplayName(item.owner) }}</small></div><StatusBadge :label="item.status" tone="info" /></article><div v-if="!detail.evaluations.length" class="mini-empty">{{ locale === 'en-US' ? 'No evaluation projects' : '暂无验证项目' }}</div></section>
        </ElTabPane>
        <ElTabPane :label="locale === 'en-US' ? `Contracts ${detail.contracts.length}` : `合同 ${detail.contracts.length}`">
          <section class="drawer-section full-section"><article v-for="item in detail.contracts" :key="item.id"><FileSignature :size="16" /><div><strong>{{ item.type }} · {{ item.id }}</strong><small>{{ money(item.amount) }} · {{ item.start }} {{ locale === 'en-US' ? 'to' : '至' }} {{ item.end }}</small></div><StatusBadge :label="item.status" :tone="item.signed ? 'positive' : 'warning'" /></article><div v-if="!detail.contracts.length" class="mini-empty">{{ locale === 'en-US' ? 'No contracts' : '暂无合同' }}</div></section>
        </ElTabPane>
      </ElTabs>
      </div>
    </template>
  </ElDrawer>
  </div>
</template>

<style scoped>
.account-drawer-host :deep(.el-overlay) { position: absolute; inset: 0; z-index: 2000; overflow: hidden; background: rgba(7,29,37,.42); }
.account-drawer-host :deep(.el-overlay-dialog) { position: absolute; inset: 0; overflow: hidden; }
.account-drawer-host :deep(.el-drawer) { position: absolute; top: 0; right: 0; display: flex; height: 100%; flex-direction: column; overflow: hidden; background: #fff; box-shadow: -18px 0 48px rgba(8,32,40,.18); }
.account-drawer-host :deep(.el-drawer__body) { min-width: 0; flex: 1; overflow: auto; padding: 20px; }
.account-drawer-host :deep(.el-tabs__header) { margin: 0 0 14px; border-bottom: 1px solid var(--crm-line); }
.account-drawer-host :deep(.el-tabs__nav-wrap) { position: relative; overflow: hidden; }
.account-drawer-host :deep(.el-tabs__nav-scroll) { overflow: hidden; }
.account-drawer-host :deep(.el-tabs__nav) { display: flex; gap: 4px; }
.account-drawer-host :deep(.el-tabs__active-bar) { position: absolute; bottom: 0; height: 2px; background: var(--crm-teal); transition: transform .2s ease; }
.account-drawer-host :deep(.el-tabs__item) { height: 40px; padding: 0 14px; color: var(--crm-text-muted); background: transparent; border: 0; font-size: 10px; cursor: pointer; }
.account-drawer-host :deep(.el-tabs__item.is-active) { color: var(--crm-teal); font-weight: 700; }
.account-drawer-host :deep(.el-tab-pane[aria-hidden="true"]) { display: none; }
.account-360 { min-height: 100%; color: var(--crm-text); font-family: var(--crm-font-sans); }
.drawer-hero { display: grid; grid-template-columns: 54px minmax(0,1fr) auto; align-items: center; gap: 14px; margin: -20px -20px 0; padding: 28px 28px 22px; color: #fff; background: var(--crm-navy); }
.hero-mark { display: grid; width: 54px; height: 54px; place-items: center; color: var(--crm-positive); background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.13); border-radius: 15px; font-size: 13px; font-weight: 800; }
.eyebrow { color: #93c7c1; font-size: 9px; font-weight: 800; letter-spacing: .13em; }
.drawer-hero h2 { margin: 4px 0; color: #fff; font-size: 19px; }
.drawer-hero p { display: flex; align-items: center; gap: 4px; margin: 0; color: rgba(255,255,255,.58); font-size: 10px; }
.drawer-kpis { display: grid; grid-template-columns: repeat(4,1fr); gap: 1px; margin: 0 -20px 14px; background: var(--crm-line); border-bottom: 1px solid var(--crm-line); }
.drawer-kpis div { display: grid; gap: 4px; padding: 14px 18px; background: #fff; }
.drawer-kpis span { color: var(--crm-text-muted); font-size: 8px; font-weight: 700; letter-spacing: .08em; }
.drawer-kpis strong { color: var(--crm-navy); font-size: 17px; font-variant-numeric: tabular-nums; }
.drawer-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.drawer-section { padding: 14px; background: var(--crm-surface); border: 1px solid var(--crm-line); border-radius: 12px; }
.drawer-section > header { display: flex; align-items: center; gap: 7px; margin-bottom: 8px; color: var(--crm-teal); }
.drawer-section > header strong { flex: 1; color: var(--crm-navy); font-size: 11px; }
.drawer-section > header span { color: var(--crm-text-muted); font-size: 9px; }
.drawer-section article { display: flex; align-items: center; gap: 9px; min-height: 50px; padding: 7px 0; border-bottom: 1px solid var(--crm-line); }
.drawer-section article:last-child { border-bottom: 0; }
.drawer-section article > div { display: grid; min-width: 0; flex: 1; gap: 4px; }
.drawer-section article strong { overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.drawer-section article small { overflow: hidden; color: var(--crm-text-muted); font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.full-section { margin-top: 12px; }
.contact-avatar { display: grid; width: 30px; height: 30px; flex: 0 0 auto; place-items: center; color: var(--crm-teal); background: var(--crm-teal-soft); border-radius: 9px; font-size: 9px; font-weight: 800; }
.mini-empty { padding: 20px; color: var(--crm-text-muted); font-size: 10px; text-align: center; }
@media (max-width: 600px) { .drawer-hero { grid-template-columns: 44px 1fr; } .drawer-hero > :last-child { display: none; } .hero-mark { width: 44px; height: 44px; } .drawer-kpis { grid-template-columns: 1fr 1fr; } .drawer-grid { grid-template-columns: 1fr; } }
</style>
