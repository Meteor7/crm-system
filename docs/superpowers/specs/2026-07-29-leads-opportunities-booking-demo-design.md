# Leads&Opportunities 与 Booking 原型 Demo 设计

## 目标

在现有 Vue 3 + TypeScript + Mock CRM Demo 中落地一套与高保真图一致、同时适配现有系统能力的线索到订单流程。

页面、左侧导航和标题统一使用精确名称 `Leads&Opportunities`，不使用“Sales 工作区”作为产品名称。`Booking` 保持独立左侧模块和独立路由。

本轮交付是可操作的前端 Mock Demo，不代表 Frappe 正式后端、数据库、鉴权审计或持久化接口已经完成。

## 信息架构

### 左侧导航

- `Leads&Opportunities`：进入 `/leads-opportunities`。
- `Booking`：进入 `/booking`。
- 原 `/opportunities-booking`、`/opportunity-strategy` 和 `/pipeline` 兼容重定向到新入口。
- FAE / Applied Engineer 与 Equipment Engineer 继续遵循现有导航隐藏规则。

### Leads&Opportunities

页面内使用两个紧凑切换项：

1. `Leads`
2. `Opportunities`

默认显示 `Leads`。切换状态写入 `?view=leads` 或 `?view=opportunities`，允许刷新和复制链接后保持当前视图。

### Booking

Booking 不出现在 `Leads&Opportunities` 的页内切换中。它拥有独立页面标题、指标、筛选、列表和新增/编辑入口。

## 页面设计

### Leads 列表

列表采用高保真图中的紧凑企业表格，但复用系统现有颜色、按钮、状态标记、空状态和错误状态。

显示字段：

- 姓名
- 公司与职位
- 电话与邮箱
- Lead Source
- Lead Status
- Owner
- 最近跟进时间

支持：

- 搜索姓名、公司、邮箱和电话
- 按状态、来源和 Owner 筛选
- 新建和编辑 Lead
- 点击行进入 Lead 详情
- 无数据、加载失败和权限拒绝状态

Lead 状态固定为：

- `New`
- `Working`
- `Qualified`
- `Nurturing`
- `Disqualified`
- `Converted`

### Lead 详情

Lead 详情使用独立路由 `/leads/:leadId`，复用 Contact 详情页的页面骨架、信息分区、时间线和操作区视觉，不复用 Contact 数据对象。

详情显示：

- 基础信息：姓名、公司、职位、联系方式、来源、Owner
- 资格判断：Fit Score 与确认项
- 初次联系备注
- 跟进时间线
- 编辑入口
- Convert 入口

无效或已删除的 Lead ID 显示可恢复错误状态，并提供返回 `Leads&Opportunities` 的按钮。

### Lead 转换

仅 `Qualified` 且未转换的 Lead 可以执行 Convert。

转换结果：

1. 按公司名称匹配并复用已有 Account；无匹配时创建 Account。
2. 按邮箱匹配并复用已有 Contact；无匹配时创建 Contact。
3. 创建一条 Opportunity，并关联 Account、Contact 和原 Lead。
4. 将 Lead 状态改为 `Converted`，记录转换后的 Account、Contact、Opportunity ID。
5. 重复点击 Convert 返回同一组结果，不重复创建数据。

Convert 对话框允许填写 Opportunity 名称、预计金额和预计成交日期。转换成功后进入 `Opportunities` 视图并选中新 Opportunity。

### Opportunities

Opportunities 首屏使用高保真图中的阶段管道和金额摘要，保留现有系统的 Opportunity 深度能力：

- 商机编辑
- Stakeholder
- Action
- Commercial Forecast
- Change History
- Strength、Red Flag、Information Needed

管道卡片显示 Stage、Probability、Amount、Close Date 和 Next Action。选中卡片后在同一页面下方显示现有策略详情，不新增重复详情路由。

### Booking

独立 Booking 页面复用现有 `BookingEditorModal` 和 Mock API 写入能力。

列表显示：

- Booking ID
- Customer / Opportunity
- Type
- Amount
- Delivery / DDL
- Status
- Owner
- Source

来源规则：

- `Equipment`：默认从 `Won` Opportunity 创建，必须保存 `sourceOpportunityId`。
- `Renewal` 或 `Maintenance`：允许直接创建，但必须选择来源类型并填写原因。
- 编辑已有 Booking 时保留原来源信息。

## 数据与接口

### Lead 数据模型

新增 Mock 领域类型：

- `LeadStatus`
- `LeadSource`
- `LeadDto`
- `LeadInput`
- `ConvertLeadInput`
- `LeadConversionResult`

新增 `CrmApi` 契约：

- `listLeads(query)`
- `getLead(id)`
- `saveLead(input)`
- `convertLead(id, input)`

Mock Adapter 提供完整行为。Frappe Adapter 对新增写操作返回明确的 `NOT_IMPLEMENTED`，避免把 Demo 能力误报为正式后端能力。

### 状态保存

沿用现有共享 Mock repository 和浏览器 Demo 状态，不引入新依赖。Lead、Opportunity 和 Booking 使用同一活动 Mock API 实例，保证路由切换后转换结果仍可见。

## 权限

- CRM Administrator、Sales Manager：可新建、编辑和转换当前可见 Lead。
- Sales User：可新建 Lead；仅可编辑和转换本人 Owner 的 Lead。
- Management Viewer：只读。
- FAE / Applied Engineer、Equipment Engineer：不显示 `Leads&Opportunities` 和 `Booking` 导航。
- 页面隐藏按钮之外，Mock Adapter 同样执行写权限校验。

本轮复用现有 `deal:view` 与 `deal:write` capability，不扩张角色权限模型。

## Booking 崩溃防护

Booking 页面必须单独加载 Account、Contact、Opportunity 和 Booking 数据，任一辅助数据失败时：

- 已有 Booking 列表仍可显示。
- 新增/编辑入口在依赖数据不可用时禁用并说明原因。
- 页面显示内联错误，不抛出未处理异常。
- 空数据、无权限和网络错误均由现有 DataState/Workspace 状态组件呈现。
- 非法 Booking、Contact 或 Opportunity 关联显示“数据需要修复”，不访问未定义字段。

## 视觉适配

- 保留现有深海军蓝、青绿色、冷灰表面和中文字体栈。
- 页面密度、圆角、表格行高和按钮尺寸沿用现有 design-system token。
- 不增加横向产品级导航。
- `Leads&Opportunities` 页内切换只承担数据视图切换，不替代左侧导航。
- 使用真实半导体客户、设备和金额示例，不使用通用占位数据。
- 所有可交互控件具有 hover、pressed、focus、disabled 状态。

## 测试与验收

### 自动测试

1. Lead 列表搜索、筛选和状态显示。
2. Lead 详情复用页面骨架并处理无效 ID。
3. 非 Qualified Lead 不能转换。
4. Qualified Lead 转换后复用 Account、创建/复用 Contact、创建 Opportunity。
5. 重复转换不生成重复记录。
6. Sales User 不能转换其他 Owner 的 Lead。
7. `Leads&Opportunities` 与 `Booking` 导航和兼容重定向。
8. Equipment Booking 必须关联 Won Opportunity。
9. Renewal/Maintenance 直接 Booking 必须提供来源和原因。
10. Booking 辅助数据失败时页面不崩溃。

### 浏览器验收流程

1. 左侧进入 `Leads&Opportunities`。
2. 搜索并打开一条 Qualified Lead。
3. 完成 Convert。
4. 返回 Opportunities 并看到新商机。
5. 将测试商机视为 Won 来源创建 Booking。
6. 左侧进入独立 `Booking`。
7. 查看、筛选和编辑该 Booking。
8. 刷新页面并验证当前 Demo 状态与错误处理符合 Mock 边界。

### 完成标准

- `pnpm test` 的相关测试通过。
- `pnpm typecheck` 通过。
- `pnpm build` 通过。
- 桌面浏览器完成主链路，无空白页、框架错误覆盖层、未处理控制台错误或水平溢出。

## 非目标

- 不修改 backend 目录。
- 不实现 Frappe Lead DocType 或正式数据库持久化。
- 不增加第三方依赖。
- 不重写现有 Contact、Account、Opportunity Strategy 或 Demo 模块。
- 不清理与本需求无关的工作树改动。
