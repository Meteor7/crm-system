import type {
  OpportunityStakeholderInfluence,
  OpportunityStakeholderRole,
  OpportunityStakeholderStance,
  StrategyOpportunityStage,
} from '@/types/workspaces'

export type Tone = 'positive' | 'info' | 'warning' | 'danger' | 'neutral'

export interface StrategyOpportunity {
  id: string
  accountId: string
  siteId: string
  title: string
  account: string
  site: string
  owner: string
  stage: StrategyOpportunityStage
  forecast: 'Commit' | 'Upside' | 'Pipeline'
  amount: number
  probability: number
  poDate: string
  updated: string
  score: number
  toolType: string
  saleType: string
  subRegion: string
  currency: string
  originalAmount: number
  shipmentDate: string
  fatDate: string
  paymentMilestones: string[]
  competition: string
  winReason: string
  lostReason: string
  history: Array<{ at: string; actor: string; field: string; from: string; to: string }>
  strengths: string[]
  redFlags: string[]
  informationNeeded: string[]
  stakeholders: Array<{ id?: string; contactId?: string; name: string; title: string; role: OpportunityStakeholderRole; influence: OpportunityStakeholderInfluence; stance: OpportunityStakeholderStance; coverage: string }>
  actions: Array<{ id?: string; title: string; owner: string; due: string; status: 'Open' | 'Done' }>
}

export interface DemoProject {
  id: string
  accountId: string
  siteId: string
  opportunityId: string
  title: string
  account: string
  opportunity: string
  owner: string
  status: string
  progress: number
  tool: string
  objective: string
  target: string
  successFactors: string[]
  contact: string
  industry: string
  salesContact: string
  waferCount: number
  specificRequest: string
  detectMeasure: string
  expectedResults: string
  otherTools: string
  complementaryTool: string
  internalQuestions: string[]
  customerQuestions: string[]
  preparedBy: string
  approvedBy: string
  conclusion: { status: 'Pending' | 'Accepted' | 'Rejected'; summary: string; customerFeedback: string; confirmedBy: string; confirmedAt: string; followUpAction: string }
  approvals: Array<{ label: string; actor: string; status: 'Done' | 'Current' | 'Waiting' }>
  executions: Array<{ id: string; tool: string; window: string; engineer: string; status: string }>
  wafers: Array<{ id: string; lot: string; material: string; diameter: string; thickness: string; status: string }>
  testRuns: Array<{ id: string; date: string; recipe: string; capture: number; falsePositive: number; wph: number; result: string }>
}

export interface InstalledTool {
  id: string
  accountId: string
  siteId: string
  serial: string
  model: string
  account: string
  site: string
  location: string
  status: string
  software: string
  targetSoftware: string
  warrantyEnd: string
  serviceLevel: string
  health: number
  sourceOpportunityId: string
  salesOrder: string
  contract: string
  warrantyStart: string
  serviceContract: string
  pmCycle: string
  lastService: string
  operatingSystem: string
  configuration: string
  ownershipType: string
  milestones: Array<{ label: string; date: string; state: 'Done' | 'Current' | 'Waiting' }>
  documents: string[]
}

export interface ServiceAppointment {
  id: string
  accountId: string
  siteId: string
  day: string
  start: string
  end: string
  engineer: string
  account: string
  tool: string
  type: string
  status: string
  severity: 'Normal' | 'Warning' | 'Critical'
  conflict?: boolean
  contact: string
  issue: string
  priority: string
  downtime: string
  actualWindow: string
  rootCause: string
  actionsPerformed: string
  spares: string
  laborHours: number
  attachments: string[]
  result: string
  nextAction: string
  customerSignoff: string
}

export interface ProcedureRun {
  id: string
  accountId: string
  siteId: string
  title: string
  account: string
  tool: string
  owner: string
  status: string
  window: string
  progress: number
  templateVersion: string
  stages: Array<{ label: string; state: 'Done' | 'Current' | 'Waiting' }>
  checklist: Array<{ id: string; title: string; owner: string; mandatory: boolean; status: 'Passed' | 'Pending' | 'Blocked' | 'Failed' | 'N/A'; evidence: string; executedAt: string; reviewer: string; reviewedAt: string; notes: string }>
  attachments: string[]
  rollbackPlan: string
  signoff: { status: 'Waiting' | 'Signed'; signer: string; signedAt: string }
  qualificationResult: string
  deviation: string
  deviationApprover: string
  rollbackResult: string
}

export interface ControlledDocument {
  id: string
  title: string
  category: 'Technical' | 'Commercial'
  type: string
  product: string
  version: string
  revision: string
  status: 'Released' | 'Under Review'
  confidentiality: string
  access: 'Direct' | 'Request'
  reviewDate: string
  owner: string
  downloads: number
  fileUrl?: string
  fileName?: string
  versions: Array<{ version: string; revision: string; status: 'Released' | 'Superseded' | 'Obsolete'; releasedAt: string; checksum: string }>
  audit: Array<{ id: string; employee: string; at: string; reason: string; version: string }>
  applicableTool: string
}

export const opportunities: StrategyOpportunity[] = [
  {
    id: 'OPP-003', accountId: 'ACC-002', siteId: 'SITE-004', title: 'HBM AOI 扩线项目', account: '示例企业044有限公司', site: '武汉二期', owner: 'Demo Staff 01', stage: '采购流程', forecast: 'Commit', amount: 32500000, probability: 79, poDate: '2026-09-18', updated: '2 天前', score: 86,
    toolType: 'Inspection Tool', saleType: 'New Tool', subRegion: 'Central China', currency: 'CNY', originalAmount: 32500000, shipmentDate: '2026-11-12', fatDate: '2026-10-28', paymentMilestones: ['30% PO', '60% Shipment', '10% SAT'], competition: 'KLA · Final shortlist', winReason: '技术指标与本地服务领先', lostReason: '', history: [{ at: '2026-07-16 17:20', actor: 'Demo Staff 01', field: 'Probability', from: '72%', to: '79%' }, { at: '2026-07-14 09:30', actor: 'Demo Staff 06', field: 'Forecast', from: 'Upside', to: 'Commit' }],
    strengths: ['技术指标在客户基准测试中排名第一', '技术负责人愿意作为内部 Champion', '交付窗口与客户扩线计划匹配'],
    redFlags: ['集团采购要求追加 5% 价格让步', '最终预算批复尚未完成'],
    informationNeeded: ['CFO 最终预算签批日期', '竞争对手最新服务承诺'],
    stakeholders: [
      { name: '王志远', title: '设备副总经理', role: 'Economic Buyer', influence: 'High', stance: 'Neutral', coverage: 'Manager relationship' },
      { name: '陈珂', title: '良率工程总监', role: 'Technical Buyer', influence: 'High', stance: 'Support', coverage: 'Weekly technical sync' },
      { name: '赵昕', title: 'AOI 工艺经理', role: 'Coach', influence: 'High', stance: 'Support', coverage: 'Direct access' },
      { name: '李敏', title: '采购经理', role: 'Procurement', influence: 'Medium', stance: 'Against', coverage: 'Needs executive visit' },
    ],
    actions: [
      { title: '准备最终商务让步边界', owner: 'Demo Staff 01', due: '07-22', status: 'Open' },
      { title: '安排 VP 与设备副总会谈', owner: 'Demo Staff 06', due: '07-25', status: 'Open' },
      { title: '提交扩产交付资源确认', owner: 'Demo Staff 05', due: '07-19', status: 'Done' },
    ],
  },
  {
    id: 'OPP-001', accountId: 'ACC-001', siteId: 'SITE-001', title: '南京缺陷检测设备 2 台', account: '示例企业014有限公司', site: '南京 12-inch Fab', owner: 'Demo Staff 01', stage: 'Wafer Demo确认', forecast: 'Upside', amount: 16800000, probability: 68, poDate: '2026-10-08', updated: '6 天前', score: 74,
    toolType: 'Macro Inspection', saleType: 'Capacity Expansion', subRegion: 'East China', currency: 'CNY', originalAmount: 16800000, shipmentDate: '2026-12-05', fatDate: '2026-11-20', paymentMilestones: ['30% PO', '50% FAT', '20% SAT'], competition: 'Onto Innovation · Benchmarking', winReason: '', lostReason: '', history: [{ at: '2026-07-15 14:00', actor: 'Demo Staff 01', field: 'Stage', from: '需求发现', to: 'Wafer Demo确认' }],
    strengths: ['客户对低 false-positive 指标高度认可', '已有同类量产案例'], redFlags: ['样片到达延迟一周', '决策人覆盖不足'], informationNeeded: ['竞争工具复测数据', '客户量产节拍目标'],
    stakeholders: [
      { name: '周楠', title: '研发总监', role: 'Technical Buyer', influence: 'High', stance: 'Support', coverage: 'Demo steering meeting' },
      { name: '顾晓', title: '采购专员', role: 'Procurement', influence: 'Medium', stance: 'Neutral', coverage: 'Email only' },
    ],
    actions: [{ title: '确认第二批样片物流', owner: 'Demo Staff 08', due: '07-21', status: 'Open' }, { title: '补齐 Economic Buyer 关系', owner: 'Demo Staff 06', due: '07-30', status: 'Open' }],
  },
  {
    id: 'OPP-007', accountId: 'ACC-005', siteId: 'SITE-005', title: '先进封装外观检测', account: '示例企业040有限公司', site: '南通工厂', owner: 'Demo Staff 02', stage: '需求发现', forecast: 'Pipeline', amount: 7600000, probability: 31, poDate: '2026-12-15', updated: '11 天前', score: 63,
    toolType: 'Package Inspection', saleType: 'New Tool', subRegion: 'East China', currency: 'CNY', originalAmount: 7600000, shipmentDate: '2027-02-18', fatDate: '2027-01-28', paymentMilestones: ['20% PO', '70% Shipment', '10% Acceptance'], competition: 'Local AOI vendor · Price pressure', winReason: '', lostReason: '价格与预算尚未确认', history: [{ at: '2026-07-10 11:10', actor: 'Demo Staff 02', field: 'Amount', from: '¥680万', to: '¥760万' }],
    strengths: ['Wafer-level package 方案覆盖完整', '本地服务团队响应快'], redFlags: ['价格竞争进入最终轮', '机会连续 11 天未更新'], informationNeeded: ['采购评分权重', '竞争对手最终报价', '厂务接口确认结果'],
    stakeholders: [
      { name: '马会东', title: '封装事业部总经理', role: 'Economic Buyer', influence: 'High', stance: 'Neutral', coverage: 'No direct access' },
      { name: '孙强', title: '设备经理', role: 'User Buyer', influence: 'High', stance: 'Support', coverage: 'Site workshop' },
      { name: '钱宇', title: '采购经理', role: 'Procurement', influence: 'High', stance: 'Against', coverage: 'Commercial meeting' },
    ],
    actions: [{ title: '更新竞争报价分析', owner: 'Demo Staff 07', due: '07-20', status: 'Open' }, { title: '发起总经理关系引荐', owner: 'Demo Staff 06', due: '07-24', status: 'Open' }],
  },
  {
    id: 'OPP-006', accountId: 'ACC-006', siteId: 'SITE-006', title: '高速 AOI 产能升级', account: '示例企业027有限公司', site: '演示员工27', owner: 'Demo Staff 02', stage: 'Won', forecast: 'Commit', amount: 18800000, probability: 100, poDate: '2026-07-02', updated: '7月14日', score: 86,
    toolType: 'FastScan 1200', saleType: 'Capacity Expansion', subRegion: 'East China', currency: 'CNY', originalAmount: 18800000, shipmentDate: '2026-08-28', fatDate: '2026-08-18', paymentMilestones: ['30% PO', '60% Shipment', '10% SAT'], competition: 'Won', winReason: '高速 AOI 产能与交付窗口满足客户要求', lostReason: '', history: [{ at: '2026-07-02 16:30', actor: 'Demo Staff 02', field: 'Stage', from: '采购流程', to: 'Won' }],
    strengths: ['高速在线检测能力已通过客户确认', '交付资源与八月底窗口匹配'], redFlags: [], informationNeeded: [],
    stakeholders: [],
    actions: [{ title: '安排交付启动会', owner: 'Demo Staff 02', due: '07-21', status: 'Open' }],
  },
]

export const demoProjects = [
  {
    id: 'DEMO-2607-01', title: 'HBM TSV 缺陷检测', account: '示例企业044', opportunity: 'HBM AOI 扩线项目', owner: '演示员工23 / FAE', status: 'Analysis', progress: 72, tool: 'RAYHER AX-9000', objective: '验证微凸点、TSV 残留及边缘裂纹的检出能力', target: '2026-07-28', successFactors: ['Capture ≥ 96%', 'False Positive ≤ 1.5%', 'WPH ≥ 42'],
    approvals: [{ label: 'Sales 提交', actor: 'Demo Staff 01', status: 'Done' }, { label: 'FAE Review', actor: '演示员工23', status: 'Done' }, { label: 'Manager Approval', actor: 'Demo Staff 06', status: 'Done' }, { label: 'Customer Review', actor: '待安排', status: 'Current' }],
    executions: [{ id: 'DEMO-2607-01-EXE-01', tool: 'AX9-LAB-02', window: '07-18 至 07-25', engineer: '演示员工23', status: 'Analysis' }],
    wafers: [{ id: 'WAF-HBM-031', lot: 'L260714-A', material: 'Silicon / Cu', diameter: '300 mm', thickness: '775 μm', status: 'Testing' }, { id: 'WAF-HBM-032', lot: 'L260714-A', material: 'Silicon / Cu', diameter: '300 mm', thickness: '775 μm', status: 'Stored' }],
    testRuns: [{ id: 'RUN-0718-A', date: '07-18', recipe: 'HBM-TSV-v4', capture: 96.8, falsePositive: 1.2, wph: 44, result: 'Pass' }, { id: 'RUN-0719-B', date: '07-19', recipe: 'HBM-EDGE-v2', capture: 95.9, falsePositive: 1.4, wph: 46, result: 'Review' }],
  },
  {
    id: 'DEMO-2607-02', title: '12-inch AOI验证', account: '豪威科技', opportunity: 'CIS 缺陷检测平台', owner: '演示员工14 / FAE', status: 'Sample Received', progress: 38, tool: 'RAYHER VI-620', objective: '验证 CIS 表面颗粒、划伤与 Pattern 缺陷分类', target: '2026-08-06', successFactors: ['Capture ≥ 95%', 'False Positive ≤ 2.0%', '完成客户 Golden Sample 对齐'],
    approvals: [{ label: 'Sales 提交', actor: 'Demo Staff 08', status: 'Done' }, { label: 'FAE Review', actor: '演示员工14', status: 'Done' }, { label: 'Manager Approval', actor: 'Demo Staff 06', status: 'Done' }, { label: 'Customer Review', actor: '待测试', status: 'Waiting' }],
    executions: [{ id: 'DEMO-2607-02-EXE-01', tool: 'VI6-DEMO-01', window: '07-24 至 08-02', engineer: '演示员工14', status: 'Scheduled' }],
    wafers: [{ id: 'WAF-12A-07', lot: 'CIS-2607', material: 'Silicon / PR', diameter: '300 mm', thickness: '725 μm', status: 'Received' }],
    testRuns: [{ id: 'RUN-PLANNED', date: '07-24', recipe: 'CIS-GOLDEN-v1', capture: 0, falsePositive: 0, wph: 0, result: 'Planned' }],
  },
  {
    id: 'DEMO-2607-03', title: 'Fan-out RDL量产评估', account: '华天科技', opportunity: '先进封装量产线', owner: '演示员工23 / FAE', status: 'Sample Received', progress: 49, tool: 'RAYHER AX-7600', objective: '确认 RDL 断线及 Via 开口缺陷的量产检出窗口', target: '2026-08-18', successFactors: ['Capture ≥ 94%', 'WPH ≥ 36', '客户复核一致率 ≥ 90%'],
    approvals: [{ label: 'Sales 提交', actor: 'Demo Staff 07', status: 'Done' }, { label: 'FAE Review', actor: '演示员工23', status: 'Done' }, { label: 'Manager Approval', actor: 'Demo Staff 06', status: 'Done' }, { label: 'Customer Review', actor: '样片追加中', status: 'Current' }],
    executions: [{ id: 'DEMO-2607-03-EXE-01', tool: 'AX7-DEMO-03', window: '07-15 至 07-18', engineer: '演示员工23', status: 'Scheduled' }],
    wafers: [{ id: 'WAF-FO-112', lot: 'FO-0720', material: 'Mold / Cu', diameter: '300 mm', thickness: '680 μm', status: 'More Sample Needed' }],
    testRuns: [{ id: 'RUN-0716-C', date: '07-16', recipe: 'RDL-OPEN-v3', capture: 91.6, falsePositive: 2.8, wph: 34, result: 'Fail' }],
  },
] as unknown as DemoProject[]

export const installedTools = [
  { id: 'TOOL-001', serial: 'AX9-CN-260018', model: 'AX-9000', account: '示例企业044', site: '武汉二期 Fab', location: 'Bay A3', status: 'Production', software: '6.4.2', targetSoftware: '6.4.2', warrantyEnd: '2027-03-31', serviceLevel: '24×7 Premium', health: 94, milestones: [{ label: 'FAT', date: '2026-01-18', state: 'Done' }, { label: 'Shipment', date: '2026-02-06', state: 'Done' }, { label: 'Installation', date: '2026-02-22', state: 'Done' }, { label: 'SAT', date: '2026-03-09', state: 'Done' }, { label: 'Warranty', date: '2027-03-31', state: 'Current' }], documents: ['User Manual AX9 v6.4', 'PM Procedure AX9 R3', 'Cybersecurity Note 2026-02'] },
  { id: 'TOOL-002', serial: 'VI6-CN-250104', model: 'VI-620', account: '豪威科技', site: '上海量产中心', location: 'Line CIS-2', status: 'Upgrade Due', software: '5.8.1', targetSoftware: '6.0.0', warrantyEnd: '2026-09-12', serviceLevel: 'Business 8×5', health: 72, milestones: [{ label: 'FAT', date: '2025-07-11', state: 'Done' }, { label: 'Shipment', date: '2025-07-25', state: 'Done' }, { label: 'Installation', date: '2025-08-12', state: 'Done' }, { label: 'SAT', date: '2025-09-12', state: 'Done' }, { label: 'Warranty', date: '2026-09-12', state: 'Current' }], documents: ['VI-620 User Manual v5.8', 'Upgrade Procedure 6.0 Draft'] },
  { id: 'TOOL-003', serial: 'AX7-CN-260041', model: 'AX-7600', account: '华天科技', site: '南京先进封装基地', location: 'FOWLP Bay 6', status: 'Installation', software: '6.3.0', targetSoftware: '6.3.1', warrantyEnd: 'Pending SAT', serviceLevel: 'Installation Coverage', health: 81, milestones: [{ label: 'FAT', date: '2026-06-18', state: 'Done' }, { label: 'Shipment', date: '2026-06-29', state: 'Done' }, { label: 'Installation', date: '2026-07-18', state: 'Current' }, { label: 'SAT', date: '2026-07-29', state: 'Waiting' }, { label: 'Warranty', date: 'After SAT', state: 'Waiting' }], documents: ['AX-7600 Installation Guide R2', 'SAT Template CN-04'] },
] as unknown as InstalledTool[]

export const serviceAppointments = [
  { id: 'SVC-101', day: '周一 07-20', start: '09:00', end: '12:00', engineer: '演示员工23', account: '示例企业044', tool: 'AX9-CN-260018', type: 'Application Support', status: 'In Progress', severity: 'Normal' },
  { id: 'SVC-102', day: '周二 07-21', start: '09:30', end: '17:00', engineer: '演示员工14', account: '豪威科技', tool: 'VI6-CN-250104', type: 'Upgrade', status: 'Planned', severity: 'Warning' },
  { id: 'SVC-103', day: '周二 07-21', start: '14:00', end: '18:00', engineer: '演示员工14', account: '华天科技', tool: 'AX7-CN-260041', type: 'Installation', status: 'Conflict', severity: 'Critical', conflict: true },
  { id: 'SVC-104', day: '周三 07-22', start: '10:00', end: '12:00', engineer: '演示员工15', account: '示例企业044', tool: 'AX9-CN-260018', type: 'PM', status: 'Planned', severity: 'Normal' },
  { id: 'SVC-105', day: '周四 07-23', start: '08:30', end: '16:30', engineer: '演示员工23', account: '华天科技', tool: 'AX7-CN-260041', type: 'SAT Preparation', status: 'Planned', severity: 'Warning' },
  { id: 'SVC-106', day: '周五 07-24', start: '13:00', end: '17:00', engineer: '演示员工15', account: '豪威科技', tool: 'VI6-CN-250104', type: 'Corrective', status: 'Overdue', severity: 'Critical' },
] as unknown as ServiceAppointment[]

export const procedureRuns = [
  { id: 'PROC-2607-01', title: 'VI-620 Software 6.0 Upgrade', account: '豪威科技', tool: 'VI6-CN-250104', owner: '演示员工14', status: 'Pre-Installation Review', window: '07-21 09:30–17:00', progress: 42, templateVersion: 'UP-VI620-6.0 / R1', stages: [{ label: 'Review', state: 'Current' }, { label: 'MOC', state: 'Waiting' }, { label: 'Backup', state: 'Waiting' }, { label: 'Install', state: 'Waiting' }, { label: 'Qualification', state: 'Waiting' }, { label: 'Sign-off', state: 'Waiting' }], checklist: [
    { id: 'release-notes', title: 'Release Notes 与兼容性确认', owner: '演示员工14', mandatory: true, status: 'Passed', evidence: 'RN-6.0.pdf' },
    { id: 'moc-approval', title: '客户 MOC Approval', owner: 'Demo Staff 08', mandatory: true, status: 'Pending', evidence: '等待客户签批' },
    { id: 'backup-checksum', title: 'Mandatory Backup 与 Checksum', owner: '演示员工15', mandatory: true, status: 'Pending', evidence: '待执行' },
    { id: 'cybersecurity', title: 'Cybersecurity Review', owner: 'R&D Security', mandatory: true, status: 'Passed', evidence: 'SEC-2607-18' },
  ], attachments: ['Release-Notes-6.0.pdf', 'SEC-2607-18.pdf'], rollbackPlan: '恢复 5.8.1 全量备份，并执行 Recipe / DB checksum 验证。', signoff: { status: 'Waiting', signer: '客户设备经理', signedAt: '—' } },
  { id: 'PROC-2607-02', title: 'AX-9000 Recipe Qualification', account: '示例企业044', tool: 'AX9-CN-260018', owner: '演示员工23', status: 'Qualification', window: '07-27 08:00–18:00', progress: 78, templateVersion: 'QUAL-AX9-6.4 / R3', stages: [{ label: 'Review', state: 'Done' }, { label: 'MOC', state: 'Done' }, { label: 'Backup', state: 'Done' }, { label: 'Install', state: 'Done' }, { label: 'Qualification', state: 'Current' }, { label: 'Sign-off', state: 'Waiting' }], checklist: [{ id: 'baseline', title: 'Pre-Installation Baseline', owner: '演示员工23', mandatory: true, status: 'Passed', evidence: 'BASE-AX9-0727.zip' }, { id: 'golden-wafer', title: 'Golden Wafer Verification', owner: 'Customer QE', mandatory: true, status: 'Pending', evidence: '测试中' }], attachments: ['BASE-AX9-0727.zip', 'Qualification-Protocol.pdf'], rollbackPlan: '恢复安装前 Recipe baseline，重新载入已验证的 Golden Wafer 参数。', signoff: { status: 'Waiting', signer: 'Customer QE', signedAt: '—' } },
] as unknown as ProcedureRun[]

export const controlledDocuments = [
  { id: 'DOC-ACONCA-FSBS-EDGE', title: 'Aconca FS/BS Edge Technical Presentation', category: 'Technical', type: 'Technical Presentation', product: 'Aconca', version: '0610', revision: 'V2', status: 'Released', confidentiality: 'Restricted', access: 'Request', reviewDate: '2027-06-10', owner: 'Product Engineering', downloads: 0 },
  { id: 'DOC-NANSI-0610', title: 'Nansi Technical Presentation', category: 'Technical', type: 'Technical Presentation', product: 'Nansi', version: '0610', revision: 'V1', status: 'Released', confidentiality: 'Restricted', access: 'Request', reviewDate: '2027-06-10', owner: 'Product Engineering', downloads: 0 },
] as unknown as ControlledDocument[]

const accountLinks = [
  { accountId: 'ACC-002', siteId: 'SITE-004', opportunityId: 'OPP-003' },
  { accountId: 'ACC-001', siteId: 'SITE-001', opportunityId: 'OPP-001' },
  { accountId: 'ACC-005', siteId: 'SITE-005', opportunityId: 'OPP-007' },
]

demoProjects.forEach((project, index) => Object.assign(project, accountLinks[index], {
  contact: ['赵昕｜AOI 工艺经理', '周楠｜研发总监', '孙强｜设备经理'][index],
  industry: ['Memory / HBM', 'Foundry / CIS', 'OSAT / Advanced Packaging'][index],
  salesContact: ['Demo Staff 01', 'Demo Staff 01', 'Demo Staff 02'][index],
  waferCount: [2, 1, 1][index],
  specificRequest: ['验证 TSV 残留、边缘裂纹与微凹点检出能力', '验证 12 英寸 CIS 表面颗粒、划伤与 Pattern 缺陷分类', '验证 Fan-out RDL 断线和 Via 开口缺陷量产窗口'][index],
  detectMeasure: ['Capture、False Positive、WPH', 'Capture、False Positive、Golden Sample 一致性', 'Capture、WPH、复核一致率'][index],
  expectedResults: project.successFactors.join(' · '),
  otherTools: ['KLA benchmark', 'Onto benchmark', 'Local AOI benchmark'][index],
  complementaryTool: ['SEM review station', 'Golden sample library', 'Offline review station'][index],
  internalQuestions: [['客户最终预算何时批准？', '量产 recipe 是否需要现场联合优化？'], ['第二批样片物流何时确认？'], ['客户是否补充更多 RDL 开路样片？']][index],
  customerQuestions: [['误报样本如何闭环？', '报告能否按 lot 导出？'], ['Golden Sample 判定口径是否一致？'], ['失效样本是否可重新扫描？']][index],
  preparedBy: project.owner,
  approvedBy: 'Demo Staff 06 / Manager',
  conclusion: [
    { status: 'Accepted', summary: '主要技术指标达到客户门槛，进入商务与量产 recipe 对齐。', customerFeedback: '认可检出率，要求补充 lot 级报告。', confirmedBy: '赵昕', confirmedAt: '2026-07-20', followUpAction: '准备最终商务让步边界' },
    { status: 'Pending', summary: '等待第二批样片完成复测。', customerFeedback: '首轮结果可接受，需补齐 Golden Sample。', confirmedBy: '', confirmedAt: '', followUpAction: '确认第二批样片物流' },
    { status: 'Pending', summary: '当前样本量不足，暂不能形成量产结论。', customerFeedback: '客户同意追加样片。', confirmedBy: '孙强', confirmedAt: '2026-07-18', followUpAction: '更新竞争报价分析' },
  ][index],
}))

installedTools.forEach((tool, index) => Object.assign(tool, accountLinks[index], {
  sourceOpportunityId: accountLinks[index].opportunityId,
  salesOrder: ['SO-260018', 'SO-250104', 'SO-260041'][index],
  contract: ['CTR-2026-018', 'CTR-2025-104', 'CTR-2026-041'][index],
  warrantyStart: ['2026-03-09', '2025-09-12', 'Pending SAT'][index],
  serviceContract: ['Premium 24x7', 'Business 8x5', 'Installation Coverage'][index],
  pmCycle: ['Quarterly', 'Semiannual', 'After SAT'][index],
  lastService: ['2026-06-22', '2026-03-18', '2026-07-18'][index],
  operatingSystem: ['Rocky Linux 9', 'Windows 11 IoT', 'Rocky Linux 9'][index],
  configuration: ['2 cameras · 300 mm · HBM recipe pack', '1 camera · 300 mm · CIS recipe pack', '2 cameras · 300 mm · FOWLP pack'][index],
  ownershipType: ['Customer Owned', 'Customer Owned', 'Customer Owned'][index],
}))

serviceAppointments.forEach((appointment, index) => {
  const linkIndex = appointment.tool.startsWith('AX9') ? 0 : appointment.tool.startsWith('VI6') ? 1 : 2
  Object.assign(appointment, accountLinks[linkIndex], {
    contact: ['赵昕', '周楠', '孙强'][linkIndex],
    issue: `${appointment.type}：${appointment.tool} 现场任务`,
    priority: appointment.severity === 'Critical' ? 'P1' : appointment.severity === 'Warning' ? 'P2' : 'P3',
    downtime: appointment.severity === 'Critical' ? '4h estimated' : 'No production stop',
    actualWindow: appointment.status === 'In Progress' ? `${appointment.start}–进行中` : 'Pending execution',
    rootCause: appointment.type === 'Corrective' ? 'Recipe service timeout under review' : 'Planned service activity',
    actionsPerformed: appointment.status === 'In Progress' ? '完成基线采集与参数复核' : '待工程师执行',
    spares: appointment.type === 'PM' ? 'Filter kit ×1' : 'None',
    laborHours: appointment.status === 'In Progress' ? 2.5 : 0,
    attachments: appointment.status === 'In Progress' ? [`${appointment.id}-baseline.zip`] : [],
    result: appointment.status === 'In Progress' ? 'Baseline passed; monitoring continues' : 'Pending',
    nextAction: appointment.conflict ? 'Service Manager 重新排期' : '按计划执行并获取客户签字',
    customerSignoff: appointment.status === 'In Progress' ? 'Pending customer sign-off' : 'Not started',
  })
})

procedureRuns.forEach((run, index) => {
  const linkIndex = index === 0 ? 1 : 0
  Object.assign(run, accountLinks[linkIndex], {
    qualificationResult: index === 0 ? 'Pending installation and qualification' : 'Baseline passed; Golden Wafer pending',
    deviation: index === 0 ? 'No deviation raised' : 'Golden Wafer review delayed by customer schedule',
    deviationApprover: index === 0 ? 'N/A' : 'Customer QE / Demo Staff 06',
    rollbackResult: 'Rollback plan reviewed; no rollback executed',
  })
  run.checklist.forEach((item) => Object.assign(item, {
    executedAt: item.status === 'Passed' ? '2026-07-20 14:30' : '',
    reviewer: item.status === 'Passed' ? 'Service Manager' : '',
    reviewedAt: item.status === 'Passed' ? '2026-07-20 16:00' : '',
    notes: item.status === 'Passed' ? 'Evidence verified' : 'Awaiting execution evidence',
  }))
})

controlledDocuments.forEach((doc, index) => Object.assign(doc, {
  applicableTool: doc.product,
  versions: [
    { version: doc.version, revision: doc.revision, status: 'Released', releasedAt: '2026-07-15', checksum: `SHA256-${doc.id}-CURRENT` },
    { version: doc.version, revision: 'R0', status: 'Superseded', releasedAt: '2026-02-10', checksum: `SHA256-${doc.id}-R0` },
  ],
  audit: [{ id: `DL-${index + 1}-001`, employee: 'Demo Staff 01', at: '2026-07-18 10:20', reason: 'Customer meeting preparation', version: `${doc.version}/${doc.revision}` }],
}))
