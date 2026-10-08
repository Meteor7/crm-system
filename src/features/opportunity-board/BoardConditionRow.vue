<script setup lang="ts">
import { useI18n } from '@/i18n'
import { condition, dateFields, fields, fieldLabel, fieldOptions, operators, operatorLabels, text } from './model'
import type { BoardCondition, BoardField, BoardFilters, BoardOperator } from './types'
import BoardMultiSelect from './BoardMultiSelect.vue'
const props = defineProps<{ modelValue: BoardCondition; filters: BoardFilters; index: number; match: 'all' | 'any' }>()
const emit = defineEmits<{ 'update:modelValue': [value: BoardCondition]; remove: [] }>()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
function value(next: BoardCondition['value']) { emit('update:modelValue', { ...props.modelValue, value: next }) }
function operator(next: BoardOperator) {
  const old = props.modelValue
  emit('update:modelValue', { ...old, operator: next, value: next === 'between' ? [String(Array.isArray(old.value) ? old.value[0] ?? '' : old.value), ''] : old.operator === 'between' ? (old.value as string[])[0] : old.value })
}
function bound(index: number, next: string) { const values = [...props.modelValue.value as string[]]; values[index] = next; value(values) }
</script>
<template>
  <div class="board-condition" :data-condition="index">
    <span class="condition-join">{{ index ? (match === 'all' ? 'AND' : 'OR') : copy('WHERE', '条件') }}</span>
    <select :value="modelValue.field" :aria-label="copy('Condition field', '条件字段')" @change="emit('update:modelValue', condition(($event.target as HTMLSelectElement).value as BoardField))">
      <option v-for="field in fields" :key="field" :value="field" :disabled="field === 'region' && !filters.regionReady">{{ fieldLabel(field, locale) }}</option>
    </select>
    <select :value="modelValue.operator" :aria-label="copy('Condition operator', '条件运算符')" @change="operator(($event.target as HTMLSelectElement).value as BoardOperator)">
      <option v-for="op in operators(modelValue.field)" :key="op" :value="op">{{ text(operatorLabels[op], locale) }}</option>
    </select>
    <BoardMultiSelect v-if="modelValue.operator === 'in' || modelValue.operator === 'not_in'" :model-value="modelValue.value as string[]" :options="fieldOptions(modelValue.field, filters, locale)" :label="copy('Condition values', '条件值')" :placeholder="copy('Select values…', '请选择…')" @update:model-value="value" />
    <div v-else-if="modelValue.operator === 'between'" class="condition-range">
      <input v-for="n in [0, 1]" :key="n" :value="(modelValue.value as string[])[n]" :type="dateFields.includes(modelValue.field) ? 'date' : 'text'" :inputmode="modelValue.field === 'amountCny' ? 'decimal' : undefined" :aria-label="n ? copy('Range end', '结束值') : copy('Range start', '起始值')" @input="bound(n, ($event.target as HTMLInputElement).value)" />
    </div>
    <input v-else :value="modelValue.value" :type="dateFields.includes(modelValue.field) ? 'date' : modelValue.field === 'stageAgeDays' ? 'number' : 'text'" :inputmode="modelValue.field === 'amountCny' ? 'decimal' : undefined" :min="modelValue.field === 'stageAgeDays' ? 0 : undefined" :max="modelValue.field === 'stageAgeDays' ? 36500 : undefined" maxlength="140" :aria-label="copy('Condition value', '条件值')" :placeholder="modelValue.field === 'amountCny' ? 'CNY' : ''" @input="value(modelValue.field === 'stageAgeDays' ? (($event.target as HTMLInputElement).value === '' ? '' : Number(($event.target as HTMLInputElement).value)) : ($event.target as HTMLInputElement).value)" />
    <button type="button" class="condition-remove" :aria-label="copy('Remove condition', '删除条件')" @click="emit('remove')">×</button>
  </div>
</template>

