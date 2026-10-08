<script setup lang="ts">
import { useI18n } from '@/i18n'
import { condition } from './model'
import type { BoardFilters, BoardNode, BoardConditionGroup } from './types'
import BoardConditionRow from './BoardConditionRow.vue'
const props = defineProps<{ modelValue: BoardNode[]; filters: BoardFilters; match: 'all' | 'any'; depth: number; total: number }>()
const emit = defineEmits<{ 'update:modelValue': [value: BoardNode[]] }>()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
function replace(index: number, value: BoardNode) { emit('update:modelValue', props.modelValue.map((node, i) => i === index ? value : node)) }
function remove(index: number) { emit('update:modelValue', props.modelValue.filter((_, i) => i !== index)) }
function add(index: number, group: BoardConditionGroup, nested: boolean) {
  replace(index, { ...group, conditions: [...group.conditions, nested ? { match: 'any', conditions: [condition()] } : condition()] })
}
</script>
<template>
  <template v-for="(node, index) in modelValue" :key="index">
    <section v-if="'conditions' in node" class="board-condition-group" :data-group-depth="depth + 1">
      <header>
        <span>{{ index ? (match === 'all' ? 'AND' : 'OR') : copy('WHERE', '条件') }} (</span>
        <select :value="node.match" :aria-label="copy('Group logic', '条件组逻辑')" @change="replace(index, { ...node, match: ($event.target as HTMLSelectElement).value as 'all' | 'any' })"><option value="all">AND</option><option value="any">OR</option></select>
        <button :disabled="total >= 30" data-add-group-condition @click="add(index, node, false)">{{ copy('Add condition', '添加条件') }}</button>
        <button v-if="depth + 1 < 3" :disabled="total >= 30" data-add-nested-group @click="add(index, node, true)">{{ copy('Add group', '添加条件组') }}</button>
        <button :aria-label="copy('Remove group', '删除条件组')" @click="remove(index)">×</button>
      </header>
      <BoardConditionGroupEditor :model-value="node.conditions" :filters="filters" :match="node.match" :depth="depth + 1" :total="total" @update:model-value="replace(index, { ...node, conditions: $event })" />
      <span>)</span>
    </section>
    <BoardConditionRow v-else :model-value="node" :filters="filters" :index="index" :match="match" @update:model-value="replace(index, $event)" @remove="remove(index)" />
  </template>
</template>
