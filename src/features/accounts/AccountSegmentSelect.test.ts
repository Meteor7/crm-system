import { mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { describe, expect, it } from 'vitest'
import AccountSegmentSelect from './AccountSegmentSelect.vue'

const CUSTOM_SEGMENT = '__custom_account_segment__'

describe('AccountSegmentSelect', () => {
  it('keeps the custom entry last and binds a required custom value', async () => {
    const Harness = defineComponent({
      components: { AccountSegmentSelect },
      setup() {
        return {
          segment: ref('Frontend'),
          segments: ['Frontend', 'Advanced Packaging'],
        }
      },
      template: `
        <AccountSegmentSelect
          v-model="segment"
          :segments="segments"
          label="客户业务领域"
          required
        />
        <output data-segment-value>{{ segment }}</output>
      `,
    })
    const wrapper = mount(Harness)
    const select = wrapper.get('select[aria-label="客户业务领域"]')

    expect(select.findAll('option').map((option) => option.text())).toEqual([
      'Frontend',
      'Advanced Packaging',
      '＋自定义领域',
    ])

    await select.setValue(CUSTOM_SEGMENT)
    const input = wrapper.get('input[aria-label="客户业务领域自定义"]')
    expect(input.attributes('required')).toBeDefined()
    for (const value of ['Front', 'Frontend', 'Frontend Equipment']) {
      await wrapper.get('input[aria-label="客户业务领域自定义"]').setValue(value)
      expect(wrapper.find('input[aria-label="客户业务领域自定义"]').exists()).toBe(true)
    }
    await input.setValue('Power Semiconductor')
    expect(wrapper.get('[data-segment-value]').text()).toBe('Power Semiconductor')

    await select.setValue('Frontend')
    expect(wrapper.find('input[aria-label="客户业务领域自定义"]').exists()).toBe(false)
    expect(wrapper.get('[data-segment-value]').text()).toBe('Frontend')
  })

  it('keeps a saved value that is not in the loaded options editable', () => {
    const wrapper = mount(AccountSegmentSelect, {
      props: {
        modelValue: 'Power Semiconductor',
        segments: ['Frontend', 'Advanced Packaging'],
        label: '客户业务领域',
      },
    })

    expect(wrapper.get('select').element.value).toBe(CUSTOM_SEGMENT)
    expect(wrapper.get('input').element.value).toBe('Power Semiconductor')
  })

  it('uses supplied copy for an empty selection and custom input', async () => {
    const wrapper = mount(AccountSegmentSelect, {
      props: {
        modelValue: '',
        segments: ['Aconca'],
        label: 'Equipment type',
        customOptionLabel: '+ Custom equipment type',
        customInputLabel: 'Equipment type',
        customPlaceholder: 'Enter a custom equipment type',
        emptyPlaceholder: 'Select equipment type',
        customOnEmpty: false,
      },
    })

    const select = wrapper.get('select[aria-label="Equipment type"]')
    expect((select.element as HTMLSelectElement).value).toBe('')
    expect(select.findAll('option').map((option) => option.text())).toEqual([
      'Select equipment type',
      'Aconca',
      '+ Custom equipment type',
    ])

    await select.setValue(CUSTOM_SEGMENT)
    const input = wrapper.get('input[aria-label="Equipment type"]')
    expect(input.attributes('placeholder')).toBe('Enter a custom equipment type')
  })
})
