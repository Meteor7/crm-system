# Opportunity Strategy 与设备工程师 Mock 闭环设计

## 目标

在纯前端 Mock Demo 中补齐 Opportunity Strategy 的新增、编辑、Stakeholder 和 Action 操作闭环，同时新增“设备工程师”身份，并为有权限的销售身份开放客户档案与商机新增能力。

本功能不连接 Frappe、后端 API、数据库或 Docker。所有写操作仅保存在当前浏览器会话内存中，刷新页面后恢复初始 Mock 数据。

## 角色与权限

| 身份 | 客户档案 | Opportunity Strategy | Demo / Wafer / Test Run |
| --- | --- | --- | --- |
| CRM Administrator | 查看、新增、编辑 | 查看、新增、编辑；维护 Stakeholder 与 Action | 全部 Demo 操作 |
| Sales Manager | 查看团队范围；新增、编辑 | 查看团队范围；新增、编辑；维护 Stakeholder 与 Action | 团队范围操作 |
| Sales User | 查看本人范围；新增、编辑 | 查看本人范围；新增、编辑；维护 Stakeholder 与 Action | 本人范围操作 |
| Management Viewer | 全公司只读 | 全公司只读 | 全公司只读 |
| FAE / Applied Engineer | 分配范围只读 | 分配范围只读 | 新增、编辑 Demo、Wafer、Test Run |
| Equipment Engineer | 分配范围只读 | 分配范围只读 | 新增、编辑 Demo、Wafer、Test Run |

设备工程师不创建或修改客户与商机，主要负责 Demo Execution、Wafer Sample、Test Run 和相关设备验证数据。

## 页面交互

### 身份切换

在现有身份切换器中增加“设备工程师”预设身份。切换后：

- 导航根据现有 Capability 机制重新计算。
- 客户、商机和技术数据按分配客户范围重新加载。
- Demo、Wafer 和 Test Run 显示可写操作。
- 客户档案和 Opportunity Strategy 仅显示查看能力。

### 客户档案

CRM Administrator、Sales Manager 和 Sales User 看到“新增客户”按钮。点击后使用现有风格的 Modal 完成最小主数据录入：

- Customer ID 自动生成。
- 客户名称、业务分段、地区、城市、负责人为必填项。
- 新增成功后立即进入当前列表，并受当前身份数据范围控制。

Management Viewer、FAE 和 Equipment Engineer 不显示新增或编辑入口。

### Opportunity Strategy

有写权限的销售身份看到“新增商机”和“编辑商机”按钮。新增/编辑统一采用现有风格的 Modal，不增加独立路由。

商机表单包含：

- 客户与 Site。
- 标题、Owner、Stage、Forecast Category。
- 金额、币种、Probability、预计 PO、Shipment 和 FAT 日期。
- Tool Type、Sale Type、Sub Region、Payment Milestones、Competition。
- Strength、Red Flag、Information Needed。

保存后列表、指标卡和当前详情立即基于同一份 Mock 状态重新计算。

### Stakeholder 闭环

有商机写权限的身份可以：

- 新增 Stakeholder。
- 编辑 Buying Role、Influence、Attitude 和 Coverage Evidence。
- 删除机会级 Stakeholder 关系。

Stakeholder 只属于当前 Opportunity，不修改客户联系人主档。保存后自动写入该商机 Change History。

### Action 闭环

有商机写权限的身份可以：

- 新增 Action，并设置 Title、Owner、Due Date 和 Status。
- 编辑 Action。
- 在 Open 与 Done 间切换。
- 删除 Action。

所有动作更新后立即刷新逾期/临期指标，并写入 Change History。

## Mock 数据与状态

扩展现有 `CrmApi` 前端契约，增加客户和 Opportunity Strategy 的 Mock 写方法。Mock Adapter 持有会话级可变副本，所有页面通过同一活动 API 实例访问。

- 同一身份和同一页面会话内，路由切换后数据仍保留。
- 身份切换后使用该身份对应的数据范围。
- 浏览器刷新后重新创建 Mock Adapter，恢复初始数据。
- 不写入 localStorage、Cookie、文件或后端。

新增记录继续使用既有编码标准：`ACC-xxx`、`SITE-xxx`、`OPP-xxx`。关联必须使用 ID，不以名称作为唯一键。

## 校验与错误处理

- 必填字段缺失时阻止保存并显示字段级错误。
- 金额不得小于 0，Probability 必须为 0–100。
- Opportunity 的 Customer 和 Site 必须来自当前身份可访问范围。
- Management Viewer、FAE 和 Equipment Engineer 的客户/商机写调用在 Mock Adapter 层同样拒绝，不能只依赖隐藏按钮。
- 保存失败时保留表单内容并显示错误，不改变原记录。

## 验收标准

1. 身份切换器中出现 Equipment Engineer，并显示对应中文身份名称。
2. Equipment Engineer 可查看分配客户和商机，但无客户或商机新增、编辑按钮。
3. Equipment Engineer 可新增或编辑 Demo、Wafer 和 Test Run。
4. CRM Administrator、Sales Manager、Sales User 可新增客户和商机。
5. Opportunity Strategy 可新增和编辑 Stakeholder、Action，并可完成或删除 Action。
6. 商机相关操作产生可见的 Change History。
7. 指标卡在商机或 Action 变更后即时重新计算。
8. Management Viewer 保持只读，Mock Adapter 对越权写入返回权限错误。
9. 路由切换后 Mock 变更仍存在，浏览器刷新后恢复初始数据。
10. 既有权限测试、页面测试、类型检查和生产构建通过。

## 非目标

- 不修改 `backend` 目录。
- 不调用已有 Frappe 保存 API。
- 不启动 Docker、数据库或后端服务。
- 不实现持久化、真实登录、真实审批或多人协作同步。
- 不新增独立商机编辑路由或第三方依赖。
