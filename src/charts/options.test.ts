import type { EChartsOption } from 'echarts'
import { describe, expect, it } from 'vitest'
import { buildAccountContributionOption, buildBookingOption, buildCountBreakdownOption, buildFunnelOption, buildOwnerPerformanceOption, buildPipelineMixOption, buildValueDistributionOption } from './options'

describe('chart option builders', () => {
  it('keeps dashboard chart labels at the unified caption size or larger', () => {
    const options = [
      buildFunnelOption([{ stage: 'demo_done', currency: 'CNY', amount: '100.00', count: 1 }]),
      buildOwnerPerformanceOption([{ owner: 'person002@crm.example.invalid', currency: 'CNY', pipeline: '100.00', booking: '20.00' }]),
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

  it('keeps amount and count in the funnel dataset without a weighted amount', () => {
    const option = buildFunnelOption([
      { stage: 'demo_done', currency: 'CNY', amount: '8000000.00', count: 3 },
    ])
    const dataset = Array.isArray(option.dataset) ? option.dataset[0] : option.dataset
    const source = dataset?.source as Array<Record<string, unknown>> | undefined
    const series = Array.isArray(option.series) ? option.series : [option.series]

    expect(source?.[0]).toEqual({
      stage: 'demo_done', currency: 'CNY', amount: '8000000.00', count: 3,
    })
    expect(series[0]).toMatchObject({ type: 'bar' })
    const stageAxisLabel = (locale: 'zh-CN' | 'en-US') => {
      const yAxis = buildFunnelOption([{ stage: 'demo_done', currency: 'CNY', amount: '1.00', count: 1 }], locale).yAxis as { axisLabel: { formatter: (value: string) => string } }
      return yAxis.axisLabel.formatter('demo_done')
    }
    expect(stageAxisLabel('zh-CN')).toBe('Demo 完成')
    expect(stageAxisLabel('en-US')).toBe('Demo done')
  })

  it('shows owner pipeline and booking as separate series without a weighted pipeline', () => {
    const option = buildOwnerPerformanceOption([
      { owner: 'person002@crm.example.invalid', currency: 'CNY', pipeline: '100.00', booking: '20.00' },
    ])
    const series = Array.isArray(option.series) ? option.series : [option.series]

    expect(series.map((item) => item?.name)).toEqual(['销售管道', '已确认订单'])
  })

  it('uses the approved semantic colors for dashboard data series', () => {
    const owner = buildOwnerPerformanceOption([
      { owner: 'person002@crm.example.invalid', currency: 'CNY', pipeline: '100.00', booking: '20.00' },
    ])
    const booking = buildBookingOption([{ label: '2026-07', amount: 20, count: 1 }])
    const distribution = buildValueDistributionOption([{ label: '华东', pipeline: 100, booking: 20 }])
    const contribution = buildAccountContributionOption([{ label: '客户 A', pipeline: 100, booking: 20 }])
    const funnel = buildFunnelOption([{ stage: 'demo_done', currency: 'CNY', amount: '100.00', count: 1 }])
    const mix = buildPipelineMixOption([{ label: 'Frontend', currency: 'CNY', pipeline: '100.00', booking: '20.00' }])
    const count = buildCountBreakdownOption([{ label: 'Planned', count: 1 }])
    const colors = (series: typeof owner.series) => (Array.isArray(series) ? series : [series])
      .map((item) => (item as { itemStyle?: { color?: string } } | undefined)?.itemStyle?.color)

    expect(colors(owner.series)).toEqual(['#FE9900', '#6366F1'])
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
    expect((Array.isArray(distribution.series) ? distribution.series : []).map((item) => item?.name)).toEqual(['销售管道', '已确认订单'])
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
    expect(option.title).toMatchObject({ text: '¥1.0亿', subtext: '开放销售管道' })
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
    expect(series.map((item) => item?.name)).toEqual(['销售管道', '已确认订单'])
  })

  it('localizes generated labels while retaining raw dimensions and tooltip escaping', () => {
    const row = { stage: "<Acme & Co's>", currency: 'CNY', amount: '8000000.00', count: 3 }
    const zh = buildFunnelOption([row], 'zh-CN')
    const en = buildFunnelOption([row], 'en-US')
    const ownerEn = buildOwnerPerformanceOption([{ owner: 'Customer owner', currency: 'CNY', pipeline: '100.00', booking: '20.00' }], 'en-US')
    const bookingEn = buildBookingOption([{ label: '2026-07', amount: 20, count: 1 }], 'en-US')
    const distributionEn = buildValueDistributionOption([{ label: 'Raw region', pipeline: 100, booking: 20 }], 'en-US')
    const contributionEn = buildAccountContributionOption([{ label: 'Raw account', pipeline: 100, booking: 20 }], 'en-US')
    const mixEn = buildPipelineMixOption([{ label: 'Raw segment', currency: 'CNY', pipeline: '100.00', booking: '20.00' }], 'en-US')
    const countEn = buildCountBreakdownOption([{ label: 'Planned', count: 1 }], 'en-US')
    const series = (option: { series?: unknown }) => (Array.isArray(option.series) ? option.series : [option.series]) as Array<{ name?: string }>
    const axisFormatter = (option: EChartsOption) => ((option.xAxis as { axisLabel?: { formatter?: (value: number) => string } }).axisLabel?.formatter)
    const tooltipFormatter = (option: EChartsOption) => (option.tooltip as { formatter?: (params: never) => string }).formatter
    const valueFormatter = (option: EChartsOption) => (option.tooltip as { valueFormatter?: (value: unknown) => string }).valueFormatter

    expect(series(ownerEn).map((item) => item.name)).toEqual(['Pipeline', 'Booking'])
    expect(series(bookingEn).map((item) => item.name)).toEqual(['Amount'])
    expect(series(distributionEn).map((item) => item.name)).toEqual(['Pipeline', 'Booking'])
    expect(series(contributionEn).map((item) => item.name)).toEqual(['Pipeline', 'Booking'])
    expect(series(mixEn).map((item) => item.name)).toEqual(['Open pipeline'])
    expect(mixEn.title).toMatchObject({ subtext: 'Open pipeline' })
    expect(series(countEn).map((item) => item.name)).toEqual(['Count'])
    expect(axisFormatter(zh)?.(5000000)).toBe('5百万')
    expect(axisFormatter(en)?.(5000000)).toBe('5M')
    expect(valueFormatter(ownerEn)?.(8000000)).toBe('¥8.0M')

    const tooltip = tooltipFormatter(en)?.([{ data: row }] as never)
    expect(tooltip).toContain('&lt;Acme &amp; Co&#39;s&gt;')
    expect(tooltip).toContain('Stage amount ¥8.0M')
    expect(tooltip).not.toContain('Weighted')
    expect(tooltip).toContain('Opportunities 3 opportunities')

    const dataset = (en.dataset as { source?: unknown }).source
    expect(dataset).toEqual([row])
    expect((series(zh)[0] as { name?: string }).name).toBe('销售管道')
  })

})
