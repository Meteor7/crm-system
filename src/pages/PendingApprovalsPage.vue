<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { RefreshCw } from '@lucide/vue'
import { api as defaultApi, type CrmApi } from '@/api'
import { requestErrorMessage } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import { useI18n, useLocaleMessage, localeMessage } from '@/i18n'
import PageHeader from '@/design-system/PageHeader.vue'
import ApprovalInbox from '@/features/approvals/ApprovalInbox.vue'
import ApprovalWorkspaceNav from '@/features/approvals/ApprovalWorkspaceNav.vue'
import { approvalTarget, visibleApprovals, type ApprovalItem, type ApprovalViewer } from '@/features/approvals/approval-queue'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const app = useAppStore(), router = useRouter(), { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const rows = ref<ApprovalItem[]>([]), loading = ref(false), opening = ref(''), error = useLocaleMessage()
const viewer = computed<ApprovalViewer | null>(() => app.bootstrap ? { ...app.bootstrap.user, capabilities: app.bootstrap.capabilities } : null)
const identity = computed(() => JSON.stringify([viewer.value?.id, viewer.value?.role, viewer.value?.capabilities]))
let revision = 0, active = false, alive = true
async function load() {
  const current = ++revision, key = identity.value
  rows.value = []; error.value = ''; loading.value = true
  if (!viewer.value) { loading.value = false; return }
  try {
    const result = await props.apiClient.listPendingApprovals()
    if (active && current === revision && key === identity.value) rows.value = result.data.items
  } catch (reason) {
    if (active && current === revision && key === identity.value) error.value = requestErrorMessage(reason)
  } finally { if (active && current === revision && key === identity.value) loading.value = false }
}
async function openSource(item: ApprovalItem) {
  if (opening.value || !viewer.value || !visibleApprovals(rows.value, viewer.value).some(row => row.id === item.id)) return
  opening.value = item.id
  try {
    const failure = await router.push(approvalTarget(item))
    if (!failure) {
      // A failed read receipt must not prevent the user from reaching the real approval workflow.
      try { await props.apiClient.markApprovalViewed(item.id) } catch { /* A later refresh will retain the unread state. */ }
    }
  } catch (reason) { error.value = requestErrorMessage(reason) }
  finally { opening.value = '' }
}
watch(identity, () => { revision++; rows.value = []; loading.value = false; if (active) void load() })
const refresh = () => { if (active) void load(); else void initialize() }
async function initialize() {
  loading.value = true; error.value = ''
  try {
    await app.loadBootstrap(props.apiClient)
    if (!alive) return
    if (!viewer.value) { error.value = app.errorSource || localeMessage('Unable to load the current user.', '无法读取当前用户信息'); loading.value = false; return }
    active = true; await load()
    if (alive) window.addEventListener('focus', refresh)
  }
  catch (reason) { if (alive) { error.value = requestErrorMessage(reason); loading.value = false } }
}
onMounted(initialize)
onBeforeUnmount(() => { alive = false; active = false; revision++; window.removeEventListener('focus', refresh) })
</script>
<template>
  <div class="pending-approvals-page">
    <PageHeader :eyebrow="viewer?.role === 'Manager' ? 'SALES WORKSPACE' : 'MY WORKSPACE'" :title="viewer?.role === 'Manager' ? copy('Sales cockpit', '销售经营看板') : copy('Information centre', '信息中心')" :description="copy('Business updates and the items that need your attention.', '查看业务信息，处理当前交给你的事项。')"><button class="refresh-approvals" type="button" :disabled="loading" @click="refresh"><RefreshCw :size="14" />{{ copy('Refresh', '刷新') }}</button></PageHeader>
    <ApprovalWorkspaceNav v-if="viewer" :pending-count="loading || error ? undefined : visibleApprovals(rows, viewer).length" />
    <div v-if="error" class="approval-load-error" role="alert"><p>{{ error }}</p><button type="button" :disabled="loading" @click="refresh">{{ copy('Retry', '重新加载') }}</button></div>
    <div v-else-if="loading" class="approval-loading" role="status">{{ copy('Loading pending approvals…', '正在读取待审批事项…') }}</div>
    <ApprovalInbox v-else-if="viewer" :items="rows" :viewer="viewer" @open-source="openSource" />
  </div>
</template>
<style scoped>
.pending-approvals-page{max-width:1600px;margin:0 auto}.refresh-approvals{display:inline-flex;align-items:center;gap:6px;height:34px;padding:0 11px;border:1px solid var(--crm-line);border-radius:7px;background:white;color:var(--crm-text-muted);font-size:12px;cursor:pointer}.refresh-approvals:disabled{opacity:.5;cursor:wait}.approval-loading,.approval-load-error{padding:35px 20px;background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:12px;color:var(--crm-text-muted);font-size:13px}.approval-load-error p{margin:0 0 14px}.approval-load-error button{border:1px solid var(--crm-line);border-radius:7px;padding:7px 12px;background:white;color:var(--crm-link);cursor:pointer}.pending-approvals-page button:focus-visible{outline:2px solid var(--crm-brand);outline-offset:3px}
</style>
