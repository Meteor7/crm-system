# Demo 员工权限视角设计

## 目标与边界

在纯前端 Mock Demo 中提供可切换的员工身份，用于演示不同角色进入 QIHENG Demo CRM 后可见的导航、数据范围和操作权限。

- 不创建真实账号。
- 不接入 Frappe 登录、后端权限或数据库。
- 身份只保存在当前页面内存，刷新后恢复 CRM Administrator。
- 前端权限仅用于 Demo 表现，不作为未来后端授权方案。

## 交互设计

右上角现有员工信息改为可点击的身份切换器。点击后显示五个预设员工：

1. 演示员工24 — CRM Administrator
2. 演示经理01 — Management Viewer（界面显示“管理者权限”）
3. Demo Staff 06 — Sales Manager
4. Demo Staff 01 — Sales User
5. 演示员工14 — FAE / Applied Engineer

选择后立即执行：

- 更新姓名、头像缩写、角色中文名和团队。
- 根据角色 Capability 重新过滤左侧导航。
- 重新创建对应角色的 Mock API，使客户和业务数据按角色范围重新加载。
- 当前路由无权访问时，跳转至该角色第一个可访问入口。
- 关闭身份菜单，并显示“Demo 身份已切换”的轻量提示。

## 角色视角

| 角色 | 数据范围 | 主要可见内容 | 写操作 |
| --- | --- | --- | --- |
| CRM Administrator | 全公司 | 全部页面与配置能力 | 全部 Demo 操作 |
| Management Viewer | 全公司只读 | 管理驾驶舱、CRM、Demo、设备、服务、Procedure、文档 | 无业务写操作 |
| Sales Manager | 本团队 | 团队客户、商机、拜访、Demo、设备与服务摘要 | 团队业务操作与审批 |
| Sales User | 本人负责客户 | 本人客户、商机、拜访、Demo、设备与服务摘要 | 本人范围业务操作 |
| FAE / Applied Engineer | 分配给自己的客户与任务 | 技术需求、Demo、Installed Tool、Service Calendar、Procedure Run、Document Center | 工程评审、测试、服务与Procedure执行 |

## 页面保护

导航可见性继续以现有 Capability 为唯一前端判断来源。身份切换时：

1. 读取切换后角色的 Capability。
2. 计算该角色可见导航。
3. 如果当前页面仍可访问，保留当前页面并重新加载数据。
4. 如果当前页面不可访问，跳转到第一项可见导航。
5. 页面按钮继续使用现有 `app.can()` 判断，不额外维护第二套权限表。

## Mock 数据流

身份切换器调用应用 Store 的 `switchDemoIdentity()`：

1. 根据预设员工创建新的 `createMockApi({ role, userName, teamOwners, assignedAccountIds })`。
2. 用新 API 获取 Bootstrap。
3. 替换当前 Bootstrap 与活动 API。
4. 为子页面增加身份版本 Key，使当前页面重新挂载并重新读取对应范围数据。

所有状态仅存在内存中，不写入 localStorage、Cookie 或后端。

## 错误与安全处理

- 身份切换失败时保留原身份，并显示错误提示。
- 切换过程中禁用重复点击。
- 不显示或生成密码、Token、Cookie、邮箱登录凭据。
- 明确标注“Demo 身份切换”，避免被误认为真实权限管理。

## 验收标准

1. 右上角可以在五个身份之间切换。
2. Management Viewer 能看到管理驾驶舱，但看不到写操作。
3. Sales User 只能看到本人负责的数据，不显示 Procedure Run。
4. FAE 看不到管理驾驶舱，能看到 Service Calendar 和 Procedure Run。
5. 从管理驾驶舱切换到 FAE 时，系统自动跳转到 FAE 可访问页面。
6. 刷新浏览器后恢复默认 CRM Administrator。
7. 原有权限测试、101 项前端测试和生产构建继续通过。
