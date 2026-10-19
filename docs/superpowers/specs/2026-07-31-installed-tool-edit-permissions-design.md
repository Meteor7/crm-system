# Installed Tool 编辑与权限设计

## 目标

在现有 Installed Tools 台账中增加设备主数据编辑能力，并保持 Booking 转入流程不变。

## 权限

- CRM Administrator：可编辑全部 Installed Tool。
- Management Viewer（Boss）：授予与演示员工170相同的 Installed Tool 编辑权限，可编辑全部客户设备。
- FAE / Applied Engineer、Equipment Engineer：仅可编辑 `engineerOwner` 为自己的设备。
- Sales Manager、Sales User：保留查看和 Booking 转入权限，不可编辑 Installed Tool。
- 新增独立 capability：`installed_tool:write`，不复用 `deal:write` 或 `service:write`。

## 编辑字段

- Serial Number（全局唯一）
- 设备型号
- 客户厂区（只能选择当前客户名下厂区）
- 现场位置
- 设备状态
- 负责工程师
- Software
- Firmware
- Configuration
- Warranty End
- Sales Order
- Contract

来源 Booking、来源 Opportunity、客户、Sales Owner 和设备 ID 只读。工程师不可更改负责工程师；演示员工170与 Boss 可以重新指派。

## 数据边界

- Mock Adapter 更新共享 Sales Repository 中的 Installed Tool 并持久化。
- Frappe Adapter 返回明确的 `NOT_IMPLEMENTED`。
- 本轮不编辑交付生命周期节点和附件记录。

## 验收

- 演示员工170和 Boss 在所有设备详情看到编辑入口并可保存。
- 演示员工14只能编辑分配给演示员工14的设备；演示员工15只能编辑分配给演示员工15的设备。
- Sales 不显示编辑入口，直接调用接口也被拒绝。
- 重复 Serial、跨客户厂区、工程师越权和无权限更新均被拒绝。
- 保存后列表、筛选和详情立即显示新值，刷新后仍保留。
