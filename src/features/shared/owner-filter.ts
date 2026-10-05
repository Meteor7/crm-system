import { personnelForRoles } from '@/demo/personnel'
import type { PersonnelRole } from '@/types/crm'

/**
 * Owner choices of a Lead or Opportunity list filter.
 *
 * A Manager or an Engineer can meet records of every Sales user and Manager, so all of them are
 * offered and the choices do not shrink to the owners on the rows loaded last. A Sales user only
 * ever sees their own records, so nobody else is offered. Owners the choices would otherwise lack (a
 * disabled user's records, the owner named in a bookmarked link) are kept from the loaded rows and
 * the current selection.
 */
export function ownerFilterOptions(
  viewer: { id: string; role: PersonnelRole } | undefined,
  loadedOwners: readonly string[],
  selected: string,
): string[] {
  const offered = viewer?.role === 'Sales' ? [viewer.id] : personnelForRoles(['Sales', 'Manager']).map((person) => person.id)
  const owners = new Set([...offered, ...loadedOwners])
  if (selected !== 'All') owners.add(selected)
  owners.delete('')
  return [...owners].sort()
}
