export const DASHBOARD_CHART_IDS = [
  'evaluation-status',
  'booking-month',
  'top-accounts',
  'region',
  'tier',
  'risk',
  'requirements',
  'budget',
  'actions',
  'action-timeliness',
  'demo',
  'demo-priority',
  'evaluation-runs',
  'visits',
  'visit-owner',
] as const

export type DashboardChartId = typeof DASHBOARD_CHART_IDS[number]
export type DashboardSubscriptionGroups = DashboardChartId[][]

export const DEFAULT_BOSS_DASHBOARD_SUBSCRIPTIONS = [
  'evaluation-status',
  'booking-month',
  'top-accounts',
] as const satisfies readonly DashboardChartId[]

export const DEFAULT_BOSS_DASHBOARD_SUBSCRIPTION_GROUPS: DashboardSubscriptionGroups = [
  [...DEFAULT_BOSS_DASHBOARD_SUBSCRIPTIONS],
]

export interface DashboardSubscriptionStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

const knownChartIds = new Set<string>(DASHBOARD_CHART_IDS)
const retiredContractChartIds = new Set(['contracts', 'contract-type', 'contract-risk'])
const maxSubscriptionGroups = Math.floor(DASHBOARD_CHART_IDS.length / 3)

export function bossDashboardSubscriptionKey(userId: string) {
  return `semiconductor-crm:boss-dashboard-subscriptions:v1:${encodeURIComponent(userId)}`
}

export function bossDashboardSubscriptionGroupsKey(userId: string) {
  return `semiconductor-crm:boss-dashboard-subscriptions:v2:${encodeURIComponent(userId)}`
}

function isValidSubscriptionList(value: unknown): value is DashboardChartId[] {
  if (!Array.isArray(value) || value.length !== 3) return false
  if (!value.every((item) => typeof item === 'string' && knownChartIds.has(item))) return false
  return new Set(value).size === 3
}

function isValidSubscriptionGroups(value: unknown): value is DashboardSubscriptionGroups {
  if (!Array.isArray(value) || value.length < 1 || value.length > maxSubscriptionGroups) return false
  if (!value.every(isValidSubscriptionList)) return false
  const ids = value.flat()
  return new Set(ids).size === ids.length
}

function migrateRetiredContractGroups(value: unknown): DashboardSubscriptionGroups | null {
  if (!Array.isArray(value)) return null
  const ids = value
    .flatMap((group) => Array.isArray(group) ? group : [])
    .filter((id): id is DashboardChartId => typeof id === 'string' && !retiredContractChartIds.has(id) && knownChartIds.has(id))
  const uniqueIds = [...new Set(ids)]
  const completeLength = Math.floor(uniqueIds.length / 3) * 3
  if (completeLength < 3) return null
  const groups: DashboardSubscriptionGroups = []
  for (let index = 0; index < completeLength; index += 3) groups.push(uniqueIds.slice(index, index + 3))
  return groups
}

export function normalizeBossDashboardSubscriptions(value: unknown): DashboardChartId[] {
  return isValidSubscriptionList(value)
    ? [...value]
    : [...DEFAULT_BOSS_DASHBOARD_SUBSCRIPTIONS]
}

export function normalizeBossDashboardSubscriptionGroups(value: unknown): DashboardSubscriptionGroups {
  return isValidSubscriptionGroups(value)
    ? value.map((group) => [...group])
    : DEFAULT_BOSS_DASHBOARD_SUBSCRIPTION_GROUPS.map((group) => [...group])
}

export function readBossDashboardSubscriptions(
  storage: DashboardSubscriptionStorage | null | undefined,
  userId: string,
): DashboardChartId[] {
  if (!storage) return [...DEFAULT_BOSS_DASHBOARD_SUBSCRIPTIONS]
  try {
    const saved = storage.getItem(bossDashboardSubscriptionKey(userId))
    return saved ? normalizeBossDashboardSubscriptions(JSON.parse(saved)) : [...DEFAULT_BOSS_DASHBOARD_SUBSCRIPTIONS]
  } catch {
    return [...DEFAULT_BOSS_DASHBOARD_SUBSCRIPTIONS]
  }
}

export function readBossDashboardSubscriptionGroups(
  storage: DashboardSubscriptionStorage | null | undefined,
  userId: string,
): DashboardSubscriptionGroups {
  if (!storage) return normalizeBossDashboardSubscriptionGroups(null)
  try {
    const savedGroups = storage.getItem(bossDashboardSubscriptionGroupsKey(userId))
    if (savedGroups !== null) {
      const parsedGroups = JSON.parse(savedGroups)
      if (isValidSubscriptionGroups(parsedGroups)) return parsedGroups.map((group) => [...group])
      return migrateRetiredContractGroups(parsedGroups) ?? normalizeBossDashboardSubscriptionGroups(null)
    }

    const legacySelection = storage.getItem(bossDashboardSubscriptionKey(userId))
    if (legacySelection === null) return normalizeBossDashboardSubscriptionGroups(null)
    const parsedLegacySelection = JSON.parse(legacySelection)
    return isValidSubscriptionList(parsedLegacySelection)
      ? [[...parsedLegacySelection]]
      : normalizeBossDashboardSubscriptionGroups(null)
  } catch {
    return normalizeBossDashboardSubscriptionGroups(null)
  }
}

export function writeBossDashboardSubscriptions(
  storage: DashboardSubscriptionStorage | null | undefined,
  userId: string,
  ids: unknown,
) {
  if (!storage || !isValidSubscriptionList(ids)) return false
  try {
    storage.setItem(bossDashboardSubscriptionKey(userId), JSON.stringify(ids))
    return true
  } catch {
    return false
  }
}

export function writeBossDashboardSubscriptionGroups(
  storage: DashboardSubscriptionStorage | null | undefined,
  userId: string,
  groups: unknown,
) {
  if (!storage || !isValidSubscriptionGroups(groups)) return false
  try {
    storage.setItem(bossDashboardSubscriptionGroupsKey(userId), JSON.stringify(groups))
    return true
  } catch {
    return false
  }
}
