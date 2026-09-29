import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { evaluations } from '@/api/mock-data'
import CustomerCommentModal from './CustomerCommentModal.vue'

const evaluation = { ...evaluations[2], testRound: 2 }

describe('CustomerCommentModal', () => {
  it('blocks submission until a comment is written', async () => {
    const wrapper = mount(CustomerCommentModal, { props: { evaluation } })
    expect(wrapper.get('[data-submit-customer-comment]').attributes('disabled')).toBeDefined()

    await wrapper.get('[data-customer-comment-body]').setValue('   ')
    expect(wrapper.get('[data-submit-customer-comment]').attributes('disabled')).toBeDefined()
    expect(wrapper.emitted('submit')).toBeUndefined()

    await wrapper.get('[data-customer-comment-body]').setValue('客户认为结果可接受')
    await wrapper.get('[data-submit-customer-comment]').trigger('click')
    expect(wrapper.emitted('submit')?.[0]).toEqual([{ comment: '客户认为结果可接受', outcome: 'archive' }])
  })

  it('preselects retest when opened from the retest action', async () => {
    const wrapper = mount(CustomerCommentModal, { props: { evaluation, defaultOutcome: 'retest' } })
    expect((wrapper.get('[data-outcome-retest]').element as HTMLInputElement).checked).toBe(true)

    await wrapper.get('[data-customer-comment-body]').setValue('误报率仍偏高')
    await wrapper.get('[data-submit-customer-comment]').trigger('click')
    expect(wrapper.emitted('submit')?.[0]).toEqual([{ comment: '误报率仍偏高', outcome: 'retest' }])
  })

  it('shows the round the comment will be filed against', () => {
    const wrapper = mount(CustomerCommentModal, { props: { evaluation } })
    expect(wrapper.text()).toContain('第 2 轮')
  })

  it('pins the overlay to the viewport so the dialog opens centred however far the page is scrolled', () => {
    const wrapper = mount(CustomerCommentModal, { props: { evaluation } })
    document.body.append(wrapper.element)

    expect(getComputedStyle(wrapper.get('.host').element).position).toBe('fixed')
    wrapper.unmount()
  })
})
