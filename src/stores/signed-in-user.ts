import { computed } from 'vue'
import { getActivePinia } from 'pinia'
import { useAppStore } from './app'

/**
 * The signed-in user, for a component that is used with or without the app around it. A component mounted
 * on its own in a unit test has no store, and then there is no user.
 */
export function useSignedInUser() {
  const store = getActivePinia() ? useAppStore() : null
  return computed(() => store?.bootstrap?.user ?? null)
}

/**
 * The only person a Sales user can make the owner of a record: themselves. The server refuses a Sales user
 * who assigns a record to anyone else, so their owner fields offer nobody else. '' for everyone who may choose.
 */
export function useOwnOwnerOnly() {
  const user = useSignedInUser()
  return computed(() => user.value?.role === 'Sales' ? user.value.id : '')
}
