<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { AccountSummaryDto, ContactSummaryDto, DemoRequestFormData, DemoWaferDetailDto } from '@/types/crm'
import ContactPicker from '@/features/contacts/ContactPicker.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import { cloneDemoRequestFormData, countDemoWafers, createEmptyDemoWafer, DEMO_REQUEST_HINTS } from '@/domain/demo-request-form'
import { demoEngineerOwnerOptions, demoSalesOwnerOptions } from '@/demo/identities'
import { personnelDisplayName } from '@/demo/personnel'

const props = withDefaults(defineProps<{
  modelValue: DemoRequestFormData
  accountId: string
  accounts: AccountSummaryDto[]
  contacts?: ContactSummaryDto[]
  primaryContactId?: string
  errors?: Record<string, string>
  disableAccount?: boolean
  showRequiredMarks?: boolean
  hideCustomerInformation?: boolean
}>(), { contacts: () => [], primaryContactId: '', errors: () => ({}), disableAccount: false, showRequiredMarks: false, hideCustomerInformation: false })

const emit = defineEmits<{
  'update:modelValue': [value: DemoRequestFormData]
  'update:accountId': [value: string]
  'update:primaryContactId': [value: string]
  'create-contact': []
}>()

const draft = ref<DemoRequestFormData>(cloneDemoRequestFormData(props.modelValue))
const waferCount = computed(() => countDemoWafers(draft.value))
const salesOwnerOptions = demoSalesOwnerOptions()
const engineerOwnerOptions = demoEngineerOwnerOptions()

watch(() => props.modelValue, (value) => {
  draft.value = cloneDemoRequestFormData(value)
})

function readValue(event: Event) {
  return (event.target as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement).value
}

function setField(key: keyof Omit<DemoRequestFormData, 'wafers'>, event: Event) {
  draft.value = { ...draft.value, [key]: readValue(event) }
  emit('update:modelValue', cloneDemoRequestFormData(draft.value))
}

function setWafer(index: number, key: keyof DemoWaferDetailDto, event: Event) {
  const wafers = draft.value.wafers.map((wafer, waferIndex) => waferIndex === index ? { ...wafer, [key]: readValue(event) } : wafer)
  draft.value = { ...draft.value, wafers }
  emit('update:modelValue', cloneDemoRequestFormData(draft.value))
}

function addWafer() {
  draft.value = { ...draft.value, wafers: [...draft.value.wafers, createEmptyDemoWafer()] }
  emit('update:modelValue', cloneDemoRequestFormData(draft.value))
}

function removeWafer(index: number) {
  if (draft.value.wafers.length === 1) return
  draft.value = { ...draft.value, wafers: draft.value.wafers.filter((_, waferIndex) => waferIndex !== index) }
  emit('update:modelValue', cloneDemoRequestFormData(draft.value))
}

function setAccount(event: Event) {
  emit('update:accountId', readValue(event))
}
</script>

<template>
  <div class="request-form">
    <section v-if="!hideCustomerInformation" class="form-section" data-customer-information>
      <h3>Customer Information</h3>
      <div class="field-grid">
        <div class="contact-field"><span>Primary Contact<RequiredMark :show="showRequiredMarks" /></span>
          <ContactPicker :model-value="primaryContactId" :contacts="contacts" :account-id="accountId" required @update:model-value="emit('update:primaryContactId', $event)" @create="emit('create-contact')" />
          <small v-if="errors.primaryContactId" data-field-error="primaryContactId">{{ errors.primaryContactId }}</small>
        </div>
        <label>Company Name<RequiredMark :show="showRequiredMarks" />
          <select name="companyName" :value="accountId" :disabled="disableAccount" required @change="setAccount">
            <option value="" disabled>{{ DEMO_REQUEST_HINTS.companyName }}</option>
            <option v-for="account in accounts" :key="account.id" :value="account.id">{{ account.name }}</option>
          </select>
        </label>
        <label>Contact Person
          <input name="contactPerson" :value="draft.contactPerson" :placeholder="DEMO_REQUEST_HINTS.contactPerson" @input="setField('contactPerson', $event)" />
          <small v-if="errors.contactPerson" data-field-error="contactPerson">{{ errors.contactPerson }}</small>
        </label>
        <label class="full">Industry<RequiredMark :show="showRequiredMarks" />
          <input name="industry" :value="draft.industry" :placeholder="DEMO_REQUEST_HINTS.industry" @input="setField('industry', $event)" />
          <small v-if="errors.industry" data-field-error="industry">{{ errors.industry }}</small>
        </label>
      </div>
    </section>

    <section class="form-section">
      <h3>Owner Information</h3>
      <div class="field-grid">
        <label>Sales Contact<RequiredMark :show="showRequiredMarks" />
          <select name="salesContact" :value="draft.salesContact" required @change="setField('salesContact', $event)">
            <option value="" disabled>请选择 Sales Owner</option>
            <option v-for="owner in salesOwnerOptions" :key="owner" :value="owner">{{ personnelDisplayName(owner) }}</option>
          </select>
          <small v-if="errors.salesContact" data-field-error="salesContact">{{ errors.salesContact }}</small>
        </label>
        <label>Demo Owner<RequiredMark :show="showRequiredMarks" />
          <select name="demoOwner" :value="draft.demoOwner" required @change="setField('demoOwner', $event)">
            <option value="" disabled>请选择 Engineer Owner</option>
            <option v-for="owner in engineerOwnerOptions" :key="owner" :value="owner">{{ personnelDisplayName(owner) }}</option>
          </select>
          <small v-if="errors.demoOwner" data-field-error="demoOwner">{{ errors.demoOwner }}</small>
        </label>
      </div>
    </section>

    <section class="form-section">
      <h3>Sample Information</h3>
      <div class="field-grid">
        <label>Number of Wafers
          <output data-wafer-count>{{ waferCount }}</output>
          <span class="field-hint">{{ DEMO_REQUEST_HINTS.waferCount }}</span>
        </label>
        <label>Size &amp; Shape<RequiredMark :show="showRequiredMarks" />
          <input name="sizeShape" :value="draft.sizeShape" :placeholder="DEMO_REQUEST_HINTS.sizeShape" @input="setField('sizeShape', $event)" />
          <small v-if="errors.sizeShape" data-field-error="sizeShape">{{ errors.sizeShape }}</small>
        </label>
        <label>Material (Substrate)<RequiredMark :show="showRequiredMarks" />
          <input name="material" :value="draft.material" :placeholder="DEMO_REQUEST_HINTS.material" @input="setField('material', $event)" />
          <small v-if="errors.material" data-field-error="material">{{ errors.material }}</small>
        </label>
        <label>Specific Request<RequiredMark :show="showRequiredMarks" />
          <textarea name="specificRequest" :value="draft.specificRequest" :placeholder="DEMO_REQUEST_HINTS.specificRequest" @input="setField('specificRequest', $event)" />
          <small v-if="errors.specificRequest" data-field-error="specificRequest">{{ errors.specificRequest }}</small>
        </label>
      </div>
    </section>

    <section class="form-section">
      <h3>Demo Purpose</h3>
      <div class="field-grid">
        <label>What to Detect / Measure<RequiredMark :show="showRequiredMarks" />
          <textarea name="detectMeasure" :value="draft.detectMeasure" :placeholder="DEMO_REQUEST_HINTS.detectMeasure" @input="setField('detectMeasure', $event)" />
          <small v-if="errors.detectMeasure" data-field-error="detectMeasure">{{ errors.detectMeasure }}</small>
        </label>
        <label>Expected Results<RequiredMark :show="showRequiredMarks" />
          <textarea name="expectedResults" :value="draft.expectedResults" :placeholder="DEMO_REQUEST_HINTS.expectedResults" @input="setField('expectedResults', $event)" />
          <small v-if="errors.expectedResults" data-field-error="expectedResults">{{ errors.expectedResults }}</small>
        </label>
      </div>
    </section>

    <section class="form-section">
      <h3>Our Proposal</h3>
      <div class="field-grid">
        <label>Other Tools<RequiredMark :show="showRequiredMarks" />
          <textarea name="otherTools" :value="draft.otherTools" :placeholder="DEMO_REQUEST_HINTS.otherTools" @input="setField('otherTools', $event)" />
          <small v-if="errors.otherTools" data-field-error="otherTools">{{ errors.otherTools }}</small>
        </label>
        <label>Primary Tool<RequiredMark :show="showRequiredMarks" />
          <input name="primaryTool" :value="draft.primaryTool" :placeholder="DEMO_REQUEST_HINTS.primaryTool" @input="setField('primaryTool', $event)" />
          <small v-if="errors.primaryTool" data-field-error="primaryTool">{{ errors.primaryTool }}</small>
        </label>
        <label>Complementary Tool <span class="optional">Optional</span>
          <input name="complementaryTool" :value="draft.complementaryTool" :placeholder="DEMO_REQUEST_HINTS.complementaryTool" @input="setField('complementaryTool', $event)" />
        </label>
        <label>Timing<RequiredMark :show="showRequiredMarks" />
          <input name="timing" type="date" :value="draft.timing" @input="setField('timing', $event)" />
          <small v-if="errors.timing" data-field-error="timing">{{ errors.timing }}</small>
        </label>
      </div>
    </section>

    <section class="form-section">
      <h3>What Will Make Us Winning</h3>
        <label>Key Success Factors<RequiredMark :show="showRequiredMarks" />
        <textarea name="keySuccessFactors" :value="draft.keySuccessFactors" :placeholder="DEMO_REQUEST_HINTS.keySuccessFactors" @input="setField('keySuccessFactors', $event)" />
        <small v-if="errors.keySuccessFactors" data-field-error="keySuccessFactors">{{ errors.keySuccessFactors }}</small>
      </label>
    </section>

    <section class="form-section">
      <h3>Open Questions</h3>
      <div class="field-grid">
        <label>Internal Questions<RequiredMark :show="showRequiredMarks" />
          <textarea name="internalQuestions" :value="draft.internalQuestions" :placeholder="DEMO_REQUEST_HINTS.internalQuestions" @input="setField('internalQuestions', $event)" />
          <small v-if="errors.internalQuestions" data-field-error="internalQuestions">{{ errors.internalQuestions }}</small>
        </label>
        <label>Customer Questions for Internal Team<RequiredMark :show="showRequiredMarks" />
          <textarea name="customerQuestions" :value="draft.customerQuestions" :placeholder="DEMO_REQUEST_HINTS.customerQuestions" @input="setField('customerQuestions', $event)" />
          <small v-if="errors.customerQuestions" data-field-error="customerQuestions">{{ errors.customerQuestions }}</small>
        </label>
      </div>
    </section>

    <section class="form-section wafer-section">
      <div class="section-heading">
        <div><h3>Wafer Details</h3><p>Number of Wafers is calculated from rows containing data.</p></div>
        <button class="secondary-button" data-add-wafer type="button" @click="addWafer">+ Add Wafer</button>
      </div>
      <small v-if="errors.wafers" data-field-error="wafers">{{ errors.wafers }}</small>
      <div class="wafer-table">
        <div v-for="(wafer, index) in draft.wafers" :key="index" class="wafer-row" data-wafer-row>
          <div class="wafer-row-heading"><strong>Wafer {{ index + 1 }}</strong><button v-if="draft.wafers.length > 1" type="button" :data-remove-wafer="index" @click="removeWafer(index)">Remove</button></div>
          <div class="wafer-grid">
              <label>Slot ID<RequiredMark :show="showRequiredMarks" /><input :name="`wafer-${index}-slotId`" :value="wafer.slotId" :placeholder="DEMO_REQUEST_HINTS.slotId" @input="setWafer(index, 'slotId', $event)" /><small v-if="errors[`wafers.${index}.slotId`]" :data-field-error="`wafers.${index}.slotId`">{{ errors[`wafers.${index}.slotId`] }}</small></label>
              <label>WID<RequiredMark :show="showRequiredMarks" /><input :name="`wafer-${index}-wid`" :value="wafer.wid" :placeholder="DEMO_REQUEST_HINTS.wid" @input="setWafer(index, 'wid', $event)" /><small v-if="errors[`wafers.${index}.wid`]" :data-field-error="`wafers.${index}.wid`">{{ errors[`wafers.${index}.wid`] }}</small></label>
              <label>Wafer Specificity<RequiredMark :show="showRequiredMarks" /><input :name="`wafer-${index}-waferSpecificity`" :value="wafer.waferSpecificity" :placeholder="DEMO_REQUEST_HINTS.waferSpecificity" @input="setWafer(index, 'waferSpecificity', $event)" /><small v-if="errors[`wafers.${index}.waferSpecificity`]" :data-field-error="`wafers.${index}.waferSpecificity`">{{ errors[`wafers.${index}.waferSpecificity`] }}</small></label>
              <label>Notch / Flat<RequiredMark :show="showRequiredMarks" /><input :name="`wafer-${index}-notchFlat`" :value="wafer.notchFlat" :placeholder="DEMO_REQUEST_HINTS.notchFlat" @input="setWafer(index, 'notchFlat', $event)" /><small v-if="errors[`wafers.${index}.notchFlat`]" :data-field-error="`wafers.${index}.notchFlat`">{{ errors[`wafers.${index}.notchFlat`] }}</small></label>
              <label>DOI / Metrology Items<RequiredMark :show="showRequiredMarks" /><textarea :name="`wafer-${index}-doiMetrologyItems`" :value="wafer.doiMetrologyItems" :placeholder="DEMO_REQUEST_HINTS.doiMetrologyItems" @input="setWafer(index, 'doiMetrologyItems', $event)" /><small v-if="errors[`wafers.${index}.doiMetrologyItems`]" :data-field-error="`wafers.${index}.doiMetrologyItems`">{{ errors[`wafers.${index}.doiMetrologyItems`] }}</small></label>
              <label>Result File Provided<RequiredMark :show="showRequiredMarks" /><textarea :name="`wafer-${index}-resultFileProvided`" :value="wafer.resultFileProvided" :placeholder="DEMO_REQUEST_HINTS.resultFileProvided" @input="setWafer(index, 'resultFileProvided', $event)" /><small v-if="errors[`wafers.${index}.resultFileProvided`]" :data-field-error="`wafers.${index}.resultFileProvided`">{{ errors[`wafers.${index}.resultFileProvided`] }}</small></label>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.request-form{display:grid;gap:14px}.form-section{display:grid;gap:11px;padding:14px;background:#FAF8F5;border:1px solid var(--crm-line);border-radius:11px}.form-section h3{margin:0;color:var(--crm-navy);font-size:12px}.field-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.full{grid-column:1/-1}.request-form label,.contact-field{display:grid;gap:6px;color:var(--crm-text-muted);font-size:9px;font-weight:700}.request-form input,.request-form select,.request-form textarea,.request-form output{width:100%;min-height:38px;padding:9px 10px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:8px;outline:0;font:inherit;font-size:10px}.request-form textarea{min-height:72px;resize:vertical}.request-form output{display:flex;align-items:center;color:var(--crm-navy);font-weight:800}.request-form input:focus,.request-form select:focus,.request-form textarea:focus{border-color:var(--crm-teal)}.request-form input::placeholder,.request-form textarea::placeholder{color:#9aa6a8;opacity:1;font-weight:400}.field-hint{color:#9aa6a8;font-size:8px;font-weight:400}.optional{color:var(--crm-teal);font-size:8px}.request-form small{color:#b64545;font-size:8px;font-weight:600}.section-heading,.wafer-row-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.section-heading p{margin:4px 0 0;color:var(--crm-text-muted);font-size:8px}.wafer-table{display:grid;gap:10px}.wafer-row{display:grid;gap:9px;padding:12px;background:#fff;border:1px solid var(--crm-line);border-radius:9px}.wafer-row-heading strong{color:var(--crm-navy);font-size:9px}.wafer-row-heading button{padding:3px 6px;color:#b64545;background:transparent;border:0;font-size:8px;cursor:pointer}.wafer-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.secondary-button{white-space:nowrap}@media(max-width:700px){.field-grid,.wafer-grid{grid-template-columns:1fr}.full{grid-column:auto}.section-heading{align-items:flex-start;flex-direction:column}}
.form-section:first-child .field-grid>label:nth-child(3){display:none}
</style>
