<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import PersonnelSelect from '@/design-system/PersonnelSelect.vue'
import { preferredPersonnelId } from '@/demo/personnel'
import { calculateOpportunityProbability, opportunityProbabilityExplanation } from '@/domain/opportunity-probability'
import type { AccountSummaryDto, SiteDto } from '@/types/crm'
import type { CreateStrategyOpportunityInput, StrategyOpportunityDto } from '@/types/workspaces'

const props = defineProps<{
  opportunity?: StrategyOpportunityDto | null
  accounts: AccountSummaryDto[]
  sitesByAccount: Record<string, SiteDto[]>
  defaultOwner: string
  busy?: boolean
  error?: string
}>()
const emit = defineEmits<{ close: []; submit: [value: CreateStrategyOpportunityInput] }>()

const SALE_TYPE_OPTIONS = ['New Equipment', 'Repeat Order', 'Service'] as const

function normalizeSaleType(value?: string) {
  if (value === 'New Tool') return 'New Equipment'
  if (value === 'Capacity Expansion') return 'Repeat Order'
  return SALE_TYPE_OPTIONS.includes(value as typeof SALE_TYPE_OPTIONS[number]) ? value! : 'New Equipment'
}

const firstAccount = props.accounts[0]
const initialAccountId = props.opportunity?.accountId ?? firstAccount?.id ?? ''
const form = ref<CreateStrategyOpportunityInput>({
  accountId: initialAccountId,
  siteId: props.opportunity?.siteId ?? props.sitesByAccount[initialAccountId]?.[0]?.id ?? '',
  title: props.opportunity?.title ?? '',
  owner: preferredPersonnelId('Sales', props.opportunity?.owner ?? props.defaultOwner),
  stage: props.opportunity?.stage ?? '需求发现',
  forecast: props.opportunity?.forecast ?? 'Pipeline',
  amount: props.opportunity?.amount ?? '',
  intentScore: props.opportunity?.score ?? 50,
  poDate: props.opportunity?.poDate ?? '2026-10-31',
  toolType: props.opportunity?.toolType ?? '',
  saleType: normalizeSaleType(props.opportunity?.saleType),
  subRegion: props.opportunity?.subRegion ?? firstAccount?.region ?? '华东',
  currency: props.opportunity?.currency ?? 'CNY',
  originalAmount: props.opportunity?.originalAmount ?? props.opportunity?.amount ?? '',
  shipmentDate: props.opportunity?.shipmentDate ?? '',
  fatDate: props.opportunity?.fatDate ?? '',
  paymentMilestones: props.opportunity?.paymentMilestones ?? [],
  competition: props.opportunity?.competition ?? '',
  winReason: props.opportunity?.winReason ?? '',
  lostReason: props.opportunity?.lostReason ?? '',
  strengths: props.opportunity?.strengths ?? [],
  redFlags: props.opportunity?.redFlags ?? [],
  informationNeeded: props.opportunity?.informationNeeded ?? [],
})
const sites = computed(() => props.sitesByAccount[form.value.accountId] ?? [])
const paymentText = ref((form.value.paymentMilestones ?? []).join('\n'))
const strengthsText = ref((form.value.strengths ?? []).join('\n'))
const redFlagsText = ref((form.value.redFlags ?? []).join('\n'))
const informationText = ref((form.value.informationNeeded ?? []).join('\n'))
const calculatedProbability = computed(() => calculateOpportunityProbability(form.value.stage, Number(form.value.intentScore)))
const probabilityExplanation = computed(() => opportunityProbabilityExplanation(form.value.stage, Number(form.value.intentScore)))

watch(() => form.value.accountId, (accountId) => {
  const account = props.accounts.find((item) => item.id === accountId)
  form.value.siteId = props.sitesByAccount[accountId]?.[0]?.id ?? ''
  if (account) form.value.subRegion = account.region
})

function lines(value: string) { return value.split('\n').map((item) => item.trim()).filter(Boolean) }
function submit() {
  emit('submit', {
    ...form.value,
    amount: form.value.amount, intentScore: Number(form.value.intentScore), originalAmount: form.value.originalAmount || form.value.amount,
    paymentMilestones: lines(paymentText.value), strengths: lines(strengthsText.value), redFlags: lines(redFlagsText.value), informationNeeded: lines(informationText.value),
  })
}
</script>

<template>
  <ModalShell :title="opportunity ? '编辑 Opportunity' : '新增 Opportunity'" eyebrow="OPPORTUNITY STRATEGY" :busy="busy" @close="$emit('close')" @submit="submit">
    <p v-if="error" class="form-error">{{ error }}</p>
    <div class="opportunity-form-grid">
      <label class="wide"><span>Opportunity 名称<RequiredMark :show="!opportunity" /></span><input v-model="form.title" aria-label="Opportunity 名称" required /></label>
      <label><span>客户</span><select v-model="form.accountId" aria-label="Opportunity 客户"><option v-for="account in accounts" :key="account.id" :value="account.id">{{ account.shortName }} · {{ account.name }}</option></select></label>
      <label><span>厂区<RequiredMark :show="!opportunity" /></span><select v-model="form.siteId" aria-label="Opportunity 厂区" required><option v-for="site in sites" :key="site.id" :value="site.id">{{ site.name }}</option></select></label>
      <label><span>负责人<RequiredMark :show="!opportunity" /></span><PersonnelSelect v-model="form.owner" :roles="['Sales', 'Manager']" :ariaLabel="'Opportunity \u8d1f\u8d23\u4eba'" required /></label>
      <div class="readonly-stage"><span>阶段</span><strong>{{ form.stage }}</strong></div>
      <label><span>预测分类</span><select v-model="form.forecast" aria-label="Opportunity 预测分类"><option>Pipeline</option><option>Upside</option><option>Commit</option></select></label>
      <label class="intent-field">
        <span>购买意愿</span>
        <div class="intent-slider-row">
          <input
            v-model.number="form.intentScore"
            aria-label="Opportunity 购买意愿"
            type="range"
            min="0"
            max="100"
            step="1"
          />
          <output data-testid="opportunity-intent-value">{{ form.intentScore }}</output>
        </div>
      </label>
      <div class="probability-preview" data-testid="calculated-opportunity-probability">
        <span>自动成交概率</span>
        <strong>{{ calculatedProbability }}%</strong>
        <small>{{ probabilityExplanation }}</small>
      </div>
      <label><span>金额<RequiredMark :show="!opportunity" /></span><input v-model="form.amount" aria-label="Opportunity 金额" type="text" inputmode="decimal" min="0.01" pattern="\d+(?:\.\d{1,2})?" required /></label>
      <label><span>币种</span><select v-model="form.currency" aria-label="Opportunity 币种"><option>CNY</option><option>USD</option><option>EUR</option></select></label>
      <label><span>原始金额</span><input v-model="form.originalAmount" aria-label="Opportunity 原始金额" type="text" inputmode="decimal" pattern="\d+(?:\.\d{1,2})?" /></label>
      <label><span>预计 PO 日期<RequiredMark :show="!opportunity" /></span><input v-model="form.poDate" aria-label="Opportunity PO 日期" type="date" required /></label>
      <label><span>设备类型</span><input v-model="form.toolType" aria-label="Opportunity 设备类型" placeholder="Inspection Tool" /></label>
      <label><span>销售类型</span><select v-model="form.saleType" aria-label="Opportunity 销售类型"><option v-for="saleType in SALE_TYPE_OPTIONS" :key="saleType" :value="saleType">{{ saleType }}</option></select></label>
      <label><span>预计发货日期</span><input v-model="form.shipmentDate" aria-label="Opportunity 发货日期" type="date" /></label>
      <label><span>预计 FAT 日期</span><input v-model="form.fatDate" aria-label="Opportunity FAT 日期" type="date" /></label>
      <label class="wide"><span>竞争情况</span><input v-model="form.competition" aria-label="Opportunity 竞争情况" /></label>
      <label><span>Payment Milestones（每行一项）</span><textarea v-model="paymentText" aria-label="Opportunity 付款节点" rows="3" /></label>
      <label><span>Strength（每行一项）</span><textarea v-model="strengthsText" aria-label="Opportunity 优势" rows="3" /></label>
      <label><span>Red Flag（每行一项）</span><textarea v-model="redFlagsText" aria-label="Opportunity 风险" rows="3" /></label>
      <label><span>Information Needed（每行一项）</span><textarea v-model="informationText" aria-label="Opportunity 信息缺口" rows="3" /></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:9px}.opportunity-form-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.opportunity-form-grid label{display:grid;gap:6px}.opportunity-form-grid label.wide{grid-column:1/-1}.opportunity-form-grid span{color:var(--crm-text-muted);font-size:9px;font-weight:700}.opportunity-form-grid input,.opportunity-form-grid select,.opportunity-form-grid textarea{box-sizing:border-box;width:100%;padding:9px 10px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.opportunity-form-grid input,.opportunity-form-grid select{height:38px}.opportunity-form-grid textarea{resize:vertical}.opportunity-form-grid :focus{border-color:var(--crm-teal);outline:0}.intent-slider-row{display:grid;grid-template-columns:minmax(0,1fr) 28px;gap:10px;align-items:center;height:38px}.opportunity-form-grid .intent-slider-row input[type="range"]{height:22px;padding:0;background:transparent;border:0;border-radius:0;accent-color:var(--crm-teal);cursor:pointer}.opportunity-form-grid .intent-slider-row input[type="range"]:focus-visible{outline:2px solid var(--crm-teal);outline-offset:2px}.intent-slider-row output{text-align:right;color:var(--crm-text);font-size:11px;font-weight:700;font-variant-numeric:tabular-nums}.probability-preview{display:grid;grid-template-columns:1fr auto;gap:4px 10px;align-content:center;padding:8px 11px;background:var(--crm-teal-soft);border:1px solid #c3e4de;border-radius:8px}.probability-preview strong{color:var(--crm-teal);font-size:16px;font-variant-numeric:tabular-nums}.probability-preview small{grid-column:1/-1;color:var(--crm-text-muted);font-size:8px;line-height:1.45}@media(max-width:560px){.opportunity-form-grid{grid-template-columns:1fr}.opportunity-form-grid label.wide{grid-column:auto}}
.readonly-stage{display:grid;gap:6px;align-content:start}.readonly-stage span{color:var(--crm-text-muted);font-size:9px;font-weight:700}.readonly-stage strong{display:flex;height:38px;box-sizing:border-box;align-items:center;padding:0 10px;color:var(--crm-text);background:var(--crm-surface-muted);border:1px solid var(--crm-line);border-radius:8px;font-size:10px}
</style>
