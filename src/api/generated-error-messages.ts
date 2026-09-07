import { localeMessage } from '@/i18n'
import { opportunityStageLabel } from '@/features/shared/sales-i18n'
import { STRATEGY_OPPORTUNITY_STAGES } from '@/types/workspaces'

// Recognize fixed service-generated messages; arbitrary backend diagnostics remain untouched.
export function generatedErrorMessage(code: string, message: string) {
  if (code === 'INVALID_TRANSITION') {
    if (message === 'RFQ can only be created when the Opportunity is in 设备规格确认.') return localeMessage('RFQ can only be created when the Opportunity is in Equipment specification.', '只有设备规格确认阶段的商机可以创建 RFQ。')
    if (message === 'Demo Request can only be created for an Opportunity in 需求发现 or Wafer Demo确认.') return localeMessage('Demo Request can only be created for an Opportunity in Discovery or Wafer demo confirmed.', '只有需求发现或 Wafer Demo确认阶段的商机可以创建 Demo Request。')
    const transition = /^Opportunity cannot move from (.+) to (.+)\.$/.exec(message)
    const workflow = /^Opportunity must be in (.+) before workflow completion can move it to (.+)\.$/.exec(message)
    const match = transition ?? workflow
    if (match && [match[1], match[2]].every((stage) => (STRATEGY_OPPORTUNITY_STAGES as readonly string[]).includes(stage))) {
      const [from, to] = [match[1], match[2]]
      return transition
        ? localeMessage(`Opportunity cannot move from ${opportunityStageLabel(from, 'en-US')} to ${opportunityStageLabel(to, 'en-US')}.`, `商机不能从${opportunityStageLabel(from, 'zh-CN')}推进至${opportunityStageLabel(to, 'zh-CN')}。`)
        : localeMessage(`Opportunity must be in ${opportunityStageLabel(from, 'en-US')} before workflow completion can move it to ${opportunityStageLabel(to, 'en-US')}.`, `商机必须处于${opportunityStageLabel(from, 'zh-CN')}阶段，才能在流程完成后推进至${opportunityStageLabel(to, 'zh-CN')}。`)
    }
  }
  if (code === 'CONFLICT' && message === 'Cancel the active Demo Request before rolling the Opportunity back to 需求发现.') return localeMessage('Cancel the active Demo Request before rolling the Opportunity back to Discovery.', '请先取消进行中的 Demo Request，再将商机退回需求发现阶段。')
  return undefined
}
