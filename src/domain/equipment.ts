/** Five preset equipment types; custom types Sales add follow them in the shared list. */
export const EQUIPMENT_PRESETS = ['Aconca', 'Drakens', 'Kibo', 'Nansi', 'Veymont'] as const

// Mirrors rayher_crm.services.equipment so the demo adapter stores what the server stores.
const NON_ALPHANUMERIC = /[^\p{L}\p{N}]/gu
const REFUSED = /[\u0000-\u001f\u007f<>]/
export const MAX_EQUIPMENT_TEXT = 140

const FORMAT_CHARACTERS = /\p{Cf}/gu

/** NFKC text without invisible format characters such as zero-width spaces or a BOM. */
function normalized(value: string) {
  return value.normalize('NFKC').replace(FORMAT_CHARACTERS, '')
}

/** Compares equipment types by letters and digits only, ignoring case, width, accents, spacing, punctuation and invisible characters. */
export function equipmentKey(value: string) {
  return normalized(value).toLowerCase().normalize('NFKD').replace(NON_ALPHANUMERIC, '')
}

/** Presets first, then custom types in the order they were added. */
export function equipmentOptions(values: readonly string[]) {
  return [...new Set([...EQUIPMENT_PRESETS, ...values.map((value) => value.trim())].filter(Boolean))]
}

/** The stored spelling for a submitted type, or '' when it would be a new custom type. */
export function matchingEquipment(value: string, options: readonly string[]) {
  const key = equipmentKey(value)
  const preset = EQUIPMENT_PRESETS.find((item) => equipmentKey(item) === key)
  if (preset) return preset
  if (options.includes(value)) return value
  return options.find((option) => equipmentKey(option) === key) ?? ''
}

/** Collapsed text of a submitted type, or '' when it is empty, only punctuation, or cannot be stored. */
export function equipmentText(value: string) {
  const text = normalized(value).split(/\s+/).filter(Boolean).join(' ')
  return text && text.length <= MAX_EQUIPMENT_TEXT && !REFUSED.test(text) && equipmentKey(text) ? text : ''
}
