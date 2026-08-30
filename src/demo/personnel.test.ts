import { describe, expect, it } from 'vitest'
import { CrmApiError } from '@/api/contracts'
import { PERSONNEL, assertPersonnelRole, isPersonnelId, personnelById, personnelDisplayName, personnelForRole, personnelForRoles, preferredPersonnelId } from './personnel'

const LIN_MO = '\u6f14\u793a\u5458\u5de524'
const BOSS_ZHAO = '\u6f14\u793a\u7ecf\u740601'
const ZHOU_NING = '\u6f14\u793a\u5458\u5de514'
const SUN_HANG = '\u6f14\u793a\u5458\u5de515'

describe('authoritative personnel directory', () => {
  it('maps every configured person to exactly one permission category', () => {
    expect(PERSONNEL.filter((person) => person.demoIdentityId).map(({ name, role }) => [name, role])).toEqual([
      [LIN_MO, 'Manager'], [BOSS_ZHAO, 'Manager'], ['Demo Staff 06', 'Manager'],
      ['Demo Staff 01', 'Sales'], ['Demo Staff 02', 'Sales'], [ZHOU_NING, 'Engineer'], [SUN_HANG, 'Engineer'],
    ])
    expect(new Set(PERSONNEL.map((person) => person.id)).size).toBe(11)
    expect(PERSONNEL.every((person) => /^[a-z.]+@crm\.example\.invalid$/.test(person.id))).toBe(true)
    expect(new Set(PERSONNEL.filter((person) => person.demoIdentityId).map((person) => person.demoIdentityId)).size).toBe(7)
    expect(new Set(PERSONNEL.map((person) => person.name)).size).toBe(11)
  })

  it('returns role-filtered assignment options and resolves Boss', () => {
    expect(personnelForRole('Sales').map((person) => person.name)).toEqual(['Demo Staff 01', 'Demo Staff 02'])
    expect(personnelForRole('Engineer').map((person) => person.name)).toEqual([ZHOU_NING, SUN_HANG])
    expect(personnelForRoles(['Sales', 'Engineer']).map((person) => person.name)).toEqual(['Demo Staff 01', 'Demo Staff 02', ZHOU_NING, SUN_HANG])
    expect(personnelById('person073@crm.example.invalid')).toMatchObject({ demoIdentityId: 'management', role: 'Manager' })
    expect(preferredPersonnelId('Sales', 'person073@crm.example.invalid')).toBe('person002@crm.example.invalid')
    expect(preferredPersonnelId('Engineer', 'person077@crm.example.invalid')).toBe('person077@crm.example.invalid')
    expect(personnelDisplayName('person077@crm.example.invalid')).toBe(ZHOU_NING)
  })

  it('rejects unknown people and people from the wrong category', () => {
    expect(isPersonnelId('person002@crm.example.invalid')).toBe(true)
    expect(isPersonnelId('Demo Staff 01')).toBe(false)
    expect(() => assertPersonnelRole('person002@crm.example.invalid', ['Sales'])).not.toThrow()
    expect(() => assertPersonnelRole('person077@crm.example.invalid', ['Sales'])).toThrowError(CrmApiError)
    expect(() => assertPersonnelRole('Unknown Owner', ['Sales'])).toThrowError(CrmApiError)
  })
})
