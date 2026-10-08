import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { setLocale } from '@/i18n'
import { reviewFixture } from './review.fixture'
import type { Metric } from './types'
import ReviewActivityBreakdown from './ReviewActivityBreakdown.vue'

describe('quote amount comparison evidence', () => {
  for (const locale of ['en-US', 'zh-CN'] as const) {
    it.each([[false, true], [true, true], [true, false]])(
      `${locale}: explains current incomplete=%s and prior incomplete=%s independently`,
      (currentIncomplete, priorIncomplete) => {
        setLocale(locale)
        const amount = (value: string, incomplete: boolean): Metric => ({ state: incomplete ? 'insufficient' : 'ready', value: incomplete ? null : value })
        const item = reviewFixture().activities.find(row => row.key === 'quotes')!
        item.quoteAmount = { actual: amount('1500000', currentIncomplete), previous: amount('2000000', priorIncomplete),
          known: '1500000', missing: currentIncomplete ? 1 : 0, previousKnown: '2000000', previousMissing: priorIncomplete ? 2 : 0, delta: null }
        const wrapper = mount(ReviewActivityBreakdown, { props: { item } })
        const current = wrapper.find('[data-quote-period="current"]')
        const prior = wrapper.find('[data-quote-period="previous"]')
        expect(current.exists()).toBe(currentIncomplete)
        expect(prior.exists()).toBe(priorIncomplete)
        if (currentIncomplete) {
          expect(current.text()).toContain(locale === 'en-US' ? 'Current recorded subtotal ¥1.5M' : '本期已记录金额小计 ¥1.5M')
          expect(current.text()).toContain(locale === 'en-US' ? '1 quotes without a CNY snapshot' : '1 份报价缺少人民币快照')
        }
        if (priorIncomplete) {
          expect(prior.text()).toContain(locale === 'en-US' ? 'Prior recorded subtotal ¥2M' : '上期已记录金额小计 ¥2M')
          expect(prior.text()).toContain(locale === 'en-US' ? '2 quotes without a CNY snapshot' : '2 份报价缺少人民币快照')
        }
        expect(wrapper.text()).toContain('Δ —')
        wrapper.unmount()
      },
    )
  }
})
