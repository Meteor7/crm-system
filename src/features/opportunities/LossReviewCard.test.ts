import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { createAppRouter } from '@/app/router'
import { setLocale } from '@/i18n'
import { useAppStore } from '@/stores/app'
import type { LossReviewDto, StrategyOpportunityDto } from '@/types/workspaces'
import type { UserRole } from '@/types/crm'
import LossReviewCard from './LossReviewCard.vue'

beforeEach(() => setLocale('zh-CN'))
const review = (extra: Partial<LossReviewDto>): LossReviewDto => ({
  id: 'r1', opportunityId: 'OPP-1', stageEventId: 'e1', lostAt: '2026-09-04T02:00:00Z', lostAtStage: 'quotation_sent', lostBy: 'alice',
  lostReason: 'Budget frozen for 2026', status: 'pending', reviewNote: '', reviewedBy: null, reviewedAt: null, reopenedAt: null,
  modified: '2026-09-04T02:00:00.000000Z', history: [], ...extra,
})
async function render(role: UserRole, reviews: LossReviewDto[]) {
  const pinia = createPinia()
  await useAppStore(pinia).loadBootstrap(createMockApi({ role, latency: 0 }))
  const router = createAppRouter()
  const opportunity = { id: 'OPP-1', lossReviews: reviews } as unknown as StrategyOpportunityDto
  const wrapper = mount(LossReviewCard, { props: { opportunity }, global: { plugins: [pinia, router] } })
  await flushPromises()
  return wrapper
}

describe('Opportunity post-mortem card', () => {
  it('shows every loss with its reason, post-mortem state, conclusion and audit trail', async () => {
    const wrapper = await render('Sales', [
      review({ id: 'r2', status: 'pending', reopenedAt: null }),
      review({ id: 'r1', status: 'reviewed', reviewNote: 'Capex frozen; revisit Q1', reviewedBy: 'manager', reviewedAt: '2026-09-05T02:00:00Z', reopenedAt: '2026-09-10T02:00:00Z',
        history: [{ id: 'h2', kind: 'ReviewReverted', status: 'pending', note: 'Capex frozen; revisit Q1', reason: 'Needs a second look', actor: 'manager', at: '2026-09-06T02:00:00Z' }] }),
    ])
    const cards = wrapper.findAll('[data-loss-review-id]')
    expect(cards.map(card => card.get('[data-loss-review-status]').text())).toEqual(['待复盘', '已重开'])
    expect(cards[0].text()).toContain('Budget frozen for 2026')
    expect(cards[1].text()).toContain('Capex frozen; revisit Q1')
    expect(cards[1].get('details').text()).toContain('原因：Needs a second look')
    // Sales can read it; only Managers are pointed to Warnings to record the post-mortem.
    expect(wrapper.find('[data-loss-review-link]').exists()).toBe(false)
  })

  it('points a Manager to Warnings for a pending post-mortem and hides when there is no loss', async () => {
    const manager = await render('Manager', [review({})])
    expect(manager.get('[data-loss-review-link]').attributes('href')).toBe('/warnings')
    const none = await render('Manager', [])
    expect(none.find('[data-testid="opportunity-loss-reviews"]').exists()).toBe(false)
  })
})
