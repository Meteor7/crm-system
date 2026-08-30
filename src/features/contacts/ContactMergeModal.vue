<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ContactSummaryDto } from '@/types/crm'
import ModalShell from '@/design-system/ModalShell.vue'

const props = defineProps<{ contact: ContactSummaryDto; contacts: ContactSummaryDto[]; busy?: boolean; error?: string }>()
const emit = defineEmits<{ close: []; submit: [payload: { survivorId: string; duplicateId: string }] }>()
const duplicateId = ref('')
const candidates = computed(() => props.contacts.filter((item) =>
  item.accountId === props.contact.accountId && item.id !== props.contact.id && item.status !== 'Archived',
))
function submit() {
  if (duplicateId.value) emit('submit', { survivorId: props.contact.id, duplicateId: duplicateId.value })
}
</script>

<template>
  <ModalShell title="合并重复联系人" eyebrow="DATA QUALITY" :busy="busy" @close="emit('close')" @submit="submit">
    <p class="merge-note">当前联系人 <strong>{{ contact.name }}</strong> 将作为保留主档。所有业务关联会迁移到主档，重复联系人会被标记为 Archived，不会被硬删除。</p>
    <p v-if="error" class="form-error">{{ error }}</p>
    <label class="merge-field"><span>选择重复联系人</span><select v-model="duplicateId" aria-label="重复联系人" required><option value="">请选择</option><option v-for="item in candidates" :key="item.id" :value="item.id" :data-merge-candidate="item.id">{{ item.name }} · {{ item.title }}</option></select></label>
  </ModalShell>
</template>

<style scoped>
.merge-note{margin:0 0 16px;padding:13px;color:var(--crm-text-muted);background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:10px;font-size:11px;line-height:1.65}.merge-note strong{color:var(--crm-navy)}.merge-field{display:grid;gap:7px;color:var(--crm-text-muted);font-size:10px;font-weight:700}.merge-field select{min-height:38px;padding:8px 10px;background:#fff;border:1px solid var(--crm-line);border-radius:8px}.form-error{padding:10px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-size:10px}
</style>
