import { describe, expect, it } from 'vitest'
import { CrmApiError } from '@/api/contracts'
import { ROLE_PROFILES, assertCapability, hasCapability } from './permissions'

describe('role permissions', () => {
  it('exposes exactly the three approved role categories', () => {
    expect(Object.keys(ROLE_PROFILES)).toEqual(['Manager', 'Sales', 'Engineer'])
  })

  it('gives Manager unrestricted scope without dead capabilities', () => {
    expect(ROLE_PROFILES.Manager).toMatchObject({
      scope: 'all',
    })
    expect(ROLE_PROFILES.Manager.capabilities).toContain('account:write')
    expect(ROLE_PROFILES.Manager.capabilities).not.toContain('system:configure')
  })

  it('keeps Manager as a complete capability superset of Sales', () => {
    expect(ROLE_PROFILES.Manager.capabilities).toEqual(expect.arrayContaining(
      ROLE_PROFILES.Sales.capabilities,
    ))
    expect(ROLE_PROFILES.Manager.capabilities).toEqual(expect.arrayContaining([
      'quotation:view', 'quotation:write', 'quotation:submit', 'quotation:approve', 'quotation:publish',
    ]))
    expect(ROLE_PROFILES.Sales.capabilities).toEqual(expect.arrayContaining([
      'quotation:view', 'quotation:write', 'quotation:submit',
    ]))
    expect(ROLE_PROFILES.Sales.capabilities).not.toContain('quotation:publish')
    expect(ROLE_PROFILES.Sales.capabilities).not.toContain('quotation:approve')
    expect(ROLE_PROFILES.Engineer.capabilities).not.toContain('quotation:view')
  })

  it('reserves Demo Request approval for Manager without template-report capabilities', () => {
    expect(ROLE_PROFILES.Manager.capabilities).toContain('demo_request:manager_approve')
    expect(ROLE_PROFILES.Sales.capabilities).not.toContain('demo_request:manager_approve')
    expect(ROLE_PROFILES.Manager.capabilities.some((item) => item.startsWith('demo_report:'))).toBe(false)
    expect(ROLE_PROFILES.Sales.capabilities.some((item) => item.startsWith('demo_report:'))).toBe(false)
  })

  it('separates Sales and Engineer workflow actions', () => {
    expect(ROLE_PROFILES.Sales.capabilities).toContain('demo_request:create')
    expect(ROLE_PROFILES.Sales.capabilities).not.toContain('demo_request:engineering_review')
    expect(ROLE_PROFILES.Engineer.capabilities).toContain('demo_request:engineering_review')
    expect(ROLE_PROFILES.Engineer.capabilities).not.toContain('deal:write')
    expect(ROLE_PROFILES.Engineer.capabilities).not.toContain('visit:view')
  })

  it('allows Manager and Engineer to edit Installed Tools but keeps Sales read-only', () => {
    expect(ROLE_PROFILES.Manager.capabilities).toContain('installed_tool:write')
    expect(ROLE_PROFILES.Engineer.capabilities).toContain('installed_tool:write')
    expect(ROLE_PROFILES.Sales.capabilities).not.toContain('installed_tool:write')
  })

  it('grants writable Contact access to Manager and Sales only', () => {
    expect(ROLE_PROFILES.Manager.capabilities).toEqual(expect.arrayContaining([
      'contact:view', 'contact:write', 'contact:merge', 'contact:delete',
    ]))
    expect(ROLE_PROFILES.Sales.capabilities).toEqual(expect.arrayContaining([
      'contact:view', 'contact:write',
    ]))
    expect(ROLE_PROFILES.Engineer.capabilities).not.toContain('contact:write')
    expect(ROLE_PROFILES.Sales.capabilities).not.toContain('contact:delete')
  })

  it('reports denied capabilities through the shared API error model', () => {
    expect(() => assertCapability(ROLE_PROFILES.Sales.capabilities, 'evaluation:write'))
      .toThrowError(CrmApiError)
    expect(hasCapability({ capabilities: ROLE_PROFILES.Manager.capabilities }, 'account:view')).toBe(true)
  })
})
