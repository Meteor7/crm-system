import {
  PERSONNEL,
  isPersonnelId,
  personnelForRole,
  type PersonnelIdentity,
} from '@/demo/personnel'

export type DemoIdentity = PersonnelIdentity

export const DEMO_IDENTITIES = PERSONNEL.filter((person) => person.demoIdentityId)
export function demoSalesOwnerOptions() {
  return personnelForRole('Sales').map((person) => person.id)
}

export function demoEngineerOwnerOptions() {
  return personnelForRole('Engineer').map((person) => person.id)
}

export function isDemoSalesOwner(value: string) {
  return isPersonnelId(value) && demoSalesOwnerOptions().includes(value)
}

export function isDemoEngineerOwner(value: string) {
  return isPersonnelId(value) && demoEngineerOwnerOptions().includes(value)
}

export function getDemoIdentity(id: string) {
  return DEMO_IDENTITIES.find((identity) => identity.demoIdentityId === id) ?? DEMO_IDENTITIES[0]
}
