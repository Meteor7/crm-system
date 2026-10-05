import { createPinia, type Pinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { accounts } from '@/api/mock-data'
import { createEmptyDemoRequestFormData } from '@/domain/demo-request-form'
import PersonnelSelect from '@/design-system/PersonnelSelect.vue'
import { preferredPersonnelId } from '@/demo/personnel'
import DemoRequestForm from '@/features/demo-requests/DemoRequestForm.vue'
import DemoRequestModal from '@/features/demo-requests/DemoRequestModal.vue'
import LeadEditorModal from '@/features/leads/LeadEditorModal.vue'
import VisitModal from '@/features/visits/VisitModal.vue'
import { useAppStore } from '@/stores/app'
import type { UserRole } from '@/types/crm'

// The second Sales user of the directory. A default that takes the first Sales user gives her a colleague.
const BELLA = 'person005@crm.example.invalid'

// The app as a signed-in user of one role sees it, or as one particular user of that role.
async function signedIn(role: UserRole, id = '') {
  const api = createMockApi({ latency: 0, role })
  const pinia: Pinia = createPinia()
  const bootstrap = (await api.getBootstrap()).data
  const user = id ? { ...bootstrap.user, id } : bootstrap.user
  useAppStore(pinia).bootstrap = { ...bootstrap, user }
  return { api, pinia, user }
}
// The people a select lets the user choose.
const people = (wrapper: ReturnType<typeof mount>) => wrapper.findAll('option:not([disabled])').filter((option) => option.attributes('value')).map((option) => option.attributes('value'))

describe('Owner fields', () => {
  it('offers a Sales user only themselves as the owner and fills an empty field with them', async () => {
    const { pinia, user } = await signedIn('Sales')
    const other = 'person005@crm.example.invalid'
    expect(user.id).not.toBe(other)
    // A new record: the field is empty, and becomes the user.
    const field = mount(PersonnelSelect, { props: { modelValue: '', roles: ['Sales', 'Manager'], ariaLabel: 'owner', owner: true, required: true }, global: { plugins: [pinia] } })
    expect(people(field)).toEqual([user.id])
    expect(field.emitted('update:modelValue')).toEqual([[user.id]])
    // A form that empties the field later gets the user again.
    await field.setProps({ modelValue: user.id })
    await field.setProps({ modelValue: '' })
    expect(field.emitted('update:modelValue')).toEqual([[user.id], [user.id]])

    // A record that already has another owner keeps that owner: it is shown, cannot be chosen, and is not
    // replaced on the user's behalf. Taking the record over is the user's own choice.
    const taken = mount(PersonnelSelect, { props: { modelValue: other, roles: ['Sales'], ariaLabel: 'owner', owner: true, required: true }, global: { plugins: [pinia] } })
    expect(taken.emitted('update:modelValue')).toBeUndefined()
    expect(taken.get<HTMLSelectElement>('select').element.value).toBe(other)
    expect(taken.get(`option[value="${other}"]`).attributes('disabled')).toBeDefined()
    expect(taken.findAll('option:not([disabled])').map((option) => option.attributes('value'))).toEqual([user.id])
    await taken.get('select').setValue(user.id)
    expect(taken.emitted('update:modelValue')).toEqual([[user.id]])

    // A field that cannot be edited is left as it is.
    const locked = mount(PersonnelSelect, { props: { modelValue: '', roles: ['Sales'], ariaLabel: 'owner', owner: true, disabled: true }, global: { plugins: [pinia] } })
    expect(locked.emitted('update:modelValue')).toBeUndefined()
    // A field without the attribute offers everyone of its roles.
    const reviewer = mount(PersonnelSelect, { props: { modelValue: '', roles: ['Sales'], ariaLabel: 'reviewer' }, global: { plugins: [pinia] } })
    expect(people(reviewer)).toContain(other)
    expect(reviewer.emitted('update:modelValue')).toBeUndefined()
  })

  it('lets a Manager choose the owner among the roles of the field', async () => {
    const { pinia, user } = await signedIn('Manager')
    const field = mount(PersonnelSelect, { props: { modelValue: 'person005@crm.example.invalid', roles: ['Sales'], ariaLabel: 'owner', owner: true }, global: { plugins: [pinia] } })
    expect(people(field)).toEqual(expect.arrayContaining(['person002@crm.example.invalid', 'person005@crm.example.invalid']))
    expect(people(field)).not.toContain(user.id)
    expect(field.emitted('update:modelValue')).toBeUndefined()
  })

  it('starts a new Lead with the signed-in Sales user as its owner', async () => {
    // Not the first Sales user of the directory, whom the form used to take.
    const { pinia, user } = await signedIn('Sales', BELLA)
    expect(preferredPersonnelId('Sales', '')).not.toBe(user.id)
    const editor = mount(LeadEditorModal, { props: { lead: null }, global: { plugins: [pinia] } })
    await flushPromises()
    const owner = editor.get<HTMLSelectElement>('select[aria-label="负责人"]')
    expect(owner.element.value).toBe(user.id)
    expect(people(owner as unknown as ReturnType<typeof mount>)).toEqual([user.id])
    editor.unmount()

    // A Manager is not a Sales user: the field starts with a Sales user and offers all of them.
    const manager = await signedIn('Manager')
    const managed = mount(LeadEditorModal, { props: { lead: null }, global: { plugins: [manager.pinia] } })
    await flushPromises()
    const managedOwner = managed.get<HTMLSelectElement>('select[aria-label="负责人"]')
    expect(people(managedOwner as unknown as ReturnType<typeof mount>).length).toBeGreaterThan(1)
    managed.unmount()
  })

  it('starts a new Visit with the signed-in Sales user, on an Account of another owner as well', async () => {
    const { pinia, user } = await signedIn('Sales', BELLA)
    // A public Account of a colleague: the form used to take the Account's owner.
    const account = accounts.find((item) => item.owner !== user.id)!
    const modal = mount(VisitModal, { props: { mode: 'create', accounts: [account], initialAccountId: account.id }, global: { plugins: [pinia] } })
    await flushPromises()
    const owner = modal.get<HTMLSelectElement>('select[aria-label="拜访负责人"]')
    expect(owner.element.value).toBe(user.id)
    expect(people(owner as unknown as ReturnType<typeof mount>)).toEqual([user.id])
    // What is sent names the user as the owner.
    await modal.get('[aria-label="拜访主题"]').setValue('Process review')
    await modal.get('[aria-label="拜访目标"]').setValue('Confirm the acceptance requirements')
    await modal.get('form').trigger('submit')
    expect(modal.emitted('submit')![0][0]).toMatchObject({ accountId: account.id, owner: user.id })
    modal.unmount()
  })

  it('keeps a Sales user as the Sales contact when an imported form names a colleague', async () => {
    const { api, pinia, user } = await signedIn('Sales', BELLA)
    const imported = createEmptyDemoRequestFormData()
    Object.assign(imported, { salesContact: 'Demo Staff 01', primaryTool: 'Aconca FS Edge' })
    const importDemoRequestForm = vi.fn().mockResolvedValue({
      data: { fileName: 'drf.pdf', companyName: accounts[0].name, formData: imported, detectedFields: ['salesContact', 'primaryTool'] },
    })
    const modal = mount(DemoRequestModal, {
      props: { mode: 'create', accounts, contacts: [], currentSalesContact: user.id, apiClient: { ...api, importDemoRequestForm } },
      global: { plugins: [pinia] },
    })
    const input = modal.get('[data-import-demo-request-input]')
    Object.defineProperty(input.element, 'files', { value: [new File(['pdf'], 'drf.pdf', { type: 'application/pdf' })] })
    await input.trigger('change')
    await flushPromises()
    // The form was read (its tool is filled in), and the Sales contact is still the user, the one choice there is.
    expect(modal.get<HTMLInputElement>('[name="primaryTool"]').element.value).toBe('Aconca FS Edge')
    const contact = modal.get<HTMLSelectElement>('select[name="salesContact"]')
    expect(contact.element.value).toBe(user.id)
    expect(people(contact as unknown as ReturnType<typeof mount>)).toEqual([user.id])
    modal.unmount()

    // A Manager's import takes the colleague the form names.
    const manager = await signedIn('Manager')
    const managed = mount(DemoRequestModal, {
      props: { mode: 'create', accounts, contacts: [], currentSalesContact: BELLA, apiClient: { ...manager.api, importDemoRequestForm } },
      global: { plugins: [manager.pinia] },
    })
    const managedInput = managed.get('[data-import-demo-request-input]')
    Object.defineProperty(managedInput.element, 'files', { value: [new File(['pdf'], 'drf.pdf', { type: 'application/pdf' })] })
    await managedInput.trigger('change')
    await flushPromises()
    expect(managed.get<HTMLSelectElement>('select[name="salesContact"]').element.value).toBe('person002@crm.example.invalid')
    managed.unmount()
  })

  it('offers a Sales user only themselves as the Sales contact of a Demo Request', async () => {
    const { pinia, user } = await signedIn('Sales')
    const form = mount(DemoRequestForm, {
      props: { modelValue: createEmptyDemoRequestFormData(user.id), accountId: '', accounts },
      global: { plugins: [pinia] },
    })
    const contact = form.get<HTMLSelectElement>('select[name="salesContact"]')
    expect(people(contact as unknown as ReturnType<typeof mount>)).toEqual([user.id])
    expect(contact.element.value).toBe(user.id)

    const manager = await signedIn('Manager')
    const managed = mount(DemoRequestForm, {
      props: { modelValue: createEmptyDemoRequestFormData(), accountId: '', accounts },
      global: { plugins: [manager.pinia] },
    })
    expect(people(managed.get('select[name="salesContact"]') as unknown as ReturnType<typeof mount>).length).toBeGreaterThan(1)
  })
})
