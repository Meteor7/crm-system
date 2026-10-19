<script setup lang="ts">
import { ArrowRight } from '@lucide/vue'
import { useI18n } from '@/i18n'

export type DemoRequestView = 'overview' | 'sales' | 'engineer' | 'manager'

defineProps<{ modelValue: DemoRequestView }>()
defineEmits<{ 'update:modelValue': [view: DemoRequestView] }>()

const flow = [
  { key: 'sales', en: 'Sales Preparation', zh: 'Sales 准备' },
  { key: 'engineer', en: 'Engineer Review', zh: '工程评估' },
  { key: 'manager', en: 'Manager Approval', zh: '经理审批' },
] as const
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
</script>

<template>
  <nav class="request-workspace-nav" :aria-label="locale === 'en-US' ? 'Demo Request workspace' : 'Demo Request 工作区'">
    <button
      type="button"
      data-demo-view="overview"
      :class="{ active: modelValue === 'overview' }"
      :aria-current="modelValue === 'overview' ? 'page' : undefined"
      @click="$emit('update:modelValue', 'overview')"
    >
      {{ copy('Demo Request', 'Demo Request') }}
    </button>
    <span class="nav-divider" aria-hidden="true" />
    <span class="flow-label">{{ locale === 'en-US' ? 'Workflow' : '处理流程' }}</span>
    <div class="flow-nodes">
      <template v-for="(item, index) in flow" :key="item.key">
        <ArrowRight v-if="index" data-demo-flow-arrow :size="17" aria-hidden="true" />
        <button
          type="button"
          :data-demo-view="item.key"
          :class="{ active: modelValue === item.key }"
          :aria-current="modelValue === item.key ? 'page' : undefined"
          @click="$emit('update:modelValue', item.key)"
        >
          {{ copy(item.en, item.zh) }}
        </button>
      </template>
    </div>
  </nav>
</template>

<style scoped>
.request-workspace-nav{display:grid;grid-template-columns:minmax(170px,220px) 1px auto minmax(0,1fr);align-items:center;gap:20px;margin-bottom:16px;padding:14px 0;border-top:1px solid var(--crm-line);border-bottom:1px solid var(--crm-line)}
button{min-height:42px;padding:0 18px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line-strong);border-radius:9px;font:inherit;font-size:12px;font-weight:700;cursor:pointer}
button:hover{border-color:#A8BAEF}.active{color:var(--crm-on-brand);background:var(--crm-teal);border-color:var(--crm-teal);box-shadow:0 7px 18px rgba(49, 89, 206,.14)}
.nav-divider{width:1px;height:42px;background:var(--crm-line-strong)}.flow-label{color:var(--crm-text-muted);font-size:11px;font-weight:800;white-space:nowrap}
.flow-nodes{display:grid;grid-template-columns:minmax(150px,1fr) auto minmax(150px,1fr) auto minmax(150px,1fr);align-items:center;gap:12px}.flow-nodes svg{color:var(--crm-text-muted)}
@media(max-width:1050px){.request-workspace-nav{grid-template-columns:1fr}.nav-divider{display:none}.flow-nodes{overflow-x:auto}.flow-label{display:none}}
</style>
