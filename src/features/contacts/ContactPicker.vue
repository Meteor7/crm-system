<script setup lang="ts">
import { computed } from 'vue'
import { Plus } from '@lucide/vue'
import { useI18n } from '@/i18n'
import type { ContactSummaryDto } from '@/types/crm'

const props = defineProps<{ contacts: ContactSummaryDto[]; accountId: string; modelValue?: string; disabled?: boolean; required?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string]; create: [] }>()
const { locale } = useI18n()
const options = computed(() => props.contacts.filter((item) => item.accountId === props.accountId && item.status === 'Active'))
</script>

<template>
  <div class="contact-picker">
    <select :value="modelValue || ''" :aria-label="locale === 'en-US' ? 'Select contact' : '选择联系人'" :disabled="disabled || !accountId" :required="required" @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)">
      <option value="">{{ locale === 'en-US' ? 'Select contact' : '请选择联系人' }}</option>
      <option v-for="contact in options" :key="contact.id" :value="contact.id" :data-contact-option="contact.id">{{ contact.name }} · {{ contact.title }}</option>
    </select>
    <button type="button" data-testid="create-contact" :disabled="disabled || !accountId" @click="emit('create')"><Plus :size="14" />{{ locale === 'en-US' ? 'Quick add contact' : '快速新增联系人' }}</button>
  </div>
</template>

<style scoped>
.contact-picker{display:flex;min-width:0;align-items:start;flex-wrap:wrap;gap:8px}.contact-picker select{width:100%;min-width:0;flex:1 1 180px;height:38px;padding:0 12px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:8px;outline:0;font-size:var(--crm-font-md);font-weight:400;transition:border-color .15s,box-shadow .15s}.contact-picker select:focus{border-color:var(--crm-teal);box-shadow:0 0 0 3px color-mix(in srgb,var(--crm-teal) 12%,transparent)}.contact-picker button{display:inline-flex;height:38px;flex:0 0 auto;align-items:center;gap:5px;padding:0 10px;color:var(--crm-link);background:var(--crm-teal-soft);border:1px solid color-mix(in srgb,var(--crm-teal) 25%,transparent);border-radius:8px;font-size:var(--crm-font-md);font-weight:600;white-space:nowrap;cursor:pointer}.contact-picker button:disabled{opacity:.5;cursor:not-allowed}@media(max-width:560px){.contact-picker{align-items:stretch;flex-direction:column}.contact-picker select{flex:auto}}
</style>
