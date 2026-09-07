import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'
import { setLocale } from '@/i18n'
import QuotationEditor from './QuotationEditor.vue'
import type { QuotationDraftInput } from './types'

describe('QuotationEditor language switching', () => {
  afterEach(() => setLocale('zh-CN'))

  it('localizes payment explanations while preserving stored contract and service text', async () => {
    const modelValue: QuotationDraftInput = {
      primaryContactId: '', addressId: '', quoteDate: '2026-09-07', validityMonths: 3,
      items: [], discountType: 'None', discountValue: '0.00',
      paymentTerms: [{ percentage: '30', triggerCondition: 'Advance', description: '收到订单1周内，买方电汇方式支付订单总价30%作为预付款。' }],
      deliveryMonths: 3, warrantyMonths: 12,
    }
    const original = JSON.parse(JSON.stringify(modelValue))
    const wrapper = mount(QuotationEditor, { props: { modelValue, contacts: [], sites: [], quotationType: 'Device' } })
    const contractText = () => wrapper.findAll('.payment-term-row p, .fixed-terms li').map((item) => item.text())
    const chineseUiText = contractText()
    expect(chineseUiText).toHaveLength(7)
    expect(chineseUiText[0]).toBe(modelValue.paymentTerms[0].description)
    setLocale('en-US')
    await nextTick()
    expect(contractText()[0]).toBe('Within one week of receiving the order, the buyer pays 30% of the order total by bank transfer as an advance payment.')
    expect(contractText().slice(1)).toEqual(chineseUiText.slice(1))
    expect(wrapper.get('.fixed-terms').text()).not.toMatch(/\p{Script=Han}/u)
    expect(wrapper.text()).toContain('Commercial terms')
    expect(modelValue).toEqual(original)
    expect(wrapper.emitted('changed')).toBeUndefined()
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    wrapper.unmount()
  })

  it('refreshes discount labels without changing draft values or emitting edits', async () => {
    const modelValue: QuotationDraftInput = {
      primaryContactId: '', addressId: '', quoteDate: '2026-09-07', validityMonths: 3,
      items: [], discountType: 'Percentage', discountValue: '12.50', paymentTerms: [],
      deliveryMonths: 3, warrantyMonths: 12,
    }
    const wrapper = mount(QuotationEditor, { props: { modelValue, contacts: [], sites: [], quotationType: 'Service' } })
    const labels = () => wrapper.findAll('[data-discount-type]').map(button => button.text())
    expect(labels()).toEqual(['无折扣', '百分比', '固定金额'])

    setLocale('en-US')
    await nextTick()
    expect(labels()).toEqual(['No discount', 'Percentage', 'Fixed amount'])
    expect(wrapper.get('[data-discount-type="Percentage"]').classes()).toContain('active')
    expect(modelValue).toMatchObject({ discountType: 'Percentage', discountValue: '12.50' })
    expect(wrapper.emitted('changed')).toBeUndefined()
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()

    await wrapper.get('[data-discount-type="Fixed Amount"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]?.[0]).toMatchObject({ discountType: 'Fixed Amount', discountValue: '12.50' })
    setLocale('zh-CN')
    await nextTick()
    expect(labels()).toEqual(['无折扣', '百分比', '固定金额'])
    expect(wrapper.emitted('changed')).toHaveLength(1)
    wrapper.unmount()
  })
})
