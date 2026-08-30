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

export const PERSONNEL: PersonnelIdentity[] = []

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
    throw new CrmApiError('INVALID_OWNER', `Owner must be selected from ${roles.join(' / ')}`, 'req_invalid_owner', false, { owner: 'Select a valid internal person' })
  }
}
