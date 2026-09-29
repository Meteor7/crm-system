import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import { setLocale } from '@/i18n'
import ReviewConversionPanel from './ReviewConversionPanel.vue'
import type { PipelineCoverage, StageConversions } from './types'

export const conversions = (): StageConversions => ({ start: '2024-09-22', end: '2026-09-22', verifiedFrom: '2024-01-01T00:00:00Z', complete: true, thresholdPercent: 45,
  items: [{ fromStage: 'qualified_opportunity', toStage: 'demo_done', fromCount: 20, toCount: 8, rate: { state: 'ready', value: '40.00' }, bottleneck: true },
    { fromStage: 'quotation_sent', toStage: 'po_received', fromCount: 8, toCount: 0, rate: { state: 'ready', value: '0.00' }, bottleneck: true }] })
export const coverage = (): PipelineCoverage => ({ openPipeline: { state: 'ready', value: '1500000' }, remainingTarget: { state: 'ready', value: '500000' }, ratio: { state: 'ready', value: '3.00' }, referenceMin: 3, referenceMax: 4 })

beforeEach(() => setLocale('zh-CN'))
describe('Review conversion panel', () => {
  it('shows actual ratios, bottlenecks, optional-stage skip and navigable samples', async () => {
    const wrapper = mount(ReviewConversionPanel, { props: { conversions: conversions(), coverage: coverage() } })
    expect(wrapper.get('.coverage-ratio').text()).toBe('3×')
    expect(wrapper.findAll('tr.bottleneck')).toHaveLength(2)
    expect(wrapper.text()).toContain('S5 报价已发出')
    expect(wrapper.text()).toContain('S7 已收到 PO')
    expect(wrapper.text()).toContain('0%')
    await wrapper.findAll('tbody button')[3].trigger('click')
    expect(wrapper.emitted('details')).toEqual([['reached_po_received']])
    wrapper.unmount()
  })

  it('labels partial samples and does not show missing history as zero percent or a bottleneck', async () => {
    const partial = conversions(); partial.complete = false
    partial.items.forEach(row => { row.rate = { state: 'insufficient', value: null }; row.bottleneck = null })
    const wrapper = mount(ReviewConversionPanel, { props: { conversions: partial } })
    expect(wrapper.get('[role="status"]').text()).toContain('已记录样本')
    expect(wrapper.findAll('tr.bottleneck')).toHaveLength(0)
    expect(wrapper.get('tbody').text()).not.toContain('0%')
    expect(wrapper.get('tbody').text()).toContain('数据不足')
    setLocale('en-US'); await wrapper.vm.$nextTick()
    expect(wrapper.get('[role="status"]').text()).toContain('not complete totals')
    wrapper.unmount()
  })

  it('explains completed targets, absent targets and unsupported scopes without numeric ratios', async () => {
    const data = coverage(); data.remainingTarget = { state: 'ready', value: '-1' }
    data.ratio = { state: 'not_applicable', value: null, reason: 'annual_target_met' }
    const wrapper = mount(ReviewConversionPanel, { props: { coverage: data } })
    expect(wrapper.text()).toContain('年度目标已达成')
    expect(wrapper.get('.coverage-ratio').text()).toBe('不适用')
    await wrapper.setProps({ coverage: { ...data, ratio: { state: 'not_applicable', value: null } } })
    expect(wrapper.text()).toContain('请选择单个销售')
    await wrapper.setProps({ coverage: { ...data, ratio: { state: 'not_set', value: null } } })
    expect(wrapper.text()).toContain('设置该销售的年度订单目标')
    wrapper.unmount()
  })
})
