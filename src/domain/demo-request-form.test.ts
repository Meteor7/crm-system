import { describe, expect, it } from 'vitest'
import {
  applyDemoRequestImport,
  countDemoWafers,
  createEmptyDemoRequestFormData,
  deriveDemoRequestSummary,
  validateDemoRequestFormData,
} from './demo-request-form'
import type { AccountSummaryDto, ContactSummaryDto } from '@/types/crm'

describe('Demo Request Word form', () => {
  it('applies recognized imported fields while preserving unrecognized owners and matching account/contact', () => {
    const current = createEmptyDemoRequestFormData('person002@crm.example.invalid')
    current.demoOwner = 'person077@crm.example.invalid'
    current.internalQuestions = 'Keep this current note'
    const accounts = [{ id: 'ACC-1', name: 'Example Semiconductor Co.', shortName: 'Example Semi' }] as AccountSummaryDto[]
    const contacts = [{
      id: 'CON-1', accountId: 'ACC-1', name: 'Ada Liu', email: 'ada@example.com', phone: '+86 21 5555 0101', status: 'Active',
    }] as ContactSummaryDto[]

    const applied = applyDemoRequestImport(current, {
      fileName: 'completed-drf.docx',
      companyName: 'Example Semiconductor Co.',
      formData: {
        ...createEmptyDemoRequestFormData(),
        contactPerson: 'Ada Liu, Process Director, ada@example.com, +86 21 5555 0101',
        industry: 'Frontend Fab',
        salesContact: 'Demo Staff 01',
        demoOwner: 'Unknown Engineer',
        primaryTool: 'Aconca FS Edge',
        timing: '2026-09-15',
        internalQuestions: '',
        wafers: [{
          slotId: '1', wid: 'W-001', waferSpecificity: '300 mm Si', notchFlat: 'Notch up',
          doiMetrologyItems: 'Particles', resultFileProvided: 'Reference KLARF',
        }],
      },
      detectedFields: ['companyName', 'contactPerson', 'industry', 'salesContact', 'primaryTool', 'timing', 'wafers'],
    }, accounts, contacts)

    expect(applied.formData).toMatchObject({
      industry: 'Frontend Fab',
      primaryTool: 'Aconca FS Edge',
      salesContact: 'person002@crm.example.invalid',
      demoOwner: 'person077@crm.example.invalid',
      internalQuestions: 'Keep this current note',
    })
    expect(applied.formData.wafers).toHaveLength(1)
    expect(applied.accountId).toBe('ACC-1')
    expect(applied.primaryContactId).toBe('CON-1')
    expect(applied.customerExpectedDate).toBe('2026-09-15')
  })

  it('requires editable template fields except the generated Contact snapshot', () => {
    const form = createEmptyDemoRequestFormData()
    const errors = validateDemoRequestFormData(form)

    expect(errors).toMatchObject({
      industry: '请填写 Industry',
      salesContact: '请填写 Sales Contact',
      wafers: '请至少填写一条 Wafer Details',
    })
    expect(errors).not.toHaveProperty('complementaryTool')
    expect(errors).not.toHaveProperty('contactPerson')
  })

  it('formats UI validation messages for English without changing default validator output', () => {
    const form = createEmptyDemoRequestFormData()

    expect(validateDemoRequestFormData(form, { locale: 'en-US' })).toMatchObject({
      industry: 'Enter Industry',
      salesContact: 'Enter Sales Contact',
      wafers: 'Add at least one Wafer Details row',
    })
    expect(validateDemoRequestFormData(form).industry).toBe('请填写 Industry')
  })

  it('does not require Customer Information fields for Self Test', () => {
    const form = createEmptyDemoRequestFormData()
    const errors = validateDemoRequestFormData(form, { requireCustomerInformation: false })

    expect(errors).not.toHaveProperty('industry')
    expect(errors).not.toHaveProperty('contactPerson')
    expect(errors).toHaveProperty('salesContact')
    expect(errors).toHaveProperty('wafers')
  })

  it('counts partially filled wafer rows and requires all six wafer cells', () => {
    const form = createEmptyDemoRequestFormData()
    form.wafers[0].slotId = '1'

    expect(countDemoWafers(form)).toBe(1)
    expect(validateDemoRequestFormData(form)).toHaveProperty('wafers.0.wid')
  })

  it('derives legacy card fields from the Word form', () => {
    const form = createEmptyDemoRequestFormData('person002@crm.example.invalid')
    Object.assign(form, {
      contactPerson: 'Pat Lee, Process Manager, pat@example.com, +86 21 5555 1234',
      industry: 'Frontend Fab',
      demoOwner: 'FAE Team',
      sizeShape: '300 mm, 775 μm, notch',
      material: 'Silicon / Cu',
      specificRequest: 'No front-side contact',
      detectMeasure: 'TSV defect capture',
      expectedResults: 'KLARF and PDF',
      otherTools: 'Customer tool of record',
      primaryTool: 'AX-9000',
      timing: '2026-08-20',
      keySuccessFactors: 'Capture >= 96%',
      internalQuestions: 'Confirm recipe owner',
      customerQuestions: 'Confirm sample delivery',
    })
    form.wafers[0] = {
      slotId: '1',
      wid: 'W-001',
      waferSpecificity: '300 mm Si',
      notchFlat: 'Notch up',
      doiMetrologyItems: 'TSV residue',
      resultFileProvided: 'KLARF',
    }

    expect(deriveDemoRequestSummary('Example Fab', form)).toEqual({
      title: 'Example Fab · AX-9000 Demo',
      objective: 'TSV defect capture',
      requestedEquipment: 'AX-9000',
      sampleType: 'Silicon / Cu',
      sampleQuantity: 1,
      targetDate: '2026-08-20',
      priority: 'High',
      acceptanceCriteria: 'Capture >= 96%',
    })
  })

  it('rejects legacy and free-text Demo owners', () => {
    const legacyEngineer = createEmptyDemoRequestFormData('person002@crm.example.invalid')
    legacyEngineer.demoOwner = 'FAE Mia'
    const invalidSales = createEmptyDemoRequestFormData('Other Sales')
    invalidSales.demoOwner = '演示员工14'

    expect(validateDemoRequestFormData(legacyEngineer).demoOwner).toBe('请选择有效的 Engineer Owner')
    expect(validateDemoRequestFormData(invalidSales).salesContact).toBe('请选择有效的 Sales Owner')
  })
})
