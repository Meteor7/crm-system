<script setup lang="ts">
import { computed } from 'vue'
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
  placeholder: 'Select assignee',
  required: false,
  disabled: false,
})

defineEmits<{ 'update:modelValue': [value: string] }>()

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
    <option v-if="!required" value="">{{ placeholder }}</option>
    <option v-else-if="!modelValue" value="" disabled>{{ placeholder }}</option>
    <option v-if="legacyValue" :value="legacyValue" disabled>{{ legacyValue }} (legacy)</option>
    <option v-for="person in options" :key="person.id" :value="person.id">
      {{ person.name }} · {{ person.role }}
    </option>
  </select>
</template>
