<script setup lang="ts">
import { ArrowRight } from '@lucide/vue'
import { useI18n } from '@/i18n'

export type EvaluationView = 'overview' | 'wafer' | 'preparation' | 'execution' | 'internal' | 'customer'

defineProps<{ modelValue: EvaluationView }>()
defineEmits<{ 'update:modelValue': [view: EvaluationView] }>()

const flow = [
  { key: 'wafer', en: 'Wafer Preparation', zh: 'Wafer 准备' },
  { key: 'preparation', en: 'Test Preparation', zh: '测试准备' },
  { key: 'execution', en: 'Test Execution', zh: '测试执行' },
  { key: 'internal', en: 'Internal Review', zh: '内部评审' },
  { key: 'customer', en: 'Customer Review', zh: '客户评审' },
] as const
const { locale, t } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
</script>

<template>
  <nav class="evaluation-workspace-nav" :aria-label="t('evaluationNav.workspace')">
    <button
      type="button"
      data-evaluation-view="overview"
      :class="{ active: modelValue === 'overview' }"
      :aria-current="modelValue === 'overview' ? 'page' : undefined"
      @click="$emit('update:modelValue', 'overview')"
    >
      {{ copy('Demo Test', 'Demo 测试') }}
    </button>
    <span class="nav-divider" aria-hidden="true" />
    <span class="flow-label">{{ t('evaluationNav.flow') }}</span>
    <div class="flow-nodes">
      <!-- An arrow and the stage it points to wrap together: a row never ends on an arrow. -->
      <template v-for="(item, index) in flow" :key="item.key">
        <span class="flow-node">
          <ArrowRight v-if="index" data-evaluation-flow-arrow :size="17" aria-hidden="true" />
          <button
            type="button"
            :data-evaluation-view="item.key"
            :class="{ active: modelValue === item.key }"
            :aria-current="modelValue === item.key ? 'page' : undefined"
            @click="$emit('update:modelValue', item.key)"
          >
            {{ copy(item.en, item.zh) }}
          </button>
        </span>
      </template>
    </div>
  </nav>
</template>

<style scoped>
.evaluation-workspace-nav{display:grid;grid-template-columns:minmax(170px,220px) 1px auto minmax(0,1fr);align-items:center;gap:20px;margin-bottom:16px;padding:14px 0;border-top:1px solid var(--crm-line);border-bottom:1px solid var(--crm-line)}
button{min-height:42px;padding:0 18px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line-strong);border-radius:9px;font:inherit;font-size:12px;font-weight:700;cursor:pointer}
button:hover{border-color:#F3C173}.active{color:var(--crm-brand-ink);background:var(--crm-teal);border-color:var(--crm-teal);box-shadow:0 7px 18px rgba(254,153,0,.14)}
.nav-divider{width:1px;height:42px;background:var(--crm-line-strong)}.flow-label{color:var(--crm-text-muted);font-size:11px;font-weight:800;white-space:nowrap}
.flow-nodes{display:flex;min-width:0;flex-wrap:wrap;align-items:center;gap:9px}.flow-node{display:flex;min-width:0;flex:1 1 118px;align-items:center;gap:9px}.flow-node button{min-width:118px;flex:1 1 auto}.flow-nodes svg{flex:none;color:var(--crm-text-muted)}
@media(max-width:1280px){.evaluation-workspace-nav{grid-template-columns:minmax(170px,220px) 1px auto}.flow-nodes{grid-column:1/-1}}
</style>
