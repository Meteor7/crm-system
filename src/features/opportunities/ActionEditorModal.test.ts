import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { setLocale, useI18n } from '@/i18n'
import type { OpportunityActionDto } from '@/types/workspaces'
import ActionEditorModal from './ActionEditorModal.vue'

beforeEach(() => setLocale('zh-CN'))
afterEach(() => { vi.restoreAllMocks(); document.body.innerHTML = '' })

describe('Action Remark', () => {
  it('keeps blocked and rescheduled actions incomplete with their own due dates', async () => {
    setLocale('en-US')
    const wrapper = mount(ActionEditorModal, { props: { action: { id: 'a', title: 'Confirm', owner: 'sales-lin', due: '2026-10-08', status: 'Blocked' }, defaultOwner: 'sales-lin' } })
    const status = wrapper.get('select[aria-label="Status"]')
    expect(status.findAll('option').map(option => option.text())).toEqual(['Not started', 'In progress', 'Blocked', 'Rescheduled', 'Done'])
    await status.setValue('Rescheduled')
    await wrapper.get('input[type="date"]').setValue('2026-10-15')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ status: 'Rescheduled', due: '2026-10-15' })
    wrapper.unmount()
  })
  it('loads empty remarks for old records and emits multiline text on save', async () => {
    const wrapper = mount(ActionEditorModal, { props: { action: { id: 'a', title: 'Confirm', owner: 'sales-lin', due: '2026-09-21', status: 'Open' }, defaultOwner: 'sales-lin' } })
    expect(wrapper.get('textarea').element.value).toBe('')
    // Resolve the label through i18n so a copy change cannot silently unhook the test.
    await wrapper.get(`[aria-label="${useI18n().t('actionEditor.remark')}"]`).setValue('第一行\n第二行')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ remark: '第一行\n第二行', status: 'Open', title: 'Confirm' })
    wrapper.unmount()
  })

  it('keeps an existing remark when the editor is reopened and clears it on demand', async () => {
    const action: OpportunityActionDto = { id: 'a', title: 'Confirm', owner: 'sales-lin', due: '2026-09-21', status: 'Open', remark: '客户要求 9 月底前出样' }
    const wrapper = mount(ActionEditorModal, { props: { action, defaultOwner: 'sales-lin' } })
    const remark = wrapper.get(`[aria-label="${useI18n().t('actionEditor.remark')}"]`)
    expect((remark.element as HTMLTextAreaElement).value).toBe(action.remark)
    await remark.setValue('')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ remark: '' })
    wrapper.unmount()
  })
})
