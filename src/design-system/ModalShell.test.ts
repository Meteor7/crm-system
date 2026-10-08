import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, ref } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'
import { setLocale } from '@/i18n'
import ModalShell from './ModalShell.vue'

describe('ModalShell', () => {
  afterEach(() => setLocale('zh-CN'))

  it('keeps Tab in the active dialog, closes with Escape, and returns focus to its opener', async () => {
    const opener = document.createElement('button')
    document.body.append(opener)
    opener.focus()
    const wrapper = mount(ModalShell, { props: { title: 'Keyboard' }, attachTo: document.body, slots: { default: '<input aria-label="Draft" />' } })
    await nextTick()
    const close = wrapper.get<HTMLButtonElement>('header button').element
    const submit = wrapper.get<HTMLButtonElement>('[data-modal-submit]').element
    expect(document.activeElement).toBe(close)
    close.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true }))
    expect(document.activeElement).toBe(submit)
    submit.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }))
    expect(document.activeElement).toBe(close)
    await wrapper.get('input').trigger('keydown', { key: 'Escape' })
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
    await nextTick()
    expect(document.activeElement).toBe(opener)
    opener.remove()
  })

  it('leaves Escape to a child popup and handles only the top dialog', async () => {
    const parent = mount(ModalShell, { props: { title: 'Parent' }, attachTo: document.body })
    await nextTick()
    const child = mount(ModalShell, { props: { title: 'Child' }, attachTo: document.body })
    await nextTick()
    const consumed = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
    consumed.preventDefault()
    child.get('header button').element.dispatchEvent(consumed)
    expect(child.emitted('close')).toBeUndefined()
    await child.get('header button').trigger('keydown', { key: 'Escape' })
    expect(child.emitted('close')).toHaveLength(1)
    expect(parent.emitted('close')).toBeUndefined()
    child.unmount()
    await nextTick()
    expect(document.activeElement).toBe(parent.get('header button').element)
    parent.unmount()
  })

  it('takes the dialog opened last as the top one, wherever the page places it', async () => {
    // Opportunity detail places its contact dialog before the PO confirmation that opens it, and the PO
    // confirmation stays open underneath with its draft.
    const Page = defineComponent({
      setup() {
        const parent = ref(true), child = ref(false)
        return () => h('div', [
          child.value ? h(ModalShell, { title: 'Child', onClose: () => { child.value = false } }, () => h('input', { 'aria-label': 'Child field' })) : null,
          parent.value ? h(ModalShell, { title: 'Parent', onClose: () => { parent.value = false } }, () => h('button', { type: 'button', 'data-open-child': '', onClick: () => { child.value = true } }, 'Add contact')) : null,
        ])
      },
    })
    const page = mount(Page, { attachTo: document.body })
    await nextTick()
    const opener = page.get<HTMLButtonElement>('[data-open-child]').element
    opener.focus()
    await page.get('[data-open-child]').trigger('click')
    await nextTick()
    await nextTick()
    const child = page.get('[role="dialog"][aria-label="Child"]')
    const zIndex = (dialog: { element: Element }) => Number(getComputedStyle(dialog.element.parentElement!).zIndex)

    expect(child.element.contains(document.activeElement)).toBe(true)
    expect(zIndex(child)).toBeGreaterThan(zIndex(page.get('[role="dialog"][aria-label="Parent"]')))
    const submit = child.get<HTMLButtonElement>('[data-modal-submit]').element
    submit.focus()
    submit.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }))
    expect(document.activeElement).toBe(child.get('header button').element)

    await child.get('input').trigger('keydown', { key: 'Escape' })
    await nextTick()
    await nextTick()
    expect(page.find('[role="dialog"][aria-label="Child"]').exists()).toBe(false)
    expect(page.find('[role="dialog"][aria-label="Parent"]').exists()).toBe(true)
    expect(document.activeElement).toBe(opener)
    page.unmount()
  })

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

  it('colours the confirm button of a dangerous action, and says the action', () => {
    const plain = mount(ModalShell, { props: { title: 'Test', submitLabel: '合并' } })
    expect(plain.get('[data-modal-submit]').classes()).not.toContain('danger-action')
    expect(plain.get('[data-modal-submit]').text()).toBe('合并')
    const dangerous = mount(ModalShell, { props: { title: 'Test', submitLabel: '删除', danger: true } })
    expect(dangerous.get('[data-modal-submit]').classes()).toContain('danger-action')
    expect(dangerous.get('[data-modal-submit]').text()).toBe('删除')
    plain.unmount()
    dangerous.unmount()
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
