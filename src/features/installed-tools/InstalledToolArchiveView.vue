<script setup lang="ts">
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
import type { InstalledToolDetailDto, InstalledToolDto, InstalledToolLifecycleHistoryDto } from '@/types/workspaces'

const props = withDefaults(defineProps<{
  items: InstalledToolDto[]
  selectedId: string
  detail?: InstalledToolDetailDto | null
  detailLoading?: boolean
  detailError?: string
}>(), { detail: null, detailLoading: false, detailError: '' })

const emit = defineEmits<{
  select: [item: InstalledToolDto]
  edit: []
  advance: []
  version: []
  service: []
  document: [name: string]
}>()

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
    <section v-if="!selected" class="workspace-panel workspace-panel-body">没有匹配筛选条件的 Installed Tool。</section>
    <section v-else class="tool-layout">
      <aside class="workspace-panel tool-list-panel">
        <header><div><span class="eyebrow">INSTALLED BASE</span><h2>设备台账</h2></div><span>{{ items.length }} 台</span></header>
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
            <div class="row"><span class="workspace-badge" :class="statusTone(tool.status)">{{ tool.status }}</span><b>{{ tool.id }}</b></div>
            <strong>{{ tool.model }} · {{ tool.serial }}</strong>
            <small>{{ tool.account }}</small>
            <small>{{ tool.site }} · {{ tool.location || '位置待确认' }}</small>
            <small>{{ personnelDisplayName(tool.engineerOwner) || '工程师待确认' }}</small>
            <div class="row foot"><span>当前：{{ currentStageFor(tool) }}</span><b>SW {{ tool.software || '—' }}</b></div>
          </button>
        </div>
      </aside>

      <div class="tool-main">
        <section v-if="detailLoading" class="workspace-panel workspace-panel-body detail-state">正在读取设备档案…</section>
        <section v-else-if="detailError" class="workspace-panel workspace-panel-body detail-state error">{{ detailError }}</section>
        <section v-else-if="!resolvedDetail" class="workspace-panel workspace-panel-body detail-state">暂无该设备的详细档案。</section>

        <template v-else>
          <section class="workspace-panel tool-header" data-testid="installed-tool-hero" :data-stage="currentStage">
            <header>
              <div class="tool-title"><span class="eyebrow">{{ resolvedDetail.id }} · {{ resolvedDetail.serial }}</span><h2>{{ resolvedDetail.model }} 设备交付档案</h2><small>{{ resolvedDetail.account }} · {{ resolvedDetail.site }}</small></div>
              <div class="tool-header-actions">
                <span class="workspace-badge" :class="statusTone(resolvedDetail.status)">{{ resolvedDetail.status }}</span>
                <button v-if="resolvedDetail.canOperate && !resolvedDetail.lifecycleCompleted" class="primary-button" type="button" data-testid="advance-installed-tool" @click="emit('advance')"><CheckCircle2 :size="13" />完成 {{ currentStage }}</button>
                <button v-if="resolvedDetail.canOperate" class="secondary-button" type="button" data-testid="add-installed-tool-version" @click="emit('version')"><History :size="13" />新增版本记录</button>
                <button v-if="resolvedDetail.canOperate" class="secondary-button" type="button" data-testid="add-installed-tool-service" @click="emit('service')"><Wrench :size="13" />新增服务记录</button>
                <button v-if="resolvedDetail.canOperate" class="secondary-button" type="button" data-testid="edit-installed-tool" @click="emit('edit')"><Pencil :size="13" />编辑主数据</button>
              </div>
            </header>
            <div class="record-summary hero-summary">
              <div><small>Customer / Site</small><strong>{{ resolvedDetail.account }}</strong><span>{{ resolvedDetail.site }} · {{ resolvedDetail.location || '位置待确认' }}</span></div>
              <div><small>当前生命周期阶段</small><strong>{{ currentStage }}</strong><span>{{ completedStages }}/5 节点已完成</span></div>
              <div><small>Software / OS</small><strong>{{ resolvedDetail.software || '—' }}</strong><span>{{ resolvedDetail.operatingSystem || '—' }}</span></div>
              <div><small>Warranty End</small><strong>{{ resolvedDetail.warrantyEnd || '待确认' }}</strong><span>{{ resolvedDetail.serviceContract || '服务等级待确认' }}</span></div>
            </div>
          </section>

          <section class="workspace-panel master-data-panel" data-testid="installed-tool-master-data">
            <header><div><span class="eyebrow">MASTER DATA</span><h2>设备主数据</h2></div><span>一机一档 · 数据来自当前设备接口</span></header>
            <div class="master-data-grid">
              <div data-master-tone="identity"><small>Serial Number</small><strong>{{ resolvedDetail.serial || '—' }}</strong></div>
              <div data-master-tone="identity"><small>Model</small><strong>{{ resolvedDetail.model || '—' }}</strong></div>
              <div data-master-tone="identity"><small>Customer</small><strong>{{ resolvedDetail.account || '—' }}</strong><span>{{ resolvedDetail.accountId }}</span></div>
              <div data-master-tone="identity"><small>Site / Location</small><strong>{{ resolvedDetail.site || '—' }}</strong><span>{{ resolvedDetail.location || '位置待确认' }}</span></div>
              <div data-master-tone="ownership"><small>Engineer Owner</small><strong>{{ personnelDisplayName(resolvedDetail.engineerOwner) || '—' }}</strong></div>
              <div data-master-tone="ownership"><small>Sales Owner</small><strong>{{ personnelDisplayName(resolvedDetail.salesOwner) || '—' }}</strong></div>
              <div data-master-tone="ownership"><small>Sales Order</small><strong>{{ resolvedDetail.salesOrder || '—' }}</strong></div>
              <div data-master-tone="ownership"><small>Contract</small><strong>{{ resolvedDetail.contract || '—' }}</strong></div>
              <div data-master-tone="ownership"><small>Ownership</small><strong>{{ resolvedDetail.ownershipType || '—' }}</strong></div>
              <div data-master-tone="ownership"><small>Source Booking</small><strong>{{ resolvedDetail.sourceBookingId || '—' }}</strong></div>
              <div data-master-tone="ownership"><small>Source Opportunity</small><strong>{{ resolvedDetail.sourceOpportunityId || '—' }}</strong></div>
              <div data-master-tone="configuration"><small>Software / Firmware</small><strong>{{ resolvedDetail.software || '—' }} / {{ resolvedDetail.firmware || '—' }}</strong></div>
              <div data-master-tone="configuration"><small>Operating System</small><strong>{{ resolvedDetail.operatingSystem || '—' }}</strong></div>
              <div data-master-tone="configuration"><small>Configuration</small><strong>{{ resolvedDetail.configuration || '—' }}</strong></div>
              <div data-master-tone="service"><small>Warranty</small><strong>{{ resolvedDetail.warrantyStart || '待确认' }} → {{ resolvedDetail.warrantyEnd || '待确认' }}</strong></div>
              <div data-master-tone="service"><small>Service Contract / PM</small><strong>{{ resolvedDetail.serviceContract || '—' }}</strong><span>{{ resolvedDetail.pmCycle || 'PM 周期待确认' }}</span></div>
              <div data-master-tone="service"><small>Last Service</small><strong>{{ resolvedDetail.lastService || '—' }}</strong></div>
            </div>
          </section>

          <nav class="detail-tabs" aria-label="设备档案分区">
            <button type="button" :class="{ active: activeSection === 'lifecycle' }" @click="activeSection = 'lifecycle'"><PackageCheck :size="14" />交付生命周期</button>
            <button type="button" :class="{ active: activeSection === 'configuration' }" @click="activeSection = 'configuration'"><History :size="14" />版本与配置</button>
            <button type="button" :class="{ active: activeSection === 'warranty' }" @click="activeSection = 'warranty'"><ShieldCheck :size="14" />质保与服务</button>
          </nav>

          <section v-if="activeSection === 'lifecycle'" class="workspace-panel lifecycle-panel">
            <header><div><span class="eyebrow">DELIVERY TRACK</span><h2>Delivery & Acceptance Lifecycle</h2><small>FAT → Shipment → Installation → SAT → Warranty</small></div><span :class="['issue-chip', { clear: openIssueCount === 0 }]"><AlertTriangle :size="12" />{{ openIssueCount }} 项记录含遗留问题</span></header>
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
                <span><b>{{ stage.label }}</b><small>{{ stage.date || '日期待确认' }}</small></span>
              </button>
            </div>
            <div class="stage-records">
              <article v-for="stage in resolvedDetail.milestones" :key="stage.label" :class="{ open: expandedStage === stage.label }">
                <button type="button" class="stage-record-head" @click="expandedStage = expandedStage === stage.label ? '' : stage.label">
                  <span :class="['stage-state-dot', `is-${stage.state.toLowerCase()}`]" />
                  <span><strong>{{ stage.label }}</strong><small>{{ historyFor(stage)?.comment || '暂无补充说明' }}</small></span>
                  <span><small>完成日期</small><b>{{ historyFor(stage)?.completedAt || '—' }}</b></span>
                  <span class="workspace-badge" :class="stageTone(stage.state)">{{ stage.state === 'Done' ? '已完成' : stage.state === 'Current' ? '进行中' : '待开始' }}</span>
                  <ChevronDown :size="14" />
                </button>
                <div v-if="expandedStage === stage.label" class="stage-record-detail">
                  <template v-if="historyFor(stage)">
                    <div><small>操作人</small><strong>{{ personnelDisplayName(historyFor(stage)?.actor || '') || historyFor(stage)?.actor }}</strong></div>
                    <div><small>验收结果</small><strong>{{ historyFor(stage)?.result || '—' }}</strong></div>
                    <div><small>遗留问题</small><strong>{{ historyFor(stage)?.openIssues || '无' }}</strong></div>
                    <div><small>客户确认</small><strong>{{ historyFor(stage)?.customerSignoff || '—' }}</strong></div>
                    <div class="evidence"><small>证据记录</small><div><span v-for="file in historyFor(stage)?.evidence" :key="file">{{ file }}</span></div><span v-if="!historyFor(stage)?.evidence.length">当前节点暂无证据记录</span></div>
                  </template>
                  <p v-else class="empty-record">该节点尚无完成记录。</p>
                </div>
              </article>
            </div>
          </section>

          <template v-else-if="activeSection === 'configuration'">
            <section class="workspace-panel configuration-panel">
              <header><div><span class="eyebrow">CURRENT BASELINE</span><h2>当前版本与现场配置</h2></div><span class="workspace-badge info">{{ resolvedDetail.ownershipType || '归属待确认' }}</span></header>
              <div class="record-summary configuration-summary">
                <div><small>Current Software</small><strong>{{ resolvedDetail.software || '—' }}</strong></div>
                <div><small>Current Firmware</small><strong>{{ resolvedDetail.firmware || '—' }}</strong></div>
                <div><small>Operating System</small><strong>{{ resolvedDetail.operatingSystem || '—' }}</strong></div>
                <div><small>Configuration</small><strong>{{ resolvedDetail.configuration || '—' }}</strong></div>
              </div>
            </section>
            <section class="workspace-panel">
              <header><div><span class="eyebrow">CHANGE LOG</span><h2>软件 / 固件 / 操作系统 / 配置变更历史</h2></div><span class="workspace-badge info">{{ resolvedDetail.versionHistory.length }} 条记录</span></header>
              <div v-if="resolvedDetail.versionHistory.length" class="table-wrap">
                <table class="record-table">
                  <thead><tr><th>日期</th><th>类型</th><th>原值</th><th>新值</th><th>操作人</th><th>原因</th></tr></thead>
                  <tbody>
                    <tr v-for="item in resolvedDetail.versionHistory" :key="item.id">
                      <td>{{ formatDisplayDate(item.changeDate) }}</td><td><b>{{ item.changeType }}</b></td><td>{{ item.fromValue || '—' }}</td><td><strong>{{ item.toValue }}</strong></td><td>{{ personnelDisplayName(item.actor) || item.actor }}</td><td>{{ item.reason }}<small v-if="item.comment">{{ item.comment }}</small></td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p v-else class="empty-record padded">暂无版本或配置变更记录。</p>
            </section>
          </template>

          <template v-else>
            <section class="warranty-grid">
              <article class="workspace-panel warranty-panel">
                <header><div><span class="eyebrow">COVERAGE</span><h2>质保状态</h2></div><span class="workspace-badge positive">{{ resolvedDetail.serviceContract || '服务等级待确认' }}</span></header>
                <div class="warranty-body">
                  <div class="health-score" :style="{ '--health': `${resolvedDetail.completeness}%` }" :aria-label="`设备档案完整度 ${resolvedDetail.completeness}%`"><strong>{{ resolvedDetail.completeness }}%</strong><span>档案完整度</span></div>
                  <div>
                    <p><span>质保开始</span><b>{{ resolvedDetail.warrantyStart || '待确认' }}</b></p>
                    <p><span>质保结束</span><b>{{ resolvedDetail.warrantyEnd || '待确认' }}</b></p>
                    <p><span>PM 周期</span><b>{{ resolvedDetail.pmCycle || '待确认' }}</b></p>
                  </div>
                </div>
              </article>
              <article class="workspace-panel document-panel">
                <header><div><span class="eyebrow">DOCUMENTS</span><h2>适用文档</h2></div><span class="workspace-badge info">{{ resolvedDetail.documents.length }} 份</span></header>
                <ul class="document-links"><li v-for="document in resolvedDetail.documents" :key="document"><FileCheck2 :size="15" /><span>{{ document }}</span><button type="button" @click="emit('document', document)"><Download :size="12" />查看</button></li></ul><p v-if="!resolvedDetail.documents.length" class="empty-record padded">暂无适用文档。</p>
              </article>
            </section>
            <section class="workspace-panel service-panel">
              <header><div><span class="eyebrow">SERVICE HISTORY</span><h2>质保维修与服务记录</h2></div><span class="workspace-badge info">Last service {{ resolvedDetail.lastService || '—' }}</span></header>
              <div v-if="resolvedDetail.serviceHistory.length" class="service-list">
                <article v-for="item in resolvedDetail.serviceHistory" :key="item.id">
                  <Wrench :size="15" />
                  <div><strong>{{ item.serviceType }}</strong><small>{{ formatDisplayDate(item.serviceDate) }} · {{ personnelDisplayName(item.actor) || item.actor }}</small></div>
                  <span>{{ item.result }}</span>
                  <small v-if="item.openIssues" class="service-alert">遗留：{{ item.openIssues }}</small>
                  <small v-if="item.nextAction" class="service-next">下一步：{{ item.nextAction }} · {{ personnelDisplayName(item.actionOwner) || item.actionOwner }} · {{ item.due }}</small>
                </article>
              </div>
              <p v-else class="empty-record padded">暂无质保或服务记录。</p>
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
