import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import { setLocale } from '@/i18n'
import RegionSelect from './RegionSelect.vue'

const regions = ['World', 'Asia', 'China', 'East China', 'Taiwan']
const parents = { Asia: 'World', China: 'Asia', 'East China': 'China' }
const indent = (depth: number) => '  '.repeat(depth)
beforeEach(() => setLocale('zh-CN'))

describe('RegionSelect', () => {
  it('indents the list under each territory and shows the chosen name without the indent while the list is closed', async () => {
    const wrapper = mount(RegionSelect, { props: { modelValue: 'East China', regions, parents, allLabel: '全部区域' } })
    const texts = () => wrapper.findAll('option').map(option => option.element.textContent)
    const select = wrapper.get('select')
    expect(select.attributes('aria-label')).toBe('Region')
    expect(select.element.value).toBe('East China')
    // Closed: the control shows the chosen option, so that one carries no indent.
    expect(texts()).toEqual(['全部区域', '全球', `${indent(1)}亚洲`, `${indent(2)}中国`, '华东', 'Taiwan'])

    // The list is about to open, by mouse or by keyboard: every name sits under its territory.
    await select.trigger('mousedown')
    expect(texts()[4]).toBe(`${indent(3)}华东`)
    await select.trigger('blur')
    expect(texts()[4]).toBe('华东')
    // Only a key that opens the list does the same; any other key leaves the closed control as it is.
    for (const key of ['Shift', 'ArrowDown', 'a', 'Tab']) {
      await select.trigger('keydown', { key })
      expect(texts()[4], key).toBe('华东')
    }
    for (const init of [{ key: ' ' }, { key: 'F4' }, { key: 'ArrowDown', altKey: true }, { key: 'ArrowUp', altKey: true }]) {
      await select.trigger('keydown', init)
      expect(texts()[4], init.key).toBe(`${indent(3)}华东`)
      // Escape closes the list without a change.
      await select.trigger('keydown', { key: 'Escape' })
      expect(texts()[4], init.key).toBe('华东')
    }
    await select.trigger('keydown', { key: ' ' })

    // Choosing closes the list: the new choice is shown plain, the old one is indented again.
    await select.setValue('China')
    expect(wrapper.emitted('update:modelValue')).toEqual([['China']])
    await wrapper.setProps({ modelValue: 'China' })
    expect(texts()).toEqual(['全部区域', '全球', `${indent(1)}亚洲`, '中国', `${indent(3)}华东`, 'Taiwan'])
  })

  it('stays flat without a tree and can be disabled', () => {
    const wrapper = mount(RegionSelect, { props: { modelValue: '', regions: ['East China', 'Taiwan'], disabled: true, allLabel: '区域待迁移' } })
    expect(wrapper.findAll('option').map(option => option.element.textContent)).toEqual(['区域待迁移', '华东', 'Taiwan'])
    expect(wrapper.get('select').attributes('disabled')).toBeDefined()
  })
})
