<script setup lang="ts">
import { meetingParseMessage } from '@/features/visits/meeting-messages'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ArrowLeft, Download, FileUp, Pencil, Save, X } from '@lucide/vue'
import { useRoute } from 'vue-router'
import { api as defaultApi, type CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import { downloadBlob } from '@/features/shared/download-blob'
import { personnelDisplayName } from '@/demo/personnel'
import { formatDisplayDate } from '@/domain/time'
import { useI18n, useLocaleMessage } from '@/i18n'
import { useAppStore } from '@/stores/app'
import type { MeetingRecordParseStatus, VisitDetailDto, VisitMeetingRecordInput, VisitStatus } from '@/types/crm'
import DataState from '@/design-system/DataState.vue'
import PageHeader from '@/design-system/PageHeader.vue'
import SectionCard from '@/design-system/SectionCard.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import { meetingRecordParseLabel, salesEnumLabel } from '@/features/shared/sales-i18n'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const { locale, t } = useI18n()
const route = useRoute()
const app = useAppStore()
const detail = ref<VisitDetailDto | null>(null)
const loading = ref(true), busy = ref(false), error = useLocaleMessage(), requestId = ref(''), editing = ref(false)
const form = reactive<VisitMeetingRecordInput>({ meetingStart: '', meetingEnd: '', purpose: '', attendees: '', agenda: '', summary: '', conclusion: '', followup: '' })
const visitId = computed(() => typeof route.params.visitId === 'string' ? route.params.visitId : '')
const canWrite = computed(() => app.can('visit:write'))
const parseTone: Record<MeetingRecordParseStatus, 'positive' | 'warning' | 'neutral' | 'danger'> = { Parsed: 'positive', NeedsManualReview: 'warning', ArchiveOnly: 'neutral', Failed: 'danger' }
const visitStatusLabel: Record<VisitStatus, string> = { Planned: '待提交拜访记录', Visited: '已完成', 'Minutes Submitted': '拜访记录已提交', 'Manager Reviewed': '管理者已审核' }
function statusText(status: VisitStatus) {
  if (locale.value !== 'en-US') return visitStatusLabel[status]
  return ({ Planned: 'Minutes pending', Visited: 'Completed', 'Minutes Submitted': 'Minutes submitted', 'Manager Reviewed': 'Manager reviewed' } as Record<VisitStatus, string>)[status]
}
function parseText(status: MeetingRecordParseStatus) {
  return meetingRecordParseLabel(status, locale.value)
}
const notRecognized = computed(() => locale.value === 'en-US' ? 'Not recognized' : '未识别')

function fillForm() {
  const record = detail.value?.meetingRecord
  Object.assign(form, record ? { meetingStart: record.meetingStart, meetingEnd: record.meetingEnd, purpose: record.purpose, attendees: record.attendees, agenda: record.agenda, summary: record.summary, conclusion: record.conclusion, followup: record.followup } : { meetingStart: '', meetingEnd: '', purpose: detail.value?.objective ?? '', attendees: '', agenda: '', summary: '', conclusion: '', followup: '' })
}

async function load() {
  loading.value = true; error.value = ''
  try { detail.value = (await props.apiClient.getVisitDetail(visitId.value)).data; fillForm() }
  catch (reason) { const mapped = mapRequestError(reason); error.value = mapped.localizedMessage ?? mapped.message; requestId.value = mapped.requestId }
  finally { loading.value = false }
}

async function save() {
  busy.value = true; error.value = ''
  try {
    await props.apiClient.updateVisitMeetingRecord(visitId.value, { ...form }, detail.value?.meetingRecord?.modified)
    editing.value = false
    await load()
  } catch (reason) { const mapped = mapRequestError(reason); error.value = mapped.localizedMessage ?? mapped.message; requestId.value = mapped.requestId }
  finally { busy.value = false }
}

async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  busy.value = true; error.value = ''
  try {
    detail.value = (await props.apiClient.submitVisitRecord(visitId.value, { blob: file, fileName: file.name, mimeType: file.type || 'application/octet-stream', size: file.size })).data
    fillForm()
  } catch (reason) { const mapped = mapRequestError(reason); error.value = mapped.localizedMessage ?? mapped.message; requestId.value = mapped.requestId }
  finally { busy.value = false; input.value = '' }
}

async function download(fileId: string) {
  busy.value = true; error.value = ''
  try { const file = await props.apiClient.getVisitAttachment(fileId); downloadBlob(file.blob, file.fileName) }
  catch (reason) { const mapped = mapRequestError(reason); error.value = mapped.localizedMessage ?? mapped.message; requestId.value = mapped.requestId }
  finally { busy.value = false }
}

function cancelEdit() { editing.value = false; fillForm() }
onMounted(async () => { await app.loadBootstrap(props.apiClient); await load() })
watch(visitId, () => { void load() })
</script>

<template>
  <div class="visit-detail-page">
    <RouterLink class="back-link" :to="{ name: 'visits' }"><ArrowLeft :size="14" />{{ t('detail.backVisits') }}</RouterLink>
    <p v-if="error" class="form-error">{{ error }}<small v-if="requestId">{{ locale === 'en-US' ? 'Request ID' : '请求编号' }} {{ requestId }}</small></p>
    <DataState v-if="loading" type="loading" />
    <template v-else-if="detail">
      <PageHeader eyebrow="VISIT RECORD" :title="detail.subject" :description="`${detail.accountName} · ${formatDisplayDate(detail.date)} · ${salesEnumLabel(detail.type, locale)}`" />

      <section class="visit-facts">
        <div><small>{{ t('detail.account') }}</small><strong>{{ detail.accountName }}</strong></div>
        <div><small>{{ t('detail.visitOwner') }}</small><strong>{{ personnelDisplayName(detail.owner) }}</strong></div>
        <div><small>{{ t('detail.primaryContactLabel') }}</small><strong>{{ detail.primaryContact?.name || t('detail.notLinked') }}</strong></div>
        <div><small>{{ t('detail.visitStatus') }}</small><strong>{{ statusText(detail.status) }}</strong></div>
      </section>

      <div class="detail-grid">
        <main>
          <SectionCard :title="t('detail.visitRecord')" eyebrow="VISIT RECORD" :description="meetingParseMessage(detail.meetingRecord?.parseMessage || '', locale) || (locale === 'en-US' ? 'No visit record submitted yet. Upload a file or enter it manually.' : '尚未提交拜访记录，可提交文件或手动补录。')">
            <template #action>
              <div class="record-actions">
                <StatusBadge v-if="detail.meetingRecord" :label="parseText(detail.meetingRecord.parseStatus)" :tone="parseTone[detail.meetingRecord.parseStatus]" />
                <label v-if="canWrite && !editing && detail.status !== 'Manager Reviewed'" class="secondary-button upload-record-button" :class="{ disabled: busy }"><FileUp :size="13" />{{ t('detail.uploadParsed') }}<input type="file" :disabled="busy" :aria-label="t('detail.uploadParsed')" @change="upload" /></label>
                <button v-if="canWrite && !editing && detail.status !== 'Manager Reviewed'" class="secondary-button" type="button" @click="editing = true"><Pencil :size="13" />{{ detail.meetingRecord ? t('detail.editRecord') : t('detail.manualEntry') }}</button>
              </div>
            </template>

            <form v-if="editing" class="record-form" @submit.prevent="save">
              <label><span>{{ t('detail.startTime') }}</span><input v-model="form.meetingStart" /></label>
              <label><span>{{ t('detail.endTime') }}</span><input v-model="form.meetingEnd" /></label>
              <label class="wide"><span>{{ t('detail.meetingPurpose') }}</span><textarea v-model="form.purpose" required /></label>
              <label class="wide"><span>{{ t('detail.attendees') }}</span><textarea v-model="form.attendees" required /></label>
              <label class="wide"><span>{{ t('detail.agenda') }}</span><textarea v-model="form.agenda" required /></label>
              <label class="wide"><span>{{ t('detail.summary') }}</span><textarea v-model="form.summary" required /></label>
              <label class="wide"><span>{{ t('detail.conclusion') }}</span><textarea v-model="form.conclusion" required /></label>
              <label class="wide"><span>{{ t('detail.followup') }}</span><textarea v-model="form.followup" required /></label>
              <div class="wide form-actions"><button class="secondary-button" type="button" :disabled="busy" @click="cancelEdit"><X :size="14" />{{ t('detail.cancel') }}</button><button class="primary-button" type="submit" :disabled="busy"><Save :size="14" />{{ t('detail.saveVisitRecord') }}</button></div>
            </form>

            <dl v-else-if="detail.meetingRecord" class="record-fields">
              <div><dt>{{ locale === 'en-US' ? 'Meeting time' : '会议时间' }}</dt><dd>{{ [detail.meetingRecord.meetingStart, detail.meetingRecord.meetingEnd].filter(Boolean).join(' - ') || notRecognized }}</dd></div>
              <div><dt>{{ locale === 'en-US' ? 'Meeting purpose' : '会议目的' }}</dt><dd>{{ detail.meetingRecord.purpose || notRecognized }}</dd></div>
              <div><dt>{{ locale === 'en-US' ? 'Attendees' : '参与人' }}</dt><dd>{{ detail.meetingRecord.attendees || notRecognized }}</dd></div>
              <div><dt>{{ locale === 'en-US' ? 'Agenda' : '议程' }}</dt><dd>{{ detail.meetingRecord.agenda || notRecognized }}</dd></div>
              <div><dt>{{ locale === 'en-US' ? 'Summary' : '总结' }}</dt><dd>{{ detail.meetingRecord.summary || notRecognized }}</dd></div>
              <div><dt>{{ locale === 'en-US' ? 'Conclusion' : '结论' }}</dt><dd>{{ detail.meetingRecord.conclusion || notRecognized }}</dd></div>
              <div><dt>{{ locale === 'en-US' ? 'Follow-up' : '后续行动' }}</dt><dd>{{ detail.meetingRecord.followup || notRecognized }}</dd></div>
            </dl>
            <div v-else class="empty-record">{{ t('detail.noMeetingRecord') }}</div>
          </SectionCard>
        </main>

        <aside>
          <SectionCard :title="t('detail.sourceFiles')" eyebrow="SOURCE FILES">
            <div v-if="detail.attachments.length" class="file-list">
              <article v-for="file in detail.attachments" :key="file.id"><div><strong>{{ file.fileName }}</strong><small>{{ Math.max(1, Math.ceil(file.size / 1024)) }} KB · {{ formatDisplayDate(file.uploadedAt) }}</small></div><button type="button" :disabled="busy" :title="t('detail.downloadSource')" @click="download(file.id)"><Download :size="15" /></button></article>
            </div>
            <p v-else class="empty-files">{{ t('detail.noArchivedFiles') }}</p>
          </SectionCard>
          <SectionCard :title="t('detail.visitObjective')" eyebrow="OBJECTIVE"><p class="objective">{{ detail.objective }}</p></SectionCard>
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
.visit-detail-page{display:grid;gap:14px}.back-link{display:inline-flex;align-items:center;gap:5px;justify-self:start;color:var(--crm-teal);font-size:10px;font-weight:750}.form-error{display:flex;justify-content:space-between;padding:10px 12px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px}.visit-detail-page :deep(.page-header){margin-bottom:0}.visit-facts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border-block:1px solid var(--crm-line);background:#fff}.visit-facts div{display:grid;gap:5px;padding:14px 18px;border-right:1px solid var(--crm-line)}.visit-facts div:last-child{border-right:0}.visit-facts small{color:var(--crm-text-muted);font-size:9px}.visit-facts strong{color:var(--crm-navy);font-size:11px}.detail-grid{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:14px;align-items:start}.detail-grid main,.detail-grid aside{display:grid;gap:14px}.detail-grid aside{position:sticky;top:16px}.record-actions{display:flex;align-items:center;gap:8px}.secondary-button,.primary-button{display:inline-flex;align-items:center;justify-content:center;gap:6px}.upload-record-button{cursor:pointer}.upload-record-button input{display:none}.upload-record-button.disabled{opacity:.55;pointer-events:none}.record-fields{display:grid;margin:0}.record-fields div{display:grid;grid-template-columns:150px minmax(0,1fr);gap:18px;padding:15px 0;border-bottom:1px solid var(--crm-line)}.record-fields div:last-child{border-bottom:0}.record-fields dt{color:var(--crm-text-muted);font-size:10px;font-weight:750}.record-fields dd{margin:0;color:var(--crm-navy);font-size:11px;line-height:1.7;white-space:pre-wrap}.record-form{display:grid;grid-template-columns:1fr 1fr;gap:12px}.record-form label{display:grid;gap:6px}.record-form .wide{grid-column:1/-1}.record-form span{color:var(--crm-text-muted);font-size:9px;font-weight:750}.record-form input,.record-form textarea{width:100%;padding:9px 10px;border:1px solid var(--crm-line);border-radius:7px;outline:0}.record-form textarea{min-height:86px;resize:vertical}.record-form :focus{border-color:var(--crm-teal)}.form-actions{display:flex;justify-content:flex-end;gap:8px}.file-list{display:grid}.file-list article{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:11px 0;border-bottom:1px solid var(--crm-line)}.file-list article:last-child{border-bottom:0}.file-list div{display:grid;min-width:0;gap:4px}.file-list strong{overflow:hidden;color:var(--crm-navy);font-size:10px;text-overflow:ellipsis;white-space:nowrap}.file-list small{color:var(--crm-text-muted);font-size:8px}.file-list button{display:grid;width:30px;height:30px;flex:0 0 auto;place-items:center;color:var(--crm-teal);background:transparent;border:0;cursor:pointer}.empty-record,.empty-files{margin:0;padding:22px 0;color:var(--crm-text-muted);font-size:10px;text-align:center}.objective{margin:0;color:var(--crm-text);font-size:11px;line-height:1.7}@media(max-width:900px){.visit-facts{grid-template-columns:1fr 1fr}.visit-facts div:nth-child(2){border-right:0}.detail-grid{grid-template-columns:1fr}.detail-grid aside{position:static}}@media(max-width:560px){.visit-facts,.record-form{grid-template-columns:1fr}.visit-facts div{border-right:0}.record-form .wide{grid-column:auto}.record-fields div{grid-template-columns:1fr;gap:6px}}
</style>
