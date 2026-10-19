<script setup lang="ts">
import { useLocalizedInput } from '@/i18n/localized-input'
import { systemValueLabel } from '@/features/shared/system-labels'
import { computed, ref, watch } from 'vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import { personnelDisplayName } from '@/demo/personnel'
import type { SiteDto } from '@/types/crm'
import type { InstalledToolDto, UpdateInstalledToolInput } from '@/types/workspaces'
import { useI18n } from '@/i18n'

type EngineerOption = { id: string; name: string; role: string }
const props = defineProps<{ tool: InstalledToolDto; sites: Array<Pick<SiteDto, 'id' | 'name' | 'city'>>; engineers: EngineerOption[]; canReassign: boolean; busy?: boolean; error?: string }>()
const emit = defineEmits<{ close: []; submit: [value: UpdateInstalledToolInput] }>()
const { locale, t } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const form = ref<UpdateInstalledToolInput>({
  siteId: '', model: '', location: '', engineerOwner: '', operatingSystem: '',
  warrantyStart: '', warrantyEnd: '', serviceContract: '', pmCycle: '', ownershipType: '',
  salesOrder: '', contract: '',
})
watch(() => props.tool, (tool) => {
  form.value = {
    siteId: tool.siteId,
    model: tool.model,
    location: tool.location,
    engineerOwner: tool.engineerOwner,
    operatingSystem: tool.operatingSystem,
    warrantyStart: tool.warrantyStart,
    warrantyEnd: tool.warrantyEnd,
    serviceContract: tool.serviceContract,
    pmCycle: tool.pmCycle,
    ownershipType: tool.ownershipType,
    salesOrder: tool.salesOrder,
    contract: tool.contract,
  }
}, { immediate: true })
const invalid = computed(() => !props.sites.length || !form.value.siteId || !form.value.model.trim() || !form.value.location.trim() || !form.value.engineerOwner || !form.value.ownershipType?.trim())
function submit() {
  emit('submit', Object.fromEntries(Object.entries(form.value).map(([key, value]) => [key, typeof value === 'string' ? value.trim() : value])) as unknown as UpdateInstalledToolInput)
}

const locationInput = useLocalizedInput(() => form.value.location, (value) => { form.value.location = value }, (value) => systemValueLabel(value, locale.value), () => props.tool)
const operatingSystemInput = useLocalizedInput(() => form.value.operatingSystem, (value) => { form.value.operatingSystem = value }, (value) => systemValueLabel(value, locale.value), () => props.tool)
const serviceContractInput = useLocalizedInput(() => form.value.serviceContract, (value) => { form.value.serviceContract = value }, (value) => systemValueLabel(value, locale.value), () => props.tool)
const pmCycleInput = useLocalizedInput(() => form.value.pmCycle, (value) => { form.value.pmCycle = value }, (value) => systemValueLabel(value, locale.value), () => props.tool)
const salesOrderInput = useLocalizedInput(() => form.value.salesOrder, (value) => { form.value.salesOrder = value }, (value) => systemValueLabel(value, locale.value), () => props.tool)
const contractInput = useLocalizedInput(() => form.value.contract, (value) => { form.value.contract = value }, (value) => systemValueLabel(value, locale.value), () => props.tool)
</script>

<template>
  <ModalShell :title="t('installed.editTitle')" :eyebrow="copy('INSTALLED TOOL MASTER DATA', '设备主数据')" :submit-label="t('installed.saveMaster')" :busy="busy" :submit-disabled="invalid" wide @close="emit('close')" @submit="submit">
    <div class="readonly-summary">
       <div><small>{{ copy('Installed Tool', '已装机设备') }}</small><strong>{{ tool.id }}</strong></div>
       <div><small>{{ copy('Customer', '客户') }}</small><strong>{{ tool.account }}</strong></div>
       <div><small>{{ copy('Source Booking', '来源 Booking') }}</small><strong>{{ tool.sourceBookingId || '—' }}</strong></div>
       <div><small>{{ copy('Sales Owner', '销售负责人') }}</small><strong>{{ personnelDisplayName(tool.salesOwner) || tool.salesOwner || '—' }}</strong></div>
    </div>
    <p class="form-note">{{ t('installed.masterAuditHint') }}</p>
    <p v-if="error" class="form-error">{{ error }}</p>
    <p v-if="!sites.length" class="form-error">{{ t('installed.noSites') }}</p>
    <div class="editor-grid">
       <label><span>{{ copy('Serial Number', '序列号') }}</span><input :value="tool.serial" :aria-label="copy('Serial Number', '序列号')" readonly /></label>
      <label><span>{{ t('installed.model') }}<RequiredMark /></span><input v-model="form.model" :aria-label="t('installed.model')" required /></label>
      <label><span>{{ t('installed.customerSiteField') }}<RequiredMark /></span><select v-model="form.siteId" :aria-label="t('installed.customerSiteField')" required><option v-for="site in sites" :key="site.id" :value="site.id">{{ site.name }} · {{ site.city }}</option></select></label>
      <label><span>{{ t('installed.siteLocation') }}<RequiredMark /></span><input v-model="locationInput" :aria-label="t('installed.siteLocation')" required /></label>
      <label><span>{{ t('installed.engineerOwner') }}<RequiredMark /></span><select v-model="form.engineerOwner" :aria-label="t('installed.engineerOwner')" required :disabled="!canReassign"><option v-if="!engineers.some((item) => item.id === form.engineerOwner)" :value="form.engineerOwner">{{ personnelDisplayName(form.engineerOwner) || form.engineerOwner }}</option><option v-for="engineer in engineers" :key="engineer.id" :value="engineer.id">{{ engineer.name }} · {{ engineer.role }}</option></select><small v-if="!canReassign">{{ t('installed.cannotReassign') }}</small></label>
       <label><span>{{ copy('Operating System', '操作系统') }}</span><input v-model="operatingSystemInput" :aria-label="copy('Operating System', '操作系统')" /></label>
       <label><span>{{ copy('Warranty Start', '质保开始') }}</span><input v-model="form.warrantyStart" type="date" :aria-label="copy('Warranty Start', '质保开始')" /></label>
       <label><span>{{ copy('Warranty End', '质保结束') }}</span><input v-model="form.warrantyEnd" type="date" :aria-label="copy('Warranty End', '质保结束')" /></label>
       <label><span>{{ copy('Service Contract', '服务演示员工116') }}</span><input v-model="serviceContractInput" :aria-label="copy('Service Contract', '服务演示员工116')" /></label>
       <label><span>{{ copy('PM Cycle', 'PM 周期') }}</span><input v-model="pmCycleInput" :aria-label="copy('PM Cycle', 'PM 周期')" /></label>
       <label><span>{{ copy('Ownership Type', '归属类型') }}<RequiredMark /></span><input v-model="form.ownershipType" :aria-label="copy('Ownership Type', '归属类型')" required /></label>
       <label><span>{{ copy('Sales Order', '销售订单') }}</span><input v-model="salesOrderInput" :aria-label="copy('Sales Order', '销售订单')" /></label>
       <label class="wide"><span>{{ copy('Contract', '演示员工116') }}</span><input v-model="contractInput" :aria-label="copy('Contract', '演示员工116')" /></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.readonly-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;margin-bottom:12px;background:var(--crm-line);border:1px solid var(--crm-line);border-radius:9px;overflow:hidden}.readonly-summary>div{display:grid;gap:4px;padding:10px;background:var(--crm-surface-muted)}.readonly-summary small{color:var(--crm-text-muted);font-size:7px}.readonly-summary strong{overflow:hidden;font-size:8px;text-overflow:ellipsis}.form-note,.form-error{margin:0 0 12px;padding:10px;border-radius:8px;font-size:9px}.form-note{color:var(--crm-teal);background:var(--crm-surface-muted)}.form-error{color:var(--crm-danger);background:var(--crm-danger-soft)}.editor-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.editor-grid label{display:grid;align-content:start;gap:6px}.editor-grid span{color:var(--crm-text-muted);font-size:9px;font-weight:700}.editor-grid input,.editor-grid select{box-sizing:border-box;width:100%;height:38px;padding:9px 10px;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.editor-grid select:disabled{background:var(--crm-surface-muted)}.editor-grid label>small{color:var(--crm-text-muted);font-size:7px}.wide{grid-column:1/-1}@media(max-width:680px){.readonly-summary{grid-template-columns:1fr 1fr}.editor-grid{grid-template-columns:1fr}.wide{grid-column:auto}}
</style>
