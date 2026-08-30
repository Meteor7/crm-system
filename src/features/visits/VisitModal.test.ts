import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { accounts } from '@/api/mock-data'
import VisitModal from './VisitModal.vue'

describe('VisitModal business dates', () => {
  afterEach(() => vi.useRealTimers())

  it('defaults a new Visit to the current Shanghai date', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-02T16:30:00.000Z'))

    const wrapper = mount(VisitModal, {
      props: { mode: 'create', accounts },
    })

    expect((wrapper.get('[aria-label="拜访日期"]').element as HTMLInputElement).value).toBe('2026-08-03')
  })

  it('keeps Manager review free of separate Action fields', async () => {
    const wrapper = mount(VisitModal, {
      props: { mode: 'review', accounts, visit: null },
    })

    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toHaveLength(1)
    expect(wrapper.find('[aria-label="行动负责人"]').exists()).toBe(false)
  })

  it('retains the Opportunity supplied by the cross-module create route', async () => {
    const wrapper = mount(VisitModal, {
      props: { mode: 'create', accounts, initialOpportunityId: 'CRM-OPP-00201' },
    })

    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ opportunityId: 'CRM-OPP-00201' })
  })

  it('requests quick Contact creation for the selected account', async () => {
    const wrapper = mount(VisitModal, { props: { mode: 'create', accounts } })

    await wrapper.get('[data-testid="create-contact"]').trigger('click')

    expect(wrapper.emitted('create-contact')?.[0]).toEqual([accounts[0].id])
  })
})
