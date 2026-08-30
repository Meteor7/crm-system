import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ModalShell from './ModalShell.vue'

describe('ModalShell', () => {
  it('submits through the native form so required and numeric constraints apply', () => {
    const wrapper = mount(ModalShell, { props: { title: 'Test' }, slots: { default: '<input required />' } })

    expect(wrapper.get('[data-modal-submit]').attributes('type')).toBe('submit')
  })
})
