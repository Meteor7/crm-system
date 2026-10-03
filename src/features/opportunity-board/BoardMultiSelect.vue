<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from '@/i18n'
import type { BoardOption } from './types'
const props = defineProps<{ modelValue: string[]; options: BoardOption[]; label: string; placeholder: string; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()
const { locale } = useI18n()
const root = ref<HTMLDetailsElement | null>(null)
const search = ref('')
const selected = computed(() => props.modelValue.map(value => props.options.find(o => o.value === value)?.label ?? value))
const options = computed(() => {
  const missing: BoardOption[] = props.modelValue.filter(v => !props.options.some(o => o.value === v)).map(v => ({ value: v, label: v }))
  return [...props.options, ...missing].filter(o => o.label.toLocaleLowerCase().includes(search.value.toLocaleLowerCase()))
})
function toggle(value: string, checked: boolean) { emit('update:modelValue', checked ? [...props.modelValue, value] : props.modelValue.filter(v => v !== value)) }
function outside(event: MouseEvent) { if (root.value && !root.value.contains(event.target as Node)) root.value.open = false }
function close() { if (root.value) { root.value.open = false; root.value.querySelector('summary')?.focus() } }
onMounted(() => document.addEventListener('click', outside))
onBeforeUnmount(() => document.removeEventListener('click', outside))
</script>
<template>
  <details ref="root" class="board-multiselect" @keydown.esc.stop.prevent="close">
    <summary :aria-label="label" :aria-disabled="disabled" :title="selected.join(', ')" @click="disabled && $event.preventDefault()">
      <span>{{ selected.length ? selected.join(' · ') : placeholder }}</span><span aria-hidden="true">▾</span>
    </summary>
    <div class="board-options" :aria-label="label">
      <input v-model="search" type="search" :aria-label="locale === 'en-US' ? 'Search options' : '搜索选项'" :placeholder="locale === 'en-US' ? 'Search…' : '搜索…'" />
      <button v-if="modelValue.length" type="button" @click="emit('update:modelValue', [])">{{ locale === 'en-US' ? 'Clear selection' : '清空选择' }}</button>
      <label v-for="option in options" :key="option.value"><input type="checkbox" :checked="modelValue.includes(option.value)" @change="toggle(option.value, ($event.target as HTMLInputElement).checked)" /><span :style="option.depth ? { paddingLeft: `${option.depth * 14}px` } : undefined">{{ option.label }}</span></label>
      <p v-if="!options.length">{{ locale === 'en-US' ? 'No options' : '暂无选项' }}</p>
    </div>
  </details>
</template>

