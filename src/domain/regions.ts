import type { Locale } from '@/i18n'

/** Five domestic regions, stored in English. Custom regions Sales add follow them in the shared list. */
export const REGION_PRESETS = ['East China', 'South China', 'West China', 'North China', 'Central China'] as const
export type RegionPreset = (typeof REGION_PRESETS)[number]

const REGION_LABELS: Record<RegionPreset, Record<Locale, string>> = {
  'East China': { 'zh-CN': '华东', 'en-US': 'East China' },
  'South China': { 'zh-CN': '华南', 'en-US': 'South China' },
  'West China': { 'zh-CN': '华西', 'en-US': 'West China' },
  'North China': { 'zh-CN': '华北', 'en-US': 'North China' },
  'Central China': { 'zh-CN': '华中', 'en-US': 'Central China' },
}

// Mirrors rayher_crm.services.regions so the demo adapter stores what the server stores.
const PRESET_ALIASES: Record<RegionPreset, readonly string[]> = {
  'East China': ['华东', '華東', 'east', 'eastern', 'eastchina', 'easternchina'],
  'South China': ['华南', '華南', 'south', 'southern', 'southchina', 'southernchina'],
  'West China': ['华西', '華西', 'west', 'western', 'westchina', 'westernchina'],
  'North China': ['华北', '華北', 'north', 'northern', 'northchina', 'northernchina'],
  'Central China': ['华中', '華中', 'central', 'centralchina'],
}
const ALIAS_TO_PRESET = new Map(
  REGION_PRESETS.flatMap((preset) => PRESET_ALIASES[preset].map((alias) => [alias, preset] as const)),
)
const CHINESE_PREFIXES = ['中国']
const CHINESE_SUFFIXES = ['大区', '地区', '区域', '区']
const LATIN_SUFFIXES = ['region', 'area']
const SEPARATORS = /[\s\-_/\\()（）.,，、·:：]+/g
const RUNS = /[㐀-鿿]+|[a-z]+|[^㐀-鿿a-z]+/g
const HAN = /^[㐀-鿿]/
const ENGLISH_NAME = /^[A-Za-z][A-Za-z0-9 &'().,/-]*$/

export function isRegionPreset(value: unknown): value is RegionPreset {
  return typeof value === 'string' && (REGION_PRESETS as readonly string[]).includes(value)
}

export function collapseRegion(value: string) {
  return value.split(/\s+/).filter(Boolean).join(' ')
}

/** Compares regions ignoring case, spacing and punctuation. */
export function regionKey(value: string) {
  return collapseRegion(value).toLowerCase().replace(SEPARATORS, '')
}

function stripAffixes(text: string, prefixes: readonly string[], suffixes: readonly string[]) {
  const prefix = prefixes.find((item) => text.startsWith(item) && text.length > item.length)
  const trimmed = prefix ? text.slice(prefix.length) : text
  const suffix = suffixes.find((item) => trimmed.endsWith(item) && trimmed.length > item.length)
  return suffix ? trimmed.slice(0, -suffix.length) : trimmed
}

/** The preset a spelling stands for ("华东区", "East" -> East China), or '' when it names no preset. */
export function presetRegion(value: string): RegionPreset | '' {
  const key = regionKey(value)
  if (!key) return ''
  const runs = key.match(RUNS) ?? []
  if (runs.some((run) => !HAN.test(run) && !/^[a-z]+$/.test(run))) return ''
  const chinese = runs.filter((run) => HAN.test(run)).join('')
  const latin = runs.filter((run) => !HAN.test(run)).join('')
  const presets = new Set<RegionPreset | undefined>()
  if (chinese) presets.add(ALIAS_TO_PRESET.get(stripAffixes(chinese, CHINESE_PREFIXES, CHINESE_SUFFIXES)))
  if (latin) presets.add(ALIAS_TO_PRESET.get(latin) ?? ALIAS_TO_PRESET.get(stripAffixes(latin, [], LATIN_SUFFIXES)))
  const [preset] = [...presets]
  return presets.size === 1 && preset ? preset : ''
}

export function isEnglishRegion(value: string) {
  return ENGLISH_NAME.test(collapseRegion(value))
}

/** Presets first, then custom regions in the order they were added. */
export function regionOptions(values: readonly string[]) {
  return [...new Set([...REGION_PRESETS, ...values.map(collapseRegion)].filter(Boolean))]
}

/** The stored spelling for a submitted region, or '' when it would be a new custom region. */
export function matchingRegion(value: string, options: readonly string[]) {
  const preset = presetRegion(value)
  if (preset) return preset
  const key = regionKey(value)
  return options.find((option) => regionKey(option) === key) ?? ''
}

/** Normalizes a region cached before the shared options; unknown spellings keep their text. */
export function normalizeStoredRegion(value: string) {
  return presetRegion(value) || collapseRegion(value)
}

/** The sales territories above the regions in the default tree; like the regions, stored in English. */
const TERRITORY_LABELS: Record<string, Record<Locale, string>> = {
  World: { 'zh-CN': '全球', 'en-US': 'World' },
  Asia: { 'zh-CN': '亚洲', 'en-US': 'Asia' },
  China: { 'zh-CN': '中国', 'en-US': 'China' },
}

export function regionLabel(value: string, locale: Locale) {
  if (isRegionPreset(value)) return REGION_LABELS[value][locale]
  return Object.hasOwn(TERRITORY_LABELS, value) ? TERRITORY_LABELS[value][locale] : value
}

/** The parent of each name in the sales territory tree, as the region filters send it. */
export type RegionParents = Readonly<Record<string, string>>

/** How many territories sit above a name; 0 for the top of the tree and for a region outside it. */
export function regionDepth(value: string, parents: RegionParents = {}) {
  const seen = new Set([value])
  let depth = 0
  for (let name = value; Object.hasOwn(parents, name) && !seen.has(parents[name]); depth++) {
    name = parents[name]
    seen.add(name)
  }
  return depth
}

/** A region filter option in a native select: the label, indented by its depth in the tree. */
export function territoryOptionLabel(value: string, parents: RegionParents | undefined, locale: Locale) {
  return '\u00a0\u00a0'.repeat(regionDepth(value, parents)) + regionLabel(value, locale)
}
