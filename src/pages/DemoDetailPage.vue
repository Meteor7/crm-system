<script setup lang="ts">
import { participantRoleLabel } from '@/features/shared/sales-i18n'
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft, MessageSquareText, UsersRound } from '@lucide/vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api as defaultApi, type CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import { useNotificationStore } from '@/stores/notifications'
import type { DemoCommentDto, DemoWorkflowDto } from '@/types/workspaces'
import DataState from '@/design-system/DataState.vue'
import DemoArchiveDetail from '@/features/demo-workflow/DemoArchiveDetail.vue'
import DemoCommentPanel from '@/features/demo-workflow/DemoCommentPanel.vue'
import DemoProjectTimeline from '@/features/demo-workflow/DemoProjectTimeline.vue'
import { downloadBlob } from '@/features/shared/download-blob'
import { readAllPages } from '@/features/shared/read-all-pages'
import { PERSONNEL, personnelById, personnelDisplayName } from '@/demo/personnel'
import { useI18n, useLocaleMessage } from '@/i18n'

type DetailTab = 'information' | 'comment'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const route = useRoute()
const router = useRouter()
const app = useAppStore()
const { locale, t } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const statusLabel = (status: string) => copy(status, ({ Requested: '已申请', 'Scope Confirmed': '范围已确认', 'Sample Received': '样品已收到', Scheduled: '已排期', Testing: '测试中', Analysis: '分析中', 'Internal Review': '内部评审', 'Customer Review': '客户评审', Accepted: '已接受', Rejected: '已拒绝' } as Record<string, string>)[status] || status)
const notifications = useNotificationStore()
const project = ref<DemoWorkflowDto | null>(null)
const comments = ref<DemoCommentDto[]>([])
const loading = ref(true)
const error = useLocaleMessage()
const requestId = ref('')
const denied = ref(false)
const commentBusy = ref(false)
const commentError = useLocaleMessage()
const artifactBusyId = ref(''), artifactError = useLocaleMessage(), artifactRequestId = ref('')
let loadSequence = 0
const tab = computed<DetailTab>(() => route.query.tab === 'comment' ? 'comment' : 'information')
const demoId = computed(() => String(route.params.demoId || ''))
const createdDate = computed(() => project.value?.projectTimeline?.find((step) => step.key === 'sales-preparation')?.date || '—')
const participants = computed(() => project.value
  ? [
      { name: personnelDisplayName(project.value.salesOwner), role: 'Sales' },
      { name: personnelDisplayName(project.value.engineerOwner), role: 'Engineer' },
      ...project.value.approvals
        .filter((item) => item.actor && ![project.value!.salesOwner, project.value!.engineerOwner].includes(item.actor))
        .map((item) => ({ name: personnelDisplayName(item.actor), role: item.label })),
    ].filter((item, index, rows) => rows.findIndex((candidate) => candidate.name === item.name) === index)
  : [])
const mentionParticipants = computed(() => {
  if (!project.value) return []
  const participantIds = [
    project.value.salesOwner,
    project.value.engineerOwner,
    ...project.value.approvals.map((item) => item.actor),
    ...PERSONNEL.filter((person) => person.role === 'Manager').map((person) => person.id),
  ].filter(Boolean)
  return [...new Set(participantIds)].map((id) => ({ id, name: personnelDisplayName(id) }))
})
const backTarget = computed(() => {
  if (route.query.from === 'demo-requests') return { name: 'demo-requests' }
  if (route.query.from === 'evaluations') return { name: 'evaluations' }
  const { from: _from, tab: _tab, ...query } = route.query
  return {
    name: 'demo-workflow',
    query: Object.keys(query).length ? query : { surface: 'project' },
  }
})

function loadAllComments(projectId: string) {
  return readAllPages((page, pageSize) => props.apiClient.listDemoComments(projectId, { page, pageSize }))
}

async function load() {
  const sequence = ++loadSequence
  loading.value = true
  error.value = ''
  denied.value = false
  try {
    await app.loadBootstrap(props.apiClient)
    const workflow = await props.apiClient.getDemoWorkflow(demoId.value)
    if (sequence !== loadSequence) return
    project.value = workflow.data
    try {
      const allComments = await loadAllComments(project.value.id)
      if (sequence !== loadSequence) return
      comments.value = allComments
    } catch (reason) {
      const mapped = mapRequestError(reason)
      commentError.value = mapped.localizedMessage ?? mapped.message
    }
  } catch (reason) {
    if (sequence !== loadSequence) return
    const mapped = mapRequestError(reason)
    error.value = mapped.localizedMessage ?? mapped.message
    requestId.value = mapped.requestId
    denied.value = mapped.denied
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

async function switchTab(next: DetailTab) {
  await router.replace({
    name: 'demo-detail',
    params: { demoId: demoId.value },
    query: { ...route.query, tab: next },
  })
}

async function publishComment(payload: { body: string; mentions: string[] }) {
  if (!project.value) return
  commentBusy.value = true
  commentError.value = ''
  try {
    await props.apiClient.addDemoComment(project.value.id, {
      body: payload.body,
      mentionedPersonIds: payload.mentions,
    })
    comments.value = await loadAllComments(project.value.id)
    for (const mention of payload.mentions) {
      const mentionedPerson = personnelById(mention)
      if (!mentionedPerson) continue
      notifications.add({
        category: 'Demo',
        recipient: mentionedPerson.name,
        recipientId: mentionedPerson.id,
        title: `${app.bootstrap?.user.name || '项目成员'} @你确认 Demo`,
        message: `${project.value.id} · ${payload.body}`,
        route: `/demo-workflow/${project.value.id}?tab=comment&from=demo-workflow`,
      })
    }
  } catch (reason) {
    const mapped = mapRequestError(reason)
    commentError.value = mapped.localizedMessage ?? mapped.message
  } finally {
    commentBusy.value = false
  }
}

async function downloadArtifact(id: string) {
  if (artifactBusyId.value) return
  artifactBusyId.value = id
  artifactError.value = ''
  artifactRequestId.value = ''
  try {
    const result = await props.apiClient.getDemoArtifact(id)
    downloadBlob(result.blob, result.fileName)
  } catch (reason) {
    const mapped = mapRequestError(reason)
    artifactError.value = mapped.localizedMessage ?? mapped.message
    artifactRequestId.value = mapped.requestId
  } finally {
    artifactBusyId.value = ''
  }
}

async function previewArtifact(id: string) {
  if (artifactBusyId.value) return
  artifactBusyId.value = id
  artifactError.value = ''
  artifactRequestId.value = ''
  try {
    const result = await props.apiClient.getDemoArtifact(id)
    const url = URL.createObjectURL(result.blob)
    window.open(url, '_blank', 'noopener,noreferrer')
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
  } catch (reason) {
    const mapped = mapRequestError(reason)
    artifactError.value = mapped.localizedMessage ?? mapped.message
    artifactRequestId.value = mapped.requestId
  } finally {
    artifactBusyId.value = ''
  }
}

watch(demoId, load)
onMounted(load)
</script>

<template>
  <main class="demo-detail-page" data-demo-detail>
    <DataState v-if="loading && !project" type="loading" />
    <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
    <section v-else-if="error || !project" class="detail-state">
      <DataState type="error" :message="error || t('demoDetail.notFound')" :request-id="requestId" @retry="load" />
      <RouterLink class="back-link detail-back-button" :to="backTarget"><ArrowLeft :size="14" />{{ t('demoDetail.back') }}</RouterLink>
    </section>
    <template v-else>
      <RouterLink class="back-link detail-back-button" :to="backTarget"><ArrowLeft :size="14" />{{ t('demoDetail.back') }}</RouterLink>

      <header class="project-heading">
        <div>
          <span>{{ t('demoDetail.archive') }} / {{ project.id }}</span>
          <h1>{{ project.title }}</h1>
          <p>{{ t('demoDetail.customer') }}: <strong>{{ project.account }}</strong></p>
        </div>
        <dl>
           <div><dt>{{ t('demoDetail.status') }}</dt><dd><span class="status-chip">{{ statusLabel(project.status) }}</span></dd></div>
          <div><dt>{{ t('demoDetail.salesOwner') }}</dt><dd>{{ personnelDisplayName(project.salesOwner) }}</dd></div>
          <div><dt>{{ t('demoDetail.engineerOwner') }}</dt><dd>{{ personnelDisplayName(project.engineerOwner) }}</dd></div>
          <div><dt>{{ t('demoDetail.createdAt') }}</dt><dd>{{ createdDate }}</dd></div>
        </dl>
      </header>

      <section class="timeline-dashboard" data-project-timeline-dashboard>
        <DemoProjectTimeline :item="project" />
      </section>

      <nav class="detail-tabs" :aria-label="t('demoDetail.tabs')">
        <button
          type="button"
          data-demo-detail-tab="information"
          :class="{ active: tab === 'information' }"
          :aria-current="tab === 'information' ? 'page' : undefined"
          @click="switchTab('information')"
        >{{ copy('Information', '基本信息') }}</button>
        <button
          type="button"
          data-demo-detail-tab="comment"
          :class="{ active: tab === 'comment' }"
          :aria-current="tab === 'comment' ? 'page' : undefined"
          @click="switchTab('comment')"
        >{{ copy('Comments', '评论') }} <span>{{ comments.length }}</span></button>
      </nav>
      <p v-if="artifactError" class="inline-error" data-artifact-error>{{ artifactError }}<small v-if="artifactRequestId">Request ID {{ artifactRequestId }}</small></p>

      <div v-if="tab === 'information'" class="detail-content-grid" data-demo-detail-information>
        <DemoArchiveDetail
          :item="project"
          :show-overview="false"
          :show-timeline="false"
          @preview="previewArtifact"
          @download="downloadArtifact"
        />
        <aside class="participants-panel">
          <header><UsersRound :size="17" /><strong>{{ t('demoDetail.participants') }}</strong></header>
          <article v-for="person in participants" :key="person.name">
            <span>{{ person.name.slice(0, 1) }}</span>
            <div><strong>{{ person.name }}</strong><small>{{ participantRoleLabel(person.role, locale) }}</small></div>
          </article>
        </aside>
      </div>
      <div v-else class="comment-layout">
        <DemoCommentPanel
          :comments="comments"
          :participants="mentionParticipants"
          :busy="commentBusy"
          :error="commentError"
          @submit="publishComment"
        />
        <aside class="comment-summary">
          <MessageSquareText :size="18" />
          <strong>{{ t('demoDetail.comments', { count: comments.length }) }}</strong>
          <span>{{ t('demoDetail.commentHint') }}</span>
        </aside>
      </div>
    </template>
  </main>
</template>

<style scoped>
.demo-detail-page{display:grid;gap:14px;min-width:0}.detail-state{display:grid;gap:12px}.back-link{display:inline-flex;width:max-content;align-items:center;gap:6px;color:var(--crm-teal);font-size:10px;font-weight:800}.project-heading{display:grid;grid-template-columns:minmax(0,1fr) minmax(520px,.92fr);align-items:end;gap:24px;padding:5px 12px 4px}.project-heading>div>span{color:var(--crm-text-muted);font-size:10px}.project-heading h1{margin:8px 0 5px;color:var(--crm-navy);font-size:clamp(25px,2.5vw,34px);letter-spacing:-.035em}.project-heading p{margin:0;color:var(--crm-text-muted);font-size:11px}.project-heading p strong{color:var(--crm-teal)}.project-heading dl{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin:0}.project-heading dl>div{display:grid;gap:6px;padding:2px 15px;border-left:1px solid var(--crm-line)}.project-heading dt{color:var(--crm-text-muted);font-size:9px}.project-heading dd{margin:0;color:var(--crm-navy);font-size:11px;font-weight:700}.status-chip{display:inline-flex;padding:5px 8px;color:#27794a;background:#e8f6ed;border-radius:6px}.timeline-dashboard{padding:18px 15px 14px;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.detail-tabs{display:flex;gap:4px;padding:4px;background:#efede9;border-radius:9px}.detail-tabs button{min-width:130px;height:38px;padding:0 16px;color:var(--crm-text-muted);background:transparent;border:0;border-radius:7px;font:inherit;font-size:10px;font-weight:800;cursor:pointer}.detail-tabs button.active{color:#b85000;background:#fff;box-shadow:0 2px 8px rgba(35,39,44,.07)}.detail-tabs span{display:inline-grid;min-width:20px;height:20px;place-items:center;margin-left:4px;background:#f0ede8;border-radius:6px;font-size:8px}.detail-content-grid,.comment-layout{display:grid;grid-template-columns:minmax(0,1fr) 260px;gap:14px;align-items:start}.participants-panel,.comment-summary{display:grid;align-content:start;gap:10px;padding:15px;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.participants-panel header{display:flex;align-items:center;gap:8px;padding-bottom:10px;border-bottom:1px solid var(--crm-line);color:var(--crm-navy);font-size:11px}.participants-panel article{display:grid;grid-template-columns:auto 1fr;align-items:center;gap:9px;padding:8px 0;border-bottom:1px solid var(--crm-line)}.participants-panel article:last-child{border-bottom:0}.participants-panel article>span{display:grid;width:32px;height:32px;place-items:center;color:#6d3d19;background:#ffe4d1;border-radius:9px;font-size:10px;font-weight:850}.participants-panel article>div{display:grid;gap:3px}.participants-panel article strong{color:var(--crm-navy);font-size:10px}.participants-panel article small{color:var(--crm-text-muted);font-size:8px}.comment-summary{justify-items:start;color:var(--crm-text-muted)}.comment-summary svg{color:#d8610b}.comment-summary strong{color:var(--crm-navy);font-size:12px}.comment-summary span{font-size:10px;line-height:1.6}@media(max-width:1050px){.project-heading{grid-template-columns:1fr}.project-heading dl{max-width:760px}.detail-content-grid,.comment-layout{grid-template-columns:1fr}.participants-panel{grid-template-columns:repeat(3,1fr)}.participants-panel header{grid-column:1/-1}.comment-summary{grid-template-columns:auto auto 1fr;align-items:center}}@media(max-width:680px){.project-heading dl{grid-template-columns:1fr 1fr}.project-heading dl>div{padding:9px;border-bottom:1px solid var(--crm-line)}.detail-tabs button{min-width:0;flex:1}.participants-panel{grid-template-columns:1fr}}
</style>
