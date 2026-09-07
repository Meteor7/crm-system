import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { setLocale } from '@/i18n'
import PersonnelSelect from './PersonnelSelect.vue'

describe('PersonnelSelect', () => {
  it('filters roles, displays names, and emits the selected stable id', async () => {
    const wrapper = mount(PersonnelSelect, { props: { modelValue: '', roles: ['Sales'], ariaLabel: 'owner' } })
    expect(wrapper.text()).toContain('Demo Staff 01')
    expect(wrapper.text()).toContain('Demo Staff 02')
    expect(wrapper.text()).not.toContain('\u6f14\u793a\u5458\u5de514')
    expect(wrapper.text()).not.toContain('\u6f14\u793a\u7ecf\u740601')
    expect(wrapper.text()).not.toContain('@crm.example.invalid')
    expect(wrapper.get('option[value=""]').text()).toBe('请选择负责人')
    setLocale('en-US')
    await flushPromises()
    expect(wrapper.get('option[value=""]').text()).toBe('Select assignee')
    expect(wrapper.get('option[value="person005@crm.example.invalid"]').text()).toContain('Sales')
    await wrapper.get('select').setValue('person005@crm.example.invalid')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['person005@crm.example.invalid'])
  })

  it('includes Boss for Manager and preserves an unknown legacy value', () => {
    const manager = mount(PersonnelSelect, { props: { modelValue: '', roles: ['Manager'], ariaLabel: 'approver' } })
    const legacy = mount(PersonnelSelect, { props: { modelValue: 'Legacy Owner', roles: ['Sales'], ariaLabel: 'owner' } })
    expect(manager.text()).toContain('\u6f14\u793a\u7ecf\u740601')
    expect(legacy.get('option[value="Legacy Owner"]').attributes('disabled')).toBeDefined()
  })
})
