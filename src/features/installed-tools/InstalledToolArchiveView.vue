<script setup lang="ts">
import { systemValueLabel } from '@/features/shared/system-labels'
import { computed, ref, watch } from 'vue'
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Download,
  FileCheck2,
  History,
  PackageCheck,
  Pencil,
  ShieldCheck,
  Wrench,
} from '@lucide/vue'
import { personnelDisplayName } from '@/demo/personnel'
import { formatDisplayDate } from '@/domain/time'
import { useI18n } from '@/i18n'
import type { InstalledToolDetailDto, InstalledToolDto, InstalledToolLifecycleHistoryDto } from '@/types/workspaces'

const props = withDefaults(defineProps<{
  items: InstalledToolDto[]
  selectedId: string
  detail?: InstalledToolDetailDto | null
  detailLoading?: boolean
  detailError?: string
  /** The page is reading the Tool again for the editor: the editor's button waits. */
  busy?: boolean
}>(), { detail: null, detailLoading: false, detailError: '', busy: false })

const emit = defineEmits<{
  select: [item: InstalledToolDto]
  edit: []
  advance: []
  version: []
  service: []
  document: [name: string]
}>()
const { locale, t } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const stageLabel = (stage: string) => copy(stage, ({ FAT: 'FAT', Shipment: '发运', Installation: '安装', SAT: 'SAT', Warranty: '质保', Completed: '已完成' } as Record<string, string>)[stage] || stage)
const statusLabel = (status: string) => copy(status, ({ Production: '生产中', 'Upgrade Due': '待升级', Installation: '安装中', Active: '启用', Pending: '待确认', Completed: '已完成', Retired: '已退役', Decommissioned: '已停用' } as Record<string, string>)[status] || status)
const serviceTypeLabel = (type: string) => t(`installed.type.${type}`)
const changeTypeLabel = (type: string) => t(`installed.change.${type}`)

const activeSection = ref<'lifecycle' | 'configuration' | 'warranty'>('lifecycle')
const expandedStage = ref('')
const selected = computed(() => props.items.find((item) => item.id === props.selectedId) ?? props.items[0])
const resolvedDetail = computed(() => props.detail?.id === props.selectedId ? props.detail : null)
const currentStage = computed(() => resolvedDetail.value?.lifecycleCompleted ? 'Completed' : resolvedDetail.value?.lifecycleStage ?? 'FAT')
const completedStages = computed(() => resolvedDetail.value?.milestones.filter((stage) => stage.state === 'Done').length ?? 0)
const openIssueCount = computed(() => resolvedDetail.value?.lifecycleHistory.filter((item) => item.openIssues.trim()).length ?? 0)

function currentStageFor(tool: InstalledToolDto) {
  return tool.lifecycleStage ?? tool.milestones.find((stage) => stage.state === 'Current')?.label ?? 'Completed'
}
function displayStage(stage: string) { return stageLabel(stage) }
function historyFor(stage: { label: string }): InstalledToolLifecycleHistoryDto | undefined {
  return resolvedDetail.value?.lifecycleHistory.find((item) => item.fromStage === stage.label)
}
function statusTone(status: string) {
  const normalized = status.trim().toLowerCase()
  if (normalized.includes('production') || normalized.includes('active') || normalized.includes('completed')) return 'positive'
  if (normalized.includes('due') || normalized.includes('upgrade') || normalized.includes('pending')) return 'warning'
  if (normalized.includes('retired') || normalized.includes('decommission') || normalized.includes('closed')) return 'danger'
  return 'info'
}
function stageTone(state: string) {
  return state === 'Done' ? 'positive' : state === 'Current' ? 'warning' : ''
}
watch(() => props.selectedId, () => {
  activeSection.value = 'lifecycle'
  expandedStage.value = ''
}, { immediate: true })
watch(resolvedDetail, (detail) => {
  if (detail) expandedStage.value = detail.lifecycleCompleted ? 'Warranty' : detail.lifecycleStage ?? 'FAT'
}, { immediate: true })
</script>

<template>
  <section class="archive-view" data-installed-tool-archive>
    <section v-if="!selected" class="workspace-panel workspace-panel-body">{{ t('installed.noFilterMatch') }}</section>
     <section v-else class="tool-layout">
      <aside class="workspace-panel tool-list-panel">
        <header><div><span class="eyebrow">INSTALLED BASE</span><h2>{{ t('installed.archiveTitle') }}</h2></div><span>{{ t('installed.count', { count: items.length }) }}</span></header>
        <div class="workspace-panel-body workspace-list">
          <button
            v-for="tool in items"
            :key="tool.id"
            type="button"
            class="workspace-select-card"
            :class="{ active: tool.id === selected.id }"
            :data-installed-tool-archive-id="tool.id"
            @click="emit('select', tool)"
          >
             <div class="row"><span class="workspace-badge" :class="statusTone(tool.status)">{{ statusLabel(tool.status) }}</span><b>{{ tool.id }}</b></div>
            <strong>{{ tool.model }} · {{ tool.serial }}</strong>
            <small>{{ tool.account }}</small>
            <small>{{ tool.site }} · {{ systemValueLabel(tool.location, locale) || t('installed.locationPending') }}</small>
            <small>{{ personnelDisplayName(tool.engineerOwner) || t('installed.engineerPending') }}</small>
             <div class="row foot"><span>{{ t('installed.currentStage', { stage: displayStage(currentStageFor(tool)) }) }}</span><b>SW {{ systemValueLabel(tool.software, locale) || '—' }}</b></div>
          </button>
        </div>
      </aside>

      <div class="tool-main">
        <section v-if="detailLoading" class="workspace-panel workspace-panel-body detail-state">{{ t('installed.readingArchive') }}</section>
        <section v-else-if="detailError" class="workspace-panel workspace-panel-body detail-state error">{{ detailError }}</section>
        <section v-else-if="!resolvedDetail" class="workspace-panel workspace-panel-body detail-state">{{ t('installed.noDetail') }}</section>

        <template v-else>
          <section class="workspace-panel tool-header" data-testid="installed-tool-hero" :data-stage="currentStage">
            <header>
              <div class="tool-title"><span class="eyebrow">{{ resolvedDetail.id }} · {{ resolvedDetail.serial }}</span><h2>{{ resolvedDetail.model }} {{ t('installed.deliveryArchive') }}</h2><small>{{ resolvedDetail.account }} · {{ resolvedDetail.site }}</small></div>
              <div class="tool-header-actions">
                 <span class="workspace-badge" :class="statusTone(resolvedDetail.status)">{{ statusLabel(resolvedDetail.status) }}</span>
                <button v-if="resolvedDetail.canOperate && !resolvedDetail.lifecycleCompleted" class="primary-button" type="button" data-testid="advance-installed-tool" @click="emit('advance')"><CheckCircle2 :size="13" />{{ t('installed.completeStage', { stage: currentStage }) }}</button>
                <button v-if="resolvedDetail.canOperate" class="secondary-button" type="button" data-testid="add-installed-tool-version" @click="emit('version')"><History :size="13" />{{ t('installed.addVersion') }}</button>
                <button v-if="resolvedDetail.canOperate" class="secondary-button" type="button" data-testid="add-installed-tool-service" @click="emit('service')"><Wrench :size="13" />{{ t('installed.addService') }}</button>
                <button v-if="resolvedDetail.canOperate" class="secondary-button" type="button" data-testid="edit-installed-tool" :disabled="busy" @click="emit('edit')"><Pencil :size="13" />{{ t('installed.editMaster') }}</button>
              </div>
            </header>
            <div class="record-summary hero-summary">
               <div><small>{{ copy('Customer / Site', '客户 / 厂区') }}</small><strong>{{ resolvedDetail.account }}</strong><span>{{ resolvedDetail.site }} · {{ systemValueLabel(resolvedDetail.location, locale) || t('installed.locationPending') }}</span></div>
              <div><small>{{ t('installed.lifecycleStage') }}</small><strong>{{ currentStage }}</strong><span>{{ t('installed.completedNodes', { done: completedStages }) }}</span></div>
               <div><small>{{ copy('Software / OS', '软件 / 操作系统') }}</small><strong>{{ systemValueLabel(resolvedDetail.software, locale) || '—' }}</strong><span>{{ systemValueLabel(resolvedDetail.operatingSystem, locale) || '—' }}</span></div>
               <div><small>{{ copy('Warranty End', '质保结束') }}</small><strong>{{ systemValueLabel(resolvedDetail.warrantyEnd, locale) || t('installed.pending') }}</strong><span>{{ systemValueLabel(resolvedDetail.serviceContract, locale) || t('installed.serviceLevelPending') }}</span></div>
            </div>
          </section>

          <section class="workspace-panel master-data-panel" data-testid="installed-tool-master-data">
            <header><div><span class="eyebrow">MASTER DATA</span><h2>{{ t('installed.masterData') }}</h2></div><span>{{ t('installed.masterDataHint') }}</span></header>
            <div class="master-data-grid">
               <div data-master-tone="identity"><small>{{ copy('Serial Number', '序列号') }}</small><strong>{{ resolvedDetail.serial || '—' }}</strong></div>
               <div data-master-tone="identity"><small>{{ copy('Model', '设备型号') }}</small><strong>{{ resolvedDetail.model || '—' }}</strong></div>
               <div data-master-tone="identity"><small>{{ copy('Customer', '客户') }}</small><strong>{{ resolvedDetail.account || '—' }}</strong><span>{{ resolvedDetail.accountId }}</span></div>
               <div data-master-tone="identity"><small>{{ copy('Site / Location', '厂区 / 位置') }}</small><strong>{{ resolvedDetail.site || '—' }}</strong><span>{{ systemValueLabel(resolvedDetail.location, locale) || t('installed.locationPending') }}</span></div>
               <div data-master-tone="ownership"><small>{{ copy('Engineer Owner', '工程师负责人') }}</small><strong>{{ personnelDisplayName(resolvedDetail.engineerOwner) || '—' }}</strong></div>
               <div data-master-tone="ownership"><small>{{ copy('Sales Owner', '销售负责人') }}</small><strong>{{ personnelDisplayName(resolvedDetail.salesOwner) || '—' }}</strong></div>
               <div data-master-tone="ownership"><small>{{ copy('Sales Order', '销售订单') }}</small><strong>{{ systemValueLabel(resolvedDetail.salesOrder, locale) || '—' }}</strong></div>
               <div data-master-tone="ownership"><small>{{ copy('Contract', '合同') }}</small><strong>{{ systemValueLabel(resolvedDetail.contract, locale) || '—' }}</strong></div>
               <div data-master-tone="ownership"><small>{{ copy('Ownership', '归属') }}</small><strong>{{ systemValueLabel(resolvedDetail.ownershipType, locale) || '—' }}</strong></div>
               <div data-master-tone="ownership"><small>{{ copy('Source Booking', '来源 Booking') }}</small><strong>{{ resolvedDetail.sourceBookingId || '—' }}</strong></div>
               <div data-master-tone="ownership"><small>{{ copy('Source Opportunity', '来源 Opportunity') }}</small><strong>{{ resolvedDetail.sourceOpportunityId || '—' }}</strong></div>
               <div data-master-tone="configuration"><small>{{ copy('Software / Firmware', '软件 / 固件') }}</small><strong>{{ systemValueLabel(resolvedDetail.software, locale) || '—' }} / {{ systemValueLabel(resolvedDetail.firmware, locale) || '—' }}</strong></div>
               <div data-master-tone="configuration"><small>{{ copy('Operating System', '操作系统') }}</small><strong>{{ systemValueLabel(resolvedDetail.operatingSystem, locale) || '—' }}</strong></div>
               <div data-master-tone="configuration"><small>{{ copy('Configuration', '配置') }}</small><strong>{{ systemValueLabel(resolvedDetail.configuration, locale) || '—' }}</strong></div>
               <div data-master-tone="service"><small>{{ copy('Warranty', '质保') }}</small><strong>{{ systemValueLabel(resolvedDetail.warrantyStart, locale) || t('installed.pending') }} → {{ systemValueLabel(resolvedDetail.warrantyEnd, locale) || t('installed.pending') }}</strong></div>
               <div data-master-tone="service"><small>{{ copy('Service Contract / PM', '服务合同 / PM') }}</small><strong>{{ systemValueLabel(resolvedDetail.serviceContract, locale) || '—' }}</strong><span>{{ systemValueLabel(resolvedDetail.pmCycle, locale) || t('installed.pmCycle') }}</span></div>
               <div data-master-tone="service"><small>{{ copy('Last Service', '最近服务') }}</small><strong>{{ systemValueLabel(resolvedDetail.lastService, locale) || '—' }}</strong></div>
            </div>
          </section>

          <nav class="detail-tabs" :aria-label="t('installed.archiveSections')">
            <button type="button" :class="{ active: activeSection === 'lifecycle' }" @click="activeSection = 'lifecycle'"><PackageCheck :size="14" />{{ t('installed.deliveryLifecycle') }}</button>
            <button type="button" :class="{ active: activeSection === 'configuration' }" @click="activeSection = 'configuration'"><History :size="14" />{{ t('installed.versionConfig') }}</button>
            <button type="button" :class="{ active: activeSection === 'warranty' }" @click="activeSection = 'warranty'"><ShieldCheck :size="14" />{{ t('installed.warrantyService') }}</button>
          </nav>

          <section v-if="activeSection === 'lifecycle'" class="workspace-panel lifecycle-panel">
             <header><div><span class="eyebrow">{{ copy('DELIVERY TRACK', '交付跟踪') }}</span><h2>{{ copy('Delivery & Acceptance Lifecycle', '交付与验收生命周期') }}</h2><small>FAT → Shipment → Installation → SAT → Warranty</small></div><span :class="['issue-chip', { clear: openIssueCount === 0 }]"><AlertTriangle :size="12" />{{ t('installed.issueCount', { count: openIssueCount }) }}</span></header>
            <div class="lifecycle-overview">
              <button
                v-for="(stage, index) in resolvedDetail.milestones"
                :key="stage.label"
                type="button"
                :class="['lifecycle-step', `is-${stage.state.toLowerCase()}`, { active: expandedStage === stage.label }]"
                :aria-current="stage.state === 'Current' ? 'step' : undefined"
                :data-state="stage.state"
                @click="expandedStage = stage.label"
              >
                <span class="step-number"><CheckCircle2 v-if="stage.state === 'Done'" :size="14" /><template v-else>{{ index + 1 }}</template></span>
                 <span><b>{{ displayStage(stage.label) }}</b><small>{{ systemValueLabel(stage.date, locale) || t('installed.datePending') }}</small></span>
              </button>
            </div>
            <div class="stage-records">
              <article v-for="stage in resolvedDetail.milestones" :key="stage.label" :class="{ open: expandedStage === stage.label }">
                <button type="button" class="stage-record-head" @click="expandedStage = expandedStage === stage.label ? '' : stage.label">
                  <span :class="['stage-state-dot', `is-${stage.state.toLowerCase()}`]" />
                   <span><strong>{{ displayStage(stage.label) }}</strong><small>{{ historyFor(stage)?.comment || t('installed.noComment') }}</small></span>
                  <span><small>{{ t('installed.completedDate') }}</small><b>{{ historyFor(stage)?.completedAt || '—' }}</b></span>
                  <span class="workspace-badge" :class="stageTone(stage.state)">{{ stage.state === 'Done' ? t('installed.status.done') : stage.state === 'Current' ? t('installed.status.current') : t('installed.status.waiting') }}</span>
                  <ChevronDown :size="14" />
                </button>
                <div v-if="expandedStage === stage.label" class="stage-record-detail">
                  <template v-if="historyFor(stage)">
                    <div><small>{{ t('installed.operator') }}</small><strong>{{ personnelDisplayName(historyFor(stage)?.actor || '') || historyFor(stage)?.actor }}</strong></div>
                     <div><small>{{ t('installed.acceptanceResult') }}</small><strong>{{ historyFor(stage)?.result || '—' }}</strong></div>
                    <div><small>{{ t('installed.openIssues') }}</small><strong>{{ systemValueLabel(historyFor(stage)?.openIssues, locale) || t('common.none') }}</strong></div>
                    <div><small>{{ t('installed.customerSignoff') }}</small><strong>{{ historyFor(stage)?.customerSignoff || '—' }}</strong></div>
                    <div class="evidence"><small>{{ t('installed.evidence') }}</small><div><span v-for="file in historyFor(stage)?.evidence" :key="file">{{ file }}</span></div><span v-if="!historyFor(stage)?.evidence.length">{{ t('installed.noEvidence') }}</span></div>
                  </template>
                  <p v-else class="empty-record">{{ t('installed.noStageRecord') }}</p>
                </div>
              </article>
            </div>
          </section>

          <template v-else-if="activeSection === 'configuration'">
            <section class="workspace-panel configuration-panel">
               <header><div><span class="eyebrow">{{ copy('CURRENT BASELINE', '当前基线') }}</span><h2>{{ t('installed.currentBaseline') }}</h2></div><span class="workspace-badge info">{{ systemValueLabel(resolvedDetail.ownershipType, locale) || t('installed.unassigned') }}</span></header>
              <div class="record-summary configuration-summary">
                 <div><small>{{ copy('Current Software', '当前软件') }}</small><strong>{{ systemValueLabel(resolvedDetail.software, locale) || '—' }}</strong></div>
                 <div><small>{{ copy('Current Firmware', '当前固件') }}</small><strong>{{ systemValueLabel(resolvedDetail.firmware, locale) || '—' }}</strong></div>
                 <div><small>{{ copy('Operating System', '操作系统') }}</small><strong>{{ systemValueLabel(resolvedDetail.operatingSystem, locale) || '—' }}</strong></div>
                 <div><small>{{ copy('Configuration', '配置') }}</small><strong>{{ systemValueLabel(resolvedDetail.configuration, locale) || '—' }}</strong></div>
              </div>
            </section>
            <section class="workspace-panel">
               <header><div><span class="eyebrow">{{ copy('CHANGE LOG', '变更记录') }}</span><h2>{{ t('installed.changeHistory') }}</h2></div><span class="workspace-badge info">{{ t('installed.recordCount', { count: resolvedDetail.versionHistory.length }) }}</span></header>
              <div v-if="resolvedDetail.versionHistory.length" class="table-wrap">
                <table class="record-table">
                 <thead><tr><th>{{ t('installed.changeDate') }}</th><th>{{ t('installed.changeType') }}</th><th>{{ copy('From', '原值') }}</th><th>{{ t('installed.newValue') }}</th><th>{{ t('installed.operator') }}</th><th>{{ t('installed.changeReason') }}</th></tr></thead>
                  <tbody>
                    <tr v-for="item in resolvedDetail.versionHistory" :key="item.id">
                       <td>{{ formatDisplayDate(item.changeDate) }}</td><td><b>{{ changeTypeLabel(item.changeType) }}</b></td><td>{{ systemValueLabel(item.fromValue, locale) || '—' }}</td><td><strong>{{ systemValueLabel(item.toValue, locale) }}</strong></td><td>{{ personnelDisplayName(item.actor) || item.actor }}</td><td>{{ item.reason }}<small v-if="item.comment">{{ item.comment }}</small></td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p v-else class="empty-record padded">{{ t('installed.noVersionHistory') }}</p>
            </section>
          </template>

          <template v-else>
            <section class="warranty-grid">
              <article class="workspace-panel warranty-panel">
                 <header><div><span class="eyebrow">{{ copy('COVERAGE', '质保覆盖') }}</span><h2>{{ t('installed.coverage') }}</h2></div><span class="workspace-badge positive">{{ systemValueLabel(resolvedDetail.serviceContract, locale) || t('installed.serviceLevelPending') }}</span></header>
                <div class="warranty-body">
                  <div class="health-score" :style="{ '--health': `${resolvedDetail.completeness}%` }" :aria-label="t('installed.completenessLabel', { value: resolvedDetail.completeness })"><strong>{{ resolvedDetail.completeness }}%</strong><span>{{ t('installed.profileCompleteness') }}</span></div>
                  <div>
                    <p><span>{{ t('installed.warrantyStart') }}</span><b>{{ systemValueLabel(resolvedDetail.warrantyStart, locale) || t('installed.pending') }}</b></p>
                    <p><span>{{ t('installed.warrantyEnd') }}</span><b>{{ systemValueLabel(resolvedDetail.warrantyEnd, locale) || t('installed.pending') }}</b></p>
                    <p><span>{{ t('installed.pmCycle') }}</span><b>{{ systemValueLabel(resolvedDetail.pmCycle, locale) || t('installed.pending') }}</b></p>
                  </div>
                </div>
              </article>
              <article class="workspace-panel document-panel">
                 <header><div><span class="eyebrow">{{ copy('DOCUMENTS', '适用文档') }}</span><h2>{{ t('installed.documents') }}</h2></div><span class="workspace-badge info">{{ t('installed.documentCount', { count: resolvedDetail.documents.length }) }}</span></header>
                <ul class="document-links"><li v-for="document in resolvedDetail.documents" :key="document"><FileCheck2 :size="15" /><span>{{ document }}</span><button type="button" @click="emit('document', document)"><Download :size="12" />{{ t('installed.view') }}</button></li></ul><p v-if="!resolvedDetail.documents.length" class="empty-record padded">{{ t('installed.noDocuments') }}</p>
              </article>
            </section>
            <section class="workspace-panel service-panel">
               <header><div><span class="eyebrow">{{ copy('SERVICE HISTORY', '服务历史') }}</span><h2>{{ t('installed.serviceHistory') }}</h2></div><span class="workspace-badge info">{{ t('installed.lastService') }} {{ systemValueLabel(resolvedDetail.lastService, locale) || '—' }}</span></header>
              <div v-if="resolvedDetail.serviceHistory.length" class="service-list">
                <article v-for="item in resolvedDetail.serviceHistory" :key="item.id">
                  <Wrench :size="15" />
                   <div><strong>{{ serviceTypeLabel(item.serviceType) }}</strong><small>{{ formatDisplayDate(item.serviceDate) }} · {{ personnelDisplayName(item.actor) || item.actor }}</small></div>
                  <span>{{ item.result }}</span>
                  <small v-if="item.openIssues" class="service-alert">{{ t('installed.issuePrefix') }}{{ systemValueLabel(item.openIssues, locale) }}</small>
                  <small v-if="item.nextAction" class="service-next">{{ t('installed.nextActionPrefix') }}{{ item.nextAction }} · {{ personnelDisplayName(item.actionOwner) || item.actionOwner }} · {{ item.due }}</small>
                </article>
              </div>
              <p v-else class="empty-record padded">{{ t('installed.noServiceHistory') }}</p>
            </section>
          </template>
        </template>
      </div>
    </section>
  </section>
</template>

<style scoped>
.archive-view{min-width:0}
.tool-layout{display:grid;grid-template-columns:280px minmax(0,1fr);gap:14px;align-items:start}
.tool-list-panel{position:sticky;top:12px;align-self:start;overflow:hidden}
.tool-list-panel>header,.workspace-panel>header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 15px;border-bottom:1px solid var(--crm-line)}
.tool-list-panel>header{background:#faf8f5}.tool-list-panel>header>div,.workspace-panel>header>div{display:grid;gap:3px}.tool-list-panel h2,.workspace-panel h2{margin:0;color:var(--crm-navy);font-size:12px}.tool-list-panel header>span,.workspace-panel header>span{color:var(--crm-text-muted);font-size:8px}
.eyebrow{color:#b85000!important;font-size:7px!important;font-weight:850;letter-spacing:.12em;text-transform:uppercase}
.workspace-list{display:grid;gap:8px;max-height:760px;overflow:auto;padding:10px}
.workspace-select-card{display:grid;gap:6px;padding:11px;text-align:left;background:#fff;border:1px solid var(--crm-line);border-radius:10px;cursor:pointer;transition:border-color .16s,background .16s,box-shadow .16s}
.workspace-select-card:hover{border-color:#f0cf9a;background:#fffcf7}.workspace-select-card.active{background:#fff8ef;border-color:#f3c173;box-shadow:inset 4px 0 var(--crm-orange),0 4px 14px rgba(31,35,41,.05)}
.workspace-select-card>strong{color:var(--crm-navy);font-size:10px}.workspace-select-card>small,.foot{color:var(--crm-text-muted);font-size:7px}.row{display:flex;align-items:center;justify-content:space-between;gap:7px}.row>b{color:var(--crm-text-muted);font-size:7px}.foot{padding-top:7px;border-top:1px solid var(--crm-line)}.foot>b{color:var(--crm-teal)}
.tool-main{display:grid;align-content:start;gap:14px;min-width:0}.detail-state{min-height:180px;display:grid;place-items:center;color:var(--crm-text-muted)}.detail-state.error{color:var(--crm-danger)}
.tool-header{position:relative;overflow:hidden}.tool-header>header{min-height:82px;align-items:flex-start;padding:18px;background:var(--crm-navy);border-bottom:0}.tool-title{display:grid;gap:4px}.tool-title h2{margin:0;color:#fff;font-size:20px;letter-spacing:-.02em}.tool-title small{color:#b8c8c6;font-size:8px}.tool-header .eyebrow{color:#ffc56b!important}
.tool-header-actions{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:7px}.tool-header-actions button{display:inline-flex;height:32px;align-items:center;gap:6px;padding:0 10px;font-size:8px}.tool-header .secondary-button{color:#fff;background:rgba(255,255,255,.08);border-color:rgba(255,255,255,.26)}.tool-header .secondary-button:hover{background:rgba(255,255,255,.14)}
.record-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;background:var(--crm-line)}.record-summary>div{display:grid;gap:5px;padding:14px;background:#fff}.record-summary small,.record-summary span{color:var(--crm-text-muted);font-size:8px;line-height:1.45}.record-summary strong{overflow:hidden;color:var(--crm-navy);font-size:11px;line-height:1.4;text-overflow:ellipsis}.hero-summary>div{box-shadow:inset 0 3px #547f9f}.hero-summary>div:nth-child(2){box-shadow:inset 0 3px var(--crm-orange)}.hero-summary>div:nth-child(3){box-shadow:inset 0 3px var(--crm-teal)}.hero-summary>div:nth-child(4){box-shadow:inset 0 3px var(--crm-positive)}
.master-data-panel{overflow:hidden}.master-data-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;background:var(--crm-line)}.master-data-grid>div{position:relative;display:grid;align-content:start;gap:5px;min-height:65px;padding:13px 13px 12px 16px;background:#fff}.master-data-grid>div::before{position:absolute;inset:0 auto 0 0;width:3px;background:#547f9f;content:""}.master-data-grid>[data-master-tone="identity"]{background:#f5f9fc}.master-data-grid>[data-master-tone="ownership"]{background:#f3faf8}.master-data-grid>[data-master-tone="ownership"]::before{background:var(--crm-teal)}.master-data-grid>[data-master-tone="configuration"]{background:#fff8ef}.master-data-grid>[data-master-tone="configuration"]::before{background:var(--crm-orange)}.master-data-grid>[data-master-tone="service"]{background:#f7f9ec}.master-data-grid>[data-master-tone="service"]::before{background:var(--crm-positive)}.master-data-grid small,.master-data-grid span{color:var(--crm-text-muted);font-size:7px}.master-data-grid strong{overflow-wrap:anywhere;color:var(--crm-navy);font-size:9px;line-height:1.45}
.detail-tabs{display:flex;gap:4px;padding:4px;background:#efede9;border-radius:10px}.detail-tabs button{display:flex;height:38px;flex:1;align-items:center;justify-content:center;gap:7px;color:var(--crm-text-muted);background:transparent;border:0;border-radius:7px;font-size:9px;font-weight:800;cursor:pointer}.detail-tabs button.active{color:#b85000;background:#fff;box-shadow:0 2px 8px rgba(35,39,44,.07)}
.lifecycle-panel{overflow:hidden}.lifecycle-panel>header small{color:var(--crm-text-muted);font-size:8px}.issue-chip{display:flex!important;align-items:center;gap:5px;padding:6px 9px!important;color:#8a651d!important;background:var(--crm-warning-soft);border-radius:999px;font-weight:750}.issue-chip.clear{color:var(--crm-positive-ink)!important;background:#eff4d7}
.lifecycle-overview{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));padding:19px 16px 21px;border-bottom:1px solid var(--crm-line)}.lifecycle-step{position:relative;display:grid;grid-template-columns:30px 1fr;align-items:center;gap:8px;padding:5px 8px;color:var(--crm-text-muted);text-align:left;background:transparent;border:0;border-radius:9px;cursor:pointer}.lifecycle-step:not(:last-child)::after{position:absolute;top:20px;right:-9px;width:18px;height:2px;background:var(--crm-line);content:""}.lifecycle-step.is-done:not(:last-child)::after{background:var(--crm-positive)}.lifecycle-step.active{background:#fff8ef}.step-number{display:grid;width:30px;height:30px;place-items:center;background:var(--crm-surface-muted);border:1px solid var(--crm-line);border-radius:50%;font-size:8px;font-weight:900}.lifecycle-step.is-done .step-number{color:#fff;background:var(--crm-positive);border-color:var(--crm-positive)}.lifecycle-step.is-current .step-number{color:var(--crm-brand-ink);background:var(--crm-teal);border-color:var(--crm-teal);box-shadow:0 0 0 4px var(--crm-teal-soft)}.lifecycle-step span:last-child{display:grid;gap:3px}.lifecycle-step b{color:var(--crm-navy);font-size:9px}.lifecycle-step small{font-size:7px}.lifecycle-step.active b{color:#b85000}
.stage-records article{border-bottom:1px solid var(--crm-line)}.stage-records article:last-child{border-bottom:0}.stage-record-head{display:grid;width:100%;grid-template-columns:10px minmax(120px,1.2fr) minmax(145px,.75fr) auto 18px;align-items:center;gap:12px;padding:13px 16px;color:inherit;text-align:left;background:#fff;border:0;cursor:pointer}.stage-records article.open .stage-record-head{background:#faf8f5}.stage-records article.open .stage-record-head>svg{transform:rotate(180deg)}.stage-state-dot{width:7px;height:7px;background:#cfd9d7;border-radius:50%}.stage-state-dot.is-done{background:var(--crm-positive)}.stage-state-dot.is-current{background:var(--crm-orange);box-shadow:0 0 0 3px var(--crm-warning-soft)}.stage-record-head>span:nth-child(2),.stage-record-head>span:nth-child(3){display:grid;gap:3px}.stage-record-head strong{color:var(--crm-navy);font-size:9px}.stage-record-head small{color:var(--crm-text-muted);font-size:7px}.stage-record-head>svg{color:var(--crm-text-muted);transition:transform .16s}
.stage-record-detail{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;padding:0 16px 16px 38px;background:#faf8f5}.stage-record-detail>div{display:grid;gap:6px;padding:13px;background:#fff}.stage-record-detail small{color:var(--crm-text-muted);font-size:7px}.stage-record-detail strong{color:var(--crm-navy);font-size:9px;line-height:1.45}.stage-record-detail>.evidence{grid-column:1/-1}.evidence>div{display:flex;flex-wrap:wrap;gap:7px}.evidence button,.document-links button{display:inline-flex;align-items:center;gap:6px;padding:7px 9px;color:var(--crm-teal);background:var(--crm-teal-soft);border:0;border-radius:7px;font-size:8px;cursor:pointer}.evidence>span{color:var(--crm-text-muted);font-size:8px}.empty-record{margin:0;color:var(--crm-text-muted);font-size:8px}.stage-record-detail>.empty-record{grid-column:1/-1;padding:14px;background:#fff}.padded{padding:18px}
.configuration-panel .record-summary>div{box-shadow:inset 0 3px var(--crm-teal)}.configuration-panel .record-summary>div:nth-child(2){box-shadow:inset 0 3px #547f9f}.configuration-panel .record-summary>div:nth-child(3){box-shadow:inset 0 3px var(--crm-orange)}.configuration-panel .record-summary>div:nth-child(4){box-shadow:inset 0 3px var(--crm-positive)}.configuration-summary>div:last-child strong{font-size:9px}
.table-wrap{overflow:auto}.record-table{width:100%;min-width:720px;border-collapse:collapse}.record-table th,.record-table td{padding:11px 14px;text-align:left;border-bottom:1px solid var(--crm-line);font-size:8px}.record-table th{color:var(--crm-text-muted);background:#faf8f5;font-size:7px}.record-table td{color:var(--crm-text-muted)}.record-table td b,.record-table td strong{color:var(--crm-navy)}.record-table td small{display:block;margin-top:4px;color:var(--crm-text-muted)}
.warranty-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.warranty-body{display:grid;grid-template-columns:110px 1fr;gap:18px;padding:18px}.health-score{position:relative;display:grid;width:92px;height:92px;place-content:center;color:var(--crm-teal);background:conic-gradient(var(--crm-teal) 0 var(--health),var(--crm-surface-muted) var(--health) 100%);border:1px solid var(--crm-line);border-radius:50%;text-align:center}.health-score::before{position:absolute;inset:9px;background:#fff;border-radius:50%;content:""}.health-score strong,.health-score span{position:relative;z-index:1}.health-score strong{font-size:20px;line-height:1}.health-score span{margin-top:4px;font-size:7px}.warranty-body>div:last-child{display:grid;align-content:center}.warranty-body p{display:flex;justify-content:space-between;gap:8px;margin:0;padding:8px 0;border-bottom:1px solid var(--crm-line);font-size:8px}.warranty-body p span{color:var(--crm-text-muted)}.warranty-body p b{color:var(--crm-navy)}
.document-links{display:grid;margin:0;padding:8px 16px;list-style:none}.document-links li{display:grid;grid-template-columns:20px 1fr auto;align-items:center;gap:8px;min-height:48px;border-bottom:1px solid var(--crm-line);font-size:8px}.document-links li:last-child{border-bottom:0}.document-links li>svg{color:var(--crm-orange)}.document-links li>span{overflow:hidden;color:var(--crm-navy);text-overflow:ellipsis;white-space:nowrap}
.service-list{display:grid}.service-list article{display:grid;grid-template-columns:24px minmax(150px,.45fr) minmax(180px,1fr);align-items:center;gap:9px;padding:13px 16px;border-bottom:1px solid var(--crm-line)}.service-list article:last-child{border-bottom:0}.service-list article>svg{color:var(--crm-teal)}.service-list div{display:grid;gap:4px}.service-list strong{color:var(--crm-navy);font-size:9px}.service-list small,.service-list span{color:var(--crm-text-muted);font-size:8px}.service-list .service-alert,.service-list .service-next{grid-column:2/-1;padding:7px 9px;border-radius:7px}.service-list .service-alert{color:#8a651d;background:var(--crm-warning-soft)}.service-list .service-next{color:var(--crm-teal);background:var(--crm-teal-soft)}
@media(max-width:1100px){.tool-layout{grid-template-columns:1fr}.tool-list-panel{position:static}.workspace-list{grid-template-columns:repeat(3,minmax(0,1fr))}.record-summary,.master-data-grid{grid-template-columns:1fr 1fr}}
@media(max-width:760px){.workspace-list{grid-template-columns:1fr}.tool-header>header{align-items:stretch;flex-direction:column}.tool-header-actions{justify-content:flex-start}.detail-tabs{overflow:auto}.detail-tabs button{min-width:130px}.lifecycle-overview{overflow:auto;grid-template-columns:repeat(5,145px)}.stage-record-head{grid-template-columns:10px 1fr auto}.stage-record-head>span:nth-child(3){grid-column:2}.stage-record-head>.workspace-badge{grid-column:3;grid-row:1}.stage-record-head>svg{display:none}.stage-record-detail{grid-template-columns:1fr;padding-left:16px}.stage-record-detail>.evidence{grid-column:auto}.warranty-grid{grid-template-columns:1fr}.service-list article{grid-template-columns:24px 1fr}.service-list article>span,.service-list .service-alert,.service-list .service-next{grid-column:2}}
@media(max-width:520px){.record-summary,.master-data-grid{grid-template-columns:1fr}.tool-title h2{font-size:17px}.warranty-body{grid-template-columns:1fr}.health-score{margin:auto}}
</style>
