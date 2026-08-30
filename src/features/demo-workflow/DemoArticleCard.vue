<script setup lang="ts">
import { computed } from 'vue'
import { Download, Eye, FileText } from '@lucide/vue'
import SectionCard from '@/design-system/SectionCard.vue'
import type { DemoWorkflowDto } from '@/types/workspaces'
import { formatDisplayDate } from '@/domain/time'

const props = defineProps<{ artifacts: NonNullable<DemoWorkflowDto['artifacts']> }>()
const emit = defineEmits<{ preview: [id: string]; download: [id: string] }>()
const reports = computed(() => props.artifacts.filter((item) => item.type === 'Test Report'))
const requests = computed(() => props.artifacts.filter((item) => item.type === 'Demo Request DOCX'))
const previewable = (mime = '') => mime === 'application/pdf' || mime.startsWith('image/') || mime.startsWith('text/')
</script>

<template>
  <SectionCard title="Article" subtitle="Test Reports / Demo Request Forms" data-demo-article>
    <div class="groups">
      <section><header><FileText :size="15" /><strong>Test Reports</strong><span>{{ reports.length }}</span></header><p v-if="!reports.length">暂无 Test Report。</p><article v-for="item in reports" :key="item.id"><div><em>{{ item.visibility === 'Customer Review' ? 'External' : 'Internal' }}</em><strong>{{ item.fileName }}</strong><small>v{{ item.version }} · {{ item.createdBy || '—' }} · {{ formatDisplayDate(item.createdAt) }}</small></div><button v-if="previewable(item.mimeType)" type="button" :data-preview-artifact="item.id" @click="emit('preview', item.id)"><Eye :size="14" />预览</button><button type="button" :data-download-artifact="item.id" @click="emit('download', item.id)"><Download :size="14" />下载</button></article></section>
      <section><header><FileText :size="15" /><strong>Demo Request Forms</strong><span>{{ requests.length }}</span></header><p v-if="!requests.length">暂无 Demo Request Form。</p><article v-for="item in requests" :key="item.id"><div><strong>{{ item.fileName }}</strong><small>v{{ item.version }} · {{ item.createdBy || '—' }} · {{ formatDisplayDate(item.createdAt) }}</small></div><button v-if="previewable(item.mimeType)" type="button" :data-preview-artifact="item.id" @click="emit('preview', item.id)"><Eye :size="14" />预览</button><button type="button" :data-download-artifact="item.id" @click="emit('download', item.id)"><Download :size="14" />下载</button></article></section>
    </div>
  </SectionCard>
</template>

<style scoped>
.groups{display:grid;grid-template-columns:1fr 1fr;gap:12px}.groups>section{overflow:hidden;border:1px solid var(--crm-line);border-radius:10px}.groups header{display:flex;align-items:center;gap:7px;padding:11px 13px;background:var(--crm-surface)}.groups header span{margin-left:auto;color:var(--crm-text-muted)}article{display:flex;align-items:center;gap:8px;padding:12px 13px;border-top:1px solid var(--crm-line)}article div{display:grid;flex:1;gap:4px}article em{width:max-content;padding:2px 5px;color:var(--crm-teal);background:var(--crm-teal-soft);border-radius:4px;font-size:8px;font-style:normal;font-weight:800}article small,p{color:var(--crm-text-muted);font-size:10px}article button{display:flex;align-items:center;gap:4px;color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line);border-radius:7px;padding:6px 8px}p{margin:0;padding:18px;text-align:center}@media(max-width:760px){.groups{grid-template-columns:1fr}}
</style>
