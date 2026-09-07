<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from '@/i18n'
import { personnelById, personnelForRoles } from '@/demo/personnel'
import type { PersonnelRole } from '@/types/crm'

const props = withDefaults(defineProps<{
  modelValue: string
  roles: PersonnelRole[]
  ariaLabel: string
  placeholder?: string
  required?: boolean
  disabled?: boolean
}>(), {
  placeholder: '',
  required: false,
  disabled: false,
})

defineEmits<{ 'update:modelValue': [value: string] }>()

const { locale } = useI18n()
const placeholderLabel = computed(() => props.placeholder || (locale.value === 'en-US' ? 'Select assignee' : '请选择负责人'))
const roleLabel = (role: PersonnelRole) => locale.value === 'en-US' ? role : ({ Manager: '经理', Sales: '销售', Engineer: '工程师' }[role] ?? role)
const options = computed(() => personnelForRoles(props.roles))
const legacyValue = computed(() => props.modelValue && !personnelById(props.modelValue) ? props.modelValue : '')
</script>

<template>
  <select
    :value="modelValue"
    :aria-label="ariaLabel"
    :required="required"
    :disabled="disabled"
    @change="$emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
  >
    <option v-if="!required" value="">{{ placeholderLabel }}</option>
    <option v-else-if="!modelValue" value="" disabled>{{ placeholderLabel }}</option>
    <option v-if="legacyValue" :value="legacyValue" disabled>{{ legacyValue }} ({{ locale === 'en-US' ? 'legacy' : '历史值' }})</option>
    <option v-for="person in options" :key="person.id" :value="person.id">
      {{ person.name }} · {{ roleLabel(person.role) }}
    </option>
  </select>
</template>
