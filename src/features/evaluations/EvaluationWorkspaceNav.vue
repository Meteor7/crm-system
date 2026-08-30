<script setup lang="ts">
import { ArrowRight } from '@lucide/vue'

export type EvaluationView = 'overview' | 'wafer' | 'preparation' | 'execution' | 'internal' | 'customer'

defineProps<{ modelValue: EvaluationView }>()
defineEmits<{ 'update:modelValue': [view: EvaluationView] }>()

const flow = [
  { key: 'wafer', label: 'Wafer Preparation' },
  { key: 'preparation', label: 'Test Preparation' },
  { key: 'execution', label: 'Test Execution' },
  { key: 'internal', label: 'Internal Review' },
  { key: 'customer', label: 'Customer Review' },
] as const
</script>

<template>
  <nav class="evaluation-workspace-nav" aria-label="Demo Test 工作区">
    <button
      type="button"
      data-evaluation-view="overview"
      :class="{ active: modelValue === 'overview' }"
      :aria-current="modelValue === 'overview' ? 'page' : undefined"
      @click="$emit('update:modelValue', 'overview')"
    >
      Demo Test
    </button>
    <span class="nav-divider" aria-hidden="true" />
    <span class="flow-label">处理流程</span>
    <div class="flow-nodes">
      <template v-for="(item, index) in flow" :key="item.key">
        <ArrowRight v-if="index" data-evaluation-flow-arrow :size="17" aria-hidden="true" />
        <button
          type="button"
          :data-evaluation-view="item.key"
          :class="{ active: modelValue === item.key }"
          :aria-current="modelValue === item.key ? 'page' : undefined"
          @click="$emit('update:modelValue', item.key)"
        >
          {{ item.label }}
        </button>
      </template>
    </div>
  </nav>
</template>

<style scoped>
.evaluation-workspace-nav{display:grid;grid-template-columns:minmax(170px,220px) 1px auto minmax(0,1fr);align-items:center;gap:20px;margin-bottom:16px;padding:14px 0;border-top:1px solid var(--crm-line);border-bottom:1px solid var(--crm-line)}
button{min-height:42px;padding:0 18px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line-strong);border-radius:9px;font:inherit;font-size:12px;font-weight:700;cursor:pointer}
button:hover{border-color:#F3C173}.active{color:var(--crm-brand-ink);background:var(--crm-teal);border-color:var(--crm-teal);box-shadow:0 7px 18px rgba(254,153,0,.14)}
.nav-divider{width:1px;height:42px;background:var(--crm-line-strong)}.flow-label{color:var(--crm-text-muted);font-size:11px;font-weight:800;white-space:nowrap}
.flow-nodes{display:flex;min-width:0;align-items:center;gap:9px}.flow-nodes button{min-width:118px;flex:1}.flow-nodes svg{flex:none;color:var(--crm-text-muted)}
</style>
