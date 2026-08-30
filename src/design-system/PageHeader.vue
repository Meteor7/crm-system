<script setup lang="ts">
import { formatDisplayDate } from '@/domain/time'
defineProps<{ eyebrow?: string; title: string; description: string; updatedAt?: string }>()
</script>

<template>
  <header class="page-header">
    <div>
      <span v-if="eyebrow" class="page-eyebrow">{{ eyebrow }}</span>
      <h1>{{ title }}</h1>
      <p>{{ description }}</p>
      <small v-if="updatedAt">数据截至 {{ formatDisplayDate(updatedAt) }}</small>
    </div>
    <div class="page-actions"><slot /></div>
  </header>
</template>

<style scoped>
.page-header { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; margin-bottom: 24px; }
.page-eyebrow { color: var(--crm-teal); font-size: 10px; font-weight: 800; letter-spacing: .13em; text-transform: uppercase; }
h1 { margin: 5px 0 7px; color: var(--crm-navy); font-size: clamp(25px, 2.4vw, 34px); line-height: 1.15; letter-spacing: -.035em; }
p { max-width: 720px; margin: 0; color: var(--crm-text-muted); font-size: 13px; line-height: 1.65; }
small { display: inline-block; margin-top: 7px; color: #90a0a3; font-size: 10px; }
.page-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 9px; }
@media (max-width: 700px) { .page-header { align-items: flex-start; flex-direction: column; } .page-actions { width: 100%; justify-content: flex-start; } }
</style>
