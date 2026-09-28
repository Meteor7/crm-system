import { localeMessage } from '@/i18n'
import { isOpportunityStage, opportunityStageLabel } from '@/domain/opportunity-stages'

type CopyPair = readonly [english: string, chinese: string]

// Fixed service-generated messages, keyed by the normalized error code. Arbitrary backend diagnostics remain untouched.
const FIXED_MESSAGES: Partial<Record<string, Record<string, CopyPair>>> = {
  INVALID_TRANSITION: {
    'RFQ can only be created when the Opportunity is at customer_budget_approved.': ['RFQ can only be created when the Opportunity is at Customer budget approved.', '只有处于客户预算批准阶段的商机可以创建 RFQ。'],
    'Demo Request can only be created for an Opportunity in qualified_opportunity or demo_done.': ['Demo Request can only be created for an Opportunity at Qualified opportunity or Demo done.', '只有处于合格商机或 Demo 完成阶段的商机可以创建 Demo Request。'],
    'New Opportunity must start at qualified_opportunity.': ['A new Opportunity must start at Qualified opportunity.', '新建商机必须从合格商机阶段开始。'],
    'Opportunity stages change only through their workflow actions.': ['Opportunity stages change only through their workflow actions.', '商机阶段只能通过对应的流程操作变更。'],
    'The probability level is frozen once the PO is received or the Opportunity is lost.': ['The success probability is frozen once the PO is received or the Opportunity is lost.', '收到 PO 或丢单后，成功概率不能再修改。'],
    'Internal validation is only available for equipment Opportunities.': ['Internal validation is only available for equipment Opportunities.', '只有设备类商机可以申请内部生产审批。'],
    'The internal validation was already decided or cancelled.': ['The internal validation was already decided or cancelled.', '该内部生产审批申请已审批或已撤销。'],
    'Rollback target must be an earlier stage.': ['The rollback target must be an earlier stage.', '回退目标必须早于当前阶段。'],
    'internal_validation requires the Booking created by an approved internal validation.': ['Rolling back to Internal validation requires the Booking created by an approved internal validation.', '只有当前 Booking 来自已批准的内部生产审批时，才能回退到内部生产审批阶段。'],
    'A lost Opportunity cannot be advanced by workflow completion.': ['A lost Opportunity cannot be advanced by workflow completion.', '已丢单的商机不能由流程完成自动推进。'],
    'Source Opportunity must belong to the Account.': ['The source Opportunity must belong to the Account.', '来源商机必须属于该客户。'],
    'Opportunity Bookings are created by confirming the PO or approving an internal validation.': ['Opportunity Bookings are created by confirming the PO or approving an internal validation.', '商机来源的 Booking 只能通过确认收到 PO 或批准内部生产审批生成。'],
    'Account, source, Opportunity and type of an Opportunity Booking cannot change.': ['The account, source, Opportunity, and type of an Opportunity Booking cannot change.', '商机来源 Booking 的客户、来源、商机和类型不能修改。'],
    "A Booking's source cannot change.": ["A Booking's source cannot change.", 'Booking 的来源不能修改。'],
    'An Opportunity Booking can only be changed to Cancelled.': ['An Opportunity Booking can only be changed to Cancelled.', '商机来源的 Booking 只能改为已取消。'],
  },
  VALIDATION_ERROR: {
    'Lost Reason is required for a lost Opportunity.': ['A lost reason is required for a lost Opportunity.', '丢单商机必须填写丢单原因。'],
    'probabilityLevel cannot be cleared once the demo is done.': ['The success probability cannot be cleared once the demo is done.', 'Demo 完成后不能清空成功概率。'],
    'Confirm the customer need and the budget owner before creating the Opportunity.': ['Confirm the customer need and the budget owner before creating the Opportunity.', '请先确认客户需求与预算负责人，再创建商机。'],
    'Set the probability level before this step.': ['Set the success probability before this step.', '请先设置成功概率，再执行此操作。'],
    'approvedOn is required.': ['Enter the budget approval date.', '请填写预算批准日期。'],
    'approvedOn cannot be in the future.': ['The budget approval date cannot be in the future.', '预算批准日期不能晚于今天。'],
    'expectedPoDate is required.': ['Enter the expected PO date.', '请填写预计 PO 日期。'],
    'A comment is required to reject an internal validation.': ['A comment is required to reject an internal validation.', '驳回内部生产审批时必须填写审批意见。'],
    'booking is required.': ['Enter the Booking details.', '请填写 Booking 信息。'],
    'Opportunity Booking requires a source Opportunity.': ['An Opportunity Booking requires a source Opportunity.', '商机来源的 Booking 必须关联来源商机。'],
  },
  CONFLICT: {
    'Account and sale type cannot change while the Opportunity has a live Booking.': ['The account and sale type cannot change while the Opportunity has a live Booking.', '商机存在未取消的 Booking 时，不能修改客户或销售类型。'],
    'The Opportunity already has a pending internal validation.': ['The Opportunity already has a pending internal validation.', '该商机已有待审批的内部生产审批申请。'],
    'No other active Manager can review this internal validation.': ['No other active Manager can review this internal validation.', '没有其他在职 Manager 可以审批该内部生产审批申请。'],
    'The Opportunity already has a live Booking.': ['The Opportunity already has a live Booking.', '该商机已有未取消的 Booking。'],
    'Cancel the Booking before marking the Opportunity lost.': ['Cancel the Booking before marking the Opportunity lost.', '请先取消 Booking，再标记丢单。'],
    'A completed Booking blocks stage rollback.': ['A completed Booking blocks stage rollback.', 'Booking 已完成，不能回退商机阶段。'],
    'Cancel the Booking before rolling the Opportunity back.': ['Cancel the Booking before rolling the Opportunity back.', '请先取消 Booking，再回退商机阶段。'],
  },
  PERMISSION_DENIED: {
    'Only the Opportunity owner can set the probability level.': ['Only the Opportunity owner can set the success probability.', '只有商机负责人可以设置成功概率。'],
    'Managers cannot review their own internal validation.': ['Managers cannot review their own internal validation.', 'Manager 不能审批自己提交的内部生产审批申请。'],
  },
  NOT_FOUND: {
    'Internal validation was not found.': ['Internal validation was not found.', '未找到该内部生产审批申请。'],
  },
}

// "<action> is not available at <stage>." names the workflow action that the current stage does not allow.
const UNAVAILABLE_ACTIONS: Record<string, CopyPair> = {
  'Budget approval': ['Budget approval', '确认客户预算'],
  'Internal validation': ['Internal validation', '申请内部生产审批'],
  'Internal validation review': ['Internal validation review', '审批内部生产申请'],
  'PO confirmation': ['PO confirmation', '确认收到 PO'],
  'Marking the Opportunity lost': ['Marking the Opportunity lost', '标记丢单'],
}

const stageLabels = (stage: string) => [opportunityStageLabel(stage, 'en-US'), opportunityStageLabel(stage, 'zh-CN')] as const

export function generatedErrorMessage(code: string, message: string) {
  const fixed = FIXED_MESSAGES[code]?.[message]
  if (fixed) return localeMessage(fixed[0], fixed[1])
  if (code === 'INVALID_TRANSITION') {
    const unavailable = /^(.+) is not available at ([a-z_]+)\.$/.exec(message)
    const action = unavailable ? UNAVAILABLE_ACTIONS[unavailable[1]] : undefined
    if (unavailable && action && isOpportunityStage(unavailable[2])) {
      const [english, chinese] = stageLabels(unavailable[2])
      return localeMessage(`${action[0]} is not available at ${english}.`, `当前阶段为${chinese}，不能${action[1]}。`)
    }
    const reopen = /^A lost Opportunity can only reopen at or below ([a-z_]+)\.$/.exec(message)
    if (reopen && isOpportunityStage(reopen[1])) {
      const [english, chinese] = stageLabels(reopen[1])
      return localeMessage(`A lost Opportunity can only reopen at ${english} or an earlier stage.`, `丢单商机只能重新打开到${chinese}或更早的阶段。`)
    }
  }
  if (code === 'CONFLICT') {
    const workflow = /^Opportunity must be at ([a-z_]+) before workflow completion can move it to ([a-z_]+)\.$/.exec(message)
    if (workflow && isOpportunityStage(workflow[1]) && isOpportunityStage(workflow[2])) {
      const [fromEnglish, fromChinese] = stageLabels(workflow[1])
      const [toEnglish, toChinese] = stageLabels(workflow[2])
      return localeMessage(
        `The Opportunity must be at ${fromEnglish} before workflow completion can move it to ${toEnglish}.`,
        `商机必须处于${fromChinese}阶段，才能在流程完成后推进至${toChinese}。`,
      )
    }
  }
  return undefined
}
