# CRM Mock Demo：接口、权限与数据同步审查

> 日期：2026-08-03
> 范围：前端 Demo（Vue 3 + TypeScript + Pinia + Mock Adapter）
> 结论：当前可以继续打磨和验收 Mock 前端；Frappe 后端尚未接入，不能把本报告当作 Stage/Production 后端验收结果。

## 1. 当前运行边界

| 项目 | 当前状态 | 说明 |
|---|---|---|
| 前端适配器 | `VITE_API_ADAPTER=mock` | `.env.local` 已固定使用 Mock |
| Mock 接口 | 已实现 | 由 `createMockApi()` 实现，用于前端业务演示和权限/同步验收 |
| Frappe 接口 | 未实现 | `createFrappeApi()` 直接抛出 `BACKEND_NOT_CONNECTED` |
| 数据库 | 未接入 | 当前无 Frappe DocType、数据库表、服务端事务或服务端授权 |
| 权限性质 | Demo 权限契约 | 权限发生在浏览器端，只用于演示；不能替代服务端鉴权 |
| Stage 建议 | 暂不切换 Frappe | 可部署一个明确标注 Mock 的纯前端预览环境，但不能作为后端联调 Stage |

## 2. 统一人员目录

| 人员 ID | 姓名 | 权限大类 | 数据范围 | 主要职责 |
|---|---|---|---|---|
| `administrator` | 演示员工24 | Manager | 全部 | 全局管理、审批、配置 |
| `management` | 演示经理01 | Manager | 全部 | 经营查看、审批、跨客户管理 |
| `sales-manager` | Demo Staff 06 | Manager | 全部 | 统一并入 Manager，不再保留 Sales Manager 子角色 |
| `sales-user` | Demo Staff 01 | Sales | 自有客户 | 销售主数据、Lead、Opportunity、Booking、Visit、Demo Request |
| `sales-bella` | Demo Staff 02 | Sales | 自有客户 | 同上，数据与 Alex 按客户 Owner 隔离 |
| `fae` | 演示员工14 | Engineer | 已分配客户/设备/Demo | 工程审核、Evaluation、Installed Tool、服务与程序执行 |
| `equipment-engineer` | 演示员工15 | Engineer | 已分配客户/设备/Demo | 同上 |

唯一合法角色类型：`Manager | Sales | Engineer`。旧的 `CRM Administrator`、`Management Viewer`、`Sales Manager`、`Sales User`、`FAE / Applied Engineer`、`Equipment Engineer` 已从运行时角色契约移除。

## 3. 权限分配

| 能力域 | Manager | Sales | Engineer |
|---|---:|---:|---:|
| Dashboard 查看 | ✅ 全局 | ✅ 自有范围 | ✅ 已分配范围 |
| Dashboard 管理 | ✅ | ❌ | ❌ |
| Account 查看 | ✅ 全部 | ✅ 自有 | ✅ 已分配 |
| Account 写入 | ✅ | ✅ 自有 | ❌ |
| Account 报告导出 | ✅ | ✅ 自有 | ❌ |
| Contact 查看/写入 | ✅ / ✅ | ✅ / ✅（自有） | ❌ / ❌ |
| Contact 合并/删除 | ✅ | ❌ | ❌ |
| Requirement 查看/写入 | ✅ / ✅ | ✅ / ✅（自有） | ✅ / ❌（已分配） |
| Lead / Opportunity 查看/写入 | ✅ / ✅ | ✅ / ✅（自有） | ✅ / ❌（已分配） |
| Booking 查看/写入 | ✅ / ✅ | ✅ / ✅（自有） | ✅ / ❌（已分配） |
| Visit 查看/新建/写入 | ✅ / ✅ / ✅ | ✅ / ✅ / ✅（自有） | ✅ / ❌ / ❌ |
| Visit Manager Review | ✅ | ❌ | ❌ |
| Demo Request 查看/新建 | ✅ / ✅ | ✅ / ✅（自有） | ✅ / ❌（被指派） |
| Demo 工程审核 | ✅ | ❌ | ✅（本人负责） |
| Demo Manager 审批 | ✅ | ❌ | ❌ |
| Demo 报告配置 | ✅ | ✅（自有） | ❌ |
| Demo 报告发布 | ✅ | ❌ | ❌ |
| Evaluation 查看/写入 | ✅ / ✅ | ✅ / ❌ | ✅ / ✅（本人负责） |
| Installed Tool 写入 | ✅ | ❌ | ✅（本人负责；不可自行转派） |
| Service 查看/写入 | ✅ / ✅ | ✅ / ❌ | ✅ / ✅（已分配） |
| Procedure 查看/执行 | ✅ / ✅ | ❌ / ❌ | ✅ / ✅ |
| Contract 查看 | ✅ | ✅（自有） | ❌ |
| System Configure | ✅ | ❌ | ❌ |

### Owner 指派规则

| 字段类型 | 下拉来源 | Mock API 校验 |
|---|---|---|
| 客户、联系人、Lead、Opportunity、Booking、Visit Owner | Sales：Demo Staff 01 / Demo Staff 02 | 必须为人员目录中的 Sales；Sales 不可把同类记录转给另一名 Sales |
| Demo Sales Contact | Sales：Demo Staff 01 / Demo Staff 02 | 必须为人员目录中的 Sales |
| Demo Owner、Installed Tool Engineer | Engineer：演示员工14 / 演示员工15 | 必须为人员目录中的 Engineer；Engineer 不可自行转派给另一名 Engineer |
| Action Owner、Visit Action Owner | Sales + Engineer | 必须来自人员目录；允许销售与工程之间交接行动 |
| Manager 审批人 | 当前 Manager 身份 | 由当前身份产生，不允许自由文本输入 |

## 4. 已有前端接口契约

`CrmApi` 当前共定义 57 个方法。下表是前端期望的稳定契约；目前只有 Mock Adapter 实现，Frappe 尚无真实对应端点。

| 域 | 契约方法 | Mock | Frappe |
|---|---|---:|---:|
| 会话与 Dashboard | `getBootstrap`, `getDashboard` | ✅ | ❌ |
| Account | `listAccounts`, `createAccount`, `updateAccount`, `getAccount360` | ✅ | ❌ |
| Visit | `listVisits`, `createVisit`, `updateVisit` | ✅ | ❌ |
| Contact | `listContacts`, `getContact`, `saveContact`, `mergeContacts`, `deleteContact` | ✅ | ❌ |
| Contact 文件 | `listContactFiles`, `uploadContactFiles`, `getContactFile`, `deleteContactFile` | ✅ | ❌ |
| Lead | `listLeads`, `getLead`, `saveLead`, `convertLead` | ✅ | ❌ |
| Stakeholder 兼容层 | `listStakeholders`, `saveStakeholder` | ✅ | ❌ |
| Requirement / Pipeline | `listRequirements`, `listPipeline` | ✅ | ❌ |
| Booking | `createBooking`, `updateBooking` | ✅ | ❌ |
| Demo Request | `listDemoRequests`, `createDemoRequest`, `updateDemoRequest`, `transitionDemoRequest` | ✅ | ❌ |
| Evaluation / Test Run | `listEvaluations`, `updateEvaluationStatus`, `addEvaluationRun`, `setEvaluationTestRunDeadline` | ✅ | ❌ |
| Demo 报告 | `configureDemoTestReport`, `getDemoTestReportContext`, `saveDemoArtifact`, `getDemoArtifact`, `releaseDemoTestReport` | ✅ | ❌ |
| Contract | `listContracts` | ✅ 只读 | ❌ |
| Opportunity Strategy | `listStrategyOpportunities`, `createStrategyOpportunity`, `updateStrategyOpportunity` | ✅ | ❌ |
| Opportunity Stakeholder | `saveOpportunityStakeholder`, `deleteOpportunityStakeholder` | ✅ | ❌ |
| Opportunity Action | `saveOpportunityAction`, `deleteOpportunityAction` | ✅ | ❌ |
| Demo 工作台 | `listDemoWorkflows`, `listDemoComments`, `addDemoComment` | ✅ | ❌ |
| Installed Tool | `listInstalledTools`, `convertBookingToInstalledTool`, `updateInstalledTool` | ✅ | ❌ |
| Document Center | `listControlledDocuments`, `requestControlledDocumentAccess` | ✅ | ❌ |

### Stage 对接时必须补充的后端公共契约

当前 57 个业务方法之外，Frappe 实现还必须统一以下服务端约束：

| 后端能力 | 要求 |
|---|---|
| 身份来源 | 从 Frappe Session/User 解析，不接受前端传入 role/userName 作为可信身份 |
| 权限 | 服务端按 Manager/Sales/Engineer 和记录范围再次校验 |
| 幂等与并发 | 写接口增加版本号或 `modified` 乐观锁，防止覆盖更新 |
| 事务 | Lead 转换、Contact 合并/删除、Demo 转 Evaluation、Booking 转 Installed Tool 必须使用数据库事务 |
| 错误模型 | 对齐 `CrmApiError(code, message, requestId, retryable, fieldErrors)` |
| 审计 | 写操作记录 actor、时间、来源记录、前后值 |
| 文件 | 附件权限、大小、类型、下载审计均在服务端执行 |
| 分页/筛选 | 与 `ListQuery`、`ContactListQuery`、`DashboardQuery` 字段一致 |

## 5. 数据前后同步

| 业务写入 | 修改前风险 | 修改后同步行为 | 验证 |
|---|---|---|---|
| 角色切换 | 六类旧角色与新角色混用，可能命中不同分支 | 运行时仅三类角色，7 人统一从 `PERSONNEL` 读取 | 人员、身份、权限测试 |
| 新建/编辑负责人 | 多处自由文本，可产生系统不存在的人名 | 所有可编辑 Owner 使用人员下拉或目录派生选项；Mock API 二次校验 | PersonnelSelect + Mock API 测试 |
| Sales 数据隔离 | 团队、本人、旧 Sales Manager 规则交叉 | Sales 按客户 Owner/本人范围；Alex 与 Bella 隔离 | 跨身份同步测试 |
| Engineer 数据隔离 | FAE/设备工程师分支重复 | Engineer 按 assignedAccountIds、Demo Owner、Installed Tool Engineer Owner 可见 | Mock API 角色测试 |
| Manager 全局通知 | 目标通知只按 recipient 过滤，Manager 看不到全局写入通知 | Manager 可看到所有目标通知；Sales/Engineer 按稳定人员 ID 过滤 | Store/AppShell 测试 |
| Account 新建 | Owner 可能为任意字符串 | 只允许 Sales 人员；Sales 只能新建给本人 | Mock API 测试 |
| Account 改名 | 子记录可能保留旧客户名 | 同步 Booking、Visit、Contract、Opportunity、Installed Tool、Demo Request、Evaluation 的客户显示名 | 跨身份同步测试 |
| Account 统计 | seed 字段可能陈旧 | Pipeline、意向、联系人、厂区、需求数量从当前数据重新计算 | Mock API / Account 测试 |
| Contact 保存 | Owner、Account、Site 可能不一致 | 校验 Sales Owner、Account 范围、Site 归属；Account 联系人数即时更新 | Mock API / 同步测试 |
| Contact 合并/删除 | 多仓库写入可能半成功 | 同步 Booking、Visit、Demo、Opportunity Stakeholder、文件；失败时回滚内存快照 | Mock API 测试 |
| Lead 转换 | Account/Contact/Opportunity 可能断链或 Owner 非法 | 同一 Sales Repository 写入并校验三类 Owner、Site/Contact 外键 | Mock API 测试 |
| Opportunity | Owner/客户/厂区可能不匹配 | 校验 Sales Owner、Account 范围、Site 归属；更新后重新计算 Pipeline | Mock API 测试 |
| Booking Primary Contact | 后端必填但前端未标记必填 | ContactPicker 支持原生 required；Booking 新建显示必填标记并阻止空提交 | Required Marker 测试 |
| Booking → Installed Tool | 两条记录可能各自成功 | 在同一 Sales Repository 中建立 `installedToolId/sourceBookingId` 双向链路并校验 Engineer | Mock API 测试 |
| Visit 新建 | 新日期超出当前列表筛选后“保存成功但消失” | 保存后自动扩展日期筛选区间，立即可见 | customer-operations 测试 |
| Visit 下一步行动 | 行动 Owner 可为任意文本 | 仅允许 Sales/Engineer 下拉；跨大类交接允许，同类越权转派拒绝 | Mock API 测试 |
| Demo Request | Sales/Engineer Owner 可能绕过目录 | create/update/transition 均校验 Sales Contact 与 Demo Owner | Mock API 测试 |
| Demo → Evaluation | Request 已 Converted 但 Evaluation 缺失 | Repository transaction 同步创建并保存双向 ID/Owner | Demo Repository / Mock API 测试 |
| Dashboard | 页面使用静态聚合会滞后 | 每次请求从当前可见 Account、Opportunity、Booking、Demo、Evaluation、Visit 重算 | Dashboard / Mock API 测试 |

## 6. 浏览器持久化边界

| 数据域 | 存储 | 同步特性 | Stage 替换目标 |
|---|---|---|---|
| Account、Lead、Contact、Opportunity、Booking、Visit、Installed Tool | `localStorage: semicrm:sales-workspace:v1` | 同一浏览器共享；无服务端并发 | Frappe DocType + 数据库事务 |
| Demo Request、Evaluation、Artifact 元数据 | IndexedDB `semiconductor-crm-demo` | 本机浏览器持久化 | Frappe DocType + File |
| Contact 文件 | IndexedDB `semiconductor-crm-contact-files` | 本机 Blob；非服务器附件 | Frappe File/附件权限 |
| 通知 | Pinia/浏览器状态 | 当前会话和前端身份过滤 | 服务端通知/事件表 |
| 静态 Requirement、Contract、Action | 前端 seed | 部分只读或仅内存，不是统一持久化源 | 对应 DocType |

## 7. 本轮对抗性审查结论

### 已修复

| 严重度 | 问题 | 结果 |
|---|---|---|
| P1 | 旧角色兼容类型重新进入运行时契约 | 已删除，类型和权限表只保留三角色 |
| P1 | Owner 自由文本/非法人员可进入数据 | 已改为下拉，并在 Mock API 二次校验 |
| P1 | Manager 看不到针对其他人的通知 | 已按 Manager 全局视角修复 |
| P1 | Booking 联系人前端非必填、API 必填 | 已对齐 |
| P1 | 新建 Visit 成功后被日期筛选隐藏 | 已修复并回归测试 |
| P2 | 原生表单 `aria-label` 被误改为 `ariaLabel` | 已恢复标准属性 |
| P2 | 旧测试仍把 Grace/Manager 当作非管理或只读角色 | 已更新三角色契约断言 |

### 仍需在 Stage 前完成

| 严重度 | 风险 | 处理建议 |
|---|---|---|
| Blocker | Frappe Adapter 未实现 | 完成真实接口、DocType、鉴权、事务和错误映射后再启用 Frappe |
| Blocker | Mock 权限在客户端，不能防篡改 | 所有权限和范围必须在 Frappe 服务端重做 |
| P1 | Mock 数据分布在 localStorage、两个 IndexedDB、静态 seed | Stage 数据迁移前建立唯一数据库真源和迁移脚本 |
| P1 | 静态 Requirement/Contract/Action 未完全进入统一 Repository | 后端建模时统一外键、版本号和审计字段 |
| P2 | 当前工作树存在其他页面改版遗留测试失败 | 在 Stage 候选分支冻结后单独清理；不要把 Mock 角色测试通过等同于全仓上线通过 |

## 8. 验证结果

| 检查 | 结果 |
|---|---|
| TypeScript `vue-tsc --noEmit` | 通过 |
| 三角色/人员/通知/Owner/同步重点测试 | 11 个测试文件，139 个测试通过 |
| 新增跨身份同步测试 | 通过 |
| Booking 必填与 Visit 可见性回归 | 9 个测试通过 |
| Vite production build | 通过 |
| 全量 Vitest | 450/472 通过；22 项失败分布在 9 个旧测试文件，集中于 Demo 归档路由/旧 DOM、客户报告模型、旧快照迁移和 Logo 超时，未发现新增三角色/Owner/同步重点用例失败 |

## 9. 上线顺序建议

1. 继续用 `VITE_API_ADAPTER=mock` 完成三轮前端 Demo 对抗审查。
2. 冻结 `CrmApi` 57 方法及 DTO，作为 Frappe 实现清单。
3. 设计 DocType、外键、唯一约束、事务边界和服务端权限。
4. 实现 Frappe Adapter，并为每个写接口跑 Manager/Sales/Engineer 三身份契约测试。
5. 建立独立 Stage 数据库，导入非敏感测试数据；禁止把 Mock localStorage/IndexedDB 当作生产数据迁移源。
6. Stage 通过接口、权限、并发、事务、审计、文件和回归测试后，再准备 Production。
