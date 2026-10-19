import type { Locale } from '@/i18n'

type LocalizedPair = Record<Locale, string>

const labels: Record<string, LocalizedPair> = {
  'Production': { 'zh-CN': '生产中', 'en-US': 'Production' },
  'Upgrade Due': { 'zh-CN': '待升级', 'en-US': 'Upgrade due' },
  'Installation': { 'zh-CN': '安装中', 'en-US': 'Installation' },
  'Retired': { 'zh-CN': '已退役', 'en-US': 'Retired' },
  'Decommissioned': { 'zh-CN': '已停用', 'en-US': 'Decommissioned' },
  'Critical': { 'zh-CN': '紧急', 'en-US': 'Critical' },
  'Planned': { 'zh-CN': '待拜访', 'en-US': 'To visit' },
  'Visited': { 'zh-CN': '已拜访', 'en-US': 'Visited' },
  'Minutes Submitted': { 'zh-CN': '待经理审核', 'en-US': 'Awaiting manager review' },
  'Manager Reviewed': { 'zh-CN': '拜访完成', 'en-US': 'Visit completed' },
  'Requested': { 'zh-CN': '已申请', 'en-US': 'Requested' },
  'Scope Confirmed': { 'zh-CN': '范围已确认', 'en-US': 'Scope confirmed' },
  'Sample Received': { 'zh-CN': '样品已收到', 'en-US': 'Sample received' },
  'Scheduled': { 'zh-CN': '已排期', 'en-US': 'Scheduled' },
  'Testing': { 'zh-CN': '测试中', 'en-US': 'Testing' },
  'Analysis': { 'zh-CN': '分析中', 'en-US': 'Analysis' },
  'Superseded': { 'zh-CN': '已替代', 'en-US': 'Superseded' },
  Active: { 'zh-CN': '启用', 'en-US': 'Active' },
  'Left Company': { 'zh-CN': '已演示员工166', 'en-US': 'Left company' },
  Archived: { 'zh-CN': '已归档', 'en-US': 'Archived' },
  Strong: { 'zh-CN': '强', 'en-US': 'Strong' },
  Developing: { 'zh-CN': '发展中', 'en-US': 'Developing' },
  Weak: { 'zh-CN': '弱', 'en-US': 'Weak' },
  'Needs Review': { 'zh-CN': '需检查', 'en-US': 'Needs review' },
  New: { 'zh-CN': '新建', 'en-US': 'New' },
  Working: { 'zh-CN': '跟进中', 'en-US': 'Working' },
  Qualified: { 'zh-CN': '已合格', 'en-US': 'Qualified' },
  Nurturing: { 'zh-CN': '培育中', 'en-US': 'Nurturing' },
  Disqualified: { 'zh-CN': '不合格', 'en-US': 'Disqualified' },
  Converted: { 'zh-CN': '已转换', 'en-US': 'Converted' },
  Won: { 'zh-CN': '已赢单', 'en-US': 'Won' },
  Lost: { 'zh-CN': '已输单', 'en-US': 'Lost' },
  Draft: { 'zh-CN': '草稿', 'en-US': 'Draft' },
  'Engineer Review': { 'zh-CN': '工程师审核', 'en-US': 'Engineer review' },
  'Engineer Returned': { 'zh-CN': '工程师退回', 'en-US': 'Engineer returned' },
  'Manager Approval': { 'zh-CN': '管理者审批', 'en-US': 'Manager approval' },
  'Sales Revision': { 'zh-CN': '销售修订', 'en-US': 'Sales revision' },
  Approved: { 'zh-CN': '已批准', 'en-US': 'Approved' },
  'Manager Rejected': { 'zh-CN': '管理者驳回', 'en-US': 'Manager rejected' },
  Returned: { 'zh-CN': '已退回', 'en-US': 'Returned' },
  Accepted: { 'zh-CN': '已接受', 'en-US': 'Accepted' },
  Rejected: { 'zh-CN': '已拒绝', 'en-US': 'Rejected' },
  Expired: { 'zh-CN': '已过期', 'en-US': 'Expired' },
  Published: { 'zh-CN': '已发布', 'en-US': 'Published' },
  'Test Preparation': { 'zh-CN': '测试准备', 'en-US': 'Test preparation' },
  'Test Execution': { 'zh-CN': '测试执行', 'en-US': 'Test execution' },
  'Internal Review': { 'zh-CN': '内部审核', 'en-US': 'Internal review' },
  'Customer Review': { 'zh-CN': '客户评审', 'en-US': 'Customer review' },
  Website: { 'zh-CN': '网站', 'en-US': 'Website' },
  'Trade Show': { 'zh-CN': '展会', 'en-US': 'Trade show' },
  'Partner Referral': { 'zh-CN': '合作伙伴推荐', 'en-US': 'Partner referral' },
  Outbound: { 'zh-CN': '主动开发', 'en-US': 'Outbound' },
  'Customer Referral': { 'zh-CN': '客户推荐', 'en-US': 'Customer referral' },
  Other: { 'zh-CN': '其他', 'en-US': 'Other' },
  Pipeline: { 'zh-CN': 'Pipeline', 'en-US': 'Pipeline' },
  'Best Case': { 'zh-CN': '最佳情况', 'en-US': 'Best case' },
  Commit: { 'zh-CN': '承诺', 'en-US': 'Commit' },
  Closed: { 'zh-CN': '已关闭', 'en-US': 'Closed' },
  'New Equipment': { 'zh-CN': '新设备', 'en-US': 'New equipment' },
  'Repeat Order': { 'zh-CN': '重复订单', 'en-US': 'Repeat order' },
  Service: { 'zh-CN': '服务', 'en-US': 'Service' },
  Device: { 'zh-CN': '设备', 'en-US': 'Device' },
  Equipment: { 'zh-CN': '设备', 'en-US': 'Equipment' },
  Frontend: { 'zh-CN': '前端', 'en-US': 'Frontend' },
  'Advanced Packaging': { 'zh-CN': '先进封装', 'en-US': 'Advanced packaging' },
  Software: { 'zh-CN': '软件', 'en-US': 'Software' },
  Firmware: { 'zh-CN': '固件', 'en-US': 'Firmware' },
  Configuration: { 'zh-CN': '配置', 'en-US': 'Configuration' },
  Opportunity: { 'zh-CN': 'Opportunity', 'en-US': 'Opportunity' },
  Booking: { 'zh-CN': 'Booking', 'en-US': 'Booking' },
  'Demo Request': { 'zh-CN': 'Demo Request', 'en-US': 'Demo Request' },
  Upsell: { 'zh-CN': '客户增购', 'en-US': 'Upsell' },
  'Existing Customer Upsell': { 'zh-CN': '现有客户增购', 'en-US': 'Existing customer upsell' },
  Pending: { 'zh-CN': '待确认', 'en-US': 'Pending' },
  Confirmed: { 'zh-CN': '已确认', 'en-US': 'Confirmed' },
  Completed: { 'zh-CN': '已完成', 'en-US': 'Completed' },
  Cancelled: { 'zh-CN': '已取消', 'en-US': 'Cancelled' },
  'On-site': { 'zh-CN': '现场拜访', 'en-US': 'On-site' },
  Video: { 'zh-CN': '视频会议', 'en-US': 'Video' },
  Phone: { 'zh-CN': '电话', 'en-US': 'Phone' },
  Open: { 'zh-CN': '进行中', 'en-US': 'Open' },
  'In Progress': { 'zh-CN': '进行中', 'en-US': 'In progress' },
  Blocked: { 'zh-CN': '阻塞', 'en-US': 'Blocked' },
  Rescheduled: { 'zh-CN': '已改期', 'en-US': 'Rescheduled' },
  Done: { 'zh-CN': '已完成', 'en-US': 'Done' },
  'Decision Maker': { 'zh-CN': '决策人', 'en-US': 'Decision maker' },
  'Economic Buyer': { 'zh-CN': '经济决策人', 'en-US': 'Economic buyer' },
  'Technical Buyer': { 'zh-CN': '技术决策人', 'en-US': 'Technical buyer' },
  'User Buyer': { 'zh-CN': '使用方决策人', 'en-US': 'User buyer' },
  Coach: { 'zh-CN': '教练', 'en-US': 'Coach' },
  Procurement: { 'zh-CN': '采购', 'en-US': 'Procurement' },
  Influencer: { 'zh-CN': '影响者', 'en-US': 'Influencer' },
  Champion: { 'zh-CN': '支持者', 'en-US': 'Champion' },
  'Technical Champion': { 'zh-CN': '技术支持者', 'en-US': 'Technical champion' },
  'Primary Contact': { 'zh-CN': '主联系人', 'en-US': 'Primary contact' },
  High: { 'zh-CN': '高', 'en-US': 'High' },
  Medium: { 'zh-CN': '中', 'en-US': 'Medium' },
  Low: { 'zh-CN': '低', 'en-US': 'Low' },
  Support: { 'zh-CN': '支持', 'en-US': 'Support' },
  Neutral: { 'zh-CN': '中立', 'en-US': 'Neutral' },
  Against: { 'zh-CN': '反对', 'en-US': 'Against' },
  Growth: { 'zh-CN': '增长型', 'en-US': 'Growth' },
  Trouble: { 'zh-CN': '困扰型', 'en-US': 'Trouble' },
  'Even Keel': { 'zh-CN': '平稳型', 'en-US': 'Even Keel' },
  Overconfident: { 'zh-CN': '过度自信型', 'en-US': 'Overconfident' },
}

const contactStatusLabels: Record<string, LocalizedPair> = {
  Active: { 'zh-CN': '在职', 'en-US': 'Active' },
  'Left Company': { 'zh-CN': '已演示员工166', 'en-US': 'Left company' },
  Archived: { 'zh-CN': '已归档', 'en-US': 'Archived' },
}

const meetingRecordParseLabels: Record<string, LocalizedPair> = {
  Parsed: { 'zh-CN': '已解析', 'en-US': 'Parsed' },
  NeedsManualReview: { 'zh-CN': '待人工检查', 'en-US': 'Needs manual review' },
  ArchiveOnly: { 'zh-CN': '仅归档', 'en-US': 'Archive only' },
  Failed: { 'zh-CN': '解析失败', 'en-US': 'Parsing failed' },
}

export function salesEnumLabel(value: string, currentLocale: Locale) {
  return labels[value]?.[currentLocale] ?? value
}

export function contactStatusLabel(value: string, currentLocale: Locale) {
  return contactStatusLabels[value]?.[currentLocale] ?? salesEnumLabel(value, currentLocale)
}

export function meetingRecordParseLabel(value: string, currentLocale: Locale) {
  return meetingRecordParseLabels[value]?.[currentLocale] ?? value
}

export function opportunityActionLabel(value: string, currentLocale: Locale) {
  return value === 'Open' ? (currentLocale === 'en-US' ? 'Not started' : '未开始') : salesEnumLabel(value, currentLocale)
}

export function salesUnits(currentLocale: Locale) {
  return currentLocale === 'en-US' ? 'units / items' : '台 / 项'
}

export function recordTypeLabel(value: string, currentLocale: Locale) {
  const chinese: Record<string, string> = { Account: '客户', Contact: '联系人', Opportunity: '商机', Deal: '商机', Booking: '订单', 'Demo Request': 'Demo 申请', Requirement: '需求', Visit: '拜访', Evaluation: '评估', Contract: '演示员工116' }
  return currentLocale === 'zh-CN' ? chinese[value] ?? value : value
}

export function participantRoleLabel(value: string, currentLocale: Locale) {
  const chinese: Record<string, string> = { Sales: '销售', Engineer: '工程师', Manager: '经理', 'Sales 提交': '销售提交', 'FAE Review': '工程评估', 'Manager Approval': '经理审批', 'Boss Approval': '经理审批', 'Internal Review': '内部评审', 'Customer Review': '客户评审' }
  return currentLocale === 'zh-CN' ? chinese[value] ?? value : value === 'Sales 提交' ? 'Sales submission' : value
}
