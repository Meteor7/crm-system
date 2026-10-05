<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { AccountSummaryDto, ContactSummaryDto, DemoRequestFormData, DemoWaferDetailDto } from '@/types/crm'
import ContactPicker from '@/features/contacts/ContactPicker.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import { cloneDemoRequestFormData, countDemoWafers, createEmptyDemoWafer, getDemoRequestHints } from '@/domain/demo-request-form'
import { demoEngineerOwnerOptions, demoSalesOwnerOptions } from '@/demo/identities'
import { personnelDisplayName } from '@/demo/personnel'
import { useOwnOwnerOnly } from '@/stores/signed-in-user'
import { useI18n } from '@/i18n'

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
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const hints = computed(() => getDemoRequestHints(locale.value))

const draft = ref<DemoRequestFormData>(cloneDemoRequestFormData(props.modelValue))
const waferCount = computed(() => countDemoWafers(draft.value))
// A Sales user can name only themselves as the Sales contact (the server refuses anyone else).
const ownOwnerOnly = useOwnOwnerOnly()
const salesOwnerOptions = computed(() => demoSalesOwnerOptions().filter((owner) => !ownOwnerOnly.value || owner === ownOwnerOnly.value))
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
      <h3>{{ copy('Customer Information', '客户信息') }}</h3>
      <div class="field-grid">
        <label data-customer-company>{{ copy('Company Name', '公司名称') }}<RequiredMark :show="showRequiredMarks" />
          <select name="companyName" :value="accountId" :disabled="disableAccount" required @change="setAccount">
            <option value="" disabled>{{ hints.companyName }}</option>
            <option v-for="account in accounts" :key="account.id" :value="account.id">{{ account.name }}</option>
          </select>
        </label>
        <div class="contact-field" data-customer-primary-contact><span>{{ copy('Primary Contact', '主要联系人') }}<RequiredMark :show="showRequiredMarks" /></span>
          <ContactPicker :model-value="primaryContactId" :contacts="contacts" :account-id="accountId" required @update:model-value="emit('update:primaryContactId', $event)" @create="emit('create-contact')" />
          <small v-if="errors.primaryContactId" data-field-error="primaryContactId">{{ errors.primaryContactId }}</small>
        </div>
        <label>{{ copy('Contact Person', '联系人') }}
          <input name="contactPerson" :value="draft.contactPerson" :placeholder="hints.contactPerson" @input="setField('contactPerson', $event)" />
          <small v-if="errors.contactPerson" data-field-error="contactPerson">{{ errors.contactPerson }}</small>
        </label>
        <label class="full">{{ copy('Industry', '行业') }}<RequiredMark :show="showRequiredMarks" />
          <input name="industry" :value="draft.industry" :placeholder="hints.industry" @input="setField('industry', $event)" />
          <small v-if="errors.industry" data-field-error="industry">{{ errors.industry }}</small>
        </label>
      </div>
    </section>

    <section class="form-section">
      <h3>{{ copy('Owner Information', '负责人信息') }}</h3>
      <div class="field-grid">
        <label>{{ copy('Sales Contact', '销售联系人') }}<RequiredMark :show="showRequiredMarks" />
          <select name="salesContact" :value="draft.salesContact" required @change="setField('salesContact', $event)">
            <option value="" disabled>{{ locale === 'en-US' ? 'Select Sales owner' : '请选择 Sales Owner' }}</option>
            <option v-for="owner in salesOwnerOptions" :key="owner" :value="owner">{{ personnelDisplayName(owner) }}</option>
          </select>
          <small v-if="errors.salesContact" data-field-error="salesContact">{{ errors.salesContact }}</small>
        </label>
        <label>{{ copy('Demo Owner', 'Demo 负责人') }}<RequiredMark :show="showRequiredMarks" />
          <select name="demoOwner" :value="draft.demoOwner" required @change="setField('demoOwner', $event)">
            <option value="" disabled>{{ locale === 'en-US' ? 'Select Engineer owner' : '请选择 Engineer Owner' }}</option>
            <option v-for="owner in engineerOwnerOptions" :key="owner" :value="owner">{{ personnelDisplayName(owner) }}</option>
          </select>
          <small v-if="errors.demoOwner" data-field-error="demoOwner">{{ errors.demoOwner }}</small>
        </label>
      </div>
    </section>

    <section class="form-section">
      <h3>{{ copy('Sample Information', '样品信息') }}</h3>
      <div class="field-grid">
        <label>{{ copy('Number of Wafers', '晶圆数量') }}
          <output data-wafer-count>{{ waferCount }}</output>
          <span class="field-hint">{{ hints.waferCount }}</span>
        </label>
        <label>{{ copy('Size &amp; Shape', '尺寸和形状') }}<RequiredMark :show="showRequiredMarks" />
          <input name="sizeShape" :value="draft.sizeShape" :placeholder="hints.sizeShape" @input="setField('sizeShape', $event)" />
          <small v-if="errors.sizeShape" data-field-error="sizeShape">{{ errors.sizeShape }}</small>
        </label>
        <label>{{ copy('Material (Substrate)', '材料（基底）') }}<RequiredMark :show="showRequiredMarks" />
          <input name="material" :value="draft.material" :placeholder="hints.material" @input="setField('material', $event)" />
          <small v-if="errors.material" data-field-error="material">{{ errors.material }}</small>
        </label>
        <label>{{ copy('Specific Request', '具体需求') }}<RequiredMark :show="showRequiredMarks" />
          <textarea name="specificRequest" :value="draft.specificRequest" :placeholder="hints.specificRequest" @input="setField('specificRequest', $event)" />
          <small v-if="errors.specificRequest" data-field-error="specificRequest">{{ errors.specificRequest }}</small>
        </label>
      </div>
    </section>

    <section class="form-section">
      <h3>{{ copy('Demo Purpose', 'Demo 目的') }}</h3>
      <div class="field-grid">
        <label>{{ copy('What to Detect / Measure', '检测 / 测量内容') }}<RequiredMark :show="showRequiredMarks" />
          <textarea name="detectMeasure" :value="draft.detectMeasure" :placeholder="hints.detectMeasure" @input="setField('detectMeasure', $event)" />
          <small v-if="errors.detectMeasure" data-field-error="detectMeasure">{{ errors.detectMeasure }}</small>
        </label>
        <label>{{ copy('Expected Results', '预期结果') }}<RequiredMark :show="showRequiredMarks" />
          <textarea name="expectedResults" :value="draft.expectedResults" :placeholder="hints.expectedResults" @input="setField('expectedResults', $event)" />
          <small v-if="errors.expectedResults" data-field-error="expectedResults">{{ errors.expectedResults }}</small>
        </label>
      </div>
    </section>

    <section class="form-section">
      <h3>{{ copy('Our Proposal', '我们的方案') }}</h3>
      <div class="field-grid">
        <label>{{ copy('Other Tools', '其他设备') }}<RequiredMark :show="showRequiredMarks" />
          <textarea name="otherTools" :value="draft.otherTools" :placeholder="hints.otherTools" @input="setField('otherTools', $event)" />
          <small v-if="errors.otherTools" data-field-error="otherTools">{{ errors.otherTools }}</small>
        </label>
        <label>{{ copy('Primary Tool', '主要设备') }}<RequiredMark :show="showRequiredMarks" />
          <input name="primaryTool" :value="draft.primaryTool" :placeholder="hints.primaryTool" @input="setField('primaryTool', $event)" />
          <small v-if="errors.primaryTool" data-field-error="primaryTool">{{ errors.primaryTool }}</small>
        </label>
        <label>{{ copy('Complementary Tool', '辅助设备') }} <span class="optional">{{ copy('Optional', '可选') }}</span>
          <input name="complementaryTool" :value="draft.complementaryTool" :placeholder="hints.complementaryTool" @input="setField('complementaryTool', $event)" />
        </label>
        <label>{{ copy('Timing', '时间') }}<RequiredMark :show="showRequiredMarks" />
          <input name="timing" type="date" :value="draft.timing" @input="setField('timing', $event)" />
          <small v-if="errors.timing" data-field-error="timing">{{ errors.timing }}</small>
        </label>
      </div>
    </section>

    <section class="form-section">
      <h3>{{ copy('What Will Make Us Winning', '成功关键因素') }}</h3>
        <label>{{ copy('Key Success Factors', '关键成功因素') }}<RequiredMark :show="showRequiredMarks" />
        <textarea name="keySuccessFactors" :value="draft.keySuccessFactors" :placeholder="hints.keySuccessFactors" @input="setField('keySuccessFactors', $event)" />
        <small v-if="errors.keySuccessFactors" data-field-error="keySuccessFactors">{{ errors.keySuccessFactors }}</small>
      </label>
    </section>

    <section class="form-section">
      <h3>{{ copy('Open Questions', '待解决问题') }}</h3>
      <div class="field-grid">
        <label>{{ copy('Internal Questions', '内部问题') }}<RequiredMark :show="showRequiredMarks" />
          <textarea name="internalQuestions" :value="draft.internalQuestions" :placeholder="hints.internalQuestions" @input="setField('internalQuestions', $event)" />
          <small v-if="errors.internalQuestions" data-field-error="internalQuestions">{{ errors.internalQuestions }}</small>
        </label>
        <label>{{ copy('Customer Questions for Internal Team', '客户给内部团队的问题') }}<RequiredMark :show="showRequiredMarks" />
          <textarea name="customerQuestions" :value="draft.customerQuestions" :placeholder="hints.customerQuestions" @input="setField('customerQuestions', $event)" />
          <small v-if="errors.customerQuestions" data-field-error="customerQuestions">{{ errors.customerQuestions }}</small>
        </label>
      </div>
    </section>

    <section class="form-section wafer-section">
      <div class="section-heading">
         <div><h3>{{ copy('Wafer Details', '晶圆详情') }}</h3><p>{{ copy('Number of Wafers is calculated from rows containing data.', '晶圆数量根据有数据的行自动计算。') }}</p></div>
         <button class="secondary-button" data-add-wafer type="button" @click="addWafer">+ {{ copy('Add Wafer', '添加晶圆') }}</button>
      </div>
      <small v-if="errors.wafers" data-field-error="wafers">{{ errors.wafers }}</small>
      <div class="wafer-table">
        <div v-for="(wafer, index) in draft.wafers" :key="index" class="wafer-row" data-wafer-row>
           <div class="wafer-row-heading"><strong>{{ copy('Wafer', '晶圆') }} {{ index + 1 }}</strong><button v-if="draft.wafers.length > 1" type="button" :data-remove-wafer="index" @click="removeWafer(index)">{{ copy('Remove', '移除') }}</button></div>
          <div class="wafer-grid">
               <label>{{ copy('Slot ID', '槽位 ID') }}<RequiredMark :show="showRequiredMarks" /><input :name="`wafer-${index}-slotId`" :value="wafer.slotId" :placeholder="hints.slotId" @input="setWafer(index, 'slotId', $event)" /><small v-if="errors[`wafers.${index}.slotId`]" :data-field-error="`wafers.${index}.slotId`">{{ errors[`wafers.${index}.slotId`] }}</small></label>
               <label>WID<RequiredMark :show="showRequiredMarks" /><input :name="`wafer-${index}-wid`" :value="wafer.wid" :placeholder="hints.wid" @input="setWafer(index, 'wid', $event)" /><small v-if="errors[`wafers.${index}.wid`]" :data-field-error="`wafers.${index}.wid`">{{ errors[`wafers.${index}.wid`] }}</small></label>
               <label>{{ copy('Wafer Specificity', '晶圆规格') }}<RequiredMark :show="showRequiredMarks" /><input :name="`wafer-${index}-waferSpecificity`" :value="wafer.waferSpecificity" :placeholder="hints.waferSpecificity" @input="setWafer(index, 'waferSpecificity', $event)" /><small v-if="errors[`wafers.${index}.waferSpecificity`]" :data-field-error="`wafers.${index}.waferSpecificity`">{{ errors[`wafers.${index}.waferSpecificity`] }}</small></label>
               <label>{{ copy('Notch / Flat', '缺口 / 平边') }}<RequiredMark :show="showRequiredMarks" /><input :name="`wafer-${index}-notchFlat`" :value="wafer.notchFlat" :placeholder="hints.notchFlat" @input="setWafer(index, 'notchFlat', $event)" /><small v-if="errors[`wafers.${index}.notchFlat`]" :data-field-error="`wafers.${index}.notchFlat`">{{ errors[`wafers.${index}.notchFlat`] }}</small></label>
               <label>{{ copy('DOI / Metrology Items', 'DOI / 计量项目') }}<RequiredMark :show="showRequiredMarks" /><textarea :name="`wafer-${index}-doiMetrologyItems`" :value="wafer.doiMetrologyItems" :placeholder="hints.doiMetrologyItems" @input="setWafer(index, 'doiMetrologyItems', $event)" /><small v-if="errors[`wafers.${index}.doiMetrologyItems`]" :data-field-error="`wafers.${index}.doiMetrologyItems`">{{ errors[`wafers.${index}.doiMetrologyItems`] }}</small></label>
               <label>{{ copy('Result File Provided', '已提供结果文件') }}<RequiredMark :show="showRequiredMarks" /><textarea :name="`wafer-${index}-resultFileProvided`" :value="wafer.resultFileProvided" :placeholder="hints.resultFileProvided" @input="setWafer(index, 'resultFileProvided', $event)" /><small v-if="errors[`wafers.${index}.resultFileProvided`]" :data-field-error="`wafers.${index}.resultFileProvided`">{{ errors[`wafers.${index}.resultFileProvided`] }}</small></label>
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
