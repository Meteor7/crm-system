import { CrmApiError } from '@/api/contracts'
import type { PersonnelRole, UserId } from '@/types/crm'

export interface PersonnelIdentity {
  id: UserId
  demoIdentityId?: string
  availableForAssignment: boolean
  name: string
  initials: string
  role: PersonnelRole
  team: string
  teamOwners: UserId[]
  assignedAccountIds: string[]
}

export const PERSONNEL: PersonnelIdentity[] = [
  { id: 'person029@crm.example.invalid', demoIdentityId: 'administrator', availableForAssignment: true, name: '\u6f14\u793a\u5458\u5de524', initials: '\u6797', role: 'Manager', team: 'CRM Operations', teamOwners: ['person002@crm.example.invalid', 'person005@crm.example.invalid'], assignedAccountIds: [] },
  { id: 'person073@crm.example.invalid', demoIdentityId: 'management', availableForAssignment: true, name: '\u6f14\u793a\u7ecf\u740601', initials: '\u8d75', role: 'Manager', team: '\u7ba1\u7406\u5c42', teamOwners: ['person002@crm.example.invalid', 'person005@crm.example.invalid'], assignedAccountIds: [] },
  { id: 'person015@crm.example.invalid', demoIdentityId: 'sales-manager', availableForAssignment: true, name: 'Demo Staff 06', initials: 'GL', role: 'Manager', team: '\u5927\u4e2d\u534e\u533a\u9500\u552e', teamOwners: ['person002@crm.example.invalid', 'person005@crm.example.invalid'], assignedAccountIds: [] },
  { id: 'person002@crm.example.invalid', demoIdentityId: 'sales-user', availableForAssignment: true, name: 'Demo Staff 01', initials: 'AC', role: 'Sales', team: '\u534e\u4e1c\u9500\u552e', teamOwners: ['person002@crm.example.invalid'], assignedAccountIds: [] },
  { id: 'person005@crm.example.invalid', demoIdentityId: 'sales-bella', availableForAssignment: true, name: 'Demo Staff 02', initials: 'BW', role: 'Sales', team: '\u534e\u4e1c\u9500\u552e', teamOwners: ['person005@crm.example.invalid'], assignedAccountIds: [] },
  { id: 'person077@crm.example.invalid', demoIdentityId: 'fae', availableForAssignment: true, name: '\u6f14\u793a\u5458\u5de514', initials: '\u5468', role: 'Engineer', team: '\u5e94\u7528\u5de5\u7a0b', teamOwners: [], assignedAccountIds: ['ACC-001', 'ACC-003', 'ACC-006'] },
  { id: 'person053@crm.example.invalid', demoIdentityId: 'equipment-engineer', availableForAssignment: true, name: '\u6f14\u793a\u5458\u5de515', initials: '\u5b59', role: 'Engineer', team: '\u8bbe\u5907\u9a8c\u8bc1\u5de5\u7a0b', teamOwners: [], assignedAccountIds: ['ACC-001', 'ACC-005', 'ACC-006'] },
  { id: 'person034@crm.example.invalid', availableForAssignment: false, name: 'Demo Staff 08', initials: 'MW', role: 'Sales', team: '\u534e\u4e1c\u9500\u552e', teamOwners: ['person034@crm.example.invalid'], assignedAccountIds: [] },
  { id: 'person025@crm.example.invalid', availableForAssignment: false, name: 'Demo Staff 07', initials: 'KS', role: 'Sales', team: '\u534e\u4e1c\u9500\u552e', teamOwners: ['person025@crm.example.invalid'], assignedAccountIds: [] },
  { id: 'person012@crm.example.invalid', availableForAssignment: false, name: 'Demo Staff 05', initials: 'EZ', role: 'Engineer', team: '\u8bbe\u5907\u9a8c\u8bc1\u5de5\u7a0b', teamOwners: [], assignedAccountIds: [] },
  { id: 'person028@crm.example.invalid', availableForAssignment: false, name: '\u6f14\u793a\u5458\u5de523', initials: '\u6797', role: 'Engineer', team: '\u5e94\u7528\u5de5\u7a0b', teamOwners: [], assignedAccountIds: [] },
]

export function initializePersonnelDirectory(personnel: PersonnelIdentity[]) {
  PERSONNEL.splice(0, PERSONNEL.length, ...personnel.map((person) => ({ ...person })))
}

export function personnelForRole(role: PersonnelRole) {
  return PERSONNEL.filter((person) => person.role === role && person.availableForAssignment)
}

export function personnelForRoles(roles: readonly PersonnelRole[]) {
  return PERSONNEL.filter((person) => roles.includes(person.role) && person.availableForAssignment)
}

export function personnelById(id: string) {
  return PERSONNEL.find((person) => person.id === id)
}

export function personnelDisplayName(id: string) {
  return personnelById(id)?.name ?? id
}

export function preferredPersonnelId(role: PersonnelRole, preferred = '') {
  const person = personnelById(preferred)
  return person?.role === role ? person.id : personnelForRole(role)[0]?.id ?? ''
}

export function isPersonnelId(value: string) {
  return Boolean(personnelById(value))
}

export function assertPersonnelRole(value: string, roles: readonly PersonnelRole[]) {
  const person = personnelById(value)
  if (!person || !roles.includes(person.role)) {
    throw new CrmApiError(
      'INVALID_OWNER',
      `Owner must be selected from ${roles.join(' / ')}`,
      'req_invalid_owner',
      false,
      { owner: 'Select a valid internal person' },
    )
  }
}
