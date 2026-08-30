<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import { personnelDisplayName } from '@/demo/personnel'
import type { SiteDto } from '@/types/crm'
import type { InstalledToolDto, UpdateInstalledToolInput } from '@/types/workspaces'

type EngineerOption = { id: string; name: string; role: string }
const props = defineProps<{ tool: InstalledToolDto; sites: SiteDto[]; engineers: EngineerOption[]; canReassign: boolean; busy?: boolean; error?: string }>()
const emit = defineEmits<{ close: []; submit: [value: UpdateInstalledToolInput] }>()
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
</script>

<template>
  <ModalShell title="编辑 Installed Tool 主数据" eyebrow="INSTALLED TOOL MASTER DATA" submit-label="保存设备主数据" :busy="busy" :submit-disabled="invalid" wide @close="emit('close')" @submit="submit">
    <div class="readonly-summary">
      <div><small>Installed Tool</small><strong>{{ tool.id }}</strong></div>
      <div><small>Customer</small><strong>{{ tool.account }}</strong></div>
      <div><small>Source Booking</small><strong>{{ tool.sourceBookingId || '—' }}</strong></div>
      <div><small>Sales Owner</small><strong>{{ personnelDisplayName(tool.salesOwner) || tool.salesOwner || '—' }}</strong></div>
    </div>
    <p class="form-note">生命周期状态与软件、固件、配置版本必须通过对应的审计操作更新。</p>
    <p v-if="error" class="form-error">{{ error }}</p>
    <p v-if="!sites.length" class="form-error">该客户暂无可用厂区，请先补齐客户厂区档案。</p>
    <div class="editor-grid">
      <label><span>Serial Number</span><input :value="tool.serial" aria-label="Serial Number" readonly /></label>
      <label><span>设备型号<RequiredMark /></span><input v-model="form.model" aria-label="设备型号" required /></label>
      <label><span>客户厂区<RequiredMark /></span><select v-model="form.siteId" aria-label="客户厂区" required><option v-for="site in sites" :key="site.id" :value="site.id">{{ site.name }} · {{ site.city }}</option></select></label>
      <label><span>现场位置<RequiredMark /></span><input v-model="form.location" aria-label="现场位置" required /></label>
      <label><span>负责工程师<RequiredMark /></span><select v-model="form.engineerOwner" aria-label="负责工程师" required :disabled="!canReassign"><option v-if="!engineers.some((item) => item.id === form.engineerOwner)" :value="form.engineerOwner">{{ personnelDisplayName(form.engineerOwner) || form.engineerOwner }}</option><option v-for="engineer in engineers" :key="engineer.id" :value="engineer.id">{{ engineer.name }} · {{ engineer.role }}</option></select><small v-if="!canReassign">工程师不能重新分配负责人</small></label>
      <label><span>Operating System</span><input v-model="form.operatingSystem" aria-label="Operating System" /></label>
      <label><span>Warranty Start</span><input v-model="form.warrantyStart" type="date" aria-label="Warranty Start" /></label>
      <label><span>Warranty End</span><input v-model="form.warrantyEnd" type="date" aria-label="Warranty End" /></label>
      <label><span>Service Contract</span><input v-model="form.serviceContract" aria-label="Service Contract" /></label>
      <label><span>PM Cycle</span><input v-model="form.pmCycle" aria-label="PM Cycle" /></label>
      <label><span>Ownership Type<RequiredMark /></span><input v-model="form.ownershipType" aria-label="Ownership Type" required /></label>
      <label><span>Sales Order</span><input v-model="form.salesOrder" aria-label="Sales Order" /></label>
      <label class="wide"><span>Contract</span><input v-model="form.contract" aria-label="Contract" /></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.readonly-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;margin-bottom:12px;background:var(--crm-line);border:1px solid var(--crm-line);border-radius:9px;overflow:hidden}.readonly-summary>div{display:grid;gap:4px;padding:10px;background:var(--crm-surface-muted)}.readonly-summary small{color:var(--crm-text-muted);font-size:7px}.readonly-summary strong{overflow:hidden;font-size:8px;text-overflow:ellipsis}.form-note,.form-error{margin:0 0 12px;padding:10px;border-radius:8px;font-size:9px}.form-note{color:var(--crm-teal);background:var(--crm-surface-muted)}.form-error{color:var(--crm-danger);background:var(--crm-danger-soft)}.editor-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.editor-grid label{display:grid;align-content:start;gap:6px}.editor-grid span{color:var(--crm-text-muted);font-size:9px;font-weight:700}.editor-grid input,.editor-grid select{box-sizing:border-box;width:100%;height:38px;padding:9px 10px;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.editor-grid select:disabled{background:var(--crm-surface-muted)}.editor-grid label>small{color:var(--crm-text-muted);font-size:7px}.wide{grid-column:1/-1}@media(max-width:680px){.readonly-summary{grid-template-columns:1fr 1fr}.editor-grid{grid-template-columns:1fr}.wide{grid-column:auto}}
</style>
