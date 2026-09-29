import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'
import { setLocale } from '@/i18n'
import ModalShell from './ModalShell.vue'

describe('ModalShell', () => {
  afterEach(() => setLocale('zh-CN'))

  it('updates default action labels when the language changes', async () => {
    const wrapper = mount(ModalShell, { props: { title: 'Test' } })
    expect(wrapper.findAll('footer button').map(button => button.text())).toEqual(['取消', '保存并继续'])

    setLocale('en-US')
    await nextTick()
    expect(wrapper.get('header button').attributes('aria-label')).toBe('Close')
    expect(wrapper.findAll('footer button').map(button => button.text())).toEqual(['Cancel', 'Save and continue'])
    await wrapper.setProps({ busy: true })
    expect(wrapper.get('[data-modal-submit]').text()).toBe('Processing…')

    setLocale('zh-CN')
    await nextTick()
    expect(wrapper.get('header button').attributes('aria-label')).toBe('关闭')
    expect(wrapper.get('footer button').text()).toBe('取消')
    expect(wrapper.get('[data-modal-submit]').text()).toBe('处理中…')
    wrapper.unmount()
  })

  it('preserves explicit action label overrides across language changes', async () => {
    const wrapper = mount(ModalShell, { props: {
      title: 'Test', cancelLabel: 'Discard', closeLabel: 'Dismiss', submitLabel: 'Publish', busyLabel: 'Publishing',
    } })
    setLocale('en-US')
    await nextTick()
    expect(wrapper.get('header button').attributes('aria-label')).toBe('Dismiss')
    expect(wrapper.findAll('footer button').map(button => button.text())).toEqual(['Discard', 'Publish'])
    await wrapper.setProps({ busy: true })
    expect(wrapper.get('[data-modal-submit]').text()).toBe('Publishing')
    wrapper.unmount()
  })

  it('submits through the native form so required and numeric constraints apply', () => {
    const wrapper = mount(ModalShell, { props: { title: 'Test' }, slots: { default: '<input required />' } })

    expect(wrapper.get('[data-modal-submit]').attributes('type')).toBe('submit')
  })

  it('pins the overlay to the viewport so the dialog opens centred however far the page is scrolled', () => {
    const wrapper = mount(ModalShell, { props: { title: 'Test' }, attachTo: document.body })

    const host = getComputedStyle(wrapper.get('.modal-host').element)
    expect(host.position).toBe('fixed')
    expect(host.placeItems).toBe('center')
    wrapper.unmount()
  })
})
