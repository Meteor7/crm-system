import { shallowRef } from 'vue'

/** The layer of the first dialog: above the Account drawer (2000). */
export const MODAL_BASE_LAYER = 2200

/**
 * Every open ModalShell, in the order it opened. The page's order is not the order of opening: a dialog
 * can open another one that the page places before it (Opportunity detail's contact dialog sits before
 * the PO confirmation that opens it, and the confirmation stays open underneath).
 */
const opened = shallowRef<HTMLElement[]>([])

export function openModal(host: HTMLElement) {
  opened.value = [...opened.value.filter(entry => entry !== host), host]
}

export function closeModal(host: HTMLElement) {
  opened.value = opened.value.filter(entry => entry !== host)
}

/** The dialog in front: the last one opened that is still in the page. */
export function topModal(): HTMLElement | undefined {
  for (let index = opened.value.length - 1; index >= 0; index--) {
    if (opened.value[index]!.isConnected) return opened.value[index]
  }
  return undefined
}

/** The z-index of a dialog: each one opened over another is painted above it. */
export function modalLayer(host: HTMLElement | null) {
  return MODAL_BASE_LAYER + (host ? Math.max(0, opened.value.indexOf(host)) : 0)
}
