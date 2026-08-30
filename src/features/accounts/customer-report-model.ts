import type { Account360Dto, ActionDto } from '@/types/crm'
import { formatMoney, moneyByCurrency } from '@/domain/money'
import { personnelDisplayName } from '@/demo/personnel'

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
const open = (stage: string) => !['Won', 'Lost'].includes(stage)
const dueState = (due: string, reportDate: string) => !due ? '待确认 / To Confirm' : due < reportDate ? '已逾期 / Overdue' : due === reportDate ? '今日到期 / Due Today' : '待完成 / Open'

interface ReportAction { type: string; source: string; cn: string; en: string; owner: string; due: string; priority: string; status: string }

function reportActions(detail: Account360Dto, reportDate: string): ReportAction[] {
  const result: ReportAction[] = []
  const seen = new Set<string>()
  const push = (action: ReportAction) => {
    const owner = personnelDisplayName(action.owner).trim().toLocaleLowerCase()
    const key = `${action.cn.trim().toLocaleLowerCase()}:${owner}:${action.due}`
    if (!seen.has(key)) { seen.add(key); result.push(action) }
  }
  detail.actions.forEach((action: ActionDto) => push({ type: action.sourceType, source: action.id, cn: action.title, en: '—', owner: action.owner, due: action.due, priority: '—', status: action.status === 'Completed' ? '已完成 / Completed' : dueState(action.due, reportDate) }))
  detail.requirements.filter((item) => item.nextAction).forEach((item) => push({ type: '采购需求 / Requirement', source: item.id, cn: item.nextAction, en: '—', owner: item.owner, due: item.due, priority: '—', status: dueState(item.due, reportDate) }))
  detail.opportunities.filter((item) => item.nextAction).forEach((item) => push({ type: '商机 / Opportunity', source: item.id, cn: item.nextAction, en: '—', owner: item.owner, due: item.due, priority: item.intentScore >= 80 ? 'High' : item.intentScore >= 60 ? 'Medium' : 'Low', status: dueState(item.due, reportDate) }))
  detail.visits.filter((item) => item.nextAction && !item.actionDone).forEach((item) => push({ type: '拜访 / Visit', source: item.id, cn: item.nextAction, en: '—', owner: item.actionOwner || item.owner, due: item.due, priority: '—', status: dueState(item.due, reportDate) }))
  return result.sort((a, b) => a.due && b.due ? a.due.localeCompare(b.due) : a.due ? -1 : b.due ? 1 : 0)
}

function reportRisks(detail: Account360Dto) {
  const risks: Array<{ level: string; title: string; source: string; reason: string; owner: string; action: string }> = []
  if (detail.account.risk !== '稳健') risks.push({ level: detail.account.risk === '高风险' ? '高 / High' : '关注 / Watch', title: '客户健康风险 / Account Health Risk', source: detail.account.id, reason: `当前客户风险标记为 ${detail.account.risk}`, owner: detail.account.owner, action: detail.account.nextAction })
  if (!detail.contacts.some((item) => item.role === 'Economic Buyer')) risks.push({ level: '关注 / Watch', title: '经济决策人尚未识别 / Economic Buyer Not Identified', source: '关键人 / Stakeholder', reason: '当前客户没有 Economic Buyer 记录', owner: detail.account.owner, action: '识别预算最终批准人与签字链' })
  detail.contracts.filter((item) => !item.signed || ['Unsigned', 'Draft'].includes(item.status)).forEach((item) => risks.push({ level: '高 / High', title: '合同尚未签署 / Contract Not Signed', source: item.id, reason: `${item.type} · ${item.status}`, owner: item.owner, action: '确认法务与签署计划' }))
  return risks
}

export function buildCustomerReportModel(detail: Account360Dto, reportDate: string): CustomerWorkbookSpec {
  const account = detail.account
  const actions = reportActions(detail, reportDate)
  const risks = reportRisks(detail)
  const pipeline = moneyByCurrency(detail.opportunities.filter((item) => open(item.stage)))
    .map((item) => formatMoney(item.amount, item.currency)).join(' · ')
  const booking = moneyByCurrency(detail.bookings.filter((item) => item.status === 'Confirmed'))
    .map((item) => formatMoney(item.amount, item.currency)).join(' · ')
  const demoCount = detail.demoRequests.length + detail.evaluations.length

  const overviewRows: CustomerReportCell[][] = [
    [cell(`${account.name} · 客户全貌报告 / Customer 360 Report`, 1)], blank(),
    [cell(`报告日期 / Report Date: ${reportDate}  |  客户 / Account: ${account.id}  |  负责人 / Owner: ${account.owner}`, 2)], blank(),
    header(['客户等级 / Tier', account.tier, '客户类型 / Type', '—', '业务领域 / Segment', account.segment, '城市 / City', account.city]),
    header(['主要厂区 / Site', detail.sites[0]?.name ?? '—', '负责人 / Owner', account.owner, '潜力金额 / Potential', '—', '客户编号 / Account ID', account.id]), blank(),
    header(['Open Pipeline', 'Confirmed Booking', '采购需求 / Requirements', '关键人 / Stakeholders', 'Demo进程 / Progress', '合同 / Contracts', '客户风险 / Risks', '待办行动 / Actions']),
    [cell(pipeline, 15), cell(booking, 15), cell(detail.requirements.length, 8), cell(detail.contacts.length, 8), cell(demoCount, 8), cell(detail.contracts.length, 8), cell(risks.length, 8), cell(actions.length, 8)], blank(),
    [cell('客户风险 / Customer Risks', 3)],
    header(['等级 / Level', '风险 / Risk', '来源 / Source', '原因 / Reason', '责任人 / Owner', '建议动作 / Suggested Action']),
  ]
  const overviewMerges = ['A1:H2', 'A3:H3', `A${overviewRows.length - 1}:H${overviewRows.length - 1}`, `F${overviewRows.length}:H${overviewRows.length}`]
  const displayRisks = risks.length ? risks : [{ level: '低 / Low', title: '暂无显著风险 / No Material Risk', source: '—', reason: '当前规则未识别到异常', owner: account.owner, action: '继续维护客户数据' }]
  displayRisks.forEach((risk) => { const row = overviewRows.length + 1; overviewRows.push([cell(risk.level, risk.level.startsWith('高') ? 9 : 10), cell(risk.title, 13), cell(risk.source), cell(risk.reason, 13), cell(risk.owner), cell(risk.action, 13)]); overviewMerges.push(`F${row}:H${row}`) })
  overviewRows.push(blank()); const actionTitleRow = overviewRows.length + 1; overviewRows.push([cell('下一步行动 / Next Actions（按截止日期排序 / Sorted by Due Date）', 3)]); overviewMerges.push(`A${actionTitleRow}:H${actionTitleRow}`)
  overviewRows.push(header(['类型 / Type', '来源 / Source', '行动内容（中文） / Action (CN)', 'English Action / Action (EN)', '负责人 / Owner', '截止日期 / Due', '优先级 / Priority', '状态 / Status']))
  actions.forEach((item) => overviewRows.push([cell(item.type, 11), cell(item.source, 11), cell(item.cn, 11), cell(item.en, 11), cell(item.owner, 11), dateCell(item.due), cell(item.priority, 11), cell(item.status, 11)]))
  const overview: CustomerWorksheetSpec = { name: '客户全貌 Overview', columns: columns([22, 28, 54, 40, 20, 20, 18, 26]), rows: overviewRows, merges: overviewMerges, freezeRows: 3 }

  const opportunityRows: CustomerReportCell[][] = [[cell('商机报告 / Opportunities Report', 1)], blank(), [cell(`截至 / As of ${reportDate}  |  客户 / Account: ${account.name}  |  负责人 / Owner: ${account.owner}`, 2)], blank(), header(['商机ID / Opportunity ID', '商机负责人 / Opportunity Owner', '区域 / Sub Region', '客户名称 / Account Name', '商机名称 / Opportunity Name', '设备类型 / Tool Type', '销售类型 / Sale Type', '金额 / Amount', '信心等级 / Confidence', '概率 / Probability (%)', 'PO日期 / PO Date', '发货日期 / Shipment Date', 'FAT日期 / FAT Date', 'PO付款比例 / % at PO', '发货付款比例 / % at Shipment', 'FAT付款比例 / % at FAT', '账期天数 / Payment Term', '说明 / Description'])]
  detail.opportunities.forEach((item) => { const req = detail.requirements.find((row) => row.id === item.sourceRequirementId); opportunityRows.push([cell(item.id), cell(item.owner), cell(account.region), cell(account.name), cell(item.title, 14), cell(req?.equipment ?? '—', 14), cell(req?.category === '软件与升级' ? 'Service' : 'Tool'), cell(item.amount, 6), cell(confidence(item.intentScore)), cell(item.probability / 100, 7), cell('—'), cell('—'), cell('—'), cell('—'), cell('—'), cell('—'), cell('—'), cell(`Next: ${item.nextAction}`, 14)]) })
  opportunityRows.push(blank()); const bookingTitleRow = opportunityRows.length + 1; opportunityRows.push([cell('确认订单 / Confirmed Booking', 3)]); opportunityRows.push(header(['订单ID / Booking ID', '订单名称 / Booking Name', '金额 / Amount', '状态 / Status', '订单日期 / Booking Date', '负责人 / Owner', '来源商机 / Source Opportunity']))
  detail.bookings.filter((item) => item.status === 'Confirmed').forEach((item) => opportunityRows.push([cell(item.id), cell(item.title, 14), cell(item.amount, 6), cell(item.status), dateCell(item.bookingDate), cell(item.owner), cell(item.sourceOpportunityId || '—')]))
  const opportunity: CustomerWorksheetSpec = { name: '商机 Opportunities', columns: columns([17, 19, 16, 32, 38, 28, 16, 18, 18, 16, 18, 18, 16, 16, 20, 18, 22, 50]), rows: opportunityRows, merges: ['A1:R2', 'A3:R3', `A${bookingTitleRow}:R${bookingTitleRow}`], freezeRows: 5 }

  const requirementRows: CustomerReportCell[][] = [[cell('采购需求与行动计划 / Requirements & Action Plan', 1)], blank(), [cell(`${account.name}  |  一个客户可维护多项独立需求 / One account can maintain multiple independent requirements`, 2)], blank(), header(['需求ID / ID', '分类 / Category', '采购需求 / Requirement', '设备/产品 / Equipment', '应用场景 / Application', '厂区 / Site', '数量 / Qty', '预算金额 / Budget', '预算状态 / Budget Status', '优先级 / Priority', '采购状态 / Status', '预计采购日期 / Purchase Date', '决策人 / Decision Maker', '负责人 / Owner', '下一步行动 / Next Action'])]
  detail.requirements.forEach((item) => requirementRows.push([cell(item.id), cell(item.category), cell(item.title, 14), cell(item.equipment, 14), cell(item.application, 14), cell(item.site, 14), cell(item.quantity), cell(item.budgetAmount, 6), cell(item.budgetStatus), cell('—'), cell(item.status), cell('—'), cell('—', 14), cell(item.owner), cell(item.nextAction, 11)]))
  requirementRows.push(blank()); const actionQueueRow = requirementRows.length + 1; requirementRows.push([cell('统一行动队列 / Consolidated Action Queue', 3)]); requirementRows.push(header(['类型 / Type', '来源 / Source', '行动内容（中文） / Action (CN)', 'English Action / Action (EN)', '负责人 / Owner', '截止日期 / Due', '优先级 / Priority', '状态 / Status']))
  actions.forEach((item) => requirementRows.push([cell(item.type, 11), cell(item.source, 11), cell(item.cn, 11), cell(item.en, 11), cell(item.owner, 11), dateCell(item.due), cell(item.priority, 11), cell(item.status, 11)]))
  const requirement: CustomerWorksheetSpec = { name: '需求与行动 Actions', columns: columns([22, 16, 44, 38, 32, 24, 16, 26, 20, 16, 18, 19, 24, 18, 46]), rows: requirementRows, merges: ['A1:O2', 'A3:O3', `A${actionQueueRow}:O${actionQueueRow}`], freezeRows: 5 }

  const peopleRows: CustomerReportCell[][] = [[cell('关键人与拜访记录 / Stakeholders & Visits', 1)], blank(), [cell(`${account.name}  |  决策链、关系强度和客户承诺 / Decision chain, relationship strength and commitments`, 2)], blank(), header(['ID', '姓名 / Name', '职位 / Title', '部门 / Department', '采购角色 / Buying Role', '影响力 / Influence', '关系强度 / Relationship', '汇报对象 / Reports To', '邮箱 / Email'])]
  detail.contacts.forEach((item) => peopleRows.push([cell(item.id), cell(item.name), cell(item.title, 14), cell(item.department, 14), cell(item.role, 14), cell(item.influence), cell(item.relationship, 14), cell(detail.contacts.find((row) => row.id === item.reportsTo)?.name ?? '—', 14), cell(item.email ?? '—')]))
  peopleRows.push(blank()); const visitTitleRow = peopleRows.length + 1; peopleRows.push([cell('拜访记录 / Visit History', 3)]); peopleRows.push(header(['ID', '拜访日期 / Visit Date', '方式 / Method', '状态 / Status', 'Sales', '主题 / Subject', '拜访目标 / Objective', '结果 / Outcome', '下一步行动 / Next Action', '行动负责人 / Action Owner', '截止日期 / Due']))
  detail.visits.forEach((item) => peopleRows.push([cell(item.id), dateCell(item.date), cell(item.type), cell(item.status), cell(item.owner), cell(item.subject, 14), cell(item.objective, 14), cell(item.outcome || '—', 14), cell(item.nextAction || '—', 11), cell(item.actionOwner || '—'), dateCell(item.due)]))
  const people: CustomerWorksheetSpec = { name: '关键人与拜访 People', columns: columns([12, 18, 28, 25, 28, 20, 28, 34, 42, 22, 18]), rows: peopleRows, merges: ['A1:K2', 'A3:K3', `A${visitTitleRow}:K${visitTitleRow}`], freezeRows: 5 }

  const demoRows: CustomerReportCell[][] = [[cell('Demo进展与合同状态 / Demo Progress & Contracts', 1)], blank(), [cell(`${account.name}  |  从 Sales 申请、工程评估到正式 Demo 和合同 / From Sales request and engineering review to Demo and contract`, 2)], blank(), header(['Request ID', '申请标题 / Request', '申请设备 / Equipment', '样品类型 / Sample', '数量 / Qty', '目标日期 / Target', '优先级 / Priority', '状态 / Status', 'Sales', '工程师 / Engineer', '可行性 / Feasibility', '技术风险 / Technical Risk', '审批意见 / Review Comment', '正式Demo / Demo ID'])]
  detail.demoRequests.forEach((item) => demoRows.push([cell(item.id), cell(item.title, 14), cell(item.requestedEquipment, 14), cell(item.sampleType, 14), cell(item.sampleQuantity), dateCell(item.targetDate), cell(item.priority), cell(item.status), cell(item.salesOwner), cell(item.engineerOwner || '—'), cell(item.feasibility || '—', 14), cell(item.technicalRisk || '—', 14), cell(item.engineerComment || item.managerComment || '—', 14), cell(item.evaluationId || '—')]))
  demoRows.push(blank()); const formalDemoRow = demoRows.length + 1; demoRows.push([cell('正式Demo / Formal Demo & Wafer Test', 3)]); demoRows.push(header(['Demo ID', '来源申请 / Source Request', 'Demo标题 / Title', '状态 / Status', '应用工程师 / Engineer', 'Wafers', '完成Runs / Completed Runs', '平均Capture / Avg. Capture', '平均FP / Avg. FP', '计划完成日 / Planned End', '验收 / Acceptance', '报告状态 / Report Status']))
  detail.evaluations.forEach((item) => { const done = item.runs.filter((run) => run.status === 'Completed'); const average = (key: 'capture' | 'falsePositive') => done.length ? done.reduce((sum, run) => sum + Number(run[key] ?? 0), 0) / done.length / 100 : '—'; demoRows.push([cell(item.id), cell(item.demoRequestId || '—'), cell(item.title, 14), cell(item.status), cell(item.owner), cell(item.wafers), cell(done.length), cell(average('capture'), 7), cell(average('falsePositive'), 7), dateCell(item.plannedEnd), cell(item.acceptance), cell(item.reportStatus)]) })
  demoRows.push(blank()); const contractRow = demoRows.length + 1; demoRows.push([cell('合同 / Contracts', 3)]); demoRows.push(header(['合同ID / Contract ID', '类型 / Type', '状态 / Status', '已签署 / Signed', '合同金额 / Amount', '开始日期 / Start', '到期日期 / End', 'PO付款比例 / % at PO', '发货付款比例 / % at Shipment', 'FAT付款比例 / % at FAT', '付款账期 / Payment Term']))
  detail.contracts.forEach((item) => demoRows.push([cell(item.id), cell(item.type), cell(item.status), cell(item.signed ? '是 / Yes' : '否 / No'), cell(item.amount, 6), dateCell(item.start), dateCell(item.end), cell('—'), cell('—'), cell('—'), cell('—')]))
  const demo: CustomerWorksheetSpec = { name: 'Demo与合同 Demo', columns: columns([18, 38, 32, 24, 18, 16, 18, 22, 18, 22, 24, 40, 46, 18]), rows: demoRows, merges: ['A1:N2', 'A3:N3', `A${formalDemoRow}:N${formalDemoRow}`, `A${contractRow}:N${contractRow}`], freezeRows: 5 }

  const safeName = account.shortName.replace(/[\\/:*?"<>|（）()\s]+/g, '_').replace(/^_+|_+$/g, '')
  return { fileName: `${safeName}_Customer_360_${reportDate}.xlsx`, sheets: [overview, opportunity, requirement, people, demo] }
}
