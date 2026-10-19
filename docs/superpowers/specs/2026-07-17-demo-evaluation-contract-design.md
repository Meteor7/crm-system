# Demo、Wafer Test 与合同管理 MVP 设计

## 目标

从当前 MVP 中撤下客户情报模块，按照原型实现三条可操作业务链路：Demo Request 审批、Demo/Wafer Test 执行追踪、合同到期管理。保持 Vue 3、TypeScript、Pinia、Vue Router memory history、Mock/Frappe 双适配器和 `.semicrm-app` 样式隔离。

## 方案选择

1. **按原型状态机落地（采用）**：复刻 Demo Request 的 Sales、工程、经理审批状态，并在批准时自动生成 Evaluation；Evaluation 管理 Test Run；合同显示签署与 30/60/90 天风险。业务价值完整，范围仍适合 MVP。
2. **三张只读页面**：实现快，但 Demo Request 无法真正审批，不能满足“功能落地”。
3. **通用工作流引擎**：扩展性高，但会引入流程配置、角色矩阵和通用表单系统，超出 MVP。

## 范围

### 撤下客户情报

- 删除客户情报导航、路由、Dashboard 情报 KPI/雷达、Account 360 情报页签。
- 从运行时 DTO、API 契约、Mock/Frappe 适配器和自动化测试中移除 IntelligenceEvent 与转行动接口。
- 不修改原始 HTML 原型和 Word 需求文档。

### Demo Request

- 四列审批看板：Sales 准备、工程评估、经理审批、已完成。
- 支持客户、Sales、状态筛选及申请总数、待工程、待经理、已转 Demo 摘要。
- 支持新建完整申请；必填字段为客户、标题、目标、设备、样品类型、样品数量、目标日期、优先级、验收标准。
- 状态机：
  - `Draft` / `Engineer Returned` / `Manager Rejected` → `Engineer Review`
  - `Engineer Review` → `Engineer Returned` 或 `Manager Approval`
  - `Manager Approval` → `Manager Rejected` 或 `Converted`
  - 可编辑状态 → `Cancelled`
- 工程确认必须包含测试方案、设备、资源窗口、预计完成日期、技术风险和工程意见。
- 经理批准必须幂等，并自动创建一条来源可追溯的 Evaluation。
- 卡片展示最近一条历史、工程/经理意见及关联 Evaluation。

### Demo / Wafer Test

- 五列看板：准备、测试/分析、客户评审、挂起、结束。
- 支持客户筛选、状态推进、挂起原因和恢复日期。
- Test Run 记录 Run 编号、日期、Lot、Wafer 数、状态、Capture、False Positive、WPH 和摘要。
- 有 Capture 结果的 Run 自动标记 `Completed`，否则为 `Planned`；Evaluation wafer 数量由所有 Run 汇总。
- 保留 Demo Request 来源编号和报告链接。

### 合同管理

- 展示合同编号、客户、类型、签署状态、金额、开始、到期和风险。
- 风险口径以 2026-07-17 为演示基准：已过期、30 天内、60 天内、90 天内、正常。
- 支持客户、状态和合同类型筛选；摘要显示合同总数、未签署、90 天内到期和合同金额。
- 当前 MVP 不实现附件上传、电子签署和审批流；这些能力由后续 Frappe 后端承载。

## 架构与数据流

- `src/types/crm.ts` 定义领域 DTO 与命令类型。
- `CrmApi` 提供三个领域的查询和写操作；Mock Adapter 只更新内存副本，Frappe Adapter 保留服务端方法边界。
- 页面沿用统一的 `readRequestMeta`、`mapRequestError`、request sequence、权限清空、stale/partial 提示。
- Demo Request 批准操作在适配器内原子完成：更新申请、追加历史、创建 Evaluation、写回 `evaluationId`，重复批准返回 `EVALUATION_EXISTS`。
- Account 360 聚合 Demo Request、Evaluation 和合同，形成客户交付视图。

## 页面与组件

- `DemoRequestsPage.vue`：摘要、筛选、四列看板和加载状态。
- `DemoRequestCard.vue`：申请字段、状态、历史和上下文操作。
- `DemoRequestModal.vue`：新建、工程评估、经理审批三种表单。
- `EvaluationsPage.vue`、`EvaluationCard.vue`、`TestRunModal.vue`：验证看板与测试批次录入。
- `ContractsPage.vue`：合同筛选、摘要和响应式合同表格。
- `ModalShell.vue`：容器内弹层，禁止 Teleport 到 Desk body。

## 错误与权限

- API 错误显示 Request ID；403 清除已加载业务数据并隐藏摘要。
- 任何非法状态跃迁、缺失字段、重复批准、无效 Evaluation/Test Run 都返回 `CrmApiError`。
- 搜索或筛选无结果显示可操作空状态，不渲染空表格/空看板。
- 所有写操作只修改当前 Mock API 实例内存，不使用 localStorage。

## Dashboard 调整

- “高分客户情报”替换为“待审批 Demo Request”。
- 情报雷达替换为“验证与合同提醒”，展示挂起 Evaluation、待经理审批和 90 天内合同。
- 经理提醒调整为 Demo 审批、样片阻塞和合同续签。

## 测试与验收

- 适配器测试：申请完整度、合法/非法跃迁、批准自动建 Evaluation、幂等、Test Run 汇总、合同风险与筛选。
- 页面测试：导航无客户情报、三条新路由可达、申请批准后 Evaluation 可见、Evaluation 空态/Test Run、合同 30/60/90 风险。
- 回归：Account 360 不再显示情报并显示 Demo/合同；Dashboard 不再包含客户情报文案。
- 最终执行 Vitest、`vue-tsc --noEmit`、Vite production build、相对资源和本地 HTTP 200 检查。

## 明确假设

- 本地演示允许在同一页面模拟 Sales、工程和经理动作；真实权限必须由 Frappe 会话角色在后端校验。
- 合同金额为人民币，NDA 金额允许为 0。
- 本轮“回退客户情报”指从当前运行产品完整撤下，不删除原始原型或需求材料中的历史描述。
