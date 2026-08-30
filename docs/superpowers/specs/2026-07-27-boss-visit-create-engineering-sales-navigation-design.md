# Boss 新建拜访与工程角色 Sales 导航隔离设计

## 目标

1. 为 Boss（`Management Viewer`）增加“新建拜访”权限。
2. FAE 与设备工程师不再看到左侧完整的“Sales 模块”导航分组。

## 权限设计

- 新增细粒度能力 `visit:create`。
- `CRM Administrator`、`Management Viewer`、`Sales Manager`、`Sales User` 拥有 `visit:create`。
- `FAE / Applied Engineer` 与 `Equipment Engineer` 不拥有 `visit:create`。
- `visit:create` 只控制新建拜访。
- `visit:write` 继续控制编辑已有拜访、完成拜访、提交纪要和完成 Action。
- `visit:review` 继续控制经理审核。
- Boss 不获得 `visit:write` 或 `visit:review`，因此创建完成后仍保持只读。

## 页面与 API 行为

- “新建拜访”按钮改由 `visit:create` 控制。
- Mock API 的 `createVisit` 同样校验 `visit:create`，并继续执行客户范围和字段校验。
- Mock API 的 `updateVisit` 保持原有 `visit:write` / `visit:review` 校验。
- Boss 创建的拜访状态为 `Planned`，保存后显示在拜访列表及关联客户数据中。
- 本次只承诺 Mock Demo 写入；Frappe Adapter 的 Visit 写入仍为 `NOT_IMPLEMENTED`。

## 工程角色导航隔离

- “Sales 模块”导航分组增加角色可见性限制。
- `FAE / Applied Engineer` 与 `Equipment Engineer` 不渲染该分组及其中的：
  - 客户档案
  - Opportunities & Booking
  - 拜访与 Action
- 工程角色现有底层只读能力暂不撤销，避免 Demo Request、Demo Test、Installed Tools 等工程页面读取客户关联信息时中断。
- 本次要求是导航不可见，不扩展为直接 URL 的全局路由封锁。
- 身份切换后的允许路径必须使用相同的可见导航结果，避免停留在已隐藏的 Sales 页面。

## 影响文件

- `src/types/crm.ts`
- `src/domain/permissions.ts`
- `src/domain/permissions.test.ts`
- `src/api/mock-adapter.ts`
- `src/api/mock-adapter.test.ts`
- `src/pages/VisitsPage.vue`
- `src/pages/customer-operations.test.ts`
- `src/app/navigation.ts`
- `src/app/AppShell.vue`
- `src/app/AppShell.test.ts`

## 验收标准

- Boss 左侧仍能看到“拜访与 Action”，进入后能看到“新建拜访”。
- Boss 可成功创建一条 `Planned` 拜访。
- Boss 创建后看不到编辑、完成拜访、提交纪要、经理审核和完成 Action 按钮。
- Mock API 允许 Boss 调用 `createVisit`，但仍拒绝 Boss 调用普通 `updateVisit`。
- FAE 和设备工程师左侧不显示“Sales 模块”及其三个入口。
- FAE 和设备工程师仍能使用原有 Demo 与工程模块。
- 销售经理、销售人员和管理员的拜访创建能力保持不变。
- 权限、Mock API、客户运营页面和 AppShell 聚焦测试通过。
- 类型检查、构建和当前 `4173` 页面验证通过。
