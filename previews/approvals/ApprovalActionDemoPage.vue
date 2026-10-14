<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, Check, FileText, ShieldCheck } from '@lucide/vue'
import { useAppStore } from '@/stores/app'
import { approvalLabels, approvalTarget, type ApprovalItem } from '@/features/approvals/approval-queue'
import { formatDisplayDateTime } from '@/domain/time'
import { demoViewer } from './demo-fixtures'
import { previewApprovalItems } from './demo-state'

const route = useRoute(), app = useAppStore()
const viewer = computed(() => demoViewer(route.query.role === 'Engineer' || route.query.role === 'Sales' ? route.query.role : 'Manager'))
const item = computed(() => previewApprovalItems(viewer.value).find(candidate => {
  const target = approvalTarget(candidate)
  return candidate.id === route.query.approval && target.path === route.path && Object.entries(target.query ?? {}).every(([key, value]) => route.query[key] === value)
}))
const decision = ref('approve'), comment = ref('')
watch([() => viewer.value.id, () => item.value?.id], () => { decision.value = 'approve'; comment.value = '' })
const backRoute = computed(() => ({ path: '/', query: { role: viewer.value.role } }))
const actionLabel = computed(() => item.value?.kind === 'demo-engineering' ? '确认评估' : item.value?.kind === 'rfq-engineering' ? '提交技术评审' : item.value?.kind === 'customer-review' ? '确认客户结论' : item.value?.kind === 'test-review' ? '确认审核' : '提交审批')
const fields = computed(() => {
  const current = item.value
  if (!current) return []
  const common = [{ name: '客户', value: current.customer }, { name: '单据编号', value: current.sourceId }, { name: '设备', value: current.equipment }]
  const details: Partial<Record<ApprovalItem['kind'], Array<{ name: string; value: string }>>> = {
    demo: [{ name: '工程评估', value: '已完成，测试条件和资源窗口已确认' }, { name: '申请目标', value: '验证晶圆表面缺陷检测能力与节拍' }],
    'demo-engineering': [{ name: '样品要求', value: '12 英寸晶圆，检测正面颗粒及划痕' }, { name: '评估重点', value: '检测可行性、样品准备和设备资源' }],
    quotation: [{ name: '报价版本', value: 'V2 · 待审批版本' }, { name: '审批内容', value: '设备配置、付款节点及交付条款' }],
    production: [{ name: '申请类型', value: '内部生产审批' }, { name: '审批内容', value: '生产计划、预计交付及 Booking 信息' }],
    visit: [{ name: '会议主题', value: '量测方案现场沟通' }, { name: '纪要内容', value: '客户需求变化及下一次沟通计划' }],
    rfq: [{ name: '技术评审', value: '已完成工程意见' }, { name: '审批内容', value: 'RFQ 条款与业务推进条件' }],
    'rfq-engineering': [{ name: '评审内容', value: '设备技术条件与客户规格要求' }],
    document: [{ name: '申请文档', value: '设备技术规格书' }, { name: '使用目的', value: '客户方案评估与技术沟通' }],
    'test-review': [{ name: '测试轮次', value: '第 1 轮' }, { name: '审核内容', value: '测试指标、原始数据及报告结论' }],
    'customer-review': [{ name: '报告状态', value: 'Customer 报告已就绪' }, { name: '确认内容', value: '客户反馈、本轮评审结论及是否重测' }],
  }
  return [...common, ...(details[current.kind] ?? [])]
})
watch(viewer, value => {
  if (app.bootstrap) app.bootstrap = { ...app.bootstrap, user: { ...app.bootstrap.user, id: value.id, name: value.name, initials: value.name.slice(0, 1), role: value.role }, capabilities: [...value.capabilities] }
}, { immediate: true })
</script>

<template>
  <main class="approval-action-demo">
    <RouterLink class="back-to-inbox" :to="backRoute"><ArrowLeft :size="15" />返回待审批</RouterLink>
    <template v-if="item">
      <header class="action-page-heading"><div><span>{{ item.sourceLabel }} / {{ item.sourceId }}</span><h1>{{ item.stage }}</h1><p>{{ item.title }}</p></div><span class="pending-label">待处理</span></header>
      <div class="action-page-context"><div><small>当前处理人</small><strong>{{ viewer.name }}</strong></div><div><small>提交人</small><strong>{{ item.requester }}</strong></div><div><small>提交时间</small><strong>{{ formatDisplayDateTime(item.submittedAt) }}</strong></div><div><small>业务类型</small><strong>{{ approvalLabels[item.kind] }}</strong></div></div>
      <div class="approval-action-layout">
        <section class="request-materials"><header><FileText :size="17" /><h2>申请资料</h2></header><dl><div v-for="field in fields" :key="field.name"><dt>{{ field.name }}</dt><dd>{{ field.value }}</dd></div></dl><section class="request-description"><h3>事项说明</h3><p>{{ item.description }}</p></section></section>
        <section class="decision-panel"><header><ShieldCheck :size="17" /><h2>{{ item.stage }}</h2></header><p class="decision-hint">核实业务资料后，在此记录处理结论。</p><div class="decision-choices"><label><input v-model="decision" type="radio" value="approve" name="decision" />{{ item.kind === 'customer-review' ? '确认通过' : item.kind === 'demo-engineering' ? '确认可行' : '同意' }}</label><label><input v-model="decision" type="radio" value="reject" name="decision" />{{ item.kind === 'customer-review' ? '需要重测' : '退回补充' }}</label></div><label class="decision-comment">{{ item.kind === 'customer-review' ? '客户反馈' : item.kind === 'rfq-engineering' ? '技术评审意见' : '处理意见' }}<textarea v-model="comment" rows="6" placeholder="填写本次处理意见" /></label><p class="preview-only"><Check :size="13" />前端演示，实际提交接口尚未接入。</p><button class="submit-decision" type="button" disabled>{{ actionLabel }}</button></section>
      </div>
    </template>
    <section v-else class="not-eligible"><ShieldCheck :size="30" /><h1>当前没有可处理的事项</h1><p>该事项不属于当前账号的待审批范围，或已不再等待处理。</p></section>
  </main>
</template>

<style scoped>
:global(.route-content:has(.approval-action-demo)){max-width:1600px;padding:26px 30px}.approval-action-demo{color:var(--crm-text);font-family:var(--crm-font-sans)}.back-to-inbox{display:inline-flex;align-items:center;gap:7px;margin-bottom:24px;color:var(--crm-link);font-size:12px;text-decoration:none}.action-page-heading{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:22px}.action-page-heading>div>span{color:var(--crm-text-muted);font-size:11px}.action-page-heading h1{margin:9px 0;font-size:28px;font-weight:650;letter-spacing:-.03em}.action-page-heading p{margin:0;color:var(--crm-text-muted);font-size:13px!important}.pending-label{padding:6px 10px;background:var(--crm-brand-soft);color:var(--crm-link);border-radius:6px;font-size:11px}.action-page-context{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:20px;padding:20px 0;border-top:1px solid var(--crm-line);border-bottom:1px solid var(--crm-line);margin-bottom:26px}.action-page-context>div{display:grid;gap:7px}.action-page-context small{color:var(--crm-text-muted);font-size:10px}.action-page-context strong{font-size:12px;font-weight:500}.approval-action-layout{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(300px,1fr);gap:22px;align-items:start}.request-materials,.decision-panel{background:#fff;border:1px solid var(--crm-line);border-radius:14px;padding:22px}.request-materials>header,.decision-panel>header{display:flex;gap:9px;align-items:center;color:var(--crm-navy)}.request-materials h2,.decision-panel h2{margin:0;font-size:16px;font-weight:600}.request-materials dl{margin:18px 0 0}.request-materials dl>div{display:grid;grid-template-columns:110px 1fr;gap:18px;padding:15px 0;border-bottom:1px solid var(--crm-line);font-size:12px}.request-materials dt{color:var(--crm-text-muted)}.request-materials dd{margin:0;font-size:12px!important;line-height:1.6}.request-description{padding-top:21px}.request-description h3{margin:0 0 9px;font-size:13px}.request-description p{margin:0;color:var(--crm-text-muted);font-size:12px!important;line-height:1.85}.decision-hint{margin:10px 0 18px;color:var(--crm-text-muted);font-size:12px!important;line-height:1.6}.decision-choices{display:flex;gap:20px;padding:14px 0;border-top:1px solid var(--crm-line);border-bottom:1px solid var(--crm-line);margin-bottom:20px}.decision-choices label{display:flex;gap:7px;align-items:center;font-size:12px!important}.decision-choices input{accent-color:var(--crm-brand)}.decision-comment{display:grid;gap:9px;color:var(--crm-text-muted);font-size:11px!important}.decision-comment textarea{width:100%;padding:10px 12px;line-height:1.6;border:1px solid var(--crm-line);border-radius:8px;resize:vertical;font:inherit;font-size:12px!important;color:var(--crm-text);outline:0}.decision-comment textarea:focus{border-color:var(--crm-brand);box-shadow:0 0 0 3px var(--crm-brand-soft)}.preview-only{display:flex;align-items:center;gap:6px;margin:15px 0;color:var(--crm-text-muted);font-size:10px!important}.submit-decision{width:100%;height:38px;border:1px solid var(--crm-line);border-radius:8px;background:var(--crm-surface);color:#92969a;font-size:12px!important;cursor:not-allowed}.not-eligible{display:grid;justify-items:center;gap:12px;padding:70px 20px;color:var(--crm-text-muted);text-align:center}.not-eligible h1{margin:0;color:var(--crm-text);font-size:22px}.not-eligible p{font-size:12px!important}.approval-action-demo a:focus-visible,.approval-action-demo input:focus-visible{outline:2px solid var(--crm-brand);outline-offset:3px}@media(max-width:1050px){.approval-action-layout{grid-template-columns:1fr}.action-page-context{grid-template-columns:1fr 1fr}}@media(max-width:600px){:global(.route-content:has(.approval-action-demo)){padding:20px 16px}.action-page-heading h1{font-size:24px}.request-materials,.decision-panel{padding:17px}.request-materials dl>div{grid-template-columns:85px 1fr;gap:12px}.action-page-context{gap:16px}.preview-only{align-items:start}}
</style>
