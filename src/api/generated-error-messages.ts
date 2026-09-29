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
    'The currency of a confirmed order cannot change through an ordinary edit.': ['The currency of a confirmed order cannot change through an ordinary edit.', '已确认订单的币种不能通过普通编辑修改。'],
    'Only a Confirmed or Completed Booking has an actual PO date.': ['Only a Confirmed or Completed Booking has an actual PO date.', '只有已确认或已完成的 Booking 才有实际 PO 日期。'],
    'Only a Confirmed or Completed Booking has a CNY amount to record.': ['Only a Confirmed or Completed Booking has an amount in CNY to record.', '只有已确认或已完成的订单需要补录人民币金额。'],
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
    'amountCny is required.': ['Enter the amount in CNY.', '请填写人民币金额。'],
    'amountCny is unchanged.': ['The amount in CNY has not changed.', '人民币金额没有变化。'],
    'A CNY Booking uses its amount.': ['A CNY Booking uses its own amount; no separate amount in CNY is needed.', '人民币订单直接使用订单金额，不需要另填人民币金额。'],
    'A reason is required to correct the CNY amount.': ['Enter a reason to correct the amount in CNY.', '更正人民币金额必须填写原因。'],
    'amountCny must be positive with at most two decimal places.': ['The amount in CNY must be greater than 0, with at most two decimal places.', '人民币金额必须大于 0，最多两位小数。'],
    'opportunityAmountCny is required.': ['Enter the amount in CNY.', '请填写人民币金额。'],
    'opportunityAmountCny must be positive with at most two decimal places.': ['The amount in CNY must be greater than 0, with at most two decimal places.', '人民币金额必须大于 0，最多两位小数。'],
    'actualPoDate is required.': ['Enter the actual PO date.', '请填写实际 PO 日期。'],
    'actualPoDate cannot be in the future.': ['The actual PO date cannot be later than today.', '实际 PO 日期不能晚于今天。'],
    'actualPoDate is unchanged.': ['The actual PO date has not changed.', '实际 PO 日期没有变化。'],
    'A reason is required to correct the actual PO date.': ['Enter a reason to correct the actual PO date.', '更正实际 PO 日期必须填写原因。'],
    "The actual PO date changes only through a Manager's correction.": ["The actual PO date changes only through a Manager's correction.", '实际 PO 日期只能由经理更正。'],
    "The CNY amount changes only through a Manager's correction.": ["The amount in CNY changes only through a Manager's correction.", '人民币金额只能由经理更正。'],
    'region must be an English region name.': ['Enter a custom region in English, for example Northeast China.', '自定义区域请用英文填写，例如 Northeast China。'],
    'subRegion is not a known region.': ['Choose one of the account regions.', '请选择已有的客户区域。'],
    'Confirmed order currency is fixed': ['The currency of a confirmed order is fixed.', '已确认订单的币种不可修改。'],
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
    'Only a Manager can fill in or correct the actual PO date.': ['Only a Manager can fill in or correct the actual PO date.', '只有经理可以补录或更正实际 PO 日期。'],
    'Only a Manager can fill in or correct the CNY amount.': ['Only a Manager can fill in or correct the amount in CNY.', '只有经理可以补录或更正人民币金额。'],
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
