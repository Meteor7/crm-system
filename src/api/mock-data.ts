import type {
  AccountSummaryDto,
  ActionDto,
  BookingDto,
  ContactDto,
  ContractDto,
  DemoRequestDto,
  EvaluationDto,
  OpportunityDto,
  RequirementDto,
  SiteDto,
  VisitDto,
} from '@/types/crm'

export const accounts: AccountSummaryDto[] = [
  { id: 'ACC-001', name: '示例企业014有限公司', shortName: 'CUSTOMER06', segment: 'Frontend', tier: 'S', city: '上海', region: 'East China', owner: 'Demo Staff 01', pipelineAmount: 28600000, intentScore: 88, stakeholderCount: 4, siteCount: 2, requirementCount: 2, completeness: 94, risk: '稳健', nextAction: '确认缺陷检测 Demo wafer 规格', nextActionDue: '2026-07-18', updatedAt: '今天 09:42' },
  { id: 'ACC-002', name: '示例企业044有限公司', shortName: 'CUSTOMER07', segment: 'Frontend', tier: 'S', city: '武汉', region: 'Central China', owner: 'Demo Staff 01', pipelineAmount: 46800000, intentScore: 92, stakeholderCount: 5, siteCount: 2, requirementCount: 2, completeness: 88, risk: '关注', nextAction: '补充预算审批材料并锁定评审会', nextActionDue: '2026-07-16', updatedAt: '昨天 17:20' },
  { id: 'ACC-003', name: '示例企业003有限公司', shortName: 'CUSTOMER02', segment: 'Frontend', tier: 'A', city: '上海', region: 'East China', owner: 'Demo Staff 02', pipelineAmount: 18200000, intentScore: 72, stakeholderCount: 3, siteCount: 2, requirementCount: 1, completeness: 82, risk: '稳健', nextAction: '准备量测设备技术澄清清单', nextActionDue: '2026-07-22', updatedAt: '7月15日' },
  { id: 'ACC-004', name: '示例企业045有限公司', shortName: 'CUSTOMER01', segment: 'Frontend', tier: 'A', city: '合肥', region: 'East China', owner: 'Demo Staff 01', pipelineAmount: 35500000, intentScore: 84, stakeholderCount: 3, siteCount: 1, requirementCount: 1, completeness: 76, risk: '关注', nextAction: '确认新厂设备入场窗口', nextActionDue: '2026-07-20', updatedAt: '7月15日' },
  { id: 'ACC-005', name: '示例企业040有限公司', shortName: 'CUSTOMER05', segment: 'Advanced Packaging', tier: 'B', city: '南通', region: 'East China', owner: 'Demo Staff 02', pipelineAmount: 12600000, intentScore: 67, stakeholderCount: 2, siteCount: 1, requirementCount: 1, completeness: 71, risk: '关注', nextAction: '补齐先进封装应用与预算信息', nextActionDue: '2026-07-19', updatedAt: '7月14日' },
  { id: 'ACC-006', name: '示例企业027有限公司', shortName: 'CUSTOMER04', segment: 'Advanced Packaging', tier: 'S', city: '江阴', region: 'East China', owner: 'Demo Staff 02', pipelineAmount: 29800000, intentScore: 86, stakeholderCount: 4, siteCount: 2, requirementCount: 1, completeness: 91, risk: '稳健', nextAction: '提交高速 AOI 产能测算', nextActionDue: '2026-07-21', updatedAt: '7月14日' },
  { id: 'ACC-007', name: '示例企业018有限公司', shortName: 'CUSTOMER03', segment: 'Advanced Packaging', tier: 'B', city: '天水', region: 'West China', owner: 'Demo Staff 02', pipelineAmount: 8800000, intentScore: 58, stakeholderCount: 1, siteCount: 1, requirementCount: 1, completeness: 63, risk: '高风险', nextAction: '重新确认项目优先级与预算来源', nextActionDue: '2026-07-15', updatedAt: '7月13日' },
]

export const sites: Record<string, SiteDto[]> = {
  'ACC-001': [
    { id: 'SITE-001', name: '南京 12-inch Fab', city: '南京', type: '晶圆制造', process: '16/28nm', status: '量产' },
    { id: 'SITE-002', name: '上海研发中心', city: '上海', type: '研发', process: '先进制程', status: '量产' },
  ],
  'ACC-002': [
    { id: 'SITE-003', name: '武汉一厂', city: '武汉', type: '存储晶圆制造', process: '3D NAND', status: '量产' },
    { id: 'SITE-004', name: '武汉二期', city: '武汉', type: '扩产项目', process: '3D NAND', status: '建设中' },
  ],
  'ACC-003': [
    { id: 'SITE-007', name: '上海 Fab 7', city: '上海', type: '晶圆制造', process: '90/55nm', status: '量产' },
    { id: 'SITE-008', name: '无锡研发中心', city: '无锡', type: '研发', process: '量测验证', status: '量产' },
  ],
  'ACC-005': [
    { id: 'SITE-005', name: '南通工厂', city: '南通', type: '先进封装', process: '2.5D/3D', status: '量产' },
  ],
  'ACC-006': [
    { id: 'SITE-006', name: '演示员工27', city: '江阴', type: '先进封装', process: '高速 AOI', status: '量产' },
  ],
}

const legacyContacts = {
  'ACC-001': [
    { id: 'CON-001', name: '演示员工36', title: '设备采购总监', department: '采购中心', role: 'Economic Buyer', influence: 'High', relationship: 'Strong' },
    { id: 'CON-002', name: '演示员工22', title: '良率提升负责人', department: '制程整合', role: 'Technical Champion', influence: 'High', relationship: 'Developing' },
    { id: 'CON-003', name: '演示员工14', title: '厂务副总经理', department: '制造运营', role: 'Decision Maker', influence: 'High', relationship: 'Developing' },
  ],
  'ACC-002': [
    { id: 'CON-004', name: '演示员工31', title: '采购经理', department: '采购部', role: 'Economic Buyer', influence: 'High', relationship: 'Strong' },
    { id: 'CON-005', name: '演示员工33', title: '设备工程负责人', department: '设备工程', role: 'Technical Champion', influence: 'High', relationship: 'Strong' },
  ],
  'ACC-003': [
    { id: 'CON-006', name: '演示员工17', title: '量测工程负责人', department: '设备工程', role: 'Technical Champion', influence: 'High', relationship: 'Developing' },
  ],
  'ACC-004': [
    { id: 'CON-007', name: '演示员工11', title: '设备验证负责人', department: '设备工程', role: 'Technical Champion', influence: 'High', relationship: 'Developing' },
  ],
  'ACC-005': [
    { id: 'CON-008', name: '演示员工20', title: '先进封装项目经理', department: '工程中心', role: 'Decision Maker', influence: 'High', relationship: 'Strong' },
  ],
  'ACC-006': [
    { id: 'CON-009', name: '演示员工35', title: 'AOI 项目负责人', department: '产品工程', role: 'Technical Champion', influence: 'High', relationship: 'Strong' },
  ],
  'ACC-007': [
    { id: 'CON-010', name: '演示员工34', title: '测试设备负责人', department: '设备工程', role: 'Technical Champion', influence: 'High', relationship: 'Developing' },
  ],
}

export const contacts: ContactDto[] = Object.entries(legacyContacts).flatMap(([accountId, rows]) => {
  const owner = accounts.find((account) => account.id === accountId)?.owner ?? ''
  return rows.map(({ role: _role, influence: _influence, ...contact }) => ({
    ...contact,
    accountId,
    relationship: contact.relationship as ContactDto['relationship'],
    owner,
    status: 'Active' as const,
    dataQuality: 'Complete' as const,
    updatedAt: '2026-07-28',
  }))
})

export const requirements: RequirementDto[] = [
  { id: 'REQ-001', accountId: 'ACC-001', accountName: '示例企业014有限公司', title: '晶圆表面缺陷检测扩容', category: '检测设备', equipment: 'Macro Inspection X8', application: '晶圆表面缺陷检测', site: '南京 12-inch Fab', quantity: 2, budgetAmount: 16800000, budgetStatus: 'Confirmed', status: 'Demo验证', completeness: 96, owner: 'person002@crm.example.invalid', nextAction: '确认 Demo wafer 与验收阈值', due: '2026-07-18', linkedDealId: 'OPP-001', linkedEvaluationId: 'EVAL-101' },
  { id: 'REQ-002', accountId: 'ACC-001', accountName: '示例企业014有限公司', title: '良率分析软件升级', category: '软件与升级', equipment: 'YieldMind 4.0', application: '缺陷归因与良率分析', site: '上海研发中心', quantity: 1, budgetAmount: 4200000, budgetStatus: 'In Review', status: '技术确认', completeness: 84, owner: 'person002@crm.example.invalid', nextAction: '完成数据接口清单', due: '2026-07-25', linkedDealId: 'OPP-002' },
  { id: 'REQ-003', accountId: 'ACC-002', accountName: '示例企业044有限公司', title: '存储晶圆缺陷检测新线', category: '检测设备', equipment: 'NanoScan Pro', application: '3D NAND 缺陷检测', site: '武汉二期', quantity: 3, budgetAmount: 32500000, budgetStatus: 'In Review', status: '预算审批', completeness: 89, owner: 'person002@crm.example.invalid', nextAction: '补充 ROI 与产能提升说明', due: '2026-07-16', linkedDealId: 'OPP-003' },
  { id: 'REQ-004', accountId: 'ACC-003', accountName: '示例企业003有限公司', title: '关键尺寸量测替换', category: '量测设备', equipment: 'CD Metrology M5', application: '90/55nm CD 量测', site: '无锡 Fab 7', quantity: 1, budgetAmount: 11200000, budgetStatus: 'Unknown', status: '技术确认', completeness: 74, owner: 'person005@crm.example.invalid', nextAction: '澄清 GR&R 指标', due: '2026-07-22', linkedDealId: 'OPP-004' },
  { id: 'REQ-005', accountId: 'ACC-004', accountName: '示例企业045有限公司', title: '新厂 AOI 导入计划', category: '检测设备', equipment: 'AOI Matrix 900', application: '先进存储封装检测', site: '合肥二厂', quantity: 2, budgetAmount: 24800000, budgetStatus: 'In Review', status: '采购计划', completeness: 78, owner: 'person002@crm.example.invalid', nextAction: '确认入场窗口与厂务条件', due: '2026-07-20', linkedDealId: 'OPP-005' },
  { id: 'REQ-006', accountId: 'ACC-005', accountName: '示例企业040有限公司', title: '先进封装外观检测', category: '检测设备', equipment: 'PackageVision P7', application: '2.5D/3D 封装外观检测', site: '南通工厂', quantity: 1, budgetAmount: 7600000, budgetStatus: 'Unknown', status: '需求识别', completeness: 62, owner: 'person005@crm.example.invalid', nextAction: '补齐预算与采购时间', due: '2026-07-19' },
  { id: 'REQ-007', accountId: 'ACC-006', accountName: '示例企业027有限公司', title: '高速 AOI 产能升级', category: '检测设备', equipment: 'FastScan 1200', application: '高密度封装在线检测', site: '演示员工27', quantity: 2, budgetAmount: 18800000, budgetStatus: 'Confirmed', status: '已确认', completeness: 93, owner: 'person005@crm.example.invalid', nextAction: '安排交付启动会', due: '2026-07-21', linkedDealId: 'OPP-006' },
  { id: 'REQ-008', accountId: 'ACC-007', accountName: '示例企业018有限公司', title: '测试设备升级评估', category: '软件与升级', equipment: 'TestFlow Suite', application: '测试数据闭环', site: '天水基地', quantity: 1, budgetAmount: 3600000, budgetStatus: 'Unknown', status: '需求识别', completeness: 55, owner: 'person005@crm.example.invalid', nextAction: '重新确认项目优先级', due: '2026-07-15' },
]

export const opportunities: OpportunityDto[] = [
  { id: 'OPP-001', accountId: 'ACC-001', accountName: '示例企业014有限公司', title: '南京缺陷检测设备 2 台', segment: 'Frontend', amount: '16800000.00', currency: 'CNY', stage: 'qualified_opportunity', probabilityLevel: 'upside', intentScore: 88, budgetStatus: 'Confirmed', owner: 'Demo Staff 01', nextAction: '确认 Demo wafer 与指标', due: '2026-07-18', sourceRequirementId: 'REQ-001' },
  { id: 'OPP-002', accountId: 'ACC-001', accountName: '示例企业014有限公司', title: 'YieldMind 软件升级', segment: 'Frontend', amount: '4200000.00', currency: 'CNY', stage: 'qualified_opportunity', probabilityLevel: '', intentScore: 74, budgetStatus: 'In Review', owner: 'Demo Staff 01', nextAction: '确认数据接口', due: '2026-07-25', sourceRequirementId: 'REQ-002' },
  { id: 'OPP-003', accountId: 'ACC-002', accountName: '示例企业044有限公司', title: '武汉二期缺陷检测新线', segment: 'Frontend', amount: '32500000.00', currency: 'CNY', stage: 'demo_done', probabilityLevel: 'committed', intentScore: 92, budgetStatus: 'In Review', owner: 'Demo Staff 01', nextAction: '推进预算评审', due: '2026-07-16', sourceRequirementId: 'REQ-003' },
  { id: 'OPP-004', accountId: 'ACC-003', accountName: '示例企业003有限公司', title: '关键尺寸量测替换', segment: 'Frontend', amount: '11200000.00', currency: 'CNY', stage: 'qualified_opportunity', probabilityLevel: '', intentScore: 72, budgetStatus: 'Unknown', owner: 'Demo Staff 02', nextAction: '提交 GR&R 测试方案', due: '2026-07-22', sourceRequirementId: 'REQ-004' },
  { id: 'OPP-005', accountId: 'ACC-004', accountName: '示例企业045有限公司', title: '合肥二厂 AOI 项目', segment: 'Frontend', amount: '24800000.00', currency: 'CNY', stage: 'quotation_sent', probabilityLevel: 'pipeline', intentScore: 84, budgetStatus: 'Confirmed', owner: 'Demo Staff 01', nextAction: '确认合同条款', due: '2026-07-20', sourceRequirementId: 'REQ-005' },
  { id: 'OPP-006', accountId: 'ACC-006', accountName: '示例企业027有限公司', title: '高速 AOI 产能升级', segment: 'Advanced Packaging', amount: '18800000.00', currency: 'CNY', stage: 'po_received', probabilityLevel: '', intentScore: 86, budgetStatus: 'Confirmed', owner: 'Demo Staff 02', nextAction: '交付启动', due: '2026-07-21', sourceRequirementId: 'REQ-007' },
  { id: 'OPP-007', accountId: 'ACC-005', accountName: '示例企业040有限公司', title: '先进封装外观检测', segment: 'Advanced Packaging', amount: '7600000.00', currency: 'CNY', stage: 'qualified_opportunity', probabilityLevel: '', intentScore: 67, budgetStatus: 'Unknown', owner: 'Demo Staff 02', nextAction: '补齐预算信息', due: '2026-07-19', sourceRequirementId: 'REQ-006' },
]

export const bookings: BookingDto[] = [
  { id: 'BKG-001', accountId: 'ACC-006', accountName: '示例企业027有限公司', title: 'FastScan 1200 · 2 台', customerContact: '演示员工20', equipment: 'FastScan 1200', quantity: 2, ddl: '2026-08-28', amount: '18800000.00', currency: 'CNY', status: 'Confirmed', bookingDate: '2026-07-02', actualPoDate: '2026-07-02', actualPoDateSource: 'po_confirmation', owner: 'Demo Staff 02', source: 'Opportunity', bookingType: 'Equipment', sourceOpportunityId: 'OPP-006', note: '客户要求八月底前确认交付窗口。' },
  { id: 'BKG-002', accountId: 'ACC-003', accountName: '示例企业003有限公司', title: '服务扩展 · 1 项', customerContact: '演示员工17', equipment: 'Service Expansion Kit', quantity: 1, ddl: '2026-09-15', amount: '3600000.00', currency: 'CNY', status: 'Confirmed', bookingDate: '2026-06-24', owner: 'Demo Staff 02', source: 'Upsell', bookingType: 'Service', sourceOpportunityId: '', note: '现有客户服务订单，不经过新 Opportunity。' },
  // Created by the approved internal validation CRM-VAL-00001; it becomes Confirmed when the PO arrives.
  { id: 'BKG-003', accountId: 'ACC-002', accountName: '示例企业044有限公司', title: 'CD Metrology M5 · 2 台', customerContact: '演示员工31', equipment: 'CD Metrology M5', quantity: 2, ddl: '2026-10-30', amount: '21600000.00', currency: 'CNY', status: 'Pending', bookingDate: '2026-07-20', owner: 'Demo Staff 01', source: 'Opportunity', bookingType: 'Equipment', sourceOpportunityId: 'OPP-008', note: '内部生产审批已批准，等待客户 PO 后确认。' },
].map((booking) => ({ ...booking, primaryContactId: '' } as BookingDto))

const demoProgressOverrides: Record<string, string> = {
  'DR-101': '2026-07-28T09:00:00+08:00',
  'DR-102': '2026-07-21T10:00:00+08:00',
  'DR-103': '2026-07-27T14:00:00+08:00',
  'DR-104': '2026-07-28T09:30:00+08:00',
  'DR-105': '2026-07-28T10:00:00+08:00',
  'DR-106': '2026-07-20T16:00:00+08:00',
  'DR-107': '2026-07-28T11:00:00+08:00',
  'DR-108': '2026-07-28T13:00:00+08:00',
  'DR-109': '2026-07-24T15:00:00+08:00',
  'DR-110': '2026-07-23T15:00:00+08:00',
}

function withDemoRequestDefaults(requests: Array<Omit<DemoRequestDto, 'customerExpectedDate' | 'tracking' | 'primaryContactId' | 'requestMode'>>): DemoRequestDto[] {
  return requests.map((request) => {
    const primaryContact = contacts.find((contact) => contact.accountId === request.accountId && contact.status === 'Active')
    return {
      ...request,
      requestMode: request.opportunityId ? 'Opportunity' : 'Self Test',
      primaryContactId: primaryContact?.id ?? '',
      customerExpectedDate: request.targetDate,
      formData: request.formData ?? {
        contactPerson: primaryContact ? `${primaryContact.name} · ${primaryContact.title}` : `${request.accountName} Demo Contact`,
        industry: request.segment,
        salesContact: request.salesOwner,
        demoOwner: request.engineerOwner || 'FAE Team',
        sizeShape: '300 mm full wafer',
        material: request.sampleType || 'Silicon',
        specificRequest: request.objective,
        detectMeasure: request.objective,
        expectedResults: request.acceptanceCriteria,
        otherTools: 'Customer tool of record to be confirmed',
        primaryTool: request.requestedEquipment,
        complementaryTool: '',
        timing: request.targetDate,
        keySuccessFactors: request.acceptanceCriteria,
        internalQuestions: request.engineerComment || 'Confirm sample readiness and resource window',
        customerQuestions: 'Confirm sample delivery date and expected output format',
        wafers: [{
          slotId: '1',
          wid: `${request.id}-W01`,
          waferSpecificity: request.sampleType || 'Silicon wafer',
          notchFlat: 'Notch up',
          doiMetrologyItems: request.objective,
          resultFileProvided: 'Wafer map and report PDF',
        }],
      },
      tracking: {
        lastProgressAt: demoProgressOverrides[request.id] ?? request.updatedAt,
        lastProgressSummary: request.history.at(-1)?.comment || '创建 Demo Request',
        lastProgressActor: request.history.at(-1)?.actor || request.createdBy,
        nextAction: '',
        nextActionOwner: '',
        nextActionDue: '',
      },
    }
  })
}

function withEvaluationDefaults(evaluations: Array<Omit<EvaluationDto, 'testRunDeadline' | 'reportStatus' | 'reportVersion' | 'testRound'>>): EvaluationDto[] {
  return evaluations.map((evaluation) => ({
    ...evaluation,
    testRunDeadline: evaluation.plannedEnd,
    reportStatus: 'Not Ready',
    reportVersion: 0,
    testRound: 1,
  }))
}

export const demoRequests = withDemoRequestDefaults([
  {
    id: 'DR-101', accountId: 'ACC-001', accountName: '示例企业014有限公司', requirementId: 'REQ-001', opportunityId: 'OPP-001',
    segment: 'Frontend', salesOwner: 'Demo Staff 01', createdBy: 'Demo Staff 01', title: '南京 CD 量测重复性验证',
    objective: '验证先进制程 CD 量测重复性与节拍', requestedEquipment: 'CD Metrology M5', sampleType: 'Patterned wafer',
    sampleQuantity: 8, targetDate: '2026-08-20', priority: 'High', acceptanceCriteria: '3σ ≤ 0.5nm；达到约定 WPH',
    status: 'Engineer Review', engineerOwner: '演示员工14', feasibility: 'Pending', testPlan: '', assignedEquipment: '',
    resourceWindow: '', estimatedCompletionDate: '', technicalRisk: '', engineerComment: '', managerDecision: '',
    managerComment: '', createdAt: '2026-07-27T09:00:00+08:00', updatedAt: '2026-07-28T09:00:00+08:00',
    history: [{ at: '2026-07-28T09:00:00+08:00', actor: 'Demo Staff 01', from: 'Draft', to: 'Engineer Review', comment: '提交演示员工14进行工程评估' }],
  },
  {
    id: 'DR-102', accountId: 'ACC-005', accountName: '示例企业040有限公司', requirementId: 'REQ-006', opportunityId: 'OPP-007',
    segment: 'Advanced Packaging', salesOwner: 'Demo Staff 02', createdBy: 'Demo Staff 02', title: '南通 2.5D 封装缺陷检测',
    objective: '验证 2.5D interposer 与 micro-bump 缺陷捕获能力', requestedEquipment: 'PackageVision P7',
    sampleType: '2.5D interposer wafer', sampleQuantity: 12, targetDate: '2026-08-18', priority: 'High',
    acceptanceCriteria: 'Capture ≥ 95%；False Positive ≤ 3%', status: 'Engineer Review', engineerOwner: '演示员工15',
    feasibility: 'Pending', testPlan: '', assignedEquipment: '', resourceWindow: '', estimatedCompletionDate: '',
    technicalRisk: '', engineerComment: '', managerDecision: '', managerComment: '',
    createdAt: '2026-07-20T10:00:00+08:00', updatedAt: '2026-07-21T10:00:00+08:00',
    history: [{ at: '2026-07-21T10:00:00+08:00', actor: 'Demo Staff 02', from: 'Draft', to: 'Engineer Review', comment: '提交演示员工15进行设备验证评估' }],
  },
  {
    id: 'DR-103', accountId: 'ACC-003', accountName: '示例企业003有限公司', opportunityId: 'OPP-004', segment: 'Frontend',
    salesOwner: 'Demo Staff 02', createdBy: 'Demo Staff 02', title: '上海功率器件表面缺陷验证', objective: '确认功率器件晶圆表面缺陷覆盖率',
    requestedEquipment: 'Macro Inspection X8', sampleType: 'Power device wafer', sampleQuantity: 6, targetDate: '2026-08-25',
    priority: 'Medium', acceptanceCriteria: '覆盖客户缺陷库并输出 gap list', status: 'Manager Approval', engineerOwner: '演示员工14',
    feasibility: 'Feasible', testPlan: '完成基线 recipe 与缺陷库回放', assignedEquipment: 'Macro Inspection Lab-01',
    resourceWindow: '2026-08-03 ~ 2026-08-12', estimatedCompletionDate: '2026-08-18', technicalRisk: '缺陷坐标需要客户复核',
    engineerComment: '资源窗口可支持，建议批准。', managerDecision: 'Pending', managerComment: '',
    createdAt: '2026-07-24T11:00:00+08:00', updatedAt: '2026-07-27T14:00:00+08:00',
    history: [
      { at: '2026-07-25T09:00:00+08:00', actor: 'Demo Staff 02', from: 'Draft', to: 'Engineer Review', comment: '提交工程评估' },
      { at: '2026-07-27T14:00:00+08:00', actor: '演示员工14', from: 'Engineer Review', to: 'Manager Approval', comment: '工程确认可执行' },
    ],
  },
  {
    id: 'DR-104', accountId: 'ACC-006', accountName: '示例企业027有限公司', requirementId: 'REQ-007', opportunityId: 'OPP-006',
    segment: 'Advanced Packaging', salesOwner: 'Demo Staff 01', createdBy: 'Demo Staff 01', title: '江阴高速 AOI Benchmark',
    objective: '验证高密度封装在线检测能力', requestedEquipment: 'FastScan 1200', sampleType: 'Post-bond chiplet wafer',
    sampleQuantity: 10, targetDate: '2026-08-22', priority: 'High', acceptanceCriteria: 'Capture ≥ 93%；输出误报 Pareto',
    status: 'Manager Approval', engineerOwner: '演示员工15', feasibility: 'Feasible', testPlan: '两批样片完成基线与优化 recipe 测试',
    assignedEquipment: 'FastScan Lab-02', resourceWindow: '2026-08-01 ~ 2026-08-12', estimatedCompletionDate: '2026-08-16',
    technicalRisk: '客户样片到货时间可能变化', engineerComment: '设备和人员窗口可支持，建议批准。',
    managerDecision: 'Pending', managerComment: '', createdAt: '2026-07-25T09:30:00+08:00', updatedAt: '2026-07-28T09:30:00+08:00',
    history: [
      { at: '2026-07-26T09:30:00+08:00', actor: 'Demo Staff 01', from: 'Draft', to: 'Engineer Review', comment: '提交设备验证评估' },
      { at: '2026-07-28T09:30:00+08:00', actor: '演示员工15', from: 'Engineer Review', to: 'Manager Approval', comment: '设备窗口与夹具已确认' },
    ],
  },
  {
    id: 'DR-105', accountId: 'ACC-001', accountName: '示例企业014有限公司', requirementId: 'REQ-001', opportunityId: 'OPP-001',
    segment: 'Frontend', salesOwner: 'Demo Staff 01', createdBy: 'Demo Staff 01', title: '先进制程缺陷复检准备',
    objective: '准备 patterned wafer 缺陷复检测试', requestedEquipment: 'Macro Inspection X8', sampleType: 'Patterned wafer',
    sampleQuantity: 8, targetDate: '2026-08-16', priority: 'High', acceptanceCriteria: 'Capture ≥ 96%；FP ≤ 3%',
    status: 'Converted', engineerOwner: '演示员工14', feasibility: 'Feasible', testPlan: '完成样片接收、recipe 建立和 golden run',
    assignedEquipment: 'Macro Inspection Lab-02', resourceWindow: '2026-07-29 ~ 2026-08-10', estimatedCompletionDate: '2026-08-14',
    technicalRisk: '客户缺陷坐标需脱敏', engineerComment: '已确认设备与人员窗口。', managerDecision: 'Approved',
    managerComment: '批准进入 Demo Test。', evaluationId: 'EVAL-101', createdAt: '2026-07-22T10:00:00+08:00',
    updatedAt: '2026-07-28T10:00:00+08:00',
    history: [
      { at: '2026-07-23T10:00:00+08:00', actor: 'Demo Staff 01', from: 'Draft', to: 'Engineer Review', comment: '提交工程评估' },
      { at: '2026-07-25T10:00:00+08:00', actor: '演示员工14', from: 'Engineer Review', to: 'Manager Approval', comment: '工程确认可执行' },
      { at: '2026-07-28T10:00:00+08:00', actor: '演示经理01', from: 'Manager Approval', to: 'Converted', comment: '批准并生成 Demo Test EVAL-101' },
    ],
  },
  {
    id: 'DR-106', accountId: 'ACC-004', accountName: '示例企业045有限公司', segment: 'Frontend',
    salesOwner: 'Demo Staff 02', createdBy: 'Demo Staff 02', title: 'DRAM 晶圆边缘缺陷验证', objective: '验证晶圆边缘崩边与污染检测能力',
    requestedEquipment: 'EdgeInspect E6', sampleType: '300 mm DRAM wafer', sampleQuantity: 6, targetDate: '2026-08-28',
    priority: 'Medium', acceptanceCriteria: '边缘缺陷检出率 ≥ 95%', status: 'Converted', engineerOwner: '演示员工15',
    feasibility: 'Feasible', testPlan: '完成夹具确认、样片验收和边缘 recipe 建立', assignedEquipment: 'EdgeInspect Lab-01',
    resourceWindow: '2026-08-02 ~ 2026-08-18', estimatedCompletionDate: '2026-08-22', technicalRisk: '样片翘曲需确认',
    engineerComment: '样片已接收，等待设备排期。', managerDecision: 'Approved', managerComment: '批准进入 Demo Test。',
    evaluationId: 'EVAL-102', createdAt: '2026-07-16T16:00:00+08:00', updatedAt: '2026-07-20T16:00:00+08:00',
    history: [
      { at: '2026-07-17T16:00:00+08:00', actor: 'Demo Staff 02', from: 'Draft', to: 'Engineer Review', comment: '提交设备验证评估' },
      { at: '2026-07-19T16:00:00+08:00', actor: '演示员工15', from: 'Engineer Review', to: 'Manager Approval', comment: '设备和夹具可支持' },
      { at: '2026-07-20T16:00:00+08:00', actor: '演示经理01', from: 'Manager Approval', to: 'Converted', comment: '批准并生成 Demo Test EVAL-102' },
    ],
  },
  {
    id: 'DR-107', accountId: 'ACC-006', accountName: '示例企业027有限公司', requirementId: 'REQ-007', opportunityId: 'OPP-006',
    segment: 'Advanced Packaging', salesOwner: 'Demo Staff 02', createdBy: 'Demo Staff 02', title: 'Chiplet Final Inspection 执行',
    objective: '完成客户 chiplet wafer benchmark', requestedEquipment: 'FastScan 1200', sampleType: 'Chiplet wafer',
    sampleQuantity: 10, targetDate: '2026-08-02', priority: 'Critical', acceptanceCriteria: 'Capture ≥ 93%；False Positive ≤ 4%',
    status: 'Converted', engineerOwner: '演示员工14', feasibility: 'Feasible', testPlan: '客户样片 benchmark 与误报分析',
    assignedEquipment: 'FastScan Lab-01', resourceWindow: '2026-07-26 ~ 2026-08-01', estimatedCompletionDate: '2026-08-01',
    technicalRisk: '交期紧迫', engineerComment: '正在执行第二批样片。', managerDecision: 'Approved',
    managerComment: '批准进入 Demo Test。', evaluationId: 'EVAL-103', createdAt: '2026-07-21T11:00:00+08:00',
    updatedAt: '2026-07-28T11:00:00+08:00',
    history: [
      { at: '2026-07-22T11:00:00+08:00', actor: 'Demo Staff 02', from: 'Draft', to: 'Engineer Review', comment: '提交工程评估' },
      { at: '2026-07-24T11:00:00+08:00', actor: '演示员工14', from: 'Engineer Review', to: 'Manager Approval', comment: '工程确认可执行' },
      { at: '2026-07-25T11:00:00+08:00', actor: '演示经理01', from: 'Manager Approval', to: 'Converted', comment: '批准并生成 Demo Test EVAL-103' },
    ],
  },
  {
    id: 'DR-108', accountId: 'ACC-005', accountName: '示例企业040有限公司', requirementId: 'REQ-006', opportunityId: 'OPP-007',
    segment: 'Advanced Packaging', salesOwner: 'Demo Staff 01', createdBy: 'Demo Staff 01', title: 'Micro-bump 检测客户评审',
    objective: '完成 micro-bump 检测结果客户评审', requestedEquipment: 'PackageVision P7', sampleType: 'Micro-bump wafer',
    sampleQuantity: 8, targetDate: '2026-08-01', priority: 'Critical', acceptanceCriteria: 'Capture ≥ 95%；False Positive ≤ 3%',
    status: 'Converted', engineerOwner: '演示员工15', feasibility: 'Feasible', testPlan: '基线测试、recipe 优化与客户结果评审',
    assignedEquipment: 'PackageVision Lab-01', resourceWindow: '2026-07-18 ~ 2026-07-28', estimatedCompletionDate: '2026-07-30',
    technicalRisk: '客户评审窗口固定', engineerComment: '结果已完成，等待客户确认。', managerDecision: 'Approved',
    managerComment: '批准进入 Demo Test。', evaluationId: 'EVAL-104', createdAt: '2026-07-15T13:00:00+08:00',
    updatedAt: '2026-07-28T13:00:00+08:00',
    history: [
      { at: '2026-07-16T13:00:00+08:00', actor: 'Demo Staff 01', from: 'Draft', to: 'Engineer Review', comment: '提交设备验证评估' },
      { at: '2026-07-17T13:00:00+08:00', actor: '演示员工15', from: 'Engineer Review', to: 'Manager Approval', comment: '设备验证方案确认' },
      { at: '2026-07-18T13:00:00+08:00', actor: '演示经理01', from: 'Manager Approval', to: 'Converted', comment: '批准并生成 Demo Test EVAL-104' },
    ],
  },
  {
    id: 'DR-109', accountId: 'ACC-003', accountName: '示例企业003有限公司', segment: 'Frontend',
    salesOwner: 'Demo Staff 01', createdBy: 'Demo Staff 01', title: '功率器件外观检测归档', objective: '完成客户功率器件晶圆外观检测验收',
    requestedEquipment: 'Macro Inspection X8', sampleType: 'Power device wafer', sampleQuantity: 6, targetDate: '2026-07-24',
    priority: 'Medium', acceptanceCriteria: '客户确认缺陷覆盖率与报告', status: 'Converted', engineerOwner: '演示员工14',
    feasibility: 'Feasible', testPlan: 'golden run、缺陷复核和验收报告', assignedEquipment: 'Macro Inspection Lab-01',
    resourceWindow: '2026-07-10 ~ 2026-07-22', estimatedCompletionDate: '2026-07-23', technicalRisk: '低',
    engineerComment: '客户已完成验收。', managerDecision: 'Approved', managerComment: '批准进入 Demo Test。',
    evaluationId: 'EVAL-105', createdAt: '2026-07-08T15:00:00+08:00', updatedAt: '2026-07-24T15:00:00+08:00',
    history: [
      { at: '2026-07-09T15:00:00+08:00', actor: 'Demo Staff 01', from: 'Draft', to: 'Engineer Review', comment: '提交工程评估' },
      { at: '2026-07-10T15:00:00+08:00', actor: '演示员工14', from: 'Engineer Review', to: 'Manager Approval', comment: '工程确认可执行' },
      { at: '2026-07-11T15:00:00+08:00', actor: '演示经理01', from: 'Manager Approval', to: 'Converted', comment: '批准并生成 Demo Test EVAL-105' },
    ],
  },
  {
    id: 'DR-110', accountId: 'ACC-007', accountName: '示例企业018有限公司', segment: 'Advanced Packaging',
    salesOwner: 'Demo Staff 02', createdBy: 'Demo Staff 02', title: 'Fan-out 面板级封装归档', objective: '验证 fan-out 面板级封装外观检测能力',
    requestedEquipment: 'PackageVision P7', sampleType: 'Fan-out panel', sampleQuantity: 4, targetDate: '2026-07-23',
    priority: 'Medium', acceptanceCriteria: 'Capture ≥ 92%；False Positive ≤ 5%', status: 'Converted', engineerOwner: '演示员工15',
    feasibility: 'Feasible', testPlan: '面板扫描、缺陷分类与客户复核', assignedEquipment: 'PackageVision Lab-02',
    resourceWindow: '2026-07-08 ~ 2026-07-20', estimatedCompletionDate: '2026-07-22', technicalRisk: '面板翘曲超出稳定窗口',
    engineerComment: '测试完成但误报率未达到客户目标。', managerDecision: 'Approved', managerComment: '批准进入 Demo Test。',
    evaluationId: 'EVAL-106', createdAt: '2026-07-06T15:00:00+08:00', updatedAt: '2026-07-23T15:00:00+08:00',
    history: [
      { at: '2026-07-07T15:00:00+08:00', actor: 'Demo Staff 02', from: 'Draft', to: 'Engineer Review', comment: '提交设备验证评估' },
      { at: '2026-07-08T15:00:00+08:00', actor: '演示员工15', from: 'Engineer Review', to: 'Manager Approval', comment: '设备验证方案确认' },
      { at: '2026-07-09T15:00:00+08:00', actor: '演示经理01', from: 'Manager Approval', to: 'Converted', comment: '批准并生成 Demo Test EVAL-106' },
    ],
  },
])

export const evaluations = withEvaluationDefaults([
  {
    id: 'EVAL-101', accountId: 'ACC-001', accountName: '示例企业014有限公司', requirementId: 'REQ-001',
    demoRequestId: 'DR-105', segment: 'Frontend', title: '先进制程缺陷复检准备', status: 'Requested', owner: '演示员工14',
    plannedEnd: '2026-08-14', wafers: 8, acceptance: 'Pending', criteria: 'Capture ≥ 96%；FP ≤ 3%', runs: [],
    waferPreparationStatus: 'Completed', waferPreparationCompletedBy: '演示员工14',
    waferPreparationCompletedAt: '2026-07-29T10:00:00+08:00', testPreparationStatus: 'Pending',
  },
  {
    id: 'EVAL-102', accountId: 'ACC-004', accountName: '示例企业045有限公司', demoRequestId: 'DR-106',
    segment: 'Frontend', title: 'DRAM 晶圆边缘缺陷验证', status: 'Sample Received', owner: '演示员工15',
    plannedEnd: '2026-08-22', wafers: 6, acceptance: 'Pending', criteria: '边缘缺陷检出率 ≥ 95%',
    runs: [{ id: 'CUSTOMER01-R01', date: '2026-08-03', lot: 'CUSTOMER01-EDGE-01', round: 1, wafers: 6, status: 'Planned', capture: null, falsePositive: null, wph: null, summary: '' }],
  },
  {
    id: 'EVAL-103', accountId: 'ACC-006', accountName: '示例企业027有限公司', requirementId: 'REQ-007',
    demoRequestId: 'DR-107', segment: 'Advanced Packaging', title: 'Chiplet Final Inspection 执行', status: 'Testing', owner: '演示员工14',
    plannedEnd: '2026-08-01', wafers: 10, acceptance: 'Pending', criteria: 'Capture ≥ 93%；False Positive ≤ 4%',
    runs: [
      { id: 'CUSTOMER04-R01', date: '2026-07-27', lot: 'JC-CHIPLET-071', round: 1, wafers: 5, status: 'Completed', capture: 93.8, falsePositive: 3.9, wph: 42, summary: '第一批达到目标，继续验证重复性。' },
      { id: 'CUSTOMER04-R02', date: '2026-07-30', lot: 'JC-CHIPLET-072', round: 1, wafers: 5, status: 'Planned', capture: null, falsePositive: null, wph: null, summary: '' },
    ],
  },
  {
    id: 'EVAL-104', accountId: 'ACC-005', accountName: '示例企业040有限公司', requirementId: 'REQ-006',
    demoRequestId: 'DR-108', segment: 'Advanced Packaging', title: 'Micro-bump 检测客户评审', status: 'Customer Review', owner: '演示员工15',
    plannedEnd: '2026-07-30', wafers: 8, acceptance: 'Pending', criteria: 'Capture ≥ 95%；False Positive ≤ 3%',
    runs: [{ id: 'CUSTOMER05-R01', date: '2026-07-26', lot: 'TF-MB-0726', round: 1, wafers: 8, status: 'Completed', capture: 96.1, falsePositive: 2.8, wph: 38, summary: '指标达标，等待客户确认最终缺陷分类。' }],
  },
  {
    id: 'EVAL-105', accountId: 'ACC-003', accountName: '示例企业003有限公司',
    demoRequestId: 'DR-109', segment: 'Frontend', title: '功率器件外观检测归档', status: 'Accepted', owner: '演示员工14',
    plannedEnd: '2026-07-23', wafers: 6, acceptance: 'Accepted', criteria: '客户确认缺陷覆盖率与报告',
    runs: [{ id: 'HH-R01', date: '2026-07-20', lot: 'HH-POWER-01', round: 1, wafers: 6, status: 'Completed', capture: 97.2, falsePositive: 2.1, wph: 35, summary: '客户确认全部验收指标。' }],
  },
  {
    id: 'EVAL-106', accountId: 'ACC-007', accountName: '示例企业018有限公司',
    demoRequestId: 'DR-110', segment: 'Advanced Packaging', title: 'Fan-out 面板级封装归档', status: 'Rejected', owner: '演示员工15',
    plannedEnd: '2026-07-22', wafers: 4, acceptance: 'Rejected', criteria: 'Capture ≥ 92%；False Positive ≤ 5%',
    runs: [{ id: 'HT-R01', date: '2026-07-19', lot: 'HT-FOPLP-01', round: 1, wafers: 4, status: 'Completed', capture: 93.4, falsePositive: 6.2, wph: 18, summary: '检出率达标，但面板翘曲导致误报率超标。' }],
  },
])

export const contracts: ContractDto[] = [
  { id: 'CON-001', accountId: 'ACC-001', opportunityId: 'OPP-001', accountName: '示例企业014有限公司', segment: 'Frontend', type: 'NDA', status: 'Active', signed: true, amount: 0, start: '2026-06-09', end: '2027-06-09', owner: 'Demo Staff 01' },
  { id: 'CON-002', accountId: 'ACC-005', opportunityId: 'OPP-007', accountName: '示例企业040有限公司', segment: 'Advanced Packaging', type: 'Evaluation Agreement', status: 'Active', signed: true, amount: 350000, start: '2026-06-09', end: '2026-09-07', owner: 'Demo Staff 02' },
  { id: 'CON-003', accountId: 'ACC-006', opportunityId: 'OPP-006', accountName: '示例企业027有限公司', segment: 'Advanced Packaging', type: 'Service Contract', status: 'Unsigned', signed: false, amount: 680000, start: '2026-08-01', end: '2027-07-31', owner: 'Demo Staff 02' },
]

export const actions: ActionDto[] = [
  { id: 'ACT-001', accountId: 'ACC-002', opportunityId: 'OPP-003', title: '补充武汉二期项目 ROI 说明', owner: 'Demo Staff 01', due: '2026-07-16', status: 'Open', sourceType: 'Requirement' },
  { id: 'ACT-002', accountId: 'ACC-001', opportunityId: 'OPP-001', title: '确认 Demo wafer 与验收阈值', owner: 'Demo Staff 01', due: '2026-07-18', status: 'Open', sourceType: 'Deal' },
  { id: 'ACT-003', accountId: 'ACC-005', opportunityId: 'OPP-007', title: '补齐先进封装项目预算信息', owner: 'Demo Staff 02', due: '2026-07-19', status: 'Open', sourceType: 'Requirement' },
  { id: 'ACT-004', accountId: 'ACC-007', title: '重估测试设备升级优先级', owner: 'Demo Staff 02', due: '2026-07-15', status: 'Open', sourceType: 'Visit' },
]

export const visits: VisitDto[] = [
  {
    id: 'V-001', accountId: 'ACC-001', primaryContactId: 'CON-001', opportunityId: 'OPP-001', accountName: '示例企业014有限公司', segment: 'Frontend',
    subject: '南京 Fab Demo 前现场确认', date: '2026-07-12', type: 'On-site', status: 'Manager Reviewed', owner: 'Demo Staff 01',
    objective: '确认 Demo wafer、验收指标与现场资源', outcome: '客户确认两批 patterned wafer，并接受分阶段验收。',
    nextAction: '提交正式测试计划与样片清单', actionOwner: 'Demo Staff 01', due: '2026-07-18', actionDone: false,
  },
  {
    id: 'V-003', accountId: 'ACC-006', primaryContactId: 'CON-009', opportunityId: 'OPP-006', accountName: '示例企业027有限公司', segment: 'Advanced Packaging',
    subject: '高速 AOI 交付启动会', date: '2026-07-22', type: 'On-site', status: 'Planned', owner: 'Demo Staff 02',
    objective: '确认交付里程碑、参会人和厂务准备', outcome: '', nextAction: '', actionOwner: '', due: '', actionDone: false,
  },
]
