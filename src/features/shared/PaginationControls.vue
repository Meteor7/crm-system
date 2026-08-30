<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ page: number; pageSize: number; total: number }>()
const emit = defineEmits<{ change: [page: number]; 'page-size-change': [pageSize: number] }>()
const totalPages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))
const pageSizeOptions = computed(() => [...new Set([props.pageSize, 10, 25, 50])].sort((left, right) => left - right))
function move(target: number) {
  if (target >= 1 && target <= totalPages.value && target !== props.page) emit('change', target)
}
function changePageSize(event: Event) {
  const value = Number((event.target as HTMLSelectElement).value)
  if (value !== props.pageSize) emit('page-size-change', value)
}
</script>

<template>
  <nav class="pagination-controls" aria-label="列表分页">
    <button type="button" data-page-previous :disabled="page <= 1" @click="move(page - 1)">上一页</button>
    <span>第 {{ page }} / {{ totalPages }} 页</span>
    <small>共 {{ total }} 条</small>
    <label>每页<select :value="pageSize" aria-label="每页数量" @change="changePageSize"><option v-for="size in pageSizeOptions" :key="size" :value="size">{{ size }}</option></select></label>
    <button type="button" data-page-next :disabled="page >= totalPages" @click="move(page + 1)">下一页</button>
  </nav>
</template>

<style scoped>
.pagination-controls{display:flex;align-items:center;justify-content:flex-end;gap:10px;padding:12px 14px;color:var(--crm-text-muted);background:#fff;border-top:1px solid var(--crm-line);font-size:9px}.pagination-controls small{margin-right:auto}.pagination-controls label{display:flex;align-items:center;gap:5px}.pagination-controls select,.pagination-controls button{min-height:32px;padding:0 11px;color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line);border-radius:8px;font:inherit;font-weight:800}.pagination-controls button{cursor:pointer}.pagination-controls button:disabled{color:var(--crm-text-muted);background:var(--crm-surface);cursor:not-allowed}@media(max-width:560px){.pagination-controls{flex-wrap:wrap;justify-content:center}.pagination-controls small{width:100%;margin:0;text-align:center}}
</style>
