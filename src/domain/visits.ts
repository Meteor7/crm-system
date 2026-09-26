import type { CreateVisitInput, UserRole, VisitStatus } from '@/types/crm'

export const VISIT_STATUS_ORDER: VisitStatus[] = ['Planned', 'Visited', 'Minutes Submitted', 'Manager Reviewed']

/** Mirrors the backend `edit` command: a Visit is frozen once the Manager has reviewed the minutes. */
export function isVisitEditable(visit: { status: VisitStatus }) {
  return visit.status !== 'Manager Reviewed'
}

/**
 * Mirrors the backend `assert_can_change_visit`. Sales also see a colleague's visit as its
 * action owner, but only to complete that action; editing the visit, writing its meeting
 * record (a complete record submits it for review) and above all naming themselves owner
 * stay with the visit owner and the Managers.
 */
export function canChangeVisit(
  visit: { owner: string; status: VisitStatus },
  user: { id: string; role: UserRole } | null | undefined,
) {
  return isVisitEditable(visit) && !!user && (user.role === 'Manager' || visit.owner === user.id)
}

export function validateCreateVisit(input: CreateVisitInput) {
  const required: Array<[keyof CreateVisitInput, string]> = [
    ['accountId', '客户'], ['subject', '拜访主题'], ['date', '拜访日期'], ['type', '拜访方式'], ['owner', '负责人'], ['objective', '拜访目标'],
  ]
  const missing = required.filter(([key]) => !String(input[key] ?? '').trim()).map(([, label]) => label)
  if (missing.length) throw new Error(`请填写：${missing.join('、')}`)
}
