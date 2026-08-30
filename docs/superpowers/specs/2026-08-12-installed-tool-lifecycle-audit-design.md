# Installed Tool 生命周期、版本配置与质保服务设计

**日期：** 2026-08-12  
**状态：** 已批准，待实施  
**范围：** 生命周期推进、关键主数据、版本配置留痕、质保服务留痕、权限与接口契约

## 1. 目标

1. 生命周期严格按 `FAT → Shipment → Installation → SAT → Warranty` 单步推进。
2. 只有 CRM Manager 和该 Installed Tool 当前负责工程师可以推进、登记版本配置变更和质保服务。
3. Sales、其他工程师和无有效 CRM 身份用户只能在其可见范围内读取。
4. 关键主数据和三类操作必须可追踪、可审计，历史不可被后续编辑覆盖。
5. 详情不得继续依赖前端 `toolProfiles` 硬编码，必须读取真实 API 数据。
6. 每个接口必须在类型、适配器、端点、服务、DocType、错误码和测试之间一一对应。

## 2. 现状

当前主表的 `status` 可自由修改，`milestones`/`documents` 是 JSON，缺少操作者、时间、前后状态和业务字段；版本配置、质保服务主要来自 `InstalledToolArchiveView.vue` 的硬编码示例。真实 API 只有列表、Booking 转换和通用更新，没有详情、推进、版本变更和服务登记接口。

复用 Demo 的服务端模式：命令式迁移、能力和角色校验、CAS 锁、savepoint、原子更新、独立历史和稳定错误码；不复制 Demo 的具体状态字段。

## 3. 数据模型

采用三个只追加的业务记录 DocType：

- `CRM Installed Tool Lifecycle History`
- `CRM Installed Tool Version History`
- `CRM Installed Tool Service History`

### 3.1 主表

新增 `lifecycle_stage`（FAT/Shipment/Installation/SAT/Warranty），Booking 转换后初始为 FAT。`status` 继续表示设备运行状态，不能再作为生命周期阶段。

关键主数据包括：Serial、Model、Site、Location、Engineer Owner、Software、Firmware、Operating System、Configuration、Sales Order、Contract、Ownership Type、Warranty Start/End、Service Contract、PM Cycle、Last Service。

日期字段改用 Date，未确认时为空，不再保存“待确认”。`completeness` 由服务端根据关键字段和生命周期计算。通用编辑不能修改 `lifecycle_stage`、历史、`last_service` 或 `completeness`。

### 3.2 生命周期历史

字段：installed_tool、at、actor、from_stage、to_stage、completed_at、result、open_issues、customer_signoff、comment、evidence（字符串数组）。除 evidence 可为空外均必填；无问题明确填写“无”。无 update/delete API。

### 3.3 版本配置历史

字段：installed_tool、at、actor、change_date、change_type（Software/Firmware/Operating System/Configuration）、from_value、to_value、reason、comment。`from_value` 只从服务端当前快照读取；创建历史与更新主表快照必须同事务完成。

### 3.4 质保服务历史

字段：installed_tool、at、actor、service_date、service_type（Warranty Activation/Preventive Maintenance/Corrective Service/Remote Support/Installation Support/Contract Change）、result、open_issues、next_action、action_owner、due、comment，以及可选的 warranty_start/end、service_contract、pm_cycle 更新快照。存在 next_action 时 owner 和 due 必填。服务端同步 last_service。

三类历史 DocType 对 CRM 角色只授予 read；写入只能经受控服务完成。

## 4. 生命周期状态机

| 当前阶段 | 完成后进入 | 运行状态联动 |
|---|---|---|
| FAT | Shipment | Shipment |
| Shipment | Installation | Installation |
| Installation | SAT | Installation Complete |
| SAT | Warranty | Production |
| Warranty | 完成 | 保持当前运行状态 |

不能跳级、回退或重复完成。Warranty 完成后推进按钮消失，服务记录仍可追加。每次推进原子写历史、更新主表、重建 milestone 兼容快照并计算 completeness；使用 `expectedModified`，并发请求仅一个成功。

## 5. 权限

- Manager：可操作任意可见设备。
- Engineer：仅 `session.user == doc.engineer_owner` 时可操作。
- 其他 Engineer：即使猜测 ID 也拒绝。
- Sales：所有新写接口拒绝。
- Guest 或角色歧义：拒绝。

前端隐藏按钮只是体验控制，服务端必须独立重复校验。重新分配负责人仍只限 Manager，Engineer 不能通过任意 payload 改负责人。

## 6. API 契约

### 6.1 读取

| 前端方法 | Frappe 方法 | 输出 |
|---|---|---|
| `listInstalledTools(query)` | `installed_tools.list_installed_tools` | `PageData<InstalledToolSummaryDto>` |
| `getInstalledTool(id)` | `installed_tools.get_installed_tool` | `InstalledToolDetailDto` |

详情返回主数据、三类历史和服务端计算的 `canOperate`、`canReassign`。列表只返回看板摘要。

### 6.2 写入

| 前端方法 | Frappe 方法 | 行为 |
|---|---|---|
| `updateInstalledTool` | `installed_tools.update_installed_tool` | 更新允许的主数据 |
| `transitionInstalledTool` | `installed_tools.transition_installed_tool` | 完成当前生命周期阶段 |
| `addInstalledToolVersionRecord` | `installed_tools.add_installed_tool_version_record` | 追加版本记录并更新快照 |
| `addInstalledToolServiceRecord` | `installed_tools.add_installed_tool_service_record` | 追加服务记录并更新快照 |

每个接口必须覆盖以下完整链路：

1. `src/types/workspaces.ts` DTO/Input
2. `src/api/contracts.ts` CrmApi 方法
3. `src/api/frappe-adapter.ts` 映射与请求封装
4. `backend/.../api/v1/installed_tools.py` whitelist 端点
5. `backend/.../services/installed_tools.py` 验证、授权、事务、序列化
6. DocType 字段和权限
7. mock adapter 等价行为（只用于测试；正式构建继续使用 Frappe adapter）
8. 前端契约测试、真实 Frappe 服务和端点测试

禁止字段命名/可选性不一致、前端方法存在但后端端点缺失、错误码未映射或 mock 与真实权限不同。

稳定错误码：`INSTALLED_TOOL_NOT_FOUND`、`INSTALLED_TOOL_SCOPE_DENIED`、`INSTALLED_TOOL_OPERATION_DENIED`、`INSTALLED_TOOL_REASSIGN_DENIED`、`INVALID_TRANSITION`、`VALIDATION_ERROR`、`VERSION_CONFLICT`、`SITE_ACCOUNT_MISMATCH`、`INSTALLED_TOOL_SERIAL_EXISTS`。端点继续返回统一 envelope 和 Request ID。

## 7. 前端交互

设备档案头部对 `canOperate` 显示“完成 FAT，推进至 Shipment”式按钮。弹窗填写实际完成日期、结果、遗留问题、客户确认、备注和证据文件名；成功后重新获取详情。

版本配置页签对可操作用户显示“新增变更记录”。根据类型显示服务端当前值，只填写新值、日期、原因、备注。

质保服务页签对可操作用户显示“新增服务记录”。根据类型显示质保/合同字段；下一步行动存在时要求负责人和截止日期。

主数据编辑补齐 OS、Warranty Start/End、Service Contract、PM Cycle、Ownership Type，并移除生命周期自由编辑。Engineer 不可重新分配，Sales 看不到写按钮。错误统一映射并展示 Request ID。

## 8. 迁移

幂等补丁为现有设备推导 lifecycle_stage：优先取 milestone Current，其次按 status 映射，无法推导则 FAT。已有 Done milestone 转成最小历史并标记 `Legacy milestone migration`；不迁移前端 `toolProfiles`，因为不是真实数据。占位日期转换为空。

## 9. 测试和接口门槛

后端必须覆盖：五阶段推进、跳级/重复/CAS/缺字段失败、Manager 和负责 Engineer 成功、Sales/其他 Engineer/跨 scope ID 失败、四种版本类型、服务条件必填、快照更新、失败注入回滚、历史表只读、全部端点 envelope 和 Request ID。

前端必须覆盖：四种身份按钮可见性、三个弹窗 payload、成功后重新加载、403/409/验证错误和 Request ID、无硬编码详情、Frappe adapter 端点/字段/expectedModified、mock 与真实状态机和权限一致。

最终执行 typecheck、Installed Tool 定向测试、Frappe schema/service/endpoint/permission 测试、Booking/Dashboard/Calendar/权限回归、production build、Docker migrate、健康检查，以及真实 HTTP 登录会话的四身份接口验证。

仅“函数存在”不能证明接口完成，必须有跨层契约和身份负向测试。

## 10. 完成标准

- 三个详情分区全部读取真实后端数据。
- 生命周期严格单步，Manager/负责 Engineer 可操作，其他身份由服务端拒绝。
- 关键主数据使用正确类型并补齐。
- 生命周期、版本配置、质保服务均形成不可覆盖记录。
- 迁移幂等。
- 每个新增接口从前端类型到真实 HTTP 均有验证证据。
- 无 P0/P1 权限绕过、跨 scope 泄露、并发重复推进或部分写入。