<script setup lang="ts">
import { ref } from 'vue'
import { regionLabel, territoryOptionLabel } from '@/domain/regions'
import { useI18n } from '@/i18n'

// The region filter of Review, Warnings and Plan: the sales territory tree in a native select.
defineProps<{ modelValue?: string; regions: string[]; parents?: Record<string, string>; disabled?: boolean; allLabel: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const { locale } = useI18n()
// A native select shows the chosen option's text in the closed control. The list indents each name under its
// territory, so the chosen one drops its indent while the list is closed and gets it back before it opens.
const listing = ref(false)
// Space, F4 and Alt with an arrow open the native list on Windows and Linux, and Escape closes it without a change.
// Any other key leaves the list closed: a plain arrow or a letter changes the value, which choose() handles.
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') listing.value = false
  else if (event.key === ' ' || event.key === 'F4' || (event.altKey && (event.key === 'ArrowDown' || event.key === 'ArrowUp'))) listing.value = true
}
function choose(event: Event) {
  listing.value = false
  emit('update:modelValue', (event.target as HTMLSelectElement).value)
}
</script>
<template>
  <select :value="modelValue ?? ''" aria-label="Region" :disabled="disabled" @mousedown="listing = true" @keydown="onKeydown" @blur="listing = false" @change="choose">
    <option value="">{{ allLabel }}</option>
    <option v-for="region in regions" :key="region" :value="region">{{ listing || region !== modelValue ? territoryOptionLabel(region, parents, locale) : regionLabel(region, locale) }}</option>
  </select>
</template>
