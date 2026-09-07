import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { accounts, demoRequests } from '@/api/mock-data'
import { createMockApi } from '@/api/mock-adapter'
import { createEmptyDemoRequestFormData } from '@/domain/demo-request-form'
import { setLocale } from '@/i18n'
import { opportunities } from '@/demo/operations-data'
import DemoRequestForm from './DemoRequestForm.vue'
import DemoRequestModal from './DemoRequestModal.vue'

describe('DemoRequestForm', () => {
  it('imports a completed PDF and fills the editable DRF without submitting it', async () => {
    const baseApi = createMockApi({ latency: 0 })
    const importedForm = createEmptyDemoRequestFormData()
    Object.assign(importedForm, {
      contactPerson: 'Ada Liu, ada@example.com',
      industry: 'Frontend Fab',
      primaryTool: 'Aconca FS Edge',
      timing: '2026-09-15',
    })
    const importDemoRequestForm = vi.fn().mockResolvedValue({
      data: {
        fileName: 'completed-drf.pdf', companyName: accounts[0].name, formData: importedForm,
        detectedFields: ['companyName', 'contactPerson', 'industry', 'primaryTool', 'timing'],
      },
    })
    const contacts = (await baseApi.listContacts({ accountId: accounts[0].id })).data.items
    const wrapper = mount(DemoRequestModal, {
      props: {
        mode: 'create', accounts, contacts, currentSalesContact: 'person002@crm.example.invalid',
        apiClient: { ...baseApi, importDemoRequestForm },
      },
    })
    const input = wrapper.get('[data-import-demo-request-input]')
    const file = new File(['pdf'], 'completed-drf.pdf', { type: 'application/pdf' })
    Object.defineProperty(input.element, 'files', { value: [file] })

    await input.trigger('change')
    await flushPromises()

    expect(importDemoRequestForm).toHaveBeenCalledOnce()
    expect((wrapper.get('[name="primaryTool"]').element as HTMLInputElement).value).toBe('Aconca FS Edge')
    expect((wrapper.get('[name="timing"]').element as HTMLInputElement).value).toBe('2026-09-15')
    expect(wrapper.get('[data-demo-request-import-success]').text()).toContain('5')
    expect(wrapper.emitted('submit')).toBeUndefined()
  })

  it('hides Customer Information for Self Test while imported customer fields remain parsed', async () => {
    const baseApi = createMockApi({ latency: 0 })
    const importedForm = createEmptyDemoRequestFormData()
    Object.assign(importedForm, {
      contactPerson: 'Ada Liu, ada@example.com',
      industry: 'Frontend Fab',
      primaryTool: 'Aconca FS Edge',
    })
    const importDemoRequestForm = vi.fn().mockResolvedValue({
      data: {
        fileName: 'self-test-drf.pdf', companyName: accounts[0].name, formData: importedForm,
        detectedFields: ['companyName', 'contactPerson', 'industry', 'primaryTool'],
      },
    })
    const contacts = (await baseApi.listContacts({ accountId: accounts[0].id })).data.items
    const wrapper = mount(DemoRequestModal, {
      props: {
        mode: 'create', accounts, contacts, opportunities,
        currentSalesContact: 'person002@crm.example.invalid',
        apiClient: { ...baseApi, importDemoRequestForm },
      },
    })

    await wrapper.get('[aria-label="关联 Opportunity"]').setValue('__SELF_TEST__')
    expect(wrapper.find('[data-customer-information]').exists()).toBe(false)

    const input = wrapper.get('[data-import-demo-request-input]')
    const file = new File(['pdf'], 'self-test-drf.pdf', { type: 'application/pdf' })
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await flushPromises()

    expect(importDemoRequestForm).toHaveBeenCalledOnce()
    expect(wrapper.find('[data-customer-information]').exists()).toBe(false)
    expect((wrapper.get('[name="primaryTool"]').element as HTMLInputElement).value).toBe('Aconca FS Edge')
    expect(wrapper.get('[data-demo-request-import-success]').text()).toContain('4')
  })

  it('does not validate hidden customer fields for Self Test', async () => {
    const wrapper = mount(DemoRequestModal, {
      props: {
        mode: 'create', accounts, opportunities,
        currentSalesContact: 'person002@crm.example.invalid',
      },
    })

    await wrapper.get('[aria-label="关联 Opportunity"]').setValue('__SELF_TEST__')
    await wrapper.get('.modal-card form').trigger('submit')

    expect(wrapper.find('[data-customer-information]').exists()).toBe(false)
    expect(wrapper.find('[data-field-error="primaryContactId"]').exists()).toBe(false)
    expect(wrapper.find('[data-field-error="industry"]').exists()).toBe(false)
    expect(wrapper.emitted('submit')).toBeUndefined()
  })

  it('shows approved example guidance and uses a date picker for Timing', async () => {
    const wrapper = mount(DemoRequestForm, {
      props: {
        modelValue: createEmptyDemoRequestFormData('person002@crm.example.invalid'),
        accountId: 'ACC-001',
        accounts,
        errors: {},
      },
    })

    const exampleFields = [
      'industry', 'sizeShape', 'material', 'specificRequest', 'detectMeasure', 'expectedResults',
      'otherTools', 'primaryTool', 'complementaryTool', 'keySuccessFactors', 'internalQuestions',
      'customerQuestions', 'wafer-0-slotId', 'wafer-0-wid', 'wafer-0-waferSpecificity',
      'wafer-0-notchFlat', 'wafer-0-doiMetrologyItems', 'wafer-0-resultFileProvided',
    ]

    exampleFields.forEach((name) => {
      expect(wrapper.get(`[name="${name}"]`).attributes('placeholder')).toMatch(/^e\.g\. /)
    })
    expect(wrapper.get('[name="industry"]').attributes('placeholder')).toBe('e.g. Semiconductor Frontend Fab')
    expect(wrapper.get('[name="primaryTool"]').attributes('placeholder')).toBe('e.g. Aconca FS Edge')
    expect(wrapper.get('[name="complementaryTool"]').attributes('placeholder')).toBe('e.g. Nansi')
    expect(wrapper.get('[name="timing"]').attributes('type')).toBe('date')
    expect(wrapper.get('[name="timing"]').attributes('placeholder')).toBeUndefined()
    expect(wrapper.get('[data-wafer-count]').text()).toBe('0')

    await wrapper.get('[name="timing"]').setValue('2026-08-20')
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual(expect.objectContaining({ timing: '2026-08-20' }))

    await wrapper.get('[name="wafer-0-slotId"]').setValue('1')
    expect(wrapper.get('[data-wafer-count]').text()).toBe('1')
  })

  it('adds and removes wafer detail rows while retaining at least one row', async () => {
    const wrapper = mount(DemoRequestForm, {
      props: {
        modelValue: createEmptyDemoRequestFormData('person002@crm.example.invalid'),
        accountId: 'ACC-001',
        accounts,
        errors: {},
      },
    })

    await wrapper.get('[data-add-wafer]').trigger('click')
    expect(wrapper.findAll('[data-wafer-row]')).toHaveLength(2)
    await wrapper.get('[data-remove-wafer="1"]').trigger('click')
    expect(wrapper.findAll('[data-wafer-row]')).toHaveLength(1)
    expect(wrapper.find('[data-remove-wafer="0"]').exists()).toBe(false)
  })

  it('uses fixed dropdown choices for the unique Sales and Engineer owners', () => {
    const wrapper = mount(DemoRequestForm, {
      props: {
        modelValue: createEmptyDemoRequestFormData('person002@crm.example.invalid'),
        accountId: 'ACC-001',
        accounts,
        errors: {},
      },
    })

    const optionValues = (name: string) => wrapper.get(`select[name="${name}"]`)
      .findAll('option')
      .map((option) => option.attributes('value'))

    expect(optionValues('salesContact')).toEqual(['', 'person002@crm.example.invalid', 'person005@crm.example.invalid'])
    expect(optionValues('demoOwner')).toEqual(['', 'person077@crm.example.invalid', 'person053@crm.example.invalid'])
    expect(wrapper.find('input[name="salesContact"]').exists()).toBe(false)
    expect(wrapper.find('input[name="demoOwner"]').exists()).toBe(false)
  })

  it('blocks an empty Demo Request submission and shows field errors', async () => {
    const wrapper = mount(DemoRequestModal, {
      props: {
        mode: 'create',
        accounts,
        opportunities,
        currentSalesContact: 'person002@crm.example.invalid',
      },
    })

    await wrapper.get('.modal-card form').trigger('submit')

    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.find('[data-field-error="primaryContactId"]').exists()).toBe(true)
    expect(wrapper.find('[data-field-error="opportunityId"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="关联 Opportunity"]').exists()).toBe(true)
    expect(wrapper.find('[data-field-error="complementaryTool"]').exists()).toBe(false)
  })

  it('updates submitted validation errors on locale change without resetting the form draft', async () => {
    setLocale('zh-CN')
    const wrapper = mount(DemoRequestModal, {
      props: { mode: 'create', accounts, opportunities, currentSalesContact: 'person002@crm.example.invalid' },
    })

    await wrapper.get('[name="primaryTool"]').setValue('Aconca FS Edge')
    await wrapper.get('.modal-card form').trigger('submit')
    expect(wrapper.get('[data-field-error="industry"]').text()).toContain('请填写')

    await wrapper.get('[name="industry"]').setValue('Frontend Fab')
    setLocale('en-US')
    await flushPromises()
    expect(wrapper.get('[data-field-error="industry"]').text()).toBe('Enter Industry')
    expect((wrapper.get('[name="industry"]').element as HTMLInputElement).value).toBe('Frontend Fab')
    expect((wrapper.get('[name="primaryTool"]').element as HTMLInputElement).value).toBe('Aconca FS Edge')

    await wrapper.get('.modal-card form').trigger('submit')
    expect(wrapper.find('[data-field-error="industry"]').exists()).toBe(false)

    setLocale('zh-CN')
    wrapper.unmount()
  })

  it('submits customer expected date without materializing a system Q&A assignment', async () => {
    const wrapper = mount(DemoRequestModal, {
      props: {
        mode: 'edit',
        request: {
          ...demoRequests[0],
          salesOwner: 'person002@crm.example.invalid',
          engineerOwner: 'person077@crm.example.invalid',
          customerExpectedDate: '2026-09-08',
          formData: demoRequests[0].formData
            ? { ...demoRequests[0].formData, salesContact: 'person002@crm.example.invalid', demoOwner: 'person077@crm.example.invalid' }
            : undefined,
        },
        accounts,
      },
    })

    expect(wrapper.get('[aria-label="客户期望时间"]').element).toBeInstanceOf(HTMLInputElement)
    expect(wrapper.find('[aria-label="Q&A 分配"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('客户给内部团队的问题')

    await wrapper.get('[aria-label="客户期望时间"]').setValue('2026-09-15')
    await wrapper.get('.modal-card form').trigger('submit')

    const submission = wrapper.emitted('submit')?.[0]?.[0]
    expect(submission).toEqual(expect.objectContaining({
      customerExpectedDate: '2026-09-15',
      formData: expect.not.objectContaining({ customerExpectedDate: expect.anything() }),
    }))
    expect(submission).not.toHaveProperty('questionAssignment')
  })

  it('keeps the linked Opportunity visible when editing a progressed Request', async () => {
    const apiClient = createMockApi({ latency: 0 })
    const linked = (await apiClient.getStrategyOpportunity('OPP-001')).data
    apiClient.listStrategyOpportunities = vi.fn().mockResolvedValue({
      data: { items: [] }, meta: { requestId: 'req_no_eligible', page: 1, pageSize: 20, total: 0 }, warnings: [],
    })
    apiClient.getStrategyOpportunity = vi.fn().mockResolvedValue({
      data: linked, meta: { requestId: 'req_linked_opportunity' }, warnings: [],
    })
    const wrapper = mount(DemoRequestModal, {
      props: { mode: 'edit', request: { ...demoRequests[0], opportunityId: linked.id }, accounts, apiClient },
    })
    await flushPromises()

    const select = wrapper.get('[aria-label="关联 Opportunity"]')
    expect((select.element as HTMLSelectElement).value).toBe(linked.id)
    expect(select.text()).toContain(linked.title)
    expect(apiClient.getStrategyOpportunity).toHaveBeenCalledWith(linked.id)
  })

  it('does not allow an Engineer to reassign the review owner', async () => {
    const request = { ...demoRequests[0], engineerOwner: 'assigned.engineer@example.invalid' }
    const wrapper = mount(DemoRequestModal, { props: { mode: 'engineer', request } })

    expect(wrapper.text()).not.toContain('请选择 Engineer Owner')
    expect(wrapper.findAll('select')).toHaveLength(1)

    const textareas = wrapper.findAll('textarea')
    const inputs = wrapper.findAll('input')
    await textareas[0].setValue('Run the agreed test plan')
    await inputs[0].setValue('Inspection 3000')
    await inputs[1].setValue('Week 48')
    await inputs[2].setValue('2026-12-20')
    await inputs[3].setValue('Sample contamination')
    await textareas[1].setValue('Feasible')
    await wrapper.get('.modal-card form').trigger('submit')

    expect(wrapper.emitted('submit')?.[0]?.[0]).toEqual(expect.objectContaining({
      type: 'engineer_approve',
      engineerOwner: request.engineerOwner,
    }))
  })
})
