import type { CreateVisitInput, VisitStatus } from '@/types/crm'

export const VISIT_STATUS_ORDER: VisitStatus[] = ['Planned', 'Visited', 'Minutes Submitted', 'Manager Reviewed']

export function validateCreateVisit(input: CreateVisitInput) {
  const required: Array<[keyof CreateVisitInput, string]> = [
    ['accountId', '客户'], ['subject', '拜访主题'], ['date', '拜访日期'], ['type', '拜访方式'], ['owner', '负责人'], ['objective', '拜访目标'],
  ]
  const missing = required.filter(([key]) => !String(input[key] ?? '').trim()).map(([, label]) => label)
  if (missing.length) throw new Error(`请填写：${missing.join('、')}`)
}
