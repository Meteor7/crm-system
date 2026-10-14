import { ROLE_PROFILES } from '@/domain/permissions'
import type { UserRole } from '@/types/crm'
import type { ApprovalItem, ApprovalKind, ApprovalViewer } from '@/features/approvals/approval-queue'

// Fictional, isolated visual-demo data. No production API or business mutation is used.
export const DEMO_NOW = '2026-10-14T12:00:00+08:00'
export function demoViewer(role: UserRole): ApprovalViewer {
  return { id: `preview-${role.toLowerCase()}`, name: { Manager: '王经理', Sales: '演示员工151', Engineer: '周工' }[role], role, capabilities: ROLE_PROFILES[role].capabilities }
}
function item(role: UserRole, kind: ApprovalKind, id: string, title: string, customer: string, stage: string, overrides: Partial<ApprovalItem> = {}): ApprovalItem {
  return { id, kind, title, customer, sourceId: id, stage, requester: '演示员工151', requesterId: 'preview-sales', sales: '演示员工151', region: '华东', market: 'Frontend', equipment: 'Kibo 4895C', submittedAt: '2026-10-14T09:30:00+08:00', unread: true, recipientId: demoViewer(role).id, recipientRole: role, state: 'pending', canReadSource: true, canHandle: true, description: '业务材料已提交，等待当前处理人核实并完成本阶段处理。', sourceLabel: '业务单据', ...overrides }
}
export function demoApprovals(): ApprovalItem[] {
  return [
    item('Manager', 'demo', 'CRM-DR-04182', '12 英寸晶圆缺陷检测 Demo 申请', '示例企业043', '经理审批', { description: '工程可行性评估已完成，设备与资源窗口已确认。请核实客户目标、样品准备和资源安排。', sourceLabel: 'Demo Request' }),
    item('Manager', 'quotation', 'PK20261012-A03', 'Kibo 4895C 设备采购报价', '示例企业012', '报价版本审批', { sourceRecordId: 'CRM-QTN-04103', requester: '陈远', requesterId: 'preview-sales-2', sales: '陈远', submittedAt: '2026-10-12T10:15:00+08:00', equipment: 'Kibo 4895C', description: '报价版本 V2 已提交。设备配置、付款节点及交付条款待核实。', sourceLabel: 'Quotation · V2' }),
    item('Manager', 'production', 'CRM-OPP-03276', 'Veymont 二期扩产生产申请', '瀚海集成电路', '内部生产审批', { requester: '陈远', requesterId: 'preview-sales-2', sales: '陈远', submittedAt: '2026-10-11T15:40:00+08:00', equipment: 'Veymont', forbidSelfApproval: true, unread: false, description: '客户预算已确认，预计 PO 和交付节点已填写。请核实生产计划及 Booking 信息。', sourceLabel: 'Opportunity · 生产申请' }),
    item('Manager', 'visit', 'CRM-VIS-02641', '量测方案现场沟通纪要', '示例企业036', '拜访纪要审核', { unread: false, submittedAt: '2026-10-13T16:20:00+08:00', equipment: 'Nansi', sourceLabel: 'Visit', description: '拜访纪要已提交，包含客户需求变化和下次沟通计划。' }),
    item('Manager', 'rfq', 'CRM-RFQ-01037', '先进封装产线 RFQ', '示例企业007', '经理审核', { requester: '陈远', requesterId: 'preview-sales-2', sales: '陈远', market: 'Advanced Packaging', region: '华南', equipment: 'Aconca', unread: false, submittedAt: '2026-10-13T11:00:00+08:00', sourceLabel: 'RFQ Center' }),
    item('Manager', 'document', 'DOC-REQ-00216', '设备技术规格书访问申请', '示例企业043', '受控文档授权', { sourceLabel: 'Document Center', description: '申请人请求查看已发布的设备技术规格书。请核实使用目的及适用的访问范围。' }),
    item('Engineer', 'demo-engineering', 'CRM-DR-04183', '前道颗粒检测可行性评估', '示例企业043', '工程可行性评估', { sourceLabel: 'Demo Request', description: '请评估检测要求、样品条件、设备配置及可用资源窗口。' }),
    item('Engineer', 'demo-engineering', 'CRM-DR-04177', 'SiC 晶圆表面量测 Demo', '示例企业020', '工程可行性评估', { submittedAt: '2026-10-12T14:10:00+08:00', equipment: 'Veymont', unread: false, sourceLabel: 'Demo Request' }),
    item('Engineer', 'test-review', 'CRM-EVAL-02945', '晶圆缺陷检测测试报告', '示例企业012', '测试结果内部审核', { sourceLabel: 'Demo Test', description: '本轮测试已完成，测试指标与原始数据已上传，等待负责工程师完成内部审核。' }),
    item('Engineer', 'rfq-engineering', 'CRM-RFQ-01038', '产线扩产设备技术评审', '示例企业007', 'RFQ 技术评审', { market: 'Advanced Packaging', equipment: 'Aconca', sourceLabel: 'RFQ Center', unread: false }),
    item('Sales', 'customer-review', 'CRM-EVAL-02942', '客户确认 Demo 测试结论', '示例企业043', '客户评审确认', { requester: '周工', requesterId: 'preview-engineer', sourceLabel: 'Demo Test', description: 'Customer 报告已就绪。请根据客户反馈记录本轮评审结论，或提出重测需求。' }),
    item('Sales', 'customer-review', 'CRM-EVAL-02936', '量测重复性客户评审', '示例企业036', '客户评审确认', { requester: '周工', requesterId: 'preview-engineer', equipment: 'Nansi', submittedAt: '2026-10-12T11:20:00+08:00', unread: false, sourceLabel: 'Demo Test' }),
    // Guard cases: never displayed, counted, searchable or included in category/filter options.
    item('Manager', 'quotation', 'DENIED-OTHER-USER', '其他经理的审批（不可见）', '不可见客户', '报价版本审批', { recipientId: 'another-manager' }),
    item('Manager', 'demo', 'DENIED-SOURCE', '源权限已撤销（不可见）', '不可见客户', '经理审批', { canReadSource: false }),
    item('Manager', 'demo', 'FINISHED', '已审批事项（不可见）', '不可见客户', '已完成', { state: 'approved' }),
  ]
}
