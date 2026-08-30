import type { EChartsOption } from 'echarts'
import type { DashboardDto } from '@/types/crm'

const DASHBOARD_SERIES_COLORS = {
  pipeline: '#FE9900',
  weightedPipeline: '#0D9488',
  booking: '#6366F1',
} as const

const compactMoney = (value: number) => value >= 100000000
  ? `¥${(value / 100000000).toFixed(1)}亿`
  : `¥${(value / 10000).toFixed(0)}万`

export function buildFunnelOption(data: DashboardDto['funnel']): EChartsOption {
  return {
    animationDuration: 500,
    dataset: { source: data },
    grid: { top: 10, right: 34, bottom: 18, left: 76, containLabel: false },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const point = Array.isArray(params) ? params[0] : params
        const row = point?.data as DashboardDto['funnel'][number]
        return `<strong>${row.stage}</strong><br/>阶段金额 ${compactMoney(Number(row.amount))}<br/>加权金额 ${compactMoney(Number(row.weightedAmount))}<br/>商机数量 ${row.count} 个`
      },
    },
    xAxis: { type: 'value', axisLabel: { formatter: (value: number) => `${Math.round(value / 1000000)}m`, color: '#858991', fontSize: 10 }, splitLine: { lineStyle: { color: '#EEEAE4' } } },
    yAxis: { type: 'category', inverse: true, axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: '#4B4F56', fontSize: 10, fontWeight: 600 } },
    series: [{ type: 'bar', encode: { x: 'amount', y: 'stage' }, barWidth: 16, itemStyle: { color: DASHBOARD_SERIES_COLORS.pipeline, borderRadius: [0, 6, 6, 0] }, label: { show: true, position: 'right', color: '#6C7179', fontSize: 10, formatter: (params) => compactMoney(Number((params.data as DashboardDto['funnel'][number]).amount)) } }],
  }
}

export function buildOwnerPerformanceOption(data: DashboardDto['ownerPerformance']): EChartsOption {
  return {
    animationDuration: 500,
    grid: { top: 38, right: 18, bottom: 24, left: 82 },
    legend: { top: 0, right: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 4, textStyle: { color: '#72777F', fontSize: 10 } },
    tooltip: { trigger: 'axis', valueFormatter: (value) => compactMoney(Number(value)) },
    xAxis: { type: 'value', axisLabel: { formatter: (value: number) => `${Math.round(value / 1000000)}m`, color: '#858991', fontSize: 10 }, splitLine: { lineStyle: { color: '#EEEAE4' } } },
    yAxis: { type: 'category', data: data.map((item) => item.owner), axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: '#4B4F56', fontSize: 10, fontWeight: 600 } },
    series: [
      { name: 'Pipeline', type: 'bar', data: data.map((item) => item.pipeline), barMaxWidth: 14, itemStyle: { color: DASHBOARD_SERIES_COLORS.pipeline, borderRadius: [0, 4, 4, 0] } },
      { name: '加权 Pipeline', type: 'bar', data: data.map((item) => item.weightedPipeline), barMaxWidth: 14, itemStyle: { color: DASHBOARD_SERIES_COLORS.weightedPipeline, borderRadius: [0, 4, 4, 0] } },
      { name: 'Booking', type: 'bar', data: data.map((item) => item.booking), barMaxWidth: 14, itemStyle: { color: DASHBOARD_SERIES_COLORS.booking, borderRadius: [0, 4, 4, 0] } },
    ],
  }
}

export function buildBookingOption(data: Array<{ label: string; amount: number; count: number }>): EChartsOption {
  return {
    animationDuration: 500,
    grid: { top: 24, right: 18, bottom: 28, left: 52 },
    tooltip: { trigger: 'axis', valueFormatter: (value) => compactMoney(Number(value)) },
    xAxis: { type: 'category', data: data.map((item) => item.label), axisTick: { show: false }, axisLine: { lineStyle: { color: '#E1DDD6' } }, axisLabel: { color: '#858991', fontSize: 10 } },
    yAxis: { type: 'value', axisLabel: { formatter: (value: number) => `${Math.round(value / 1000000)}m`, color: '#858991', fontSize: 10 }, splitLine: { lineStyle: { color: '#EEEAE4' } } },
    series: [{ name: '金额', type: 'bar', data: data.map((item) => item.amount), barMaxWidth: 34, itemStyle: { color: DASHBOARD_SERIES_COLORS.booking, borderRadius: [6, 6, 0, 0] } }],
  }
}

export function buildValueDistributionOption(data: Array<{ label: string; pipeline: number; booking: number }>): EChartsOption {
  return {
    animationDuration: 500,
    grid: { top: 38, right: 16, bottom: 30, left: 52 },
    legend: { top: 0, right: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 4, textStyle: { color: '#72777F', fontSize: 10 } },
    tooltip: { trigger: 'axis', valueFormatter: (value) => compactMoney(Number(value)) },
    xAxis: { type: 'category', data: data.map((item) => item.label), axisTick: { show: false }, axisLine: { lineStyle: { color: '#E1DDD6' } }, axisLabel: { color: '#858991', fontSize: 10, interval: 0 } },
    yAxis: { type: 'value', axisLabel: { formatter: (value: number) => `${Math.round(value / 1000000)}m`, color: '#858991', fontSize: 10 }, splitLine: { lineStyle: { color: '#EEEAE4' } } },
    series: [
      { name: 'Pipeline', type: 'bar', data: data.map((item) => item.pipeline), barMaxWidth: 22, itemStyle: { color: DASHBOARD_SERIES_COLORS.pipeline, borderRadius: [4, 4, 0, 0] } },
      { name: 'Booking', type: 'bar', data: data.map((item) => item.booking), barMaxWidth: 22, itemStyle: { color: DASHBOARD_SERIES_COLORS.booking, borderRadius: [4, 4, 0, 0] } },
    ],
  }
}

export function buildAccountContributionOption(data: Array<{ label: string; pipeline: number; booking: number }>): EChartsOption {
  return {
    animationDuration: 500,
    grid: { top: 38, right: 18, bottom: 18, left: 112 },
    legend: { top: 0, right: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 4, textStyle: { color: '#72777F', fontSize: 10 } },
    tooltip: { trigger: 'axis', valueFormatter: (value) => compactMoney(Number(value)) },
    xAxis: { type: 'value', axisLabel: { formatter: (value: number) => `${Math.round(value / 1000000)}m`, color: '#858991', fontSize: 10 }, splitLine: { lineStyle: { color: '#EEEAE4' } } },
    yAxis: {
      type: 'category',
      data: data.map((item) => item.label),
      inverse: true,
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: { color: '#4B4F56', fontSize: 10, width: 92, overflow: 'truncate' },
    },
    series: [
      { name: 'Pipeline', type: 'bar', data: data.map((item) => item.pipeline), barMaxWidth: 13, itemStyle: { color: DASHBOARD_SERIES_COLORS.pipeline, borderRadius: [0, 4, 4, 0] } },
      { name: 'Booking', type: 'bar', data: data.map((item) => item.booking), barMaxWidth: 13, itemStyle: { color: DASHBOARD_SERIES_COLORS.booking, borderRadius: [0, 4, 4, 0] } },
    ],
  }
}

export function buildPipelineMixOption(data: DashboardDto['segmentDistribution']): EChartsOption {
  const rows = data.filter((item) => Number(item.pipeline) > 0)
  const total = rows.reduce((sum, item) => sum + Number(item.pipeline), 0)
  return {
    animationDuration: 500,
    color: [DASHBOARD_SERIES_COLORS.pipeline, DASHBOARD_SERIES_COLORS.weightedPipeline, DASHBOARD_SERIES_COLORS.booking],
    title: {
      text: compactMoney(total),
      subtext: 'Open Pipeline',
      left: 'center',
      top: '37%',
      textStyle: { color: '#24272D', fontSize: 18, fontWeight: 800 },
      subtextStyle: { color: '#858991', fontSize: 10, fontWeight: 600 },
    },
    tooltip: { trigger: 'item', valueFormatter: (value) => compactMoney(Number(value)) },
    legend: { bottom: 0, left: 'center', icon: 'circle', itemWidth: 8, itemHeight: 8, textStyle: { color: '#72777F', fontSize: 10 } },
    series: [{
      name: 'Open Pipeline',
      type: 'pie',
      radius: ['56%', '76%'],
      center: ['50%', '44%'],
      avoidLabelOverlap: true,
      itemStyle: { borderColor: '#fff', borderWidth: 3, borderRadius: 6 },
      label: { show: true, color: '#4B4F56', fontSize: 10, formatter: '{d}%' },
      labelLine: { length: 7, length2: 5, lineStyle: { color: '#aebcba' } },
      data: rows.map((item) => ({ name: item.label, value: Number(item.pipeline) })),
    }],
  }
}

export function buildCountBreakdownOption(data: Array<{ label: string; count: number }>): EChartsOption {
  return {
    animationDuration: 500,
    grid: { top: 10, right: 22, bottom: 20, left: 104 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', minInterval: 1, axisLabel: { color: '#858991', fontSize: 10 }, splitLine: { lineStyle: { color: '#EEEAE4' } } },
    yAxis: { type: 'category', data: data.map((item) => item.label), inverse: true, axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: '#4B4F56', fontSize: 10 } },
    series: [{ name: '数量', type: 'bar', data: data.map((item) => item.count), barMaxWidth: 15, itemStyle: { color: DASHBOARD_SERIES_COLORS.pipeline, borderRadius: [0, 5, 5, 0] }, label: { show: true, position: 'right', color: '#6C7179', fontSize: 10 } }],
  }
}
