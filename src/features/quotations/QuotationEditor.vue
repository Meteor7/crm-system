<script setup lang="ts">
import { computed } from 'vue'
import { Plus, Trash2 } from '@lucide/vue'
import SectionCard from '@/design-system/SectionCard.vue'
import type { ContactSummaryDto, SiteDto } from '@/types/crm'
import type { QuotationCatalogItemDto, QuotationDiscountType, QuotationDraftInput, QuotationItemDto, QuotationPricingMode, QuotationType } from './types'
import QuotationCatalogFilter from './QuotationCatalogFilter.vue'
import QuotationPicker from './QuotationPicker.vue'

const props = withDefaults(defineProps<{
  modelValue: QuotationDraftInput
  contacts: ContactSummaryDto[]
  sites: SiteDto[]
  quotationType: QuotationType
  catalog?: QuotationCatalogItemDto[]
  catalogError?: string
  readonly?: boolean
}>(), { catalog: () => [], catalogError: '', readonly: false })
const emit = defineEmits<{ 'update:modelValue': [value: QuotationDraftInput]; changed: [] }>()
const model = computed({ get: () => props.modelValue, set: (value: QuotationDraftInput) => emit('update:modelValue', value) })
const discountTypes: { value: QuotationDiscountType; label: string }[] = [
  { value: 'None', label: '无折扣' }, { value: 'Percentage', label: '百分比' }, { value: 'Fixed Amount', label: '固定金额' },
]
const pricingModeOptions: { value: QuotationPricingMode; label: string }[] = [
  { value: 'Included', label: 'Included' }, { value: 'Charged', label: 'Charged' },
]
const paymentDescriptions = [
  (value: string) => `收到订单1周内，买方电汇方式支付订单总价${value}%作为预付款。`,
  (value: string) => `发货前两周内，买方电汇方式支付订单总价${value}%作为发货款。`,
  (value: string) => `设备验收完成后两周内，支付订单总价${value}%，发货之后两个月之内组织验收。`,
  (value: string) => `设备发货之后一年，买方付${value}% PO的尾款。`,
]
const fixedServices = [
  'Installation, 5 days – included', 'Maintenance training, 5 days /4 EE – included',
  'Application training: 5 days /4 PE – included', 'Operator training: 2 days/ 3 operators – included',
  'Documentation(manual printout on cleanroom paper) – included', 'Packing in stretched foil, alupack film and wooden crates – included',
]

function touch() {
  emit('update:modelValue', JSON.parse(JSON.stringify(model.value)) as QuotationDraftInput)
  emit('changed')
}
const contactOptions = computed(() => props.contacts.map((item) => ({ value: item.id, label: [item.name, item.title].filter(Boolean).join(' · ') })))
const siteOptions = computed(() => props.sites.map((item) => ({ value: item.id, label: item.name })))
const devices = computed(() => model.value.items.filter((item) => item.lineType === 'Device'))
const systems = (deviceKey: string) => model.value.items.filter((item) => item.lineType === 'System' && item.parentDeviceKey === deviceKey)
const accessories = (systemKey: string) => model.value.items.filter((item) => item.lineType === 'Accessory' && item.parentSystemKey === systemKey)
const legacyAccessories = (deviceKey: string) => model.value.items.filter((item) => item.lineType === 'Accessory' && item.parentDeviceKey === deviceKey && !item.parentSystemKey)
const catalogDevices = computed(() => props.catalog.filter((item) => item.level === 'Device'))
const catalogSystems = (device: QuotationItemDto) => props.catalog.filter((item) => item.level === 'System' && item.parentId === device.catalogItemId)
const catalogAccessories = (system: QuotationItemDto) => props.catalog.filter((item) => item.level === 'Accessory' && item.parentId === system.catalogItemId)
const selectedDeviceIds = computed(() => devices.value.map((item) => item.catalogItemId || '').filter(Boolean))
const selectedSystemIds = (deviceKey: string) => systems(deviceKey).map((item) => item.catalogItemId || '').filter(Boolean)
const selectedAccessoryIds = (systemKey: string) => accessories(systemKey).map((item) => item.catalogItemId || '').filter(Boolean)

function key(prefix: string) { return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}` }
function line(lineType: 'Device' | 'System' | 'Accessory', name: string, catalogItemId = '', parentDeviceKey = '', parentSystemKey = ''): QuotationItemDto {
  return {
    lineKey: key(lineType.toLowerCase()), lineType, parentDeviceKey, parentSystemKey, catalogItemId,
    name, model: '', description: '', pricingMode: lineType === 'Accessory' ? 'Included' : lineType === 'System' ? 'Included' : 'Charged',
    quantity: 1, unitPrice: '0.00', lineAmount: '0.00',
  }
}
function duplicateName(items: QuotationItemDto[], name: string) {
  const normalized = name.trim().replace(/\s+/g, ' ').toLocaleLowerCase()
  return items.some((item) => item.name.trim().replace(/\s+/g, ' ').toLocaleLowerCase() === normalized)
}
function addServiceItem() { model.value.items.push(line('Device', 'New Service Item')); touch() }
function addDevice(item: QuotationCatalogItemDto) {
  if (selectedDeviceIds.value.includes(item.id)) return
  model.value.items.push(line('Device', item.name, item.id)); touch()
}
function addCustomDevice(name: string) {
  if (duplicateName(devices.value, name)) return
  model.value.items.push(line('Device', name)); touch()
}
function addSystem(device: QuotationItemDto, item: QuotationCatalogItemDto) {
  if (selectedSystemIds(device.lineKey).includes(item.id)) return
  insertSystem(device, line('System', item.name, item.id, device.lineKey)); touch()
}
function addCustomSystem(device: QuotationItemDto, name: string) {
  if (duplicateName(systems(device.lineKey), name)) return
  insertSystem(device, line('System', name, '', device.lineKey)); touch()
}
function insertSystem(device: QuotationItemDto, system: QuotationItemDto) {
  const deviceIndex = model.value.items.findIndex((item) => item.lineKey === device.lineKey)
  const nextDevice = model.value.items.findIndex((item, index) => index > deviceIndex && item.lineType === 'Device')
  model.value.items.splice(nextDevice < 0 ? model.value.items.length : nextDevice, 0, system)
}
function addAccessory(system: QuotationItemDto, item: QuotationCatalogItemDto) {
  if (selectedAccessoryIds(system.lineKey).includes(item.id)) return
  insertAccessory(system, line('Accessory', item.name, item.id, system.parentDeviceKey, system.lineKey)); touch()
}
function addCustomAccessory(system: QuotationItemDto, name: string) {
  if (duplicateName(accessories(system.lineKey), name)) return
  insertAccessory(system, line('Accessory', name, '', system.parentDeviceKey, system.lineKey)); touch()
}
function insertAccessory(system: QuotationItemDto, accessory: QuotationItemDto) {
  const systemIndex = model.value.items.findIndex((item) => item.lineKey === system.lineKey)
  const nextGroup = model.value.items.findIndex((item, index) => index > systemIndex && (item.lineType === 'Device' || item.lineType === 'System'))
  model.value.items.splice(nextGroup < 0 ? model.value.items.length : nextGroup, 0, accessory)
}
function removeLine(item: QuotationItemDto) {
  if (item.lineType === 'Device') model.value.items = model.value.items.filter((lineItem) => lineItem.lineKey !== item.lineKey && lineItem.parentDeviceKey !== item.lineKey)
  else if (item.lineType === 'System') model.value.items = model.value.items.filter((lineItem) => lineItem.lineKey !== item.lineKey && lineItem.parentSystemKey !== item.lineKey)
  else model.value.items = model.value.items.filter((lineItem) => lineItem.lineKey !== item.lineKey)
  touch()
}
function setAccessoryPricingMode(accessory: QuotationItemDto, value: string) {
  if (value !== 'Included' && value !== 'Charged') return
  accessory.pricingMode = value; touch()
}
function setDiscountType(value: QuotationDiscountType) {
  if (props.readonly || model.value.discountType === value) return
  model.value.discountType = value
  if (value === 'None') model.value.discountValue = '0.00'
  touch()
}
</script>

<template>
  <div class="quotation-editor" @input="touch" @change="touch">
    <SectionCard title="客户与报价信息" eyebrow="HEADER">
      <div class="form-grid four">
        <label><span>ATTN</span><QuotationPicker v-model="model.primaryContactId" :options="contactOptions" placeholder="请选择联系人" label="ATTN" test-id="quotation-contact-select" :disabled="readonly" @change="touch" /></label>
        <label><span>地址 / Site</span><QuotationPicker v-model="model.addressId" :options="siteOptions" placeholder="请选择地址" label="地址 / Site" test-id="quotation-site-select" :disabled="readonly" @change="touch" /></label>
        <label><span>报价日期</span><input v-model="model.quoteDate" type="date" :disabled="readonly" /></label>
        <label><span>报价有效期（月）</span><input v-model.number="model.validityMonths" aria-label="报价有效期月数" type="number" min="1" step="1" :disabled="readonly" /></label>
      </div>
    </SectionCard>

    <SectionCard
      :title="quotationType === 'Service' ? '服务与配件项目' : '设备、系统与选装配件'"
      :eyebrow="quotationType === 'Service' ? 'SERVICE ITEMS' : 'CONFIGURATION'"
      :description="quotationType === 'Service' ? '用于售后服务、维修和配件订购；数量仅允许正整数。' : '从全局目录逐级选择设备、系统和配件；系统仅分组，不参与计价。'"
    >
      <template #action>
        <button v-if="!readonly && quotationType === 'Service'" class="secondary-button" type="button" data-testid="add-device" @click="addServiceItem"><Plus :size="14" />添加项目</button>
        <QuotationCatalogFilter v-else-if="!readonly" :options="catalogDevices" :selected-ids="selectedDeviceIds" label="设备" placeholder="添加设备" custom-placeholder="输入自定义设备名称" test-id="add-device" @select="addDevice" @custom="addCustomDevice" />
      </template>
      <p v-if="quotationType === 'Device' && catalogError" class="catalog-error">{{ catalogError }}</p>
      <div class="device-stack">
        <article v-for="(device, index) in devices" :key="device.lineKey" class="device-card">
          <header><div><span>{{ quotationType === 'Service' ? 'SERVICE ITEM' : 'DEVICE' }} {{ index + 1 }}</span><strong>{{ device.name || (quotationType === 'Service' ? '未命名项目' : '未命名设备') }}</strong></div><button v-if="!readonly && (devices.length > 1 || quotationType === 'Device')" class="remove-line-button" type="button" :aria-label="quotationType === 'Service' ? '删除项目' : '删除设备'" @click="removeLine(device)"><Trash2 :size="14" /></button></header>
          <div class="form-grid item-fields">
            <label><span>{{ quotationType === 'Service' ? '服务 / 配件项目' : '设备名称' }}</span><input v-model="device.name" :aria-label="quotationType === 'Service' ? '服务或配件项目' : '设备名称'" :disabled="readonly || (quotationType === 'Device' && !!device.catalogItemId)" /></label>
            <label><span>型号</span><input v-model="device.model" :disabled="readonly" /></label>
            <label class="wide"><span>规格 / 描述</span><textarea v-model="device.description" :disabled="readonly" /></label>
            <label><span>数量</span><input v-model.number="device.quantity" type="number" min="1" step="1" aria-label="设备数量" :disabled="readonly" /></label>
            <label><span>含税单价 (CNY)</span><input v-model="device.unitPrice" aria-label="设备含税单价" inputmode="decimal" :disabled="readonly" /></label>
          </div>
          <template v-if="quotationType === 'Device'">
            <section v-for="(system, systemIndex) in systems(device.lineKey)" :key="system.lineKey" class="system-card">
              <header>
                <div><span>SYSTEM {{ index + 1 }}.{{ systemIndex + 1 }}</span><input v-if="!system.catalogItemId" v-model="system.name" aria-label="系统名称" :disabled="readonly" /><strong v-else>{{ system.name }}</strong></div>
                <button v-if="!readonly" class="remove-line-button" type="button" aria-label="删除系统" @click="removeLine(system)"><Trash2 :size="14" /></button>
              </header>
              <div class="accessory-list">
                <div v-for="accessory in accessories(system.lineKey)" :key="accessory.lineKey" class="accessory-row">
                  <div class="form-grid item-fields">
                    <label><span>配件名称</span><input v-model="accessory.name" aria-label="配件名称" :disabled="readonly || !!accessory.catalogItemId" /></label>
                    <label><span>型号</span><input v-model="accessory.model" :disabled="readonly" /></label>
                    <label class="wide"><span>规格 / 描述</span><textarea v-model="accessory.description" :disabled="readonly" /></label>
                    <label><span>计价方式</span><QuotationPicker :model-value="accessory.pricingMode" :options="pricingModeOptions" placeholder="请选择计价方式" label="计价方式" test-id="accessory-pricing-mode-select" :allow-empty="false" :disabled="readonly" @update:model-value="setAccessoryPricingMode(accessory, $event)" /></label>
                    <label><span>总数量</span><input v-model.number="accessory.quantity" type="number" min="1" step="1" aria-label="配件数量" :disabled="readonly" /></label>
                    <label><span>含税单价</span><input v-model="accessory.unitPrice" aria-label="配件含税单价" inputmode="decimal" :disabled="readonly || accessory.pricingMode === 'Included'" /></label>
                  </div>
                  <button v-if="!readonly" class="remove-line-button" type="button" aria-label="删除配件" @click="removeLine(accessory)"><Trash2 :size="14" /></button>
                </div>
              </div>
              <QuotationCatalogFilter v-if="!readonly" class="add-child" :options="catalogAccessories(system)" :selected-ids="selectedAccessoryIds(system.lineKey)" label="配件" placeholder="添加配件" custom-placeholder="输入自定义配件名称" :test-id="`add-accessory-${system.lineKey}`" multiple @select="addAccessory(system, $event)" @custom="addCustomAccessory(system, $event)" />
            </section>
            <section v-if="legacyAccessories(device.lineKey).length" class="system-card legacy-system">
              <header><div><span>LEGACY</span><strong>历史未分组配件</strong></div></header>
              <div class="accessory-list"><div v-for="accessory in legacyAccessories(device.lineKey)" :key="accessory.lineKey" class="accessory-row"><div class="form-grid item-fields"><label><span>配件名称</span><input v-model="accessory.name" aria-label="配件名称" :disabled="readonly" /></label><label><span>型号</span><input v-model="accessory.model" :disabled="readonly" /></label><label class="wide"><span>规格 / 描述</span><textarea v-model="accessory.description" :disabled="readonly" /></label><label><span>计价方式</span><QuotationPicker :model-value="accessory.pricingMode" :options="pricingModeOptions" placeholder="请选择计价方式" label="计价方式" test-id="accessory-pricing-mode-select" :allow-empty="false" :disabled="readonly" @update:model-value="setAccessoryPricingMode(accessory, $event)" /></label><label><span>总数量</span><input v-model.number="accessory.quantity" type="number" min="1" step="1" aria-label="配件数量" :disabled="readonly" /></label><label><span>含税单价</span><input v-model="accessory.unitPrice" aria-label="配件含税单价" inputmode="decimal" :disabled="readonly || accessory.pricingMode === 'Included'" /></label></div><button v-if="!readonly" class="remove-line-button" type="button" aria-label="删除配件" @click="removeLine(accessory)"><Trash2 :size="14" /></button></div></div>
            </section>
            <QuotationCatalogFilter v-if="!readonly" class="add-child" :options="catalogSystems(device)" :selected-ids="selectedSystemIds(device.lineKey)" label="系统" placeholder="添加系统" custom-placeholder="输入自定义系统名称" :test-id="`add-system-${device.lineKey}`" @select="addSystem(device, $event)" @custom="addCustomSystem(device, $event)" />
          </template>
        </article>
      </div>
    </SectionCard>

    <SectionCard title="价格与整单折扣" eyebrow="PRICING">
      <div class="pricing-grid">
        <label><span>币种</span><input value="CNY / RMB" disabled /></label>
        <div class="discount-field"><span>折扣方式</span><div class="discount-options"><button v-for="option in discountTypes" :key="option.value" type="button" :data-discount-type="option.value" :class="{ active: model.discountType === option.value }" :disabled="readonly" @click="setDiscountType(option.value)">{{ option.label }}</button></div></div>
        <label><span>{{ model.discountType === 'Percentage' ? '折扣百分比' : '折扣金额' }}</span><input v-model="model.discountValue" aria-label="整单折扣值" inputmode="decimal" :disabled="readonly || model.discountType === 'None'" /></label>
        <div class="tax-note"><strong>含税价</strong><small>系统不拆分税额</small></div>
      </div>
    </SectionCard>

    <SectionCard title="商务条款" eyebrow="COMMERCIAL TERMS" description="付款比例可在草稿中调整，提交审批或发布时合计必须为 100%。">
      <div v-if="quotationType === 'Device'" class="form-grid three">
        <label><span>交期（月）</span><input v-model.number="model.deliveryMonths" aria-label="交期月数" type="number" min="1" step="1" :disabled="readonly" /><small>{{ model.deliveryMonths }}月内(标准交期) 收到买方正式PO为准。</small></label>
        <label><span>Warranty（月）</span><input v-model.number="model.warrantyMonths" aria-label="维保月数" type="number" min="1" step="1" :disabled="readonly" /><small>{{ model.warrantyMonths }}个月自发货日起维保</small></label>
        <label><span>报价有效期（月）</span><input v-model.number="model.validityMonths" type="number" min="1" step="1" aria-label="商务报价有效期月数" :disabled="readonly" /><small>报价有效期{{ model.validityMonths }}个月</small></label>
      </div>
      <div class="fixed-terms">
        <p v-if="quotationType === 'Device'"><strong>Incoterm：</strong>FOB上海&nbsp;&nbsp;FOB Shanghai</p>
        <h3>Payment Terms</h3>
        <div v-for="(term, index) in model.paymentTerms" :key="term.triggerCondition || index" class="payment-term-row">
          <label>
            <span>第 {{ index + 1 }} 期比例</span>
            <span class="percentage-input"><input v-model="term.percentage" :data-payment-percentage="index" inputmode="decimal" :disabled="readonly" /><b>%</b></span>
          </label>
          <p>{{ paymentDescriptions[index]?.(term.percentage) || term.description }}</p>
        </div>
        <template v-if="quotationType === 'Device'">
          <h3>Installation &amp; Training</h3>
          <ol><li v-for="line in fixedServices" :key="line">{{ line }}</li></ol>
        </template>
      </div>
    </SectionCard>
  </div>
</template>

<style scoped>
.quotation-editor{display:grid;gap:12px}.form-grid{display:grid;gap:12px}.form-grid.four{grid-template-columns:repeat(4,minmax(0,1fr))}.form-grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}.form-grid.item-fields{grid-template-columns:1.4fr 1fr 1fr 1fr}.form-grid label,.pricing-grid label{display:grid;gap:5px}.form-grid label.wide{grid-column:span 2}.form-grid label>span,.pricing-grid label>span,.discount-field>span{color:var(--crm-text-muted);font-size:10px;font-weight:700}.form-grid label small{color:var(--crm-text-muted);line-height:1.4}.form-grid input,.form-grid select,.form-grid textarea,.pricing-grid input{width:100%;min-height:36px;padding:7px 9px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:7px;box-sizing:border-box}.form-grid textarea{min-height:58px;resize:vertical}.device-stack{display:grid;gap:12px}.catalog-error{margin:0 0 10px;padding:8px 10px;color:#a63c3c;background:#fff0ef;border-radius:7px;font-size:10px}.system-card{display:grid;gap:10px;margin-top:12px;padding:11px;background:#fff;border:1px solid #cbd8d6;border-left:3px solid var(--crm-teal);border-radius:7px}.system-card>header{display:flex;align-items:center;justify-content:space-between;gap:10px}.system-card>header div{min-width:0;flex:1}.system-card>header span{display:block;color:var(--crm-teal);font-size:8px;font-weight:800;letter-spacing:.08em}.system-card>header strong{display:block;margin-top:3px;color:var(--crm-navy);font-size:11px}.system-card>header input{width:100%;min-height:34px;margin-top:4px;padding:6px 8px;border:1px solid var(--crm-line);border-radius:6px}.legacy-system{border-left-color:#98a3aa;background:#fafbfb}.add-child{display:block;width:max-content;max-width:100%;margin-top:9px}.device-card{padding:14px;background:#f9fbfb;border:1px solid var(--crm-line);border-radius:11px}.device-card>header{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}.device-card>header span,.device-card>header strong{display:block}.device-card>header span{color:var(--crm-teal);font-size:8px;font-weight:800;letter-spacing:.12em}.remove-line-button{display:inline-grid;min-width:30px;min-height:30px;place-items:center;color:var(--crm-danger);background:#fff;border:1px solid #e5b8b8;border-radius:7px;cursor:pointer;transition:background-color .18s ease,border-color .18s ease}.remove-line-button:hover{background:var(--crm-danger-soft);border-color:#cf8585}.accessory-list{display:grid;gap:8px;margin-top:10px}.accessory-row{display:flex;align-items:flex-start;gap:8px;padding:11px;background:#fff;border-left:3px solid #8db4af}.accessory-row .form-grid{flex:1}.add-child{min-height:32px!important;margin-top:9px!important;padding:0 10px!important}.pricing-grid{display:grid;grid-template-columns:1fr 2fr 1.3fr 1fr;gap:12px}.discount-field{display:grid;gap:5px}.discount-options{display:grid;grid-template-columns:repeat(3,1fr);gap:5px}.discount-options button{min-height:36px;padding:5px;border:1px solid var(--crm-line);border-radius:7px;background:#fff;color:var(--crm-text-muted);cursor:pointer}.discount-options button.active{border-color:var(--crm-teal);background:#eaf4f2;color:var(--crm-teal);font-weight:700}.tax-note{display:grid;align-content:center;padding:8px 10px;background:#eff7f6;border-radius:8px}.tax-note small{color:var(--crm-muted)}.fixed-terms{margin-top:16px;padding:14px;background:#f8faf9;border:1px solid var(--crm-line);border-radius:9px}.fixed-terms h3{margin:13px 0 7px;font-size:11px}.fixed-terms p{margin:6px 0;color:var(--crm-text-muted);font-size:11px;line-height:1.5}.fixed-terms ol{margin:0;padding-left:20px;color:var(--crm-text-muted);font-size:11px;line-height:1.7}.payment-term-row{display:grid;grid-template-columns:130px 1fr;align-items:end;gap:12px;padding:8px 0;border-bottom:1px solid var(--crm-line)}.payment-term-row:last-of-type{border-bottom:0}.payment-term-row label{display:grid;gap:5px;color:var(--crm-text-muted);font-size:10px;font-weight:700}.percentage-input{display:flex;align-items:center;gap:5px}.percentage-input input{width:88px;min-height:34px;padding:6px 8px;border:1px solid var(--crm-line);border-radius:7px}.percentage-input b{font-size:11px}.payment-term-row p{margin:0}@media(max-width:1000px){.form-grid.four,.form-grid.three,.form-grid.item-fields,.pricing-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:640px){.form-grid.four,.form-grid.three,.form-grid.item-fields,.pricing-grid,.payment-term-row{grid-template-columns:1fr}.form-grid label.wide{grid-column:auto}}
</style>
