import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { evaluations } from '@/api/mock-data'
import { setLocale } from '@/i18n'
import TerminateEvaluationModal from './TerminateEvaluationModal.vue'

describe('TerminateEvaluationModal', () => {
  afterEach(() => setLocale('zh-CN'))

  it('requires a nonblank reason and emits it trimmed', async () => {
    const wrapper = mount(TerminateEvaluationModal, { props: { evaluation: evaluations[2] } })
    const reason = wrapper.get('[aria-label="终止原因"]')
    expect(reason.attributes('maxlength')).toBe('1000')

    await wrapper.get('.modal-card form').trigger('submit')
    expect(wrapper.get('[role="alert"]').text()).toBe('请填写终止原因')
    await reason.setValue('   ')
    await wrapper.get('.modal-card form').trigger('submit')
    expect(wrapper.emitted('submit')).toBeUndefined()

    setLocale('en-US')
    await flushPromises()
    expect(wrapper.get('[role="dialog"]').attributes('aria-label')).toBe('Terminate Demo')
    expect(wrapper.get('[role="alert"]').text()).toBe('A reason is required')

    await wrapper.get('[aria-label="Termination reason"]').setValue('  Customer paused the project  ')
    await wrapper.get('.modal-card form').trigger('submit')
    expect(wrapper.emitted('submit')).toEqual([[{ reason: 'Customer paused the project' }]])
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('shows a server refusal with its Request ID', () => {
    const wrapper = mount(TerminateEvaluationModal, {
      props: { evaluation: evaluations[2], submitError: 'Evaluation is already Rejected.', requestId: 'req-terminate' },
    })
    expect(wrapper.get('[role="alert"]').text()).toContain('Evaluation is already Rejected.')
    expect(wrapper.get('[role="alert"]').text()).toContain('req-terminate')
  })

  it('clears the missing-reason error as soon as the reason is edited', async () => {
    const wrapper = mount(TerminateEvaluationModal, { props: { evaluation: evaluations[2] } })
    await wrapper.get('.modal-card form').trigger('submit')
    expect(wrapper.get('[role="alert"]').text()).toBe('请填写终止原因')

    await wrapper.get('[aria-label="终止原因"]').setValue('C')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.emitted('submit')).toBeUndefined()
  })

  it('shows the server refusal again once the missing-reason error is answered', async () => {
    const wrapper = mount(TerminateEvaluationModal, {
      props: { evaluation: evaluations[2], submitError: 'Connection interrupted', requestId: 'req-terminate-network' },
    })
    const reason = wrapper.get('[aria-label="终止原因"]')
    await reason.setValue('  ')
    await wrapper.get('.modal-card form').trigger('submit')
    expect(wrapper.get('[role="alert"]').text()).toBe('请填写终止原因')

    await reason.setValue('Customer paused the project')
    const alert = wrapper.get('[role="alert"]')
    expect(alert.text()).toContain('Connection interrupted')
    expect(alert.text()).toContain('req-terminate-network')
    expect(alert.text()).not.toContain('请填写终止原因')
  })
})
