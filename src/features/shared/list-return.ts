import type { LocationQuery, RouteLocationRaw, Router } from 'vue-router'

// A list opens a record with its own URL in `from`: its search, filters and page. The record's "Back to ..."
// control returns there, and to the plain list when the record was opened elsewhere or `from` is not that list.
export function listReturnTarget(router: Router, query: LocationQuery, list: string): RouteLocationRaw {
  const from = query.from
  if (typeof from === 'string' && from.startsWith('/') && router.resolve(from).name === list) return from
  return { name: list }
}
