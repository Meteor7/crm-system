import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import VisitModal from './VisitModal.vue'
import { accounts } from '@/api/mock-data'
import { createMockApi } from '@/api/mock-adapter'
import { setLocale } from '@/i18n'

describe('VisitModal business dates', () => {
  afterEach(() => {
    vi.useRealTimers()
    setLocale('zh-CN')
  })

  it('preserves the visit draft and linked records across language changes', async () => {
    const contacts = (await createMockApi({ latency: 0 }).listContacts({ pageSize: 100 })).data.items
    const contact = contacts.find(item => item.status === 'Active')!
    const wrapper = mount(VisitModal, { props: {
      mode: 'create', accounts, contacts, initialAccountId: contact.accountId,
      initialPrimaryContactId: contact.id, initialOpportunityId: 'CRM-OPP-00201',
    } })
    await wrapper.get('[aria-label="拜访主题"]').setValue('Customer process review')
    await wrapper.get('[aria-label="拜访目标"]').setValue('Confirm custom acceptance requirements')
    await wrapper.get('[aria-label="拜访日期"]').setValue('2026-10-12')
    await wrapper.get('[aria-label="拜访方式"]').setValue('Video')
    await wrapper.get('form').trigger('submit')
    const original = wrapper.emitted('submit')![0][0]

    setLocale('en-US')
    await nextTick()
    expect(wrapper.text()).toContain('New customer visit')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')![1][0]).toEqual(original)
    expect(wrapper.emitted('submit')![1][0]).toMatchObject({
      accountId: contact.accountId, primaryContactId: contact.id, opportunityId: 'CRM-OPP-00201',
      subject: 'Customer process review', objective: 'Confirm custom acceptance requirements', date: '2026-10-12', type: 'Video',
    })

    setLocale('zh-CN')
    await nextTick()
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')![2][0]).toEqual(original)
    wrapper.unmount()
  })

  it('defaults a new Visit to the current Shanghai date', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-02T16:30:00.000Z'))

    const wrapper = mount(VisitModal, {
      props: { mode: 'create', accounts },
    })

    expect((wrapper.get('[aria-label="拜访日期"]').element as HTMLInputElement).value).toBe('2026-08-03')
  })

  it('keeps Manager review free of separate Action fields', async () => {
    const wrapper = mount(VisitModal, {
      props: { mode: 'review', accounts, visit: null },
    })

    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toHaveLength(1)
    expect(wrapper.find('[aria-label="行动负责人"]').exists()).toBe(false)
  })

  it('prefills the edit form from the Visit and emits only the editable basic fields', async () => {
    const visit = {
      id: 'V-100', accountId: accounts[0].id, accountName: accounts[0].name, segment: accounts[0].segment,
      subject: '原定拜访', date: '2026-07-21', type: 'Video' as const, status: 'Planned' as const, owner: 'person002@crm.example.invalid',
      objective: '确认样片', outcome: '', nextAction: '', actionOwner: '', due: '', actionDone: false, modified: '2026-07-20 10:00:00.000000',
    }
    const wrapper = mount(VisitModal, { props: { mode: 'edit', accounts: [], visit } })

    expect(wrapper.text()).toContain('编辑拜访')
    expect(wrapper.find('[aria-label="拜访客户"]').exists()).toBe(false)
    expect(wrapper.find('input[type="file"]').exists()).toBe(false)
    expect((wrapper.get('[aria-label="拜访主题"]').element as HTMLInputElement).value).toBe('原定拜访')
    expect((wrapper.get('[aria-label="拜访日期"]').element as HTMLInputElement).value).toBe('2026-07-21')

    await wrapper.get('[aria-label="拜访日期"]').setValue('2026-07-28')
    await wrapper.get('[aria-label="拜访方式"]').setValue('On-site')
    await wrapper.get('[aria-label="拜访目标"]').setValue('确认样片与参会人')
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('submit')![0]).toEqual([
      { subject: '原定拜访', date: '2026-07-28', type: 'On-site', owner: 'person002@crm.example.invalid', objective: '确认样片与参会人' },
    ])
  })

  it('retains the Opportunity supplied by the cross-module create route', async () => {
    const wrapper = mount(VisitModal, {
      props: { mode: 'create', accounts, initialOpportunityId: 'CRM-OPP-00201' },
    })

    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ opportunityId: 'CRM-OPP-00201' })
  })

  it('requests quick Contact creation for the selected account', async () => {
    const wrapper = mount(VisitModal, { props: { mode: 'create', accounts } })

    await wrapper.get('[data-testid="create-contact"]').trigger('click')

    expect(wrapper.emitted('create-contact')?.[0]).toEqual([accounts[0].id])
  })

  it('renders the create form in English without translating business data', () => {
    setLocale('en-US')
    const wrapper = mount(VisitModal, { props: { mode: 'create', accounts } })

    expect(wrapper.text()).toContain('New customer visit')
    expect(wrapper.text()).toContain('Primary contact')
    expect(wrapper.text()).toContain('Visit minutes file (optional)')
    expect(wrapper.text()).toContain('Save and continue')
    expect(wrapper.text()).not.toContain('主要联系人')
    expect(wrapper.text()).toContain(accounts[0].name)
  })
})
