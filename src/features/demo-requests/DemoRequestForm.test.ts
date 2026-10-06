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
  it('guides account selection before Opportunity filtering and shows Company Name before Primary Contact', () => {
    const modal = mount(DemoRequestModal, {
      props: { mode: 'create', accounts, opportunities },
    })
    expect(modal.get('[aria-label="搜索 Opportunity"]').attributes('placeholder')).toBe('请先选择下方客户公司名筛选 Opportunities 或自测')
    expect(modal.get('[aria-label="关联 Opportunity"] option[value=""]').text()).toBe('请先选择下方客户公司名筛选 Opportunities 或自测')

    const form = mount(DemoRequestForm, {
      props: {
        modelValue: createEmptyDemoRequestFormData(),
        accountId: '',
        accounts,
      },
    })
    const customerFields = form.get('[data-customer-information] .field-grid').element.children
    expect(customerFields[0]?.hasAttribute('data-customer-company')).toBe(true)
    expect(customerFields[1]?.hasAttribute('data-customer-primary-contact')).toBe(true)
  })

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

  it('does not send a wafer row left empty, as it does not count it', async () => {
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
    const before = wrapper.findAll('[data-wafer-row]').length

    await wrapper.get('[data-add-wafer]').trigger('click')
    expect(wrapper.findAll('[data-wafer-row]')).toHaveLength(before + 1)
    await wrapper.get('.modal-card form').trigger('submit')

    const submission = wrapper.emitted('submit')?.[0]?.[0] as { formData: { wafers: unknown[] } }
    expect(submission.formData.wafers).toHaveLength(before)
    expect(wrapper.find('[data-field-error="wafers"]').exists()).toBe(false)
  })

  it('shows the refusal of a save in the dialog and flags the fields it names', () => {
    const wrapper = mount(DemoRequestModal, {
      props: {
        mode: 'edit',
        request: { ...demoRequests[0], salesOwner: 'person002@crm.example.invalid', engineerOwner: 'person077@crm.example.invalid', customerExpectedDate: '2026-09-08' },
        accounts,
        error: 'Demo Request form is incomplete.',
        requestId: 'req_demo_refused',
        fieldErrors: { 'wafers.0.slotId': 'Required', sizeShape: 'Required', timing: 'formData.timing must use YYYY-MM-DD.' },
      },
    })

    expect(wrapper.get('[data-modal-error]').text()).toContain('Demo Request form is incomplete.')
    expect(wrapper.get('[data-modal-error]').text()).toContain('req_demo_refused')
    expect(wrapper.get('[data-field-error="wafers.0.slotId"]').text()).toBe('请填写此项')
    expect(wrapper.get('[data-field-error="sizeShape"]').text()).toBe('请填写此项')
    expect(wrapper.get('[data-field-error="timing"]').text()).toBe('formData.timing must use YYYY-MM-DD.')
  })

  it('flags the server\'s wafer errors on the rows it sent, not on an empty row left before them', async () => {
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
    // The second row holds the data (the first row's cells are cleared): the first is not sent, the second is `wafers.0`.
    await wrapper.get('[data-add-wafer]').trigger('click')
    const fields = ['slotId', 'wid', 'waferSpecificity', 'notchFlat', 'doiMetrologyItems', 'resultFileProvided']
    for (const field of fields) {
      await wrapper.get(`[name="wafer-1-${field}"]`).setValue((wrapper.get(`[name="wafer-0-${field}"]`).element as HTMLInputElement).value || 'x')
      await wrapper.get(`[name="wafer-0-${field}"]`).setValue('')
    }
    await wrapper.get('.modal-card form').trigger('submit')
    expect(wrapper.findAll('[data-field-error]').map((item) => `${item.attributes('data-field-error')}: ${item.text()}`)).toEqual([])
    const submission = wrapper.emitted('submit')?.[0]?.[0] as { formData: { wafers: unknown[] } }
    expect(submission.formData.wafers).toHaveLength(1)

    await wrapper.setProps({ error: 'Demo Request form is incomplete.', fieldErrors: { 'wafers.0.slotId': 'Required' } })
    expect(wrapper.find('[data-field-error="wafers.0.slotId"]').exists()).toBe(false)
    expect(wrapper.get('[data-field-error="wafers.1.slotId"]').text()).toBe('请填写此项')
    // The server's hint follows the language, as the editor's own do.
    setLocale('en-US')
    await flushPromises()
    expect(wrapper.get('[data-field-error="wafers.1.slotId"]').text()).toBe('Enter this field')
    setLocale('zh-CN')
    await flushPromises()
    expect(wrapper.get('[data-field-error="wafers.1.slotId"]').text()).toBe('请填写此项')

    // The empty first row removed after the refusal: the hint follows its row up; a row added afterwards gets none,
    // and a language change keeps it so.
    await wrapper.get('[data-remove-wafer="0"]').trigger('click')
    expect(wrapper.find('[data-field-error="wafers.1.slotId"]').exists()).toBe(false)
    expect(wrapper.get('[data-field-error="wafers.0.slotId"]').text()).toBe('请填写此项')
    await wrapper.get('[data-add-wafer]').trigger('click')
    expect(wrapper.find('[data-field-error="wafers.1.slotId"]').exists()).toBe(false)
    setLocale('en-US')
    await flushPromises()
    expect(wrapper.get('[data-field-error="wafers.0.slotId"]').text()).toBe('Enter this field')
    expect(wrapper.find('[data-field-error="wafers.1.slotId"]').exists()).toBe(false)
    setLocale('zh-CN')
    await flushPromises()
    // The flagged row itself removed: its hint goes with it.
    await wrapper.get('[data-remove-wafer="0"]').trigger('click')
    expect(wrapper.findAll('[data-field-error]')).toHaveLength(0)
    setLocale('en-US')
    await flushPromises()
    expect(wrapper.findAll('[data-field-error]')).toHaveLength(0)
    setLocale('zh-CN')
  })

  it('keeps the wafer rows in their places while a save is out', async () => {
    const wrapper = mount(DemoRequestModal, {
      props: { mode: 'edit', request: { ...demoRequests[0], salesOwner: 'person002@crm.example.invalid', engineerOwner: 'person077@crm.example.invalid', customerExpectedDate: '2026-09-08' }, accounts, busy: true },
    })
    await wrapper.get('[data-add-wafer]').trigger('click')
    expect(wrapper.get('[data-add-wafer]').attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('[data-wafer-row]')).toHaveLength(demoRequests[0].formData?.wafers.length ?? 1)
    await wrapper.setProps({ busy: false })
    expect(wrapper.get('[data-add-wafer]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[data-add-wafer]').trigger('click')
    expect(wrapper.get('[data-remove-wafer="1"]').attributes('disabled')).toBeUndefined()
    await wrapper.setProps({ busy: true })
    expect(wrapper.get('[data-remove-wafer="1"]').attributes('disabled')).toBeDefined()
  })

  it('holds the save while a form is being read, and does not apply a form read while a save is out', async () => {
    const baseApi = createMockApi({ latency: 0 })
    const held: { resolve: (value: unknown) => void } = { resolve: () => undefined }
    const importDemoRequestForm = vi.fn().mockImplementation(() => new Promise((resolve) => { held.resolve = resolve }))
    const contacts = (await baseApi.listContacts({ accountId: accounts[0].id })).data.items
    const wrapper = mount(DemoRequestModal, {
      props: { mode: 'create', accounts, contacts, currentSalesContact: 'person002@crm.example.invalid', apiClient: { ...baseApi, importDemoRequestForm } },
    })
    const input = wrapper.get('[data-import-demo-request-input]')
    Object.defineProperty(input.element, 'files', { value: [new File(['pdf'], 'completed-drf.pdf', { type: 'application/pdf' })] })
    await input.trigger('change')
    expect(importDemoRequestForm).toHaveBeenCalledOnce()
    // Being read: the save waits for it (the rows it would count are about to change).
    expect(wrapper.get('[data-modal-submit]').attributes('disabled')).toBeDefined()

    // A save out all the same (the page's doing) when the form arrives: the form is not applied, and says so.
    await wrapper.setProps({ busy: true })
    held.resolve({ data: { fileName: 'completed-drf.pdf', companyName: accounts[0].name, formData: { ...createEmptyDemoRequestFormData('person002@crm.example.invalid'), primaryTool: 'Aconca FS Edge' }, detectedFields: ['primaryTool'] } })
    await flushPromises()
    expect((wrapper.get('[name="primaryTool"]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.find('[data-demo-request-import-success]').exists()).toBe(false)
    expect(wrapper.get('[data-demo-request-import-error]').text()).toContain('识别结果未应用')
    await wrapper.setProps({ busy: false })
    expect(wrapper.get('[data-modal-submit]').attributes('disabled')).toBeUndefined()
  })

  it('translates only the errors in force when the language changes', async () => {
    const wrapper = mount(DemoRequestModal, {
      props: {
        mode: 'edit',
        request: {
          ...demoRequests[0], salesOwner: 'person002@crm.example.invalid', engineerOwner: 'person077@crm.example.invalid', customerExpectedDate: '2026-09-08',
          formData: demoRequests[0].formData ? { ...demoRequests[0].formData, salesContact: 'person002@crm.example.invalid', demoOwner: 'person077@crm.example.invalid' } : undefined,
        },
        accounts,
      },
    })
    await wrapper.setProps({ error: 'Demo Request form is incomplete.', fieldErrors: { 'wafers.0.slotId': 'Required' } })
    expect(wrapper.get('[data-field-error="wafers.0.slotId"]').text()).toBe('请填写此项')
    // The next submit checks the draft anew: its own errors replace the server's, and a language change keeps it so.
    await wrapper.get('input[type="date"][aria-label="客户期望时间"]').setValue('')
    await wrapper.get('.modal-card form').trigger('submit')
    expect(wrapper.findAll('[data-field-error]').map((item) => item.attributes('data-field-error'))).toEqual(['customerExpectedDate'])
    setLocale('en-US')
    await flushPromises()
    expect(wrapper.findAll('[data-field-error]').map((item) => item.attributes('data-field-error'))).toEqual(['customerExpectedDate'])
    expect(wrapper.get('[data-field-error="customerExpectedDate"]').text()).toBe('Enter the customer expected date')
    setLocale('zh-CN')
    await flushPromises()
    expect(wrapper.find('[data-field-error="wafers.0.slotId"]').exists()).toBe(false)
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
    expect(wrapper.findAll('select')).toHaveLength(2)
    const ownerSelect = wrapper.get('[aria-label="工程负责人"]')
    expect(ownerSelect.attributes('disabled')).toBeDefined()
    expect((ownerSelect.element as HTMLSelectElement).value).toBe(request.engineerOwner)

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
