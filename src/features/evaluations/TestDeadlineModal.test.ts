import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { evaluations } from '@/api/mock-data'
import TestDeadlineModal from './TestDeadlineModal.vue'

describe('TestDeadlineModal', () => {
  it('keeps an empty deadline inside the modal with a local error', async () => {
    const wrapper = mount(TestDeadlineModal, { props: { evaluation: evaluations[0] } })

    await wrapper.get('[aria-label="Test Run DDL"]').setValue('')
    await wrapper.get('.modal-card form').trigger('submit')

    expect(wrapper.get('[role="alert"]').text()).toContain('有效日期')
    expect(wrapper.emitted('submit')).toBeUndefined()
  })

  it('rejects a nonexistent calendar date before emitting', async () => {
    const wrapper = mount(TestDeadlineModal, { props: { evaluation: evaluations[0] } })
    const input = wrapper.get('[aria-label="Test Run DDL"]')
    input.element.setAttribute('type', 'text')

    await input.setValue('2026-09-31')
    await wrapper.get('.modal-card form').trigger('submit')

    expect(wrapper.get('[role="alert"]').text()).toContain('有效日期')
    expect(wrapper.emitted('submit')).toBeUndefined()
  })
})
