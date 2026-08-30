import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { evaluations } from '@/api/mock-data'
import EvaluationCard from './EvaluationCard.vue'

describe('EvaluationCard alignment', () => {
  it('uses fixed content zones for every Demo and Wafer Test card', () => {
    const wrapper = mount(EvaluationCard, { props: { evaluation: evaluations[0], canWrite: true } })

    expect(wrapper.get('.evaluation-card').classes()).toContain('is-aligned')
    expect(wrapper.get('.runs').attributes('data-scroll-region')).toBe('runs')
    expect(wrapper.get('h3').classes()).toContain('line-clamp-2')
    expect(wrapper.get('.controls').classes()).toContain('card-controls')
  })

  it('offers the Test Run DDL action only during Preparation', async () => {
    const preparation = {
      ...evaluations[0],
      status: 'Requested' as const,
      waferPreparationStatus: 'Pending' as const,
      testPreparationStatus: 'Pending' as const,
    }
    const wrapper = mount(EvaluationCard, { props: { evaluation: preparation, canWrite: true } })

    expect(wrapper.text()).toContain('Test Run DDL')
    await wrapper.get(`[data-set-ddl="${preparation.id}"]`).trigger('click')
    expect(wrapper.emitted('deadline')).toEqual([[preparation]])

    await wrapper.setProps({ evaluation: { ...preparation, status: 'Testing' as const } })
    expect(wrapper.find(`[data-set-ddl="${preparation.id}"]`).exists()).toBe(false)
  })

  it('offers the Test Report upload action only with write access during Testing', async () => {
    const reviewEvaluation = { ...evaluations[0], status: 'Testing' as const }
    const wrapper = mount(EvaluationCard, { props: { evaluation: reviewEvaluation, canWrite: true, canReport: true } })

    expect(wrapper.find('[data-add-run]').exists()).toBe(true)
    await wrapper.get(`[data-report-action="${reviewEvaluation.id}"]`).trigger('click')
    expect(wrapper.emitted('report')).toEqual([[reviewEvaluation]])

    await wrapper.setProps({ canWrite: false })
    expect(wrapper.find(`[data-report-action="${evaluations[0].id}"]`).exists()).toBe(false)
  })

  it('removes the legacy report link while keeping the formal Test Report action', () => {
    const legacyEvaluation = { ...evaluations[0], status: 'Testing' as const, reportLink: 'https://example.com/legacy-report' }
    const wrapper = mount(EvaluationCard, {
      props: { evaluation: legacyEvaluation, canWrite: true, canReport: true },
    })

    expect(wrapper.find('a').exists()).toBe(false)
    expect(wrapper.find(`[data-report-action="${legacyEvaluation.id}"]`).exists()).toBe(true)
  })

  it('shows Test Run only in Test Execution without an On Hold control', async () => {
    const testing = { ...evaluations[0], status: 'Testing' as const }
    const wrapper = mount(EvaluationCard, { props: { evaluation: testing, canWrite: true, canReport: true } })

    expect(wrapper.find(`[data-add-run="${testing.id}"]`).exists()).toBe(true)
    expect(wrapper.find(`[data-hold-evaluation="${testing.id}"]`).exists()).toBe(false)
    expect(wrapper.find(`[data-report-action="${testing.id}"]`).exists()).toBe(true)
    expect(wrapper.find('select').exists()).toBe(false)

    await wrapper.setProps({ evaluation: { ...testing, status: 'Customer Review' as const } })
    expect(wrapper.find(`[data-add-run="${testing.id}"]`).exists()).toBe(false)
    expect(wrapper.find(`[data-report-action="${testing.id}"]`).exists()).toBe(false)
  })

  it('renders workflow buttons and no status select', () => {
    const preparation = {
      ...evaluations[0],
      status: 'Requested' as const,
      waferPreparationStatus: 'Pending' as const,
      testPreparationStatus: 'Pending' as const,
    }
    const wrapper = mount(EvaluationCard, { props: { evaluation: preparation, canWrite: true } })

    expect(wrapper.find('select').exists()).toBe(false)
    expect(wrapper.find('[data-complete-preparation="wafer"]').exists()).toBe(true)
    expect(wrapper.find('[data-complete-preparation="test"]').exists()).toBe(true)
    expect(wrapper.find('[data-reject-evaluation]').exists()).toBe(true)
  })
})
