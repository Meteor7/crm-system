<script setup lang="ts">
import { computed } from 'vue'
import { Plus } from '@lucide/vue'
import type { ContactSummaryDto } from '@/types/crm'

const props = defineProps<{ contacts: ContactSummaryDto[]; accountId: string; modelValue?: string; disabled?: boolean; required?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string]; create: [] }>()
const options = computed(() => props.contacts.filter((item) => item.accountId === props.accountId && item.status === 'Active'))
</script>

<template>
  <div class="contact-picker">
    <select :value="modelValue || ''" aria-label="选择联系人" :disabled="disabled || !accountId" :required="required" @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)">
      <option value="">请选择联系人</option>
      <option v-for="contact in options" :key="contact.id" :value="contact.id" :data-contact-option="contact.id">{{ contact.name }} · {{ contact.title }}</option>
    </select>
    <button type="button" data-testid="create-contact" :disabled="disabled || !accountId" @click="emit('create')"><Plus :size="14" />快速新增联系人</button>
  </div>
</template>

<style scoped>
.contact-picker{display:flex;align-items:center;gap:8px}.contact-picker select{min-width:220px;min-height:36px;padding:7px 10px;background:#fff;border:1px solid var(--crm-line);border-radius:8px}.contact-picker button{display:flex;align-items:center;gap:5px;padding:8px 10px;color:var(--crm-teal);background:var(--crm-teal-soft);border:1px solid color-mix(in srgb,var(--crm-teal) 25%,transparent);border-radius:8px;font-weight:700;cursor:pointer}.contact-picker button:disabled{opacity:.5;cursor:not-allowed}@media(max-width:560px){.contact-picker{align-items:stretch;flex-direction:column}.contact-picker select{min-width:0}}
</style>
