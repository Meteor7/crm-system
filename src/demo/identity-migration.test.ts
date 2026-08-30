import { describe, expect, it } from 'vitest'
import { CrmApiError } from '@/api/contracts'
import { LEGACY_INTERNAL_USER_MAPPINGS, migrateLegacyUserId } from './identity-migration'
import { isPersonnelId, personnelDisplayName } from './personnel'

describe('legacy internal identity migration', () => {
  it('resolves every controlled legacy name and alias to a known Frappe User id', () => {
    for (const row of LEGACY_INTERNAL_USER_MAPPINGS) {
      expect(migrateLegacyUserId(row.legacyValue, 'owner')).toBe(row.userId)
      expect(isPersonnelId(row.userId)).toBe(true)
      expect(personnelDisplayName(row.userId)).not.toContain('@crm.example.invalid')
    }
  })

  it('is idempotent for already migrated values', () => {
    expect(migrateLegacyUserId('person002@crm.example.invalid', 'owner')).toBe('person002@crm.example.invalid')
  })

  it('fails closed for external labels and unknown internal values', () => {
    expect(() => migrateLegacyUserId('Customer QE', 'actor')).toThrowError(CrmApiError)
    expect(() => migrateLegacyUserId('Product Engineering', 'owner')).toThrowError(CrmApiError)
    expect(() => migrateLegacyUserId('Unknown Owner', 'owner')).toThrowError(CrmApiError)
  })
})
