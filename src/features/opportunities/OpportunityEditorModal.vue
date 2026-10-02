<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import PersonnelSelect from '@/design-system/PersonnelSelect.vue'
import AccountSegmentSelect from '@/features/accounts/AccountSegmentSelect.vue'
import { EQUIPMENT_PRESETS } from '@/domain/equipment'
import { preferredPersonnelId } from '@/demo/personnel'
import { OPPORTUNITY_PROBABILITY_LEVELS, opportunityProbabilityLevelLabel, opportunityProbabilityLevelRank } from '@/domain/opportunity-probability'
import { isClosedOpportunityStage, opportunityStageLabel } from '@/domain/opportunity-stages'
import type { AccountSummaryDto, SiteDto } from '@/types/crm'
import type { CreateStrategyOpportunityInput, StrategyOpportunityDto } from '@/types/workspaces'
import { useI18n, useLocaleMessage } from '@/i18n'
import { salesEnumLabel } from '@/features/shared/sales-i18n'

const props = defineProps<{
  opportunity?: StrategyOpportunityDto | null
  accounts: AccountSummaryDto[]
  sitesByAccount: Record<string, SiteDto[]>
  defaultOwner: string
  /** The signed-in user; only the Opportunity owner may set the success probability. */
  currentUserId?: string
  /** Equipment type options from listEquipmentTypes; the presets until they load. */
  equipmentTypes?: readonly string[]
  busy?: boolean
  error?: string
}>()
const emit = defineEmits<{ close: []; submit: [value: CreateStrategyOpportunityInput] }>()
const { t, locale, message } = useI18n()

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
  amount: props.opportunity?.amount ?? '',
  intentScore: props.opportunity?.score ?? 50,
  probabilityLevel: props.opportunity?.probabilityLevel ?? '',
  poDate: props.opportunity?.poDate ?? '2026-10-31',
  toolType: props.opportunity?.toolType ?? '',
  saleType: normalizeSaleType(props.opportunity?.saleType),
  subRegion: props.opportunity?.subRegion ?? firstAccount?.region ?? 'East China',
  currency: props.opportunity?.currency ?? 'CNY',
  originalAmount: props.opportunity?.originalAmount ?? props.opportunity?.amount ?? '',
  amountCny: props.opportunity?.amountCny ?? '',
  shipmentDate: props.opportunity?.shipmentDate ?? '',
  fatDate: props.opportunity?.fatDate ?? '',
  paymentMilestones: props.opportunity?.paymentMilestones ?? [],
  competition: props.opportunity?.competition ?? '',
  singleSalesObjective: props.opportunity?.singleSalesObjective ?? '',
  winReason: props.opportunity?.winReason ?? '',
  lostReason: props.opportunity?.lostReason ?? '',
  strengths: props.opportunity?.strengths ?? [],
  redFlags: props.opportunity?.redFlags ?? [],
  informationNeeded: props.opportunity?.informationNeeded ?? [],
})
const sites = computed(() => props.sitesByAccount[form.value.accountId] ?? [])
// No opportunity prop = creating a new one, which always starts at stage 1 (amount optional).
// An existing opportunity requires the amount once it has left stage 1; a deal lost at stage 1 never did.
const reachedStage = computed(() => props.opportunity?.stage === 'lost' && props.opportunity.lostAtStage ? props.opportunity.lostAtStage : props.opportunity?.stage)
const amountRequired = computed(() => !!props.opportunity && reachedStage.value !== 'qualified_opportunity')
// Past stage 1, an Opportunity without a CNY amount (older ones in another currency, or one that advanced
// before anyone entered it) must get one before saving.
const amountCnyMissing = computed(() => amountRequired.value && !props.opportunity?.amountCny)
const paymentText = ref((form.value.paymentMilestones ?? []).join('\n'))
const strengthsText = ref((form.value.strengths ?? []).join('\n'))
const redFlagsText = ref((form.value.redFlags ?? []).join('\n'))
const informationText = ref((form.value.informationNeeded ?? []).join('\n'))
// Every new Opportunity starts at the first milestone; afterwards the stage moves only through workflow actions.
const currentStage = computed(() => props.opportunity?.stage ?? 'qualified_opportunity')
const qualificationConfirmed = ref(false)
const qualificationError = useLocaleMessage()
// The server's limit on the trimmed objective, counted in characters (not UTF-16 units), so a native maxlength cannot stand in for it.
const MAX_OBJECTIVE_LENGTH = 2000
const objectiveError = useLocaleMessage()
watch(() => form.value.singleSalesObjective, () => { objectiveError.value = '' })
// Purchase intent stays independent of the level.
const isLevelOwner = computed(() => Boolean(props.currentUserId) && props.opportunity?.owner === props.currentUserId)
// The level is frozen once the PO is received or the Opportunity is lost.
const levelFrozen = computed(() => isClosedOpportunityStage(currentStage.value))
// Whoever opens an Opportunity sets its first level, a Manager opening one for Sales included; after that only the owner changes it.
const canSetProbabilityLevel = computed(() => !props.opportunity || (isLevelOwner.value && !levelFrozen.value))
// Empty only survives on an Opportunity from before the levels, and nothing can return to it.
const originalLevel = props.opportunity?.probabilityLevel ?? ''
const lowersLevel = computed(() => Boolean(originalLevel)
  && opportunityProbabilityLevelRank(form.value.probabilityLevel ?? '') < opportunityProbabilityLevelRank(originalLevel))
const probabilityReason = ref('')
const probabilityActionPlan = ref('')
const planError = useLocaleMessage()
const levelError = useLocaleMessage()
const reasonError = useLocaleMessage()
watch(() => form.value.probabilityLevel, () => { levelError.value = '' })
watch(probabilityReason, () => { reasonError.value = '' })
watch(probabilityActionPlan, () => { planError.value = '' })
watch(qualificationConfirmed, (confirmed) => {
  if (confirmed) qualificationError.value = ''
})

watch(() => form.value.accountId, (accountId) => {
  const account = props.accounts.find((item) => item.id === accountId)
  form.value.siteId = props.sitesByAccount[accountId]?.[0]?.id ?? ''
  if (account) form.value.subRegion = account.region
})

function lines(value: string) { return value.split('\n').map((item) => item.trim()).filter(Boolean) }
function submit() {
  // A stored objective that is already longer (Frappe's HTML cleaning can lengthen one) is sent back as it was
  // without complaint; only a changed one is held to the limit, as the server does.
  const objective = (form.value.singleSalesObjective ?? '').trim()
  if (objective !== (props.opportunity?.singleSalesObjective ?? '').trim() && Array.from(objective).length > MAX_OBJECTIVE_LENGTH) {
    objectiveError.value = message('oppEditor.objectiveTooLong')
    return
  }
  if (!props.opportunity && !qualificationConfirmed.value) {
    qualificationError.value = message('oppEditor.qualificationRequired')
    return
  }
  if (!props.opportunity && !form.value.probabilityLevel) {
    levelError.value = message('oppEditor.probabilityLevelRequired')
    return
  }
  if (lowersLevel.value && !probabilityReason.value.trim()) {
    reasonError.value = message('oppEditor.probabilityReasonRequired')
    return
  }
  if (lowersLevel.value && (!probabilityActionPlan.value.trim() || probabilityActionPlan.value.trim().length > 4000)) {
    planError.value = message('oppEditor.probabilityPlanRequired')
    return
  }
  const { probabilityLevel, ...fields } = form.value
  const value: CreateStrategyOpportunityInput = {
    ...fields,
    // Without an amount (allowed at stage 1) the original amount goes out blank too, never a stale one beside an unknown amount.
    amount: form.value.amount, intentScore: Number(form.value.intentScore), originalAmount: form.value.amount ? form.value.originalAmount || form.value.amount : '',
    paymentMilestones: lines(paymentText.value), strengths: lines(strengthsText.value), redFlags: lines(redFlagsText.value), informationNeeded: lines(informationText.value),
  }
  // A non-owner or frozen edit leaves the level untouched.
  if (canSetProbabilityLevel.value) value.probabilityLevel = probabilityLevel ?? ''
  if (lowersLevel.value) {
    value.probabilityReason = probabilityReason.value.trim()
    value.probabilityActionPlan = probabilityActionPlan.value.trim()
  }
  if (!props.opportunity) value.qualificationConfirmed = true
  emit('submit', value)
}

const equipmentChoices = computed(() => props.equipmentTypes ?? EQUIPMENT_PRESETS)
</script>

<template>
  <ModalShell :title="opportunity ? t('oppEditor.edit') : t('oppEditor.new')" eyebrow="OPPORTUNITY STRATEGY" :busy="busy" @close="$emit('close')" @submit="submit">
    <p v-if="error" class="form-error">{{ error }}</p>
    <div class="opportunity-form-grid">
      <div v-if="!opportunity" class="wide qualification-field" data-testid="qualification-confirmed-field">
        <label class="qualification-check"><input v-model="qualificationConfirmed" type="checkbox" :aria-label="t('oppEditor.qualificationConfirmed')" data-testid="qualification-confirmed" required /><span>{{ t('oppEditor.qualificationConfirmed') }}<RequiredMark /></span></label>
        <small v-if="qualificationError" data-field-error="qualificationConfirmed">{{ qualificationError }}</small>
      </div>
      <label class="wide"><span>{{ t('oppEditor.name') }}<RequiredMark :show="!opportunity" /></span><input v-model="form.title" :aria-label="t('oppEditor.name')" required /></label>
      <label><span>{{ t('oppEditor.account') }}<RequiredMark :show="!opportunity" /></span><select v-model="form.accountId" :aria-label="t('oppEditor.account')" required><option value="" disabled>{{ t('quotations.selectAccount') }}</option><option v-for="account in accounts" :key="account.id" :value="account.id">{{ account.shortName }} · {{ account.name }}</option></select></label>
      <label><span>{{ t('oppEditor.site') }}<RequiredMark :show="!opportunity" /></span><select v-model="form.siteId" :aria-label="t('oppEditor.site')" required><option v-for="site in sites" :key="site.id" :value="site.id">{{ site.name }}</option></select></label>
      <label><span>{{ t('oppEditor.owner') }}<RequiredMark :show="!opportunity" /></span><PersonnelSelect v-model="form.owner" :roles="['Sales', 'Manager']" :ariaLabel="t('oppEditor.owner')" required /></label>
      <div class="readonly-stage"><span>{{ t('oppEditor.stage') }}</span><strong>{{ opportunityStageLabel(currentStage, locale) }}</strong></div>
      <label class="probability-level-field">
        <span>{{ t('oppEditor.probabilityLevel') }}<RequiredMark :show="!opportunity" /></span>
        <select v-model="form.probabilityLevel" :aria-label="t('oppEditor.probabilityLevel')" :disabled="!canSetProbabilityLevel" :required="!opportunity" data-testid="opportunity-probability-level">
          <option v-if="!originalLevel" value="" disabled>{{ opportunity ? opportunityProbabilityLevelLabel('', locale) : t('oppEditor.probabilityLevelRequired') }}</option>
          <option v-for="level in OPPORTUNITY_PROBABILITY_LEVELS" :key="level" :value="level">{{ opportunityProbabilityLevelLabel(level, locale) }}</option>
        </select>
        <small v-if="levelError" class="field-error" data-field-error="probabilityLevel">{{ levelError }}</small>
        <small v-else-if="opportunity && !isLevelOwner" data-testid="opportunity-probability-level-owner-only">{{ t('oppEditor.probabilityLevelOwnerOnly') }}</small>
        <small v-else-if="levelFrozen" data-testid="opportunity-probability-level-frozen">{{ t('oppEditor.probabilityLevelFrozen') }}</small>
      </label>
      <label class="intent-field">
        <span>{{ t('oppEditor.intent') }}</span>
        <div class="intent-slider-row">
          <input
            v-model.number="form.intentScore"
            :aria-label="t('oppEditor.intent')"
            type="range"
            min="0"
            max="100"
            step="1"
          />
          <output data-testid="opportunity-intent-value">{{ form.intentScore }}</output>
        </div>
      </label>
      <label v-if="lowersLevel" class="wide probability-reason-field">
        <span>{{ t('oppEditor.probabilityReason') }}<RequiredMark /></span>
        <textarea v-model="probabilityReason" :aria-label="t('oppEditor.probabilityReason')" rows="2" data-testid="opportunity-probability-reason" required />
        <small v-if="reasonError" class="field-error" data-field-error="probabilityReason">{{ reasonError }}</small>
      </label>
      <label v-if="lowersLevel" class="wide probability-reason-field">
        <span>{{ t('oppEditor.probabilityActionPlan') }}<RequiredMark /></span>
        <textarea v-model="probabilityActionPlan" :aria-label="t('oppEditor.probabilityActionPlan')" rows="3" maxlength="4000" data-testid="opportunity-probability-plan" required />
        <small v-if="planError" class="field-error" data-field-error="probabilityActionPlan">{{ planError }}</small>
      </label>
      <label><span>{{ t('oppEditor.amount') }}</span><input v-model="form.amount" :aria-label="t('oppEditor.amount')" type="text" inputmode="decimal" min="0.01" pattern="\d+(?:\.\d{1,2})?" :required="amountRequired" /></label>
      <label><span>{{ t('oppEditor.currency') }}<RequiredMark :show="!opportunity" /></span><select v-model="form.currency" :aria-label="t('oppEditor.currency')" required><option>CNY</option><option>USD</option><option>EUR</option></select></label>
      <label><span>{{ t('oppEditor.originalAmount') }}</span><input v-model="form.originalAmount" :aria-label="t('oppEditor.originalAmount')" type="text" inputmode="decimal" pattern="\d+(?:\.\d{1,2})?" /></label>
      <label class="amount-cny-field"><span>{{ t('oppEditor.amountCny') }}</span><input v-model="form.amountCny" :aria-label="t('oppEditor.amountCny')" type="text" inputmode="decimal" pattern="\d+(?:\.\d{1,2})?" :required="amountRequired" /><small v-if="amountCnyMissing" data-testid="opportunity-amount-cny-missing">{{ t('oppEditor.amountCnyMissing') }}</small></label>
      <label><span>{{ t('oppEditor.poDate') }}<RequiredMark :show="!opportunity" /></span><input v-model="form.poDate" :aria-label="t('oppEditor.poDate')" type="date" required /></label>
      <label><span>{{ t('oppEditor.toolType') }}<RequiredMark :show="!opportunity" /></span><AccountSegmentSelect v-model="form.toolType" :segments="equipmentChoices" :label="t('oppEditor.toolType')" :custom-option-label="locale === 'en-US' ? '+ Custom equipment type' : '＋自定义设备类型'" :custom-input-label="t('oppEditor.toolType')" :custom-placeholder="locale === 'en-US' ? 'Enter a custom equipment type' : '请输入自定义设备类型'" :empty-placeholder="locale === 'en-US' ? 'Select equipment type' : '请选择设备类型'" :custom-on-empty="false" required /></label>
      <label><span>{{ t('oppEditor.saleType') }}<RequiredMark :show="!opportunity" /></span><select v-model="form.saleType" :aria-label="t('oppEditor.saleType')" required><option v-for="saleType in SALE_TYPE_OPTIONS" :key="saleType" :value="saleType">{{ salesEnumLabel(saleType, locale) }}</option></select></label>
      <label><span>{{ t('oppEditor.shipmentDate') }}</span><input v-model="form.shipmentDate" :aria-label="t('oppEditor.shipmentDate')" type="date" /></label>
      <label><span>{{ t('oppEditor.fatDate') }}</span><input v-model="form.fatDate" :aria-label="t('oppEditor.fatDate')" type="date" /></label>
      <label class="wide"><span>{{ t('oppEditor.competition') }}</span><input v-model="form.competition" :aria-label="t('oppEditor.competition')" /></label>
      <label class="wide"><span>{{ t('oppEditor.singleSalesObjective') }}</span><textarea v-model="form.singleSalesObjective" :aria-label="t('oppEditor.singleSalesObjective')" rows="3" /><small v-if="objectiveError" class="field-error" data-field-error="singleSalesObjective">{{ objectiveError }}</small></label>
      <label><span>{{ t('oppEditor.payment') }}</span><textarea v-model="paymentText" :aria-label="t('oppEditor.payment')" rows="3" /></label>
      <label><span>{{ t('oppEditor.strength') }}</span><textarea v-model="strengthsText" :aria-label="t('oppEditor.strength')" rows="3" /></label>
      <label><span>{{ t('oppEditor.redFlag') }}</span><textarea v-model="redFlagsText" :aria-label="t('oppEditor.redFlag')" rows="3" /></label>
      <label><span>{{ t('oppEditor.infoNeeded') }}</span><textarea v-model="informationText" :aria-label="t('oppEditor.infoNeeded')" rows="3" /></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:9px}.opportunity-form-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.opportunity-form-grid label{display:grid;gap:6px}.opportunity-form-grid label.wide,.opportunity-form-grid .wide{grid-column:1/-1}.opportunity-form-grid span{color:var(--crm-text-muted);font-size:9px;font-weight:700}.opportunity-form-grid input,.opportunity-form-grid select,.opportunity-form-grid textarea{box-sizing:border-box;width:100%;padding:9px 10px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.opportunity-form-grid input,.opportunity-form-grid select{height:38px}.opportunity-form-grid textarea{resize:vertical}.opportunity-form-grid :focus{border-color:var(--crm-teal);outline:0}.intent-slider-row{display:grid;grid-template-columns:minmax(0,1fr) 28px;gap:10px;align-items:center;height:38px}.opportunity-form-grid .intent-slider-row input[type="range"]{height:22px;padding:0;background:transparent;border:0;border-radius:0;accent-color:var(--crm-teal);cursor:pointer}.opportunity-form-grid .intent-slider-row input[type="range"]:focus-visible{outline:2px solid var(--crm-teal);outline-offset:2px}.intent-slider-row output{text-align:right;color:var(--crm-text);font-size:11px;font-weight:700;font-variant-numeric:tabular-nums}.opportunity-form-grid select:disabled{color:var(--crm-text-muted);background:var(--crm-surface-muted);cursor:not-allowed}.probability-level-field small{color:var(--crm-text-muted);font-size:8px;line-height:1.45}@media(max-width:560px){.opportunity-form-grid{grid-template-columns:1fr}.opportunity-form-grid label.wide,.opportunity-form-grid .wide{grid-column:auto}}
.readonly-stage{display:grid;gap:6px;align-content:start}.readonly-stage span{color:var(--crm-text-muted);font-size:9px;font-weight:700}.readonly-stage strong{display:flex;height:38px;box-sizing:border-box;align-items:center;padding:0 10px;color:var(--crm-text);background:var(--crm-surface-muted);border:1px solid var(--crm-line);border-radius:8px;font-size:10px}
.opportunity-form-grid small.field-error{color:var(--crm-danger);font-size:8px;line-height:1.45}
.amount-cny-field small{color:var(--crm-warning,#9a6700);font-size:8px;line-height:1.45}
.qualification-field{display:grid;gap:5px;padding:10px 12px;background:var(--crm-teal-soft);border-radius:9px}.opportunity-form-grid .qualification-check{display:flex;align-items:center;gap:8px;cursor:pointer}.opportunity-form-grid .qualification-check input{width:16px;height:16px;flex:0 0 auto;margin:0;padding:0;accent-color:var(--crm-teal)}.opportunity-form-grid .qualification-check span{color:var(--crm-text);font-size:10px}.qualification-field small{color:var(--crm-danger);font-size:8px}
</style>
