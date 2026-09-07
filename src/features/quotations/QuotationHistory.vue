<script setup lang="ts">
import { Download, Eye } from '@lucide/vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import type { QuotationVersionDto } from './types'
import { formatDisplayDate } from '@/domain/time'
import { localeMessage, useI18n } from '@/i18n'
defineProps<{ versions: QuotationVersionDto[]; selectedId: string }>()
defineEmits<{ select:[id:string]; download:[id:string] }>()
const { locale } = useI18n()
const ui = (english: string, chinese: string) => localeMessage(english, chinese)[locale.value]
const statusLabel = (value: QuotationVersionDto['status']) => ({ Draft: ui('Draft', '草稿'), Published: ui('Published', '已发布'), Accepted: ui('Accepted', '已接受'), Rejected: ui('Rejected', '已驳回'), Expired: ui('Expired', '已过期'), Superseded: ui('Superseded', '已被替代') }[value])
</script>
<template><div class="version-history"><div v-for="item in versions" :key="item.id" class="history-row" :class="{selected:item.id===selectedId}"><div><strong>V{{ item.version }}</strong><StatusBadge :label="statusLabel(item.status)" :tone="item.status==='Accepted'?'positive':item.status==='Rejected'?'danger':item.status==='Published'?'info':'neutral'" /><small>{{ formatDisplayDate(item.publishedAt || item.modified) }}</small></div><div class="actions"><button type="button" :aria-label="ui(`View V${item.version}`, `查看 V${item.version}`)" @click="$emit('select',item.id)"><Eye :size="14" /></button><button v-if="item.pdfAvailable" type="button" :aria-label="ui(`Download V${item.version}`, `下载 V${item.version}`)" @click="$emit('download',item.id)"><Download :size="14" /></button></div></div></div></template>
<style scoped>.version-history{display:grid;gap:8px}.history-row{display:flex;align-items:center;justify-content:space-between;padding:10px 12px;background:#f7f9f9;border:1px solid var(--crm-line);border-radius:9px}.history-row.selected{border-color:#7aa9a5;background:#eff7f6}.history-row>div:first-child{display:flex;align-items:center;gap:8px}.history-row small{color:var(--crm-muted)}.actions{display:flex;gap:5px}.actions button{display:grid;width:30px;height:30px;place-items:center;background:#fff;border:1px solid var(--crm-line);border-radius:7px;cursor:pointer}</style>
