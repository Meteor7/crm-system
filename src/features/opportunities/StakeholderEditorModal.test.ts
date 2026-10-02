import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { setLocale } from '@/i18n'
import type { OpportunityStakeholderDto } from '@/types/workspaces'
import StakeholderEditorModal from './StakeholderEditorModal.vue'

beforeEach(() => setLocale('zh-CN'))
afterEach(() => { vi.restoreAllMocks(); document.body.innerHTML = '' })

const props = { contacts: [], accountId: 'ACC-1' }
const existing: OpportunityStakeholderDto = {
  id: 'stakeholder-1', contactId: 'contact-1', name: 'Pat Buyer', title: 'Buyer',
  role: 'Economic Buyer', influence: 'High', stance: 'Support', coverage: 'Weekly', responseMode: 'Trouble',
}

describe('StakeholderEditorModal response mode', () => {
  it('submits the selected response mode', async () => {
    const wrapper = mount(StakeholderEditorModal, { props })
    await wrapper.get('[aria-label="反应模式"]').setValue('Growth')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ responseMode: 'Growth' })
    wrapper.unmount()
  })

  it('offers the four modes plus an unset choice and defaults to unset', () => {
    const wrapper = mount(StakeholderEditorModal, { props })
    const select = wrapper.get('[aria-label="反应模式"]')
    expect((select.element as HTMLSelectElement).value).toBe('')
    expect(select.findAll('option').map((option) => option.attributes('value'))).toEqual(['', 'Growth', 'Trouble', 'Even Keel', 'Overconfident'])
    wrapper.unmount()
  })

  it('loads the stored mode when editing and resends it with an unrelated edit', async () => {
    const wrapper = mount(StakeholderEditorModal, { props: { ...props, stakeholder: existing } })
    expect((wrapper.get('[aria-label="反应模式"]').element as HTMLSelectElement).value).toBe('Trouble')
    await wrapper.get('[aria-label="关键人覆盖证据"]').setValue('Monthly')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ responseMode: 'Trouble' })
    wrapper.unmount()
  })

  it('clears a stored mode back to unset on demand', async () => {
    const wrapper = mount(StakeholderEditorModal, { props: { ...props, stakeholder: existing } })
    await wrapper.get('[aria-label="反应模式"]').setValue('')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ responseMode: '' })
    wrapper.unmount()
  })
})
