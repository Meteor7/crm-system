import type { Account360Dto, ActionDto } from '@/types/crm'
import { formatKnownTotals, formatMoney, moneyByCurrency } from '@/domain/money'
import { personnelDisplayName } from '@/demo/personnel'
import type { Locale } from '@/i18n'
import { bookingTitle } from '@/features/shared/system-labels'
import { salesEnumLabel } from '@/features/shared/sales-i18n'
import { regionLabel } from '@/domain/regions'
import { opportunityProbabilityLevelLabel } from '@/domain/opportunity-probability'
import { isOpenOpportunityStage } from '@/domain/opportunity-stages'
import { isTerminatedDemo } from '@/domain/evaluations'


// These labels are authored by this report builder; business cell values never pass through this helper.
const englishReportText: Record<string, string> = {
  "客户全貌 Overview": "Overview",
  "商机 Opportunities": "Opportunities",
  "需求与行动 Actions": "Actions",
  "关键人与拜访 People": "People",
  "Demo与演示员工116 Demo": "Demo and contracts",
  "当前客户没有 Economic Buyer 记录": "No economic buyer has been identified for this account.",
  "当前规则未识别到异常": "No issues were identified by the current rules.",
  "确认法务与签署计划": "Confirm the legal review and signing plan.",
  "继续维护客户数据": "Continue maintaining account data.",
  "识别预算最终批准人与签字链": "Identify the final budget approver and signing chain.",
  "下一步行动 / Next Actions（按截止日期排序 / Sorted by Due Date）": "Next Actions (Sorted by Due Date)"
}
function reportText(value: string, locale: Locale) {
  return locale === 'en-US' ? englishReportText[value] ?? value.split(' / ').slice(1).join(' / ') : value
}


function reportEnum(value: string, locale: Locale) {
  const english: Record<string, string> = { '稳健': 'Stable', '关注': 'Watch', '高风险': 'High risk', '需求识别': 'Need identified', '技术确认': 'Technical confirmation', 'Demo验证': 'Demo validation', '预算审批': 'Budget approval', '采购计划': 'Procurement planning', '已确认': 'Confirmed' }
  return locale === 'en-US' ? english[value] ?? salesEnumLabel(value, locale) : value
}

export type CustomerReportValue = string | number
export interface CustomerReportCell { v: CustomerReportValue; s: number }
export interface CustomerReportColumn { width: number; wrapText?: boolean }
export interface CustomerWorksheetSpec { name: string; columns: CustomerReportColumn[]; rows: CustomerReportCell[][]; merges: string[]; freezeRows: number }
export interface CustomerWorkbookSpec { fileName: string; sheets: CustomerWorksheetSpec[] }

const cell = (v: CustomerReportValue | null | undefined, s = 5): CustomerReportCell => ({ v: v === '' || v == null ? '—' : v, s })
const dateCell = (value: string | null | undefined): CustomerReportCell => {
  if (!value) return cell('—')
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return cell(value)
  const serial = (Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])) - Date.UTC(1899, 11, 30)) / 86_400_000
  return cell(serial, 12)
}
const blank = (): CustomerReportCell[] => []
const header = (values: CustomerReportValue[]) => values.map((value) => cell(value, 4))
const columns = (values: number[]): CustomerReportColumn[] => values.map((width) => ({ width }))
const confidence = (intent: number) => intent >= 70 ? 'High' : intent >= 50 ? 'Medium' : 'Low'
const open = (stage: string) => isOpenOpportunityStage(stage)
const dueState = (due: string, reportDate: string, locale: Locale) => !due ? reportText('待确认 / To Confirm', locale) : due < reportDate ? reportText('已逾期 / Overdue', locale) : due === reportDate ? reportText('今日到期 / Due Today', locale) : reportText('待完成 / Open', locale)

// A terminated Demo keeps the stored Rejected status: its row names the termination and the
// reason, and a customer acceptance still Pending reads as not reviewed. Other rows are unchanged.
const evaluationStatusCell = (item: Account360Dto['evaluations'][number], locale: Locale) => isTerminatedDemo(item)
  ? cell(`${reportText('已终止 / Terminated', locale)} · ${reportText('原因 / Reason', locale)}: ${item.terminationReason?.trim()}`, 14)
  : cell(reportEnum(item.status, locale))
const evaluationAcceptanceCell = (item: Account360Dto['evaluations'][number], locale: Locale) => isTerminatedDemo(item) && item.acceptance === 'Pending'
  ? cell(reportText('未评审 / Not reviewed', locale))
  : cell(item.acceptance)

interface ReportAction { type: string; source: string; cn: string; en: string; owner: string; due: string; priority: string; status: string }

function reportActions(detail: Account360Dto, reportDate: string, locale: Locale): ReportAction[] {
  const result: ReportAction[] = []
  const seen = new Set<string>()
  const push = (action: ReportAction) => {
    const owner = personnelDisplayName(action.owner).trim().toLocaleLowerCase()
    const key = `${action.cn.trim().toLocaleLowerCase()}:${owner}:${action.due}`
    if (!seen.has(key)) { seen.add(key); result.push(action) }
  }
  detail.actions.forEach((action: ActionDto) => push({ type: action.sourceType, source: action.id, cn: action.title, en: '—', owner: action.owner, due: action.due, priority: '—', status: action.status === 'Completed' ? reportText('已完成 / Completed', locale) : dueState(action.due, reportDate, locale) }))
  detail.requirements.filter((item) => item.nextAction).forEach((item) => push({ type: reportText('采购需求 / Requirement', locale), source: item.id, cn: item.nextAction, en: '—', owner: item.owner, due: item.due, priority: '—', status: dueState(item.due, reportDate, locale) }))
  detail.opportunities.filter((item) => item.nextAction).forEach((item) => push({ type: reportText('商机 / Opportunity', locale), source: item.id, cn: item.nextAction, en: '—', owner: item.owner, due: item.due, priority: item.intentScore >= 80 ? 'High' : item.intentScore >= 60 ? 'Medium' : 'Low', status: dueState(item.due, reportDate, locale) }))
  detail.visits.filter((item) => item.nextAction && !item.actionDone).forEach((item) => push({ type: reportText('拜访 / Visit', locale), source: item.id, cn: item.nextAction, en: '—', owner: item.actionOwner || item.owner, due: item.due, priority: '—', status: dueState(item.due, reportDate, locale) }))
  return result.sort((a, b) => a.due && b.due ? a.due.localeCompare(b.due) : a.due ? -1 : b.due ? 1 : 0)
}

function reportRisks(detail: Account360Dto, locale: Locale) {
  const risks: Array<{ level: string; title: string; source: string; reason: string; owner: string; action: string }> = []
  if (detail.account.risk !== '稳健') risks.push({ level: detail.account.risk === '高风险' ? reportText('高 / High', locale) : reportText('关注 / Watch', locale), title: reportText('客户健康风险 / Account Health Risk', locale), source: detail.account.id, reason: locale === 'en-US' ? `Current account risk is ${reportEnum(detail.account.risk, locale)}` : `当前客户风险标记为 ${detail.account.risk}`, owner: detail.account.owner, action: detail.account.nextAction })
  if (!detail.contacts.some((item) => item.role === 'Economic Buyer')) risks.push({ level: reportText('关注 / Watch', locale), title: reportText('经济决策人尚未识别 / Economic Buyer Not Identified', locale), source: reportText('关键人 / Stakeholder', locale), reason: reportText('当前客户没有 Economic Buyer 记录', locale), owner: detail.account.owner, action: reportText('识别预算最终批准人与签字链', locale) })
  detail.contracts.filter((item) => !item.signed || ['Unsigned', 'Draft'].includes(item.status)).forEach((item) => risks.push({ level: reportText('高 / High', locale), title: reportText('演示员工116尚未签署 / Contract Not Signed', locale), source: item.id, reason: `${item.type} · ${item.status}`, owner: item.owner, action: reportText('确认法务与签署计划', locale) }))
  return risks
}

export function buildCustomerReportModel(detail: Account360Dto, reportDate: string, locale: Locale = 'zh-CN'): CustomerWorkbookSpec {
  const account = detail.account
  const actions = reportActions(detail, reportDate, locale)
  const risks = reportRisks(detail, locale)
  // Known amounts only, followed by how many are not entered yet, so the total never reads as complete.
  const pipeline = formatKnownTotals(detail.opportunities.filter((item) => open(item.stage)),
    (count) => locale === 'en-US' ? `${count} without an amount` : `${count} 条未填金额`)
  const booking = moneyByCurrency(detail.bookings.filter((item) => item.status === 'Confirmed'))
    .map((item) => formatMoney(item.amount, item.currency)).join(' · ')
  const demoCount = detail.demoRequests.length + detail.evaluations.length

  const overviewRows: CustomerReportCell[][] = [
    [cell(`${account.name} · ${reportText('客户全貌报告 / Customer 360 Report', locale)}`, 1)], blank(),
    [cell(`${reportText('报告日期 / Report Date', locale)}: ${reportDate}  |  ${reportText('客户 / Account', locale)}: ${account.id}  |  ${reportText('负责人 / Owner', locale)}: ${account.owner}`, 2)], blank(),
    header([reportText('客户等级 / Tier', locale), account.tier, reportText('客户类型 / Type', locale), '—', reportText('业务领域 / Segment', locale), account.segment, reportText('城市 / City', locale), account.city]),
    header([reportText('主要厂区 / Site', locale), detail.sites[0]?.name ?? '—', reportText('负责人 / Owner', locale), account.owner, reportText('潜力金额 / Potential', locale), '—', reportText('客户编号 / Account ID', locale), account.id]), blank(),
    header(['Open Pipeline', 'Confirmed Booking', reportText('采购需求 / Requirements', locale), reportText('关键人 / Stakeholders', locale), reportText('Demo进程 / Progress', locale), reportText('演示员工116 / Contracts', locale), reportText('客户风险 / Risks', locale), reportText('待办行动 / Actions', locale)]),
    [cell(pipeline, 15), cell(booking, 15), cell(detail.requirements.length, 8), cell(detail.contacts.length, 8), cell(demoCount, 8), cell(detail.contracts.length, 8), cell(risks.length, 8), cell(actions.length, 8)], blank(),
    [cell(reportText('客户风险 / Customer Risks', locale), 3)],
    header([reportText('等级 / Level', locale), reportText('风险 / Risk', locale), reportText('来源 / Source', locale), reportText('原因 / Reason', locale), reportText('责任人 / Owner', locale), reportText('建议动作 / Suggested Action', locale)]),
  ]
  const overviewMerges = ['A1:H2', 'A3:H3', `A${overviewRows.length - 1}:H${overviewRows.length - 1}`, `F${overviewRows.length}:H${overviewRows.length}`]
  // A Sales user who does not own the Account gets its risk zeroed by the server: the report says so, not "no risk".
  const ownerOnly = account.metricsRestricted ? [{ level: '—', title: reportText('仅客户负责人可见 / Visible to the account owner only', locale), source: account.id, reason: reportText('客户风险、Pipeline 与意愿仅对负责人开放 / Account risk, pipeline and intent are seen by the owner alone', locale), owner: account.owner, action: '—' }] : []
  const displayRisks = ownerOnly.length || risks.length ? [...ownerOnly, ...risks] : [{ level: reportText('低 / Low', locale), title: reportText('暂无显著风险 / No Material Risk', locale), source: '—', reason: reportText('当前规则未识别到异常', locale), owner: account.owner, action: reportText('继续维护客户数据', locale) }]
  displayRisks.forEach((risk) => { const row = overviewRows.length + 1; overviewRows.push([cell(risk.level, risk.level === reportText('高 / High', locale) ? 9 : 10), cell(risk.title, 13), cell(risk.source), cell(risk.reason, 13), cell(risk.owner), cell(risk.action, 13)]); overviewMerges.push(`F${row}:H${row}`) })
  overviewRows.push(blank()); const actionTitleRow = overviewRows.length + 1; overviewRows.push([cell(reportText('下一步行动 / Next Actions（按截止日期排序 / Sorted by Due Date）', locale), 3)]); overviewMerges.push(`A${actionTitleRow}:H${actionTitleRow}`)
  overviewRows.push(header([reportText('类型 / Type', locale), reportText('来源 / Source', locale), reportText('行动内容（中文） / Action (CN)', locale), 'English Action / Action (EN)', reportText('负责人 / Owner', locale), reportText('截止日期 / Due', locale), reportText('优先级 / Priority', locale), reportText('状态 / Status', locale)]))
  actions.forEach((item) => overviewRows.push([cell(item.type, 11), cell(item.source, 11), cell(item.cn, 11), cell(item.en, 11), cell(item.owner, 11), dateCell(item.due), cell(item.priority, 11), cell(item.status, 11)]))
  const overview: CustomerWorksheetSpec = { name: reportText('客户全貌 Overview', locale), columns: columns([22, 28, 54, 40, 20, 20, 18, 26]), rows: overviewRows, merges: overviewMerges, freezeRows: 3 }

  const opportunityRows: CustomerReportCell[][] = [[cell(reportText('商机报告 / Opportunities Report', locale), 1)], blank(), [cell(`${reportText('截至 / As of', locale)} ${reportDate}  |  ${reportText('客户 / Account', locale)}: ${account.name}  |  ${reportText('负责人 / Owner', locale)}: ${account.owner}`, 2)], blank(), header([reportText('商机ID / Opportunity ID', locale), reportText('商机负责人 / Opportunity Owner', locale), reportText('区域 / Sub Region', locale), reportText('客户名称 / Account Name', locale), reportText('商机名称 / Opportunity Name', locale), reportText('设备类型 / Tool Type', locale), reportText('销售类型 / Sale Type', locale), reportText('金额 / Amount', locale), reportText('信心等级 / Confidence', locale), reportText('成功概率 / Success Probability', locale), reportText('PO日期 / PO Date', locale), reportText('发货日期 / Shipment Date', locale), reportText('FAT日期 / FAT Date', locale), reportText('PO付款比例 / % at PO', locale), reportText('发货付款比例 / % at Shipment', locale), reportText('FAT付款比例 / % at FAT', locale), reportText('账期天数 / Payment Term', locale), reportText('说明 / Description', locale)])]
  detail.opportunities.forEach((item) => { const req = detail.requirements.find((row) => row.id === item.sourceRequirementId); opportunityRows.push([cell(item.id), cell(item.owner), cell(regionLabel(account.region, locale)), cell(account.name), cell(item.title, 14), cell(req?.equipment ?? '—', 14), cell(req?.category === '软件与升级' ? 'Service' : 'Tool'), cell(item.amount, 6), cell(confidence(item.intentScore)), cell(opportunityProbabilityLevelLabel(item.probabilityLevel, locale)), cell('—'), cell('—'), cell('—'), cell('—'), cell('—'), cell('—'), cell('—'), cell(`Next: ${item.nextAction}`, 14)]) })
  opportunityRows.push(blank()); const bookingTitleRow = opportunityRows.length + 1; opportunityRows.push([cell(reportText('确认订单 / Confirmed Booking', locale), 3)]); opportunityRows.push(header([reportText('订单ID / Booking ID', locale), reportText('订单名称 / Booking Name', locale), reportText('金额 / Amount', locale), reportText('状态 / Status', locale), reportText('订单日期 / Booking Date', locale), reportText('负责人 / Owner', locale), reportText('来源商机 / Source Opportunity', locale)]))
  detail.bookings.filter((item) => item.status === 'Confirmed').forEach((item) => opportunityRows.push([cell(item.id), cell(bookingTitle(item, locale), 14), cell(item.amount, 6), cell(reportEnum(item.status, locale)), dateCell(item.bookingDate), cell(item.owner), cell(item.sourceOpportunityId || '—')]))
  const opportunity: CustomerWorksheetSpec = { name: reportText('商机 Opportunities', locale), columns: columns([17, 19, 16, 32, 38, 28, 16, 18, 18, 16, 18, 18, 16, 16, 20, 18, 22, 50]), rows: opportunityRows, merges: ['A1:R2', 'A3:R3', `A${bookingTitleRow}:R${bookingTitleRow}`], freezeRows: 5 }

  const requirementRows: CustomerReportCell[][] = [[cell(reportText('采购需求与行动计划 / Requirements & Action Plan', locale), 1)], blank(), [cell(`${account.name}  |  ${reportText('一个客户可维护多项独立需求 / One account can maintain multiple independent requirements', locale)}`, 2)], blank(), header([reportText('需求ID / ID', locale), reportText('分类 / Category', locale), reportText('采购需求 / Requirement', locale), reportText('设备/产品 / Equipment', locale), reportText('应用场景 / Application', locale), reportText('厂区 / Site', locale), reportText('数量 / Qty', locale), reportText('预算金额 / Budget', locale), reportText('预算状态 / Budget Status', locale), reportText('优先级 / Priority', locale), reportText('采购状态 / Status', locale), reportText('预计采购日期 / Purchase Date', locale), reportText('决策人 / Decision Maker', locale), reportText('负责人 / Owner', locale), reportText('下一步行动 / Next Action', locale)])]
  detail.requirements.forEach((item) => requirementRows.push([cell(item.id), cell(item.category), cell(item.title, 14), cell(item.equipment, 14), cell(item.application, 14), cell(item.site, 14), cell(item.quantity), cell(item.budgetAmount, 6), cell(item.budgetStatus), cell('—'), cell(reportEnum(item.status, locale)), cell('—'), cell('—', 14), cell(item.owner), cell(item.nextAction, 11)]))
  requirementRows.push(blank()); const actionQueueRow = requirementRows.length + 1; requirementRows.push([cell(reportText('统一行动队列 / Consolidated Action Queue', locale), 3)]); requirementRows.push(header([reportText('类型 / Type', locale), reportText('来源 / Source', locale), reportText('行动内容（中文） / Action (CN)', locale), 'English Action / Action (EN)', reportText('负责人 / Owner', locale), reportText('截止日期 / Due', locale), reportText('优先级 / Priority', locale), reportText('状态 / Status', locale)]))
  actions.forEach((item) => requirementRows.push([cell(item.type, 11), cell(item.source, 11), cell(item.cn, 11), cell(item.en, 11), cell(item.owner, 11), dateCell(item.due), cell(item.priority, 11), cell(item.status, 11)]))
  const requirement: CustomerWorksheetSpec = { name: reportText('需求与行动 Actions', locale), columns: columns([22, 16, 44, 38, 32, 24, 16, 26, 20, 16, 18, 19, 24, 18, 46]), rows: requirementRows, merges: ['A1:O2', 'A3:O3', `A${actionQueueRow}:O${actionQueueRow}`], freezeRows: 5 }

  const peopleRows: CustomerReportCell[][] = [[cell(reportText('关键人与拜访记录 / Stakeholders & Visits', locale), 1)], blank(), [cell(`${account.name}  |  ${reportText('决策链、关系强度和客户承诺 / Decision chain, relationship strength and commitments', locale)}`, 2)], blank(), header(['ID', reportText('姓名 / Name', locale), reportText('职位 / Title', locale), reportText('部门 / Department', locale), reportText('采购角色 / Buying Role', locale), reportText('影响力 / Influence', locale), reportText('关系强度 / Relationship', locale), reportText('汇报对象 / Reports To', locale), reportText('邮箱 / Email', locale)])]
  detail.contacts.forEach((item) => peopleRows.push([cell(item.id), cell(item.name), cell(item.title, 14), cell(item.department, 14), cell(item.role, 14), cell(item.influence), cell(item.relationship, 14), cell(detail.contacts.find((row) => row.id === item.reportsTo)?.name ?? '—', 14), cell(item.email ?? '—')]))
  peopleRows.push(blank()); const visitTitleRow = peopleRows.length + 1; peopleRows.push([cell(reportText('拜访记录 / Visit History', locale), 3)]); peopleRows.push(header(['ID', reportText('拜访日期 / Visit Date', locale), reportText('方式 / Method', locale), reportText('状态 / Status', locale), 'Sales', reportText('主题 / Subject', locale), reportText('拜访目标 / Objective', locale), reportText('结果 / Outcome', locale), reportText('下一步行动 / Next Action', locale), reportText('行动负责人 / Action Owner', locale), reportText('截止日期 / Due', locale)]))
  detail.visits.forEach((item) => peopleRows.push([cell(item.id), dateCell(item.date), cell(item.type), cell(reportEnum(item.status, locale)), cell(item.owner), cell(item.subject, 14), cell(item.objective, 14), cell(item.outcome || '—', 14), cell(item.nextAction || '—', 11), cell(item.actionOwner || '—'), dateCell(item.due)]))
  const people: CustomerWorksheetSpec = { name: reportText('关键人与拜访 People', locale), columns: columns([12, 18, 28, 25, 28, 20, 28, 34, 42, 22, 18]), rows: peopleRows, merges: ['A1:K2', 'A3:K3', `A${visitTitleRow}:K${visitTitleRow}`], freezeRows: 5 }

  const demoRows: CustomerReportCell[][] = [[cell(reportText('Demo进展与演示员工116状态 / Demo Progress & Contracts', locale), 1)], blank(), [cell(`${account.name}  |  ${reportText('从 Sales 申请、工程评估到正式 Demo 和演示员工116 / From Sales request and engineering review to Demo and contract', locale)}`, 2)], blank(), header(['Request ID', reportText('申请标题 / Request', locale), reportText('申请设备 / Equipment', locale), reportText('样品类型 / Sample', locale), reportText('数量 / Qty', locale), reportText('目标日期 / Target', locale), reportText('优先级 / Priority', locale), reportText('状态 / Status', locale), 'Sales', reportText('工程师 / Engineer', locale), reportText('可行性 / Feasibility', locale), reportText('技术风险 / Technical Risk', locale), reportText('审批意见 / Review Comment', locale), reportText('正式Demo / Demo ID', locale)])]
  detail.demoRequests.forEach((item) => demoRows.push([cell(item.id), cell(item.title, 14), cell(item.requestedEquipment, 14), cell(item.sampleType, 14), cell(item.sampleQuantity), dateCell(item.targetDate), cell(item.priority), cell(reportEnum(item.status, locale)), cell(item.salesOwner), cell(item.engineerOwner || '—'), cell(item.feasibility || '—', 14), cell(item.technicalRisk || '—', 14), cell(item.engineerComment || item.managerComment || '—', 14), cell(item.evaluationId || '—')]))
  demoRows.push(blank()); const formalDemoRow = demoRows.length + 1; demoRows.push([cell(reportText('正式Demo / Formal Demo & Wafer Test', locale), 3)]); demoRows.push(header(['Demo ID', reportText('来源申请 / Source Request', locale), reportText('Demo标题 / Title', locale), reportText('状态 / Status', locale), reportText('应用工程师 / Engineer', locale), 'Wafers', reportText('完成Runs / Completed Runs', locale), reportText('平均Capture / Avg. Capture', locale), reportText('平均FP / Avg. FP', locale), reportText('计划完成日 / Planned End', locale), reportText('验收 / Acceptance', locale), reportText('报告状态 / Report Status', locale)]))
  detail.evaluations.forEach((item) => { const done = item.runs.filter((run) => run.status === 'Completed'); const average = (key: 'capture' | 'falsePositive') => done.length ? done.reduce((sum, run) => sum + Number(run[key] ?? 0), 0) / done.length / 100 : '—'; demoRows.push([cell(item.id), cell(item.demoRequestId || '—'), cell(item.title, 14), evaluationStatusCell(item, locale), cell(item.owner), cell(item.wafers), cell(done.length), cell(average('capture'), 7), cell(average('falsePositive'), 7), dateCell(item.plannedEnd), evaluationAcceptanceCell(item, locale), cell(item.reportStatus)]) })
  demoRows.push(blank()); const contractRow = demoRows.length + 1; demoRows.push([cell(reportText('演示员工116 / Contracts', locale), 3)]); demoRows.push(header([reportText('演示员工116ID / Contract ID', locale), reportText('类型 / Type', locale), reportText('状态 / Status', locale), reportText('已签署 / Signed', locale), reportText('演示员工116金额 / Amount', locale), reportText('开始日期 / Start', locale), reportText('到期日期 / End', locale), reportText('PO付款比例 / % at PO', locale), reportText('发货付款比例 / % at Shipment', locale), reportText('FAT付款比例 / % at FAT', locale), reportText('付款账期 / Payment Term', locale)]))
  detail.contracts.forEach((item) => demoRows.push([cell(item.id), cell(item.type), cell(reportEnum(item.status, locale)), cell(item.signed ? reportText('是 / Yes', locale) : reportText('否 / No', locale)), cell(item.amount, 6), dateCell(item.start), dateCell(item.end), cell('—'), cell('—'), cell('—'), cell('—')]))
  const demo: CustomerWorksheetSpec = { name: reportText('Demo与演示员工116 Demo', locale), columns: columns([18, 38, 32, 24, 18, 16, 18, 22, 18, 22, 24, 40, 46, 18]), rows: demoRows, merges: ['A1:N2', 'A3:N3', `A${formalDemoRow}:N${formalDemoRow}`, `A${contractRow}:N${contractRow}`], freezeRows: 5 }

  const safeName = account.shortName.replace(/[\\/:*?"<>|（）()\s]+/g, '_').replace(/^_+|_+$/g, '')
  return { fileName: `${safeName}_Customer_360_${reportDate}.xlsx`, sheets: [overview, opportunity, requirement, people, demo] }
}
