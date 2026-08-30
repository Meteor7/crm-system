<script setup lang="ts">
import { AlertTriangle, Ban, Inbox, LoaderCircle, RefreshCw } from '@lucide/vue'

withDefaults(defineProps<{ type: 'loading' | 'empty' | 'error' | 'denied'; title?: string; message?: string; requestId?: string }>(), {
  title: '', message: '', requestId: '',
})
defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="data-state" :class="`state-${type}`" role="status">
    <LoaderCircle v-if="type === 'loading'" class="spin" :size="28" />
    <Inbox v-else-if="type === 'empty'" :size="28" />
    <AlertTriangle v-else-if="type === 'error'" :size="28" />
    <Ban v-else :size="28" />
    <strong>{{ title || ({ loading: '正在读取经营数据', empty: '当前没有匹配记录', error: '数据暂时无法加载', denied: '你没有查看权限' }[type]) }}</strong>
    <p>{{ message || ({ loading: '正在同步客户、商机与情报口径…', empty: '调整筛选条件，或创建第一条业务记录。', error: '请稍后重试；若持续失败，请提供请求编号。', denied: '如需访问，请联系 CRM 管理员调整数据范围。' }[type]) }}</p>
    <small v-if="requestId">Request ID · {{ requestId }}</small>
    <button v-if="type === 'error'" type="button" @click="$emit('retry')"><RefreshCw :size="14" />重试</button>
  </div>
</template>

<style scoped>
.data-state { display: grid; min-height: 260px; place-items: center; align-content: center; gap: 9px; padding: 34px; color: var(--crm-text-muted); text-align: center; }
.data-state svg { color: var(--crm-teal); }
.state-error svg { color: var(--crm-danger); }
.state-denied svg { color: var(--crm-warning); }
strong { color: var(--crm-navy); font-size: 14px; }
p { max-width: 420px; margin: 0; font-size: 11px; line-height: 1.6; }
small { font-family: ui-monospace, monospace; font-size: 9px; }
button { display: flex; align-items: center; gap: 6px; margin-top: 5px; padding: 8px 12px; color: var(--crm-brand-ink); background: var(--crm-teal); border: 0; border-radius: 8px; cursor: pointer; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
