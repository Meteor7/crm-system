<script setup lang="ts">
import { useI18n } from '@/i18n'
import { labels, metricText } from './presentation'
import type { Metric, PipelineCoverage, StageConversions } from './types'

defineProps<{ conversions?: StageConversions; coverage?: PipelineCoverage }>()
const emit = defineEmits<{ details: [key: string] }>()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const stageNames = ['qualified_opportunity', 'demo_done', 'customer_budget_approved', 'rfq_validated', 'quotation_sent', 'internal_validation', 'po_received']
const stage = (key: string) => `S${stageNames.indexOf(key) + 1} ${key === 'po_received' ? copy('PO received', '已收到 PO') : labels[key]?.[locale.value === 'en-US' ? 1 : 0] ?? key}`
const value = (metric: Metric, suffix = '') => metric.state === 'ready' && metric.value !== null
  ? `${Number(metric.value).toLocaleString(locale.value, { maximumFractionDigits: 2 })}${suffix}` : metricText(metric, locale.value)
</script>

<template>
  <section class="conversion-panel" :aria-labelledby="conversions ? 'conversion-heading' : 'coverage-heading'">
    <div v-if="conversions" class="conversion-history">
      <header><div><p class="eyebrow">{{ copy('STAGE HISTORY', '阶段历史') }}</p><h2 id="conversion-heading">{{ copy('Stage conversion', '阶段转化率') }}</h2></div><span>{{ conversions.start }} — {{ conversions.end }}</span></header>
      <p class="metric-note">{{ copy('Distinct opportunities reaching each stage in the last 24 months. S6 is optional; the final step is S5 → S7. Click a count to inspect its records.', '近 24 个月内到达各阶段的商机数，按商机去重。S6 可选，最后一步按 S5 → S7 计算。点击数量查看记录。') }}</p>
      <p v-if="!conversions.complete" class="coverage-gap" role="status">{{ copy('History is incomplete; counts below are recorded samples, not complete totals. Rates remain unavailable.', '历史数据不完整；下列数量仅为已记录样本，不是完整总量，转化率暂不可用。') }} <span v-if="conversions.verifiedFrom">{{ copy('Verified history starts', '历史覆盖起点') }} {{ new Date(conversions.verifiedFrom).toLocaleDateString(locale, { timeZone: 'Asia/Shanghai' }) }}.</span></p>
      <div class="conversion-scroll"><table><thead><tr><th>{{ copy('Stage', '阶段') }}</th><th>{{ copy('Reached from', '到达前阶段') }}</th><th>{{ copy('Reached next', '到达后阶段') }}</th><th>{{ copy('Conversion', '转化率') }}</th></tr></thead><tbody>
        <tr v-for="row in conversions.items" :key="row.fromStage" :class="{ bottleneck: row.bottleneck === true }">
          <th scope="row"><span>{{ stage(row.fromStage) }}</span><small>→ {{ stage(row.toStage) }}</small></th>
          <td><button :aria-label="`${stage(row.fromStage)} · ${copy('Recorded opportunities', '已记录商机')}`" @click="emit('details', `reached_${row.fromStage}`)">{{ row.fromCount }}</button></td>
          <td><button :aria-label="`${stage(row.toStage)} · ${copy('Recorded opportunities', '已记录商机')}`" @click="emit('details', `reached_${row.toStage}`)">{{ row.toCount }}</button></td>
          <td><strong>{{ value(row.rate, '%') }}</strong><small v-if="row.bottleneck === true">{{ copy('Below', '低于') }} {{ conversions.thresholdPercent }}%</small><small v-else-if="row.rate.reason === 'no_source_stage'">{{ copy('No source-stage records', '前阶段无记录') }}</small></td>
        </tr>
      </tbody></table></div>
      <p class="metric-note">{{ copy('Each stage is counted independently. Later-stage arrivals can come from before this window, so a ratio may exceed 100%. No stage is inferred from the current stage.', '各阶段分别统计。后阶段商机可能在窗口开始前已到达前阶段，因此比例可能超过 100%；不根据当前阶段推测历史。') }}</p>
    </div>
    <aside v-if="coverage" class="pipeline-coverage" aria-labelledby="coverage-heading">
      <p class="eyebrow">{{ copy('PIPELINE COVERAGE', '商机覆盖') }}</p><h2 id="coverage-heading">{{ copy('Pipeline coverage', '覆盖倍数') }}</h2>
      <strong class="coverage-ratio" data-coverage-ratio>{{ value(coverage.ratio, '×') }}</strong>
      <p v-if="coverage.ratio.reason === 'annual_target_met'" class="metric-note">{{ copy('Annual target met; no remaining target to cover.', '年度目标已达成，没有待覆盖的目标差额。') }}</p>
      <p v-else-if="coverage.targetState === 'not_applicable'" class="metric-note">{{ copy('Clear market and equipment filters. Use an individual salesperson without a region filter, or a territory view without a salesperson filter.', '请清除市场和设备筛选。个人目标视图选择销售并清除区域筛选；地域目标视图清除销售筛选。') }}</p>
      <p v-else-if="coverage.targetState === 'not_set' && coverage.targetScope === 'sales'" class="metric-note">{{ copy('Set this salesperson’s annual order target to calculate coverage.', '设置该销售的年度订单目标后即可计算覆盖倍数。') }}</p>
      <p v-else-if="coverage.targetState === 'not_set' && coverage.targetScope === 'territory'" class="metric-note">{{ copy('Set annual order targets for every leaf territory in this view to calculate coverage.', '为当前范围内的每个末级地域设置年度订单目标后，即可计算覆盖倍数。') }}</p>
      <p v-else-if="coverage.targetState === 'insufficient' && coverage.targetScope === 'territory'" class="metric-note">{{ copy('Complete or correct the leaf territory annual targets and customer region assignments shown in the target sources.', '请按目标来源明细补齐或修正末级地域年度目标及客户区域归属。') }}</p>
      <p v-else-if="coverage.targetState === 'insufficient' && coverage.targetScope === 'sales'" class="metric-note">{{ copy('Correct this salesperson’s invalid or duplicate annual order target before calculating coverage.', '请先修正该销售无效或重复的年度订单目标，再计算覆盖倍数。') }}</p>
      <dl><div><dt>{{ copy('Open S2–S6 · CNY', '未结商机 S2–S6 · 人民币') }}</dt><dd>{{ metricText(coverage.openPipeline, locale, true) }}</dd></div><div><dt>{{ copy('Annual target − YTD orders · CNY', '年度目标 − 年累计订单 · 人民币') }}</dt><dd>{{ metricText(coverage.remainingTarget, locale, true) }}</dd></div></dl>
      <p class="metric-note">{{ copy('Reference range', '参考范围') }} {{ coverage.referenceMin }}–{{ coverage.referenceMax }}× · {{ copy('Open pipeline ÷ remaining annual target. Uses the same CNY amounts, cutoff and scope as Review.', '未结商机金额 ÷ 剩余年度目标，与 Review 使用相同人民币金额、截止日和筛选范围。') }}</p>
    </aside>
  </section>
</template>

<style scoped>
.conversion-panel{display:grid;grid-template-columns:minmax(0,2fr) minmax(230px,1fr);gap:24px;margin-top:20px;padding:24px;border:1px solid var(--crm-line);border-radius:12px;background:var(--crm-surface-raised)}
header{display:flex;align-items:center;justify-content:space-between;gap:16px}header>span,.metric-note{font-size:12px;color:var(--crm-text-muted);line-height:1.65}.eyebrow{margin:0 0 5px;color:var(--crm-teal);font-size:10px;font-weight:750;letter-spacing:1.5px}h2{margin:0;font-size:18px}.coverage-gap{padding:10px 12px;border-radius:6px;background:#fff4df;color:#835500;font-size:12px;line-height:1.7}.conversion-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:10px 8px;border-bottom:1px solid var(--crm-line);text-align:right}th:first-child{text-align:left}thead th{font-weight:500;color:var(--crm-text-muted)}tbody th{font-weight:600}small{display:block;margin-top:4px;font-size:11px;font-weight:400;color:var(--crm-text-muted)}button{border:0;border-bottom:1px dotted currentColor;padding:3px 5px;color:var(--crm-link);background:transparent;cursor:pointer;font:inherit}button:focus-visible{outline:2px solid var(--crm-teal);outline-offset:3px}.bottleneck td:last-child strong,.bottleneck td:last-child small{color:#ad5a12}.pipeline-coverage{padding-left:24px;border-left:1px solid var(--crm-line)}.coverage-ratio{display:block;margin:22px 0;font-size:32px;font-weight:700;color:var(--crm-teal)}dl{margin:20px 0}dl>div{padding:12px 0;border-top:1px solid var(--crm-line)}dt{font-size:12px;color:var(--crm-text-muted)}dd{margin:6px 0 0;font-size:17px;font-weight:600}
@media(max-width:900px){.conversion-panel{grid-template-columns:1fr}.pipeline-coverage{padding:20px 0 0;border-left:0;border-top:1px solid var(--crm-line)}}@media(max-width:600px){.conversion-panel{padding:16px}header{align-items:flex-start;flex-direction:column;gap:6px}th,td{padding:8px 4px}}
</style>
