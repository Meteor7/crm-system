<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from '@/i18n'
import { personnelById, personnelForRoles } from '@/demo/personnel'
import { useOwnOwnerOnly } from '@/stores/signed-in-user'
import type { PersonnelRole } from '@/types/crm'

const props = withDefaults(defineProps<{
  modelValue: string
  roles: PersonnelRole[]
  ariaLabel: string
  placeholder?: string
  required?: boolean
  disabled?: boolean
  /**
   * The field is the owner of a record. A Sales user can assign a record only to themselves, so for them the
   * field offers nobody else, and an empty one is filled with their own name; a Manager chooses among the
   * roles as before.
   */
  owner?: boolean
}>(), {
  placeholder: '',
  required: false,
  disabled: false,
  owner: false,
})

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const { locale } = useI18n()
const placeholderLabel = computed(() => props.placeholder || (locale.value === 'en-US' ? 'Select assignee' : '请选择负责人'))
const roleLabel = (role: PersonnelRole) => locale.value === 'en-US' ? role : ({ Manager: '经理', Sales: '销售', Engineer: '工程师' }[role] ?? role)
const ownOwnerOnly = useOwnOwnerOnly()
const only = computed(() => props.owner ? ownOwnerOnly.value : '')
const options = computed(() => personnelForRoles(props.roles).filter((person) => !only.value || person.id === only.value))
const legacyValue = computed(() => props.modelValue && !personnelById(props.modelValue) ? props.modelValue : '')
// The owner a record already has when the field does not offer that person: shown, and not to be chosen.
const heldPerson = computed(() => {
  const person = only.value && props.modelValue ? personnelById(props.modelValue) : undefined
  return person && person.id !== only.value ? person : undefined
})
// An empty owner field of a Sales user can only become that user. A record that already has another owner
// keeps it until the user changes it: taking a record over is never done for them.
watch(() => [only.value, props.modelValue, props.disabled] as const, ([own, value, disabled]) => {
  if (own && !disabled && !value && options.value.some((person) => person.id === own)) emit('update:modelValue', own)
}, { immediate: true })
</script>

<template>
  <select
    :value="modelValue"
    :aria-label="ariaLabel"
    :required="required"
    :disabled="disabled"
    @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
  >
    <option v-if="!required" value="">{{ placeholderLabel }}</option>
    <option v-else-if="!modelValue" value="" disabled>{{ placeholderLabel }}</option>
    <option v-if="legacyValue" :value="legacyValue" disabled>{{ legacyValue }} ({{ locale === 'en-US' ? 'legacy' : '历史值' }})</option>
    <option v-if="heldPerson" :value="heldPerson.id" disabled>{{ heldPerson.name }} · {{ roleLabel(heldPerson.role) }}</option>
    <option v-for="person in options" :key="person.id" :value="person.id">
      {{ person.name }} · {{ roleLabel(person.role) }}
    </option>
  </select>
</template>
