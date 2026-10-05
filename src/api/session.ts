/** Dispatched on `window` when a request finds the session gone while the page is in use. */
export const SESSION_EXPIRED_EVENT = 'rayher-crm:session-expired'

/** The Frappe login page, coming back to the current address after signing in. */
export function loginUrl() {
  const redirect = window.location.pathname + window.location.search + window.location.hash
  return '/login?redirect-to=' + encodeURIComponent(redirect || '/crm')
}
