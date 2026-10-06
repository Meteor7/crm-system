<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ContactSummaryDto } from '@/types/crm'
import ModalShell from '@/design-system/ModalShell.vue'
import { useI18n } from '@/i18n'

const props = defineProps<{ contact: ContactSummaryDto; contacts: ContactSummaryDto[]; busy?: boolean; error?: string }>()
const emit = defineEmits<{ close: []; submit: [payload: { survivorId: string; duplicateId: string }] }>()
const duplicateId = ref('')
const { locale } = useI18n()
const candidates = computed(() => props.contacts.filter((item) =>
  item.accountId === props.contact.accountId && item.id !== props.contact.id && item.status !== 'Archived',
))
function submit() {
  if (duplicateId.value) emit('submit', { survivorId: props.contact.id, duplicateId: duplicateId.value })
}
</script>

<template>
  <ModalShell :title="locale === 'en-US' ? 'Merge duplicate contact' : '合并重复联系人'" eyebrow="DATA QUALITY" :busy="busy" :submit-label="locale === 'en-US' ? 'Merge' : '合并'" @close="emit('close')" @submit="submit">
    <p class="merge-note">{{ locale === 'en-US' ? 'Current contact ' : '当前联系人 ' }}<strong>{{ contact.name }}</strong>{{ locale === 'en-US' ? ' is kept as the master. The duplicate is marked Archived and noted as merged into it, and its direct reports report to the master; its Opportunities, Bookings, Demo Requests and Visits stay in its name (not moved).' : ' 将作为保留主档。重复联系人会被标记为“已归档”并记下合并到主档，其直属下属改为汇报给主档；它名下的 Opportunity、Booking、Demo Request 和拜访留在它名下，不迁移。' }}</p>
    <p v-if="error" class="form-error">{{ error }}</p>
    <label class="merge-field"><span>{{ locale === 'en-US' ? 'Select duplicate contact' : '选择重复联系人' }}</span><select v-model="duplicateId" :aria-label="locale === 'en-US' ? 'Duplicate contact' : '重复联系人'" required><option value="">{{ locale === 'en-US' ? 'Select' : '请选择' }}</option><option v-for="item in candidates" :key="item.id" :value="item.id" :data-merge-candidate="item.id">{{ item.name }} · {{ item.title }}</option></select></label>
  </ModalShell>
</template>

<style scoped>
.merge-note{margin:0 0 16px;padding:13px;color:var(--crm-text-muted);background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:10px;font-size:11px;line-height:1.65}.merge-note strong{color:var(--crm-navy)}.merge-field{display:grid;gap:7px;color:var(--crm-text-muted);font-size:10px;font-weight:700}.merge-field select{min-height:38px;padding:8px 10px;background:#fff;border:1px solid var(--crm-line);border-radius:8px}.form-error{padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:10px}
</style>
