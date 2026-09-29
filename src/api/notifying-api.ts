import type { CrmApi } from './contracts'
import type { NotificationInput } from '@/types/notifications'
import { personnelById } from '@/demo/personnel'

type RecordValue = Record<string, unknown>
type NotificationSink = (input: NotificationInput) => void

const NOTIFYING_API = Symbol('notifying-api')

function record(value: unknown): RecordValue {
  return value && typeof value === 'object' ? value as RecordValue : {}
}

function text(value: unknown, fallback = '') {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback
}

function nodeRoute(path: string, id: string) {
  return id ? `${path}?highlight=${encodeURIComponent(id)}` : path
}

function recipientFor(value: unknown): Pick<NotificationInput, 'recipientId' | 'recipient'> {
  const userId = text(value)
  const person = personnelById(userId)
  if (person) return { recipientId: person.id, recipient: person.name }
  return {}
}

function notificationFor(method: keyof CrmApi, args: unknown[], data: unknown): NotificationInput | null {
  const result = record(data)
  const input = record(
    method === 'updateOpportunityStakeholder' || method === 'updateOpportunityAction'
      ? args[2]
      : args[1] ?? args[0],
  )
  const id = text(result.id, text(args[0]))

  switch (method) {
    case 'createAccount':
    case 'updateAccount':
      return {
        category: 'Account',
        title: method === 'createAccount' ? '\u65b0\u589e\u5ba2\u6237\u6863\u6848' : '\u5ba2\u6237\u6863\u6848\u5df2\u66f4\u65b0',
        message: `${text(result.name, id)} - ${text(result.owner, text(input.owner))}`,
        route: id ? `/accounts/${encodeURIComponent(id)}` : '/accounts',
        ...recipientFor(text(result.owner, text(input.owner))),
      }
    case 'createContact':
    case 'updateContact':
      return {
        category: 'Contact',
        title: method === 'updateContact' ? '\u8054\u7cfb\u4eba\u5df2\u66f4\u65b0' : '\u65b0\u589e\u8054\u7cfb\u4eba',
        message: `${text(result.name, id)} - ${text(result.owner, text(input.owner))}`,
        route: id ? `/contacts/${encodeURIComponent(id)}` : '/contacts',
        ...recipientFor(text(result.owner, text(input.owner))),
      }
    case 'createLead':
    case 'updateLead':
      return {
        category: 'Lead',
        title: method === 'updateLead' ? 'Lead 信息已更新' : '新增 Lead 待跟进',
        message: `${text(result.name, text(input.name, id))} · ${text(result.company, text(input.company, '待补充公司'))}`,
        route: id ? `/leads/${encodeURIComponent(id)}` : '/leads',
        ...recipientFor(text(result.owner, text(input.owner))),
      }
    case 'convertLead': {
      const opportunity = record(result.opportunity)
      const opportunityId = text(opportunity.id)
      return {
        category: 'Opportunity',
        title: 'Lead 已转为 Opportunity',
        message: `${text(opportunity.title, text(args[0]))} · ${text(opportunity.owner, text(input.owner))}`,
        route: opportunityId ? `/opportunities/${encodeURIComponent(opportunityId)}` : '/opportunities',
        ...recipientFor(text(opportunity.owner, text(input.opportunityOwner))),
      }
    }
    case 'createStrategyOpportunity':
      return {
        category: 'Opportunity',
        title: '新增 Opportunity',
        message: `${text(result.title, text(input.title, id))} · ${text(result.owner, text(input.owner))}`,
        route: id ? `/opportunities/${encodeURIComponent(id)}` : '/opportunities',
        ...recipientFor(text(result.owner, text(input.owner))),
      }
    case 'updateStrategyOpportunity':
      return {
        category: 'Opportunity',
        title: 'Opportunity 信息已更新',
        message: `${text(result.title, id)} · ${text(result.owner)}`,
        route: id ? `/opportunities/${encodeURIComponent(id)}` : '/opportunities',
        ...recipientFor(text(result.owner, text(input.owner))),
      }
    case 'requestInternalValidation':
      // The other Managers review the request, so the notice has no single recipient.
      return {
        category: 'Opportunity',
        title: '内部生产审批已申请',
        message: `${text(result.title, id)} · ${text(input.reason)}`,
        route: id ? `/opportunities/${encodeURIComponent(id)}` : '/opportunities',
      }
    case 'reviewInternalValidation': {
      const validation = record(result.internalValidation)
      const comment = text(input.comment)
      return {
        category: 'Opportunity',
        title: input.decision === 'rejected' ? '内部生产审批已驳回' : '内部生产审批已批准',
        message: comment ? `${text(result.title, id)} · ${comment}` : text(result.title, id),
        route: id ? `/opportunities/${encodeURIComponent(id)}` : '/opportunities',
        ...recipientFor(text(validation.requestedBy, text(result.owner))),
      }
    }
    case 'confirmPo': {
      const booking = record(result.liveBooking)
      const bookingId = text(booking.id)
      const owner = text(booking.owner, text(record(input.booking).owner))
      return {
        category: 'Booking',
        title: 'Booking 已确认',
        message: `${text(booking.equipment, text(result.title, id))} · ${owner}`,
        route: bookingId ? `/booking/${encodeURIComponent(bookingId)}` : '/booking',
        ...recipientFor(owner),
      }
    }
    case 'createOpportunityStakeholder':
    case 'updateOpportunityStakeholder':
      return {
        category: 'Opportunity',
        title: method === 'updateOpportunityStakeholder' ? '商机关键人已更新' : '商机新增关键人',
        message: `${text(result.name, text(input.contactId))} · ${text(result.role, text(input.role))}`,
        route: `/opportunities/${encodeURIComponent(text(args[0]))}`,
      }
    case 'createOpportunityAction':
    case 'updateOpportunityAction':
      return {
        category: 'Action',
        title: method === 'updateOpportunityAction' ? '推进 Action 已更新' : '新增推进 Action',
        message: `${text(result.title, text(input.title))} · ${text(result.owner, text(input.owner))} · 截止 ${text(result.due, text(input.due))}`,
        route: `/opportunities/${encodeURIComponent(text(args[0]))}`,
        ...recipientFor(text(result.owner, text(input.owner))),
      }
    case 'createVisit':
      return {
        category: 'Visit',
        title: '新增拜访计划',
        message: `${text(result.subject, text(input.subject, id))} · ${text(result.owner, text(input.owner))}`,
        route: nodeRoute('/visits', id),
        ...recipientFor(text(result.owner, text(input.owner))),
      }
    case 'updateVisit':
      return {
        category: 'Visit',
        title: '拜访已更新',
        message: `${text(result.subject, text(input.subject, id))} · ${text(result.owner, text(input.owner))}`,
        route: nodeRoute('/visits', id),
        ...recipientFor(text(result.owner, text(input.owner))),
      }
    case 'reviewVisit':
      return {
        category: 'Visit',
        title: '\u62dc\u8bbf\u8bb0\u5f55\u5df2\u5ba1\u6838',
        message: `${text(result.subject, id)} - ${text(result.status)}`,
        route: nodeRoute('/visits', id),
        ...recipientFor(text(result.owner)),
      }
    case 'createBooking':
    case 'updateBooking':
      return {
        category: 'Booking',
        title: method === 'createBooking' ? '新增 Confirmed Booking' : 'Booking 已更新',
        message: `${text(result.title, text(input.equipment, id))} · ${text(result.owner, text(input.owner))}`,
        route: id ? `/booking/${encodeURIComponent(id)}` : '/booking',
        ...recipientFor(text(result.owner, text(input.owner))),
      }
    case 'createDemoRequest':
    case 'updateDemoRequest':
      return {
        category: 'Demo',
        title: method === 'createDemoRequest' ? '新增 Demo 需求' : 'Demo Request 已更新',
        message: `${text(result.title, id)} · ${text(result.status)}`,
        route: id ? `/demo-workflow/${encodeURIComponent(id)}?tab=information` : '/demo-workflow',
        ...recipientFor(text(result.engineerOwner, text(result.salesOwner))),
      }
    case 'transitionDemoRequest': {
      const request = record(result.request)
      const requestId = text(request.id, text(args[0]))
      return {
        category: 'Demo',
        title: `Demo Request 推进至 ${text(request.status, text(input.type))}`,
        message: `${text(request.title, requestId)} · ${text(request.engineerOwner, text(request.salesOwner))}`,
        route: requestId ? `/demo-workflow/${encodeURIComponent(requestId)}?tab=information` : '/demo-workflow',
        ...recipientFor(text(request.engineerOwner, text(request.salesOwner))),
      }
    }
    case 'updateEvaluationStatus':
      return {
        category: 'Evaluation',
        title: `Demo Test 推进至 ${text(result.status, text(input.status))}`,
        message: `${text(result.title, id)} · ${text(result.owner)}`,
        route: id ? `/demo-workflow/${encodeURIComponent(id)}?tab=information` : '/demo-workflow',
        ...recipientFor(result.owner),
      }
    case 'convertBookingToInstalledTool': {
      const installedTool = record(result.installedTool)
      const installedToolId = text(installedTool.id)
      return {
        category: 'InstalledTool',
        title: '\u8bbe\u5907\u5df2\u5206\u914d\u7ed9\u5de5\u7a0b\u5e08',
        message: `${text(installedTool.serial, installedToolId)} - ${text(installedTool.engineerOwner, text(input.engineerOwner))}`,
        route: nodeRoute('/installed-tools', installedToolId),
        ...recipientFor(text(installedTool.engineerOwner, text(input.engineerOwner))),
      }
    }
    case 'updateInstalledTool':
      return {
        category: 'InstalledTool',
        title: '\u8bbe\u5907\u8d1f\u8d23\u4eba\u5df2\u66f4\u65b0',
        message: `${text(result.serial, id)} - ${text(result.engineerOwner, text(input.engineerOwner))}`,
        route: nodeRoute('/installed-tools', id),
        ...recipientFor(text(result.engineerOwner, text(input.engineerOwner))),
      }
    case 'addEvaluationRun':
    case 'updateEvaluationRun':
    case 'cancelEvaluationRun':
      return {
        category: 'Evaluation',
        title: 'Test Run 已更新',
        message: `${text(result.title, id)} · Run ${text(input.id)}`,
        route: nodeRoute('/evaluations', id),
      }
    case 'setEvaluationTestRunDeadline':
      return {
        category: 'Evaluation',
        title: 'Test Run 截止日期已更新',
        message: `${text(result.title, id)} · 截止 ${text(input.testRunDeadline)}`,
        route: nodeRoute('/evaluations', id),
      }
    case 'releaseDemoTestReport':
      return {
        category: 'Evaluation',
        title: 'Demo Test 报告已发布',
        message: `${text(result.fileName, id)} · Version ${String(result.version ?? '')}`,
        route: nodeRoute('/evaluations', text(result.evaluationId, text(args[0]))),
      }
    default:
      return null
  }
}

export type NotificationDelivery = 'local' | 'server'

export function createNotifyingApi(
  api: CrmApi,
  sink: NotificationSink,
  delivery: NotificationDelivery = 'local',
): CrmApi {
  if (delivery === 'server') return api
  if ((api as CrmApi & { [NOTIFYING_API]?: boolean })[NOTIFYING_API]) return api

  return new Proxy(api, {
    get(target, property, receiver) {
      if (property === NOTIFYING_API) return true
      const value = Reflect.get(target, property, receiver)
      if (typeof property !== 'string' || typeof value !== 'function') return value

      return async (...args: unknown[]) => {
        const result = await value.apply(target, args)
        const message = notificationFor(property as keyof CrmApi, args, record(result).data)
        if (message) sink(message)
        return result
      }
    },
  }) as CrmApi
}
