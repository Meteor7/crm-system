<script setup lang="ts">
import { computed, ref } from 'vue'
import { ChevronDown } from '@lucide/vue'

interface PickerOption { value: string; label: string }
const props = withDefaults(defineProps<{ modelValue: string; options: PickerOption[]; placeholder: string; label: string; disabled?: boolean; testId: string; allowEmpty?: boolean }>(), { allowEmpty: true })
const emit = defineEmits<{ 'update:modelValue': [value: string]; change: [] }>()
const open = ref(false)
const selectedLabel = computed(() => props.options.find((item) => item.value === props.modelValue)?.label || props.placeholder)
function choose(value: string) { emit('update:modelValue', value); emit('change'); open.value = false }
function closeOnFocusOut(event: FocusEvent) {
  const root = event.currentTarget as HTMLElement
  if (!root.contains(event.relatedTarget as Node | null)) open.value = false
}
</script>

<template>
  <div class="quotation-picker" :data-testid="testId" @focusout="closeOnFocusOut">
    <button
      type="button"
      role="combobox"
      :aria-label="label"
      :aria-expanded="open"
      aria-haspopup="listbox"
      :disabled="disabled"
      @click="open = !open"
      @keydown.escape.prevent="open = false"
      @keydown.down.prevent="open = true"
    >
      <span :class="{ placeholder: !modelValue }">{{ selectedLabel }}</span>
      <ChevronDown :size="15" aria-hidden="true" />
    </button>
    <div v-if="open" class="picker-menu" role="listbox" :aria-label="label">
      <button v-if="allowEmpty" type="button" role="option" :aria-selected="!modelValue" @click="choose('')">{{ placeholder }}</button>
      <button
        v-for="item in options"
        :key="item.value"
        type="button"
        role="option"
        :aria-selected="item.value === modelValue"
        @click="choose(item.value)"
      >{{ item.label }}</button>
    </div>
  </div>
</template>

<style scoped>
.quotation-picker{position:relative;min-width:0}.quotation-picker>button{display:flex;width:100%;min-height:36px;align-items:center;justify-content:space-between;gap:8px;padding:7px 9px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:7px;font:inherit;text-align:left;cursor:pointer}.quotation-picker>button:focus-visible{border-color:var(--crm-teal);outline:2px solid color-mix(in srgb,var(--crm-teal) 22%,transparent);outline-offset:1px}.quotation-picker>button:disabled{cursor:not-allowed;opacity:.6}.placeholder{color:var(--crm-muted)}.picker-menu{position:absolute;top:calc(100% + 5px);right:0;left:0;z-index:80;display:grid;max-height:240px;overflow:auto;padding:5px;background:#fff;border:1px solid var(--crm-line);border-radius:8px;box-shadow:0 12px 30px rgba(8,32,40,.16)}.picker-menu button{width:100%;padding:8px 9px;color:var(--crm-text);background:transparent;border:0;border-radius:5px;font:inherit;text-align:left;cursor:pointer}.picker-menu button:hover,.picker-menu button:focus-visible,.picker-menu button[aria-selected="true"]{color:var(--crm-teal);background:#eef6f5;outline:0}
</style>
