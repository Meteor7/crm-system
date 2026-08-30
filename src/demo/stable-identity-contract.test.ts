import { describe, expect, expectTypeOf, it } from 'vitest'
import type { BootstrapDto, UserId } from '@/types/crm'
import { PERSONNEL, personnelById, personnelDisplayName } from './personnel'

describe('stable internal identity contract', () => {
  it('uses the same UserId space for Bootstrap and personnel records', () => {
    expectTypeOf<BootstrapDto['user']['id']>().toEqualTypeOf<UserId>()
    expectTypeOf<(typeof PERSONNEL)[number]['id']>().toEqualTypeOf<UserId>()
  })

  it('does not resolve a customer contact display name as an internal user id', () => {
    expect(personnelById('演示员工14')).toBeUndefined()
    expect(personnelDisplayName('演示员工14')).toBe('演示员工14')
    expect(personnelById('person077@crm.example.invalid')?.name).toBe('演示员工14')
  })
})
