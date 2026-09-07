<script setup lang="ts">
import { ref, watch } from 'vue'
import ModalShell from '@/design-system/ModalShell.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import { personnelDisplayName } from '@/demo/personnel'
import type { PersonnelIdentity } from '@/demo/personnel'
import type { BookingDto, SiteDto } from '@/types/crm'
import type { ConvertBookingToInstalledToolInput } from '@/types/workspaces'
import { useI18n } from '@/i18n'
import { salesEnumLabel } from '@/features/shared/sales-i18n'

const props = defineProps<{
  booking: BookingDto
  sites: SiteDto[]
  engineers: PersonnelIdentity[]
  busy?: boolean
  error?: string
}>()
const emit = defineEmits<{ close: []; submit: [value: ConvertBookingToInstalledToolInput] }>()
const { t, locale } = useI18n()

const form = ref({
  siteId: props.sites[0]?.id ?? '',
  engineerOwner: props.engineers[0]?.id ?? '',
  model: props.booking.equipment,
  location: '',
  salesOrder: '',
  contract: '',
  software: '',
  firmware: '',
  configuration: '',
})
watch(() => props.sites, (sites) => {
  if (!form.value.siteId) form.value.siteId = sites[0]?.id ?? ''
}, { immediate: true })
watch(() => props.engineers, (engineers) => {
  if (!form.value.engineerOwner) form.value.engineerOwner = engineers[0]?.id ?? ''
}, { immediate: true })

function submit() {
  emit('submit', Object.fromEntries(
    Object.entries(form.value).map(([key, value]) => [key, value.trim()]),
  ) as unknown as ConvertBookingToInstalledToolInput)
}
</script>

<template>
  <ModalShell
    :title="t('bookingEditor.convertTool')"
    eyebrow="BOOKING HANDOFF"
    :submit-label="t('bookingEditor.confirmConvert')"
    :busy="busy"
    :submit-disabled="!sites.length"
    @close="$emit('close')"
    @submit="submit"
  >
    <p class="handoff-summary">
      <strong>{{ booking.id }} · {{ booking.equipment }}</strong>
      <span>{{ booking.accountName }} · {{ locale === 'en-US' ? 'Sales' : '销售' }} {{ personnelDisplayName(booking.owner) }}</span>
    </p>
    <p v-if="error" class="form-error">{{ error }}</p>
    <p v-if="!sites.length" class="form-error">{{ t('bookingEditor.noSites') }}</p>
    <div class="handoff-form-grid">
      <label><span>{{ t('installed.customerSiteField') }}<RequiredMark /></span><select v-model="form.siteId" :aria-label="t('installed.customerSiteField')" required><option v-for="site in sites" :key="site.id" :value="site.id">{{ site.name }} · {{ site.city }}</option></select></label>
      <label><span>{{ t('installed.engineerOwner') }}<RequiredMark /></span><select v-model="form.engineerOwner" :aria-label="t('installed.engineerOwner')" required><option v-for="engineer in engineers" :key="engineer.id" :value="engineer.id">{{ engineer.name }} · {{ engineer.demoIdentityId === 'fae' ? 'FAE' : (locale === 'en-US' ? 'Engineer' : '工程师') }}</option></select></label>
      <label><span>{{ t('installed.model') }}<RequiredMark /></span><input v-model="form.model" :aria-label="t('installed.model')" required /></label>
      <label><span>{{ t('installed.siteLocation') }}</span><input v-model="form.location" :aria-label="t('installed.siteLocation')" :placeholder="t('bookingEditor.pendingPlaceholder')" /></label>
      <label><span>{{ locale === 'en-US' ? 'Sales order' : '销售订单' }}</span><input v-model="form.salesOrder" :aria-label="locale === 'en-US' ? 'Sales order' : '销售订单'" :placeholder="t('bookingEditor.pendingPlaceholder')" /></label>
      <label><span>{{ locale === 'en-US' ? 'Contract' : '合同' }}</span><input v-model="form.contract" :aria-label="locale === 'en-US' ? 'Contract' : '合同'" :placeholder="t('bookingEditor.pendingPlaceholder')" /></label>
      <label><span>{{ salesEnumLabel('Software', locale) }}</span><input v-model="form.software" :aria-label="salesEnumLabel('Software', locale)" :placeholder="t('bookingEditor.pendingPlaceholder')" /></label>
      <label><span>{{ salesEnumLabel('Firmware', locale) }}</span><input v-model="form.firmware" :aria-label="salesEnumLabel('Firmware', locale)" :placeholder="t('bookingEditor.pendingPlaceholder')" /></label>
      <label><span>{{ salesEnumLabel('Configuration', locale) }}</span><input v-model="form.configuration" :aria-label="salesEnumLabel('Configuration', locale)" :placeholder="t('bookingEditor.pendingPlaceholder')" /></label>
    </div>
  </ModalShell>
</template>

<style scoped>
.handoff-summary{display:grid;gap:4px;margin:0 0 14px;padding:12px;background:var(--crm-surface-muted);border-radius:9px}.handoff-summary strong{color:var(--crm-navy);font-size:11px}.handoff-summary span{color:var(--crm-text-muted);font-size:9px}.form-error{margin:0 0 12px;padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:9px}.handoff-form-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.handoff-form-grid label{display:grid;gap:6px}.handoff-form-grid span{color:var(--crm-text-muted);font-size:9px;font-weight:700}.handoff-form-grid input,.handoff-form-grid select{box-sizing:border-box;width:100%;height:38px;padding:9px 10px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;font:inherit}.handoff-form-grid :focus{border-color:var(--crm-teal);outline:0}@media(max-width:560px){.handoff-form-grid{grid-template-columns:1fr}}
</style>
