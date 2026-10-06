<script setup lang="ts">
import { computed } from 'vue'
import { Download, Eye, FileText } from '@lucide/vue'
import SectionCard from '@/design-system/SectionCard.vue'
import type { DemoWorkflowDto } from '@/types/workspaces'
import { formatDisplayDate } from '@/domain/time'
import { useI18n } from '@/i18n'

const props = defineProps<{ artifacts: NonNullable<DemoWorkflowDto['artifacts']> }>()
const { locale, t } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const emit = defineEmits<{ preview: [id: string]; download: [id: string] }>()
const reports = computed(() => props.artifacts.filter((item) => item.type === 'Test Report'))
const requests = computed(() => props.artifacts.filter((item) => item.type === 'Demo Request DOCX'))
const customerReports = computed(() => props.artifacts.filter((item) => item.type === 'Customer Report'))
// Retests never overwrite a previous round's file, so the round is what tells them apart.
const roundLabel = (round?: number) => round ? copy(`Round ${round}`, `第 ${round} 轮`) : ''
const previewable = (mime = '') => mime === 'application/pdf' || mime.startsWith('image/') || mime.startsWith('text/')
</script>

<template>
  <SectionCard :title="copy('Artifacts', '归档资料')" :subtitle="copy('Test Reports / Customer Reports / Demo Request Forms', '测试报告 / Customer 报告 / Demo Request 表单')" data-demo-article>
    <div class="groups">
      <section><header><FileText :size="15" /><strong>{{ copy('Test Reports', '测试报告') }}</strong><span>{{ reports.length }}</span></header><p v-if="!reports.length">{{ copy('No Test Reports.', '暂无测试报告。') }}</p><article v-for="item in reports" :key="item.id"><div><em>{{ item.visibility === 'Customer Review' ? copy('External', '外部') : copy('Internal', '内部') }}</em><strong>{{ item.fileName }}</strong><small><template v-if="item.round">{{ roundLabel(item.round) }} · </template>v{{ item.version }} · {{ item.createdBy || '—' }} · {{ formatDisplayDate(item.createdAt) }}</small></div><button v-if="previewable(item.mimeType)" type="button" :data-preview-artifact="item.id" @click="emit('preview', item.id)"><Eye :size="14" />{{ copy('Preview', '预览') }}</button><button type="button" :data-download-artifact="item.id" @click="emit('download', item.id)"><Download :size="14" />{{ copy('Download', '下载') }}</button></article></section>
      <section><header><FileText :size="15" /><strong>{{ t('customerReport.section') }}</strong><span>{{ customerReports.length }}</span></header><p v-if="!customerReports.length">{{ t('customerReport.empty') }}</p><article v-for="item in customerReports" :key="item.id"><div><em>{{ copy('Customer', '客户') }}</em><strong>{{ item.fileName }}</strong><small><template v-if="item.round">{{ roundLabel(item.round) }} · </template>v{{ item.version }} · {{ item.createdBy || '—' }} · {{ formatDisplayDate(item.createdAt) }}</small></div><button v-if="previewable(item.mimeType)" type="button" :data-preview-artifact="item.id" @click="emit('preview', item.id)"><Eye :size="14" />{{ copy('Preview', '预览') }}</button><button type="button" :data-download-artifact="item.id" @click="emit('download', item.id)"><Download :size="14" />{{ copy('Download', '下载') }}</button></article></section>
      <section><header><FileText :size="15" /><strong>{{ copy('Demo Request Forms', 'Demo Request 表单') }}</strong><span>{{ requests.length }}</span></header><p v-if="!requests.length">{{ copy('No Demo Request Forms.', '暂无 Demo Request 表单。') }}</p><article v-for="item in requests" :key="item.id"><div><strong>{{ item.fileName }}</strong><small><template v-if="item.round">{{ roundLabel(item.round) }} · </template>v{{ item.version }} · {{ item.createdBy || '—' }} · {{ formatDisplayDate(item.createdAt) }}</small></div><button v-if="previewable(item.mimeType)" type="button" :data-preview-artifact="item.id" @click="emit('preview', item.id)"><Eye :size="14" />{{ copy('Preview', '预览') }}</button><button type="button" :data-download-artifact="item.id" @click="emit('download', item.id)"><Download :size="14" />{{ copy('Download', '下载') }}</button></article></section>
    </div>
  </SectionCard>
</template>

<style scoped>
.groups{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.groups>section{overflow:hidden;border:1px solid var(--crm-line);border-radius:10px}.groups header{display:flex;align-items:center;gap:7px;padding:11px 13px;background:var(--crm-surface)}.groups header span{margin-left:auto;color:var(--crm-text-muted)}article{display:flex;align-items:center;gap:8px;padding:12px 13px;border-top:1px solid var(--crm-line)}article div{display:grid;flex:1;min-width:0;gap:4px}article div strong,article div small{overflow-wrap:anywhere}article em{width:max-content;padding:2px 5px;color:var(--crm-teal);background:var(--crm-teal-soft);border-radius:4px;font-size:8px;font-style:normal;font-weight:800}article small,p{color:var(--crm-text-muted);font-size:10px}article button{display:flex;flex:none;align-items:center;gap:4px;color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line);border-radius:7px;padding:6px 8px}p{margin:0;padding:18px;text-align:center}@media(max-width:1100px){.groups{grid-template-columns:1fr 1fr}}@media(max-width:760px){.groups{grid-template-columns:1fr}}
</style>
