import { describe, expect, it } from 'vitest'
import { personnelForRoles } from '@/demo/personnel'
import { ownerFilterOptions } from './owner-filter'

describe('ownerFilterOptions', () => {
  const directory = personnelForRoles(['Sales', 'Manager']).map((person) => person.id).sort()
  const manager = { id: personnelForRoles(['Manager'])[0]!.id, role: 'Manager' as const }
  const sales = { id: personnelForRoles(['Sales'])[0]!.id, role: 'Sales' as const }
  const engineer = { id: personnelForRoles(['Engineer'])[0]!.id, role: 'Engineer' as const }

  it('offers a Manager or an Engineer everyone who can own the record, whatever rows are loaded', () => {
    expect(directory.length).toBeGreaterThan(1)
    for (const viewer of [manager, engineer]) {
      expect(ownerFilterOptions(viewer, [], 'All')).toEqual(directory)
      expect(ownerFilterOptions(viewer, [directory[0]!], directory[0]!)).toEqual(directory)
    }
    for (const person of personnelForRoles(['Engineer'])) {
      expect(ownerFilterOptions(manager, [], 'All')).not.toContain(person.id)
    }
  })

  it('offers a Sales user only themselves', () => {
    expect(ownerFilterOptions(sales, [], 'All')).toEqual([sales.id])
    expect(ownerFilterOptions(sales, [sales.id], sales.id)).toEqual([sales.id])
  })

  it('keeps owners it would otherwise lack, from the loaded rows and the selection', () => {
    expect(ownerFilterOptions(manager, ['former.sales@example.invalid', ''], 'bookmarked.owner@example.invalid')).toEqual(
      [...directory, 'bookmarked.owner@example.invalid', 'former.sales@example.invalid'].sort(),
    )
    expect(ownerFilterOptions(sales, ['former.sales@example.invalid'], 'All')).toEqual([sales.id, 'former.sales@example.invalid'].sort())
  })

  it('offers the directory until the current user is known', () => {
    expect(ownerFilterOptions(undefined, [], 'All')).toEqual(directory)
  })
})
