export interface DemoResourceInput { code: string; title: string; platform: string; maintainer: string; enabled: boolean }
export interface DemoResource extends DemoResourceInput { id: string; modified: string; canMaintain: boolean }
export interface DemoResourceCatalogue { resources: DemoResource[]; maintainers: { id: string; name: string }[] }
export interface DemoUnavailabilityInput { start: string; end: string; reason: string; status: 'Active' | 'Resolved' }
export interface DemoUnavailability extends DemoUnavailabilityInput { id: string; resourceId: string; modified: string }
export interface DemoResourceScheduleInput { resourceId: string; start: string | null; end: string | null }
export interface DemoResourceImpact { key: string; evaluationId: string; resourceId: string; unavailabilityId: string; reason: string; plannedStart: string; plannedEnd: string; unavailableStart: string; unavailableEnd: string }
export type DemoResourceState = 'unknown' | 'blocked' | 'available' | 'inactive' | 'elapsed'
export interface DemoResourceSchedule extends DemoResourceScheduleInput {
  evaluationId: string; modified: string; state: DemoResourceState; canWrite: boolean; impacts: DemoResourceImpact[]
  history: { id: string; detectedAt: string; current: boolean; snapshot: DemoResourceImpact }[]
}
export interface DemoResourceWarnings {
  count: number; unknown: number
  items: { id: string; demoRequestId: string; title: string; customer: string; owner: string | null; engineer: string; resourceName: string; state: 'blocked' | 'unknown'; impacts: DemoResourceImpact[] }[]
}

// datetime-local explicitly means Shanghai time in these forms, not the browser's zone.
export function shanghaiInput(value: string | null): string {
  if (!value) return ''
  return new Date(new Date(value).getTime() + 8 * 60 * 60 * 1000).toISOString().slice(0, 16)
}
export function shanghaiTimestamp(value: string): string { return `${value}:00+08:00` }

export function resourceDateTime(value: string): string {
  return `${new Date(value).toLocaleString('sv-SE', { timeZone: 'Asia/Shanghai', hour12: false })} (UTC+8)`
}
