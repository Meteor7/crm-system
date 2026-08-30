import { describe, expect, it } from 'vitest'
import { buildAccountContributionOption, buildBookingOption, buildCountBreakdownOption, buildFunnelOption, buildOwnerPerformanceOption, buildPipelineMixOption, buildValueDistributionOption } from './options'

describe('chart option builders', () => {
  it('keeps dashboard chart labels at the unified caption size or larger', () => {
    const options = [
      buildFunnelOption([{ stage: 'Wafer Demo确认', currency: 'CNY', amount: '100.00', weightedAmount: '70.00', count: 1 }]),
      buildOwnerPerformanceOption([{ owner: 'person002@crm.example.invalid', currency: 'CNY', pipeline: '100.00', weightedPipeline: '70.00', booking: '20.00' }]),
      buildBookingOption([{ label: '2026-07', amount: 20, count: 1 }]),
      buildValueDistributionOption([{ label: '华东', pipeline: 100, booking: 20 }]),
      buildAccountContributionOption([{ label: '客户 A', pipeline: 100, booking: 20 }]),
      buildPipelineMixOption([{ label: 'Frontend', currency: 'CNY', pipeline: '100.00', booking: '20.00' }]),
      buildCountBreakdownOption([{ label: 'Planned', count: 1 }]),
    ]
    const fontSizes: number[] = []
    const collectFontSizes = (value: unknown): void => {
      if (!value || typeof value !== 'object') return
      for (const [key, nestedValue] of Object.entries(value)) {
        if (key === 'fontSize' && typeof nestedValue === 'number') fontSizes.push(nestedValue)
        else collectFontSizes(nestedValue)
      }
    }

    options.forEach(collectFontSizes)

    expect(fontSizes.length).toBeGreaterThan(0)
    expect(Math.min(...fontSizes)).toBeGreaterThanOrEqual(10)
  })

  it('keeps amount, weighted amount and count in the funnel dataset', () => {
    const option = buildFunnelOption([
      { stage: 'Wafer Demo确认', currency: 'CNY', amount: '8000000.00', weightedAmount: '2400000.00', count: 3 },
    ])
    const dataset = Array.isArray(option.dataset) ? option.dataset[0] : option.dataset
    const source = dataset?.source as Array<Record<string, unknown>> | undefined
    const series = Array.isArray(option.series) ? option.series : [option.series]

    expect(source?.[0]).toMatchObject({
      stage: 'Wafer Demo确认', currency: 'CNY', amount: '8000000.00', weightedAmount: '2400000.00', count: 3,
    })
    expect(series[0]).toMatchObject({ type: 'bar' })
  })

  it('shows owner pipeline, weighted pipeline and booking as separate series', () => {
    const option = buildOwnerPerformanceOption([
      { owner: 'person002@crm.example.invalid', currency: 'CNY', pipeline: '100.00', weightedPipeline: '70.00', booking: '20.00' },
    ])
    const series = Array.isArray(option.series) ? option.series : [option.series]

    expect(series.map((item) => item?.name)).toEqual(['Pipeline', '加权 Pipeline', 'Booking'])
  })

  it('uses the approved semantic colors for dashboard data series', () => {
    const owner = buildOwnerPerformanceOption([
      { owner: 'person002@crm.example.invalid', currency: 'CNY', pipeline: '100.00', weightedPipeline: '70.00', booking: '20.00' },
    ])
    const booking = buildBookingOption([{ label: '2026-07', amount: 20, count: 1 }])
    const distribution = buildValueDistributionOption([{ label: '华东', pipeline: 100, booking: 20 }])
    const contribution = buildAccountContributionOption([{ label: '客户 A', pipeline: 100, booking: 20 }])
    const funnel = buildFunnelOption([{ stage: 'Wafer Demo确认', currency: 'CNY', amount: '100.00', weightedAmount: '70.00', count: 1 }])
    const mix = buildPipelineMixOption([{ label: 'Frontend', currency: 'CNY', pipeline: '100.00', booking: '20.00' }])
    const count = buildCountBreakdownOption([{ label: 'Planned', count: 1 }])
    const colors = (series: typeof owner.series) => (Array.isArray(series) ? series : [series])
      .map((item) => (item as { itemStyle?: { color?: string } } | undefined)?.itemStyle?.color)

    expect(colors(owner.series)).toEqual(['#FE9900', '#0D9488', '#6366F1'])
    expect(colors(booking.series)).toEqual(['#6366F1'])
    expect(colors(distribution.series)).toEqual(['#FE9900', '#6366F1'])
    expect(colors(contribution.series)).toEqual(['#FE9900', '#6366F1'])
    expect(colors(funnel.series)).toEqual(['#FE9900'])
    expect(mix.color).toEqual(['#FE9900', '#0D9488', '#6366F1'])
    expect(colors(count.series)).toEqual(['#FE9900'])
  })

  it('uses actual booking months and supports value and count breakdown charts', () => {
    const booking = buildBookingOption([{ label: '2026-07', amount: 100, count: 1 }])
    const distribution = buildValueDistributionOption([{ label: '华东', pipeline: 100, booking: 20 }])
    const count = buildCountBreakdownOption([{ label: 'Planned', count: 2 }])

    expect((booking.xAxis as { data: string[] }).data).toEqual(['2026-07'])
    expect((Array.isArray(distribution.series) ? distribution.series : []).map((item) => item?.name)).toEqual(['Pipeline', 'Booking'])
    expect((count.yAxis as { data: string[] }).data).toEqual(['Planned'])
  })

  it('builds a pipeline-only donut with the open pipeline total', () => {
    const option = buildPipelineMixOption([
      { label: 'Frontend', currency: 'CNY', pipeline: '70000000.00', booking: '20000000.00' },
      { label: 'Advanced Packaging', currency: 'CNY', pipeline: '30000000.00', booking: '10000000.00' },
    ])
    const series = Array.isArray(option.series) ? option.series[0] : option.series

    expect(series).toMatchObject({ type: 'pie', radius: ['56%', '76%'] })
    expect((series as { data: unknown[] }).data).toEqual([
      { name: 'Frontend', value: 70_000_000 },
      { name: 'Advanced Packaging', value: 30_000_000 },
    ])
    expect(option.title).toMatchObject({ text: '¥1.0亿', subtext: 'Open Pipeline' })
  })

  it('uses a horizontal axis for long customer names', () => {
    const option = buildAccountContributionOption([
      { label: '示例企业044有限公司', pipeline: 32_500_000, booking: 0 },
      { label: '示例企业014有限公司', pipeline: 20_500_000, booking: 18_800_000 },
    ])
    const series = Array.isArray(option.series) ? option.series : [option.series]

    expect(option.xAxis).toMatchObject({ type: 'value' })
    expect(option.yAxis).toMatchObject({
      type: 'category',
      data: ['示例企业044有限公司', '示例企业014有限公司'],
    })
    expect(series.map((item) => item?.name)).toEqual(['Pipeline', 'Booking'])
  })

})
