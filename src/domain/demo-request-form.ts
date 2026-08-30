import type { AccountSummaryDto, ContactSummaryDto, DemoRequestDto, DemoRequestFormData, DemoRequestImportResult, DemoWaferDetailDto } from '@/types/crm'
import { demoEngineerOwnerOptions, demoSalesOwnerOptions, isDemoEngineerOwner, isDemoSalesOwner } from '@/demo/identities'
import { PERSONNEL } from '@/demo/personnel'

export const DEMO_REQUEST_HINTS = {
  companyName: '请输入客户公司全称',
  contactPerson: 'Name, title, email, phone',
  industry: 'e.g. Semiconductor Frontend Fab',
  salesContact: 'Sales dept contact for this demo',
  demoOwner: 'R&D or Applications engineer responsible',
  waferCount: '根据下方 Wafer Details 自动计算',
  sizeShape: 'e.g. 300 mm round wafer, 775 um thickness, standard notch',
  material: 'e.g. Bare silicon wafer, Si(100)',
  specificRequest: 'e.g. Frontside inspection with 3 mm edge exclusion; non-contact handling required.',
  detectMeasure: 'e.g. Detect frontside particles, scratches and surface defects above 1 um.',
  expectedResults: 'e.g. Defect map, defect images, CSV data and PDF summary report.',
  otherTools: 'e.g. KLA Surfscan comparison; enter N/A when none',
  primaryTool: 'e.g. Aconca FS Edge',
  complementaryTool: 'e.g. Nansi',
  timing: '请选择日期',
  keySuccessFactors: 'e.g. Capture rate >= 95%, false positive rate <= 5%, complete defect map output.',
  internalQuestions: 'e.g. Confirm recipe preparation and machine availability.',
  customerQuestions: 'e.g. Confirm sample delivery date and required report format.',
  slotId: 'e.g. 1',
  wid: 'e.g. DEMO-ACONCA-001',
  waferSpecificity: 'e.g. 300 mm bare Si(100), 775 um thickness',
  notchFlat: "e.g. Standard notch, notch at 6 o'clock",
  doiMetrologyItems: 'e.g. Particles, scratches and surface defects above 1 um',
  resultFileProvided: 'e.g. Customer will provide reference defect map and KLARF baseline.',
} as const

export function createEmptyDemoWafer(): DemoWaferDetailDto {
  return { slotId: '', wid: '', waferSpecificity: '', notchFlat: '', doiMetrologyItems: '', resultFileProvided: '' }
}

export function createEmptyDemoRequestFormData(salesContact = ''): DemoRequestFormData {
  return {
    contactPerson: '',
    industry: '',
    salesContact,
    demoOwner: '',
    sizeShape: '',
    material: '',
    specificRequest: '',
    detectMeasure: '',
    expectedResults: '',
    otherTools: '',
    primaryTool: '',
    complementaryTool: '',
    timing: '',
    keySuccessFactors: '',
    internalQuestions: '',
    customerQuestions: '',
    wafers: [createEmptyDemoWafer()],
  }
}

export function cloneDemoRequestFormData(form: DemoRequestFormData): DemoRequestFormData {
  return { ...form, wafers: form.wafers.map((wafer) => ({ ...wafer })) }
}

function normalizedMatchValue(value: string) {
  return value.normalize('NFKC').toLocaleLowerCase().replace(/[^\p{L}\p{N}@+.]/gu, '')
}

function importedOwner(value: string, allowedIds: string[], fallback: string) {
  const target = normalizedMatchValue(value)
  if (!target) return fallback
  const match = PERSONNEL.find((person) => allowedIds.includes(person.id) && [
    person.id,
    person.name,
    person.id.split('@')[0] || '',
  ].some((candidate) => normalizedMatchValue(candidate) === target))
  return match?.id ?? fallback
}

function matchingContactId(contactPerson: string, accountId: string, contacts: ContactSummaryDto[]) {
  const source = normalizedMatchValue(contactPerson)
  if (!source || !accountId) return ''
  const contact = contacts.find((candidate) => candidate.accountId === accountId && candidate.status === 'Active' && [
    candidate.email || '',
    candidate.phone || '',
    candidate.name,
  ].some((value) => {
    const normalized = normalizedMatchValue(value)
    return normalized.length >= 3 && source.includes(normalized)
  }))
  return contact?.id ?? ''
}

export function applyDemoRequestImport(
  current: DemoRequestFormData,
  imported: DemoRequestImportResult,
  accounts: AccountSummaryDto[],
  contacts: ContactSummaryDto[],
) {
  const formData = cloneDemoRequestFormData(current)
  const scalarKeys: Array<keyof Omit<DemoRequestFormData, 'wafers' | 'salesContact' | 'demoOwner'>> = [
    'contactPerson', 'industry', 'sizeShape', 'material', 'specificRequest', 'detectMeasure',
    'expectedResults', 'otherTools', 'primaryTool', 'complementaryTool', 'timing',
    'keySuccessFactors', 'internalQuestions', 'customerQuestions',
  ]
  scalarKeys.forEach((key) => {
    const value = imported.formData[key]?.trim()
    if (value) formData[key] = value
  })
  formData.salesContact = importedOwner(imported.formData.salesContact, demoSalesOwnerOptions(), current.salesContact)
  formData.demoOwner = importedOwner(imported.formData.demoOwner, demoEngineerOwnerOptions(), current.demoOwner)
  if (imported.formData.wafers.some(hasWaferContent)) {
    formData.wafers = imported.formData.wafers.filter(hasWaferContent).map((wafer) => ({ ...wafer }))
  }

  const company = normalizedMatchValue(imported.companyName)
  const accountId = accounts.find((account) => [account.name, account.shortName]
    .some((value) => normalizedMatchValue(value) === company))?.id ?? ''
  const primaryContactId = matchingContactId(formData.contactPerson, accountId, contacts)
  const customerExpectedDate = /^\d{4}-\d{2}-\d{2}$/.test(formData.timing) ? formData.timing : ''
  return { formData, accountId, primaryContactId, customerExpectedDate }
}

function hasWaferContent(wafer: DemoWaferDetailDto) {
  return Object.values(wafer).some((value) => value.trim())
}

export function countDemoWafers(form: DemoRequestFormData) {
  return form.wafers.filter(hasWaferContent).length
}

export function validateDemoRequestFormData(
  form: DemoRequestFormData,
  options: { requireCustomerInformation?: boolean } = {},
) {
  const errors: Record<string, string> = {}
  const requireCustomerInformation = options.requireCustomerInformation ?? true
  const fields: Array<[keyof Omit<DemoRequestFormData, 'wafers' | 'complementaryTool'>, string]> = [
    ['salesContact', 'Sales Contact'],
    ['demoOwner', 'Demo Owner'],
    ['sizeShape', 'Size & Shape'],
    ['material', 'Material (Substrate)'],
    ['specificRequest', 'Specific Request'],
    ['detectMeasure', 'What to Detect / Measure'],
    ['expectedResults', 'Expected Results'],
    ['otherTools', 'Other Tools'],
    ['primaryTool', 'Primary Tool'],
    ['timing', 'Timing'],
    ['keySuccessFactors', 'Key Success Factors'],
    ['internalQuestions', 'Internal Questions'],
    ['customerQuestions', 'Questions for Customer'],
  ]
  if (requireCustomerInformation) fields.unshift(['industry', 'Industry'])
  fields.forEach(([key, label]) => {
    if (!form[key].trim()) errors[key] = `请填写 ${label}`
  })
  if (form.salesContact.trim() && !isDemoSalesOwner(form.salesContact.trim())) {
    errors.salesContact = '请选择有效的 Sales Owner'
  }
  if (form.demoOwner.trim() && !isDemoEngineerOwner(form.demoOwner.trim())) {
    errors.demoOwner = '请选择有效的 Engineer Owner'
  }
  const active = form.wafers.map((wafer, index) => ({ wafer, index })).filter(({ wafer }) => hasWaferContent(wafer))
  if (!active.length) errors.wafers = '请至少填写一条 Wafer Details'
  active.forEach(({ wafer, index }) => {
    const waferFields: Array<[keyof DemoWaferDetailDto, string]> = [
      ['slotId', 'Slot ID'],
      ['wid', 'WID'],
      ['waferSpecificity', 'Wafer Specificity'],
      ['notchFlat', 'Notch / Flat'],
      ['doiMetrologyItems', 'DOI / Metrology Items'],
      ['resultFileProvided', 'Result File Provided'],
    ]
    waferFields.forEach(([key, label]) => {
      if (!wafer[key].trim()) errors[`wafers.${index}.${key}`] = `请填写 ${label}`
    })
  })
  return errors
}

export function deriveDemoRequestSummary(accountName: string, form: DemoRequestFormData) {
  return {
    title: `${accountName} · ${form.primaryTool.trim()} Demo`,
    objective: form.detectMeasure.trim(),
    requestedEquipment: form.primaryTool.trim(),
    sampleType: form.material.trim(),
    sampleQuantity: countDemoWafers(form),
    targetDate: form.timing.trim(),
    priority: 'High' as const,
    acceptanceCriteria: form.keySuccessFactors.trim(),
  }
}

export function getDemoRequestFormData(request?: DemoRequestDto | null): DemoRequestFormData {
  if (!request) return createEmptyDemoRequestFormData()
  if (request.formData) return cloneDemoRequestFormData(request.formData)
  return {
    contactPerson: '',
    industry: request.segment,
    salesContact: request.salesOwner,
    demoOwner: request.engineerOwner || '',
    sizeShape: '',
    material: request.sampleType || '',
    specificRequest: request.objective,
    detectMeasure: request.objective,
    expectedResults: request.acceptanceCriteria,
    otherTools: '',
    primaryTool: request.requestedEquipment,
    complementaryTool: '',
    timing: request.targetDate,
    keySuccessFactors: request.acceptanceCriteria,
    internalQuestions: request.engineerComment || '',
    customerQuestions: '',
    wafers: [createEmptyDemoWafer()],
  }
}
