<script setup lang="ts">
import { useI18n } from '@/i18n'
defineProps<{ src: string }>()
const { locale } = useI18n()
</script>

<template>
  <iframe
    class="quotation-preview"
    data-testid="quotation-preview"
    :title="locale === 'en-US' ? 'Quotation PDF preview' : '报价单 PDF 预览'"
    :src="src"
  />
</template>

<style scoped>
.quotation-preview{display:block;width:100%;min-height:820px;background:#fff;border:1px solid #dfe3ec;border-radius:2px;box-shadow:0 14px 30px rgba(21,35,61,.08)}
</style>
