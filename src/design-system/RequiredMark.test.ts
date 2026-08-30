import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import RequiredMark from './RequiredMark.vue'

describe('RequiredMark', () => {
  it('renders an accessibility-hidden required marker when enabled', () => {
    const wrapper = mount(RequiredMark)

    expect(wrapper.get('[data-required-mark]').text()).toBe('*')
    expect(wrapper.get('[data-required-mark]').attributes('aria-hidden')).toBe('true')
  })

  it('renders nothing when disabled', () => {
    const wrapper = mount(RequiredMark, { props: { show: false } })

    expect(wrapper.find('[data-required-mark]').exists()).toBe(false)
  })
})
