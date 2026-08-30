import { describe, expect, it } from 'vitest'
import { ROLE_PROFILES } from '@/domain/permissions'
import {
  DEMO_IDENTITIES,
  demoEngineerOwnerOptions,
  demoSalesOwnerOptions,
  getDemoIdentity,
} from './identities'

describe('demo employee identities', () => {
  it('covers every configured person through the three permission categories', () => {
    expect(new Set(DEMO_IDENTITIES.map((identity) => identity.demoIdentityId)).size).toBe(7)
    expect(DEMO_IDENTITIES.map((identity) => identity.role)).toEqual([
      'Manager',
      'Manager',
      'Manager',
      'Sales',
      'Sales',
      'Engineer',
      'Engineer',
    ])
  })

  it('returns the requested identity and defaults to the administrator', () => {
    expect(getDemoIdentity('sales-user').name).toBe('Demo Staff 01')
    expect(getDemoIdentity('missing').demoIdentityId).toBe('administrator')
  })

  it('keeps the engineering category in assigned scope', () => {
    expect(ROLE_PROFILES.Engineer.scope).toBe('assigned')
  })

  it('publishes only the approved Demo owner choices', () => {
    expect(demoSalesOwnerOptions()).toEqual(['person002@crm.example.invalid', 'person005@crm.example.invalid'])
    expect(demoEngineerOwnerOptions()).toEqual(['person077@crm.example.invalid', 'person053@crm.example.invalid'])
  })
})
