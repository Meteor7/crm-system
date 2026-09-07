import type { EChartsOption } from 'echarts'
import type { Locale } from '@/i18n'
import type { DashboardDto } from '@/types/crm'

const DASHBOARD_SERIES_COLORS = {
  pipeline: '#FE9900',
  weightedPipeline: '#0D9488',
  booking: '#6366F1',
} as const

type ChartCopy = {
  pipeline: string
  weightedPipeline: string
  booking: string
  amount: string
  openPipeline: string
  count: string
  stageAmount: string
  weightedAmount: string
  opportunityCount: string
  opportunityCountUnit: string
  millionUnit: string
}

const CHART_COPY: Record<Locale, ChartCopy> = {
  'zh-CN': {
    pipeline: '销售管道',
    weightedPipeline: '加权销售管道',
    booking: '已确认订单',
    amount: '金额',
    openPipeline: '开放销售管道',
    count: '数量',
    stageAmount: '阶段金额',
    weightedAmount: '加权金额',
    opportunityCount: '商机数量',
    opportunityCountUnit: '个',
    millionUnit: '百万',
  },
  'en-US': {
    pipeline: 'Pipeline',
    weightedPipeline: 'Weighted pipeline',
    booking: 'Booking',
    amount: 'Amount',
    openPipeline: 'Open pipeline',
    count: 'Count',
    stageAmount: 'Stage amount',
    weightedAmount: 'Weighted amount',
    opportunityCount: 'Opportunities',
    opportunityCountUnit: 'opportunities',
    millionUnit: 'M',
  },
}

const chartCopy = (locale: Locale = 'zh-CN') => CHART_COPY[locale]

const numericValue = (value: unknown) => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

const compactMoney = (value: number, locale: Locale = 'zh-CN') => {
  const normalized = numericValue(value)
  if (locale === 'en-US') {
    return normalized >= 1000000000
      ? `¥${(normalized / 1000000000).toLocaleString(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}B`
      : `¥${(normalized / 1000000).toLocaleString(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}M`
  }

  return normalized >= 100000000
    ? `¥${(normalized / 100000000).toLocaleString(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}亿`
    : `¥${(normalized / 10000).toLocaleString(locale, { maximumFractionDigits: 0 })}万`
}

const compactMillions = (value: number, locale: Locale) => `${Math.round(numericValue(value) / 1000000)}${chartCopy(locale).millionUnit}`

const escapeHtml = (value: unknown) => String(value)
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;')

export function buildFunnelOption(data: DashboardDto['funnel'], locale: Locale = 'zh-CN'): EChartsOption {
  const copy = chartCopy(locale)
  return {
    animationDuration: 500,
    dataset: { source: data },
    grid: { top: 10, right: 34, bottom: 18, left: 76, containLabel: false },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const point = Array.isArray(params) ? params[0] : params
        const row = point?.data as DashboardDto['funnel'][number] | undefined
        if (!row) return ''
        const count = numericValue(row.count)
        return `<strong>${escapeHtml(row.stage)}</strong><br/>${copy.stageAmount} ${compactMoney(numericValue(row.amount), locale)}<br/>${copy.weightedAmount} ${compactMoney(numericValue(row.weightedAmount), locale)}<br/>${copy.opportunityCount} ${escapeHtml(count)} ${copy.opportunityCountUnit}`
      },
    },
    xAxis: { type: 'value', axisLabel: { formatter: (value: number) => compactMillions(value, locale), color: '#858991', fontSize: 10 }, splitLine: { lineStyle: { color: '#EEEAE4' } } },
    yAxis: { type: 'category', inverse: true, axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: '#4B4F56', fontSize: 10, fontWeight: 600 } },
    series: [{ name: copy.pipeline, type: 'bar', encode: { x: 'amount', y: 'stage' }, barWidth: 16, itemStyle: { color: DASHBOARD_SERIES_COLORS.pipeline, borderRadius: [0, 6, 6, 0] }, label: { show: true, position: 'right', color: '#6C7179', fontSize: 10, formatter: (params) => compactMoney(numericValue((params.data as DashboardDto['funnel'][number]).amount), locale) } }],
  }
}

export function buildOwnerPerformanceOption(data: DashboardDto['ownerPerformance'], locale: Locale = 'zh-CN'): EChartsOption {
  const copy = chartCopy(locale)
  return {
    animationDuration: 500,
    grid: { top: 38, right: 18, bottom: 24, left: 82 },
    legend: { top: 0, right: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 4, textStyle: { color: '#72777F', fontSize: 10 } },
    tooltip: { trigger: 'axis', valueFormatter: (value) => compactMoney(numericValue(value), locale) },
    xAxis: { type: 'value', axisLabel: { formatter: (value: number) => compactMillions(value, locale), color: '#858991', fontSize: 10 }, splitLine: { lineStyle: { color: '#EEEAE4' } } },
    yAxis: { type: 'category', data: data.map((item) => item.owner), axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: '#4B4F56', fontSize: 10, fontWeight: 600 } },
    series: [
      { name: copy.pipeline, type: 'bar', data: data.map((item) => item.pipeline), barMaxWidth: 14, itemStyle: { color: DASHBOARD_SERIES_COLORS.pipeline, borderRadius: [0, 4, 4, 0] } },
      { name: copy.weightedPipeline, type: 'bar', data: data.map((item) => item.weightedPipeline), barMaxWidth: 14, itemStyle: { color: DASHBOARD_SERIES_COLORS.weightedPipeline, borderRadius: [0, 4, 4, 0] } },
      { name: copy.booking, type: 'bar', data: data.map((item) => item.booking), barMaxWidth: 14, itemStyle: { color: DASHBOARD_SERIES_COLORS.booking, borderRadius: [0, 4, 4, 0] } },
    ],
  }
}

export function buildBookingOption(data: Array<{ label: string; amount: number; count: number }>, locale: Locale = 'zh-CN'): EChartsOption {
  const copy = chartCopy(locale)
  return {
    animationDuration: 500,
    grid: { top: 24, right: 18, bottom: 28, left: 52 },
    tooltip: { trigger: 'axis', valueFormatter: (value) => compactMoney(numericValue(value), locale) },
    xAxis: { type: 'category', data: data.map((item) => item.label), axisTick: { show: false }, axisLine: { lineStyle: { color: '#E1DDD6' } }, axisLabel: { color: '#858991', fontSize: 10 } },
    yAxis: { type: 'value', axisLabel: { formatter: (value: number) => compactMillions(value, locale), color: '#858991', fontSize: 10 }, splitLine: { lineStyle: { color: '#EEEAE4' } } },
    series: [{ name: copy.amount, type: 'bar', data: data.map((item) => item.amount), barMaxWidth: 34, itemStyle: { color: DASHBOARD_SERIES_COLORS.booking, borderRadius: [6, 6, 0, 0] } }],
  }
}

export function buildValueDistributionOption(data: Array<{ label: string; pipeline: number; booking: number }>, locale: Locale = 'zh-CN'): EChartsOption {
  const copy = chartCopy(locale)
  return {
    animationDuration: 500,
    grid: { top: 38, right: 16, bottom: 30, left: 52 },
    legend: { top: 0, right: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 4, textStyle: { color: '#72777F', fontSize: 10 } },
    tooltip: { trigger: 'axis', valueFormatter: (value) => compactMoney(numericValue(value), locale) },
    xAxis: { type: 'category', data: data.map((item) => item.label), axisTick: { show: false }, axisLine: { lineStyle: { color: '#E1DDD6' } }, axisLabel: { color: '#858991', fontSize: 10, interval: 0 } },
    yAxis: { type: 'value', axisLabel: { formatter: (value: number) => compactMillions(value, locale), color: '#858991', fontSize: 10 }, splitLine: { lineStyle: { color: '#EEEAE4' } } },
    series: [
      { name: copy.pipeline, type: 'bar', data: data.map((item) => item.pipeline), barMaxWidth: 22, itemStyle: { color: DASHBOARD_SERIES_COLORS.pipeline, borderRadius: [4, 4, 0, 0] } },
      { name: copy.booking, type: 'bar', data: data.map((item) => item.booking), barMaxWidth: 22, itemStyle: { color: DASHBOARD_SERIES_COLORS.booking, borderRadius: [4, 4, 0, 0] } },
    ],
  }
}

export function buildAccountContributionOption(data: Array<{ label: string; pipeline: number; booking: number }>, locale: Locale = 'zh-CN'): EChartsOption {
  const copy = chartCopy(locale)
  return {
    animationDuration: 500,
    grid: { top: 38, right: 18, bottom: 18, left: 112 },
    legend: { top: 0, right: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 4, textStyle: { color: '#72777F', fontSize: 10 } },
    tooltip: { trigger: 'axis', valueFormatter: (value) => compactMoney(numericValue(value), locale) },
    xAxis: { type: 'value', axisLabel: { formatter: (value: number) => compactMillions(value, locale), color: '#858991', fontSize: 10 }, splitLine: { lineStyle: { color: '#EEEAE4' } } },
    yAxis: {
      type: 'category',
      data: data.map((item) => item.label),
      inverse: true,
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: { color: '#4B4F56', fontSize: 10, width: 92, overflow: 'truncate' },
    },
    series: [
      { name: copy.pipeline, type: 'bar', data: data.map((item) => item.pipeline), barMaxWidth: 13, itemStyle: { color: DASHBOARD_SERIES_COLORS.pipeline, borderRadius: [0, 4, 4, 0] } },
      { name: copy.booking, type: 'bar', data: data.map((item) => item.booking), barMaxWidth: 13, itemStyle: { color: DASHBOARD_SERIES_COLORS.booking, borderRadius: [0, 4, 4, 0] } },
    ],
  }
}

export function buildPipelineMixOption(data: DashboardDto['segmentDistribution'], locale: Locale = 'zh-CN'): EChartsOption {
  const copy = chartCopy(locale)
  const rows = data.filter((item) => Number(item.pipeline) > 0)
  const total = rows.reduce((sum, item) => sum + numericValue(item.pipeline), 0)
  return {
    animationDuration: 500,
    color: [DASHBOARD_SERIES_COLORS.pipeline, DASHBOARD_SERIES_COLORS.weightedPipeline, DASHBOARD_SERIES_COLORS.booking],
    title: {
      text: compactMoney(total, locale),
      subtext: copy.openPipeline,
      left: 'center',
      top: '37%',
      textStyle: { color: '#24272D', fontSize: 18, fontWeight: 800 },
      subtextStyle: { color: '#858991', fontSize: 10, fontWeight: 600 },
    },
    tooltip: { trigger: 'item', valueFormatter: (value) => compactMoney(numericValue(value), locale) },
    legend: { bottom: 0, left: 'center', icon: 'circle', itemWidth: 8, itemHeight: 8, textStyle: { color: '#72777F', fontSize: 10 } },
    series: [{
      name: copy.openPipeline,
      type: 'pie',
      radius: ['56%', '76%'],
      center: ['50%', '44%'],
      avoidLabelOverlap: true,
      itemStyle: { borderColor: '#fff', borderWidth: 3, borderRadius: 6 },
      label: { show: true, color: '#4B4F56', fontSize: 10, formatter: '{d}%' },
      labelLine: { length: 7, length2: 5, lineStyle: { color: '#aebcba' } },
      data: rows.map((item) => ({ name: item.label, value: numericValue(item.pipeline) })),
    }],
  }
}

export function buildCountBreakdownOption(data: Array<{ label: string; count: number }>, locale: Locale = 'zh-CN'): EChartsOption {
  const copy = chartCopy(locale)
  return {
    animationDuration: 500,
    grid: { top: 10, right: 22, bottom: 20, left: 104 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', minInterval: 1, axisLabel: { color: '#858991', fontSize: 10 }, splitLine: { lineStyle: { color: '#EEEAE4' } } },
    yAxis: { type: 'category', data: data.map((item) => item.label), inverse: true, axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: '#4B4F56', fontSize: 10 } },
    series: [{ name: copy.count, type: 'bar', data: data.map((item) => item.count), barMaxWidth: 15, itemStyle: { color: DASHBOARD_SERIES_COLORS.pipeline, borderRadius: [0, 5, 5, 0] }, label: { show: true, position: 'right', color: '#6C7179', fontSize: 10 } }],
  }
}
