import { computed, ref, watch } from 'vue'

// Localize a generated default until the user edits it. Locale changes never write the draft.
export function useLocalizedInput(read: () => string | undefined, write: (value: string) => void, display: (value: string) => string, resetOn?: () => unknown) {
  const edited = ref(false)
  if (resetOn) watch(resetOn, () => { edited.value = false })
  return computed({
    get: () => edited.value ? read() ?? '' : display(read() ?? ''),
    set: (value: string) => { edited.value = true; write(value) },
  })
}
