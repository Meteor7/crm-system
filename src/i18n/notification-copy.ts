import type { NotificationInput } from '@/types/notifications'
import type { Locale } from './index'
import { salesEnumLabel } from '@/features/shared/sales-i18n'

const localTitles: Partial<Record<NotificationInput['category'], Record<string, string>>> = {
  "Account": {
    "新增客户档案": "New account",
    "客户档案已更新": "Account updated"
  },
  "Contact": {
    "联系人已更新": "Contact updated",
    "新增联系人": "New contact"
  },
  "Lead": {
    "Lead 信息已更新": "Lead updated",
    "新增 Lead 待跟进": "New lead to follow up"
  },
  "Opportunity": {
    "Lead 已转为 Opportunity": "Lead converted to opportunity",
    "新增 Opportunity": "New opportunity",
    "Opportunity 信息已更新": "Opportunity updated",
    "商机关键人已更新": "Opportunity stakeholder updated",
    "商机新增关键人": "New opportunity stakeholder",
    "内部生产审批已申请": "Internal validation requested",
    "内部生产审批已批准": "Internal validation approved",
    "内部生产审批已驳回": "Internal validation rejected"
  },
  "Action": {
    "推进 Action 已更新": "Opportunity action updated",
    "新增推进 Action": "New opportunity action"
  },
  "Visit": {
    "新增拜访计划": "New visit planned",
    "拜访记录已审核": "Visit record reviewed"
  },
  "Booking": {
    "新增 Confirmed Booking": "New confirmed booking",
    "Booking 已更新": "Booking updated",
    "Booking 已确认": "Booking confirmed"
  },
  "Demo": {
    "新增 Demo 需求": "New Demo Request",
    "Demo Request 已更新": "Demo Request updated"
  },
  "InstalledTool": {
    "设备已分配给工程师": "Equipment assigned to engineer",
    "设备负责人已更新": "Equipment owner updated"
  },
  "Evaluation": {
    "Test Run 已更新": "Test run updated",
    "Test Run 截止日期已更新": "Test run deadline updated",
    "Demo Test 报告已发布": "Demo test report published"
  },
  "Requirement": {
    "需求待跟进": "Requirement to follow up"
  }
}

// Known generated notification formats only; customer names and message bodies remain data.
export function notificationCopy(notification: NotificationInput, locale: Locale) {
  let { title, message } = notification
  if (locale === 'zh-CN') return { title, message }
  const reminder = /^(Booking|Demo 客户期望|Test Run) DDL 提醒 · 剩余 (7|15) 天$/.exec(title)
  const reminderCategories: Record<string, string> = { Booking: 'Booking', 'Demo 客户期望': 'Demo', 'Test Run': 'Evaluation' }
  if (reminder && notification.category === reminderCategories[reminder[1]]) {
    const label = { Booking: 'Booking', 'Demo 客户期望': 'Demo customer expected date', 'Test Run': 'Test run' }[reminder[1]]!
    const suffix = ` 的 ${reminder[1]} DDL 为 `
    const split = message.lastIndexOf(suffix)
    const ending = new RegExp(`^(\\d{4}-\\d{2}-\\d{2})，距离截止还有 ${reminder[2]} 天，请及时跟进。$`).exec(message.slice(split + suffix.length))
    if (split > 0 && ending) {
      title = `${label} deadline reminder · ${reminder[2]} days remaining`
      message = `${message.slice(0, split)}: ${label} deadline is ${ending[1]}; ${reminder[2]} days remain. Please follow up.`
    }
    return { title, message }
  }
  // Existing server DDL rows have no kind, so both complete generated formats are required above.
  if (!notification.generatedLocally) return { title, message }
  const translated = localTitles[notification.category]?.[title]
  if (translated) {
    if (notification.category === 'Action' || title === 'Test Run 截止日期已更新') message = message.replace(/ · 截止 (?=\d{4}-\d{2}-\d{2}$)/, ' · Due ')
    if (notification.category === 'Lead') message = message.replace(/ · 待补充公司$/, ' · Company not provided')
    return { title: translated, message }
  }
  if (notification.category === 'Demo') {
    const mention = /^(.+) @你确认 Demo$/.exec(title)
    if (mention) title = `${mention[1] === '项目成员' ? 'A project member' : mention[1]} mentioned you on a Demo`
  }
  // Opportunity stages move only through workflow actions, which carry their own titles above.
  const moved = /^(Demo Request|Demo Test) 推进至 (.+)$/.exec(title)
  const categories: Record<string, string> = { 'Demo Request': 'Demo', 'Demo Test': 'Evaluation' }
  if (moved && notification.category === categories[moved[1]]) title = `${moved[1]} moved to ${salesEnumLabel(moved[2], locale)}`
  return { title, message }
}
