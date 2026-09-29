import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it } from 'vitest'
import { createAppRouter } from '@/app/router'
import { createMockApi } from '@/api/mock-adapter'
import { accounts, bookings, contacts, demoRequests, evaluations, sites, visits } from '@/api/mock-data'
import { ROLE_PROFILES } from '@/domain/permissions'
import { useAppStore } from '@/stores/app'
import type { OpportunityActionDto, OpportunityStakeholderDto } from '@/types/workspaces'
import AccountsPage from '@/pages/AccountsPage.vue'
import ContactModal from '@/features/contacts/ContactModal.vue'
import DemoRequestModal from '@/features/demo-requests/DemoRequestModal.vue'
import TestRunModal from '@/features/evaluations/TestRunModal.vue'
import ActionEditorModal from '@/features/opportunities/ActionEditorModal.vue'
import BookingEditorModal from '@/features/opportunities/BookingEditorModal.vue'
import OpportunityEditorModal from '@/features/opportunities/OpportunityEditorModal.vue'
import StakeholderEditorModal from '@/features/opportunities/StakeholderEditorModal.vue'
import StakeholderModal from '@/features/stakeholders/StakeholderModal.vue'
import VisitModal from '@/features/visits/VisitModal.vue'

function expectNativeRequiredFieldsMarked(wrapper: VueWrapper, expected: number) {
  expect(wrapper.findAll(':required')).toHaveLength(expected)
  expect(wrapper.findAll('[data-required-mark]')).toHaveLength(expected)
}

function expectNoRequiredMarks(wrapper: VueWrapper) {
  expect(wrapper.findAll('[data-required-mark]')).toHaveLength(0)
}

describe('create form required markers', () => {
  it('marks every required field in the create-account form', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    useAppStore(pinia).bootstrap = {
      user: { id: 'admin', name: 'Admin', initials: 'AD', role: 'Manager', team: 'Test' },
      capabilities: ROLE_PROFILES['Manager'].capabilities,
      version: 'test',
    }
    const router = createAppRouter()
    await router.push('/accounts')
    await router.isReady()
    const wrapper = mount(AccountsPage, {
      props: { apiClient: createMockApi({ latency: 0 }) },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    await wrapper.get('[data-testid="new-account"]').trigger('click')

    expectNativeRequiredFieldsMarked(wrapper, 8)
  })

  it('marks required fields only in shared modal create modes', async () => {
    const opportunity = (await createMockApi({ latency: 0 }).listStrategyOpportunities()).data.items[0]
    const action: OpportunityActionDto = { id: 'ACT-1', title: 'Follow up', owner: 'person002@crm.example.invalid', due: '2026-08-01', status: 'Open' }
    const stakeholder: OpportunityStakeholderDto = {
      id: 'STK-1',
      contactId: 'CON-001',
      name: 'Contact',
      title: 'Manager',
      role: 'Influencer',
      influence: 'Medium',
      stance: 'Neutral',
      coverage: 'Weekly sync',
    }
    const contactProps = { accounts, sites: Object.entries(sites).flatMap(([accountId, rows]) => rows.map((site) => ({ ...site, accountId }))), contacts: [] }
    const cases = [
      {
        create: mount(ContactModal, { props: contactProps }),
        edit: mount(ContactModal, { props: { ...contactProps, contact: contacts[0] } }),
        count: 7,
      },
      {
        create: mount(StakeholderModal, { props: { accountId: accounts[0].id, contacts } }),
        edit: mount(StakeholderModal, { props: { accountId: accounts[0].id, contacts, contact: contacts[0] } }),
        count: 4,
      },
      {
        create: mount(VisitModal, { props: { mode: 'create', accounts } }),
        edit: mount(VisitModal, { props: { mode: 'review', accounts, visit: visits[0] } }),
        count: 6,
      },
      {
        create: mount(OpportunityEditorModal, { props: { accounts, sitesByAccount: sites, defaultOwner: 'Demo Staff 01' } }),
        edit: mount(OpportunityEditorModal, { props: { accounts, sitesByAccount: sites, defaultOwner: 'Demo Staff 01', opportunity } }),
        count: 12,
      },
      {
        create: mount(BookingEditorModal, { props: { accounts, opportunities: [], contacts: [], defaultOwner: 'Demo Staff 01' } }),
        edit: mount(BookingEditorModal, { props: { accounts, opportunities: [], contacts: [], defaultOwner: 'Demo Staff 01', booking: bookings[0] } }),
        count: 10,
      },
      {
        create: mount(ActionEditorModal, { props: { defaultOwner: 'Demo Staff 01' } }),
        edit: mount(ActionEditorModal, { props: { defaultOwner: 'Demo Staff 01', action } }),
        count: 4,
      },
      {
        create: mount(StakeholderEditorModal, { props: { accountId: accounts[0].id, contacts: [] } }),
        edit: mount(StakeholderEditorModal, { props: { accountId: accounts[0].id, contacts: [], stakeholder } }),
        count: 5,
      },
    ]

    cases.forEach(({ create, edit, count }) => {
      expect(create.findAll(':required')).toHaveLength(count)
      expect(create.findAll('[data-required-mark]')).toHaveLength(count)
      expectNoRequiredMarks(edit)
    })
  })

  it('marks all validation-required Demo Request fields only while creating', () => {
    const create = mount(DemoRequestModal, { props: { mode: 'create', accounts, currentSalesContact: 'person002@crm.example.invalid' } })
    const edit = mount(DemoRequestModal, { props: { mode: 'edit', accounts, request: demoRequests[0] } })
    const requiredNames = [
      'companyName',
      'industry',
      'salesContact',
      'demoOwner',
      'sizeShape',
      'material',
      'specificRequest',
      'detectMeasure',
      'expectedResults',
      'otherTools',
      'primaryTool',
      'timing',
      'keySuccessFactors',
      'internalQuestions',
      'customerQuestions',
      'wafer-0-slotId',
      'wafer-0-wid',
      'wafer-0-waferSpecificity',
      'wafer-0-notchFlat',
      'wafer-0-doiMetrologyItems',
      'wafer-0-resultFileProvided',
    ]

    requiredNames.forEach((name) => {
      expect(create.get(`[name="${name}"]`).element.closest('label')?.querySelector('[data-required-mark]')).not.toBeNull()
    })
    expect(create.get('.contact-picker').element.closest('label')?.querySelector('[data-required-mark]')).not.toBeNull()
    expect(create.get('[aria-label="客户期望时间"]').element.closest('label')?.querySelector('[data-required-mark]')).not.toBeNull()
    expect(create.findAll('[data-required-mark]')).toHaveLength(24)
    expect(create.get('[name="contactPerson"]').element.closest('label')?.querySelector('[data-required-mark]')).toBeNull()
    expect(create.get('[name="complementaryTool"]').element.closest('label')?.querySelector('[data-required-mark]')).toBeNull()
    expectNoRequiredMarks(edit)
  })

  it('marks the three user-entered Wafer Test Run fields and hides the server-owned ID', () => {
    const wrapper = mount(TestRunModal, { props: { evaluation: evaluations[0] } })

    expectNativeRequiredFieldsMarked(wrapper, 3)
    expect(wrapper.text()).not.toContain('Run 编号')
  })
})
